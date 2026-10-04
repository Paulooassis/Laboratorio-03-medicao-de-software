import argparse
import json
import sys
from .api import APIError, GitHubClient
from .output import save_output
from .search import CandidateSearch
from .selection import MetadataCollector, Window, funnel, timestamp


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lab03S01 Card 1 — seleção de repositórios")
    parser.add_argument("--start", required=True, help="Início inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--end", required=True, help="Fim inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--min-stars", type=int, default=1001)
    parser.add_argument("--output", default="outputs/card1")
    args = parser.parse_args(argv)
    if args.target < 100 or args.min_stars < 1:
        parser.error("--target deve ser >= 100 e --min-stars >= 1")
    try:
        window = Window(timestamp(args.start), timestamp(args.end))
        if window.start.microsecond or window.end.microsecond:
            raise ValueError("Use precisão de segundos, sem frações.")
        client = GitHubClient()
    except (APIError, ValueError) as exc:
        parser.error(str(exc))
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
