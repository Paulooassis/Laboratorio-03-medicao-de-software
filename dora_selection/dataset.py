"""S2: dataset final em CSV, nos níveis de repositório, release e episódio de falha.

Funções puras sobre os resultados de `metrics`, `cfr` e `rating`, mais a gravação dos
arquivos. Nenhuma métrica é recalculada aqui: as tabelas só achatam o que já foi medido
e trazem junto as contagens de censura e de releases ignoradas, que precisam ser
reportadas. Célula vazia significa métrica sem amostra, nunca zero.
"""
import csv
from collections import Counter
from pathlib import Path
from .metrics import moment


RUN_QUERY_LIMIT = 1000
REPOSITORY_FIELDS = [
    "repository", "url", "stars", "language", "contributors", "created_at", "age_days", "project_type",
    "gold_sample", "collection_complete",
    "releases", "deployment_frequency_per_week", "median_releases_per_week",
    "lead_time_a_hours", "lead_time_a_releases", "lead_time_b_hours", "lead_time_b_commits",
    "releases_ignored", "releases_no_previous", "releases_compare_not_found", "releases_compare_error",
    "releases_no_new_commits", "releases_no_commit_dates",
    "cfr_a", "cfr_a_runs", "cfr_a_failures", "runs_ignored",
    "cfr_b", "cfr_b_version", "cfr_b_evaluated", "cfr_b_failed", "cfr_b_corrective", "cfr_b_censored",
    "rework_rate", "rework_evaluated", "rework_corrective", "rework_no_previous",
    "recovery_hours", "recovery_episodes", "recovery_recovered", "recovery_censored",
    "recovery_censored_share", "recovery_inconsistent",
    "deployment_frequency_level", "lead_time_level", "change_failure_rate_level", "recovery_time_level",
    "median_score", "overall"]
RELEASE_FIELDS = [
    "repository", "release_id", "tag_name", "published_at", "previous_tag_name", "comparison_status",
    "lead_time_status", "commits", "measured_commits", "first_commit_author_date", "lead_time_a_hours",
    "lead_time_b_hours", "corrective", "cfr_b_censored", "cfr_b_failed", "fixed_by_tag_name"]
EPISODE_FIELDS = [
    "repository", "workflow_id", "workflow_name", "failure_run_id", "failures", "started_at",
    "recovery_run_id", "recovered_at", "recovery_hours", "observed_hours", "recovered", "censored",
    "inconsistent"]
FUNNEL_STAGES = (("candidates_found", "Candidatos recebidos da busca"),
                 ("unique_repositories", "Repositórios únicos avaliados"),
                 ("with_github_actions", "Com GitHub Actions"),
                 ("with_sufficient_releases", "Com 5 ou mais releases na janela"),
                 ("with_sufficient_runs", "Com 50 ou mais workflow runs válidos"),
                 ("included", "Incluídos na amostra"))


def load_project_types(path):
    """Tipo do projeto consensual (S2-06) dos repositórios da amostra-ouro, por nome em minúsculas."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if any(not row.get("repository") or not row.get("project_type") for row in rows):
        raise ValueError(f"{path}: esperadas as colunas repository e project_type preenchidas.")
    return {row["repository"].strip().casefold(): row["project_type"].strip() for row in rows}


def share(part, total):
    """Proporção; None sem amostra, em vez de zero."""
    return part / total if total else None


def repository_row(repo, deployment, measured, classification, complete, window, project_types=None):
    """Uma linha por repositório: fatores da RQ 06, as métricas em todas as variantes e as contagens."""
    name = repo["full_name"]
    created = moment(repo.get("created_at"))
    kind = (project_types or {}).get(name.casefold())
    frequency, recovery = measured["deployment_frequency"], measured["recovery_time"]
    per_release, per_commit = measured["lead_time_per_release"], measured["lead_time_per_commit"]
    runs = measured["change_failure_rate"]
    delivery = measured.get("change_failure_rate_b") or {}
    rework = measured.get("rework") or {}
    ignored = per_release["releases_ignored"]
    compared = Counter(release.get("comparison_status") for release in (deployment.get("releases") or []))
    return {
        "repository": name, "url": repo.get("url"), "stars": repo.get("stars"),
        "language": repo.get("language"), "contributors": repo.get("contributors"),
        "created_at": repo.get("created_at"),
        "age_days": None if created is None else (window.end - created).days,
        "project_type": kind, "gold_sample": kind is not None, "collection_complete": complete,
        "releases": frequency["releases"], "deployment_frequency_per_week": frequency["releases_per_week"],
        "median_releases_per_week": frequency["median_releases_per_week"],
        "lead_time_a_hours": per_release["median_hours"], "lead_time_a_releases": per_release["measured"],
        "lead_time_b_hours": per_commit["median_hours"], "lead_time_b_commits": per_commit["measured"],
        "releases_ignored": sum(ignored.values()), "releases_no_previous": ignored["no_previous_release"],
        "releases_compare_not_found": compared["not_found"], "releases_compare_error": compared["error"],
        "releases_no_new_commits": ignored["no_commits"],
        "releases_no_commit_dates": ignored["no_commit_dates"],
        "cfr_a": runs["change_failure_rate"], "cfr_a_runs": runs["considered"],
        "cfr_a_failures": runs["failure"], "runs_ignored": runs["ignored"],
        "cfr_b": delivery.get("change_failure_rate"), "cfr_b_version": delivery.get("heuristic"),
        "cfr_b_evaluated": delivery.get("evaluated"), "cfr_b_failed": delivery.get("failed"),
        "cfr_b_corrective": delivery.get("corrective"), "cfr_b_censored": delivery.get("censored"),
        "rework_rate": rework.get("rework_rate"), "rework_evaluated": rework.get("evaluated"),
        "rework_corrective": rework.get("corrective"), "rework_no_previous": rework.get("no_previous"),
        "recovery_hours": recovery["median_recovery_hours"], "recovery_episodes": recovery["episodes"],
        "recovery_recovered": recovery["recovered"], "recovery_censored": recovery["censored"],
        "recovery_censored_share": share(recovery["censored"], recovery["episodes"]),
        "recovery_inconsistent": recovery["inconsistent"],
        **{f"{metric}_level": rating["level"] for metric, rating in classification["ratings"].items()},
        "median_score": classification["median_score"], "overall": classification["overall"]}


def release_rows(deployment, measured):
    """Uma linha por release da janela: Lead Time (a) e (b) e o resultado da heurística corretiva."""
    compared = {release.get("release_id"): release.get("comparison_status")
                for release in (deployment.get("releases") or [])}
    delivery = {detail["release_id"]: detail
                for detail in (measured.get("change_failure_rate_b") or {}).get("details", [])}
    rows = []
    for record in measured["lead_time_per_release"]["releases"]:
        detail = delivery.get(record["release_id"], {})
        rows.append({
            "repository": measured["repository"], "release_id": record["release_id"],
            "tag_name": record["tag_name"], "published_at": record["published_at"],
            "previous_tag_name": record["previous_tag_name"],
            "comparison_status": compared.get(record["release_id"]), "lead_time_status": record["status"],
            "commits": record["commits"], "measured_commits": record["measured_commits"],
            "first_commit_author_date": record["first_commit_author_date"],
            "lead_time_a_hours": record["lead_time_hours"],
            "lead_time_b_hours": record["median_commit_lead_time_hours"],
            "corrective": detail.get("corrective"), "cfr_b_censored": detail.get("censored"),
            "cfr_b_failed": detail.get("failed"), "fixed_by_tag_name": detail.get("fixed_by_tag_name")})
    return rows


def episode_rows(measured):
    """Uma linha por episódio de falha, recuperado ou censurado, de cada workflow."""
    rows = []
    for workflow in measured["recovery_time"]["workflows"]:
        for episode in workflow["episodes"]:
            rows.append({**{field: episode.get(field) for field in EPISODE_FIELDS},
                         "repository": measured["repository"], "workflow_id": workflow["workflow_id"],
                         "workflow_name": workflow["name"]})
    return rows


def build_dataset(window, selected, deployments, metrics, classifications, table, project_types=None):
    """Tabelas de repositório, release e episódio para os repositórios selecionados."""
    collected = {repo["full_name"].casefold(): repo for repo in deployments}
    dataset = {"repositories": [], "releases": [], "episodes": []}
    for repo, measured, classification, row in zip(selected, metrics, classifications, table):
        deployment = collected.get(repo["full_name"].casefold()) or {}
        dataset["repositories"].append(repository_row(repo, deployment, measured, classification,
                                                      row["collection_complete"], window, project_types))
        dataset["releases"] += release_rows(deployment, measured)
        dataset["episodes"] += episode_rows(measured)
    return dataset


def censoring(rows):
    """Censura na amostra: releases fora do denominador do CFR (b) e episódios sem recuperação (RQ 04)."""
    total = lambda field: sum(row[field] or 0 for row in rows)
    return {"cfr_b_releases": total("cfr_b_evaluated") + total("cfr_b_censored"),
            "cfr_b_censored_releases": total("cfr_b_censored"),
            "cfr_b_censored_share": share(total("cfr_b_censored"),
                                          total("cfr_b_evaluated") + total("cfr_b_censored")),
            "recovery_episodes": total("recovery_episodes"),
            "recovery_censored_episodes": total("recovery_censored"),
            "recovery_censored_share": share(total("recovery_censored"), total("recovery_episodes")),
            "repositories_with_censored_majority": sum(
                (row["recovery_censored_share"] or 0) > 0.5 for row in rows)}


def collection_checks(deployments, workflow_runs):
    """Casos que só aparecem em escala: comparações perdidas, releases sem intervalo e meses no teto.

    Um mês com 1000 ou mais runs não cabe em uma consulta filtrada da API; a coleta já o
    subdivide, e aqui ele fica registrado para conferência.
    """
    statuses, without_commits, large = Counter(), 0, 0
    for repo in deployments:
        for release in repo["releases"]:
            statuses[release["comparison_status"]] += 1
            without_commits += release["comparison_status"] == "completed" and not release["commits"]
            large += len(release["commits"]) > 250
    saturated = []
    for repo in workflow_runs:
        months = Counter(run["created_at"][:7] for workflow in repo["workflows"] for run in workflow["runs"])
        saturated += [{"repository": repo["full_name"], "month": month, "runs": count}
                      for month, count in sorted(months.items()) if count >= RUN_QUERY_LIMIT]
    return {"compare_not_found": statuses["not_found"], "compare_error": statuses["error"],
            "releases_without_previous": statuses["no_previous_release"],
            "releases_without_new_commits": without_commits,
            "releases_over_250_commits": large,
            "months_at_run_limit": len(saturated), "months_at_run_limit_detail": saturated}


def funnel_table(funnel):
    """Funil da seleção em Markdown, regenerado a cada execução."""
    lines = ["| Etapa | Repositórios |", "| --- | ---: |"]
    lines += [f"| {label} | {funnel.get(key, 0)} |" for key, label in FUNNEL_STAGES]
    lines += ["", "| Motivo de descarte | Repositórios |", "| --- | ---: |"]
    reasons = funnel.get("discarded_by_reason") or {}
    lines += [f"| `{reason}` | {reasons[reason]} |" for reason in sorted(reasons, key=lambda r: (-reasons[r], r))]
    return "\n".join(lines) + "\n"


def write_csv(path, fields, rows):
    """Escrita atômica, como em `save_json`: uma interrupção não deixa o CSV pela metade."""
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def save_dataset(directory, dataset, funnel):
    """Grava `repositorios.csv`, os CSVs auxiliares e o funil; devolve os caminhos gravados."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = {"repositories": directory / "repositorios.csv", "releases": directory / "releases.csv",
             "episodes": directory / "episodios_falha.csv", "funnel": directory / "funil.md"}
    write_csv(files["repositories"], REPOSITORY_FIELDS, dataset["repositories"])
    write_csv(files["releases"], RELEASE_FIELDS, dataset["releases"])
    write_csv(files["episodes"], EPISODE_FIELDS, dataset["episodes"])
    files["funnel"].write_text(funnel_table(funnel), encoding="utf-8")
    return {name: str(path) for name, path in files.items()}
