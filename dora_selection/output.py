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


def save_json(path, data):
    """Escrita atômica: uma interrupção não deixa o arquivo anterior pela metade."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)
    return path


DORA_FIELDS = ["repository", "stars", "language", "created_at", "contributors", "collection_complete",
               "releases", "releases_per_week", "commit_lead_time_hours", "release_lead_time_hours",
               "considered_runs", "change_failure_rate", "recovery_hours", "censored_episodes",
               "deployment_frequency_level", "lead_time_level", "change_failure_rate_level",
               "recovery_time_level", "median_score", "overall"]


def dora_row(repo, metrics, classification, complete):
    """Uma linha por repositório: metadados, valores das métricas e classificações."""
    ratings = classification["ratings"]
    return {"repository": repo["full_name"], "stars": repo.get("stars"), "language": repo.get("language"),
            "created_at": repo.get("created_at"), "contributors": repo.get("contributors"),
            "collection_complete": complete,
            "releases": metrics["deployment_frequency"]["releases"],
            "releases_per_week": metrics["deployment_frequency"]["releases_per_week"],
            "commit_lead_time_hours": metrics["lead_time_per_commit"]["median_hours"],
            "release_lead_time_hours": metrics["lead_time_per_release"]["median_hours"],
            "considered_runs": metrics["change_failure_rate"]["considered"],
            "change_failure_rate": metrics["change_failure_rate"]["change_failure_rate"],
            "recovery_hours": metrics["recovery_time"]["median_recovery_hours"],
            "censored_episodes": metrics["recovery_time"]["censored"],
            **{f"{name}_level": rating["level"] for name, rating in ratings.items()},
            "median_score": classification["median_score"], "overall": classification["overall"]}


def save_dora(directory, rows, metrics, classifications):
    """Métricas e classificações completas em JSON e o resumo por repositório em CSV."""
    directory = Path(directory)
    save_json(directory / "metrics.json", metrics)
    save_json(directory / "classification.json", classifications)
    with (directory / "dora.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=DORA_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
