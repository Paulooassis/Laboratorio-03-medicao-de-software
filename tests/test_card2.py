import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from dora_selection.api import APIError, GitHubClient
from dora_selection.deployments import DeploymentCollector, collect_repositories
from dora_selection.output import save_deployments
from dora_selection.selection import Window, timestamp
from dora_selection.deployments import main


WINDOW = Window(timestamp("2026-01-01T00:00:00Z"), timestamp("2026-02-01T00:00:00Z"))


def release(n, **changes):
    return {"id": n, "tag_name": f"v{n}", "published_at": f"2026-01-{n:02d}T00:00:00Z",
            "draft": False, "prerelease": False, **changes}


def commit(n):
    return {"sha": f"sha{n}", "commit": {"author": {"date": "2025-12-10T00:00:00Z"},
            "committer": {"date": "2026-01-15T00:00:00Z"}, "message": f"Mensagem {n}\nDetalhes"}}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.releases = [release(3), release(1), release(2)]
        self.tags = [{"name": f"v{n}", "commit": {"sha": f"tagsha{n}"}} for n in (1, 2, 3)]
        def pages(path, params=None, key=None):
            if path.endswith("/releases"):
                return iter(self.releases)
            if path.endswith("/tags"):
                return iter(self.tags)
            return iter([commit(1), commit(2)])
        self.client.pages.side_effect = pages

    def collect(self, tag_dates=False):
        return DeploymentCollector(self.client, WINDOW, tag_dates).collect("owner/repo")

    def test_window_drafts_prereleases_and_fields(self):
        self.releases += [release(4, draft=True), release(5, prerelease=True),
                          release(6, published_at="2025-12-31T23:59:59Z"),
                          release(7, published_at="2026-02-01T00:00:01Z")]
        result = self.collect()
        self.assertEqual([r["tag_name"] for r in result["releases"]], ["v1", "v2", "v3"])
        self.assertEqual([r["tag_name"] for r in result["prereleases"]], ["v5"])
        self.assertEqual(result["summary"]["drafts_excluded"], 1)
        self.assertEqual(result["summary"]["prereleases"], 1)
        self.assertEqual(result["prereleases"][0]["comparison_status"], "not_applicable")
        for r in result["releases"]:
            self.assertTrue({"tag_name", "published_at", "draft", "prerelease"} <= r.keys())
            self.assertFalse(r["draft"])
            self.assertFalse(r["prerelease"])

    def test_consecutive_releases_and_associations(self):
        result = self.collect()
        first, second, third = result["releases"]
        self.assertEqual(first["comparison_status"], "no_previous_release")
        self.assertEqual(first["commits"], [])
        self.assertEqual(result["summary"]["without_previous"], 1)
        self.assertEqual(second["previous_release_id"], first["release_id"])
        self.assertEqual(third["previous_release_id"], second["release_id"])
        comparisons = [c.args[0] for c in self.client.pages.call_args_list if "/compare/" in c.args[0]]
        self.assertEqual(comparisons, ["/repos/owner/repo/compare/tagsha1...tagsha2", "/repos/owner/repo/compare/tagsha2...tagsha3"])
        for r in (second, third):
            self.assertEqual(r["comparison_status"], "completed")
            for c in r["commits"]:
                self.assertEqual(c["repository"], "owner/repo")
                self.assertEqual(c["release_id"], r["release_id"])
                self.assertEqual(c["release_tag_name"], r["tag_name"])
                self.assertEqual(c["author_date"], "2025-12-10T00:00:00Z")
                self.assertIn("\nDetalhes", c["message"])

    def test_first_release_of_the_window_is_compared_with_the_one_before_the_window(self):
        self.tags.append({"name": "v6", "commit": {"sha": "tagsha6"}})
        self.releases += [release(6, published_at="2025-12-31T23:59:59Z"),
                          release(8, published_at="2025-06-01T00:00:00Z"),
                          release(9, published_at="2025-12-31T23:59:59Z", prerelease=True),
                          release(7, published_at="2026-02-01T00:00:01Z")]
        result = self.collect()
        first = result["releases"][0]
        # A anterior é a release mais recente antes da janela; pré-releases e as posteriores não contam.
        self.assertEqual([r["tag_name"] for r in result["releases"]], ["v1", "v2", "v3"])
        self.assertEqual((first["previous_release_id"], first["previous_tag_name"]), (6, "v6"))
        self.assertEqual(first["comparison_status"], "completed")
        self.assertEqual(len(first["commits"]), 2)
        self.assertEqual(result["summary"]["without_previous"], 0)
        self.assertEqual(result["summary"]["comparisons_completed"], 3)
        comparisons = [c.args[0] for c in self.client.pages.call_args_list if "/compare/" in c.args[0]]
        self.assertEqual(comparisons[0], "/repos/owner/repo/compare/tagsha6...tagsha1")

    def test_comparisons_in_parallel_keep_release_order(self):
        serial = self.collect()
        parallel = DeploymentCollector(self.client, WINDOW, workers=4).collect("owner/repo")
        self.assertEqual(parallel, serial)

    def test_prerelease_does_not_break_pairs(self):
        self.releases[2]["prerelease"] = True
        result = self.collect()
        self.assertEqual(result["releases"][1]["previous_tag_name"], "v1")
        self.assertEqual(result["summary"]["comparisons_completed"], 1)

    def test_tags_dates_and_shared_commit(self):
        self.tags.append({"name": "alias", "commit": {"sha": "tagsha1"}})
        self.client.get.return_value = commit(1), {}
        result = self.collect(tag_dates=True)
        self.assertEqual(len(result["tags"]), 4)
        self.assertEqual(self.client.get.call_count, 3)
        self.assertEqual(result["tags"][0]["commit_author_date"], "2025-12-10T00:00:00Z")
        self.assertEqual(result["releases"][0]["commit_sha"], "tagsha1")
        self.assertEqual(result["tags"][0]["repository"], "owner/repo")

    def test_tag_error_does_not_stop_comparisons(self):
        original = self.client.pages.side_effect
        def pages(path, *args, **kwargs):
            if path.endswith("/tags"):
                raise APIError("HTTP 403", 403)
            return original(path, *args, **kwargs)
        self.client.pages.side_effect = pages
        result = self.collect()
        self.assertEqual(result["errors"][0]["stage"], "tags")
        self.assertEqual(result["summary"]["comparisons_completed"], 2)
        self.assertTrue(any("/compare/v1...v2" in c.args[0] for c in self.client.pages.call_args_list))

    def test_404_count_and_next_consecutive_pair(self):
        original = self.client.pages.side_effect
        def pages(path, *args, **kwargs):
            if path.endswith("tagsha1...tagsha2"):
                raise APIError("HTTP 404", 404)
            return original(path, *args, **kwargs)
        self.client.pages.side_effect = pages
        result = self.collect()
        self.assertEqual(result["summary"]["releases_ignored_comparison_error"], 1)
        self.assertEqual(result["releases"][1]["comparison_status"], "not_found")
        self.assertEqual(result["releases"][1]["commits"], [])
        self.assertEqual(result["releases"][2]["previous_release_id"], 2)
        self.assertEqual(result["releases"][2]["comparison_status"], "completed")

    def test_partial_compare_not_saved_as_complete(self):
        original = self.client.pages.side_effect
        def broken():
            yield commit(1)
            raise APIError("HTTP 500", 500)
        def pages(path, *args, **kwargs):
            return broken() if "/compare/" in path else original(path, *args, **kwargs)
        self.client.pages.side_effect = pages
        result = self.collect()
        self.assertEqual(result["summary"]["releases_ignored_comparison_error"], 2)
        self.assertEqual(result["releases"][1]["commits"], [])

    def test_empty_or_single_release(self):
        for count in (0, 1):
            self.releases = [release(1)] * count
            result = self.collect()
            self.assertEqual(result["summary"]["comparisons_completed"], 0)
            self.assertEqual(result["summary"]["without_previous"], count)

    def test_repository_failure_continues_and_deduplication(self):
        original = self.client.pages.side_effect
        def pages(path, *args, **kwargs):
            if path.startswith("/repos/bad/repo"):
                raise APIError("HTTP 403", 403)
            return original(path, *args, **kwargs)
        self.client.pages.side_effect = pages
        results = collect_repositories(self.client, WINDOW, ["bad/repo", "owner/repo", "OWNER/REPO"])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["errors"])
        self.assertEqual(results[1]["summary"]["comparisons_completed"], 2)

    def test_tag_with_slash_encoded(self):
        self.tags = []
        self.releases = [release(1, tag_name="release/v1"), release(2, tag_name="release/v2")]
        self.collect()
        self.assertIn("/compare/release%2Fv1...release%2Fv2", self.client.pages.call_args.args[0])

    def test_missing_author_date_comparison_error(self):
        original = self.client.pages.side_effect
        broken = commit(1)
        broken["commit"]["author"] = None
        self.client.pages.side_effect = lambda path, *a, **k: iter([broken]) if "/compare/" in path else original(path, *a, **k)
        self.assertEqual(self.collect()["summary"]["releases_ignored_comparison_error"], 2)

    def test_no_overwrite(self):
        result = self.collect()
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "deployments.json"
            previous.write_text("existing")
            first = save_deployments(directory, [result], WINDOW)
            second = save_deployments(directory, [result], WINDOW)
            self.assertNotEqual(first, second)
            self.assertEqual(previous.read_text(), "existing")
            data = json.loads((first / "deployments.json").read_text(encoding="utf-8"))
            self.assertEqual(data[0]["releases"][1]["commits"][0]["release_id"], 2)
            self.assertEqual(json.loads((first / "summary.json").read_text())["repositories"], 1)


class PaginationTests(unittest.TestCase):
    @patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-only"})
    def test_real_paginator_over_250_commits_and_release_tag_pages(self):
        client = GitHubClient()
        requests = []
        def get(path, params=None):
            requests.append((path, params))
            if path.endswith("/releases"):
                return [release(2)], {"Link": '<https://api.github.com/release-page2>; rel="next"'}
            if path.endswith("release-page2"):
                return [release(1)], {}
            if path.endswith("/tags"):
                return [{"name": "v1", "commit": {"sha": "base"}}], {"Link": '<https://api.github.com/tag-page2>; rel="next"'}
            if path.endswith("tag-page2"):
                return [{"name": "v2", "commit": {"sha": "head"}}], {}
            if "/compare/" in path:
                self.assertEqual(params, {"page": 1, "per_page": 100})
                return {"commits": [commit(n) for n in range(100)]}, {"Link": '<https://api.github.com/compare-page2>; rel="next"'}
            if path.endswith("compare-page2"):
                return {"commits": [commit(n) for n in range(100, 200)]}, {"Link": '<https://api.github.com/compare-page3>; rel="next"'}
            if path.endswith("compare-page3"):
                return {"commits": [commit(n) for n in range(200, 301)]}, {}
            raise AssertionError(path)
        client.get = Mock(side_effect=get)
        result = DeploymentCollector(client, WINDOW).collect("owner/repo")
        commits = result["releases"][1]["commits"]
        self.assertEqual(len(commits), 301)
        self.assertEqual(commits[-1]["sha"], "sha300")
        self.assertEqual(result["summary"]["comparisons_completed"], 1)
        self.assertEqual(len(result["tags"]), 2)
        self.assertEqual(len(requests), 7)


class CommandTests(unittest.TestCase):
    @patch("dora_selection.deployments.GitHubClient")
    def test_cli_input_and_outputs(self, client):
        client.return_value.pages.return_value = iter([])
        with tempfile.TemporaryDirectory() as directory, patch("sys.stdout"):
            source = Path(directory) / "selected.json"
            source.write_text(json.dumps([{"full_name": "owner/repo", "included": True}, {"full_name": "other/repo", "included": False}]))
            self.assertEqual(main(["--input", str(source), "--start", "2026-01-01T00:00:00Z", "--end", "2026-02-01T00:00:00Z", "--output", str(Path(directory) / "out")]), 0)
            result_file = next((Path(directory) / "out").glob("run-*/deployments.json"))
            self.assertEqual(json.loads(result_file.read_text())[0]["full_name"], "owner/repo")
            self.assertEqual(source.read_text(), json.dumps([{"full_name": "owner/repo", "included": True}, {"full_name": "other/repo", "included": False}]))


if __name__ == "__main__":
    unittest.main()
