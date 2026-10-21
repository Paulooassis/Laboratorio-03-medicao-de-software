"""S3 (#41): unidades de deploy da RQ 07 (release + pré-release e tag) e o cliente GraphQL."""
import csv
import json
import logging
import pytest
import yaml
import pipeline
from pathlib import Path
from urllib.parse import urlsplit
from dora_selection.api import APIError, GitHubClient
from dora_selection.resilience import ResponseCache, configure_logging
from dora_selection.selection import Window, timestamp
from dora_selection.variants import (DEPLOY_FIELDS, VARIANT_FIELDS, build_variants, collect_tag_dates,
                                     collect_variant, collect_variants, compare_deploys,
                                     release_prerelease_deploys, save_variants, tag_commit, tag_deploys,
                                     variant_summary)
from test_card8 import FakeGitHub, Response, TOKEN


WINDOW = Window(timestamp("2026-01-01T00:00:00Z"), timestamp("2026-01-31T23:59:59Z"))


def commit(oid, date, committed=None):
    return {"__typename": "Commit", "oid": oid, "authoredDate": date, "committedDate": committed or date}


def node(name, target):
    return {"name": name, "target": target}


def page(nodes, cursor=None):
    refs = {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}
    return {"data": {"repository": {"refs": refs}}}


class StubClient:
    """Cliente mínimo: respostas GraphQL em fila e `compare` por par de SHAs."""

    def __init__(self, pages=(), compares=None):
        self.pages_left = list(pages)
        self.compares = compares or {}
        self.graphql_calls = []
        self.compare_calls = []

    def graphql(self, query, variables=None):
        self.graphql_calls.append(variables)
        return self.pages_left.pop(0)

    def pages(self, path, params=None, key=None):
        self.compare_calls.append(path)
        outcome = self.compares.get(path.rsplit("/compare/", 1)[1], [])
        if isinstance(outcome, Exception):
            raise outcome
        return iter(outcome)


def compared(sha, day):
    return {"sha": sha, "commit": {"author": {"date": f"2026-01-{day:02d}T00:00:00Z"},
                                   "message": f"{sha}\n\ndetalhes"}}


# ---- tags e suas datas --------------------------------------------------------------------------

def test_tag_commit_follows_annotated_tags_up_to_two_levels():
    direct = commit("a", "2026-01-02T00:00:00Z")
    annotated = {"__typename": "Tag", "target": direct}
    double = {"__typename": "Tag", "target": annotated}
    triple = {"__typename": "Tag", "target": double}
    assert tag_commit(direct) is direct
    assert tag_commit(annotated) is direct
    assert tag_commit(double) is direct
    assert tag_commit(triple) is None
    assert tag_commit({"__typename": "Tree"}) is None
    assert tag_commit(None) is None


def test_tag_dates_stop_at_the_first_page_older_than_the_window():
    client = StubClient([
        page([node("v3", commit("c3", "2026-01-20T00:00:00Z")), node("v2", commit("c2", "2026-01-10T00:00:00Z"))],
             "cursor-1"),
        page([node("v1", commit("c1", "2025-12-20T00:00:00Z")), node("v0", commit("c0", "2025-11-01T00:00:00Z"))],
             "cursor-2"),
        page([node("never", commit("cx", "2020-01-01T00:00:00Z"))])])
    result = collect_tag_dates(client, "owner/repo", WINDOW)
    assert [tag["name"] for tag in result["tags"]] == ["v3", "v2", "v1", "v0"]
    assert result["pages"] == 2
    assert client.graphql_calls == [{"owner": "owner", "name": "repo", "cursor": None},
                                    {"owner": "owner", "name": "repo", "cursor": "cursor-1"}]


def test_tag_dates_read_every_page_when_all_tags_are_inside_the_window():
    client = StubClient([page([node("v2", commit("c2", "2026-01-20T00:00:00Z"))], "next"),
                         page([node("v1", commit("c1", "2026-01-10T00:00:00Z"))])])
    result = collect_tag_dates(client, "owner/repo", WINDOW)
    assert (result["pages"], len(result["tags"])) == (2, 2)


def test_tags_that_do_not_point_to_a_commit_are_counted_not_dropped_silently():
    client = StubClient([page([node("tree", {"__typename": "Tree"}), node("none", None),
                               node("ok", commit("c", "2026-01-10T00:00:00Z"))])])
    result = collect_tag_dates(client, "owner/repo", WINDOW)
    assert (len(result["tags"]), result["without_commit"]) == (1, 2)


@pytest.mark.parametrize("response", [{"data": {"repository": None}}, {"data": None}, {}])
def test_graphql_response_without_refs_is_an_error(response):
    with pytest.raises(ValueError):
        collect_tag_dates(StubClient([response]), "owner/repo", WINDOW)


def tag(name, sha, date):
    return {"name": name, "commit_sha": sha, "author_date": date}


def test_tags_on_the_same_commit_are_one_deploy():
    tags = [tag("pkg-b@1.0", "s1", "2026-01-10T00:00:00Z"), tag("pkg-a@1.0", "s1", "2026-01-10T00:00:00Z"),
            tag("v2", "s2", "2026-01-20T00:00:00Z")]
    deploys, previous = tag_deploys("owner/repo", tags, WINDOW)
    assert [(deploy["tag_name"], deploy["tags"]) for deploy in deploys] == [("pkg-a@1.0", 2), ("v2", 1)]
    assert previous is None


def test_tag_deploys_keep_only_the_window_and_use_the_latest_tag_before_it_as_base():
    tags = [tag("old", "s0", "2025-10-01T00:00:00Z"), tag("recent", "s1", "2025-12-30T00:00:00Z"),
            tag("in", "s2", "2026-01-31T23:59:59Z"), tag("after", "s3", "2026-02-01T00:00:00Z"),
            tag("undated", "s4", None)]
    deploys, previous = tag_deploys("owner/repo", tags, WINDOW)
    assert [deploy["tag_name"] for deploy in deploys] == ["in"]
    assert previous == {"tag_name": "recent", "commit_sha": "s1"}


# ---- release + pré-release ----------------------------------------------------------------------

def release(number, day, prerelease=False, **changes):
    return {"repository": "owner/repo", "release_id": number, "tag_name": f"v{number}",
            "published_at": f"2026-01-{day:02d}T12:00:00Z", "prerelease": prerelease,
            "commit_sha": f"sha{number}", "previous_tag_name": None, **changes}


def deployment():
    return {"full_name": "owner/repo",
            "releases": [release(1, 5, previous_tag_name="v0"), release(3, 20, previous_tag_name="v1")],
            "prereleases": [release(2, 12, True)],
            "tags": [{"name": "v0", "commit_sha": "sha0"}]}


def test_release_and_prerelease_form_one_chronological_sequence():
    deploys, previous = release_prerelease_deploys(deployment())
    assert [(deploy["tag_name"], deploy["prerelease"]) for deploy in deploys] == [
        ("v1", False), ("v2", True), ("v3", False)]
    assert previous == {"tag_name": "v0", "commit_sha": "sha0"}
    assert all(deploy["commits"] == [] and deploy["comparison_status"] == "pending" for deploy in deploys)


def test_sequence_without_a_release_before_the_window_has_no_base():
    data = deployment()
    data["releases"][0]["previous_tag_name"] = None
    assert release_prerelease_deploys(data)[1] is None
    assert release_prerelease_deploys({"releases": [], "prereleases": []}) == ([], None)


def test_each_deploy_is_compared_with_the_previous_one_of_the_combined_sequence():
    deploys, previous = release_prerelease_deploys(deployment())
    client = StubClient(compares={"sha0...sha1": [compared("a", 4)], "sha1...sha2": [compared("b", 11)],
                                  "sha2...sha3": [compared("c", 19), compared("d", 18)]})
    from dora_selection.deployments import DeploymentCollector
    errors = compare_deploys(DeploymentCollector(client, WINDOW), "owner/repo", deploys, previous)
    assert errors == []
    assert [deploy["previous_tag_name"] for deploy in deploys] == ["v0", "v1", "v2"]
    assert [len(deploy["commits"]) for deploy in deploys] == [1, 1, 2]
    # Só SHA, data e primeira linha da mensagem ficam guardados.
    assert deploys[0]["commits"] == [{"sha": "a", "author_date": "2026-01-04T00:00:00Z", "message": "a"}]


def test_first_deploy_without_base_and_failed_comparisons_are_recorded():
    deploys, _ = release_prerelease_deploys(deployment())
    client = StubClient(compares={"sha1...sha2": APIError("HTTP 404 em /compare", status_code=404),
                                  "sha2...sha3": APIError("HTTP 500", status_code=500)})
    from dora_selection.deployments import DeploymentCollector
    errors = compare_deploys(DeploymentCollector(client, WINDOW), "owner/repo", deploys, None)
    assert [deploy["comparison_status"] for deploy in deploys] == ["no_previous_release", "not_found", "error"]
    assert [error["stage"] for error in errors] == ["compare", "compare"]
    # O próximo par continua sendo de deploys consecutivos, mesmo depois do erro.
    assert deploys[2]["previous_tag_name"] == "v2"


def test_identical_commits_cost_no_compare_request():
    deploys = [{"tag_name": "a", "commit_sha": "same", "published_at": "2026-01-02T00:00:00Z", "commits": [],
                "comparison_status": "pending"},
               {"tag_name": "b", "commit_sha": "same", "published_at": "2026-01-03T00:00:00Z", "commits": [],
                "comparison_status": "pending"}]
    client = StubClient()
    from dora_selection.deployments import DeploymentCollector
    compare_deploys(DeploymentCollector(client, WINDOW), "owner/repo", deploys, {"tag_name": "z", "commit_sha": "same"})
    assert client.compare_calls == []
    assert [deploy["comparison_status"] for deploy in deploys] == ["completed", "completed"]


# ---- coleta e tabelas ---------------------------------------------------------------------------

def variant_client():
    return StubClient(
        pages=[page([node("v2", commit("sha2", "2026-01-20T00:00:00Z")),
                     node("v1", commit("sha1", "2026-01-05T00:00:00Z")),
                     node("v0", commit("sha0", "2025-12-01T00:00:00Z"))])],
        compares={"sha0...sha1": [compared("a", 4)], "sha1...sha2": [compared("b", 19)],
                  "sha2...sha3": [compared("c", 19)]})


def test_collect_variant_returns_both_alternative_units():
    result = collect_variant(variant_client(), WINDOW, deployment())
    assert result["errors"] == []
    assert [deploy["tag_name"] for deploy in result["units"]["release_prerelease"]] == ["v1", "v2", "v3"]
    assert [deploy["tag_name"] for deploy in result["units"]["tag"]] == ["v1", "v2"]
    assert result["summary"] == {"tag_pages": 1, "tags_read": 3, "tags_without_commit": 0}


def test_tag_collection_failure_does_not_lose_the_other_unit():
    client = StubClient(pages=[{"data": None}], compares={"sha0...sha1": [compared("a", 4)]})
    result = collect_variant(client, WINDOW, deployment())
    assert result["units"]["tag"] is None
    assert [error["stage"] for error in result["errors"]] == ["tag_dates"]
    assert len(result["units"]["release_prerelease"]) == 3


class Journal:
    """Diário de retomada em memória."""

    def __init__(self):
        self.entries, self.recorded = {}, []

    def done(self, unit):
        return self.entries.get(unit)

    def record(self, unit, result, complete=True):
        self.recorded.append((unit, complete))
        if complete:
            self.entries[unit] = result


def test_resume_does_not_collect_a_finished_repository_again():
    journal, client = Journal(), variant_client()
    collect_variants(client, WINDOW, [deployment()], journal)
    calls = len(client.graphql_calls) + len(client.compare_calls)
    again = collect_variants(client, WINDOW, [deployment()], journal)
    assert len(client.graphql_calls) + len(client.compare_calls) == calls
    assert len(again) == 1


def test_repository_with_errors_is_not_marked_as_done():
    journal = Journal()
    collect_variants(StubClient(pages=[{"data": None}], compares={}), WINDOW, [deployment()], journal)
    assert journal.recorded == [("owner/repo", False)]


@pytest.fixture
def tables():
    selected = [{"full_name": "owner/repo"}]
    data = deployment()
    variants = [collect_variant(variant_client(), WINDOW, data)]
    return build_variants(WINDOW, selected, [data], variants), variants


def test_variant_table_has_one_row_per_repository_and_unit(tables):
    rows = tables[0]["variants"]
    assert [row["unit"] for row in rows] == ["release", "release_prerelease", "tag"]
    assert all(list(row) == VARIANT_FIELDS for row in rows)
    release_row, combined, by_tag = rows
    assert (release_row["deploys"], combined["deploys"], by_tag["deploys"]) == (2, 3, 2)
    assert all(row["collection_complete"] for row in rows)
    # Janela de 31 dias: 3 deploys em 31/7 semanas.
    assert combined["deployment_frequency_per_week"] == pytest.approx(3 / (31 * 86400 / 604800))


def test_deploy_table_has_one_row_per_deploy_and_the_lead_time_of_each(tables):
    rows = tables[0]["deploys"]
    assert all(list(row) == DEPLOY_FIELDS for row in rows)
    assert [(row["unit"], row["tag_name"]) for row in rows] == [
        ("release", "v1"), ("release", "v3"), ("release_prerelease", "v1"), ("release_prerelease", "v2"),
        ("release_prerelease", "v3"), ("tag", "v1"), ("tag", "v2")]
    by_tag = {(row["unit"], row["tag_name"]): row for row in rows}
    # v1 publicada às 12h do dia 5 com commit às 0h do dia 4: 36 horas.
    assert by_tag[("release_prerelease", "v1")]["lead_time_a_hours"] == 36.0
    # Na unidade tag, o deploy tem a data do commit (0h do dia 5): 24 horas.
    assert by_tag[("tag", "v1")]["lead_time_a_hours"] == 24.0


def test_failed_unit_is_incomplete_and_not_confused_with_no_deploys():
    selected, data = [{"full_name": "owner/repo"}], deployment()
    broken = collect_variant(StubClient(pages=[{"data": None}], compares={"sha0...sha1": [compared("a", 4)]}),
                             WINDOW, data)
    rows = build_variants(WINDOW, selected, [data], [broken])["variants"]
    # A falha das datas das tags invalida só a unidade tag; as outras têm dados completos.
    assert [(row["unit"], row["collection_complete"]) for row in rows] == [
        ("release", True), ("release_prerelease", True), ("tag", False)]
    assert rows[2]["deploys"] == 0 and rows[2]["lead_time_a_hours"] is None


def test_compare_404_does_not_make_a_unit_incomplete():
    selected, data = [{"full_name": "owner/repo"}], deployment()
    client = variant_client()
    client.compares["sha1...sha2"] = APIError("HTTP 404 em /compare", status_code=404)
    variant = collect_variant(client, WINDOW, data)
    rows = build_variants(WINDOW, selected, [data], [variant])["variants"]
    # A comparação perdida fica contada, e a unidade continua completa.
    assert [row["collection_complete"] for row in rows] == [True, True, True]
    assert rows[2]["compare_not_found"] == 1 and rows[1]["compare_not_found"] >= 1


def test_release_listing_error_makes_the_release_units_incomplete_not_empty():
    data = {**deployment(), "releases": [], "prereleases": [],
            "errors": [{"stage": "releases", "error": "HTTP 500"}]}
    variant = collect_variant(variant_client(), WINDOW, data)
    rows = build_variants(WINDOW, [{"full_name": "owner/repo"}], [data], [variant])["variants"]
    assert [row["collection_complete"] for row in rows] == [False, False, True]


def test_repository_missing_from_the_variant_collection_is_incomplete():
    rows = build_variants(WINDOW, [{"full_name": "owner/repo"}], [deployment()], [])["variants"]
    assert [row["collection_complete"] for row in rows] == [True, False, False]


def test_repository_with_a_single_release_has_no_lead_time_but_one_evaluated_release():
    data = {"full_name": "owner/repo", "releases": [release(1, 5)], "prereleases": [], "tags": []}
    variant = collect_variant(StubClient(pages=[page([])]), WINDOW, data)
    rows = build_variants(WINDOW, [{"full_name": "owner/repo"}], [data], [variant])["variants"]
    combined = rows[1]
    assert (combined["deploys"], combined["deploys_no_previous"]) == (1, 1)
    # Sem release anterior não há Lead Time; a release única, fora dos últimos 7 dias, é avaliada.
    assert combined["lead_time_a_hours"] is None and combined["lead_time_b_hours"] is None
    assert (combined["cfr_b_evaluated"], combined["cfr_b"]) == (1, 0.0)


def test_summary_reports_cost_and_collapsed_tags(tables):
    summary = variant_summary(tables[1])
    assert summary["graphql_pages"] == 1 and summary["tags_read"] == 3
    assert (summary["release_prerelease_deploys"], summary["tag_deploys"]) == (3, 2)
    assert summary["tag_dates_failed"] == 0 and summary["tag_share_collapsed"] == 0


def test_csv_files_are_written(tmp_path, tables):
    files = save_variants(tmp_path / "out", tables[0])
    with open(files["variants"], encoding="utf-8", newline="") as file:
        assert len(list(csv.DictReader(file))) == 3
    assert Path(files["deploys"]).name == "deploys_variantes.csv"


# ---- cliente GraphQL ----------------------------------------------------------------------------

class GraphQLResponse(Response):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}


@pytest.fixture
def client_factory(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    sent, waits = [], []

    def make(*responses, **options):
        queue = list(responses)

        def fake(request, timeout=None):
            sent.append(request)
            return queue.pop(0)
        monkeypatch.setattr("dora_selection.api.urlopen", fake)
        return GitHubClient(sleep=waits.append, now=lambda: 1000.0, **options)
    return make, sent, waits


def test_graphql_posts_the_query_and_the_token(client_factory):
    make, sent, _ = client_factory
    data = make(GraphQLResponse({"data": {"ok": 1}})).graphql("query { a }", {"x": 1})
    assert data == {"data": {"ok": 1}}
    request = sent[0]
    assert (request.get_method(), request.full_url) == ("POST", "https://api.github.com/graphql")
    assert request.get_header("Authorization") == "Bearer " + TOKEN
    assert json.loads(request.data) == {"query": "query { a }", "variables": {"x": 1}}


def test_graphql_answers_are_cached_by_query_and_variables(client_factory, tmp_path):
    make, sent, _ = client_factory
    client = make(GraphQLResponse({"data": 1}), GraphQLResponse({"data": 2}), cache=ResponseCache(tmp_path))
    assert client.graphql("q", {"a": 1}) == client.graphql("q", {"a": 1}) == {"data": 1}
    assert client.graphql("q", {"a": 2}) == {"data": 2}
    assert len(sent) == 2 and client.stats["cache_hits"] == 1


def test_graphql_errors_raise_and_are_not_cached(client_factory, tmp_path):
    make, sent, _ = client_factory
    failure = {"errors": [{"type": "NOT_FOUND", "message": "Could not resolve"}]}
    client = make(GraphQLResponse(failure), GraphQLResponse({"data": 1}), cache=ResponseCache(tmp_path))
    with pytest.raises(APIError, match="Could not resolve"):
        client.graphql("q")
    assert client.graphql("q") == {"data": 1}
    assert len(sent) == 2


def test_graphql_waits_for_the_reset_when_rate_limited(client_factory):
    make, _, waits = client_factory
    limited = {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
    client = make(GraphQLResponse(limited, {"X-RateLimit-Reset": "1030"}), GraphQLResponse({"data": 1}))
    assert client.graphql("q") == {"data": 1}
    assert waits == [31.0]
    assert client.stats["rate_limit_waits"] == 1


def test_graphql_gives_up_when_the_reset_is_too_far(client_factory):
    make, _, _ = client_factory
    limited = {"errors": [{"type": "RATE_LIMITED", "message": "limit"}]}
    client = make(GraphQLResponse(limited, {"X-RateLimit-Reset": "9999"}), max_wait=60)
    with pytest.raises(APIError, match="excede"):
        client.graphql("q")


def test_graphql_and_rest_quotas_are_tracked_separately(client_factory):
    make, _, waits = client_factory
    client = make(GraphQLResponse({"data": 1}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1100"}),
                  GraphQLResponse([], {"X-RateLimit-Remaining": "4000", "X-RateLimit-Reset": "5000"}))
    client.graphql("q")
    assert (client.stats["graphql_remaining"], client.stats["graphql_reset"]) == (0, 1100)
    # A cota GraphQL zerada não atrasa uma chamada REST.
    client.get("/repos/o/r/tags")
    assert waits == []
    assert client.stats["rate_limit_remaining"] == 4000
    assert (client.stats["requests"], client.stats["graphql_requests"]) == (1, 1)


# ---- pipeline e configuração ---------------------------------------------------------------------

DAYS = (2, 9, 16, 23, 30)


class FakeWithGraphQL(FakeGitHub):
    """Acrescenta as tags com data à API simulada: o commit shaN foi escrito às 0h do dia N."""

    def __call__(self, request, timeout=None):
        if urlsplit(request.full_url).path != "/graphql":
            return super().__call__(request, timeout)
        self.requests.append("/graphql")
        variables = json.loads(request.data)["variables"]
        repository = f"{variables['owner']}/{variables['name']}"
        dates = {"v0": "2025-12-20T00:00:00Z", **{f"v{day}": f"2026-01-{day:02d}T00:00:00Z" for day in DAYS}}
        nodes = ([node(name, commit("sha" + name[1:], date)) for name, date in reversed(dates.items())]
                 if repository in self.eligible else [])
        return Response(page(nodes))


@pytest.fixture
def configured(tmp_path, monkeypatch, capsys):
    fake = FakeWithGraphQL()
    monkeypatch.setenv("GITHUB_TOKEN", TOKEN)
    monkeypatch.setattr("dora_selection.api.urlopen", fake)
    official = yaml.safe_load((Path(__file__).resolve().parents[1] / "config.yaml").read_text())
    config = {"coleta": {"inicio": "2026-01-01T00:00:00Z", "fim": "2026-01-31T23:59:59Z", "alvo": 2,
                         "min_estrelas": 1001, "saida": str(tmp_path / "out"),
                         "processados": str(tmp_path / "data"), "workers": 1, "variantes": True},
              "heuristica_corretiva": official["heuristica_corretiva"]}

    def run(**changes):
        config["coleta"].update(changes)
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        code = pipeline.main(["--config", str(path)])
        capsys.readouterr()
        return code
    yield run, fake
    configure_logging(None, logging.CRITICAL)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_pipeline_writes_the_variant_tables_for_every_unit(configured, tmp_path):
    run, _ = configured
    assert run() == 0
    rows = read_csv(tmp_path / "data" / "variantes.csv")
    assert [(row["repository"], row["unit"]) for row in rows] == [
        (name, unit) for name in ("owner/one", "owner/two") for unit in ("release", "release_prerelease", "tag")]
    by_unit = {row["unit"]: row for row in rows[:3]}
    # Sem pré-releases, release + pré-release coincide com a definição principal (12 h).
    assert by_unit["release"]["lead_time_a_hours"] == by_unit["release_prerelease"]["lead_time_a_hours"] == "12.0"
    # Na unidade tag o deploy tem a data do commit, escrito no mesmo instante: lead time 0.
    assert (by_unit["tag"]["deploys"], by_unit["tag"]["lead_time_a_hours"]) == ("5", "0.0")
    assert all(row["collection_complete"] == "True" for row in rows)
    assert len(read_csv(tmp_path / "data" / "deploys_variantes.csv")) == 30
    summary = json.loads((tmp_path / "out" / "summary.json").read_text(encoding="utf-8"))
    assert summary["variants"]["tag_deploys"] == 10 and summary["variants"]["tag_dates_failed"] == 0
    assert summary["dataset"]["files"]["variants"].endswith("variantes.csv")


def test_variants_are_off_by_default(configured, tmp_path):
    run, fake = configured
    assert run(variantes=False) == 0
    assert not (tmp_path / "data" / "variantes.csv").exists()
    assert "/graphql" not in fake.requests


def test_second_run_rebuilds_the_variants_without_requests(configured, tmp_path):
    run, fake = configured
    assert run() == 0
    made, expected = len(fake.requests), (tmp_path / "data" / "variantes.csv").read_bytes()
    (tmp_path / "data" / "variantes.csv").unlink()
    assert run() == 0
    assert len(fake.requests) == made
    assert (tmp_path / "data" / "variantes.csv").read_bytes() == expected


def test_config_flag_must_be_boolean(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("coleta:\n  variantes: sim\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        pipeline.main(["--config", str(path)])
