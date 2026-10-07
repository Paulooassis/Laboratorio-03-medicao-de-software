"""Persistência dos candidatos avaliados, selecionados e funil."""
import csv
import json
import tempfile
from pathlib import Path


def save_deployments(directory, repositories, window, stats=None):
    """Cada execução recebe uma pasta exclusiva, preservando saídas anteriores."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    run_directory = Path(tempfile.mkdtemp(prefix="run-", dir=directory))
    summary = {"window_start": window.start.isoformat(), "window_end": window.end.isoformat(),
               "repositories": len(repositories),
               "repositories_with_errors": sum(bool(r["errors"]) for r in repositories),
               "releases_ignored_comparison_error": sum(r["summary"]["releases_ignored_comparison_error"] for r in repositories),
               "api": stats or {}}
    for name, data in (("deployments", repositories), ("summary", summary)):
        with (run_directory / f"{name}.json").open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return run_directory


def save_output(directory, rows, summary):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in (("repositories", rows), ("selected", [r for r in rows if r["included"]]), ("funnel", summary)):
        (directory / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["full_name", "url", "stars", "language", "created_at", "default_branch", "contributors",
              "valid_releases", "valid_workflow_runs", "uses_github_actions", "included", "exclusion_reason", "error"]
    for name, data in (("repositories", rows), ("selected", [r for r in rows if r["included"]])):
        with (directory / f"{name}.csv").open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)


def save_workflow_runs(directory, repositories, window, stats=None):
    """Nova pasta por execução; nunca sobrescreve amostras anteriores."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    run_directory = Path(tempfile.mkdtemp(prefix="run-", dir=directory))
    summary = {"window_start": window.start.isoformat(), "window_end": window.end.isoformat(),
               "repositories": len(repositories),
               "repositories_with_errors": sum(not r["complete"] for r in repositories),
               "complete": all(r["complete"] for r in repositories), "api": stats or {}}
    for category in ("success", "failure", "ignored", "total"):
        summary[category] = sum(r["summary"][category] for r in repositories)
    for name, data in (("workflow_runs", repositories), ("summary", summary)):
        with (run_directory / f"{name}.json").open("x", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
    return run_directory
