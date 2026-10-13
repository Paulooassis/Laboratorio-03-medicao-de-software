"""Testes do S2-06: maioria simples, pauta da reunião e decisões registradas.

Amostra: 2 repositórios (A e B) com 2 releases cada, 3 avaliadores.

- `project_type`: A = library, library, cli (maioria); B = cli, other, application (1-1-1).
- `releases_represent_deliveries`: A = yes, yes, uncertain (maioria, revisar);
  B = uncertain, uncertain, no (maioria `uncertain`, vai para a reunião).
- `is_corrective`: sim-sim-sim, sim-não-não, não-não-não, sim-sim-não.
"""
import csv
import pytest
from dora_selection.gold_sample import EVALUATOR_FIELDS
from validacao.consenso import DECISION_FIELDS, compute_consensus, main, majority, read_decisions


RELEASES = [("owner/a", 1), ("owner/a", 2), ("owner/b", 3), ("owner/b", 4)]
PROJECT_TYPE = {"owner/a": ("library/framework", "library/framework", "cli"),
                "owner/b": ("cli", "other", "application/service")}
DELIVERIES = {"owner/a": ("yes", "yes", "uncertain"), "owner/b": ("uncertain", "uncertain", "no")}
CORRECTIVE = [("yes", "yes", "yes"), ("yes", "no", "no"), ("no", "no", "no"), ("yes", "yes", "no")]
RESOLVED = [
    {"dimension": "project_type", "repository": "owner/b", "release_id": "", "label": "cli",
     "justification": "README descreve uso pela linha de comando"},
    {"dimension": "releases_represent_deliveries", "repository": "owner/b", "release_id": "",
     "label": "no", "justification": "Releases só marcam snapshots internos"},
]


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def sheet_rows(rater):
    return [{field: "" for field in EVALUATOR_FIELDS} | {
        "sample_id": repository[-1], "repository": repository, "release_id": release,
        "project_type": PROJECT_TYPE[repository][rater],
        "releases_represent_deliveries": DELIVERIES[repository][rater],
        "release_tag": f"v{release}", "is_corrective": CORRECTIVE[index][rater]}
        for index, (repository, release) in enumerate(RELEASES)]


@pytest.fixture
def sheets(tmp_path):
    return [write_csv(tmp_path / f"rotulos_{rater + 1}.csv", EVALUATOR_FIELDS, sheet_rows(rater))
            for rater in range(3)]


@pytest.fixture
def decisions(tmp_path):
    return write_csv(tmp_path / "decisoes.csv", DECISION_FIELDS, RESOLVED)


def by_item(rows):
    return {(row["dimension"], row["repository"], row["release_id"]): row for row in rows}


def test_majority_requires_more_than_half():
    assert majority(["yes", "yes", "no"]) == "yes"
    assert majority(["cli", "other", "cli"]) == "cli"
    assert majority(["cli", "other", "library/framework"]) is None
    assert majority(["yes", "no"]) is None
    assert majority(["yes"]) == "yes"


def test_majority_unanimity_and_pending_without_decisions(tmp_path, sheets):
    consensus, pending = compute_consensus(sheets, tmp_path / "ausente.csv")
    items = by_item(consensus)
    assert len(consensus) == 2 + 2 + 4
    assert items[("project_type", "owner/a", "")] == {
        "dimension": "project_type", "level": "repository", "repository": "owner/a", "release_id": "",
        "votes": "library/framework|library/framework|cli", "label": "library/framework",
        "method": "majority", "justification": ""}
    assert items[("is_corrective", "owner/a", "1")]["method"] == "unanimous"
    assert [items[("is_corrective", r, str(i))]["label"] for r, i in RELEASES] == ["yes", "no", "no", "yes"]
    assert items[("project_type", "owner/b", "")]["label"] is None
    assert items[("releases_represent_deliveries", "owner/b", "")]["label"] is None
    # Um voto `uncertain` com maioria definida não bloqueia o consenso.
    assert items[("releases_represent_deliveries", "owner/a", "")]["label"] == "yes"
    reasons = {(row["dimension"], row["repository"]): row["reason"] for row in pending}
    assert reasons == {("project_type", "owner/b"): "tie",
                       ("releases_represent_deliveries", "owner/a"): "uncertain_vote",
                       ("releases_represent_deliveries", "owner/b"): "uncertain_majority"}
    assert by_item(pending)[("releases_represent_deliveries", "owner/b", "")]["majority"] == "uncertain"


def test_meeting_decisions_resolve_pending_items(sheets, decisions):
    consensus, pending = compute_consensus(sheets, decisions)
    items = by_item(consensus)
    assert all(row["label"] for row in consensus)
    tie = items[("project_type", "owner/b", "")]
    assert (tie["label"], tie["method"]) == ("cli", "meeting")
    assert tie["justification"] == "README descreve uso pela linha de comando"
    assert by_item(pending)[("project_type", "owner/b", "")]["decided_label"] == "cli"
    assert by_item(pending)[("releases_represent_deliveries", "owner/a", "")]["decided_label"] == ""


def test_decision_overrides_majority_of_a_release(tmp_path, sheets):
    override = {"dimension": "is_corrective", "repository": "owner/a", "release_id": "2", "label": "yes",
                "justification": "Release notes só listam correções"}
    path = write_csv(tmp_path / "decisoes.csv", DECISION_FIELDS, RESOLVED + [override])
    consensus, pending = compute_consensus(sheets, path)
    item = by_item(consensus)[("is_corrective", "owner/a", "2")]
    assert (item["label"], item["method"], item["votes"]) == ("yes", "meeting", "yes|no|no")
    assert ("is_corrective", "owner/a", "2") not in by_item(pending)


@pytest.mark.parametrize("change, message", [
    ({"dimension": "tipo"}, "desconhecida"),
    ({"repository": "owner/c"}, "não existe"),
    ({"dimension": "is_corrective", "release_id": "99"}, "não existe"),
    ({"label": "framework"}, "não é permitido"),
    ({"justification": " "}, "justificativa"),
])
def test_invalid_decisions_are_rejected(tmp_path, sheets, change, message):
    path = write_csv(tmp_path / "decisoes.csv", DECISION_FIELDS, [RESOLVED[0] | change])
    with pytest.raises(ValueError, match=message):
        compute_consensus(sheets, path)


def test_duplicate_decision_and_missing_columns(tmp_path, sheets):
    path = write_csv(tmp_path / "dup.csv", DECISION_FIELDS, [RESOLVED[0], RESOLVED[0]])
    with pytest.raises(ValueError, match="duplicada"):
        compute_consensus(sheets, path)
    path = write_csv(tmp_path / "col.csv", DECISION_FIELDS[:-1], [{k: RESOLVED[0][k] for k in DECISION_FIELDS[:-1]}])
    with pytest.raises(ValueError, match="colunas ausentes: justification"):
        read_decisions(path, {})


def test_needs_two_sheets_with_the_same_items(tmp_path, sheets):
    with pytest.raises(ValueError, match="pelo menos dois"):
        compute_consensus(sheets[:1])
    short = write_csv(tmp_path / "short.csv", EVALUATOR_FIELDS, sheet_rows(0)[:3])
    with pytest.raises(ValueError, match="itens diferentes"):
        compute_consensus([sheets[0], short])


def run_cli(tmp_path, monkeypatch, decisions_rows=None):
    labels = tmp_path / "validacao" / "rotulos"
    labels.mkdir(parents=True)
    for rater in range(3):
        write_csv(labels / f"rotulos_{'ABC'[rater]}.csv", EVALUATOR_FIELDS, sheet_rows(rater))
    if decisions_rows is not None:
        write_csv(tmp_path / "validacao" / "decisoes.csv", DECISION_FIELDS, decisions_rows)
    monkeypatch.chdir(tmp_path)
    return main([])


def test_cli_with_pending_items_writes_only_the_agenda(tmp_path, monkeypatch, capsys):
    assert run_cli(tmp_path, monkeypatch) == 1
    assert len(read_csv(tmp_path / "validacao" / "resultados" / "pendencias.csv")) == 3
    assert not (tmp_path / "validacao" / "consenso.csv").exists()
    assert not (tmp_path / "validacao" / "resultados" / "tipo_projeto.csv").exists()
    assert "2 itens sem rótulo" in capsys.readouterr().out


def test_cli_writes_consensus_and_project_type(tmp_path, monkeypatch, capsys):
    assert run_cli(tmp_path, monkeypatch, RESOLVED) == 0
    consensus = read_csv(tmp_path / "validacao" / "consenso.csv")
    assert len(consensus) == 8 and all(row["label"] and row["method"] for row in consensus)
    assert read_csv(tmp_path / "validacao" / "resultados" / "tipo_projeto.csv") == [
        {"repository": "owner/a", "project_type": "library/framework"},
        {"repository": "owner/b", "project_type": "cli"}]
    assert "meeting=2" in capsys.readouterr().out


def test_cli_reports_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
