import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from dora_selection.api import APIError, GitHubClient
from dora_selection.selection import CandidateSearch, MetadataCollector, Window, classify_run, exclusion, funnel, timestamp
from dora_selection.output import save_output
from dora_selection.__main__ import main


DATE = "2026-01-10T00:00:00Z"
REPO = {"id": 1, "full_name": "owner/repo", "html_url": "https://github.com/owner/repo",
        "stargazers_count": 1500, "language": None, "created_at": "2020-01-01T00:00:00Z", "default_branch": "main"}


def run(i, **kwargs):
    return {"id": i, "head_branch": "main", "event": "push", "created_at": DATE,
            "status": "completed", "conclusion": "success", **kwargs}


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(timestamp("2026-01-01T00:00:00Z"), timestamp("2026-02-01T00:00:00Z"))
        self.client = Mock()
        self.client.get.side_effect = lambda path, params: ([{"login": "person"}], {"Link": '<https://api.github.com/repos/owner/repo/contributors?per_page=1&page=17>; rel="last"'}) if path.endswith("contributors") else ({"total_count": len({r["id"] for r in self.runs})}, {})
        self.workflows = [{"id": 1}]
        self.releases = [{"draft": False, "prerelease": False, "published_at": DATE} for _ in range(5)]
        self.runs = [run(i) for i in range(50)]
        self.client.pages.side_effect = lambda path, params=None, key=None: iter(self.workflows if path.endswith("workflows") else self.releases if path.endswith("releases") else self.runs)

    def collect(self):
        return MetadataCollector(self.client, self.window).collect(REPO)

    def test_included_and_metadata(self):
        row = self.collect()
        self.assertTrue(row["included"])
        self.assertEqual(row["contributors"], 17)
        self.assertEqual(row["default_branch"], "main")
        self.assertIsNone(row["language"])

    def test_no_actions(self):
        self.workflows = []
        self.assertEqual(self.collect()["exclusion_reason"], "no_github_actions")

    def test_insufficient_releases_and_validity(self):
        self.releases[0]["prerelease"] = True
        self.releases.extend([{"draft": True, "prerelease": False, "published_at": DATE},
                              {"draft": False, "prerelease": False, "published_at": "2025-01-01T00:00:00Z"},
                              {"draft": False, "prerelease": False, "published_at": None}])
        row = self.collect()
        self.assertEqual(row["valid_releases"], 4)
        self.assertEqual(row["exclusion_reason"], "insufficient_releases")

    def test_insufficient_runs_and_filters(self):
        self.runs = [run(i) for i in range(49)] + [run(50, head_branch="dev"), run(51, event="pull_request"),
            run(52, created_at="2025-01-01T00:00:00Z"), run(53, conclusion="cancelled"), run(54, status="in_progress"), run(0)]
        row = self.collect()
        self.assertEqual(row["valid_workflow_runs"], 49)
        self.assertEqual(row["exclusion_reason"], "insufficient_workflow_runs")

    def test_classification(self):
        for conclusion in ("success", "failure", "timed_out", "startup_failure"):
            self.assertEqual(classify_run(run(1, conclusion=conclusion)), "success" if conclusion == "success" else "failure")
        for conclusion in ("cancelled", "skipped", "neutral", "action_required", "stale", None, "unknown"):
            self.assertIsNone(classify_run(run(1, conclusion=conclusion)))
        self.assertIsNone(classify_run(run(1, status="in_progress")))

    def test_error_and_missing_metadata(self):
        self.client.get.side_effect = APIError("HTTP 403")
        row = self.collect()
        self.assertFalse(row["included"])
        self.assertEqual(row["exclusion_reason"], "collection_error")
        self.assertIsNone(row["contributors"])
        self.assertEqual(MetadataCollector(self.client, self.window).collect({})["exclusion_reason"], "collection_error")

    def test_funnel(self):
        rows = []
        for actions, releases, runs in ((False, 5, 50), (True, 4, 50), (True, 5, 49), (True, 5, 50)):
            row = {"uses_github_actions": actions, "valid_releases": releases, "valid_workflow_runs": runs}
            row.update(exclusion_reason=exclusion(row), included=exclusion(row) is None)
            rows.append(row)
        result = funnel(rows, 6, 4)
        self.assertEqual([result[k] for k in ("candidates_found", "unique_repositories", "with_github_actions", "with_sufficient_releases", "with_sufficient_runs", "included")], [6, 4, 3, 2, 1, 1])
        self.assertEqual(sum(result["discarded_by_reason"].values()), 3)

    def test_window_boundaries(self):
        self.assertTrue(self.window.contains("2026-01-01T00:00:00Z"))
        self.assertTrue(self.window.contains("2026-02-01T00:00:00Z"))
        self.assertFalse(self.window.contains(None))
        with self.assertRaises(ValueError):
            timestamp("2026-01-01")

    def test_runs_split_and_deduplicate(self):
        def get(path, params):
            if path.endswith("contributors"):
                return [], {}
            return {"total_count": 1500 if params["created"] == "2026-01-01T00:00:00Z..2026-02-01T00:00:00Z" else 50}, {}
        self.client.get.side_effect = get
        row = self.collect()
        self.assertEqual(row["valid_workflow_runs"], 50)
        self.assertEqual(sum(call.args[0].endswith("runs") for call in self.client.pages.call_args_list), 2)

    def test_output(self):
        with tempfile.TemporaryDirectory() as directory:
            row = self.collect()
            save_output(directory, [row], funnel([row], 1, 1))
            from pathlib import Path
            self.assertEqual(json.loads((Path(directory) / "selected.json").read_text())[0]["contributors"], 17)
            self.assertIn("exclusion_reason", (Path(directory) / "repositories.csv").read_text())


class SearchTests(unittest.TestCase):
    def test_pagination_and_duplicates(self):
        client = Mock()
        client.get.side_effect = [({"total_count": 101, "items": [REPO]}, {}), ({"total_count": 101, "items": [REPO]}, {}),
                                 ({"items": [REPO, {**REPO, "id": 2, "full_name": "o/b"}]}, {})]
        search = CandidateSearch(client)
        self.assertEqual(len(list(search.candidates())), 2)
        self.assertEqual((search.found, search.unique), (3, 2))
        self.assertEqual(client.get.call_args.args[1]["page"], 2)

    def test_star_partition(self):
        client = Mock()
        client.get.side_effect = [({"total_count": 1001, "items": [{**REPO, "stargazers_count": 1002}]}, {}),
            ({"total_count": 1001, "items": []}, {}), ({"total_count": 1, "items": [REPO]}, {}),
            ({"total_count": 0, "items": []}, {})]
        self.assertEqual(len(list(CandidateSearch(client).candidates())), 1)
        queries = [c.args[1]["q"] for c in client.get.call_args_list]
        self.assertIn("is:public stars:1002..1002", queries)
        self.assertIn("is:public stars:1001..1001", queries)

    def test_date_partition_and_incomplete(self):
        client = Mock()
        client.get.side_effect = [({"total_count": 1001, "items": [{**REPO, "stargazers_count": 1001}]}, {}),
            ({"total_count": 1001, "items": []}, {}), ({"total_count": 1, "items": [REPO]}, {}),
            ({"total_count": 0, "items": []}, {})]
        self.assertEqual(len(list(CandidateSearch(client).candidates())), 1)
        self.assertIn("created:", client.get.call_args.args[1]["q"])
        client.get.side_effect = None
        client.get.return_value = {"incomplete_results": True}, {}
        with self.assertRaises(APIError):
            list(CandidateSearch(client).candidates())


class ClientTests(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_link_pagination(self):
        client = GitHubClient()
        client.get = Mock(side_effect=[({"items": [1]}, {"Link": '<https://api.github.com/page2>; rel="next"'}), ({"items": [2]}, {})])
        self.assertEqual(list(client.pages("/test", key="items")), [1, 2])

    @patch.dict(os.environ, {}, clear=True)
    def test_token_required(self):
        with self.assertRaises(APIError):
            GitHubClient()

    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_http_error_and_host(self):
        with patch("dora_selection.api.urlopen", side_effect=HTTPError("url", 403, "Forbidden", {}, None)):
            with self.assertRaisesRegex(APIError, "HTTP 403") as caught:
                GitHubClient().get("/search/repositories")
            self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(APIError):
            GitHubClient().get("https://example.com")

    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_request_headers_and_invalid_json(self):
        response = Mock()
        response.headers = {}
        response.read.return_value = b'{"items": []}'
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        with patch("dora_selection.api.urlopen", return_value=context) as opener:
            self.assertEqual(GitHubClient().get("/search/repositories", {"q": "stars:>1000"})[0], {"items": []})
            request = opener.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture-only")
            self.assertTrue(request.full_url.startswith("https://api.github.com/"))
            response.read.return_value = b'not-json'
            with self.assertRaises(APIError):
                GitHubClient().get("/search/repositories")

    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_invalid_page_is_not_silent(self):
        client = GitHubClient()
        client.get = Mock(return_value=({"wrong_key": []}, {}))
        with self.assertRaises(APIError):
            list(client.pages("/actions/runs", key="workflow_runs"))


class PipelineTests(unittest.TestCase):
    @patch("dora_selection.__main__.GitHubClient")
    @patch("dora_selection.__main__.CandidateSearch")
    def test_insufficient_sample_and_search_error_are_persisted(self, search, client):
        from pathlib import Path
        for failure in (False, True):
            search.return_value.found = 0
            search.return_value.unique = 0
            search.return_value.candidates.side_effect = APIError("HTTP 403") if failure else None
            search.return_value.candidates.return_value = iter([])
            with tempfile.TemporaryDirectory() as directory, patch("sys.stdout"), patch("sys.stderr"):
                self.assertEqual(main(["--start", "2026-01-01T00:00:00Z", "--end", "2026-02-01T00:00:00Z", "--output", directory]), 1)
                summary = json.loads((Path(directory) / "funnel.json").read_text())
                self.assertFalse(summary["target_reached"])
                self.assertEqual(summary["stop_reason"], "search_error" if failure else "candidates_exhausted")

    @patch("dora_selection.__main__.GitHubClient")
    @patch("dora_selection.__main__.MetadataCollector")
    @patch("dora_selection.__main__.CandidateSearch")
    def test_reaches_100_and_continues_after_bad_repository(self, search, collector, client):
        search.return_value.candidates.return_value = iter([REPO] * 102)
        search.return_value.found = 101
        search.return_value.unique = 101
        good = {"full_name": "o/r", "url": "url", "stars": 2000, "language": None, "created_at": DATE,
                "default_branch": "main", "contributors": 1, "uses_github_actions": True,
                "valid_releases": 5, "valid_workflow_runs": 50, "included": True, "exclusion_reason": None, "error": None}
        collector.return_value.collect.side_effect = [{**good, "included": False, "exclusion_reason": "collection_error", "error": "HTTP 404"}] + [good] * 101
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(["--start", "2026-01-01T00:00:00Z", "--end", "2026-02-01T00:00:00Z", "--output", directory]), 0)
            from pathlib import Path
            self.assertEqual(len(json.loads((Path(directory) / "selected.json").read_text())), 100)
            self.assertEqual(collector.return_value.collect.call_count, 101)


if __name__ == "__main__":
    unittest.main()
