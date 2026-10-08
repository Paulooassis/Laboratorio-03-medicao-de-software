"""Card 2: releases, tags e commits; sem cálculo de Lead Time."""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from .api import APIError, GitHubClient, LOGGER
from .output import save_deployments
from .resilience import (add_resilience_arguments, client_options, collection_report,
                         configure_logging, open_checkpoint, parallel)
from .selection import Window, timestamp


COLLECTION_ERRORS = (APIError, ValueError, KeyError, TypeError, AttributeError)


class DeploymentCollector:
    def __init__(self, client, window, tag_dates=False, workers=1):
        self.client = client
        self.window = window
        self.tag_dates = tag_dates
        self.workers = workers

    def collect(self, full_name):
        result = {"full_name": full_name, "releases": [], "prereleases": [], "tags": [],
                  "errors": [], "summary": {"valid_releases": 0, "prereleases": 0,
                  "drafts_excluded": 0, "without_previous": 0,
                  "releases_ignored_comparison_error": 0, "comparisons_completed": 0}}
        path = "/repos/" + full_name
        # Última release publicada antes da janela: base da primeira comparação.
        earlier = None
        try:
            releases = list(self.client.pages(path + "/releases"))
            seen = set()
            for release in releases:
                identity = release["id"]
                if identity in seen:
                    continue
                seen.add(identity)
                if release["draft"] is True:
                    result["summary"]["drafts_excluded"] += 1
                    continue
                if release["draft"] is not False or not isinstance(release["prerelease"], bool):
                    raise APIError("Flags de release inválidas.")
                if not self.window.contains(release.get("published_at")):
                    published = release.get("published_at")
                    if (not release["prerelease"] and published and release.get("tag_name")
                            and timestamp(published) < self.window.start):
                        key = (timestamp(published), identity)
                        if earlier is None or key > earlier[0]:
                            earlier = (key, {"release_id": identity, "tag_name": release["tag_name"],
                                             "published_at": published, "commit_sha": None})
                    continue
                if not release.get("tag_name"):
                    raise APIError("Release sem tag_name.")
                item = {"repository": full_name, "release_id": identity,
                        "tag_name": release["tag_name"], "published_at": release["published_at"],
                        "draft": release["draft"], "prerelease": release["prerelease"],
                        "commit_sha": None, "previous_release_id": None, "previous_tag_name": None,
                        "comparison_status": "not_applicable" if release["prerelease"] else "pending",
                        "comparison_error": None, "commits": []}
                result["prereleases" if item["prerelease"] else "releases"].append(item)
            for key in ("releases", "prereleases"):
                result[key].sort(key=lambda r: (timestamp(r["published_at"]), r["release_id"]))
        except COLLECTION_ERRORS as exc:
            result["errors"].append({"stage": "releases", "error": str(exc)})
            # Uma listagem parcial não fornece pares consecutivos confiáveis.
            result["releases"] = []
            result["prereleases"] = []
            return result

        try:
            tags = list(self.client.pages(path + "/tags"))
            seen = set()
            dates = {}
            for tag in tags:
                name, sha = tag["name"], tag["commit"]["sha"]
                if not name or not sha:
                    raise APIError("Tag sem nome ou commit SHA.")
                if name in seen:
                    continue
                seen.add(name)
                item = {"repository": full_name, "name": name, "commit_sha": sha,
                        "commit_author_date": None, "error": None}
                if self.tag_dates:
                    try:
                        if sha not in dates:
                            commit, _ = self.client.get(path + "/commits/" + quote(sha, safe=""))
                            date = commit["commit"]["author"]["date"]
                            timestamp(date)
                            dates[sha] = date
                        item["commit_author_date"] = dates[sha]
                    except COLLECTION_ERRORS as exc:
                        item["error"] = str(exc)
                        result["errors"].append({"stage": "tag_commit", "tag_name": name, "error": str(exc)})
                result["tags"].append(item)
        except COLLECTION_ERRORS as exc:
            result["errors"].append({"stage": "tags", "error": str(exc)})

        tag_shas = {t["name"]: t["commit_sha"] for t in result["tags"]}
        for release in result["releases"] + result["prereleases"]:
            release["commit_sha"] = tag_shas.get(release["tag_name"])
        result["summary"]["valid_releases"] = len(result["releases"])
        result["summary"]["prereleases"] = len(result["prereleases"])
        # A release anterior pode estar fora da janela; só a primeira da história fica sem par.
        previous = earlier[1] if earlier else None
        if previous:
            previous["commit_sha"] = tag_shas.get(previous["tag_name"])
        pairs = []
        for release in result["releases"]:
            if previous is None:
                release["comparison_status"] = "no_previous_release"
                result["summary"]["without_previous"] += 1
            else:
                release["previous_release_id"] = previous["release_id"]
                release["previous_tag_name"] = previous["tag_name"]
                pairs.append((previous, release))
            # Mesmo após erro, o próximo par continua sendo de releases consecutivas.
            previous = release

        def compare(pair):
            previous, release = pair
            base = quote(previous["commit_sha"] or previous["tag_name"], safe="")
            head = quote(release["commit_sha"] or release["tag_name"], safe="")
            try:
                commits = []
                seen = set()
                for item in self.client.pages(path + f"/compare/{base}...{head}", {"page": 1}, "commits"):
                    sha = item["sha"]
                    if not sha:
                        raise APIError("Commit sem SHA.")
                    if sha in seen:
                        continue
                    seen.add(sha)
                    author_date = item["commit"]["author"]["date"]
                    timestamp(author_date)
                    commits.append({"repository": full_name, "release_id": release["release_id"],
                                    "release_tag_name": release["tag_name"], "sha": sha,
                                    "author_date": author_date, "message": item["commit"]["message"]})
                return commits, None
            except COLLECTION_ERRORS as exc:
                return None, exc

        # As comparações são independentes entre si e podem ser consultadas em paralelo.
        for (previous, release), (commits, exc) in zip(pairs, parallel(compare, pairs, self.workers)):
            if exc is None:
                # Só publica a comparação depois de completar todas as páginas.
                release["commits"] = commits
                release["comparison_status"] = "completed"
                result["summary"]["comparisons_completed"] += 1
            else:
                release["comparison_status"] = "not_found" if isinstance(exc, APIError) and exc.status_code == 404 else "error"
                release["comparison_error"] = str(exc)
                result["summary"]["releases_ignored_comparison_error"] += 1
                result["errors"].append({"stage": "compare", "release_id": release["release_id"],
                                         "previous_release_id": previous["release_id"], "error": str(exc)})
        return result


def collect_repositories(client, window, names, tag_dates=False, checkpoint=None, results=None, workers=1):
    """Card 4: repositórios sem erro em execução anterior não são recoletados."""
    collector = DeploymentCollector(client, window, tag_dates, workers)
    results = [] if results is None else results
    seen = set()
    for name in names:
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        done = checkpoint.done(name.casefold()) if checkpoint else None
        if done is not None:
            results.append(done)
            continue
        result = collector.collect(name)
        LOGGER.info("Releases de %s: %d releases, %d comparações (%d de %d repositórios).", name,
                    result["summary"]["valid_releases"], result["summary"]["comparisons_completed"],
                    len(results) + 1, len(names))
        if checkpoint:
            checkpoint.record(name.casefold(), result, not result["errors"])
        results.append(result)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S01 Card 2 — releases, tags e commits")
    parser.add_argument("--input", default="outputs/card1/selected.json")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", default="outputs/card2")
    parser.add_argument("--tag-dates", action="store_true", help="Consultar também commit.author.date de cada tag")
    add_resilience_arguments(parser)
    args = parser.parse_args(argv)
    configure_logging(args.log_file or Path(args.output) / "collection.log")
    try:
        window = Window(timestamp(args.start), timestamp(args.end))
        if window.start.microsecond or window.end.microsecond:
            raise ValueError("Use precisão de segundos, sem frações.")
        rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("Entrada deve ser uma lista JSON de repositórios do Card 1.")
        names = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("full_name"), str):
                raise ValueError("Repositório sem full_name.")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", row["full_name"]):
                raise ValueError("full_name deve ter o formato owner/repository.")
            if row.get("included", True) is True:
                names.append(row["full_name"])
        client = GitHubClient(**client_options(args))
        checkpoint = open_checkpoint(args, {"card": "2", "window_start": window.start.isoformat(),
                                            "window_end": window.end.isoformat(), "tag_dates": bool(args.tag_dates)})
    except (APIError, ValueError, OSError) as exc:
        parser.error(str(exc))
    results = []
    interrupted = False
    try:
        collect_repositories(client, window, names, args.tag_dates, checkpoint, results)
    except KeyboardInterrupt:
        # O diário já tem os repositórios concluídos; o parcial ainda é persistido.
        interrupted = True
        LOGGER.error("Coleta interrompida; retome com os mesmos --output/--state.")
    finally:
        if checkpoint:
            checkpoint.close()
    for repo in results:
        for error in repo["errors"]:
            LOGGER.error("%s [%s]: %s", repo["full_name"], error["stage"], error["error"])
    try:
        directory = save_deployments(args.output, results, window, collection_report(client, checkpoint))
    except OSError as exc:
        LOGGER.error("Erro de persistência: %s", exc)
        return 1
    print(f"Dados salvos em {directory}")
    return 1 if interrupted or any(repo["errors"] for repo in results) else 0


if __name__ == "__main__":
    sys.exit(main())
