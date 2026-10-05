import argparse
import json
import re
import sys
from pathlib import Path
from .api import APIError, GitHubClient
from .output import save_output, save_workflow_runs
from .search import CandidateSearch
from .selection import MetadataCollector, Window, collect_workflow_repositories, funnel, timestamp


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S01 — seleção e coleta de workflow runs")
    parser.add_argument("--card", choices=("1", "3"), default="1")
    parser.add_argument("--input", default="outputs/card1/selected.json", help="Amostra JSON do Card 1 (para Card 3)")
    parser.add_argument("--start", required=True, help="Início inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--end", required=True, help="Fim inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--min-stars", type=int, default=1001)
    parser.add_argument("--output", help="Pasta de saída (padrão outputs/card1 ou outputs/card3)")
    args = parser.parse_args(argv)
    args.output = args.output or f"outputs/card{args.card}"
    if args.target < 100 or args.min_stars < 1:
        parser.error("--target deve ser >= 100 e --min-stars >= 1")
    try:
        window = Window(timestamp(args.start), timestamp(args.end))
        if window.start.microsecond or window.end.microsecond:
            raise ValueError("Use precisão de segundos, sem frações.")
        client = GitHubClient()
    except (APIError, ValueError) as exc:
        parser.error(str(exc))
    if args.card == "3":
        try:
            repositories = json.loads(Path(args.input).read_text(encoding="utf-8"))
            if not isinstance(repositories, list) or any(
                not isinstance(repo, dict) or not isinstance(repo.get("full_name"), str)
                or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo["full_name"])
                for repo in repositories):
                raise ValueError("Entrada deve ser uma lista de repositórios com full_name owner/repository.")
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        results = collect_workflow_repositories(client, window, repositories)
        for repo in results:
            for error in repo["errors"]:
                print(f"{repo['full_name']}: {error['error']}", file=sys.stderr)
        try:
            directory = save_workflow_runs(args.output, results, window)
        except OSError as exc:
            print(f"Erro de persistência: {exc}", file=sys.stderr)
            return 1
        print(f"Workflow runs salvos em {directory}")
        return 0 if all(repo["complete"] for repo in results) else 1
    search = CandidateSearch(client, args.min_stars)
    collector = MetadataCollector(client, window)
    rows = []
    selected = 0
    error = None
    try:
        for candidate in search.candidates():
            row = collector.collect(candidate)
            rows.append(row)
            selected += int(row["included"])
            if row["error"]:
                print(f"{row['full_name']}: {row['error']}", file=sys.stderr)
            if selected >= args.target:
                break
    except APIError as exc:
        error = str(exc)
        print(error, file=sys.stderr)
    summary = funnel(rows, search.found, search.unique)
    summary.update({"window_start": window.start.isoformat(), "window_end": window.end.isoformat(),
                    "target": args.target, "target_reached": selected >= args.target,
                    "min_stars": args.min_stars, "search_error": error,
                    "stop_reason": "search_error" if error else "target_reached" if selected >= args.target else "candidates_exhausted"})
    save_output(args.output, rows, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if selected >= args.target and error is None else 1


if __name__ == "__main__":
    sys.exit(main())
