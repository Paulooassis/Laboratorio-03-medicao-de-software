import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from dora_selection.api import APIError, GitHubClient
from dora_selection.__main__ import main
from dora_selection.output import save_workflow_runs
from dora_selection.selection import (Window, WorkflowRunCollector, collect_workflow_repositories,
                                      monthly_periods, timestamp)


REPO = {"full_name": "owner/repo", "default_branch": "main", "included": True}
WINDOW = Window(timestamp("2026-01-01T00:00:00Z"), timestamp("2026-01-31T23:59:59Z"))


def run(i, **changes):
    return {"id": i, "workflow_id": 7, "name": "CI", "status": "completed", "conclusion": "success",
            "created_at": "2026-01-10T00:00:00Z", "run_started_at": "2026-01-10T00:01:00Z",
            "updated_at": "2026-01-10T00:02:00Z", "head_branch": "main", "event": "push", **changes}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.runs = [run(1)]
        self.client = Mock()
        self.client.get.side_effect = lambda *a, **k: ({"total_count": len({r["id"] for r in self.runs})}, {})
        self.client.pages.side_effect = lambda *a, **k: iter(self.runs)

    def collect(self, window=WINDOW):
        return WorkflowRunCollector(self.client, window).collect(REPO)

    def test_filters_and_fields(self):
        self.runs += [run(2, head_branch="dev"), run(3, event="pull_request"),
                      run(4, created_at="2025-12-31T23:59:59Z"), run(5, created_at="2026-02-01T00:00:00Z")]
        result = self.collect()
        self.assertTrue(result["complete"])
        workflow = result["workflows"][0]
        self.assertEqual(workflow["repository"], REPO["full_name"])
        self.assertEqual(workflow["workflow_id"], 7)
        self.assertEqual(len(workflow["runs"]), 1)
        item = workflow["runs"][0]
        self.assertEqual(item["classification"], "success")
        self.assertTrue({"id", "workflow_id", "name", "conclusion", "run_started_at", "updated_at",
                         "created_at", "branch", "event", "repository"} <= item.keys())
        params = self.client.get.call_args.args[1]
        self.assertEqual((params["branch"], params["event"]), ("main", "push"))

    def test_classifications_including_empty_and_in_progress(self):
        conclusions = ["success", "failure", "timed_out", "startup_failure", "cancelled", "skipped",
                       "neutral", "action_required", "stale", None, "", "unknown"]
        self.runs = [run(i, conclusion=c) for i, c in enumerate(conclusions)] + [run(20, status="in_progress")]
        result = self.collect()
        self.assertEqual(result["summary"], {"success": 1, "failure": 3, "ignored": 9, "total": 13})
        self.assertEqual([r["classification"] for r in result["workflows"][0]["runs"]],
                         ["success"] + ["failure"] * 3 + ["ignored"] * 9)

    def test_monthly_boundaries_leap_year_and_utc(self):
        window = Window(timestamp("2024-01-31T23:59:59Z"), timestamp("2024-03-01T00:00:00Z"))
        periods = list(monthly_periods(window))
        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[1], (timestamp("2024-02-01T00:00:00Z"), timestamp("2024-02-29T23:59:59Z")))
        december = list(monthly_periods(Window(timestamp("2025-12-31T23:59:59Z"), timestamp("2026-01-01T00:00:00Z"))))
        self.assertEqual(len(december), 2)
        local = list(monthly_periods(Window(timestamp("2026-01-31T21:00:00-03:00"), timestamp("2026-01-31T22:00:00-03:00"))))
        self.assertEqual(local[0][0], timestamp("2026-02-01T00:00:00Z"))

    def test_month_queries_and_cross_period_duplicates(self):
        window = Window(WINDOW.start, timestamp("2026-02-28T23:59:59Z"))
        self.runs += [run(1), run(2, workflow_id=8, created_at="2026-02-01T00:00:00Z")]
        result = self.collect(window)
        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual(len(result["workflows"]), 2)
        self.assertEqual([c.args[1]["created"] for c in self.client.get.call_args_list],
                         ["2026-01-01T00:00:00Z..2026-01-31T23:59:59Z", "2026-02-01T00:00:00Z..2026-02-28T23:59:59Z"])

    def test_saturated_month_subdivides(self):
        self.client.get.side_effect = lambda path, params: ({"total_count": 1000 if params["created"] ==
            "2026-01-01T00:00:00Z..2026-01-31T23:59:59Z" else 1}, {})
        result = self.collect()
        self.assertTrue(result["complete"])
        self.assertEqual(self.client.get.call_count, 3)
        self.assertEqual(result["summary"]["total"], 1)

    def test_indivisible_saturation_is_explicit(self):
        self.client.get.side_effect = None
        self.client.get.return_value = {"total_count": 1500}, {}
        result = self.collect(Window(WINDOW.start, WINDOW.start))
        self.assertFalse(result["complete"])
        self.assertIn("saturado", result["errors"][0]["error"])

    def test_count_mismatch_is_not_silent(self):
        self.client.get.side_effect = None
        self.client.get.return_value = {"total_count": 2}, {}
        result = self.collect()
        self.assertFalse(result["complete"])
        self.assertEqual(result["workflows"], [])
        self.assertIn("incompleto", result["errors"][0]["error"])

    def test_error_month_and_repository_do_not_stop_others(self):
        def get(path, params):
            if "bad/repo" in path or params["created"].startswith("2026-01"):
                raise APIError("HTTP 403")
            return {"total_count": 1}, {}
        self.client.get.side_effect = get
        self.runs = [run(1, created_at="2026-02-10T00:00:00Z")]
        results = collect_workflow_repositories(self.client, Window(WINDOW.start, timestamp("2026-02-28T23:59:59Z")),
            [{**REPO, "full_name": "bad/repo"}, REPO, {**REPO, "full_name": "OWNER/REPO"}, {**REPO, "included": False}])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["summary"]["total"], 0)
        self.assertEqual(results[1]["summary"]["total"], 1)
        self.assertFalse(results[1]["complete"])
        self.assertTrue(results[1]["periods"][1]["complete"])

    def test_missing_branch_or_workflow_id(self):
        self.assertFalse(WorkflowRunCollector(self.client, WINDOW).collect({"full_name": "o/r"})["complete"])
        self.runs = [run(1, workflow_id=None)]
        self.assertFalse(self.collect()["complete"])

    def test_output_preserves_previous_and_nested_association(self):
        result = self.collect()
        with tempfile.TemporaryDirectory() as directory:
            first = save_workflow_runs(directory, [result], WINDOW)
            old = (first / "workflow_runs.json").read_bytes()
            second = save_workflow_runs(directory, [result], WINDOW)
            self.assertNotEqual(first, second)
            self.assertEqual((first / "workflow_runs.json").read_bytes(), old)
            data = json.loads(old)
            self.assertEqual(data[0]["workflows"][0]["runs"][0]["repository"], REPO["full_name"])

    @patch("dora_selection.__main__.GitHubClient")
    def test_cli(self, client):
        client.return_value = self.client
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout"):
            source = Path(directory) / "selected.json"
            source.write_text(json.dumps([REPO]))
            self.assertEqual(main(["--card", "3", "--input", str(source), "--start", "2026-01-01T00:00:00Z",
                "--end", "2026-01-31T23:59:59Z", "--output", str(Path(directory) / "out")]), 0)
            self.assertEqual(len(list((Path(directory) / "out").glob("run-*/workflow_runs.json"))), 1)


class PaginationTests(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_actual_paginator_multiple_pages(self):
        client = GitHubClient()
        client.get = Mock(side_effect=[({"total_count": 101}, {}),
            ({"workflow_runs": [run(i) for i in range(100)]},
             {"Link": '<https://api.github.com/repos/owner/repo/actions/runs?page=2>; rel="next"'}),
            ({"workflow_runs": [run(99), run(100)]}, {})])
        result = WorkflowRunCollector(client, WINDOW).collect(REPO)
        self.assertTrue(result["complete"])
        self.assertEqual(result["summary"]["total"], 101)
        self.assertEqual(client.get.call_args_list[1].args[1]["per_page"], 100)


if __name__ == "__main__":
    unittest.main()
