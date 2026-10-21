"""S2: o dicionário de dados documenta exatamente as colunas de cada CSV final."""
import csv
import re
from pathlib import Path
import pytest
from dora_selection.dataset import EPISODE_FIELDS, RELEASE_FIELDS, REPOSITORY_FIELDS
from dora_selection.variants import DEPLOY_FIELDS, VARIANT_FIELDS


ROOT = Path(__file__).resolve().parents[1]
DICTIONARY = ROOT / "docs" / "dicionario_de_dados.md"
TABLES = {"repositorios.csv": REPOSITORY_FIELDS, "releases.csv": RELEASE_FIELDS,
          "episodios_falha.csv": EPISODE_FIELDS, "variantes.csv": VARIANT_FIELDS,
          "deploys_variantes.csv": DEPLOY_FIELDS}


def section(name):
    """Texto da seção `## <name>` do dicionário."""
    text = DICTIONARY.read_text(encoding="utf-8")
    found = re.search(rf"^## {re.escape(name)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert found, f"seção {name} ausente do dicionário"
    return found.group(1)


def documented(name):
    """Colunas com linha própria nas tabelas da seção, na ordem em que aparecem."""
    return re.findall(r"^\| `([a-z_]+)` \|", section(name), re.MULTILINE)


@pytest.mark.parametrize("name", TABLES)
def test_every_column_is_documented_once(name):
    columns = documented(name)
    assert sorted(columns) == sorted(TABLES[name])
    assert len(columns) == len(set(columns))


@pytest.mark.parametrize("name", TABLES)
def test_every_row_has_type_unit_formula_and_origin(name):
    text = section(name)
    for column in TABLES[name]:
        row = re.search(rf"^\| `{column}` \|(.*)\|$", text, re.MULTILINE).group(1)
        # Tipo, unidade, descrição/fórmula e origem; `—` marca unidade não aplicável.
        cells = [cell.strip() for cell in row.split("|")]
        assert len(cells) == 4 and all(cells), column


@pytest.mark.parametrize("name", TABLES)
def test_published_csv_has_the_documented_header(name):
    path = ROOT / "data" / "processed" / name
    if not path.exists():
        pytest.skip("dataset final ainda não gerado")
    with path.open(encoding="utf-8", newline="") as file:
        assert next(csv.reader(file)) == TABLES[name]


def test_readme_links_the_dictionary():
    assert "docs/dicionario_de_dados.md" in (ROOT / "README.md").read_text(encoding="utf-8")
