import unittest
from datetime import datetime
from dora_selection.metrics import (aggregate_metrics, change_failure_rate, deployment_frequency,
                                    elapsed_hours, failure_episodes, iso_weeks, lead_time_per_commit,
                                    lead_time_per_release, median, moment, ordered_runs,
                                    recovery_time_by_workflow, repository_metrics)
from dora_selection.selection import Window, timestamp


# Janela de quatro semanas ISO completas: 2026-W02 a 2026-W05.
WINDOW = Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))


def release(n, published, commits=(), **changes):
    return {"repository": "owner/repo", "release_id": n, "tag_name": f"v{n}", "published_at": published,
            "comparison_status": "completed", "commits": list(commits), **changes}


def commit(sha, author_date):
    return {"repository": "owner/repo", "sha": sha, "author_date": author_date, "message": sha}


def run(i, classification="success", created="2026-01-05T00:00:00Z", updated=None, **changes):
    return {"repository": "owner/repo", "workflow_id": 7, "id": i, "classification": classification,
            "created_at": created, "updated_at": updated or created, **changes}


class HelperTests(unittest.TestCase):
    def test_missing_and_invalid_dates_do_not_raise(self):
        for value in (None, "", "sem data", 42, [], "2026-01-05T00:00:00"):
            self.assertIsNone(moment(value))
        self.assertIsNone(moment(datetime(2026, 1, 5)))
        self.assertEqual(moment("2026-01-05T00:00:00Z"), timestamp("2026-01-05T00:00:00Z"))
        self.assertEqual(moment(timestamp("2026-01-05T00:00:00Z")), timestamp("2026-01-05T00:00:00Z"))

    def test_median_ignores_missing_and_handles_empty(self):
        self.assertIsNone(median([]))
        self.assertIsNone(median(None))
        self.assertIsNone(median([None, None]))
        self.assertEqual(median([3, None, 1]), 2)
        self.assertEqual(median([1, 3]), 2.0)
        self.assertEqual(median(v for v in (5, 1, 3)), 3)

    def test_elapsed_hours_requires_both_dates(self):
        self.assertIsNone(elapsed_hours(None, "2026-01-05T00:00:00Z"))
        self.assertIsNone(elapsed_hours("2026-01-05T00:00:00Z", None))
        self.assertEqual(elapsed_hours("2026-01-05T00:00:00Z", "2026-01-05T06:00:00Z"), 6.0)
        self.assertEqual(elapsed_hours("2026-01-05T06:00:00Z", "2026-01-05T00:00:00Z"), -6.0)


class DeploymentFrequencyTests(unittest.TestCase):
    def frequency(self, dates, window=WINDOW):
        return deployment_frequency([release(n, d) for n, d in enumerate(dates)], window)

    def test_releases_per_week_and_weekly_median(self):
        result = self.frequency(["2026-01-05T00:00:00Z", "2026-01-07T00:00:00Z", "2026-01-11T23:59:59Z",
                                 "2026-01-15T00:00:00Z",
                                 "2026-01-26T00:00:00Z", "2026-01-28T00:00:00Z",
                                 "2026-01-30T00:00:00Z", "2026-02-01T23:59:59Z"])
        self.assertEqual(result["releases"], 8)
        self.assertEqual(result["weeks"], 4.0)
        self.assertEqual(result["releases_per_week"], 2.0)
        self.assertEqual([w["week"] for w in result["weekly_counts"]],
                         ["2026-W02", "2026-W03", "2026-W04", "2026-W05"])
        self.assertEqual([w["releases"] for w in result["weekly_counts"]], [3, 1, 0, 4])
        self.assertEqual(result["median_releases_per_week"], 2.0)
        self.assertEqual(result["complete_weeks"], 4)

    def test_window_and_missing_dates_are_counted_not_guessed(self):
        result = self.frequency(["2026-01-04T23:59:59Z", "2026-02-02T00:00:00Z", None, "inválida",
                                 "2026-01-06T00:00:00Z"])
        self.assertEqual(result["releases"], 1)
        self.assertEqual(result["ignored_outside_window"], 2)
        self.assertEqual(result["ignored_missing_date"], 2)

    def test_no_releases_and_partial_weeks(self):
        window = Window(timestamp("2026-01-07T00:00:00Z"), timestamp("2026-01-20T00:00:00Z"))
        result = deployment_frequency([], window)
        self.assertEqual(result["releases"], 0)
        self.assertEqual(result["releases_per_week"], 0.0)
        self.assertEqual(result["median_releases_per_week"], 0)
        self.assertEqual([w["complete"] for w in result["weekly_counts"]], [False, True, False])
        self.assertEqual(result["complete_weeks"], 1)
        self.assertEqual(deployment_frequency(None, window)["releases"], 0)

    def test_single_second_window_does_not_divide_by_zero(self):
        instant = timestamp("2026-01-05T00:00:00Z")
        result = deployment_frequency([release(1, "2026-01-05T00:00:00Z")], Window(instant, instant))
        self.assertEqual(len(result["weekly_counts"]), 1)
        self.assertEqual(result["releases"], 1)
        self.assertGreater(result["releases_per_week"], 0)

    def test_weeks_are_utc_monday_to_sunday(self):
        # Domingo 2026-01-04 às 21h em -03:00 já é segunda-feira em UTC: semana 2026-W02.
        weeks = iso_weeks(Window(timestamp("2026-01-04T21:00:00-03:00"), timestamp("2026-01-05T12:00:00Z")))
        self.assertEqual([w["week"] for w in weeks], ["2026-W02"])
        self.assertEqual(weeks[0]["start"], "2026-01-05T00:00:00+00:00")
        self.assertEqual(weeks[0]["end"], "2026-01-11T23:59:59+00:00")


class LeadTimeTests(unittest.TestCase):
    def setUp(self):
        self.measured = release(1, "2026-01-10T12:00:00Z", [
            commit("a", "2026-01-10T00:00:00Z"), commit("b", "2026-01-08T12:00:00Z"),
            commit("c", "2026-01-09T12:00:00Z")])

    def test_lead_time_per_commit(self):
        result = lead_time_per_commit([self.measured])
        self.assertEqual([c["lead_time_hours"] for c in result["commits"]], [12.0, 48.0, 24.0])
        self.assertEqual(result["measured"], 3)
        self.assertEqual(result["median_hours"], 24.0)
        first = result["commits"][0]
        self.assertEqual((first["repository"], first["release_id"], first["release_tag_name"]),
                         ("owner/repo", 1, "v1"))
        self.assertEqual(first["author_date"], "2026-01-10T00:00:00Z")
        self.assertEqual(first["published_at"], "2026-01-10T12:00:00Z")

    def test_lead_time_per_release_uses_oldest_commit(self):
        result = lead_time_per_release([self.measured])
        record = result["releases"][0]
        self.assertEqual(record["status"], "measured")
        self.assertEqual(record["lead_time_hours"], 48.0)
        self.assertEqual(record["median_commit_lead_time_hours"], 24.0)
        self.assertEqual(record["first_commit_author_date"], "2026-01-08T12:00:00+00:00")
        self.assertEqual(record["last_commit_author_date"], "2026-01-10T00:00:00+00:00")
        self.assertEqual((record["commits"], record["measured_commits"]), (3, 3))
        self.assertEqual(result["measured"], 1)
        self.assertEqual(result["median_hours"], 48.0)

    def test_median_over_several_releases(self):
        other = release(2, "2026-01-20T00:00:00Z", [commit("d", "2026-01-19T00:00:00Z")])
        third = release(3, "2026-01-25T00:00:00Z", [commit("e", "2026-01-01T00:00:00Z")])
        result = lead_time_per_release([self.measured, other, third])
        self.assertEqual([r["lead_time_hours"] for r in result["releases"]], [48.0, 24.0, 576.0])
        self.assertEqual(result["median_hours"], 48.0)
        self.assertEqual(lead_time_per_commit([self.measured, other, third])["median_hours"], 24.0)

    def test_releases_without_usable_interval(self):
        releases = [release(1, "2026-01-10T00:00:00Z", comparison_status="no_previous_release"),
                    release(2, "2026-01-11T00:00:00Z", comparison_status="not_found"),
                    release(3, "2026-01-12T00:00:00Z", comparison_status="error"),
                    release(4, None, [commit("a", "2026-01-01T00:00:00Z")]),
                    release(5, "2026-01-13T00:00:00Z", [])]
        for result in (lead_time_per_release(releases), lead_time_per_commit(releases)):
            self.assertEqual(result["releases_ignored"], {"no_previous_release": 1, "no_comparison": 2,
                                                          "no_date": 1, "no_commits": 1, "no_commit_dates": 0})
            self.assertIsNone(result["median_hours"])
        self.assertEqual([r["status"] for r in lead_time_per_release(releases)["releases"]],
                         ["no_previous_release", "no_comparison", "no_comparison", "no_date", "no_commits"])
        self.assertEqual(lead_time_per_release(releases)["measured"], 0)
        self.assertEqual(lead_time_per_commit(releases)["commits"], [])

    def test_commits_without_date_and_negative_lead_time(self):
        item = release(1, "2026-01-10T12:00:00Z", [commit("a", None), commit("b", "sem data"),
                                                   commit("c", "2026-01-10T18:00:00Z")])
        per_commit = lead_time_per_commit([item])
        self.assertEqual(per_commit["commits_without_date"], 2)
        self.assertEqual(per_commit["negative"], 1)
        self.assertEqual(per_commit["median_hours"], -6.0)
        per_release = lead_time_per_release([item])
        self.assertEqual(per_release["commits_without_date"], 2)
        self.assertEqual(per_release["releases"][0]["measured_commits"], 1)
        self.assertEqual(per_release["releases"][0]["lead_time_hours"], -6.0)

    def test_release_with_only_undated_commits(self):
        item = release(1, "2026-01-10T12:00:00Z", [commit("a", None)])
        result = lead_time_per_release([item])
        self.assertEqual(result["releases"][0]["status"], "no_commit_dates")
        self.assertEqual(result["releases_ignored"]["no_commit_dates"], 1)
        self.assertIsNone(result["releases"][0]["lead_time_hours"])
        self.assertIsNone(result["median_hours"])

    def test_empty_input(self):
        for function in (lead_time_per_commit, lead_time_per_release):
            for value in ([], None, [{}], [None]):
                result = function(value)
                self.assertIsNone(result["median_hours"])
                self.assertEqual(result["measured"], 0)

    def test_minimal_data_without_pipeline_fields(self):
        minimal = [{"published_at": "2026-01-10T00:00:00Z",
                    "commits": [{"author_date": "2026-01-09T00:00:00Z"}]}]
        self.assertEqual(lead_time_per_commit(minimal)["median_hours"], 24.0)
        self.assertEqual(lead_time_per_release(minimal)["median_hours"], 24.0)
        self.assertEqual(lead_time_per_commit(minimal)["commits"][0]["sha"], None)


class ChangeFailureRateTests(unittest.TestCase):
    def test_rate_ignores_runs_outside_the_denominator(self):
        runs = ([run(i, "success") for i in range(6)] + [run(10, "failure"), run(11, "failure")]
                + [run(12, "ignored"), run(13, "ignored"), run(14, "ignored")])
        result = change_failure_rate(runs)
        self.assertEqual((result["success"], result["failure"], result["ignored"]), (6, 2, 3))
        self.assertEqual((result["considered"], result["total"]), (8, 11))
        self.assertEqual(result["change_failure_rate"], 0.25)

    def test_no_considered_runs_returns_none_instead_of_zero(self):
        for runs in ([], None, [run(1, "ignored")]):
            result = change_failure_rate(runs)
            self.assertEqual(result["considered"], 0)
            self.assertIsNone(result["change_failure_rate"])

    def test_all_failures_and_all_successes(self):
        self.assertEqual(change_failure_rate([run(1, "failure")])["change_failure_rate"], 1.0)
        self.assertEqual(change_failure_rate([run(1, "success")])["change_failure_rate"], 0.0)

    def test_classification_recalculated_when_absent(self):
        raw = [{"status": "completed", "conclusion": "success"},
               {"status": "completed", "conclusion": "timed_out"},
               {"status": "completed", "conclusion": "startup_failure"},
               {"status": "completed", "conclusion": "failure"},
               {"status": "completed", "conclusion": "cancelled"},
               {"status": "in_progress", "conclusion": None}, {}, None]
        result = change_failure_rate(raw)
        self.assertEqual((result["success"], result["failure"], result["ignored"]), (1, 3, 4))
        self.assertEqual(result["change_failure_rate"], 0.75)


class FailureEpisodeTests(unittest.TestCase):
    def setUp(self):
        self.runs = [
            run(1, "success", "2026-01-05T00:00:00Z"),
            run(2, "failure", "2026-01-05T01:00:00Z", "2026-01-05T01:30:00Z"),
            run(3, "failure", "2026-01-05T02:00:00Z", "2026-01-05T02:30:00Z"),
            run(4, "ignored", "2026-01-05T03:00:00Z"),
            run(5, "success", "2026-01-05T04:00:00Z", "2026-01-05T05:00:00Z"),
        ]

    def test_consecutive_failures_form_one_episode(self):
        result = failure_episodes(self.runs, WINDOW.end)
        self.assertEqual(len(result["episodes"]), 1)
        episode = result["episodes"][0]
        self.assertEqual((episode["failure_run_id"], episode["failures"], episode["recovery_run_id"]), (2, 2, 5))
        self.assertEqual(episode["started_at"], "2026-01-05T01:00:00+00:00")
        self.assertEqual(episode["recovered_at"], "2026-01-05T05:00:00+00:00")
        self.assertEqual(episode["recovery_hours"], 4.0)
        self.assertTrue(episode["recovered"])
        self.assertFalse(episode["censored"])
        self.assertIsNone(episode["observed_hours"])
        self.assertEqual((result["recovered"], result["censored"]), (1, 0))
        self.assertEqual(result["median_recovery_hours"], 4.0)
        self.assertEqual((result["considered"], result["ignored"], result["runs"]), (4, 1, 5))
        self.assertEqual((episode["repository"], episode["workflow_id"]), ("owner/repo", 7))

    def test_out_of_order_input_is_sorted(self):
        shuffled = [self.runs[i] for i in (4, 0, 3, 2, 1)]
        self.assertEqual(failure_episodes(shuffled)["median_recovery_hours"], 4.0)
        ordered, undated = ordered_runs(shuffled + [run(9, "success", None)])
        self.assertEqual([r["id"] for r in ordered], [1, 2, 3, 4, 5])
        self.assertEqual(undated, 1)

    def test_success_before_any_failure_opens_nothing(self):
        result = failure_episodes([run(1, "success"), run(2, "success", "2026-01-06T00:00:00Z")])
        self.assertEqual(result["episodes"], [])
        self.assertIsNone(result["median_recovery_hours"])

    def test_separate_episodes_and_median(self):
        runs = self.runs + [
            run(6, "failure", "2026-01-06T00:00:00Z"),
            run(7, "success", "2026-01-06T01:00:00Z", "2026-01-06T02:00:00Z"),
        ]
        result = failure_episodes(runs, WINDOW.end)
        self.assertEqual([e["recovery_hours"] for e in result["episodes"]], [4.0, 2.0])
        self.assertEqual([e["failures"] for e in result["episodes"]], [2, 1])
        self.assertEqual(result["median_recovery_hours"], 3.0)

    def test_unrecovered_episode_is_censored_and_outside_the_median(self):
        runs = self.runs + [run(6, "failure", "2026-01-30T00:00:00Z"),
                            run(7, "failure", "2026-01-31T00:00:00Z"),
                            run(8, "ignored", "2026-02-01T00:00:00Z")]
        result = failure_episodes(runs, WINDOW.end)
        censored = result["episodes"][1]
        self.assertTrue(censored["censored"])
        self.assertFalse(censored["recovered"])
        self.assertIsNone(censored["recovery_hours"])
        self.assertIsNone(censored["recovered_at"])
        self.assertEqual(censored["failures"], 2)
        self.assertEqual(censored["observed_hours"], elapsed_hours("2026-01-30T00:00:00Z", WINDOW.end))
        self.assertEqual((result["recovered"], result["censored"]), (1, 1))
        self.assertEqual(result["median_recovery_hours"], 4.0)

    def test_only_failures_leaves_no_recovery_time(self):
        result = failure_episodes([run(1, "failure", "2026-01-05T00:00:00Z", "2026-01-05T06:00:00Z")])
        self.assertEqual(result["censored"], 1)
        self.assertIsNone(result["median_recovery_hours"])
        self.assertEqual(result["episodes"][0]["observed_hours"], 6.0)

    def test_missing_timestamps_do_not_break_episodes(self):
        runs = [run(1, "failure", "2026-01-05T01:00:00Z", updated_at=None),
                run(2, "success", "2026-01-05T03:00:00Z", updated_at=None),
                run(3, "failure", None)]
        result = failure_episodes(runs)
        self.assertEqual(result["runs_without_date"], 1)
        self.assertEqual(result["episodes"][0]["recovery_hours"], 2.0)
        self.assertEqual(len(result["episodes"]), 1)

    def test_inconsistent_recovery_is_flagged_and_excluded(self):
        runs = [run(1, "failure", "2026-01-05T01:00:00Z"),
                run(2, "success", "2026-01-05T02:00:00Z", "2026-01-05T00:30:00Z"),
                run(3, "failure", "2026-01-06T01:00:00Z"),
                run(4, "success", "2026-01-06T02:00:00Z", "2026-01-06T03:00:00Z")]
        result = failure_episodes(runs)
        self.assertTrue(result["episodes"][0]["inconsistent"])
        self.assertEqual(result["inconsistent"], 1)
        self.assertEqual(result["median_recovery_hours"], 2.0)

    def test_empty_input(self):
        for value in ([], None, [{}], [None]):
            result = failure_episodes(value)
            self.assertEqual(result["episodes"], [])
            self.assertIsNone(result["median_recovery_hours"])

    def test_minimal_runs_without_pipeline_fields(self):
        runs = [{"status": "completed", "conclusion": "failure", "created_at": "2026-01-05T00:00:00Z"},
                {"status": "completed", "conclusion": "success", "created_at": "2026-01-05T03:00:00Z"}]
        result = failure_episodes(runs)
        self.assertEqual(result["episodes"][0]["recovery_hours"], 3.0)
        self.assertIsNone(result["episodes"][0]["workflow_id"])


class RecoveryByWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflows = [
            {"repository": "owner/repo", "workflow_id": 7, "name": "CI", "runs": [
                run(1, "failure", "2026-01-05T00:00:00Z"),
                run(2, "success", "2026-01-05T04:00:00Z", "2026-01-05T04:00:00Z")]},
            {"repository": "owner/repo", "workflow_id": 8, "name": "Release", "runs": [
                run(3, "failure", "2026-01-06T00:00:00Z", workflow_id=8),
                run(4, "success", "2026-01-06T02:00:00Z", workflow_id=8),
                run(5, "failure", "2026-01-20T00:00:00Z", workflow_id=8)]},
            {"repository": "owner/repo", "workflow_id": 9, "name": "Docs", "runs": [run(6, "success")]},
        ]

    def test_per_workflow_series_and_medians(self):
        result = recovery_time_by_workflow(self.workflows, WINDOW.end)
        self.assertEqual([w["workflow_id"] for w in result["workflows"]], [7, 8, 9])
        self.assertEqual([w["median_recovery_hours"] for w in result["workflows"]], [4.0, 2.0, None])
        self.assertEqual(result["median_recovery_hours"], 3.0)
        self.assertEqual(result["median_workflow_recovery_hours"], 3.0)
        self.assertEqual((result["with_failures"], result["episodes"]), (2, 3))
        self.assertEqual((result["recovered"], result["censored"]), (2, 1))
        self.assertEqual(result["workflows"][1]["episodes"][1]["observed_hours"],
                         elapsed_hours("2026-01-20T00:00:00Z", WINDOW.end))
        self.assertEqual(result["workflows"][2]["name"], "Docs")

    def test_failures_are_not_mixed_between_workflows(self):
        self.workflows[0]["runs"] = [run(1, "failure", "2026-01-05T00:00:00Z")]
        result = recovery_time_by_workflow(self.workflows, WINDOW.end)
        self.assertEqual(result["workflows"][0]["censored"], 1)
        self.assertIsNone(result["workflows"][0]["median_recovery_hours"])
        self.assertEqual(result["median_recovery_hours"], 2.0)

    def test_empty_input(self):
        for value in ([], None, [{}], [None]):
            result = recovery_time_by_workflow(value)
            self.assertIsNone(result["median_recovery_hours"])
            self.assertEqual(result["with_failures"], 0)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.releases = [release(1, "2026-01-05T00:00:00Z", comparison_status="no_previous_release"),
                         release(2, "2026-01-12T00:00:00Z",
                                 [commit("a", "2026-01-10T00:00:00Z"), commit("b", "2026-01-11T00:00:00Z")],
                                 previous_tag_name="v1")]
        self.workflows = [{"repository": "owner/repo", "workflow_id": 7, "name": "CI", "runs": [
            run(1, "failure", "2026-01-05T00:00:00Z"),
            run(2, "success", "2026-01-05T02:00:00Z"),
            run(3, "ignored", "2026-01-06T00:00:00Z")]}]

    def test_repository_metrics_reuses_each_function(self):
        result = repository_metrics(WINDOW, self.releases, self.workflows, "owner/repo")
        self.assertEqual(result["repository"], "owner/repo")
        self.assertEqual(result["deployment_frequency"]["releases_per_week"], 0.5)
        self.assertEqual(result["lead_time_per_release"]["median_hours"], 48.0)
        self.assertEqual(result["lead_time_per_commit"]["median_hours"], 36.0)
        self.assertEqual(result["change_failure_rate"]["change_failure_rate"], 0.5)
        self.assertEqual(result["recovery_time"]["median_recovery_hours"], 2.0)
        self.assertEqual(result["window_start"], "2026-01-05T00:00:00+00:00")

    def test_repository_metrics_without_data(self):
        result = repository_metrics(WINDOW)
        self.assertEqual(result["deployment_frequency"]["releases"], 0)
        self.assertIsNone(result["change_failure_rate"]["change_failure_rate"])
        self.assertIsNone(result["lead_time_per_commit"]["median_hours"])
        self.assertIsNone(result["recovery_time"]["median_recovery_hours"])

    def test_aggregate_medians_skip_repositories_without_value(self):
        first = repository_metrics(WINDOW, self.releases, self.workflows, "owner/repo")
        second = repository_metrics(WINDOW, self.releases, [{"runs": [run(1, "failure")]}], "other/repo")
        empty = repository_metrics(WINDOW, [], [], "empty/repo")
        result = aggregate_metrics([first, second, empty, None])
        self.assertEqual(result["repositories"], 3)
        self.assertEqual(result["median_releases_per_week"], 0.5)
        self.assertEqual(result["median_recovery_hours"], 2.0)
        self.assertEqual(result["median_change_failure_rate"], 0.75)
        self.assertEqual(result["censored_episodes"], 1)
        self.assertEqual(result["repositories_without_releases"], 1)
        self.assertEqual(result["repositories_without_considered_runs"], 1)
        self.assertEqual(result["repositories_without_recovery"], 2)
        self.assertEqual(aggregate_metrics([])["repositories"], 0)
        self.assertIsNone(aggregate_metrics(None)["median_recovery_hours"])


if __name__ == "__main__":
    unittest.main()
