"""Validação offline do sorteio e das planilhas cegas."""
import copy
import csv
import json
from collections import Counter

import pytest

from dora_selection.gold_sample import MANUAL_VALUES, main, observation_window, sample_records
from dora_selection.selection import Window, timestamp


@pytest.fixture
def dataset():
    repositories = [{"full_name": f"owner/repo{i:03}", "included": True,
                     "is_corrective": True, "project_type": "automatic"} for i in range(65)]
    deployments = []
    for repo in repositories:
        releases = [{"release_id": i, "tag_name": f"v/{i}+#", "published_at": f"2025-01-{i:02}T00:00:00Z",
                     "draft": False, "prerelease": False, "comparison_status": "completed",
                     "previous_tag_name": f"v/{i-1}", "is_corrective": True,
                     "hotfix": True} for i in range(1, 9)]
        deployments.append({"full_name": repo["full_name"], "releases": releases, "errors": []})
    window = Window(timestamp("2025-01-01T00:00:00Z"), timestamp("2025-01-31T00:00:00Z"))
    return repositories, deployments, window


def test_reproducibility_and_counts(dataset):
    repositories, deployments, window = dataset
    expected = sample_records(*dataset)
    assert sample_records(*dataset) == expected
    assert sample_records(repositories[::-1], deployments[::-1], window) == expected
    shuffled = copy.deepcopy(deployments)
    for repo in shuffled:
        repo["releases"].reverse()
        repo["releases"].append(copy.deepcopy(repo["releases"][0]))
    assert sample_records(repositories + repositories, shuffled, window) == expected
    repo_rows, release_rows, _ = expected
    assert len(repo_rows) == len({r["repository"] for r in repo_rows}) == 60
    assert len(release_rows) == 300
    assert set(Counter(r["repository"] for r in release_rows).values()) == {5}
    assert len({(r["repository"], r["release_id"]) for r in release_rows}) == 300
    assert sample_records(*dataset, seed=43) != expected


def test_release_filters_and_censoring(dataset):
    repositories, deployments, window = dataset
    expected = sample_records(*dataset)
    for repo in deployments:
        for changes in ({"draft": True}, {"prerelease": True},
                        {"published_at": "2025-01-25T00:00:00Z"},
                        {"published_at": "2024-12-31T00:00:00Z"}):
            repo["releases"].append({**repo["releases"][0], "release_id": 99, **changes})
    assert sample_records(repositories, deployments, window) == expected
    for repo in deployments:
        repo["releases"] = [{**repo["releases"][0], "published_at": "2025-01-24T00:00:00Z"}]
    assert len(sample_records(*dataset, count=1, releases_per_repository=1)[1]) == 1


def test_insufficient_and_excluded_repositories(dataset):
    repositories, deployments, window = dataset
    with pytest.raises(ValueError, match="60 repositórios"):
        sample_records(repositories[:59], deployments, window)
    for row in repositories[59:]:
        row["included"] = False
    with pytest.raises(ValueError, match="disponíveis: 59"):
        sample_records(*dataset)


@pytest.mark.parametrize("problem", ["few", "missing", "flags", "compare", "conflict", "collection"])
def test_incomplete_releases(dataset, problem):
    repositories, deployments, window = dataset
    for repo in deployments:
        if problem == "few":
            repo["releases"] = repo["releases"][:4]
        elif problem == "missing":
            del repo["releases"]
        elif problem == "flags":
            del repo["releases"][0]["draft"]
        elif problem == "compare":
            repo["releases"][0]["comparison_status"] = "not_found"
        elif problem == "conflict":
            repo["releases"].append({**repo["releases"][0], "tag_name": "conflict"})
        else:
            repo["errors"] = [{"stage": "releases"}]
    with pytest.raises(ValueError):
        sample_records(repositories, deployments, window)


def write_inputs(tmp_path, dataset):
    repositories, deployments, window = dataset
    source = tmp_path / "selected.json"
    releases = tmp_path / "deployments.json"
    source.write_text(json.dumps(repositories), encoding="utf-8")
    releases.write_text(json.dumps(deployments), encoding="utf-8")
    (tmp_path / "summary.json").write_text(json.dumps({"window_start": window.start.isoformat(),
                                                     "window_end": window.end.isoformat()}), encoding="utf-8")
    return ["--input", str(source), "--releases", str(releases), "--output", str(tmp_path / "gold")]


def test_cli_outputs_blinding_and_urls(tmp_path, dataset, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Nenhuma consulta à API deve ocorrer")
    monkeypatch.setattr("dora_selection.api.GitHubClient.get", forbidden)
    args = write_inputs(tmp_path, dataset)
    assert main(args) == 0
    directory = tmp_path / "gold"
    evaluators = [(directory / f"evaluator_{i}.csv").read_bytes() for i in range(1, 4)]
    assert evaluators[0] == evaluators[1] == evaluators[2]
    with (directory / "evaluator_1.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 300
    for row in rows:
        assert all(row[field] == "" for field in MANUAL_VALUES)
        assert "hotfix" not in row
        assert "automatic" not in row.values()
        identity = int(row["release_id"])
        base = row["repository_url"]
        assert row["release_url"] == f"{base}/releases/tag/v%2F{identity}%2B%23"
        assert row["commits_url"] == f"{base}/compare/v%2F{identity-1}...v%2F{identity}%2B%23"
    metadata = json.loads((directory / "sample_metadata.json").read_text(encoding="utf-8"))
    assert metadata["seed"] == 42
    assert metadata["total_releases"] == 300
    assert len(metadata["inputs"]["repositories"]["sha256"]) == 64
    with pytest.raises(SystemExit):
        main(args)
    assert (directory / "evaluator_1.csv").read_bytes() == evaluators[0]


def test_no_partial_output(tmp_path, dataset, capsys):
    dataset[0].clear()
    args = write_inputs(tmp_path, dataset)
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert "60 repositórios" in capsys.readouterr().err
    assert not (tmp_path / "gold").exists()


def test_csv_input(tmp_path, dataset):
    args = write_inputs(tmp_path, dataset)
    source = tmp_path / "selected.csv"
    with source.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["full_name", "included"])
        writer.writeheader()
        writer.writerows({"full_name": row["full_name"], "included": row["included"]}
                         for row in reversed(dataset[0]))
    args[1] = str(source)
    assert main(args) == 0


def test_window_validation(tmp_path):
    path = tmp_path / "deployments.json"
    with pytest.raises(ValueError, match="Janela indisponível"):
        observation_window(path)
    with pytest.raises(ValueError, match="juntos"):
        observation_window(path, "2025-01-01T00:00:00Z")
    summary = {"window_start": "2025-01-01T00:00:00Z", "window_end": "2025-01-31T00:00:00Z"}
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="difere"):
        observation_window(path, "2025-01-02T00:00:00Z", summary["window_end"])


def test_first_historical_release_uses_collected_sha(dataset):
    repositories, deployments, window = dataset
    for repo in deployments:
        repo["releases"] = [{**repo["releases"][0], "comparison_status": "no_previous_release",
                             "previous_release_id": None, "previous_tag_name": None,
                             "commit_sha": "abc123"}]
    rows = sample_records(repositories, deployments, window, count=1, releases_per_repository=1)[1]
    assert rows[0]["commits_url"] == f"https://github.com/{rows[0]['repository']}/commits/abc123"
    for repo in deployments:
        repo["releases"][0]["commit_sha"] = None
    with pytest.raises(ValueError, match="SHA da primeira release"):
        sample_records(repositories, deployments, window, count=1, releases_per_repository=1)
