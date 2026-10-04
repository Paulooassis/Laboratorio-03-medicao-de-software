"""Metadados, janela inclusiva em UTC e regras de inclusão."""
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from .api import APIError, links


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Datas precisam de fuso horário.")
    return result.astimezone(timezone.utc)


def classify_run(run):
    if run.get("status") != "completed":
        return None
    if run.get("conclusion") == "success":
        return "success"
    if run.get("conclusion") in {"failure", "timed_out", "startup_failure"}:
        return "failure"
    return None


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.start > self.end:
            raise ValueError("Janela inválida: use datas com fuso e início <= fim.")

    def contains(self, value):
        return bool(value) and self.start <= timestamp(value) <= self.end


def exclusion(row):
    if not row["uses_github_actions"]:
        return "no_github_actions"
    if row["valid_releases"] < 5:
        return "insufficient_releases"
    if row["valid_workflow_runs"] < 50:
        return "insufficient_workflow_runs"
    return None


class MetadataCollector:
    def __init__(self, client, window):
        self.client, self.window = client, window

    def _runs(self, path, branch, start, end):
        fmt = lambda d: d.isoformat(timespec="seconds").replace("+00:00", "Z")
        params = {"branch": branch, "event": "push", "created": f"{fmt(start)}..{fmt(end)}"}
        probe, _ = self.client.get(path, {**params, "per_page": 1})
        if not isinstance(probe, dict) or not isinstance(probe.get("total_count"), int):
            raise APIError("Resposta de workflow runs inválida.")
        if probe["total_count"] > 1000:
            from datetime import timedelta
            seconds = int((end - start).total_seconds())
            if seconds < 1:
                raise APIError("Mais de 1000 runs no mesmo segundo; contagem indisponível.")
            middle = start + timedelta(seconds=seconds // 2)
            yield from self._runs(path, branch, start, middle)
            yield from self._runs(path, branch, middle + timedelta(seconds=1), end)
        else:
            yield from self.client.pages(path, params, "workflow_runs")

    def collect(self, repo):
        row = {"full_name": repo.get("full_name"), "url": repo.get("html_url"),
               "stars": repo.get("stargazers_count"), "language": repo.get("language"),
               "created_at": repo.get("created_at"), "default_branch": repo.get("default_branch"),
               "contributors": None, "valid_releases": None, "valid_workflow_runs": None,
               "uses_github_actions": None, "included": False, "exclusion_reason": None,
               "error": None}
        try:
            if any(row[k] is None or row[k] == "" for k in ("full_name", "url", "stars", "created_at", "default_branch")):
                raise APIError("Metadados obrigatórios ausentes.")
            path = "/repos/" + row["full_name"]
            people, headers = self.client.get(path + "/contributors", {"per_page": 1, "anon": "true"})
            if not isinstance(people, list):
                raise APIError("Resposta de contribuidores inválida.")
            last = links(headers.get("Link", headers.get("link", ""))).get("last")
            if last:
                row["contributors"] = int(parse_qs(urlparse(last).query)["page"][0])
            elif links(headers.get("Link", headers.get("link", ""))).get("next"):
                row["contributors"] = sum(1 for _ in self.client.pages(path + "/contributors", {"anon": "true"}))
            else:
                row["contributors"] = len(people)
            workflows = list(self.client.pages(path + "/actions/workflows", key="workflows"))
            row["uses_github_actions"] = bool(workflows)
            row["valid_releases"] = sum(1 for r in self.client.pages(path + "/releases")
                if r.get("draft") is False and r.get("prerelease") is False
                and self.window.contains(r.get("published_at")))
            seen = set()
            count = 0
            for run in self._runs(path + "/actions/runs", row["default_branch"], self.window.start, self.window.end):
                if run.get("id") is None:
                    raise APIError("Workflow run sem identificador.")
                if run["id"] in seen:
                    continue
                seen.add(run["id"])
                if (run.get("head_branch") == row["default_branch"] and run.get("event") == "push"
                        and self.window.contains(run.get("created_at")) and classify_run(run)):
                    count += 1
            row["valid_workflow_runs"] = count
            row["exclusion_reason"] = exclusion(row)
            row["included"] = row["exclusion_reason"] is None
        except (APIError, ValueError, KeyError, TypeError, AttributeError) as exc:
            row["exclusion_reason"] = "collection_error"
            row["error"] = str(exc)
        return row


def funnel(rows, found, unique):
    stages = {"candidates_found": found, "unique_repositories": unique,
              "with_github_actions": 0, "with_sufficient_releases": 0,
              "with_sufficient_runs": 0, "included": 0, "discarded_by_reason": {}}
    for row in rows:
        if row["uses_github_actions"]:
            stages["with_github_actions"] += 1
            if row["valid_releases"] is not None and row["valid_releases"] >= 5:
                stages["with_sufficient_releases"] += 1
                if row["valid_workflow_runs"] is not None and row["valid_workflow_runs"] >= 50:
                    stages["with_sufficient_runs"] += 1
        stages["included"] += int(row["included"])
        reason = row["exclusion_reason"]
        if reason:
            stages["discarded_by_reason"][reason] = stages["discarded_by_reason"].get(reason, 0) + 1
    return stages
