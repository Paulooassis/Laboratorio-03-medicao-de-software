"""Card 8: pipeline completo com o cliente real e apenas o transporte HTTP simulado."""
import csv
import json
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import pytest
from dora_selection.pipeline import main
from dora_selection.resilience import configure_logging


TOKEN = "fixture-only-token"
ROOT = Path(__file__).resolve().parents[1]
RELEASE_DAYS = (2, 9, 16, 23, 30)


class Response:
    """Resposta mínima no formato que o cliente consome de urlopen."""

    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self):
        return self.body


def repository(name, stars):
    return {"id": stars, "full_name": name, "html_url": "https://github.com/" + name,
            "stargazers_count": stars, "language": "Python", "created_at": "2020-01-01T00:00:00Z",
            "default_branch": "main"}


def workflow_runs():
    """50 runs de hora em hora; 5 falhas, cada uma recuperada pelo run seguinte."""
    runs = []
    for number in range(1, 51):
        created = f"2026-01-{5 + number // 24:02d}T{number % 24:02d}:00:00Z"
        runs.append({"id": number, "workflow_id": 7, "name": "CI", "status": "completed",
                     "conclusion": "failure" if number % 10 == 5 else "success", "created_at": created,
                     "run_started_at": created, "updated_at": created, "head_branch": "main",
                     "event": "push"})
    return runs


class FakeGitHub:
    """API mínima: dois repositórios elegíveis e um sem GitHub Actions."""

    def __init__(self, eligible=("owner/one", "owner/two")):
        self.eligible = set(eligible)
        self.repositories = [repository("owner/one", 5000), repository("owner/two", 4000),
                             repository("owner/noactions", 3000)]
        self.requests = []
        self.interrupt_on = None
        self.fail_search = False

    def __call__(self, request, timeout=None):
        url = urlsplit(request.full_url)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        self.requests.append(url.path)
        if self.interrupt_on and self.interrupt_on in url.path:
            raise KeyboardInterrupt
        return Response(self.route(url.path, query))

    def route(self, path, query):
        if path == "/search/repositories":
            items = [] if self.fail_search else self.repositories
            return {"total_count": len(self.repositories), "incomplete_results": self.fail_search,
                    "items": items[:int(query["per_page"])]}
        name, _, resource = path.removeprefix("/repos/").partition("/")
        owner, _, resource = resource.partition("/")
        full_name, active = f"{name}/{owner}", f"{name}/{owner}" in self.eligible
        if resource == "contributors":
            return [{"login": "dev"}]
        if resource == "actions/workflows":
            return {"workflows": [{"id": 7}] if active else []}
        if resource == "releases":
            return [{"id": day, "tag_name": f"v{day}", "published_at": f"2026-01-{day:02d}T12:00:00Z",
                     "draft": False, "prerelease": False} for day in RELEASE_DAYS] if active else []
        if resource == "tags":
            return [{"name": f"v{day}", "commit": {"sha": f"sha{day}"}} for day in RELEASE_DAYS]
        if resource == "actions/runs":
            runs = workflow_runs() if active else []
            return {"total_count": len(runs), "workflow_runs": runs[:int(query["per_page"])]}
        if resource.startswith("compare/"):
            day = int(resource.rpartition("sha")[2])
            # Um commit escrito 12 horas antes da publicação da release.
            return {"commits": [{"sha": f"{full_name}-{day}", "commit": {
                "author": {"date": f"2026-01-{day:02d}T00:00:00Z"}, "message": "change"}}]}
        raise AssertionError("rota inesperada: " + path)


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setattr("dora_selection.api.urlopen", fake)
    yield fake
    configure_logging(None, logging.CRITICAL)


@pytest.fixture
def execute(tmp_path, capsys):
    """Executa o comando único e devolve (código, resumo gravado)."""
    def run(*extra, target="2"):
        code = main(["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z",
                     "--target", target, "--output", str(tmp_path), *extra])
        capsys.readouterr()
        return code, json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    return run


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_single_command_runs_every_stage(github, execute, tmp_path):
    code, summary = execute()
    assert code == 0
    assert (summary["status"], summary["stage"]) == ("complete", "metrics")
    assert summary["selection"]["included"] == 2
    assert summary["selection"]["target_reached"] is True
    assert summary["deployments"] == {"repositories": 2, "repositories_with_errors": 0, "valid_releases": 10,
                                      "comparisons_completed": 8, "releases_ignored_comparison_error": 0}
    assert summary["workflow_runs"] == {"repositories": 2, "repositories_with_errors": 0, "success": 90,
                                        "failure": 10, "ignored": 0, "total": 100}
    assert summary["incomplete_repositories"] == []
    for name in ("selection/selected.json", "selection/repositories.csv", "selection/funnel.json",
                 "deployments.json", "workflow_runs.json", "metrics.json", "classification.json",
                 "dora.csv", "summary.json", "collection.log", "state/selection.jsonl",
                 "state/deployments.jsonl", "state/workflow_runs.jsonl"):
        assert (tmp_path / name).is_file(), name
    assert list((tmp_path / "cache").glob("*/*.json"))


def test_metrics_and_classification_of_the_known_sample(github, execute, tmp_path):
    execute()
    metrics = read(tmp_path / "metrics.json")
    assert [row["repository"] for row in metrics] == ["owner/one", "owner/two"]
    first = metrics[0]
    # 5 releases em 31 dias; 4 delas com um commit 12 h antes; 5 falhas em 50 runs.
    assert first["deployment_frequency"]["releases_per_week"] == pytest.approx(5 / (31 / 7))
    assert first["lead_time_per_commit"]["median_hours"] == 12.0
    assert first["lead_time_per_release"]["median_hours"] == 12.0
    assert first["change_failure_rate"]["change_failure_rate"] == 0.1
    assert first["recovery_time"]["median_recovery_hours"] == 1.0
    classification = read(tmp_path / "classification.json")[0]
    assert {name: rating["level"] for name, rating in classification["ratings"].items()} == {
        "deployment_frequency": "High", "lead_time": "High", "change_failure_rate": "Elite",
        "recovery_time": "High"}
    assert classification["overall"] == "High"
    with (tmp_path / "dora.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [(row["repository"], row["stars"], row["overall"], row["collection_complete"]) for row in rows] == [
        ("owner/one", "5000", "High", "True"), ("owner/two", "4000", "High", "True")]
    assert read(tmp_path / "summary.json")["classification"]["by_overall"]["High"] == 2


def test_second_execution_reuses_cache_and_diaries(github, execute):
    execute()
    made = len(github.requests)
    code, summary = execute()
    assert code == 0
    # Só a busca de candidatos é repetida, e ela vem do cache.
    assert len(github.requests) == made
    assert summary["api"]["requests"] == 0
    assert summary["api"]["resumed_units"] == 6


def test_stages_share_one_cache(github, execute):
    execute()
    # Releases e runs pedidos na seleção não são pedidos de novo nas etapas seguintes.
    assert github.requests.count("/repos/owner/one/releases") == 1
    assert github.requests.count("/repos/owner/one/actions/runs") == 2


def test_sample_below_target_still_produces_metrics(github, execute, tmp_path):
    code, summary = execute(target="3")
    assert code == 1
    assert summary["status"] == "incomplete"
    assert summary["selection"]["target_reached"] is False
    assert summary["selection"]["discarded_by_reason"] == {"no_github_actions": 1}
    assert len(read(tmp_path / "metrics.json")) == 2


def test_search_error_stops_before_collection(github, execute, tmp_path):
    github.fail_search = True
    code, summary = execute()
    assert code == 1
    assert (summary["status"], summary["stage"]) == ("search_error", "selection")
    assert summary["selection"]["search_error"]
    assert not (tmp_path / "deployments.json").exists()


def test_no_selected_repository_stops_after_selection(github, execute, tmp_path):
    github.eligible.clear()
    code, summary = execute()
    assert code == 1
    assert (summary["status"], summary["stage"]) == ("incomplete", "selection")
    assert not (tmp_path / "deployments.json").exists()


def test_interruption_keeps_partial_data_and_resumes(github, execute, tmp_path):
    github.interrupt_on = "/repos/owner/two/compare/"
    code, summary = execute()
    assert code == 1
    assert (summary["status"], summary["stage"]) == ("interrupted", "deployments")
    assert [repo["full_name"] for repo in read(tmp_path / "deployments.json")] == ["owner/one"]
    assert not (tmp_path / "metrics.json").exists()
    github.interrupt_on = None
    github.requests.clear()
    code, summary = execute()
    assert code == 0
    assert summary["status"] == "complete"
    assert not [path for path in github.requests if path.startswith("/repos/owner/one/")]
    assert len(read(tmp_path / "metrics.json")) == 2


def test_comparison_error_is_a_special_case_not_a_failed_collection(github, execute, tmp_path, monkeypatch):
    route = github.route
    # Resposta sem a lista de commits: a comparação falha, a coleta do repositório não.
    monkeypatch.setattr(github, "route", lambda path, query: (
        {} if "/compare/" in path else route(path, query)))
    code, summary = execute()
    assert code == 0
    assert summary["deployments"]["releases_ignored_comparison_error"] == 8
    classification = read(tmp_path / "classification.json")[0]
    assert classification["ratings"]["lead_time"]["reason"] == "comparison_unavailable"


def test_other_window_refuses_the_existing_diaries(github, execute, tmp_path):
    execute()
    with pytest.raises(SystemExit):
        main(["--start", "2025-01-01T00:00:00Z", "--end", "2025-12-31T23:59:59Z", "--output", str(tmp_path)])


def test_no_resume_and_no_cache_collect_everything_again(github, execute, tmp_path):
    execute("--no-resume", "--no-cache")
    made = len(github.requests)
    code, summary = execute("--no-resume", "--no-cache")
    assert code == 0
    assert len(github.requests) == 2 * made
    assert summary["api"]["resumed_units"] == 0
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "cache").exists()


def test_token_comes_only_from_the_environment(github, execute, tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN")
    with pytest.raises(SystemExit):
        main(["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z", "--output", str(tmp_path)])
    assert not github.requests


def test_token_is_never_written_to_outputs(github, execute, tmp_path):
    execute()
    files = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert files
    assert not [path for path in files if TOKEN in path.read_text(encoding="utf-8")]


@pytest.mark.parametrize("arguments", [
    ["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z", "--target", "0"],
    ["--start", "2026-01-01T00:00:00", "--end", "2026-01-31T23:59:59Z"],
    ["--start", "2026-01-01T00:00:00.5Z", "--end", "2026-01-31T23:59:59Z"],
    ["--start", "2026-02-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z"],
])
def test_invalid_arguments_are_rejected(github, tmp_path, arguments, capsys):
    with pytest.raises(SystemExit):
        main([*arguments, "--output", str(tmp_path)])
    capsys.readouterr()
    assert not github.requests


def test_secrets_and_outputs_are_ignored_by_git():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    assert {".env", "outputs/"} <= set(ignored)
