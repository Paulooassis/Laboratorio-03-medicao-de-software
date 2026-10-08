"""Fixtures reutilizáveis: amostras pequenas com resultados conhecidos de antemão.

A amostra de referência (`releases` + `workflows`) foi montada para que cada métrica
tenha um valor calculável à mão:

- Deployment Frequency: 4 releases em 4 semanas ISO completas = 1,0 por semana;
- Lead Time por commit: 24 h, 6 h e 48 h, mediana 24 h;
- Lead Time por release: 24 h e 48 h, mediana 36 h;
- Change Failure Rate: 4 falhas em 8 runs considerados = 0,5 (2 ignorados);
- Tempo de recuperação: episódios de 6 h e 2 h, mediana 4 h, e 1 falha não recuperada.
"""
import pytest
from dora_selection.metrics import repository_metrics
from dora_selection.selection import Window, timestamp


REPOSITORY = "owner/repo"


@pytest.fixture
def window():
    """Quatro semanas ISO completas: 2026-W02 a 2026-W05."""
    return Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))


@pytest.fixture
def make_commit():
    def commit(sha, author_date):
        return {"repository": REPOSITORY, "sha": sha, "author_date": author_date, "message": sha}
    return commit


@pytest.fixture
def make_release():
    """Release no formato do Card 2; `comparison_status` padrão é `completed`."""
    def release(number, published_at, commits=(), **changes):
        return {"repository": REPOSITORY, "release_id": number, "tag_name": f"v{number}",
                "published_at": published_at, "comparison_status": "completed",
                "commits": list(commits), **changes}
    return release


@pytest.fixture
def make_run():
    """Run no formato do Card 3, já classificado."""
    def run(number, classification="success", created_at="2026-01-05T00:00:00Z", updated_at=None,
            **changes):
        return {"repository": REPOSITORY, "workflow_id": 7, "id": number,
                "classification": classification, "created_at": created_at,
                "updated_at": updated_at or created_at, **changes}
    return run


@pytest.fixture
def make_raw_run():
    """Run como vem da API, sem o campo `classification` do Card 3."""
    def run(number, conclusion="success", status="completed", created_at="2026-01-05T00:00:00Z"):
        return {"repository": REPOSITORY, "workflow_id": 7, "id": number, "status": status,
                "conclusion": conclusion, "created_at": created_at, "updated_at": created_at}
    return run


@pytest.fixture
def releases(make_release, make_commit):
    """Uma release por semana: a primeira sem anterior e a última sem commits novos."""
    return [
        make_release(1, "2026-01-06T12:00:00Z", comparison_status="no_previous_release"),
        make_release(2, "2026-01-13T12:00:00Z", [make_commit("a", "2026-01-12T12:00:00Z"),
                                                 make_commit("b", "2026-01-13T06:00:00Z")],
                     previous_tag_name="v1"),
        make_release(3, "2026-01-20T12:00:00Z", [make_commit("c", "2026-01-18T12:00:00Z")],
                     previous_tag_name="v2"),
        make_release(4, "2026-01-27T12:00:00Z", previous_tag_name="v3"),
    ]


@pytest.fixture
def ci_runs(make_run):
    """Workflow com dois episódios recuperados (6 h e 2 h) e dois runs ignorados."""
    return [
        make_run(1, "success", "2026-01-05T10:00:00Z"),
        make_run(2, "failure", "2026-01-06T10:00:00Z"),
        make_run(3, "failure", "2026-01-06T12:00:00Z"),
        make_run(4, "ignored", "2026-01-06T13:00:00Z", conclusion="cancelled"),
        make_run(5, "success", "2026-01-06T15:00:00Z", "2026-01-06T16:00:00Z"),
        make_run(6, "failure", "2026-01-10T00:00:00Z"),
        make_run(7, "success", "2026-01-10T01:30:00Z", "2026-01-10T02:00:00Z"),
        make_run(8, "ignored", "2026-01-11T00:00:00Z", conclusion="skipped"),
    ]


@pytest.fixture
def deploy_runs(make_run):
    """Workflow cuja última falha nunca é recuperada dentro da janela."""
    return [
        make_run(9, "success", "2026-01-29T00:00:00Z", workflow_id=8),
        make_run(10, "failure", "2026-01-30T00:00:00Z", "2026-01-30T00:10:00Z", workflow_id=8),
    ]


@pytest.fixture
def workflows(ci_runs, deploy_runs):
    return [
        {"repository": REPOSITORY, "workflow_id": 7, "name": "CI", "runs": ci_runs},
        {"repository": REPOSITORY, "workflow_id": 8, "name": "Deploy", "runs": deploy_runs},
    ]


@pytest.fixture
def metrics(window, releases, workflows):
    """As cinco métricas da amostra de referência."""
    return repository_metrics(window, releases, workflows, REPOSITORY)
