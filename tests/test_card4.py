"""Card 4: cache, retomada, rate limit, retry com backoff e log de erros."""
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from dora_selection.api import APIError, GitHubClient
from dora_selection.deployments import collect_repositories
from dora_selection.__main__ import main
from dora_selection.resilience import (Checkpoint, ResponseCache, collection_report,
                                       configure_logging)
from dora_selection.selection import Window, collect_workflow_repositories, timestamp


TOKEN = {"GITHUB_TOKEN": "fixture-only"}
WINDOW = Window(timestamp("2026-01-01T00:00:00Z"), timestamp("2026-01-31T23:59:59Z"))
NEXT_LINK = '<https://api.github.com/repos/o/r/releases?page=2>; rel="next"'


class Response:
    """Resposta mínima no formato que o cliente consome de urlopen."""

    def __init__(self, body=None, headers=None):
        self.body = b"" if body is None else json.dumps(body).encode("utf-8")
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self):
        return self.body


def build(cache=None, **options):
    options.setdefault("sleep", Mock())
    options.setdefault("now", lambda: 1000.0)
    return GitHubClient(cache=cache, **options)


def run(identifier, **changes):
    return {"id": identifier, "workflow_id": 7, "name": "CI", "status": "completed",
            "conclusion": "success", "created_at": "2026-01-10T00:00:00Z",
            "run_started_at": None, "updated_at": None, "head_branch": "main",
            "event": "push", **changes}


@patch.dict(os.environ, TOKEN)
class CacheTests(unittest.TestCase):
    def test_cache_answers_repeated_and_later_executions(self):
        with tempfile.TemporaryDirectory() as directory:
            client = build(ResponseCache(directory))
            with patch("dora_selection.api.urlopen",
                       return_value=Response([{"id": 1}], {"Link": NEXT_LINK})) as opener:
                first = client.get("/repos/o/r/releases")
                second = client.get("/repos/o/r/releases")
            self.assertEqual(opener.call_count, 1)
            self.assertEqual(first, second)
            self.assertEqual(first[1]["Link"], NEXT_LINK)
            self.assertEqual((client.stats["requests"], client.stats["cache_hits"]), (1, 1))
            # Outra execução reaproveita o mesmo diretório e não chama a API.
            resumed = build(ResponseCache(directory))
            with patch("dora_selection.api.urlopen", side_effect=AssertionError("não deve chamar")):
                self.assertEqual(resumed.get("/repos/o/r/releases"), first)

    def test_key_ignores_parameter_order(self):
        with tempfile.TemporaryDirectory() as directory:
            client = build(ResponseCache(directory))
            with patch("dora_selection.api.urlopen", return_value=Response({"total_count": 1})) as opener:
                client.get("/repos/o/r/actions/runs", {"branch": "main", "event": "push"})
                client.get("/repos/o/r/actions/runs", {"event": "push", "branch": "main"})
            self.assertEqual(opener.call_count, 1)

    def test_only_link_is_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ResponseCache(directory)
            cache.set("https://api.github.com/x", [], {"Link": NEXT_LINK,
                      "X-RateLimit-Remaining": "0", "Date": "ontem"})
            self.assertEqual(cache.get("https://api.github.com/x")[1], {"Link": NEXT_LINK})
            self.assertEqual((cache.hits, cache.writes), (1, 1))

    def test_expired_and_corrupt_entries_are_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ResponseCache(directory, ttl=10)
            cache.set("https://api.github.com/x", {"ok": True}, {})
            self.assertIsNotNone(cache.get("https://api.github.com/x"))
            with patch("dora_selection.resilience.time.time", return_value=9e9):
                self.assertIsNone(cache.get("https://api.github.com/x"))
            entry = next(Path(directory).glob("*/*.json"))
            entry.write_text("{trunca", encoding="utf-8")
            self.assertIsNone(cache.get("https://api.github.com/x"))
            self.assertEqual(cache.misses, 2)

    def test_pagination_uses_cached_link(self):
        pages = [Response({"items": [1]}, {"Link": '<https://api.github.com/p2>; rel="next"'}),
                 Response({"items": [2]}, {})]
        with tempfile.TemporaryDirectory() as directory:
            client = build(ResponseCache(directory))
            with patch("dora_selection.api.urlopen", side_effect=pages):
                self.assertEqual(list(client.pages("/test", key="items")), [1, 2])
            again = build(ResponseCache(directory))
            with patch("dora_selection.api.urlopen", side_effect=AssertionError("não deve chamar")):
                self.assertEqual(list(again.pages("/test", key="items")), [1, 2])


@patch.dict(os.environ, TOKEN)
class RateLimitTests(unittest.TestCase):
    def test_reads_headers_and_waits_for_reset(self):
        sleep = Mock()
        client = build(sleep=sleep)
        responses = [Response({}, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1060"}),
                     Response({"ok": 1}, {"X-RateLimit-Remaining": "4999", "X-RateLimit-Reset": "4600"})]
        with patch("dora_selection.api.urlopen", side_effect=responses):
            client.get("/a")
            self.assertEqual(client.stats["rate_limit_remaining"], 0)
            self.assertEqual(client.stats["rate_limit_reset"], 1060)
            client.get("/b")
        sleep.assert_called_once_with(61.0)
        self.assertEqual(client.stats["rate_limit_waits"], 1)
        self.assertEqual(client.stats["rate_limit_remaining"], 4999)

    def test_reserve_and_past_reset(self):
        sleep = Mock()
        client = build(sleep=sleep, reserve=10)
        with patch("dora_selection.api.urlopen", side_effect=[
                Response({}, {"X-RateLimit-Remaining": "10", "X-RateLimit-Reset": "1030"}),
                Response({}, {"X-RateLimit-Remaining": "10", "X-RateLimit-Reset": "900"}),
                Response({})]):
            client.get("/a")
            client.get("/b")
            client.get("/c")
        sleep.assert_called_once_with(31.0)

    def test_quota_error_waits_once_and_repeats(self):
        sleep = Mock()
        client = build(sleep=sleep)
        exhausted = HTTPError("u", 403, "rate limit", {"X-RateLimit-Remaining": "0",
                                                       "X-RateLimit-Reset": "1030"}, None)
        with patch("dora_selection.api.urlopen", side_effect=[exhausted, Response({"ok": 1})]):
            self.assertEqual(client.get("/a")[0], {"ok": 1})
        sleep.assert_called_once_with(31.0)
        self.assertEqual(client.stats["rate_limit_waits"], 1)

    def test_retry_after_on_secondary_limit(self):
        sleep = Mock()
        client = build(sleep=sleep)
        limited = HTTPError("u", 429, "slow down", {"Retry-After": "30"}, None)
        with patch("dora_selection.api.urlopen", side_effect=[limited, Response({"ok": 1})]):
            self.assertEqual(client.get("/a")[0], {"ok": 1})
        sleep.assert_called_once_with(31)

    def test_forbidden_without_quota_signal_is_definitive(self):
        sleep = Mock()
        client = build(sleep=sleep)
        with patch("dora_selection.api.urlopen",
                   side_effect=HTTPError("u", 403, "forbidden", {}, None)) as opener:
            with self.assertRaisesRegex(APIError, "HTTP 403"):
                client.get("/a")
        self.assertEqual((opener.call_count, sleep.call_count), (1, 0))

    def test_wait_longer_than_limit_is_explicit(self):
        client = build(max_wait=60)
        with patch("dora_selection.api.urlopen", side_effect=[
                Response({}, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "99999"}), Response({})]):
            client.get("/a")
            with self.assertRaisesRegex(APIError, "excede o limite"):
                client.get("/b")


@patch.dict(os.environ, TOKEN)
class RetryTests(unittest.TestCase):
    def test_server_errors_use_exponential_backoff(self):
        sleep = Mock()
        client = build(sleep=sleep)
        failures = [HTTPError("u", 500, "x", {}, None), HTTPError("u", 502, "x", {}, None),
                    Response({"ok": 1})]
        with patch("dora_selection.api.urlopen", side_effect=failures):
            self.assertEqual(client.get("/a")[0], {"ok": 1})
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])
        self.assertEqual(client.stats["retries"], 2)

    def test_maximum_attempts_and_backoff_ceiling(self):
        sleep = Mock()
        client = build(sleep=sleep, max_attempts=4, backoff=10.0, max_backoff=15.0)
        with patch("dora_selection.api.urlopen",
                   side_effect=HTTPError("u", 503, "x", {}, None)) as opener:
            with self.assertRaisesRegex(APIError, "após 4 tentativa") as caught:
                client.get("/a")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(opener.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [10.0, 15.0, 15.0])

    def test_connection_failure_is_temporary_and_not_found_is_not(self):
        sleep = Mock()
        client = build(sleep=sleep)
        with patch("dora_selection.api.urlopen", side_effect=[URLError("reset"), Response({"ok": 1})]):
            self.assertEqual(client.get("/a")[0], {"ok": 1})
        self.assertEqual(sleep.call_count, 1)
        with patch("dora_selection.api.urlopen",
                   side_effect=HTTPError("u", 404, "missing", {}, None)) as opener:
            with self.assertRaises(APIError):
                client.get("/b")
        self.assertEqual((opener.call_count, sleep.call_count), (1, 1))

    def test_failed_response_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ResponseCache(directory)
            client = build(cache, sleep=Mock(), max_attempts=1)
            with patch("dora_selection.api.urlopen", side_effect=HTTPError("u", 500, "x", {}, None)):
                with self.assertRaises(APIError):
                    client.get("/a")
            self.assertEqual((cache.writes, list(Path(directory).glob("*/*.json"))), (0, []))

    def test_invalid_options(self):
        for options in ({"max_attempts": 0}, {"backoff": 0}, {"max_backoff": 0.1}, {"reserve": -1}):
            with self.assertRaises(APIError):
                build(**options)

    def test_errors_are_logged_in_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection.log"
            configure_logging(path)
            try:
                client = build(sleep=Mock(), max_attempts=2)
                with patch("dora_selection.api.urlopen", side_effect=HTTPError("u", 503, "x", {}, None)):
                    with self.assertRaises(APIError):
                        client.get("/search/repositories")
            finally:
                configure_logging(None, logging.CRITICAL)
            text = path.read_text(encoding="utf-8")
            self.assertIn("HTTP 503", text)
            self.assertIn("tentativa 2 de 2", text)
            self.assertIn("desistindo", text)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.jsonl"
        self.meta = {"card": "3", "window_start": WINDOW.start.isoformat()}

    def open(self):
        checkpoint = Checkpoint(self.path, self.meta)
        self.addCleanup(checkpoint.close)
        return checkpoint

    def test_completed_units_are_not_repeated(self):
        first = self.open()
        first.record("owner/ok", {"full_name": "owner/ok"}, True)
        first.record("owner/bad", {"full_name": "owner/bad"}, False)
        # Dentro da mesma execução o resultado recém-gravado não substitui a coleta.
        self.assertIsNone(first.done("owner/ok"))
        first.close()
        second = self.open()
        self.assertEqual(second.done("owner/ok"), {"full_name": "owner/ok"})
        self.assertIsNone(second.done("owner/bad"))
        self.assertEqual(second.reused, 1)

    def test_truncated_last_line_is_discarded_and_data_survives(self):
        first = self.open()
        first.record("owner/ok", {"full_name": "owner/ok"}, True)
        first.close()
        with self.path.open("a", encoding="utf-8") as file:
            file.write('{"unit": "owner/par')
        second = self.open()
        self.assertEqual(second.done("owner/ok"), {"full_name": "owner/ok"})
        second.record("owner/other", {"full_name": "owner/other"}, True)
        second.close()
        third = self.open()
        self.assertIsNotNone(third.done("owner/other"))
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 3)

    def test_other_configuration_is_refused(self):
        self.open().close()
        with self.assertRaisesRegex(APIError, "outra configuração"):
            Checkpoint(self.path, {"card": "3", "window_start": "2020-01-01T00:00:00+00:00"})

    def test_collection_reuses_and_retries(self):
        runs = [run(1)]
        client = Mock()
        client.get.side_effect = lambda *a, **k: ({"total_count": len(runs)}, {})
        client.pages.side_effect = lambda *a, **k: iter(runs)
        repositories = [{"full_name": "owner/ok", "default_branch": "main", "included": True},
                        {"full_name": "owner/bad", "default_branch": None, "included": True}]
        first = self.open()
        results = collect_workflow_repositories(client, WINDOW, repositories, first)
        first.close()
        self.assertEqual([r["complete"] for r in results], [True, False])
        calls = client.get.call_count
        second = self.open()
        again = collect_workflow_repositories(client, WINDOW, repositories, second)
        second.close()
        self.assertEqual(again[0], results[0])
        self.assertEqual(client.get.call_count, calls)  # repositório concluído não é recoletado
        self.assertEqual(second.reused, 1)
        self.assertFalse(again[1]["complete"])

    def test_releases_collection_reuses_and_retries(self):
        client = Mock()

        def pages(path, params=None, key=None):
            if "owner/bad" in path:
                raise APIError("HTTP 500 em /releases")
            return iter([])

        client.pages.side_effect = pages
        names = ["owner/ok", "owner/bad", "OWNER/OK"]
        first = self.open()
        results = collect_repositories(client, WINDOW, names, False, first)
        first.close()
        self.assertEqual([bool(r["errors"]) for r in results], [False, True])
        calls = client.pages.call_count
        second = self.open()
        again = collect_repositories(client, WINDOW, names, False, second)
        second.close()
        self.assertEqual(again[0], results[0])
        self.assertEqual(second.reused, 1)
        # Só o repositório com erro é consultado outra vez.
        self.assertEqual(client.pages.call_count, calls + 1)


@patch.dict(os.environ, TOKEN)
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "card3"
        self.source = Path(self.directory.name) / "selected.json"
        self.source.write_text(json.dumps([
            {"full_name": "owner/one", "default_branch": "main", "included": True},
            {"full_name": "owner/two", "default_branch": "main", "included": True}]), encoding="utf-8")
        self.addCleanup(configure_logging, None, logging.CRITICAL)

    def command(self):
        return ["--card", "3", "--input", str(self.source), "--start", "2026-01-01T00:00:00Z",
                "--end", "2026-01-31T23:59:59Z", "--output", str(self.output)]

    @patch("dora_selection.__main__.GitHubClient")
    def test_interruption_preserves_data_and_resumes(self, factory):
        self.interrupt = True
        client = Mock()
        client.stats = {"requests": 1}
        client.cache = None

        def get(path, params=None):
            if self.interrupt and "owner/two" in path:
                raise KeyboardInterrupt
            return {"total_count": 1}, {}

        client.get.side_effect = get
        client.pages.side_effect = lambda *a, **k: iter([run(1)])
        factory.return_value = client
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(self.command()), 1)
            interrupted = next(self.output.glob("run-*"))
            partial = json.loads((interrupted / "workflow_runs.json").read_text())
            self.assertEqual([r["full_name"] for r in partial], ["owner/one"])
            state = (self.output / "state.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(state[1])["unit"], "owner/one")
            self.interrupt = False
            self.assertEqual(main(self.command()), 0)
        # Nomes de pasta são aleatórios; a retomada é a que não existia antes.
        runs = [path for path in self.output.glob("run-*") if path != interrupted]
        self.assertEqual(len(runs), 1)
        complete = json.loads((runs[0] / "workflow_runs.json").read_text())
        self.assertEqual([r["full_name"] for r in complete], ["owner/one", "owner/two"])
        self.assertEqual(complete[0]["summary"]["total"], 1)
        summary = json.loads((runs[0] / "summary.json").read_text())
        self.assertEqual((summary["complete"], summary["api"]["resumed_units"]), (True, 1))
        # owner/one veio do diário; só owner/two foi consultado na retomada.
        self.assertNotIn("owner/one", str(client.get.call_args_list[-1]))

    @patch("dora_selection.__main__.GitHubClient")
    def test_no_resume_and_no_cache_options(self, factory):
        client = Mock()
        client.stats = {}
        client.cache = None
        client.get.side_effect = lambda *a, **k: ({"total_count": 0}, {})
        client.pages.side_effect = lambda *a, **k: iter([])
        factory.return_value = client
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(self.command() + ["--no-resume", "--no-cache"]), 0)
        self.assertFalse((self.output / "state.jsonl").exists())
        self.assertFalse((self.output / "cache").exists())
        self.assertIsNone(factory.call_args.kwargs["cache"])

    @patch("dora_selection.__main__.GitHubClient")
    def test_default_options_configure_cache_and_log(self, factory):
        client = Mock()
        client.stats = {}
        client.cache = None
        client.get.side_effect = lambda *a, **k: ({"total_count": 0}, {})
        client.pages.side_effect = lambda *a, **k: iter([])
        factory.return_value = client
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(self.command()), 0)
        options = factory.call_args.kwargs
        self.assertEqual(str(options["cache"].directory), str(self.output / "cache"))
        self.assertEqual((options["max_attempts"], options["backoff"]), (5, 1.0))
        self.assertTrue((self.output / "collection.log").exists())
        self.assertTrue((self.output / "state.jsonl").exists())


@patch.dict(os.environ, TOKEN)
class SelectionResumeTests(unittest.TestCase):
    ROW = {"full_name": "owner/repo", "url": "https://github.com/owner/repo", "stars": 1500,
           "language": None, "created_at": "2020-01-01T00:00:00Z", "default_branch": "main",
           "contributors": 3, "valid_releases": 5, "valid_workflow_runs": 50,
           "uses_github_actions": True, "included": True, "exclusion_reason": None, "error": None}

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "card1"
        self.addCleanup(configure_logging, None, logging.CRITICAL)

    @patch("dora_selection.__main__.GitHubClient")
    @patch("dora_selection.__main__.MetadataCollector")
    @patch("dora_selection.__main__.CandidateSearch")
    def test_evaluated_repository_is_not_collected_again(self, search, collector, factory):
        client = Mock()
        client.stats = {}
        client.cache = None
        factory.return_value = client
        search.return_value.candidates.side_effect = lambda: iter([{"full_name": "owner/repo"}])
        search.return_value.found = 1
        search.return_value.unique = 1
        collector.return_value.collect.return_value = self.ROW
        command = ["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z",
                   "--output", str(self.output)]
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(command), 1)  # amostra abaixo da meta
            self.assertEqual(collector.return_value.collect.call_count, 1)
            self.assertEqual(main(command), 1)
        self.assertEqual(collector.return_value.collect.call_count, 1)
        summary = json.loads((self.output / "funnel.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["api"]["resumed_units"], 1)
        self.assertEqual(summary["included"], 1)
        self.assertEqual(json.loads((self.output / "selected.json").read_text())[0]["full_name"],
                         "owner/repo")

    @patch("dora_selection.__main__.GitHubClient")
    @patch("dora_selection.__main__.MetadataCollector")
    @patch("dora_selection.__main__.CandidateSearch")
    def test_other_window_refuses_the_existing_diary(self, search, collector, factory):
        client = Mock()
        client.stats = {}
        client.cache = None
        factory.return_value = client
        search.return_value.candidates.side_effect = lambda: iter([])
        search.return_value.found = search.return_value.unique = 0
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(main(["--start", "2026-01-01T00:00:00Z", "--end", "2026-01-31T23:59:59Z",
                                   "--output", str(self.output)]), 1)
            with self.assertRaises(SystemExit):
                main(["--start", "2025-01-01T00:00:00Z", "--end", "2025-12-31T23:59:59Z",
                      "--output", str(self.output)])


@patch.dict(os.environ, TOKEN)
class EndToEndTests(unittest.TestCase):
    """Card 3 completo com o cliente real e apenas o transporte HTTP simulado."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "card3"
        self.source = Path(self.directory.name) / "selected.json"
        self.source.write_text(json.dumps([{"full_name": "owner/one", "default_branch": "main",
                                            "included": True}]), encoding="utf-8")
        self.addCleanup(configure_logging, None, logging.CRITICAL)
        self.failures = [HTTPError("u", 503, "unavailable", {}, None)]

    def transport(self, request, timeout=None):
        if self.failures:
            raise self.failures.pop(0)
        if "per_page=1&" in request.full_url or request.full_url.endswith("per_page=1"):
            return Response({"total_count": 1}, {"X-RateLimit-Remaining": "4999",
                                                 "X-RateLimit-Reset": "0"})
        return Response({"workflow_runs": [run(1)]}, {"X-RateLimit-Remaining": "4998",
                                                      "X-RateLimit-Reset": "0"})

    def command(self, *extra):
        return ["--card", "3", "--input", str(self.source), "--start", "2026-01-01T00:00:00Z",
                "--end", "2026-01-31T23:59:59Z", "--output", str(self.output),
                "--backoff", "0.001", *extra]

    def test_collects_with_retry_and_repeats_nothing_afterwards(self):
        with patch("dora_selection.api.urlopen", side_effect=self.transport) as opener:
            with patch("sys.stdout"):
                self.assertEqual(main(self.command()), 0)
        self.assertEqual(opener.call_count, 3)  # 503, contagem e página
        data = json.loads(next(self.output.glob("run-*/workflow_runs.json")).read_text())
        self.assertEqual(data[0]["summary"], {"success": 1, "failure": 0, "ignored": 0, "total": 1})
        summary = json.loads(next(self.output.glob("run-*/summary.json")).read_text())
        self.assertEqual((summary["api"]["retries"], summary["api"]["requests"]), (1, 2))
        self.assertTrue(list((self.output / "cache").glob("*/*.json")))
        # Sem o diário, a coleta é refeita inteira e ainda assim não chama a API.
        with patch("dora_selection.api.urlopen", side_effect=AssertionError("não deve chamar")):
            with patch("sys.stdout"):
                self.assertEqual(main(self.command("--no-resume")), 0)
        again = [json.loads(path.read_text()) for path in self.output.glob("run-*/summary.json")]
        self.assertEqual(sorted(entry["api"]["cache_hits"] for entry in again), [0, 2])


class ReportTests(unittest.TestCase):
    @patch.dict(os.environ, TOKEN)
    def test_report_is_serializable_and_counts_resumption(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ResponseCache(Path(directory) / "cache")
            checkpoint = Checkpoint(Path(directory) / "state.jsonl", {"card": "1"})
            checkpoint.record("owner/ok", {"ok": True}, True)
            checkpoint.close()
            resumed = Checkpoint(Path(directory) / "state.jsonl", {"card": "1"})
            resumed.done("owner/ok")
            report = collection_report(build(cache), resumed)
            resumed.close()
            self.assertEqual(report["resumed_units"], 1)
            self.assertEqual(report["cache_hits"], 0)
            json.dumps(report)

    def test_report_tolerates_clients_without_statistics(self):
        self.assertEqual(collection_report(Mock(), None)["resumed_units"], 0)


if __name__ == "__main__":
    unittest.main()
