"""S3 (#41): unidades de deploy alternativas para a análise de sensibilidade (RQ 07).

A definição principal usa releases publicadas. A RQ 07 compara com duas variantes:

- `release_prerelease`: releases e pré-releases da janela numa só sequência
  cronológica; cada deploy é comparado com o anterior dessa sequência combinada;
- `tag`: tags cuja data é o `commit.author.date` do commit apontado (tags não têm data
  própria). Tags no mesmo commit formam um só deploy, para que monorepos que marcam
  vários pacotes de uma vez não multipliquem a frequência.

As datas das tags vêm da API GraphQL, ordenadas pela data do commit (`TAG_COMMIT_DATE`),
100 por consulta. A paginação para ao passar do início da janela: um repositório com
milhares de tags antigas custa poucas consultas, em vez de uma chamada REST por tag.

As métricas de cada unidade são as mesmas funções de `metrics` e `cfr` da definição
principal; aqui só se montam as sequências de deploys e as comparações entre eles.
"""
from pathlib import Path
from .api import LOGGER
from .cfr import cfr_entrega
from .dataset import share, write_csv
from .deployments import COLLECTION_ERRORS, DeploymentCollector, comparison_key
from .metrics import deployment_frequency, lead_time_per_commit, lead_time_per_release, moment


UNITS = ("release", "release_prerelease", "tag")
TAG_PAGE = 100
COMMIT_FIELDS = "oid authoredDate committedDate"
TAG_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    refs(refPrefix: "refs/tags/", first: %d, after: $cursor,
         orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        target {
          __typename
          ... on Commit { %s }
          ... on Tag { target { __typename ... on Commit { %s }
                                ... on Tag { target { __typename ... on Commit { %s } } } } }
        }
      }
    }
  }
}
""" % (TAG_PAGE, COMMIT_FIELDS, COMMIT_FIELDS, COMMIT_FIELDS)
VARIANT_FIELDS = [
    "repository", "unit", "deploys", "deploys_without_date", "tags", "deployment_frequency_per_week",
    "lead_time_a_hours", "lead_time_a_deploys", "lead_time_b_hours", "lead_time_b_commits",
    "deploys_ignored", "deploys_no_previous", "compare_not_found", "compare_error", "deploys_no_new_commits",
    "deploys_no_commit_dates", "cfr_b", "cfr_b_evaluated", "cfr_b_failed", "cfr_b_corrective",
    "cfr_b_censored", "collection_complete"]
DEPLOY_FIELDS = [
    "repository", "unit", "tag_name", "tags", "prerelease", "published_at", "commit_sha", "previous_tag_name",
    "comparison_status", "lead_time_status", "commits", "measured_commits", "lead_time_a_hours",
    "lead_time_b_hours", "corrective", "cfr_b_censored", "cfr_b_failed", "fixed_by_tag_name"]


def tag_commit(target):
    """Commit apontado pela tag, seguindo até duas tags anotadas; None se não for commit."""
    for _ in range(3):
        if not isinstance(target, dict):
            return None
        if target.get("__typename") == "Commit":
            return target
        target = target.get("target")
    return None


def collect_tag_dates(client, full_name, window):
    """Tags com a data do commit, da mais recente até a primeira página anterior à janela.

    A ordenação da API usa a data do commit (committer); como a de autoria não é
    posterior a ela, toda tag que fica depois do corte tem autoria anterior à janela.
    Devolve as tags lidas, o nº de consultas e as tags que não apontam para um commit.
    """
    owner, name = full_name.split("/", 1)
    result = {"tags": [], "pages": 0, "without_commit": 0}
    cursor = None
    while True:
        data = client.graphql(TAG_QUERY, {"owner": owner, "name": name, "cursor": cursor})
        refs = ((data.get("data") or {}).get("repository") or {}).get("refs")
        if not isinstance(refs, dict) or not isinstance(refs.get("nodes"), list):
            raise ValueError(f"Resposta GraphQL sem refs para {full_name}.")
        result["pages"] += 1
        oldest = None
        for node in refs["nodes"]:
            commit = tag_commit(node.get("target"))
            if commit is None or not commit.get("authoredDate"):
                result["without_commit"] += 1
                continue
            committed = moment(commit.get("committedDate"))
            oldest = committed if oldest is None or (committed and committed < oldest) else oldest
            result["tags"].append({"name": node["name"], "commit_sha": commit["oid"],
                                   "author_date": commit["authoredDate"],
                                   "committed_date": commit.get("committedDate")})
        info = refs.get("pageInfo") or {}
        if not info.get("hasNextPage") or (oldest is not None and oldest < window.start):
            return result
        cursor = info.get("endCursor")


def tag_deploys(full_name, tags, window):
    """Tags da janela agrupadas por commit, em ordem de data, e a última tag antes dela.

    Cada grupo vira um deploy com o nome da primeira tag em ordem alfabética e a
    contagem de tags em `tags`. A base da primeira comparação é a tag mais recente
    anterior à janela, como a release anterior na definição principal.
    """
    groups, before = {}, None
    for tag in tags:
        when = moment(tag["author_date"])
        if when is None:
            continue
        if when < window.start:
            if before is None or (when, tag["name"]) > before[0]:
                before = ((when, tag["name"]), tag)
        elif when <= window.end:
            groups.setdefault(tag["commit_sha"], []).append(tag)
    deploys = []
    for sha, group in groups.items():
        names = sorted(tag["name"] for tag in group)
        deploys.append({"repository": full_name, "release_id": None, "tag_name": names[0], "tags": len(names),
                        "prerelease": None, "published_at": group[0]["author_date"], "commit_sha": sha,
                        "previous_tag_name": None, "comparison_status": "pending", "commits": []})
    deploys.sort(key=lambda deploy: (moment(deploy["published_at"]), deploy["tag_name"]))
    previous = None
    if before:
        tag = before[1]
        previous = {"tag_name": tag["name"], "commit_sha": tag["commit_sha"]}
    return deploys, previous


def release_prerelease_deploys(deployment):
    """Releases e pré-releases da janela numa só sequência; base é a release anterior à janela."""
    deploys = []
    for release in (deployment.get("releases") or []) + (deployment.get("prereleases") or []):
        deploys.append({key: release.get(key) for key in
                        ("repository", "release_id", "tag_name", "published_at", "prerelease", "commit_sha")}
                       | {"tags": 1, "previous_tag_name": None, "comparison_status": "pending", "commits": []})
    deploys.sort(key=lambda deploy: (moment(deploy["published_at"]), deploy["release_id"] or 0))
    previous = None
    first = next(iter(deployment.get("releases") or []), None)
    if first and first.get("previous_tag_name"):
        shas = {tag["name"]: tag["commit_sha"] for tag in deployment.get("tags") or []}
        previous = {"tag_name": first["previous_tag_name"], "commit_sha": shas.get(first["previous_tag_name"])}
    return deploys, previous


def compare_deploys(collector, full_name, deploys, previous):
    """Preenche commits e status de comparação de cada deploy com o anterior da sequência.

    Os commits guardam só SHA, data de autoria e a primeira linha da mensagem, que é o que
    o Lead Time e a heurística corretiva usam. Devolve os erros de comparação.
    """
    pairs = []
    for deploy in deploys:
        if previous is None:
            deploy["comparison_status"] = "no_previous_release"
        else:
            deploy["previous_tag_name"] = previous["tag_name"]
            pairs.append((previous, deploy))
        previous = deploy
    comparisons = collector.compare_pairs(full_name, pairs)
    errors = []
    for before, deploy in pairs:
        commits, exc = comparisons[comparison_key((before, deploy))]
        if exc is None:
            deploy["commits"] = [{"sha": commit["sha"], "author_date": commit["author_date"],
                                  "message": (commit.get("message") or "").split("\n", 1)[0]}
                                 for commit in commits]
            deploy["comparison_status"] = "completed"
        else:
            deploy["comparison_status"] = "not_found" if getattr(exc, "status_code", None) == 404 else "error"
            errors.append({"stage": "compare", "tag_name": deploy["tag_name"],
                           "previous_tag_name": before["tag_name"], "error": str(exc)})
    return errors


def collect_variant(client, window, deployment, workers=1):
    """Deploys das duas unidades alternativas de um repositório, já comparados."""
    full_name = deployment["full_name"]
    collector = DeploymentCollector(client, window, workers=workers)
    result = {"full_name": full_name, "units": {}, "errors": [],
              "summary": {"tag_pages": 0, "tags_read": 0, "tags_without_commit": 0}}
    deploys, previous = release_prerelease_deploys(deployment)
    result["errors"] += compare_deploys(collector, full_name, deploys, previous)
    result["units"]["release_prerelease"] = deploys
    try:
        tags = collect_tag_dates(client, full_name, window)
    except COLLECTION_ERRORS as exc:
        result["errors"].append({"stage": "tag_dates", "error": str(exc)})
        result["units"]["tag"] = None
        return result
    result["summary"].update(tag_pages=tags["pages"], tags_read=len(tags["tags"]),
                             tags_without_commit=tags["without_commit"])
    deploys, previous = tag_deploys(full_name, tags["tags"], window)
    result["errors"] += compare_deploys(collector, full_name, deploys, previous)
    result["units"]["tag"] = deploys
    return result


def collect_variants(client, window, deployments, checkpoint=None, results=None, workers=1):
    """Card 4 aplicado às variantes: repositórios concluídos sem erro não são recoletados."""
    results = [] if results is None else results
    for number, deployment in enumerate(deployments, 1):
        unit = deployment["full_name"].casefold()
        done = checkpoint.done(unit) if checkpoint else None
        if done is None:
            done = collect_variant(client, window, deployment, workers)
            if checkpoint:
                checkpoint.record(unit, done, not done["errors"])
            units = done["units"]
            LOGGER.info("Variantes de %s: %d release+pré-release, %s deploys por tag (%d de %d).",
                        deployment["full_name"], len(units["release_prerelease"]),
                        "?" if units["tag"] is None else len(units["tag"]), number, len(deployments))
        results.append(done)
    return results


def variant_metrics(deploys, window):
    """As métricas que dependem da unidade de deploy, com as mesmas funções da definição principal."""
    return {"deployment_frequency": deployment_frequency(deploys, window),
            "lead_time_per_release": lead_time_per_release(deploys),
            "lead_time_per_commit": lead_time_per_commit(deploys),
            "change_failure_rate_b": cfr_entrega(deploys, window.end)}


def variant_row(full_name, unit, deploys, measured, complete):
    """Uma linha por repositório e unidade; célula vazia é métrica sem amostra, nunca zero."""
    frequency, per_release = measured["deployment_frequency"], measured["lead_time_per_release"]
    per_commit, delivery = measured["lead_time_per_commit"], measured["change_failure_rate_b"]
    ignored = per_release["releases_ignored"]
    statuses = [deploy.get("comparison_status") for deploy in deploys]
    return {"repository": full_name, "unit": unit, "deploys": frequency["releases"],
            "deploys_without_date": frequency["ignored_missing_date"],
            "tags": sum(deploy.get("tags") or 1 for deploy in deploys),
            "deployment_frequency_per_week": frequency["releases_per_week"],
            "lead_time_a_hours": per_release["median_hours"], "lead_time_a_deploys": per_release["measured"],
            "lead_time_b_hours": per_commit["median_hours"], "lead_time_b_commits": per_commit["measured"],
            "deploys_ignored": sum(ignored.values()), "deploys_no_previous": ignored["no_previous_release"],
            "compare_not_found": statuses.count("not_found"), "compare_error": statuses.count("error"),
            "deploys_no_new_commits": ignored["no_commits"], "deploys_no_commit_dates": ignored["no_commit_dates"],
            "cfr_b": delivery["change_failure_rate"], "cfr_b_evaluated": delivery["evaluated"],
            "cfr_b_failed": delivery["failed"], "cfr_b_corrective": delivery["corrective"],
            "cfr_b_censored": delivery["censored"], "collection_complete": complete}


def deploy_rows(full_name, unit, deploys, measured):
    """Uma linha por deploy, com Lead Time e o resultado da heurística corretiva."""
    lead = {id(deploy): record for deploy, record in zip(deploys, measured["lead_time_per_release"]["releases"])}
    delivery = {(detail["tag_name"], detail["published_at"]): detail
                for detail in measured["change_failure_rate_b"]["details"]}
    rows = []
    for deploy in deploys:
        record, detail = lead[id(deploy)], delivery.get((deploy["tag_name"], deploy["published_at"]), {})
        rows.append({"repository": full_name, "unit": unit, "tag_name": deploy["tag_name"],
                     "tags": deploy.get("tags") or 1, "prerelease": deploy.get("prerelease"),
                     "published_at": deploy["published_at"], "commit_sha": deploy.get("commit_sha"),
                     "previous_tag_name": deploy.get("previous_tag_name"),
                     "comparison_status": deploy.get("comparison_status"), "lead_time_status": record["status"],
                     "commits": record["commits"], "measured_commits": record["measured_commits"],
                     "lead_time_a_hours": record["lead_time_hours"],
                     "lead_time_b_hours": record["median_commit_lead_time_hours"],
                     "corrective": detail.get("corrective"), "cfr_b_censored": detail.get("censored"),
                     "cfr_b_failed": detail.get("failed"), "fixed_by_tag_name": detail.get("fixed_by_tag_name")})
    return rows


def build_variants(window, selected, deployments, variants):
    """Tabelas `variantes.csv` e `deploys_variantes.csv` para as três unidades de deploy.

    A unidade `release` repete a definição principal, para que a RQ 07 leia as três
    unidades do mesmo arquivo. Uma unidade cuja coleta falhou fica sem linha de deploy e
    com `collection_complete` falso, em vez de parecer um repositório sem deploys.

    Um `compare` com erro (inclusive o 404 de uma tag apagada) não torna a unidade
    incompleta: como na definição principal, o deploy fica fora do Lead Time e é contado em
    `compare_not_found`/`compare_error`. A falha de uma unidade também não invalida as outras.
    """
    released = {repo["full_name"].casefold(): repo for repo in deployments}
    alternatives = {repo["full_name"].casefold(): repo for repo in variants}
    tables = {"variants": [], "deploys": []}
    for repo in selected:
        name = repo["full_name"]
        deployment = released.get(name.casefold()) or {}
        variant = alternatives.get(name.casefold()) or {"units": {}, "errors": [{"stage": "missing"}]}
        # A listagem de releases com erro vira lista vazia na coleta; não é "zero deploys".
        listing_failed = any(error["stage"] == "releases" for error in deployment.get("errors") or [])
        units = {"release": deployment.get("releases"), **variant["units"]}
        for unit in UNITS:
            deploys = units.get(unit)
            complete = deploys is not None and not (listing_failed and unit != "tag")
            deploys = deploys or []
            measured = variant_metrics(deploys, window)
            tables["variants"].append(variant_row(name, unit, deploys, measured, complete))
            tables["deploys"] += deploy_rows(name, unit, deploys, measured)
    return tables


def variant_summary(variants):
    """Custo e completude da coleta das variantes para o `summary.json`."""
    total = lambda key: sum(repo["summary"][key] for repo in variants)
    tag_deploys = [repo["units"].get("tag") for repo in variants]
    return {"repositories": len(variants),
            "repositories_with_errors": sum(bool(repo["errors"]) for repo in variants),
            "tag_dates_failed": sum(deploys is None for deploys in tag_deploys),
            "graphql_pages": total("tag_pages"), "tags_read": total("tags_read"),
            "tags_without_commit": total("tags_without_commit"),
            "release_prerelease_deploys": sum(len(repo["units"]["release_prerelease"]) for repo in variants),
            "tag_deploys": sum(len(deploys or []) for deploys in tag_deploys),
            "compare_errors": sum(error["stage"] == "compare" for repo in variants for error in repo["errors"]),
            "tag_share_collapsed": share(sum(deploy["tags"] - 1 for deploys in tag_deploys for deploy in deploys or []),
                                         sum(deploy["tags"] for deploys in tag_deploys for deploy in deploys or []))}


def save_variants(directory, tables):
    """Grava `variantes.csv` e `deploys_variantes.csv` ao lado do dataset principal."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = {"variants": directory / "variantes.csv", "deploys": directory / "deploys_variantes.csv"}
    write_csv(files["variants"], VARIANT_FIELDS, tables["variants"])
    write_csv(files["deploys"], DEPLOY_FIELDS, tables["deploys"])
    return {name: str(path) for name, path in files.items()}
