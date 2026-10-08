"""Card 7: métricas e classificação DORA verificadas com pytest e fixtures do conftest."""
import pytest
from dora_selection.metrics import (aggregate_metrics, change_failure_rate, deployment_frequency,
                                    failure_episodes, lead_time_per_commit, lead_time_per_release,
                                    recovery_time_by_workflow, repository_metrics)
from dora_selection.rating import (CHANGE_FAILURE_RATE, DEPLOYMENT_FREQUENCY, ELITE, HIGH, LEAD_TIME,
                                   LOW, MEDIUM, MONTHLY, RECOVERY_TIME, change_failure_rate_rating,
                                   classify_repository, classify_sample, deployment_frequency_rating,
                                   lead_time_rating, overall_classification, recovery_time_rating)
from dora_selection.selection import Window, timestamp


class TestDeploymentFrequency:
    def test_known_sample_has_one_release_per_week(self, releases, window):
        result = deployment_frequency(releases, window)
        assert result["releases"] == 4
        assert result["weeks"] == 4.0
        assert result["complete_weeks"] == 4
        assert result["releases_per_week"] == 1.0
        assert result["median_releases_per_week"] == 1
        assert [week["week"] for week in result["weekly_counts"]] == [
            "2026-W02", "2026-W03", "2026-W04", "2026-W05"]
        assert [week["releases"] for week in result["weekly_counts"]] == [1, 1, 1, 1]

    def test_window_limits_are_inclusive(self, make_release, window):
        result = deployment_frequency([make_release(1, "2026-01-05T00:00:00Z"),
                                       make_release(2, "2026-02-01T23:59:59Z"),
                                       make_release(3, "2026-01-04T23:59:59Z"),
                                       make_release(4, "2026-02-02T00:00:00Z")], window)
        assert result["releases"] == 2
        assert result["ignored_outside_window"] == 2

    def test_weeks_without_release_enter_the_median(self, make_release, window):
        result = deployment_frequency([make_release(n, "2026-01-07T00:00:00Z") for n in range(3)], window)
        assert [week["releases"] for week in result["weekly_counts"]] == [3, 0, 0, 0]
        assert result["releases_per_week"] == 0.75
        assert result["median_releases_per_week"] == 0

    @pytest.mark.parametrize("published_at", [None, "", "sem data", "2026-01-07T00:00:00"])
    def test_release_without_valid_date_is_counted_not_estimated(self, make_release, window, published_at):
        result = deployment_frequency([make_release(1, published_at)], window)
        assert result["releases"] == 0
        assert result["ignored_missing_date"] == 1

    @pytest.mark.parametrize("empty", [None, []])
    def test_no_releases_is_zero_not_missing(self, window, empty):
        result = deployment_frequency(empty, window)
        assert result["releases"] == 0
        assert result["releases_per_week"] == 0.0

    def test_partial_weeks_are_flagged(self, make_release):
        partial = Window(timestamp("2026-01-07T00:00:00Z"), timestamp("2026-01-13T23:59:59Z"))
        result = deployment_frequency([make_release(1, "2026-01-08T00:00:00Z")], partial)
        assert result["weeks"] == 1.0
        assert result["complete_weeks"] == 0
        assert [week["complete"] for week in result["weekly_counts"]] == [False, False]


class TestLeadTimePerCommit:
    def test_known_sample(self, releases):
        result = lead_time_per_commit(releases)
        assert [commit["lead_time_hours"] for commit in result["commits"]] == [24.0, 6.0, 48.0]
        assert result["measured"] == 3
        assert result["median_hours"] == 24.0
        assert result["releases_measured"] == 2
        assert result["releases_ignored"] == {"no_previous_release": 1, "no_comparison": 0, "no_date": 0,
                                              "no_commits": 1, "no_commit_dates": 0}

    def test_commit_carries_release_identification(self, releases):
        first = lead_time_per_commit(releases)["commits"][0]
        assert (first["repository"], first["release_id"], first["release_tag_name"], first["sha"]) == (
            "owner/repo", 2, "v2", "a")

    def test_commit_without_date_is_counted(self, make_release, make_commit):
        result = lead_time_per_commit([make_release(2, "2026-01-13T12:00:00Z", [
            make_commit("a", None), make_commit("b", "2026-01-13T00:00:00Z")])])
        assert result["commits_without_date"] == 1
        assert result["median_hours"] == 12.0

    def test_negative_lead_time_is_kept_and_counted(self, make_release, make_commit):
        result = lead_time_per_commit([make_release(2, "2026-01-13T12:00:00Z", [
            make_commit("a", "2026-01-13T15:00:00Z")])])
        assert result["negative"] == 1
        assert result["median_hours"] == -3.0


class TestLeadTimePerRelease:
    def test_example_from_the_assignment(self, make_release, make_commit):
        # v1.1 em 15/03 com commits de 02/03, 10/03 e 14/03: 13 dias por release; 13, 5 e 1 por commit.
        release = make_release(2, "2026-03-15T00:00:00Z", [make_commit("a", "2026-03-02T00:00:00Z"),
                                                           make_commit("b", "2026-03-10T00:00:00Z"),
                                                           make_commit("c", "2026-03-14T00:00:00Z")])
        assert lead_time_per_release([release])["releases"][0]["lead_time_hours"] == 13 * 24
        per_commit = lead_time_per_commit([release])
        assert [commit["lead_time_hours"] for commit in per_commit["commits"]] == [13 * 24, 5 * 24, 24]
        assert per_commit["median_hours"] == 5 * 24

    def test_known_sample(self, releases):
        result = lead_time_per_release(releases)
        assert [record["status"] for record in result["releases"]] == [
            "no_previous_release", "measured", "measured", "no_commits"]
        assert [record["lead_time_hours"] for record in result["releases"]] == [None, 24.0, 48.0, None]
        assert result["measured"] == 2
        assert result["median_hours"] == 36.0
        # Mediana por release dos commits: (24 + 6) / 2 = 15 h e 48 h.
        assert [record["median_commit_lead_time_hours"] for record in result["releases"]] == [
            None, 15.0, 48.0, None]
        assert result["median_commit_lead_time_hours"] == 31.5

    def test_interval_runs_from_oldest_commit(self, releases):
        record = lead_time_per_release(releases)["releases"][1]
        assert record["first_commit_author_date"] == "2026-01-12T12:00:00+00:00"
        assert record["last_commit_author_date"] == "2026-01-13T06:00:00+00:00"
        assert (record["commits"], record["measured_commits"]) == (2, 2)

    def test_release_whose_commits_have_no_date(self, make_release, make_commit):
        result = lead_time_per_release([make_release(2, "2026-01-13T12:00:00Z", [make_commit("a", None)])])
        assert result["releases"][0]["status"] == "no_commit_dates"
        assert result["releases_ignored"]["no_commit_dates"] == 1
        assert result["median_hours"] is None

    @pytest.mark.parametrize("changes, reason", [
        ({"comparison_status": "error"}, "no_comparison"),
        ({"comparison_status": "not_found"}, "no_comparison"),
        ({"published_at": None}, "no_date"),
    ])
    def test_unusable_releases_report_the_reason(self, make_release, make_commit, changes, reason):
        release = make_release(2, "2026-01-13T12:00:00Z", [make_commit("a", "2026-01-12T12:00:00Z")])
        release.update(changes)
        for variant in (lead_time_per_commit, lead_time_per_release):
            result = variant([release])
            assert result["releases_ignored"][reason] == 1
            assert result["median_hours"] is None


class TestReleaseWithoutNewCommits:
    """Release sem commits novos: conta como deployment, mas não produz Lead Time."""

    @pytest.fixture
    def empty_releases(self, make_release):
        return [make_release(1, "2026-01-06T12:00:00Z", comparison_status="no_previous_release"),
                make_release(2, "2026-01-13T12:00:00Z"),
                make_release(3, "2026-01-20T12:00:00Z")]

    def test_still_counts_as_deployment(self, empty_releases, window):
        assert deployment_frequency(empty_releases, window)["releases"] == 3

    def test_both_lead_time_variants_stay_empty(self, empty_releases):
        per_commit, per_release = lead_time_per_commit(empty_releases), lead_time_per_release(empty_releases)
        assert per_commit["median_hours"] is None and per_release["median_hours"] is None
        assert per_commit["releases_ignored"]["no_commits"] == 2
        assert per_release["releases_ignored"]["no_commits"] == 2
        assert [record["status"] for record in per_release["releases"]][1:] == ["no_commits", "no_commits"]

    def test_classification_reports_the_special_case(self, empty_releases, window):
        result = classify_repository(repository_metrics(window, empty_releases, [], "owner/repo"))
        assert result["ratings"]["lead_time"]["level"] is None
        assert result["ratings"]["lead_time"]["reason"] == "releases_without_new_commits"
        assert result["special_cases"]["releases_without_new_commits"] == 2
        assert result["special_cases"]["deployments_counted"] == 3


class TestSingleRelease:
    """Repositório com uma única release: sem release anterior não há intervalo de commits."""

    @pytest.fixture
    def single(self, make_release, window):
        releases = [make_release(1, "2026-01-06T12:00:00Z", comparison_status="no_previous_release")]
        return repository_metrics(window, releases, [], "owner/repo")

    def test_frequency_is_measured(self, single):
        assert single["deployment_frequency"]["releases"] == 1
        assert single["deployment_frequency"]["releases_per_week"] == 0.25

    def test_lead_time_is_unavailable(self, single):
        assert single["lead_time_per_commit"]["median_hours"] is None
        assert single["lead_time_per_release"]["median_hours"] is None
        assert single["lead_time_per_release"]["releases"][0]["status"] == "no_previous_release"

    def test_classification(self, single):
        result = classify_repository(single)
        assert result["ratings"]["deployment_frequency"]["level"] == MEDIUM
        assert result["ratings"]["lead_time"]["reason"] == "single_release"
        assert result["special_cases"]["single_release"] is True
        assert result["special_cases"]["releases_without_previous"] == 1
        # Só Deployment Frequency foi medida; as demais não entram na mediana.
        assert result["classified_metrics"] == 1
        assert result["overall"] == MEDIUM


class TestChangeFailureRate:
    def test_known_sample(self, ci_runs, deploy_runs):
        result = change_failure_rate(ci_runs + deploy_runs)
        assert result == {"total": 10, "success": 4, "failure": 4, "ignored": 2, "considered": 8,
                          "change_failure_rate": 0.5}

    def test_only_successes_is_zero(self, make_run):
        assert change_failure_rate([make_run(1), make_run(2)])["change_failure_rate"] == 0.0

    def test_only_failures_is_one(self, make_run):
        assert change_failure_rate([make_run(1, "failure")])["change_failure_rate"] == 1.0

    @pytest.mark.parametrize("empty", [None, []])
    def test_without_runs_the_rate_is_none(self, empty):
        result = change_failure_rate(empty)
        assert result["total"] == 0
        assert result["change_failure_rate"] is None


class TestIgnoredRuns:
    """Runs `cancelled` e demais valores ignorados ficam fora de todos os cálculos."""

    IGNORED_CONCLUSIONS = ["cancelled", "skipped", "neutral", "action_required", "stale", None, "", "unknown"]

    @pytest.mark.parametrize("conclusion", IGNORED_CONCLUSIONS)
    def test_conclusion_is_ignored(self, make_raw_run, conclusion):
        result = change_failure_rate([make_raw_run(1, conclusion)])
        assert (result["ignored"], result["considered"]) == (1, 0)
        assert result["change_failure_rate"] is None

    @pytest.mark.parametrize("status", ["in_progress", "queued", "requested", "waiting", None])
    def test_unfinished_run_is_ignored_even_with_conclusion(self, make_raw_run, status):
        result = change_failure_rate([make_raw_run(1, "failure", status=status)])
        assert (result["ignored"], result["failure"]) == (1, 0)

    @pytest.mark.parametrize("conclusion, kind", [("success", "success"), ("failure", "failure"),
                                                  ("timed_out", "failure"), ("startup_failure", "failure")])
    def test_considered_conclusions(self, make_raw_run, conclusion, kind):
        result = change_failure_rate([make_raw_run(1, conclusion)])
        assert result[kind] == 1 and result["considered"] == 1

    def test_ignored_runs_do_not_change_the_rate(self, make_raw_run):
        runs = [make_raw_run(1, "success"), make_raw_run(2, "failure")]
        noise = [make_raw_run(n, "cancelled") for n in range(3, 9)]
        assert change_failure_rate(runs)["change_failure_rate"] == 0.5
        assert change_failure_rate(runs + noise)["change_failure_rate"] == 0.5

    def test_cancelled_run_neither_opens_extends_nor_closes_an_episode(self, make_run):
        result = failure_episodes([
            make_run(1, "ignored", "2026-01-05T00:00:00Z", conclusion="cancelled"),
            make_run(2, "failure", "2026-01-05T10:00:00Z"),
            make_run(3, "ignored", "2026-01-05T11:00:00Z", conclusion="cancelled"),
            make_run(4, "success", "2026-01-05T13:00:00Z"),
        ])
        assert result["ignored"] == 2
        assert len(result["episodes"]) == 1
        episode = result["episodes"][0]
        assert (episode["failure_run_id"], episode["recovery_run_id"]) == (2, 4)
        assert (episode["failures"], episode["recovery_hours"]) == (1, 3.0)

    def test_only_ignored_runs_leave_cfr_unclassified(self, make_raw_run):
        rating = change_failure_rate_rating(change_failure_rate([make_raw_run(1, "cancelled")]))
        assert rating["level"] is None
        assert rating["reason"] == "only_ignored_runs"

    def test_invalid_persisted_classification_is_recomputed(self, make_raw_run):
        run = dict(make_raw_run(1, "timed_out"), classification="talvez")
        assert change_failure_rate([run])["failure"] == 1


class TestRecoveryTime:
    def test_known_workflow(self, ci_runs):
        result = failure_episodes(ci_runs)
        assert [episode["recovery_hours"] for episode in result["episodes"]] == [6.0, 2.0]
        assert result["median_recovery_hours"] == 4.0
        assert (result["runs"], result["considered"], result["ignored"]) == (8, 6, 2)
        assert (result["recovered"], result["censored"]) == (2, 0)

    def test_consecutive_failures_form_one_episode(self, ci_runs):
        first = failure_episodes(ci_runs)["episodes"][0]
        assert first["failures"] == 2
        assert (first["failure_run_id"], first["recovery_run_id"]) == (2, 5)
        assert first["started_at"] == "2026-01-06T10:00:00+00:00"
        # A recuperação termina no `updated_at` do sucesso, não no `created_at`.
        assert first["recovered_at"] == "2026-01-06T16:00:00+00:00"

    def test_example_from_the_assignment(self, make_run):
        # 09:00 success, 10:00 failure, 10:30 failure, 11:15 success que termina às 11:20: 1h20.
        result = failure_episodes([
            make_run(1, "success", "2026-01-05T09:00:00Z"),
            make_run(2, "failure", "2026-01-05T10:00:00Z"),
            make_run(3, "failure", "2026-01-05T10:30:00Z"),
            make_run(4, "success", "2026-01-05T11:15:00Z", "2026-01-05T11:20:00Z"),
        ])
        assert result["episodes"][0]["recovery_hours"] == pytest.approx(4 / 3)

    def test_episode_starts_at_run_started_at_of_the_first_failure(self, make_run):
        # Run criado às 10:00, mas iniciado (ou reexecutado) às 10:30.
        result = failure_episodes([
            make_run(1, "failure", "2026-01-05T10:00:00Z", run_started_at="2026-01-05T10:30:00Z"),
            make_run(2, "success", "2026-01-05T11:00:00Z", "2026-01-05T12:00:00Z"),
        ])
        episode = result["episodes"][0]
        assert episode["started_at"] == "2026-01-05T10:30:00+00:00"
        assert episode["recovery_hours"] == 1.5

    def test_run_without_run_started_at_falls_back_to_created_at(self, make_run):
        result = failure_episodes([
            make_run(1, "failure", "2026-01-05T10:00:00Z", run_started_at=None),
            make_run(2, "success", "2026-01-05T12:00:00Z"),
        ])
        assert result["episodes"][0]["recovery_hours"] == 2.0

    def test_runs_are_ordered_before_pairing(self, ci_runs):
        assert failure_episodes(list(reversed(ci_runs)))["median_recovery_hours"] == 4.0

    def test_run_without_date_is_left_out(self, ci_runs, make_run):
        undated = make_run(99, "failure", None)
        undated["updated_at"] = None
        result = failure_episodes(ci_runs + [undated])
        assert result["runs_without_date"] == 1
        assert result["median_recovery_hours"] == 4.0

    def test_no_failures_means_no_recovery_time(self, make_run):
        result = failure_episodes([make_run(1), make_run(2)])
        assert result["episodes"] == []
        assert result["median_recovery_hours"] is None

    def test_recovery_before_failure_is_flagged_inconsistent(self, make_run):
        result = failure_episodes([
            make_run(1, "failure", "2026-01-05T10:00:00Z"),
            make_run(2, "success", "2026-01-05T11:00:00Z", "2026-01-05T09:00:00Z"),
        ])
        assert result["inconsistent"] == 1
        assert result["median_recovery_hours"] is None

    def test_each_workflow_is_an_independent_series(self, workflows, window):
        result = recovery_time_by_workflow(workflows, window.end)
        assert (result["with_failures"], result["episodes"]) == (2, 3)
        assert (result["recovered"], result["censored"]) == (2, 1)
        assert result["median_recovery_hours"] == 4.0
        assert result["median_workflow_recovery_hours"] == 4.0
        assert [workflow["name"] for workflow in result["workflows"]] == ["CI", "Deploy"]


class TestUnrecoveredFailure:
    """Falha não recuperada: episódio censurado, fora da mediana e nunca tratado como zero."""

    def test_episode_is_censored_with_lower_bound(self, deploy_runs, window):
        result = failure_episodes(deploy_runs, window.end)
        episode = result["episodes"][0]
        assert (result["recovered"], result["censored"]) == (0, 1)
        assert episode["recovered"] is False and episode["censored"] is True
        assert episode["recovery_run_id"] is None and episode["recovery_hours"] is None
        # De 30/01 00:00:00 até o fim da janela, 01/02 23:59:59.
        assert episode["observed_hours"] == pytest.approx(72 - 1 / 3600)
        assert result["median_recovery_hours"] is None

    def test_without_window_end_the_last_run_bounds_the_observation(self, deploy_runs):
        episode = failure_episodes(deploy_runs)["episodes"][0]
        assert episode["observed_hours"] == pytest.approx(10 / 60)

    def test_censored_episode_does_not_enter_the_median(self, ci_runs, make_run, window):
        unrecovered = make_run(20, "failure", "2026-01-12T00:00:00Z")
        result = failure_episodes(ci_runs + [unrecovered], window.end)
        assert (result["recovered"], result["censored"]) == (2, 1)
        assert result["median_recovery_hours"] == 4.0

    def test_short_observation_stays_unclassified(self, deploy_runs, window):
        rating = recovery_time_rating(recovery_time_by_workflow([{"workflow_id": 8, "runs": deploy_runs}],
                                                                window.end))
        assert rating["level"] is None
        assert rating["reason"] == "never_recovered"

    def test_observation_beyond_a_week_is_low(self, make_run, window):
        runs = [make_run(1, "failure", "2026-01-05T00:00:00Z")]
        rating = recovery_time_rating(recovery_time_by_workflow([{"workflow_id": 7, "runs": runs}], window.end))
        assert rating["level"] == LOW
        assert rating["basis"] == "censored_lower_bound"

    def test_special_cases_count_it(self, metrics):
        cases = classify_repository(metrics)["special_cases"]
        assert cases["failures_never_recovered"] == 1
        assert cases["failure_episodes"] == 3
        assert cases["censored_majority"] is False


class TestRepositoryMetrics:
    def test_known_sample(self, metrics):
        assert metrics["repository"] == "owner/repo"
        assert metrics["window_start"] == "2026-01-05T00:00:00+00:00"
        assert metrics["window_end"] == "2026-02-01T23:59:59+00:00"
        assert metrics["deployment_frequency"]["releases_per_week"] == 1.0
        assert metrics["lead_time_per_commit"]["median_hours"] == 24.0
        assert metrics["lead_time_per_release"]["median_hours"] == 36.0
        assert metrics["change_failure_rate"]["change_failure_rate"] == 0.5
        assert metrics["recovery_time"]["median_recovery_hours"] == 4.0

    def test_empty_repository(self, window):
        result = repository_metrics(window)
        assert result["deployment_frequency"]["releases"] == 0
        assert result["lead_time_per_commit"]["median_hours"] is None
        assert result["change_failure_rate"]["change_failure_rate"] is None
        assert result["recovery_time"]["median_recovery_hours"] is None

    def test_aggregate_skips_repositories_without_value(self, metrics, window):
        result = aggregate_metrics([metrics, repository_metrics(window), None])
        assert result["repositories"] == 2
        assert result["median_releases_per_week"] == 0.5
        assert result["median_commit_lead_time_hours"] == 24.0
        assert result["median_release_lead_time_hours"] == 36.0
        assert result["median_change_failure_rate"] == 0.5
        assert result["median_recovery_hours"] == 4.0
        assert result["censored_episodes"] == 1
        assert result["repositories_without_releases"] == 1
        assert result["repositories_without_considered_runs"] == 1
        assert result["repositories_without_recovery"] == 1


class TestDoraThresholds:
    @pytest.mark.parametrize("value, level", [(7.0, ELITE), (6.99, HIGH), (1.0, HIGH), (0.99, MEDIUM),
                                              (MONTHLY, MEDIUM), (MONTHLY - 0.001, LOW), (0.0, LOW)])
    def test_deployment_frequency(self, value, level):
        assert DEPLOYMENT_FREQUENCY.level(value) == level

    @pytest.mark.parametrize("value, level", [(0.0, ELITE), (23.99, ELITE), (24.0, HIGH), (167.99, HIGH),
                                              (168.0, MEDIUM), (719.99, MEDIUM), (720.0, LOW)])
    def test_lead_time(self, value, level):
        # Enunciado: < 1 dia, < 1 semana, < 30 dias.
        assert LEAD_TIME.level(value) == level

    @pytest.mark.parametrize("value, level", [(0.0, ELITE), (0.99, ELITE), (1.0, HIGH), (23.99, HIGH),
                                              (24.0, MEDIUM), (167.99, MEDIUM), (168.0, LOW)])
    def test_recovery_time(self, value, level):
        # Enunciado: < 1 hora, < 1 dia, < 1 semana.
        assert RECOVERY_TIME.level(value) == level

    @pytest.mark.parametrize("value, level", [(0.0, ELITE), (0.15, ELITE), (0.151, HIGH), (0.30, HIGH),
                                              (0.301, MEDIUM), (0.45, MEDIUM), (0.451, LOW), (1.0, LOW)])
    def test_change_failure_rate(self, value, level):
        assert CHANGE_FAILURE_RATE.level(value) == level

    @pytest.mark.parametrize("value", [None, "1", True, float("nan"), float("inf")])
    def test_non_numeric_value_has_no_level(self, value):
        assert LEAD_TIME.level(value) is None


class TestDoraClassification:
    def test_known_sample(self, metrics):
        result = classify_repository(metrics)
        levels = {name: rating["level"] for name, rating in result["ratings"].items()}
        # Lead Time de 24 h já não é "menos de 1 dia": High, não Elite.
        assert levels == {"deployment_frequency": HIGH, "lead_time": HIGH,
                          "change_failure_rate": LOW, "recovery_time": HIGH}
        assert result["scores"] == [3, 3, 1, 3]
        assert result["median_score"] == 3.0
        assert (result["overall_score"], result["overall"]) == (3, HIGH)
        assert result["repository"] == "owner/repo"
        assert result["special_cases"]["unclassified_metrics"] == {}

    def test_lead_time_prefers_release_median(self, metrics):
        # Variante (a): mediana por release, 36 h; a por commit seria 24 h.
        rating = lead_time_rating(metrics["lead_time_per_commit"], metrics["lead_time_per_release"])
        assert (rating["value"], rating["basis"]) == (36.0, "release_median")

    def test_lead_time_falls_back_to_commit_median(self):
        rating = lead_time_rating({"median_hours": 0.5}, {"median_hours": None})
        assert (rating["level"], rating["basis"]) == (ELITE, "commit_median")

    @pytest.mark.parametrize("ratings, overall", [
        ([ELITE, ELITE, ELITE, ELITE], ELITE),
        ([ELITE, ELITE, HIGH, HIGH], HIGH),
        ([ELITE, HIGH, MEDIUM, LOW], MEDIUM),
        ([LOW, LOW, LOW, ELITE], LOW),
        ([HIGH, None, None, None], HIGH),
        ([ELITE, LOW, None, None], MEDIUM),
        ([None, None, None, None], None),
    ])
    def test_overall_is_the_floored_median(self, ratings, overall):
        assert overall_classification(ratings)["overall"] == overall

    def test_example_from_the_assignment(self):
        # Notas (4, 3, 3, 1): mediana 3, logo High.
        result = overall_classification([ELITE, HIGH, HIGH, LOW])
        assert (result["median_score"], result["overall"]) == (3.0, HIGH)

    def test_unmeasured_metrics_never_become_elite(self, window):
        result = classify_repository(repository_metrics(window))
        reasons = {name: rating["reason"] for name, rating in result["ratings"].items()}
        assert reasons == {"deployment_frequency": None, "lead_time": "no_releases",
                           "change_failure_rate": "no_runs", "recovery_time": "no_failures"}
        # Zero release é medição válida (Low); o restante fica sem classificação.
        assert result["ratings"]["deployment_frequency"]["level"] == LOW
        assert (result["classified_metrics"], result["overall"]) == (1, LOW)

    def test_missing_window_leaves_frequency_unclassified(self):
        assert deployment_frequency_rating(None)["reason"] == "no_window"

    def test_empty_input_is_fully_unclassified(self):
        result = classify_repository(None)
        assert result["overall"] is None
        assert result["classified_metrics"] == 0

    def test_sample_distribution(self, metrics, window):
        rows = [classify_repository(metrics), classify_repository(repository_metrics(window)), None]
        sample = classify_sample(rows)
        assert sample["repositories"] == 2
        assert sample["by_overall"] == {ELITE: 0, HIGH: 1, MEDIUM: 0, LOW: 1, "unclassified": 0}
        assert sample["by_metric"]["lead_time"] == {ELITE: 0, HIGH: 1, MEDIUM: 0, LOW: 0, "unclassified": 1}
        # Notas 3 e 1: mediana 2, Medium.
        assert (sample["median_score"], sample["overall"]) == (2.0, MEDIUM)
        assert sample["special_cases"]["failures_never_recovered"] == 1
