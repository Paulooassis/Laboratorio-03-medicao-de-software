"""Consultas economizadas sem truncar os dados usados nas métricas."""
from unittest.mock import Mock

import pytest

from dora_selection.api import APIError, GitHubClient
from dora_selection.selection import MetadataCollector, Window, timestamp
from dora_selection.deployments import DeploymentCollector


@pytest.fixture
def collector(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-only")
    client = GitHubClient()
    window = Window(timestamp("2025-01-01T00:00:00Z"), timestamp("2025-01-31T23:59:59Z"))
    return MetadataCollector(client, window)


def test_first_page_is_reused_and_all_pages_are_collected(collector):
    collector.client.get = Mock(side_effect=[
        ({"total_count": 101, "workflow_runs": [{"id": i} for i in range(100)]},
         {"Link": '<https://api.github.com/repos/owner/repo/actions/runs?page=2>; rel="next"'}),
        ({"workflow_runs": [{"id": 100}]}, {})])
    runs = list(collector._runs("/repos/owner/repo/actions/runs", "main",
                                collector.window.start, collector.window.end, True))
    assert len(runs) == 101
    assert collector.client.get.call_count == 2
    assert collector.client.get.call_args_list[0].args[1]["per_page"] == 100


def test_empty_period_needs_only_one_request(collector):
    collector.client.get = Mock(return_value=({"total_count": 0, "workflow_runs": []}, {}))
    assert list(collector._runs("/repos/owner/repo/actions/runs", "main",
                                collector.window.start, collector.window.end, True)) == []
    assert collector.client.get.call_count == 1


def test_count_validation_is_preserved(collector):
    collector.client.get = Mock(return_value=({"total_count": 2, "workflow_runs": [{"id": 1}]}, {}))
    with pytest.raises(APIError, match="Contagem"):
        list(collector._runs("/repos/owner/repo/actions/runs", "main",
                            collector.window.start, collector.window.end, True))


def test_workflow_existence_does_not_fetch_later_pages(collector):
    paths = []
    def pages(path, params=None, key=None):
        paths.append(path)
        if path.endswith("workflows"):
            yield {"id": 1}
            pytest.fail("A existência de Actions não exige baixar os demais workflows")
    collector.client.pages = pages
    collector.client.get = Mock(return_value=([], {}))
    repo = {"full_name": "owner/repo", "html_url": "https://github.com/owner/repo",
            "stargazers_count": 2000, "created_at": "2020-01-01T00:00:00Z", "default_branch": "main"}
    row = collector.collect(repo)
    assert row["uses_github_actions"] is True
    assert row["exclusion_reason"] == "insufficient_releases"


@pytest.mark.parametrize("shas, expected_calls", [(["a", "a", "a", "a"], 0),
                                                 (["a", "b", "a", "b"], 2)])
def test_identical_and_repeated_comparisons(collector, shas, expected_calls):
    releases = [{"id": i, "tag_name": f"v{i}", "published_at": f"2025-01-0{i}T00:00:00Z",
                 "draft": False, "prerelease": False} for i in range(1, 5)]
    tags = [{"name": f"v{i}", "commit": {"sha": sha}} for i, sha in enumerate(shas, 1)]
    comparisons = []
    def pages(path, params=None, key=None):
        if path.endswith("/releases"):
            return iter(releases)
        if path.endswith("/tags"):
            return iter(tags)
        comparisons.append(path)
        return iter([{"sha": "commit-sha", "commit": {
            "author": {"date": "2025-01-01T00:00:00Z"}, "message": "change"}}])
    collector.client.pages = pages
    result = DeploymentCollector(collector.client, collector.window, workers=4).collect("owner/repo")
    assert not result["errors"]
    assert len(comparisons) == expected_calls
    assert result["summary"]["comparisons_completed"] == 3
    for release in result["releases"][1:]:
        assert release["comparison_status"] == "completed"
        if expected_calls:
            assert release["commits"][0]["release_id"] == release["release_id"]
            assert release["commits"][0]["release_tag_name"] == release["tag_name"]
    if expected_calls:
        assert result["releases"][1]["commits"] is not result["releases"][3]["commits"]
