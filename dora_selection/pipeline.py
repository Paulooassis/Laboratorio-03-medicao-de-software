"""Card 8: seleção, coleta, métricas, classificação e dataset final em um único comando.

Reúne os Cards 1 a 6 sem mudar nenhuma regra: um só cliente, um só cache e um diário
de retomada por etapa. Cada etapa é persistida ao terminar, de modo que uma execução
interrompida recomeça de onde parou. Dentro de cada repositório, os meses de workflow
runs e as comparações entre releases são consultados em paralelo (`--workers`).
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from .api import APIError, GitHubClient, LOGGER
from .dataset import build_dataset, censoring, collection_checks, load_project_types, save_dataset
from .deployments import collect_repositories
from .metrics import aggregate_metrics, repository_metrics
from .cfr import HEURISTIC_VERSION, cfr_entrega, official_version, rework_rate
from .output import dora_row, save_dora, save_json, save_output
from .rating import classify_repository, classify_sample
from .resilience import (Checkpoint, add_resilience_arguments, client_options, collection_report,
                         configure_logging)
from .selection import (CandidateSearch, MetadataCollector, Window, collect_workflow_repositories,
                        funnel, timestamp)
from .variants import build_variants, collect_variants, save_variants, variant_summary


STAGES = ("selection", "deployments", "workflow_runs", "variants")
# Versão das regras de coleta de cada etapa: um diário gravado com regras antigas é recusado.
RULES = {"selection": 1, "deployments": 2, "workflow_runs": 1, "variants": 1}


def select_repositories(search, collector, target, checkpoint=None, rows=None):
    """Card 1: avalia candidatos até a meta; devolve o erro global de busca, se houver."""
    rows = [] if rows is None else rows
    selected = 0
    try:
        for candidate in search.candidates():
            unit = str(candidate.get("full_name", "")).casefold()
            row = checkpoint.done(unit) if checkpoint else None
            if row is None:
                row = collector.collect(candidate)
                if checkpoint:
                    checkpoint.record(unit, row, row["error"] is None)
            rows.append(row)
            if row["error"]:
                LOGGER.error("%s: %s", row["full_name"], row["error"])
            if row["included"]:
                selected += 1
                LOGGER.info("Selecionado %d de %d: %s", selected, target, row["full_name"])
            if selected >= target:
                break
    except APIError as exc:
        LOGGER.error("%s", exc)
        return str(exc)
    return None


def read_repository_list(path):
    """Repositórios de um CSV de subamostra: aceita `repository`, `full_name` ou uma coluna só.

    A replicação cruzada precisa rodar sobre uma subamostra dada do dataset publicado, e
    não sobre a busca por estrelas, que muda com o tempo. Cada grupo nomeia essa coluna de
    um jeito, então os nomes mais comuns são aceitos; sem cabeçalho reconhecido, a
    primeira coluna é usada.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise ValueError(f"{path} está vazio.")
    header = [name.strip() for name in rows[0]]
    known = next((header.index(name) for name in ("repository", "full_name", "repo", "nameWithOwner")
                  if name in header), None)
    body = rows[1:] if known is not None or len(header) > 1 else rows
    column = known if known is not None else 0
    names = []
    for row in body:
        name = row[column].strip() if len(row) > column else ""
        if name and name not in names and "/" in name:
            names.append(name)
    if not names:
        raise ValueError(f"{path} não tem nenhum repositório no formato dono/nome.")
    return names


def select_from_list(client, collector, names, checkpoint=None, rows=None):
    """Card 1 sobre uma lista dada: metadados de cada repositório, sem busca por estrelas.

    Os critérios de inclusão continuam valendo e o funil continua reportando quem ficou de
    fora: `--repos` troca a origem dos candidatos, não as regras do estudo.
    """
    rows = [] if rows is None else rows
    for position, name in enumerate(names, start=1):
        unit = str(name).casefold()
        row = checkpoint.done(unit) if checkpoint else None
        if row is None:
            failure = None
            try:
                repo, _ = client.get("/repos/" + name)
            except APIError as exc:
                repo, failure = {}, str(exc)
            repo = dict(repo) if isinstance(repo, dict) else {}
            repo.setdefault("full_name", name)
            row = collector.collect(repo)
            if failure:
                row["error"], row["included"] = failure, False
            if checkpoint:
                checkpoint.record(unit, row, row["error"] is None)
        rows.append(row)
        if row["error"]:
            LOGGER.error("%s: %s", row["full_name"], row["error"])
        LOGGER.info("Lista %d de %d: %s%s", position, len(names), row["full_name"],
                    "" if row["included"] else f" (fora: {row['exclusion_reason'] or row['error']})")
    return None


def compute_dora(window, selected, deployments, workflow_runs, corrective_version=None):
    """Cards 5 e 6: métricas e classificação de cada repositório selecionado."""
    if corrective_version not in (None, HEURISTIC_VERSION):
        raise ValueError(f'Versão de CFR (b) não implementada: {corrective_version}.')
    releases = {repo["full_name"].casefold(): repo for repo in deployments}
    runs = {repo["full_name"].casefold(): repo for repo in workflow_runs}
    rows, metrics, classifications = [], [], []
    for repo in selected:
        deployment = releases.get(repo["full_name"].casefold()) or {}
        workflows = runs.get(repo["full_name"].casefold()) or {}
        measured = repository_metrics(window, deployment.get("releases"), workflows.get("workflows"),
                                      repo["full_name"])
        if corrective_version is not None:
            measured['change_failure_rate_b'] = cfr_entrega(deployment.get('releases'), window.end)
            measured['rework'] = rework_rate(deployment.get('releases'))
        classification = classify_repository(measured)
        # Erro de comparação entre duas releases já é caso especial do Card 6, não coleta incompleta.
        complete = (bool(workflows.get("complete")) and bool(deployment)
                    and not any(error["stage"] == "releases" for error in deployment["errors"]))
        metrics.append(measured)
        classifications.append(classification)
        rows.append(dora_row(repo, measured, classification, complete))
    return rows, metrics, classifications


def run_pipeline(client, window, output, target=100, min_stars=1001, tag_dates=False, checkpoints=None,
                 workers=1, names=None, corrective_version=None, processed=None, project_types=None,
                 variants=False):
    """Executa as etapas em ordem e devolve o resumo gravado em `summary.json`.

    Com `variants`, coleta também as unidades de deploy alternativas da RQ 07
    (release + pré-release e tag) e grava `variantes.csv` e `deploys_variantes.csv`.
    """
    output = Path(output)
    processed = Path(processed) if processed else output / "processed"
    checkpoints = checkpoints or {}
    summary = {"window_start": window.start.isoformat(), "window_end": window.end.isoformat(),
               "target": target, "min_stars": min_stars, "status": "incomplete", "stage": STAGES[0],
               "selection": None, "deployments": None, "workflow_runs": None, "metrics": None,
               "classification": None, "api": {}}
    summary['corrective_heuristic_version'] = corrective_version
    rows, deployments, workflow_runs, alternatives = [], [], [], []
    search = CandidateSearch(client, min_stars)
    error = None
    try:
        collector = MetadataCollector(client, window, workers)
        from_list = names is not None
        try:
            if from_list:
                LOGGER.info("Etapa 1 de 4: %d repositórios informados por --repos.", len(names))
                error = select_from_list(client, collector, names,
                                         checkpoints.get("selection"), rows)
            else:
                LOGGER.info("Etapa 1 de 4: seleção de %d repositórios.", target)
                error = select_repositories(search, collector, target,
                                            checkpoints.get("selection"), rows)
        finally:
            found = len(names) if from_list else search.found
            unique = len(names) if from_list else search.unique
            selected = [row for row in rows if row["included"]]
            # Com `--repos` a meta é ter avaliado a lista inteira: um repositório excluído
            # pelos critérios de inclusão é resultado do estudo, não falha de execução.
            reached = len(rows) >= len(names) if from_list else len(selected) >= target
            summary["selection"] = {**funnel(rows, found, unique), "from_list": from_list,
                                    "target_reached": reached, "search_error": error}
            save_output(output / "selection", rows, summary["selection"])
        if error:
            summary["status"] = "search_error"
            return summary
        if not selected:
            return summary

        summary["stage"] = STAGES[1]
        LOGGER.info("Etapa 2 de 4: releases, tags e commits de %d repositórios.", len(selected))
        try:
            collect_repositories(client, window, [row["full_name"] for row in selected], tag_dates,
                                 checkpoints.get("deployments"), deployments, workers)
        finally:
            summary["deployments"] = {
                "repositories": len(deployments),
                "repositories_with_errors": sum(bool(repo["errors"]) for repo in deployments),
                "valid_releases": sum(repo["summary"]["valid_releases"] for repo in deployments),
                "comparisons_completed": sum(repo["summary"]["comparisons_completed"] for repo in deployments),
                "releases_ignored_comparison_error": sum(
                    repo["summary"]["releases_ignored_comparison_error"] for repo in deployments)}
            save_json(output / "deployments.json", deployments)
        for repo in deployments:
            for item in repo["errors"]:
                LOGGER.error("%s [%s]: %s", repo["full_name"], item["stage"], item["error"])

        summary["stage"] = STAGES[2]
        # As consultas são as mesmas da seleção: o que ela baixou vem do cache.
        LOGGER.info("Etapa 3 de 4: workflow runs de %d repositórios.", len(selected))
        try:
            collect_workflow_repositories(client, window, selected, checkpoints.get("workflow_runs"),
                                          workflow_runs, workers)
        finally:
            summary["workflow_runs"] = {
                "repositories": len(workflow_runs),
                "repositories_with_errors": sum(not repo["complete"] for repo in workflow_runs),
                **{key: sum(repo["summary"][key] for repo in workflow_runs)
                   for key in ("success", "failure", "ignored", "total")}}
            save_json(output / "workflow_runs.json", workflow_runs)
        for repo in workflow_runs:
            for item in repo["errors"]:
                LOGGER.error("%s: %s", repo["full_name"], item["error"])

        if variants:
            summary["stage"] = STAGES[3]
            LOGGER.info("Etapa extra: unidades de deploy alternativas (RQ 07) de %d repositórios.", len(deployments))
            try:
                collect_variants(client, window, deployments, checkpoints.get("variants"), alternatives, workers)
            finally:
                summary["variants"] = variant_summary(alternatives)
                save_json(output / "variants.json", alternatives)
            for repo in alternatives:
                for item in repo["errors"]:
                    LOGGER.error("%s [variantes, %s]: %s", repo["full_name"], item["stage"], item["error"])

        summary["stage"] = "metrics"
        LOGGER.info("Etapa 4 de 4: métricas, classificação DORA e dataset final.")
        table, metrics, classifications = compute_dora(window, selected, deployments, workflow_runs, corrective_version)
        save_dora(output, table, metrics, classifications)
        summary["metrics"] = aggregate_metrics(metrics)
        summary["classification"] = classify_sample(classifications)
        dataset = build_dataset(window, selected, deployments, metrics, classifications, table, project_types)
        summary["dataset"] = {"files": save_dataset(processed, dataset, summary["selection"]),
                              **{name: len(rows) for name, rows in dataset.items()},
                              "censoring": censoring(dataset["repositories"])}
        if variants:
            summary["dataset"]["files"].update(
                save_variants(processed, build_variants(window, selected, deployments, alternatives)))
        summary["collection_checks"] = collection_checks(deployments, workflow_runs)
        summary["incomplete_repositories"] = [row["repository"] for row in table
                                              if not row["collection_complete"]]
        if summary["selection"]["target_reached"] and not summary["incomplete_repositories"]:
            summary["status"] = "complete"
    except KeyboardInterrupt:
        # O que já foi coletado está no cache, nos diários e nos arquivos da etapa.
        summary["status"] = "interrupted"
        LOGGER.error("Execução interrompida em %s; repita o mesmo comando para retomar.", summary["stage"])
    finally:
        for checkpoint in checkpoints.values():
            checkpoint.close()
        summary["api"] = collection_report(client)
        summary["api"]["resumed_units"] = sum(checkpoint.reused for checkpoint in checkpoints.values())
        save_json(output / "summary.json", summary)
    return summary


def set_aside_outdated(path, meta):
    """Diário da mesma coleta gravado com regras antigas: fica guardado e a etapa é refeita.

    As respostas da API continuam no cache, então refazer a etapa custa pouco.
    """
    try:
        with path.open(encoding="utf-8") as file:
            stored = json.loads(file.readline() or "{}").get("meta")
    except (OSError, ValueError, AttributeError):
        return
    if isinstance(stored, dict) and stored != meta and {**stored, "rules": meta["rules"]} == meta:
        path.replace(path.with_name(path.name + ".old"))
        LOGGER.warning("%s foi gravado com regras de coleta anteriores; a etapa será refeita a partir do cache.",
                       path)


def open_checkpoints(args, window):
    """Um diário por etapa, pois as unidades (candidato, repositório) são diferentes."""
    if args.no_resume:
        return {}
    directory = Path(args.state) if args.state else Path(args.output) / "state"
    base = {"window_start": window.start.isoformat(), "window_end": window.end.isoformat()}
    extra = {"selection": {"min_stars": args.min_stars}, "deployments": {"tag_dates": bool(args.tag_dates)},
             "workflow_runs": {}, "variants": {}}
    opened = {}
    try:
        for stage in STAGES:
            if stage == "variants" and not getattr(args, "variants", False):
                continue
            meta = {"stage": stage, **base, **extra[stage]}
            if RULES[stage] > 1:
                meta["rules"] = RULES[stage]
                set_aside_outdated(directory / f"{stage}.jsonl", meta)
            opened[stage] = Checkpoint(directory / f"{stage}.jsonl", meta)
    except (APIError, OSError):
        for checkpoint in opened.values():
            checkpoint.close()
        raise
    return opened


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m dora_selection.pipeline",
        description="Lab03S01 — pipeline completo: seleção, coleta, métricas e classificação DORA")
    parser.add_argument("--start", required=True, help="Início inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--end", required=True, help="Fim inclusivo ISO 8601 com fuso (precisão de segundos)")
    parser.add_argument("--target", type=int, default=100, help="Repositórios a selecionar (padrão 100)")
    parser.add_argument("--repos", type=Path,
                        help="CSV com a lista de repositórios (coluna repository ou full_name); "
                             "substitui a busca por estrelas, para replicar uma subamostra dada")
    parser.add_argument("--min-stars", type=int, default=1001)
    parser.add_argument("--output", default="outputs/pipeline", help="Pasta de saída (padrão outputs/pipeline)")
    parser.add_argument("--tag-dates", action="store_true", help="Consultar também commit.author.date de cada tag")
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1]/'config.yaml',
                        help='Configuração da versão oficial do CFR (b)')
    parser.add_argument("--processed", help="Pasta do dataset final em CSV (padrão <output>/processed)")
    parser.add_argument("--project-types", type=Path,
                        help="CSV repository,project_type do consenso da amostra-ouro (fator da RQ 06)")
    parser.add_argument("--variants", action="store_true",
                        help="Coletar também as unidades de deploy da RQ 07 (release + pré-release e tag)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Consultas simultâneas dentro de cada repositório (padrão 4; 1 desliga)")
    add_resilience_arguments(parser)
    args = parser.parse_args(argv)
    if args.target < 1 or args.min_stars < 1 or not 1 <= args.workers <= 16:
        parser.error("--target e --min-stars devem ser >= 1 e --workers deve ficar entre 1 e 16")
    configure_logging(args.log_file or Path(args.output) / "collection.log")
    try:
        window = Window(timestamp(args.start), timestamp(args.end))
        if window.start.microsecond or window.end.microsecond:
            raise ValueError("Use precisão de segundos, sem frações.")
        corrective_version = official_version(args.config)
        if corrective_version is None:
            LOGGER.info('CFR (b) pendente: nenhuma versão oficial validada em config.yaml.')
        project_types = load_project_types(args.project_types) if args.project_types else None
        client = GitHubClient(**client_options(args))
        checkpoints = open_checkpoints(args, window)
    except (APIError, ValueError, OSError, ImportError) as exc:
        parser.error(str(exc))
    try:
        names = read_repository_list(args.repos) if args.repos else None
        summary = run_pipeline(client, window, args.output,
                               len(names) if names else args.target, args.min_stars,
                               args.tag_dates, checkpoints, args.workers, names=names,
                               corrective_version=corrective_version, processed=args.processed,
                               project_types=project_types, variants=args.variants)
    except OSError as exc:
        LOGGER.error("Erro de persistência: %s", exc)
        return 1
    selection = summary["selection"] or {}
    print(json.dumps({"status": summary["status"], "stage": summary["stage"],
                      "selected": selection.get("included"), "target": summary["target"],
                      "classification": (summary["classification"] or {}).get("by_overall"),
                      "dataset": (summary.get("dataset") or {}).get("files"),
                      "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
