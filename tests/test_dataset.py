"""S2: dataset final (repositório, release, episódio), contagens de escala e comando por configuração."""
import csv
import json
import logging
import pytest
import yaml
import pipeline
from dora_selection.cfr import cfr_entrega, rework_rate
from dora_selection.dataset import (EPISODE_FIELDS, RELEASE_FIELDS, REPOSITORY_FIELDS, build_dataset, censoring,
                                    collection_checks, episode_rows, funnel_table, load_project_types,
                                    release_rows, repository_row, save_dataset)
from dora_selection.rating import classify_repository
from dora_selection.resilience import configure_logging
from conftest import REPOSITORY
from test_card8 import FakeGitHub, TOKEN


REPO = {"full_name": "Owner/Repo", "url": "https://github.com/owner/repo", "stars": 1500, "language": "Go",
        "contributors": 12, "created_at": "2024-02-01T23:59:59Z"}


@pytest.fixture
def measured(metrics, releases, window):
    """Amostra de referência com o CFR (b): v4 sai nos últimos 7 dias da janela e fica censurada."""
    return {**metrics, "change_failure_rate_b": cfr_entrega(releases, window.end),
            "rework": rework_rate(releases)}


@pytest.fixture
def row(measured, releases, window):
    return repository_row(REPO, {"releases": releases}, measured, classify_repository(measured), True, window,
                          {"owner/repo": "cli"})


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_repository_row_has_every_variant_and_the_rq06_factors(row):
    assert list(row) == REPOSITORY_FIELDS
    assert (row["repository"], row["stars"], row["language"], row["contributors"]) == ("Owner/Repo", 1500, "Go", 12)
    # Criado exatamente dois anos antes do fim da janela, um deles bissexto.
    assert row["age_days"] == 731
    assert (row["project_type"], row["gold_sample"]) == ("cli", True)
    assert row["deployment_frequency_per_week"] == 1.0
    assert (row["lead_time_a_hours"], row["lead_time_a_releases"]) == (36.0, 2)
    assert (row["lead_time_b_hours"], row["lead_time_b_commits"]) == (24.0, 3)
    assert (row["cfr_a"], row["cfr_a_runs"], row["cfr_a_failures"], row["runs_ignored"]) == (0.5, 8, 4, 2)
    assert (row["cfr_b"], row["cfr_b_version"], row["cfr_b_evaluated"], row["cfr_b_censored"]) == (0.0, "v1", 3, 1)
    assert row["recovery_hours"] == 4.0
    assert row["overall"] is not None


def test_repository_row_has_the_rework_rate_without_censoring(row):
    # v1 é a primeira da história (fora do denominador); v2 a v4 não são corretivas, e a v4,
    # que o CFR (b) censura por sair nos últimos 7 dias, continua avaliada no rework rate.
    assert (row["rework_rate"], row["rework_evaluated"], row["rework_corrective"],
            row["rework_no_previous"]) == (0.0, 3, 0, 1)
    assert row["cfr_b_evaluated"] == 3 and row["cfr_b_censored"] == 1


def test_repository_row_without_the_heuristic_leaves_the_rework_empty(measured, releases, window):
    sem_heuristica = {chave: valor for chave, valor in measured.items()
                      if chave not in ("change_failure_rate_b", "rework")}
    linha = repository_row(REPO, {"releases": releases}, sem_heuristica,
                           classify_repository(sem_heuristica), True, window)
    assert [linha[campo] for campo in ("rework_rate", "rework_evaluated", "rework_corrective",
                                       "rework_no_previous")] == [None] * 4


def test_repository_row_counts_ignored_releases_and_censored_episodes(row):
    assert (row["releases"], row["releases_ignored"]) == (4, 2)
    assert (row["releases_no_previous"], row["releases_no_new_commits"]) == (1, 1)
    assert (row["releases_compare_not_found"], row["releases_compare_error"]) == (0, 0)
    assert (row["recovery_episodes"], row["recovery_recovered"], row["recovery_censored"]) == (3, 2, 1)
    assert row["recovery_censored_share"] == pytest.approx(1 / 3)


def test_repository_outside_the_gold_sample_and_without_data_keeps_cells_empty(window):
    from dora_selection.metrics import repository_metrics
    empty = repository_metrics(window, [], [], "owner/empty")
    row = repository_row({"full_name": "owner/empty"}, {}, empty, classify_repository(empty), False, window)
    assert (row["project_type"], row["gold_sample"], row["age_days"]) == (None, False, None)
    assert (row["cfr_a"], row["cfr_b"], row["cfr_b_censored"], row["recovery_hours"]) == (None, None, None, None)
    # Sem episódios não há proporção de censura: vazio, não zero.
    assert (row["recovery_episodes"], row["recovery_censored_share"]) == (0, None)


def test_release_rows_join_lead_time_and_the_corrective_heuristic(measured, releases):
    releases[2]["comparison_status"] = "completed"
    rows = release_rows({"releases": releases}, measured)
    assert [list(item) for item in rows] == [RELEASE_FIELDS] * 4
    assert [item["lead_time_status"] for item in rows] == ["no_previous_release", "measured", "measured",
                                                           "no_commits"]
    assert [item["lead_time_a_hours"] for item in rows] == [None, 24.0, 48.0, None]
    assert [item["lead_time_b_hours"] for item in rows] == [None, 15.0, 48.0, None]
    assert [item["cfr_b_censored"] for item in rows] == [False, False, False, True]
    assert rows[1]["comparison_status"] == "completed" and rows[1]["previous_tag_name"] == "v1"
    assert {item["repository"] for item in rows} == {REPOSITORY}


def test_release_rows_without_official_heuristic_leave_the_columns_empty(metrics, releases):
    rows = release_rows({"releases": releases}, metrics)
    assert {(item["corrective"], item["cfr_b_failed"]) for item in rows} == {(None, None)}


def test_episode_rows_list_recovered_and_censored_episodes(measured):
    rows = episode_rows(measured)
    assert [list(item) for item in rows] == [EPISODE_FIELDS] * 3
    assert [(item["workflow_name"], item["failures"], item["recovery_hours"], item["censored"])
            for item in rows] == [("CI", 2, 6.0, False), ("CI", 1, 2.0, False), ("Deploy", 1, None, True)]
    assert rows[2]["observed_hours"] is not None and rows[2]["repository"] == REPOSITORY


def test_censoring_sums_the_sample(row):
    other = {**row, "cfr_b_evaluated": None, "cfr_b_censored": None, "recovery_episodes": 1,
             "recovery_censored": 1, "recovery_censored_share": 1.0}
    assert censoring([row, other]) == {
        "cfr_b_releases": 4, "cfr_b_censored_releases": 1, "cfr_b_censored_share": 0.25,
        "recovery_episodes": 4, "recovery_censored_episodes": 2, "recovery_censored_share": 0.5,
        "repositories_with_censored_majority": 1}
    assert censoring([])["recovery_censored_share"] is None


def test_collection_checks_count_the_cases_that_only_show_up_at_scale(make_release, make_commit, make_run):
    deployments = [{"full_name": "owner/a", "releases": [
        make_release(1, "2026-01-06T12:00:00Z", comparison_status="no_previous_release"),
        make_release(2, "2026-01-07T12:00:00Z", comparison_status="not_found"),
        make_release(3, "2026-01-08T12:00:00Z", comparison_status="error"),
        make_release(4, "2026-01-09T12:00:00Z"),
        make_release(5, "2026-01-10T12:00:00Z",
                     [make_commit(str(number), "2026-01-09T00:00:00Z") for number in range(251)])]}]
    runs = ([make_run(number, created_at="2026-01-10T00:00:00Z") for number in range(1000)]
            + [make_run(number, created_at="2026-02-10T00:00:00Z") for number in range(1000, 1999)])
    workflow_runs = [{"full_name": "owner/a", "workflows": [{"runs": runs[:600]}, {"runs": runs[600:]}]}]
    assert collection_checks(deployments, workflow_runs) == {
        "compare_not_found": 1, "compare_error": 1, "releases_without_previous": 1,
        "releases_without_new_commits": 1, "releases_over_250_commits": 1, "months_at_run_limit": 1,
        "months_at_run_limit_detail": [{"repository": "owner/a", "month": "2026-01", "runs": 1000}]}


def test_funnel_table_lists_stages_and_discards_by_size():
    table = funnel_table({"candidates_found": 9, "unique_repositories": 8, "with_github_actions": 6,
                          "with_sufficient_releases": 4, "with_sufficient_runs": 3, "included": 3,
                          "discarded_by_reason": {"no_github_actions": 2, "insufficient_releases": 2,
                                                  "insufficient_workflow_runs": 1}})
    lines = table.splitlines()
    assert lines[2] == "| Candidatos recebidos da busca | 9 |"
    assert lines[7] == "| Incluídos na amostra | 3 |"
    assert lines[-3:] == ["| `insufficient_releases` | 2 |", "| `no_github_actions` | 2 |",
                          "| `insufficient_workflow_runs` | 1 |"]


def test_project_types_require_both_columns(tmp_path):
    path = tmp_path / "tipo.csv"
    path.write_text("﻿repository,project_type\nOwner/Repo, cli\n", encoding="utf-8")
    assert load_project_types(path) == {"owner/repo": "cli"}
    path.write_text("repository,project_type\nowner/repo,\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_project_types(path)


def test_dataset_is_saved_with_one_row_per_unit(tmp_path, measured, releases, window):
    table = [{"collection_complete": True}]
    dataset = build_dataset(window, [REPO], [{"full_name": "owner/repo", "releases": releases}], [measured],
                            [classify_repository(measured)], table)
    files = save_dataset(tmp_path / "processed", dataset, {"included": 1})
    assert sorted(path.name for path in (tmp_path / "processed").iterdir()) == [
        "episodios_falha.csv", "funil.md", "releases.csv", "repositorios.csv"]
    repositories = read_csv(tmp_path / "processed" / "repositorios.csv")
    assert len(repositories) == 1 and len(read_csv(tmp_path / "processed" / "releases.csv")) == 4
    assert len(read_csv(tmp_path / "processed" / "episodios_falha.csv")) == 3
    # Métrica sem amostra e fator ausente ficam vazios no CSV.
    assert (repositories[0]["project_type"], repositories[0]["releases_compare_not_found"]) == ("", "0")
    assert files["repositories"].endswith("repositorios.csv")


@pytest.fixture
def configured(tmp_path, monkeypatch, capsys):
    """Executa `python -m pipeline --config` com a API simulada do Card 8."""
    fake = FakeGitHub()
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setattr("dora_selection.api.urlopen", fake)
    (tmp_path / "tipo.csv").write_text("repository,project_type\nowner/one,cli\n", encoding="utf-8")
    official = yaml.safe_load((pipeline.Path(__file__).resolve().parents[1] / "config.yaml").read_text())
    config = {"coleta": {"inicio": "2026-01-01T00:00:00Z", "fim": "2026-01-31T23:59:59Z", "alvo": 2,
                         "min_estrelas": 1001, "saida": str(tmp_path / "out"),
                         "processados": str(tmp_path / "data"), "tipo_projeto": str(tmp_path / "tipo.csv"),
                         "workers": 1},
              "heuristica_corretiva": official["heuristica_corretiva"]}

    def run(*extra, **changes):
        config["coleta"].update(changes)
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        code = pipeline.main(["--config", str(path), *extra])
        capsys.readouterr()
        return code
    yield run, fake
    configure_logging(None, logging.CRITICAL)


def test_config_command_generates_the_final_dataset(configured, tmp_path):
    run, _ = configured
    assert run() == 0
    repositories = read_csv(tmp_path / "data" / "repositorios.csv")
    assert [(item["repository"], item["project_type"], item["gold_sample"]) for item in repositories] == [
        ("owner/one", "cli", "True"), ("owner/two", "", "False")]
    first = repositories[0]
    assert (first["lead_time_a_hours"], first["lead_time_b_hours"], first["cfr_a"]) == ("12.0", "12.0", "0.1")
    # A release de 30/01 sai nos últimos 7 dias da janela: censurada no CFR (b).
    assert (first["cfr_b_version"], first["cfr_b_evaluated"], first["cfr_b_censored"]) == ("v1", "4", "1")
    # A release de 30/01 também entra no rework rate, que não censura; v0 fica antes da janela.
    assert (first["rework_rate"], first["rework_evaluated"], first["rework_corrective"],
            first["rework_no_previous"]) == ("0.0", "5", "0", "0")
    assert len(read_csv(tmp_path / "data" / "releases.csv")) == 10
    assert len(read_csv(tmp_path / "data" / "episodios_falha.csv")) == 10
    assert "| Incluídos na amostra | 2 |" in (tmp_path / "data" / "funil.md").read_text(encoding="utf-8")
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["dataset"]["repositories"] == 2
    assert summary["dataset"]["censoring"]["cfr_b_censored_releases"] == 2
    assert summary["collection_checks"]["releases_without_previous"] == 0


def test_second_run_rebuilds_the_dataset_from_cache_without_requests(configured, tmp_path):
    run, fake = configured
    assert run() == 0
    made = len(fake.requests)
    expected = (tmp_path / "data" / "repositorios.csv").read_bytes()
    (tmp_path / "data" / "repositorios.csv").unlink()
    assert run() == 0
    assert len(fake.requests) == made
    assert (tmp_path / "data" / "repositorios.csv").read_bytes() == expected


def test_command_line_overrides_the_configuration(configured, tmp_path):
    run, _ = configured
    assert run("--processed", str(tmp_path / "other")) == 0
    assert (tmp_path / "other" / "repositorios.csv").is_file()
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("content", ["heuristica_corretiva: {}\n", "coleta: {janela: 1}\n", "coleta: [\n"])
def test_invalid_configuration_is_refused(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit):
        pipeline.main(["--config", str(path)])
    with pytest.raises(SystemExit):
        pipeline.main(["--config", str(tmp_path / "ausente.yaml")])
