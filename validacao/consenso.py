"""S2-06: consenso entre avaliadores e protocolo de desempate (validacao/PROTOCOLO.md).

Aplica a maioria simples a cada item das planilhas dos avaliadores (as mesmas lidas por
`validacao.concordancia`) e separa o que precisa ir para a reunião de consenso:

- `tie`: nenhum rótulo tem maioria (1-1-1);
- `uncertain_majority`: a maioria escolheu `uncertain`.

Itens em que só parte dos avaliadores marcou `uncertain` ficam com o rótulo da maioria,
mas entram na pauta como `uncertain_vote`, para revisão. As decisões da reunião ficam em
`validacao/decisoes.csv` (dimensão, item, rótulo e justificativa) e prevalecem sobre a
maioria; assim `consenso.csv` é sempre regenerado a partir dos arquivos versionados.

Saídas: `validacao/resultados/pendencias.csv` (pauta da reunião, sempre gravada),
`validacao/consenso.csv` (rótulo final de cada item) e
`validacao/resultados/tipo_projeto.csv` (tipo do projeto consensual, fator da RQ 06).
Os dois últimos só são gravados quando nenhum item fica sem rótulo.

Uso: python -m validacao.consenso [planilhas...] [--decisions validacao/decisoes.csv]
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from dora_selection.gold_sample import MANUAL_VALUES
from .concordancia import (DIMENSIONS, LABELS_DIRECTORY, LABELS_PATTERN, check_same_items,
                           normalized, read_labels, read_rows)


DECISIONS = Path("validacao/decisoes.csv")
CONSENSUS = Path("validacao/consenso.csv")
PENDING = Path("validacao/resultados/pendencias.csv")
PROJECT_TYPE = Path("validacao/resultados/tipo_projeto.csv")
UNCERTAIN = "uncertain"
DECISION_FIELDS = ["dimension", "repository", "release_id", "label", "justification"]
CONSENSUS_FIELDS = ["dimension", "level", "repository", "release_id", "label", "method", "votes",
                    "justification"]
PENDING_FIELDS = ["dimension", "level", "repository", "release_id", "votes", "reason", "majority",
                  "decided_label"]
LEVELS = dict(DIMENSIONS)


def majority(votes):
    """Rótulo com maioria simples (mais da metade dos votos); None se não houver."""
    label, count = Counter(votes).most_common(1)[0]
    return label if count * 2 > len(votes) else None


def item_key(dimension, repository, release_id):
    return (dimension, repository) if LEVELS[dimension] == "repository" else (dimension, (repository, release_id))


def read_decisions(path, items):
    """Decisões da reunião por item; arquivo ausente equivale a nenhuma decisão."""
    path = Path(path)
    if not path.exists():
        return {}
    decisions = {}
    for line, row in enumerate(read_rows(path), 2):
        missing = [field for field in DECISION_FIELDS if field not in row]
        if missing:
            raise ValueError(f"{path}: colunas ausentes: {', '.join(missing)}.")
        dimension = normalized(row["dimension"])
        if dimension not in LEVELS:
            raise ValueError(f"{path}, linha {line}: dimensão {row['dimension']!r} desconhecida.")
        key = item_key(dimension, normalized(row["repository"]), (row["release_id"] or "").strip())
        if key not in items:
            raise ValueError(f"{path}, linha {line}: item não existe nas planilhas: {key[1]}.")
        if key in decisions:
            raise ValueError(f"{path}, linha {line}: decisão duplicada para {key[1]}.")
        label = normalized(row["label"])
        if label not in MANUAL_VALUES[dimension]:
            raise ValueError(f"{path}, linha {line}: rótulo {row['label']!r} não é permitido em {dimension}.")
        justification = (row["justification"] or "").strip()
        if not justification:
            raise ValueError(f"{path}, linha {line}: toda decisão precisa de justificativa.")
        decisions[key] = {"label": label, "justification": justification}
    return decisions


def collect_votes(sheets):
    """Votos de cada item, na ordem das planilhas: `{(dimensão, item): [rótulos]}`."""
    first = next(iter(sheets.values()))
    return {(dimension, item): [labels[level][item][dimension] for labels in sheets.values()]
            for dimension, level in DIMENSIONS for item in sorted(first[level])}


def resolve(votes, decisions):
    """Rótulo final, método e motivo de pauta de cada item."""
    consensus, pending = [], []
    for (dimension, item), item_votes in votes.items():
        level = LEVELS[dimension]
        repository, release_id = (item, "") if level == "repository" else item
        winner = majority(item_votes)
        reason = ("tie" if winner is None else "uncertain_majority" if winner == UNCERTAIN
                  else "uncertain_vote" if UNCERTAIN in item_votes else None)
        decision = decisions.get((dimension, item))
        if decision:
            label, method, justification = decision["label"], "meeting", decision["justification"]
        elif reason in ("tie", "uncertain_majority"):
            label, method, justification = None, None, ""
        else:
            label = winner
            method = "unanimous" if len(set(item_votes)) == 1 else "majority"
            justification = ""
        row = {"dimension": dimension, "level": level, "repository": repository, "release_id": release_id,
               "votes": "|".join(item_votes)}
        if reason:
            pending.append({**row, "reason": reason, "majority": winner or "",
                            "decided_label": label if method == "meeting" else ""})
        consensus.append({**row, "label": label, "method": method, "justification": justification})
    return consensus, pending


def project_types(consensus):
    """Tipo do projeto consensual de cada repositório, para a RQ 06."""
    return [{"repository": row["repository"], "project_type": row["label"]}
            for row in consensus if row["dimension"] == "project_type"]


def compute_consensus(paths, decisions_path=DECISIONS):
    """Consenso e pauta a partir de duas ou mais planilhas e das decisões da reunião."""
    if len(paths) < 2:
        raise ValueError("São necessárias as planilhas de pelo menos dois avaliadores.")
    sheets = {str(path): read_labels(path) for path in paths}
    check_same_items(sheets)
    votes = collect_votes(sheets)
    return resolve(votes, read_decisions(decisions_path, votes))


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S02 — consenso da amostra-ouro")
    parser.add_argument("labels", nargs="*", type=Path,
                        help=f"Planilhas preenchidas (padrão: {LABELS_DIRECTORY / LABELS_PATTERN})")
    parser.add_argument("--decisions", type=Path, default=DECISIONS)
    parser.add_argument("--output", type=Path, default=CONSENSUS)
    parser.add_argument("--pending", type=Path, default=PENDING)
    parser.add_argument("--project-type", type=Path, default=PROJECT_TYPE)
    args = parser.parse_args(argv)
    paths = args.labels or sorted(LABELS_DIRECTORY.glob(LABELS_PATTERN))
    try:
        consensus, pending = compute_consensus(paths, args.decisions)
        write_csv(args.pending, PENDING_FIELDS, pending)
        unresolved = [row for row in consensus if row["label"] is None]
        if not unresolved:
            write_csv(args.output, CONSENSUS_FIELDS, consensus)
            write_csv(args.project_type, ["repository", "project_type"], project_types(consensus))
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    methods = Counter(row["method"] or "pending" for row in consensus)
    print(f"Itens: {len(consensus)} ({', '.join(f'{key}={value}' for key, value in sorted(methods.items()))}).")
    print(f"Pauta da reunião em {args.pending}: {len(pending)} itens.")
    if unresolved:
        print(f"{len(unresolved)} itens sem rótulo: registre as decisões em {args.decisions} e rode de novo.")
        return 1
    print(f"Consenso salvo em {args.output} e tipo do projeto em {args.project_type}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
