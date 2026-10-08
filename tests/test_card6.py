import unittest
from dora_selection.metrics import repository_metrics
from dora_selection.rating import (CHANGE_FAILURE_RATE, DEPLOYMENT_FREQUENCY, ELITE, HIGH, LEAD_TIME,
                                   LOW, MEDIUM, RECOVERY_TIME, change_failure_rate_rating,
                                   classify_repository, classify_sample, deployment_frequency_rating,
                                   lead_time_rating, level_from_score, overall_classification,
                                   recovery_time_rating, score)
from dora_selection.selection import Window, timestamp


# Quatro semanas ISO completas, a mesma janela usada nos testes do Card 5.
WINDOW = Window(timestamp("2026-01-05T00:00:00Z"), timestamp("2026-02-01T23:59:59Z"))


def release(n, published, commits=(), **changes):
    return {"repository": "owner/repo", "release_id": n, "tag_name": f"v{n}", "published_at": published,
            "comparison_status": "completed", "commits": list(commits), **changes}


def commit(sha, author_date):
    return {"repository": "owner/repo", "sha": sha, "author_date": author_date, "message": sha}


def run(i, classification="success", created="2026-01-05T00:00:00Z", updated=None, **changes):
    return {"repository": "owner/repo", "workflow_id": 7, "id": i, "classification": classification,
            "created_at": created, "updated_at": updated or created, **changes}


class ThresholdTests(unittest.TestCase):
    """Limites do enunciado, verificados também nas bordas de cada faixa."""

    def test_deployment_frequency_uses_inclusive_lower_bounds(self):
        for value, level in ((14.0, ELITE), (7.0, ELITE), (6.999, HIGH), (1.0, HIGH), (0.999, MEDIUM),
                             (0.23, MEDIUM), (0.2299, LOW), (0.0, LOW)):
            self.assertEqual(DEPLOYMENT_FREQUENCY.level(value), level, value)

    def test_lead_time_uses_exclusive_upper_bounds(self):
        for value, level in ((0.0, ELITE), (23.99, ELITE), (24.0, HIGH), (167.99, HIGH), (168.0, MEDIUM),
                             (719.99, MEDIUM), (720.0, LOW), (5000.0, LOW)):
            self.assertEqual(LEAD_TIME.level(value), level, value)

    def test_change_failure_rate_uses_inclusive_upper_bounds(self):
        for value, level in ((0.0, ELITE), (0.15, ELITE), (0.1501, HIGH), (0.30, HIGH),
                             (0.3001, MEDIUM), (0.45, MEDIUM), (0.4501, LOW), (1.0, LOW)):
            self.assertEqual(CHANGE_FAILURE_RATE.level(value), level, value)

    def test_recovery_time_uses_exclusive_upper_bounds(self):
        for value, level in ((0.0, ELITE), (0.999, ELITE), (1.0, HIGH), (23.99, HIGH), (24.0, MEDIUM),
                             (167.99, MEDIUM), (168.0, LOW), (5000.0, LOW)):
            self.assertEqual(RECOVERY_TIME.level(value), level, value)

    def test_non_numeric_values_are_not_classified(self):
        for scale in (DEPLOYMENT_FREQUENCY, LEAD_TIME, CHANGE_FAILURE_RATE, RECOVERY_TIME):
            for value in (None, "1", True, float("nan"), [], {}):
                self.assertIsNone(scale.level(value), (scale.metric, value))
        self.assertEqual(LEAD_TIME.level(-5.0), ELITE)


class ScoreTests(unittest.TestCase):
    """Elite = 4, High = 3, Medium = 2, Low = 1 e mediana arredondada para baixo."""

    def test_levels_convert_to_scores_and_back(self):
        self.assertEqual([score(level) for level in (ELITE, HIGH, MEDIUM, LOW)], [4, 3, 2, 1])
        self.assertEqual([level_from_score(n) for n in (4, 3, 2, 1)], [ELITE, HIGH, MEDIUM, LOW])
        self.assertIsNone(score("Outro"))
        self.assertIsNone(score(None))
        self.assertIsNone(level_from_score(0))
        self.assertIsNone(level_from_score(2.5))

    def test_median_of_four_classifications_is_rounded_down(self):
        cases = {(ELITE, HIGH, MEDIUM, LOW): (2.5, 2, MEDIUM),
                 (ELITE, ELITE, HIGH, HIGH): (3.5, 3, HIGH),
                 (ELITE, ELITE, ELITE, HIGH): (4.0, 4, ELITE),
                 (LOW, LOW, MEDIUM, ELITE): (1.5, 1, LOW),
                 (ELITE, ELITE, ELITE, ELITE): (4, 4, ELITE),
                 (LOW, LOW, LOW, LOW): (1, 1, LOW)}
        for levels, (middle, rounded, overall) in cases.items():
            result = overall_classification(levels)
            self.assertEqual((result["median_score"], result["overall_score"], result["overall"]),
                             (middle, rounded, overall), levels)
            self.assertEqual(result["classified_metrics"], 4)

    def test_scores_levels_and_ratings_are_accepted(self):
        self.assertEqual(overall_classification([4, 3, 2, 1])["overall"], MEDIUM)
        ratings = [{"score": 4}, {"score": 3}, {"score": 3}, {"score": None}]
        self.assertEqual(overall_classification(ratings)["overall"], HIGH)

    def test_metrics_without_classification_stay_out_of_the_median(self):
        result = overall_classification([ELITE, None, LOW, None])
        self.assertEqual((result["classified_metrics"], result["median_score"]), (2, 2.5))
        self.assertEqual(result["overall"], MEDIUM)
        empty = overall_classification([None, None, None, None])
        self.assertEqual((empty["classified_metrics"], empty["median_score"]), (0, None))
        self.assertIsNone(empty["overall_score"])
        self.assertIsNone(empty["overall"])
        self.assertIsNone(overall_classification(None)["overall"])


class MetricRatingTests(unittest.TestCase):
    def test_deployment_frequency_counts_zero_releases_as_low(self):
        result = deployment_frequency_rating({"releases": 0, "releases_per_week": 0.0})
        self.assertEqual((result["level"], result["score"], result["reason"]), (LOW, 1, None))
        daily = deployment_frequency_rating({"releases": 28, "releases_per_week": 7.0})
        self.assertEqual(daily["level"], ELITE)

    def test_deployment_frequency_without_window_is_not_classified(self):
        result = deployment_frequency_rating({"releases": 3, "releases_per_week": None})
        self.assertEqual((result["level"], result["score"], result["reason"]), (None, None, "no_window"))
        self.assertIsNone(deployment_frequency_rating(None)["level"])

    def test_lead_time_prefers_the_release_median(self):
        result = lead_time_rating({"median_hours": 30.0}, {"median_hours": 800.0})
        self.assertEqual((result["level"], result["basis"]), (LOW, "release_median"))
        fallback = lead_time_rating({"median_hours": 30.0}, None)
        self.assertEqual((fallback["level"], fallback["basis"]), (HIGH, "commit_median"))

    def test_change_failure_rate_rating(self):
        result = change_failure_rate_rating({"total": 10, "success": 9, "failure": 1,
                                             "ignored": 0, "considered": 10,
                                             "change_failure_rate": 0.1})
        self.assertEqual((result["level"], result["score"]), (ELITE, 4))

    def test_recovery_time_uses_the_median_of_recovered_episodes(self):
        result = recovery_time_rating({"recovered": 2, "censored": 0, "median_recovery_hours": 30.0,
                                       "workflows": []})
        self.assertEqual((result["level"], result["basis"]), (MEDIUM, "recovered_median"))

    def test_repository_without_failures_is_not_elite_by_omission(self):
        result = recovery_time_rating({"recovered": 0, "censored": 0, "median_recovery_hours": None,
                                       "workflows": [{"episodes": []}]})
        self.assertEqual((result["level"], result["reason"]), (None, "no_failures"))
        self.assertIsNone(recovery_time_rating(None)["level"])
        self.assertIsNone(recovery_time_rating({})["score"])


class SpecialCaseTests(unittest.TestCase):
    """Casos de borda: sem commits novos, release única, falha sem recuperação e runs ignoráveis."""

    def classify(self, releases=(), workflows=()):
        metrics = repository_metrics(WINDOW, list(releases), list(workflows), "owner/repo")
        return classify_repository(metrics)

    def test_release_without_new_commits_still_counts_as_deployment(self):
        releases = [release(1, "2026-01-06T00:00:00Z", comparison_status="no_previous_release"),
                    release(2, "2026-01-20T00:00:00Z")]
        result = self.classify(releases)
        cases = result["special_cases"]
        self.assertEqual(cases["deployments_counted"], 2)
        self.assertEqual(cases["releases_without_new_commits"], 1)
        self.assertEqual(cases["releases_without_previous"], 1)
        self.assertEqual(result["ratings"]["deployment_frequency"]["level"], MEDIUM)
        lead_time = result["ratings"]["lead_time"]
        self.assertEqual((lead_time["level"], lead_time["reason"]), (None, "releases_without_new_commits"))
        self.assertEqual(result["ratings"]["lead_time"]["value"], None)
        self.assertEqual(cases["unclassified_metrics"]["lead_time"], "releases_without_new_commits")

    def test_repository_with_a_single_release_has_no_lead_time(self):
        result = self.classify([release(1, "2026-01-06T00:00:00Z",
                                        [commit("a", "2026-01-05T00:00:00Z")],
                                        comparison_status="no_previous_release")])
        cases = result["special_cases"]
        self.assertTrue(cases["single_release"])
        self.assertEqual(cases["releases_considered"], 1)
        self.assertEqual(cases["releases_without_previous"], 1)
        self.assertEqual(cases["deployments_counted"], 1)
        self.assertEqual(result["ratings"]["lead_time"]["reason"], "single_release")
        # A frequência continua medida: uma release em quatro semanas é Medium.
        self.assertEqual(result["ratings"]["deployment_frequency"]["level"], MEDIUM)
        self.assertEqual(result["classified_metrics"], 1)
        self.assertEqual(result["overall"], MEDIUM)

    def test_failure_never_recovered_is_neither_instant_nor_ignored(self):
        workflows = [{"repository": "owner/repo", "workflow_id": 7,
                      "runs": [run(1, "success", "2026-01-05T00:00:00Z"),
                               run(2, "failure", "2026-02-01T12:00:00Z")]}]
        result = self.classify([], workflows)
        recovery = result["ratings"]["recovery_time"]
        self.assertEqual((recovery["level"], recovery["reason"]), (None, "never_recovered"))
        self.assertIsNone(recovery["value"])
        cases = result["special_cases"]
        self.assertEqual(cases["failures_never_recovered"], 1)
        self.assertEqual(cases["failure_episodes"], 1)
        self.assertTrue(cases["censored_majority"])
        self.assertEqual(cases["unclassified_metrics"],
                         {"lead_time": "no_releases", "recovery_time": "never_recovered"})

    def test_long_censored_failure_is_classified_low_by_its_lower_bound(self):
        workflows = [{"repository": "owner/repo", "workflow_id": 7,
                      "runs": [run(1, "failure", "2026-01-06T00:00:00Z")]}]
        result = self.classify([], workflows)
        recovery = result["ratings"]["recovery_time"]
        self.assertEqual((recovery["level"], recovery["basis"]), (LOW, "censored_lower_bound"))
        # Limite inferior: do início da falha até o fim da janela.
        self.assertAlmostEqual(recovery["value"], 647.9997, places=3)
        self.assertEqual(result["special_cases"]["failures_never_recovered"], 1)

    def test_censored_episodes_stay_out_of_the_recovered_median(self):
        workflows = [{"repository": "owner/repo", "workflow_id": 7,
                      "runs": [run(1, "failure", "2026-01-06T00:00:00Z"),
                               run(2, "success", "2026-01-06T02:00:00Z"),
                               run(3, "failure", "2026-02-01T00:00:00Z")]}]
        result = self.classify([], workflows)
        recovery = result["ratings"]["recovery_time"]
        self.assertEqual((recovery["value"], recovery["level"], recovery["basis"]),
                         (2.0, HIGH, "recovered_median"))
        self.assertEqual(result["special_cases"]["failures_never_recovered"], 1)

    def test_only_ignorable_runs_do_not_become_elite(self):
        ignorable = [run(i, "ignored", "2026-01-06T00:00:00Z") for i in range(1, 6)]
        result = self.classify([], [{"repository": "owner/repo", "workflow_id": 7, "runs": ignorable}])
        failure_rate = result["ratings"]["change_failure_rate"]
        self.assertEqual((failure_rate["level"], failure_rate["reason"]), (None, "only_ignored_runs"))
        cases = result["special_cases"]
        self.assertEqual((cases["ignored_runs"], cases["considered_runs"]), (5, 0))
        self.assertTrue(cases["only_ignored_runs"])
        self.assertEqual(cases["failure_episodes"], 0)
        self.assertEqual(result["ratings"]["recovery_time"]["reason"], "no_failures")

    def test_ignorable_runs_do_not_open_or_close_failure_episodes(self):
        runs = [run(1, "failure", "2026-01-06T00:00:00Z"),
                run(2, "ignored", "2026-01-06T00:10:00Z"),
                run(3, "success", "2026-01-06T00:30:00Z"),
                run(4, "ignored", "2026-01-06T01:00:00Z")]
        result = self.classify([], [{"repository": "owner/repo", "workflow_id": 7, "runs": runs}])
        recovery = result["ratings"]["recovery_time"]
        self.assertEqual((recovery["value"], recovery["level"]), (0.5, ELITE))
        cases = result["special_cases"]
        self.assertEqual((cases["failure_episodes"], cases["failures_never_recovered"]), (1, 0))
        self.assertEqual(cases["ignored_runs"], 2)
        # Denominador só com sucesso e falha: 1/2 está acima de 45%.
        self.assertEqual(result["ratings"]["change_failure_rate"]["level"], LOW)

    def test_runs_classified_by_status_and_conclusion_without_the_card3_field(self):
        runs = [{"id": 1, "workflow_id": 7, "status": "completed", "conclusion": "failure",
                 "created_at": "2026-01-06T00:00:00Z", "updated_at": "2026-01-06T00:00:00Z"},
                {"id": 2, "workflow_id": 7, "status": "in_progress", "conclusion": None,
                 "created_at": "2026-01-06T00:30:00Z", "updated_at": "2026-01-06T00:30:00Z"},
                {"id": 3, "workflow_id": 7, "status": "completed", "conclusion": "success",
                 "created_at": "2026-01-06T02:00:00Z", "updated_at": "2026-01-06T02:00:00Z"}]
        result = self.classify([], [{"workflow_id": 7, "runs": runs}])
        self.assertEqual(result["ratings"]["recovery_time"]["value"], 2.0)
        self.assertEqual(result["special_cases"]["ignored_runs"], 1)

    def test_missing_dates_and_negative_lead_times_are_reported(self):
        releases = [release(1, "2026-01-06T00:00:00Z", comparison_status="no_previous_release"),
                    release(2, "2026-01-07T00:00:00Z",
                            [commit("a", "2026-01-07T06:00:00Z"), commit("b", None)]),
                    release(3, None, [commit("c", "2026-01-08T00:00:00Z")])]
        result = self.classify(releases)
        cases = result["special_cases"]
        self.assertEqual(cases["commits_without_date"], 1)
        self.assertEqual(cases["negative_lead_times"], 1)
        self.assertEqual(cases["releases_without_date"], 1)
        self.assertEqual(cases["releases_ignored_by_date"], 1)
        self.assertEqual(result["ratings"]["lead_time"]["level"], ELITE)

    def test_release_with_comparison_error_does_not_produce_lead_time(self):
        releases = [release(1, "2026-01-06T00:00:00Z", comparison_status="no_previous_release"),
                    release(2, "2026-01-20T00:00:00Z", comparison_status="not_found")]
        result = self.classify(releases)
        self.assertEqual(result["ratings"]["lead_time"]["reason"], "comparison_unavailable")
        self.assertEqual(result["special_cases"]["releases_without_comparison"], 1)

    def test_empty_repository_has_no_classification_except_frequency(self):
        result = self.classify()
        self.assertEqual(result["ratings"]["deployment_frequency"]["level"], LOW)
        self.assertEqual(result["ratings"]["lead_time"]["reason"], "no_releases")
        self.assertEqual(result["ratings"]["change_failure_rate"]["reason"], "no_runs")
        self.assertEqual(result["ratings"]["recovery_time"]["reason"], "no_failures")
        self.assertEqual((result["classified_metrics"], result["overall"]), (1, LOW))

    def test_classification_tolerates_missing_and_empty_input(self):
        for metrics in (None, {}, {"deployment_frequency": None}):
            result = classify_repository(metrics)
            self.assertEqual(len(result["ratings"]), 4)
            self.assertIsNone(result["overall"])
            self.assertEqual(result["classified_metrics"], 0)
        self.assertEqual(classify_repository({}, "owner/repo")["repository"], "owner/repo")


class RepositoryClassificationTests(unittest.TestCase):
    def setUp(self):
        self.releases = [release(1, "2026-01-05T06:00:00Z", comparison_status="no_previous_release"),
                         release(2, "2026-01-06T06:00:00Z", [commit("a", "2026-01-06T00:00:00Z"),
                                                             commit("b", "2026-01-05T18:00:00Z")]),
                         release(3, "2026-01-07T06:00:00Z", [commit("c", "2026-01-07T00:00:00Z")]),
                         release(4, "2026-01-08T06:00:00Z", [commit("d", "2026-01-08T00:00:00Z")]),
                         release(5, "2026-01-12T06:00:00Z", [commit("e", "2026-01-12T00:00:00Z")])]
        self.workflows = [{"repository": "owner/repo", "workflow_id": 7,
                           "runs": [run(1, "success", "2026-01-06T00:00:00Z"),
                                    run(2, "failure", "2026-01-07T00:00:00Z"),
                                    run(3, "success", "2026-01-07T00:30:00Z"),
                                    run(4, "success", "2026-01-08T00:00:00Z"),
                                    run(5, "success", "2026-01-09T00:00:00Z"),
                                    run(6, "success", "2026-01-10T00:00:00Z"),
                                    run(7, "ignored", "2026-01-11T00:00:00Z")]}]

    def test_four_metrics_are_classified_and_the_median_is_floored(self):
        metrics = repository_metrics(WINDOW, self.releases, self.workflows, "owner/repo")
        result = classify_repository(metrics)
        self.assertEqual(result["repository"], "owner/repo")
        self.assertEqual(result["window_start"], metrics["window_start"])
        levels = {name: rating["level"] for name, rating in result["ratings"].items()}
        self.assertEqual(levels, {"deployment_frequency": HIGH, "lead_time": ELITE,
                                  "change_failure_rate": HIGH, "recovery_time": ELITE})
        self.assertEqual(result["scores"], [3, 4, 3, 4])
        self.assertEqual((result["median_score"], result["overall_score"], result["overall"]),
                         (3.5, 3, HIGH))
        self.assertEqual(result["ratings"]["change_failure_rate"]["value"], 1 / 6)
        self.assertEqual(result["ratings"]["recovery_time"]["value"], 0.5)
        self.assertEqual(result["special_cases"]["unclassified_metrics"], {})
        self.assertEqual(result["special_cases"]["ignored_runs"], 1)

    def test_sample_distribution_and_overall(self):
        good = classify_repository(repository_metrics(WINDOW, self.releases, self.workflows, "owner/repo"))
        single = classify_repository(repository_metrics(
            WINDOW, [release(1, "2026-01-06T00:00:00Z", comparison_status="no_previous_release")],
            [], "owner/single"))
        empty = classify_repository(repository_metrics(WINDOW, [], [], "owner/empty"))
        result = classify_sample([good, single, empty, None])
        self.assertEqual(result["repositories"], 3)
        self.assertEqual(result["by_metric"]["deployment_frequency"],
                         {ELITE: 0, HIGH: 1, MEDIUM: 1, LOW: 1, "unclassified": 0})
        self.assertEqual(result["by_metric"]["lead_time"],
                         {ELITE: 1, HIGH: 0, MEDIUM: 0, LOW: 0, "unclassified": 2})
        self.assertEqual(result["by_overall"],
                         {ELITE: 0, HIGH: 1, MEDIUM: 1, LOW: 1, "unclassified": 0})
        self.assertEqual((result["median_score"], result["overall_score"], result["overall"]), (2, 2, MEDIUM))
        self.assertEqual(result["classified_repositories"], 3)
        self.assertEqual(result["special_cases"]["single_release"], 1)
        self.assertEqual(result["special_cases"]["deployments_counted"], 6)
        self.assertEqual(classify_sample([])["repositories"], 0)
        self.assertIsNone(classify_sample(None)["overall"])


if __name__ == "__main__":
    unittest.main()
