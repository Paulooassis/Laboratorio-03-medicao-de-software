"""Testes do S2-05 com planilhas pequenas cujo kappa foi calculado à mão.

Amostra de referência: 2 repositórios (A e B) com 2 releases cada, 3 avaliadores.

- `is_corrective` (4 releases): sim-sim-sim, sim-sim-não, não-não-não, sim-não-não.
  P̄ = (1 + 1/3 + 1 + 1/3) / 4 = 2/3; p(sim) = p(não) = 1/2, Pe = 1/2;
  κ = (2/3 − 1/2) / (1 − 1/2) = 1/3, "razoável"; unanimidade em 2 de 4 itens.
- `project_type` (2 repositórios): A é library/framework e B é cli para os três.
  P̄ = 1, Pe = 1/2, κ = 1, "quase perfeita".
- `releases_represent_deliveries`: todos marcam yes; só uma categoria usada, Pe = 1 e
  o kappa é indefinido (0/0).
"""
import csv
import pytest
from dora_selection.gold_sample import EVALUATOR_FIELDS
from validacao.concordancia import (check_same_items, compute_agreement, landis_koch, main,
                                    read_labels, write_results)


RELEASES = [("owner/a", 1), ("owner/a", 2), ("owner/b", 3), ("owner/b", 4)]
PROJECT_TYPE = {"owner/a": "library/framework", "owner/b": "cli"}
CORRECTIVE = [("yes", "yes", "yes"), ("yes", "yes", "no"), ("no", "no", "no"), ("yes", "no", "no")]


def rows(rater, corrective=None, **changes):
    corrective = corrective or [labels[rater] for labels in CORRECTIVE]
    result = []
    for (repository, release), value in zip(RELEASES, corrective):
        result.append({field: "" for field in EVALUATOR_FIELDS} | {
            "sample_id": repository[-1], "repository": repository, "release_id": release,
            "project_type": PROJECT_TYPE[repository], "releases_represent_deliveries": "yes",
            "release_tag": f"v{release}", "is_corrective": value, **changes})
    return result


def write_sheet(path, data, delimiter=",", fields=EVALUATOR_FIELDS):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, delimiter=delimiter, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    return path


@pytest.fixture
def sheets(tmp_path):
    return [write_sheet(tmp_path / f"rotulos_{rater + 1}.csv", rows(rater)) for rater in range(3)]


def by_dimension(results):
    return {row["dimension"]: row for row in results}


def test_hand_computed_fleiss_kappa(sheets):
    results = by_dimension(compute_agreement(sheets))
    corrective = results["is_corrective"]
    assert corrective["fleiss_kappa"] == pytest.approx(1 / 3)
    assert corrective["interpretation"] == "razoável"
    assert (corrective["items"], corrective["raters"], corrective["categories_used"]) == (4, 3, 2)
    assert corrective["unanimous_agreement"] == pytest.approx(0.5)
    assert corrective["pairwise_agreement"] == pytest.approx(2 / 3)
    assert corrective["level"] == "release"


def test_perfect_agreement_is_one(sheets):
    project = by_dimension(compute_agreement(sheets))["project_type"]
    assert project["fleiss_kappa"] == pytest.approx(1.0)
    assert project["interpretation"] == "quase perfeita"
    assert (project["items"], project["level"]) == (2, "repository")
    assert project["unanimous_agreement"] == project["pairwise_agreement"] == 1.0


def test_single_category_has_undefined_kappa(sheets):
    deliveries = by_dimension(compute_agreement(sheets))["releases_represent_deliveries"]
    assert deliveries["fleiss_kappa"] is None
    assert deliveries["interpretation"] == "indefinido"
    assert deliveries["categories_used"] == 1
    assert deliveries["unanimous_agreement"] == 1.0


def test_systematic_disagreement_is_negative(tmp_path):
    first = write_sheet(tmp_path / "1.csv", rows(0, ["yes", "no", "yes", "no"]))
    second = write_sheet(tmp_path / "2.csv", rows(0, ["no", "yes", "no", "yes"]))
    corrective = by_dimension(compute_agreement([first, second]))["is_corrective"]
    assert corrective["fleiss_kappa"] == pytest.approx(-1.0)
    assert corrective["interpretation"] == "pobre"
    assert corrective["unanimous_agreement"] == corrective["pairwise_agreement"] == 0.0


@pytest.mark.parametrize("kappa, label", [(None, "indefinido"), (-0.01, "pobre"), (0.0, "leve"),
                                          (0.20, "leve"), (0.21, "razoável"), (0.40, "razoável"),
                                          (0.60, "moderada"), (0.61, "substancial"), (0.80, "substancial"),
                                          (0.81, "quase perfeita"), (1.0, "quase perfeita")])
def test_landis_koch_scale(kappa, label):
    assert landis_koch(kappa) == label


def test_tolerates_excel_formatting(tmp_path):
    data = rows(0, is_corrective=" YES ")
    # Rótulos do repositório preenchidos só na primeira linha de cada um.
    for row in data[1::2]:
        row["project_type"] = row["releases_represent_deliveries"] = ""
    labels = read_labels(write_sheet(tmp_path / "excel.csv", data, delimiter=";"))
    assert labels["repository"]["owner/b"] == {"project_type": "cli", "releases_represent_deliveries": "yes"}
    assert labels["release"][("owner/a", "1")] == {"is_corrective": "yes"}


def test_extra_columns_such_as_notes_are_ignored(tmp_path):
    data = [row | {"observacao": "difícil"} for row in rows(0)]
    path = write_sheet(tmp_path / "notes.csv", data, fields=EVALUATOR_FIELDS + ["observacao"])
    assert len(read_labels(path)["release"]) == 4


@pytest.mark.parametrize("change, message", [
    ({"is_corrective": ""}, "is_corrective vazio"),
    ({"is_corrective": "talvez"}, "não é permitido"),
    ({"project_type": "biblioteca"}, "não é permitido"),
    ({"project_type": "", "releases_represent_deliveries": ""}, "não foi preenchido"),
    ({"repository": ""}, "obrigatórios"),
])
def test_invalid_cells_are_reported(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        read_labels(write_sheet(tmp_path / "bad.csv", rows(0, **change)))


def test_inconsistent_repository_labels_are_rejected(tmp_path):
    data = rows(0)
    data[1]["project_type"] = "other"
    with pytest.raises(ValueError, match="valores diferentes"):
        read_labels(write_sheet(tmp_path / "bad.csv", data))


def test_duplicate_release_missing_column_and_empty_sheet(tmp_path):
    data = rows(0)
    with pytest.raises(ValueError, match="duplicada"):
        read_labels(write_sheet(tmp_path / "dup.csv", data + data[:1]))
    with pytest.raises(ValueError, match="colunas ausentes: is_corrective"):
        read_labels(write_sheet(tmp_path / "col.csv", data, fields=EVALUATOR_FIELDS[:-1]))
    with pytest.raises(ValueError, match="sem linhas"):
        read_labels(write_sheet(tmp_path / "empty.csv", []))


def test_sheets_must_cover_the_same_items(tmp_path, sheets):
    short = write_sheet(tmp_path / "short.csv", rows(0)[:3])
    with pytest.raises(ValueError, match=r"itens diferentes \(release\).*'4'"):
        compute_agreement([sheets[0], short])
    other = {"repository": {"owner/c": {}}, "release": {}}
    with pytest.raises(ValueError, match=r"\(repository\)"):
        check_same_items({"a": read_labels(sheets[0]), "b": other})
    with pytest.raises(ValueError, match="pelo menos dois"):
        compute_agreement(sheets[:1])


def test_write_results_rounds_and_leaves_undefined_empty(tmp_path, sheets):
    output = tmp_path / "resultados" / "kappa.csv"
    write_results(output, compute_agreement(sheets))
    with output.open(encoding="utf-8-sig", newline="") as file:
        saved = {row["dimension"]: row for row in csv.DictReader(file)}
    assert saved["is_corrective"]["fleiss_kappa"] == "0.3333"
    assert saved["is_corrective"]["items"] == "4"
    assert saved["releases_represent_deliveries"]["fleiss_kappa"] == ""
    assert saved["releases_represent_deliveries"]["interpretation"] == "indefinido"


def test_cli_finds_default_sheets_and_writes_kappa(tmp_path, monkeypatch, capsys):
    labels = tmp_path / "validacao" / "rotulos"
    labels.mkdir(parents=True)
    for rater in range(3):
        write_sheet(labels / f"rotulos_{'ABC'[rater]}.csv", rows(rater))
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert (tmp_path / "validacao" / "resultados" / "kappa.csv").exists()
    output = capsys.readouterr().out
    assert "κ=0.333" in output and "κ=—" in output


def test_cli_reports_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
