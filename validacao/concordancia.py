"""S2-05: concordância entre avaliadores da amostra-ouro (kappa de Fleiss).

Lê as planilhas preenchidas, uma por avaliador, no formato gerado por
`dora_selection.gold_sample` (uma linha por release, com as colunas do repositório
repetidas), confere que todas cobrem os mesmos itens e calcula, para cada dimensão:

- kappa de Fleiss (`statsmodels`), com a interpretação de Landis & Koch (1977);
- concordância bruta: fração de itens em que todos concordam (`unanimous_agreement`)
  e concordância média entre pares de avaliadores (`pairwise_agreement`, o P̄ de Fleiss).

As dimensões do repositório (`project_type`, `releases_represent_deliveries`) têm um
item por repositório: basta preenchê-las em uma das linhas dele, mas valores diferentes
entre as linhas do mesmo repositório são erro. `is_corrective` tem um item por release.

Uso: python -m validacao.concordancia [planilhas...] [--output validacao/resultados/kappa.csv]
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa

from dora_selection.gold_sample import MANUAL_VALUES


LABELS_DIRECTORY = Path("validacao/rotulos")
LABELS_PATTERN = "rotulos_*.csv"
OUTPUT = Path("validacao/resultados/kappa.csv")
# Dimensão, nível do item e valores permitidos, na ordem em que entram no relatório.
DIMENSIONS = [("project_type", "repository"), ("releases_represent_deliveries", "repository"),
              ("is_corrective", "release")]
RESULT_FIELDS = ["dimension", "level", "items", "raters", "categories_used", "fleiss_kappa",
                 "interpretation", "unanimous_agreement", "pairwise_agreement"]
# Landis & Koch (1977): abaixo de 0 é "pobre"; daí, limite superior inclusivo de cada faixa.
LANDIS_KOCH = [(0.20, "leve"), (0.40, "razoável"), (0.60, "moderada"), (0.80, "substancial"),
               (1.0, "quase perfeita")]
UNDEFINED = "indefinido"


def read_rows(path):
    """Linhas da planilha; aceita `;` como separador, como o Excel em pt-BR salva."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        header = file.readline()
        file.seek(0)
        delimiter = ";" if header.count(";") > header.count(",") else ","
        return list(csv.DictReader(file, delimiter=delimiter))


def normalized(value):
    return value.strip().lower() if isinstance(value, str) else ""


def read_labels(path):
    """Rótulos de um avaliador: `{"repository": {repo: {...}}, "release": {(repo, id): {...}}}`.

    Falha com ValueError em coluna ausente, célula vazia, valor fora de `MANUAL_VALUES`,
    release duplicada ou repositório com rótulos diferentes entre suas linhas.
    """
    rows = read_rows(path)
    if not rows:
        raise ValueError(f"{path}: planilha sem linhas.")
    missing = [column for column in ["repository", "release_id"] + [d for d, _ in DIMENSIONS]
               if column not in rows[0]]
    if missing:
        raise ValueError(f"{path}: colunas ausentes: {', '.join(missing)}.")
    labels = {"repository": {}, "release": {}}
    for line, row in enumerate(rows, 2):
        repository, release = normalized(row["repository"]), (row["release_id"] or "").strip()
        if not repository or not release:
            raise ValueError(f"{path}, linha {line}: repository e release_id são obrigatórios.")
        key = (repository, release)
        if key in labels["release"]:
            raise ValueError(f"{path}, linha {line}: release {release} de {repository} duplicada.")
        labels["release"][key] = {}
        repository_labels = labels["repository"].setdefault(repository, {})
        for dimension, level in DIMENSIONS:
            value = normalized(row[dimension])
            if value and value not in MANUAL_VALUES[dimension]:
                raise ValueError(f"{path}, linha {line}: {dimension} = {row[dimension]!r} não é permitido; "
                                 f"use {', '.join(MANUAL_VALUES[dimension])}.")
            if level == "release":
                if not value:
                    raise ValueError(f"{path}, linha {line}: {dimension} vazio.")
                labels["release"][key][dimension] = value
            elif value:
                if repository_labels.get(dimension, value) != value:
                    raise ValueError(f"{path}: {dimension} de {repository} tem valores diferentes "
                                     f"({repository_labels[dimension]!r} e {value!r}).")
                repository_labels[dimension] = value
    for repository, values in labels["repository"].items():
        for dimension, level in DIMENSIONS:
            if level == "repository" and dimension not in values:
                raise ValueError(f"{path}: {dimension} de {repository} não foi preenchido.")
    return labels


def check_same_items(sheets):
    """Todas as planilhas cobrem os mesmos repositórios e as mesmas releases."""
    (first_name, first), *others = sheets.items()
    for name, labels in others:
        for level in ("repository", "release"):
            missing = sorted(set(first[level]) - set(labels[level]))
            extra = sorted(set(labels[level]) - set(first[level]))
            if missing or extra:
                raise ValueError(f"{name} e {first_name} têm itens diferentes ({level}): "
                                 f"ausentes {missing[:5]}, a mais {extra[:5]}.")


def ratings(sheets, dimension, level):
    """Matriz itens × avaliadores com o índice da categoria em `MANUAL_VALUES`."""
    categories = MANUAL_VALUES[dimension]
    items = sorted(next(iter(sheets.values()))[level])
    return np.array([[categories.index(labels[level][item][dimension]) for labels in sheets.values()]
                     for item in items], dtype=int)


def landis_koch(kappa):
    """Faixa de Landis & Koch (1977) do kappa; `indefinido` quando não há kappa."""
    if kappa is None:
        return UNDEFINED
    if kappa < 0:
        return "pobre"
    return next((label for limit, label in LANDIS_KOCH if kappa <= limit + 1e-12), LANDIS_KOCH[-1][1])


def agreement(data, categories):
    """Kappa de Fleiss e concordâncias brutas de uma matriz itens × avaliadores.

    Com uma única categoria usada por todos, a concordância esperada é 1 e o kappa é
    indefinido (0/0): retorna None em vez de NaN.
    """
    table, _ = aggregate_raters(data, n_cat=categories)
    raters = data.shape[1]
    used = int((table.sum(axis=0) > 0).sum())
    kappa = float(fleiss_kappa(table, method="fleiss")) if used > 1 else None
    pairwise = ((table ** 2).sum(axis=1) - raters) / (raters * (raters - 1))
    return {"items": int(data.shape[0]), "raters": raters, "categories_used": used,
            "fleiss_kappa": kappa, "interpretation": landis_koch(kappa),
            "unanimous_agreement": float((table.max(axis=1) == raters).mean()),
            "pairwise_agreement": float(pairwise.mean())}


def compute_agreement(paths):
    """Uma linha de resultado por dimensão, a partir de duas ou mais planilhas."""
    if len(paths) < 2:
        raise ValueError("São necessárias as planilhas de pelo menos dois avaliadores.")
    sheets = {str(path): read_labels(path) for path in paths}
    check_same_items(sheets)
    return [{"dimension": dimension, "level": level,
             **agreement(ratings(sheets, dimension, level), len(MANUAL_VALUES[dimension]))}
            for dimension, level in DIMENSIONS]


def rounded(value):
    return f"{value:.4f}" if isinstance(value, float) else ("" if value is None else value)


def write_results(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows({key: rounded(row[key]) for key in RESULT_FIELDS} for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S02 — kappa de Fleiss da amostra-ouro")
    parser.add_argument("labels", nargs="*", type=Path,
                        help=f"Planilhas preenchidas (padrão: {LABELS_DIRECTORY / LABELS_PATTERN})")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    paths = args.labels or sorted(LABELS_DIRECTORY.glob(LABELS_PATTERN))
    try:
        rows = compute_agreement(paths)
        write_results(args.output, rows)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    for row in rows:
        kappa = "—" if row["fleiss_kappa"] is None else f"{row['fleiss_kappa']:.3f}"
        print(f"{row['dimension']:<30} itens={row['items']:<4} κ={kappa:<7} {row['interpretation']:<15} "
              f"unânime={row['unanimous_agreement']:.1%} pares={row['pairwise_agreement']:.1%}")
    print(f"Resultados salvos em {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
