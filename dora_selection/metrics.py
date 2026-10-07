"""Card 5: métricas DORA sobre os dados dos Cards 2 e 3.

Funções puras, sem rede nem persistência: cada uma recebe dados simples e pode ser
usada isoladamente. Datas ausentes ou inválidas são contabilizadas, nunca estimadas;
divisões sem amostra retornam None em vez de zero.
"""
from datetime import datetime, timedelta, timezone
from statistics import median as _median
from .selection import classify_run, timestamp


HOUR = 3600.0
WEEK = 604800.0
SUCCESS, FAILURE, IGNORED = "success", "failure", "ignored"
# Card 2 usa "completed"; dados montados à mão podem não trazer o campo.
USABLE_COMPARISON = {"completed", None}


def moment(value):
    """Instante em UTC; valor ausente ou inválido retorna None em vez de erro."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else None
    try:
        return timestamp(value)
    except (AttributeError, TypeError, ValueError):
        return None


def iso(value):
    """Representação ISO 8601 em UTC de um instante opcional."""
    return value.isoformat() if value is not None else None


def median(values):
    """Mediana da amostra, ignorando valores ausentes; None quando não há dados."""
    sample = [value for value in (values if values is not None else [])
              if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return _median(sample) if sample else None


def elapsed_hours(start, end):
    """Duração em horas entre dois instantes; None quando falta alguma data."""
    start, end = moment(start), moment(end)
    return None if start is None or end is None else (end - start).total_seconds() / HOUR


def week_key(value):
    """Rótulo da semana ISO (`AAAA-Www`) do instante em UTC."""
    year, number, _ = value.astimezone(timezone.utc).isocalendar()
    return f"{year}-W{number:02d}"


def iso_weeks(window):
    """Semanas ISO (segunda a domingo, UTC) que cobrem a janela inclusiva."""
    start, end = window.start.astimezone(timezone.utc), window.end.astimezone(timezone.utc)
    first = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = []
    while first <= end:
        last = first + timedelta(days=7) - timedelta(seconds=1)
        weeks.append({"week": week_key(first), "start": first.isoformat(), "end": last.isoformat(),
                      "releases": 0, "complete": start <= first and last <= end})
        first += timedelta(days=7)
    return weeks


def deployment_frequency(releases, window):
    """Deployment Frequency: releases por semana na janela inclusiva.

    `releases_per_week` é a média sobre a duração exata da janela; `weekly_counts`
    traz todas as semanas ISO cobertas, inclusive as sem release, e a mediana é
    calculada sobre elas. Semanas parciais nas pontas ficam marcadas em `complete`.
    """
    weeks = iso_weeks(window)
    index = {week["week"]: week for week in weeks}
    start, end = window.start.astimezone(timezone.utc), window.end.astimezone(timezone.utc)
    result = {"releases": 0, "ignored_missing_date": 0, "ignored_outside_window": 0,
              "weeks": None, "complete_weeks": sum(week["complete"] for week in weeks),
              "releases_per_week": None, "median_releases_per_week": None, "weekly_counts": weeks}
    for release in releases if releases is not None else []:
        when = moment((release or {}).get("published_at"))
        if when is None:
            result["ignored_missing_date"] += 1
            continue
        bucket = index.get(week_key(when)) if start <= when <= end else None
        if bucket is None:
            result["ignored_outside_window"] += 1
        else:
            result["releases"] += 1
            bucket["releases"] += 1
    # Janela inclusiva com precisão de segundos: o último segundo também conta.
    span = (end - start).total_seconds() + 1
    result["weeks"] = span / WEEK
    if result["weeks"] > 0:
        result["releases_per_week"] = result["releases"] / result["weeks"]
    result["median_releases_per_week"] = median(week["releases"] for week in weeks)
    return result


def release_interval(release):
    """Separa releases utilizáveis das que não oferecem intervalo confiável de commits."""
    release = release or {}
    status = release.get("comparison_status")
    if status == "no_previous_release":
        return release, None, [], "no_previous_release"
    if status not in USABLE_COMPARISON:
        return release, None, [], "no_comparison"
    published = moment(release.get("published_at"))
    if published is None:
        return release, None, [], "no_date"
    commits = [commit or {} for commit in (release.get("commits") or [])]
    return release, published, commits, "measured" if commits else "no_commits"


def _ignored_releases():
    """Motivos pelos quais uma release não produz Lead Time, sempre explícitos."""
    return {"no_previous_release": 0, "no_comparison": 0, "no_date": 0, "no_commits": 0,
            "no_commit_dates": 0}


def lead_time_per_commit(releases):
    """Lead Time por commit: publicação da release menos `commit.author.date`.

    Commits sem data não são estimados: entram em `commits_without_date`. Valores
    negativos (commit escrito depois da publicação, por rebase ou cherry-pick)
    são mantidos e contados em `negative`, sem descarte silencioso.
    """
    result = {"commits": [], "measured": 0, "median_hours": None, "negative": 0,
              "commits_without_date": 0, "releases_measured": 0, "releases_ignored": _ignored_releases()}
    for item in releases if releases is not None else []:
        release, published, commits, status = release_interval(item)
        if status != "measured":
            result["releases_ignored"][status] += 1
            continue
        result["releases_measured"] += 1
        for commit in commits:
            authored = moment(commit.get("author_date"))
            if authored is None:
                result["commits_without_date"] += 1
                continue
            value = elapsed_hours(authored, published)
            result["negative"] += int(value < 0)
            result["commits"].append({
                "repository": commit.get("repository") or release.get("repository"),
                "release_id": release.get("release_id"), "release_tag_name": release.get("tag_name"),
                "sha": commit.get("sha"), "author_date": commit.get("author_date"),
                "published_at": release.get("published_at"), "lead_time_hours": value})
    result["measured"] = len(result["commits"])
    result["median_hours"] = median(commit["lead_time_hours"] for commit in result["commits"])
    return result


def lead_time_per_release(releases):
    """Lead Time por release: do commit mais antigo do intervalo até a publicação.

    Cada release aparece com seu `status`, mesmo sem medição. `lead_time_hours`
    cobre o intervalo inteiro da release e `median_commit_lead_time_hours` resume
    seus commits. A mediana da amostra usa apenas releases medidas.
    """
    result = {"releases": [], "measured": 0, "median_hours": None,
              "median_commit_lead_time_hours": None, "commits_without_date": 0,
              "releases_ignored": _ignored_releases()}
    for item in releases if releases is not None else []:
        release, published, commits, status = release_interval(item)
        record = {"repository": release.get("repository"), "release_id": release.get("release_id"),
                  "tag_name": release.get("tag_name"), "published_at": release.get("published_at"),
                  "previous_tag_name": release.get("previous_tag_name"), "status": status,
                  "commits": len(commits), "measured_commits": 0,
                  "first_commit_author_date": None, "last_commit_author_date": None,
                  "lead_time_hours": None, "median_commit_lead_time_hours": None}
        result["releases"].append(record)
        if status != "measured":
            result["releases_ignored"][status] += 1
            continue
        dates = []
        for commit in commits:
            authored = moment(commit.get("author_date"))
            if authored is None:
                result["commits_without_date"] += 1
            else:
                dates.append(authored)
        if not dates:
            record["status"] = "no_commit_dates"
            result["releases_ignored"]["no_commit_dates"] += 1
            continue
        oldest = min(dates)
        record["measured_commits"] = len(dates)
        record["first_commit_author_date"] = iso(oldest)
        record["last_commit_author_date"] = iso(max(dates))
        record["lead_time_hours"] = elapsed_hours(oldest, published)
        record["median_commit_lead_time_hours"] = median(elapsed_hours(date, published) for date in dates)
        result["measured"] += 1
    result["median_hours"] = median(r["lead_time_hours"] for r in result["releases"])
    result["median_commit_lead_time_hours"] = median(
        r["median_commit_lead_time_hours"] for r in result["releases"])
    return result


def classification(run):
    """Classificação persistida pelo Card 3; recalculada com `classify_run` se ausente."""
    value = (run or {}).get("classification")
    return value if value in (SUCCESS, FAILURE, IGNORED) else (classify_run(run or {}) or IGNORED)


def change_failure_rate(runs):
    """Change Failure Rate = falhas / (sucessos + falhas) dos workflow runs.

    Runs `ignored` (cancelados, em andamento, conclusões desconhecidas) ficam fora
    do denominador. Sem runs considerados, a taxa é None, não zero.
    """
    result = {"total": 0, "success": 0, "failure": 0, "ignored": 0, "considered": 0,
              "change_failure_rate": None}
    for run in runs if runs is not None else []:
        result[classification(run)] += 1
        result["total"] += 1
    result["considered"] = result["success"] + result["failure"]
    if result["considered"]:
        result["change_failure_rate"] = result["failure"] / result["considered"]
    return result


def ordered_runs(runs):
    """Ordem cronológica por `created_at`, desempate por id; runs sem data ficam de fora."""
    dated, undated = [], 0
    for run in runs if runs is not None else []:
        run = run or {}
        when = moment(run.get("created_at"))
        if when is None:
            undated += 1
        else:
            dated.append((when, run.get("id") if isinstance(run.get("id"), int) else 0, run))
    dated.sort(key=lambda item: item[:2])
    return [run for _, _, run in dated], undated


def run_end(run):
    """Fim observado de um run: `updated_at` e, na falta dele, `created_at`."""
    return moment((run or {}).get("updated_at")) or moment((run or {}).get("created_at"))


def failure_episodes(runs, observed_until=None):
    """Episódios de falha e tempo de recuperação de uma sequência de runs.

    Falhas consecutivas pertencem ao mesmo episódio, encerrado pelo primeiro sucesso
    posterior: a recuperação vai do `created_at` da primeira falha ao `updated_at`
    desse sucesso. Runs `ignored` não abrem, estendem nem encerram episódios.

    Um episódio sem sucesso posterior fica censurado (`censored`): `observed_hours`
    é apenas um limite inferior e não entra na mediana. `observed_until` (por exemplo
    o fim da janela) define até quando a ausência de recuperação foi observada.
    """
    ordered, undated = ordered_runs(runs)
    result = {"episodes": [], "runs": len(ordered) + undated, "considered": 0, "ignored": 0,
              "runs_without_date": undated, "recovered": 0, "censored": 0, "inconsistent": 0,
              "median_recovery_hours": None}
    limit = moment(observed_until)
    episode = None
    for run in ordered:
        kind = classification(run)
        if kind == IGNORED:
            result["ignored"] += 1
            continue
        result["considered"] += 1
        when = moment(run.get("created_at"))
        if kind == FAILURE:
            if episode is None:
                episode = {"repository": run.get("repository"), "workflow_id": run.get("workflow_id"),
                           "failure_run_id": run.get("id"), "failures": 0, "started_at": iso(when),
                           "recovery_run_id": None, "recovered_at": None, "recovery_hours": None,
                           "observed_hours": None, "recovered": False, "censored": True,
                           "inconsistent": False, "_start": when, "_last": when}
                result["episodes"].append(episode)
            episode["failures"] += 1
            episode["_last"] = run_end(run) or when
        elif episode is not None:
            end = run_end(run) or when
            hours = elapsed_hours(episode["_start"], end)
            episode.update({"recovery_run_id": run.get("id"), "recovered_at": iso(end),
                            "recovery_hours": hours, "recovered": True, "censored": False,
                            "inconsistent": hours is None or hours < 0})
            episode = None
    for item in result["episodes"]:
        start, last = item.pop("_start"), item.pop("_last")
        if item["recovered"]:
            result["recovered"] += 1
            result["inconsistent"] += int(item["inconsistent"])
        else:
            # Limite inferior: observado até o fim da janela ou do último run.
            item["observed_hours"] = elapsed_hours(start, max(c for c in (limit, last, start) if c is not None))
            result["censored"] += 1
    result["median_recovery_hours"] = median(item["recovery_hours"] for item in result["episodes"]
                                             if item["recovered"] and not item["inconsistent"])
    return result


def recovery_time_by_workflow(workflows, observed_until=None):
    """Tempo de recuperação por workflow: episódios, mediana e episódios censurados.

    Cada workflow é uma série independente, pois uma falha é recuperada pelo próximo
    sucesso do mesmo workflow. `median_recovery_hours` reúne todos os episódios
    recuperados; `median_workflow_recovery_hours` é a mediana das medianas.
    """
    result = {"workflows": [], "with_failures": 0, "episodes": 0, "recovered": 0, "censored": 0,
              "inconsistent": 0, "median_recovery_hours": None, "median_workflow_recovery_hours": None}
    pooled = []
    for workflow in workflows if workflows is not None else []:
        workflow = workflow or {}
        episodes = failure_episodes(workflow.get("runs"), observed_until)
        result["workflows"].append({"repository": workflow.get("repository"),
                                    "workflow_id": workflow.get("workflow_id"),
                                    "name": workflow.get("name"), **episodes})
        for key in ("recovered", "censored", "inconsistent"):
            result[key] += episodes[key]
        result["episodes"] += len(episodes["episodes"])
        result["with_failures"] += int(bool(episodes["episodes"]))
        pooled += [item["recovery_hours"] for item in episodes["episodes"]
                   if item["recovered"] and not item["inconsistent"]]
    result["median_recovery_hours"] = median(pooled)
    result["median_workflow_recovery_hours"] = median(
        workflow["median_recovery_hours"] for workflow in result["workflows"])
    return result


def repository_metrics(window, releases=None, workflows=None, full_name=None):
    """Reúne as cinco métricas de um repositório sem acoplar as funções entre si."""
    runs = [run for workflow in (workflows or []) for run in ((workflow or {}).get("runs") or [])]
    return {"repository": full_name, "window_start": window.start.astimezone(timezone.utc).isoformat(),
            "window_end": window.end.astimezone(timezone.utc).isoformat(),
            "deployment_frequency": deployment_frequency(releases, window),
            "lead_time_per_release": lead_time_per_release(releases),
            "lead_time_per_commit": lead_time_per_commit(releases),
            "change_failure_rate": change_failure_rate(runs),
            "recovery_time": recovery_time_by_workflow(workflows, window.end)}


def aggregate_metrics(metrics):
    """Medianas da amostra; repositórios sem valor não entram em cada mediana."""
    rows = [row for row in (metrics if metrics is not None else []) if row]
    return {"repositories": len(rows),
            "median_releases_per_week": median(r["deployment_frequency"]["releases_per_week"] for r in rows),
            "median_release_lead_time_hours": median(r["lead_time_per_release"]["median_hours"] for r in rows),
            "median_commit_lead_time_hours": median(r["lead_time_per_commit"]["median_hours"] for r in rows),
            "median_change_failure_rate": median(r["change_failure_rate"]["change_failure_rate"] for r in rows),
            "median_recovery_hours": median(r["recovery_time"]["median_recovery_hours"] for r in rows),
            "censored_episodes": sum(r["recovery_time"]["censored"] for r in rows),
            "repositories_without_releases": sum(not r["deployment_frequency"]["releases"] for r in rows),
            "repositories_without_considered_runs": sum(
                r["change_failure_rate"]["considered"] == 0 for r in rows),
            "repositories_without_recovery": sum(
                r["recovery_time"]["median_recovery_hours"] is None for r in rows)}
