"""Sorteio offline da amostra-ouro e planilhas cegas para três avaliadores."""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from .output import save_json
from .selection import Window, timestamp


REPOSITORY_FIELDS = ["sample_id", "repository", "repository_url"]
RELEASE_FIELDS = ["sample_id", "repository", "release_id", "tag_name",
                  "published_at", "release_url", "commits_url"]
EVALUATOR_FIELDS = ["sample_id", "repository", "repository_url", "project_type",
                    "releases_represent_deliveries", "release_id", "release_tag",
                    "published_at", "release_url", "commits_url", "is_corrective"]
MANUAL_VALUES = {"project_type": ["library/framework", "application/service", "cli", "other"],
                 "releases_represent_deliveries": ["yes", "no", "uncertain"],
                 "is_corrective": ["yes", "no"]}


def load_records(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as file:
            records = list(csv.DictReader(file))
    else:
        records = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError(f"{path}: esperado uma lista de registros.")
    return records


def repository_name(row):
    name = row.get("full_name", row.get("repository"))
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise ValueError("Repositório deve ter full_name no formato owner/repository.")
    return name.lower()


def sample_records(repositories, deployments, window, seed=42, count=60, releases_per_repository=5):
    if count < 1 or releases_per_repository < 1:
        raise ValueError("As quantidades de repositórios e releases devem ser positivas.")
    names = set()
    for row in repositories:
        if row.get("included", True) not in (True, "True", "true"):
            continue
        if row.get("error") or row.get("exclusion_reason"):
            raise ValueError("Amostra final contém repositório incluído com erro ou exclusão.")
        names.add(repository_name(row))
    if len(names) < count:
        raise ValueError(f"São necessários {count} repositórios elegíveis; disponíveis: {len(names)}.")
    rng = random.Random(seed)
    selected = rng.sample(sorted(names), count)
    collected = {}
    for row in deployments:
        name = repository_name(row)
        if name in collected:
            raise ValueError(f"Dados de coleta duplicados para {name}.")
        collected[name] = row
    repository_rows, release_rows = [], []
    cutoff = window.end - timedelta(days=7)
    for sample_id, name in enumerate(selected, 1):
        data = collected.get(name)
        if data is None or not isinstance(data.get("releases"), list):
            raise ValueError(f"{name}: dados de releases indisponíveis.")
        # Falhas de compare não invalidam a listagem, mas tornam o link de evidência indisponível.
        if any(error.get("stage") == "releases" for error in data.get("errors", [])):
            raise ValueError(f"{name}: listagem de releases incompleta.")
        valid = {}
        base = f"https://github.com/{name}"
        for release in data["releases"]:
            if not isinstance(release, dict):
                raise ValueError(f"{name}: registro de release inválido.")
            if release.get("draft") is True or release.get("prerelease") is True:
                continue
            if release.get("draft") is not False or release.get("prerelease") is not False:
                raise ValueError(f"{name}: flags de release ausentes ou inválidas.")
            if not isinstance(release.get("published_at"), str):
                raise ValueError(f"{name}: release sem published_at válido.")
            published = timestamp(release["published_at"])
            if not window.start <= published <= cutoff:
                continue
            identity, tag = release.get("release_id"), release.get("tag_name")
            if type(identity) is not int or identity < 1 or not isinstance(tag, str) or not tag:
                raise ValueError(f"{name}: release sem release_id ou tag_name válido.")
            previous = release.get("previous_tag_name")
            status = release.get("comparison_status")
            if status == "no_previous_release" and previous is None and release.get("previous_release_id") is None:
                sha = release.get("commit_sha")
                if not isinstance(sha, str) or not sha:
                    raise ValueError(f"{name}, release {identity}: SHA da primeira release indisponível.")
                commits_url = base + "/commits/" + quote(sha, safe="")
            elif status == "completed" and isinstance(previous, str) and previous:
                commits_url = base + "/compare/" + quote(previous, safe="") + "..." + quote(tag, safe="")
            else:
                raise ValueError(f"{name}, release {identity}: comparação anterior indisponível.")
            item = {"sample_id": sample_id, "repository": name, "release_id": identity,
                    "tag_name": tag, "published_at": published.isoformat(),
                    "release_url": base + "/releases/tag/" + quote(tag, safe=""),
                    "commits_url": commits_url}
            if identity in valid and valid[identity] != item:
                raise ValueError(f"{name}: dados conflitantes para release {identity}.")
            valid[identity] = item
        if len(valid) < releases_per_repository:
            raise ValueError(f"{name}: necessárias {releases_per_repository} releases elegíveis "
                             f"com acompanhamento de 7 dias; disponíveis: {len(valid)}.")
        repository_rows.append({"sample_id": sample_id, "repository": name, "repository_url": base})
        release_rows.extend(rng.sample([valid[key] for key in sorted(valid)], releases_per_repository))
    return repository_rows, release_rows, len(names)


def observation_window(releases_path, start=None, end=None):
    if bool(start) != bool(end):
        raise ValueError("Informe --start e --end juntos.")
    summary_path = Path(releases_path).with_name("summary.json")
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    stored_start, stored_end = summary.get("window_start"), summary.get("window_end")
    if start and stored_start and stored_end:
        if timestamp(start) != timestamp(stored_start) or timestamp(end) != timestamp(stored_end):
            raise ValueError("Janela informada difere da janela da coleta em summary.json.")
    start, end = start or stored_start, end or stored_end
    if not start or not end:
        raise ValueError("Janela indisponível: informe --start e --end ou mantenha summary.json junto às releases.")
    return Window(timestamp(start), timestamp(end))


def write_csv(path, fields, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S02 — amostra-ouro e validação manual offline")
    parser.add_argument("--input", default="outputs/pipeline/selection/selected.json")
    parser.add_argument("--releases", default="outputs/pipeline/deployments.json")
    parser.add_argument("--output", default="outputs/gold_sample")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=60)
    parser.add_argument("--releases-per-repository", type=int, default=5)
    parser.add_argument("--start")
    parser.add_argument("--end")
    args = parser.parse_args(argv)
    try:
        window = observation_window(args.releases, args.start, args.end)
        repositories, releases, population = sample_records(
            load_records(args.input), load_records(args.releases), window,
            args.seed, args.count, args.releases_per_repository)
        directory = Path(args.output)
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("A pasta de saída deve estar vazia para preservar os rótulos dos avaliadores.")
        evaluator_rows = []
        for row in releases:
            evaluator_rows.append({**{key: row[key] for key in RELEASE_FIELDS if key != "tag_name"},
                                   "repository_url": f"https://github.com/{row['repository']}",
                                   "release_tag": row["tag_name"],
                                   **{field: "" for field in MANUAL_VALUES}})
        metadata = {"seed": args.seed, "sample_size": len(repositories),
                    "releases_per_repository": args.releases_per_repository,
                    "total_releases": len(releases), "eligible_repositories": population,
                    "inputs": {key: {"path": str(Path(path)), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                               for key, path in (("repositories", args.input), ("releases", args.releases))},
                    "window_start": window.start.isoformat(), "window_end": window.end.isoformat(),
                    "release_cutoff_inclusive": (window.end - timedelta(days=7)).isoformat(),
                    "algorithm": "random.Random(seed).sample: nomes lowercase ordenados; depois IDs de releases "
                                 "ordenados, usando o mesmo RNG na ordem dos repositórios sorteados",
                    "censoring": "Excluídas releases após window_end - 7 dias; sem substituição de repositórios.",
                    "manual_values": MANUAL_VALUES}
        directory.mkdir(parents=True, exist_ok=True)
        write_csv(directory / "sample_repositories.csv", REPOSITORY_FIELDS, repositories)
        write_csv(directory / "sample_releases.csv", RELEASE_FIELDS, releases)
        for number in range(1, 4):
            write_csv(directory / f"evaluator_{number}.csv", EVALUATOR_FIELDS, evaluator_rows)
        save_json(directory / "sample_metadata.json", metadata)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Amostra-ouro: {len(repositories)} repositórios e {len(releases)} releases em {directory}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
