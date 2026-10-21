import unittest
from dora_selection.cfr import (cfr_entrega, eh_corretiva, eh_fix_commit, parse_semver, rework_rate,
                                semver_patch_only)
from dora_selection.selection import timestamp


# Fim da janela da Sprint 2: releases após 2026-01-25T23:59:59Z ficam censuradas.
END = "2026-02-01T23:59:59Z"


def release(n, tag, published, messages=(), **changes):
    return {"repository": "owner/repo", "release_id": n, "tag_name": tag, "published_at": published,
            "comparison_status": "completed", "commits": [commit(m) for m in messages], **changes}


def commit(message):
    return {"repository": "owner/repo", "sha": message[:7], "message": message}


class SemverTests(unittest.TestCase):
    def test_parses_tolerant_prefixes_and_suffixes(self):
        for tag, expected in (("1.2.3", (1, 2, 3)), ("v1.2.3", (1, 2, 3)), ("V1.2.3", (1, 2, 3)),
                              ("release-1.2.3", (1, 2, 3)), ("pkg@1.2.3", (1, 2, 3)),
                              ("v2.0", (2, 0, 0)), (" v1.2.3 ", (1, 2, 3)),
                              ("v1.2.3-rc.1", (1, 2, 3)), ("1.2.3+build.5", (1, 2, 3))):
            self.assertEqual(parse_semver(tag), expected, tag)

    def test_unparseable_tags_return_none_instead_of_raising(self):
        for tag in ("2024-05-10", "2024.05.10", "latest", "v1", "", None, 42, "1.2.3.4", "v1.2.x"):
            self.assertIsNone(parse_semver(tag), tag)

    def test_patch_only_decides_when_tags_are_comparable(self):
        self.assertTrue(semver_patch_only({"tag_name": "v2.3.1"}, {"tag_name": "v2.3.0"}))
        self.assertFalse(semver_patch_only({"tag_name": "v2.5.0"}, {"tag_name": "v2.4.0"}))
        self.assertFalse(semver_patch_only({"tag_name": "v3.0.0"}, {"tag_name": "v2.9.9"}))

    def test_own_patch_decides_without_smaller_previous(self):
        self.assertTrue(semver_patch_only({"tag_name": "v2.3.1"}, None))
        self.assertFalse(semver_patch_only({"tag_name": "v2.3.0"}, {"tag_name": "nightly"}))
        # Tag menor ou igual à anterior (backport, retag): decide o próprio patch.
        self.assertTrue(semver_patch_only({"tag_name": "v1.0.1"}, {"tag_name": "v2.0.0"}))
        self.assertFalse(semver_patch_only({"tag_name": "v1.0.0"}, {"tag_name": "1.0.0"}))

    def test_undecided_when_tag_is_not_semver(self):
        self.assertIsNone(semver_patch_only({"tag_name": "2024-05-10"}, {"tag_name": "v1.0.0"}))
        self.assertIsNone(semver_patch_only({}, None))


class FixCommitTests(unittest.TestCase):
    def test_matches_whole_words_only(self):
        for message in ("fix: null pointer", "Fix typo", "hotfix for login", "Revert \"feat: x\"",
                        "fix(api): timeout", "chore: quick fix"):
            self.assertTrue(eh_fix_commit(commit(message)), message)
        for message in ("feat: add prefix option", "test: new fixture", "bugfix in parser",
                        "fixes #12", "docs: update README"):
            self.assertFalse(eh_fix_commit(commit(message)), message)

    def test_only_first_line_and_missing_messages(self):
        self.assertFalse(eh_fix_commit(commit("feat: new api\n\nAlso a small fix")))
        self.assertFalse(eh_fix_commit({"message": None}))
        self.assertFalse(eh_fix_commit(None))


class EhCorretivaTests(unittest.TestCase):
    def test_semver_overrides_commit_messages(self):
        self.assertTrue(eh_corretiva({"tag_name": "v2.3.1"}, {"tag_name": "v2.3.0"}, []))
        self.assertFalse(eh_corretiva({"tag_name": "v2.5.0"}, {"tag_name": "v2.4.0"},
                                      [commit("fix: a"), commit("fix: b")]))

    def test_commits_decide_without_comparable_semver(self):
        current, previous = {"tag_name": "2024-05-10"}, {"tag_name": "2024-05-01"}
        self.assertTrue(eh_corretiva(current, previous, [commit("fix: a"), commit("feat: b")]))
        self.assertFalse(eh_corretiva(current, previous,
                                      [commit("fix: a"), commit("feat: b"), commit("feat: c")]))
        self.assertTrue(eh_corretiva({"tag_name": "nightly"}, None, [commit("hotfix: crash")]))

    def test_without_commits_or_semver_is_not_corrective(self):
        self.assertFalse(eh_corretiva({"tag_name": "nightly"}, {"tag_name": "nightly-2"}, []))
        self.assertFalse(eh_corretiva({"tag_name": "nightly"}, None, None))
        self.assertFalse(eh_corretiva({"tag_name": "nightly"}, None, [None]))


class CfrEntregaTests(unittest.TestCase):
    def test_release_followed_by_patch_within_seven_days_failed(self):
        result = cfr_entrega([release(1, "v2.3.0", "2026-01-05T12:00:00Z"),
                              release(2, "v2.3.1", "2026-01-08T12:00:00Z")], END)
        first, second = result["details"]
        self.assertTrue(first["failed"])
        self.assertEqual(first["fixed_by_tag_name"], "v2.3.1")
        self.assertFalse(second["failed"])
        self.assertTrue(second["corrective"])
        self.assertEqual((result["evaluated"], result["failed"], result["censored"]), (2, 1, 0))
        self.assertEqual(result["change_failure_rate"], 0.5)
        self.assertEqual(result["heuristic"], "v1")

    def test_minor_release_does_not_fail_the_previous(self):
        result = cfr_entrega([release(1, "v2.4.0", "2026-01-05T12:00:00Z"),
                              release(2, "v2.5.0", "2026-01-06T12:00:00Z", ["fix: a"])], END)
        self.assertEqual((result["failed"], result["corrective"]), (0, 0))
        self.assertEqual(result["change_failure_rate"], 0.0)

    def test_fix_after_seven_days_does_not_count(self):
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-05T12:00:00Z"),
                              release(2, "v1.0.1", "2026-01-12T12:00:01Z")], END)
        self.assertFalse(result["details"][0]["failed"])
        # Exatamente 7 dias depois ainda conta.
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-05T12:00:00Z"),
                              release(2, "v1.0.1", "2026-01-12T12:00:00Z")], END)
        self.assertTrue(result["details"][0]["failed"])

    def test_any_later_fix_of_the_same_line_within_seven_days_counts(self):
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-05T12:00:00Z"),
                              release(2, "v2.0.0", "2026-01-06T12:00:00Z"),
                              release(3, "v1.0.1", "2026-01-07T12:00:00Z")], END)
        self.assertEqual([d["failed"] for d in result["details"]], [True, False, False])
        self.assertEqual(result["details"][0]["fixed_by_tag_name"], "v1.0.1")

    def test_releases_in_last_seven_days_are_censored(self):
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-20T12:00:00Z"),
                              release(2, "v1.0.1", "2026-01-26T12:00:00Z"),
                              release(3, "v1.1.0", "2026-01-30T12:00:00Z")], END)
        self.assertEqual([d["censored"] for d in result["details"]], [False, True, True])
        self.assertEqual((result["evaluated"], result["failed"], result["censored"]), (1, 1, 2))
        # Uma corretiva censurada ainda serve de correção para a release anterior.
        self.assertEqual(result["change_failure_rate"], 1.0)
        # Publicada exatamente 7 dias antes do fim: tem os 7 dias observados.
        boundary = cfr_entrega([release(1, "v1.0.0", "2026-01-25T23:59:59Z")], END)
        self.assertEqual((boundary["evaluated"], boundary["censored"]), (1, 0))

    def test_only_censored_releases_have_no_rate(self):
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-31T00:00:00Z")], END)
        self.assertEqual((result["evaluated"], result["censored"]), (0, 1))
        self.assertIsNone(result["change_failure_rate"])

    def test_single_release(self):
        result = cfr_entrega([release(1, "v1.0.0", "2026-01-05T12:00:00Z")], END)
        self.assertEqual((result["releases"], result["evaluated"], result["failed"]), (1, 1, 0))
        self.assertEqual(result["change_failure_rate"], 0.0)

    def test_tags_outside_semver_fall_back_to_commits(self):
        result = cfr_entrega([release(1, "2024-05-10", "2026-01-05T12:00:00Z", ["feat: a"]),
                              release(2, "2024-05-12", "2026-01-07T12:00:00Z", ["fix: crash"]),
                              release(3, "2024-05-20", "2026-01-15T12:00:00Z", ["feat: b"])], END)
        self.assertEqual([d["corrective"] for d in result["details"]], [False, True, False])
        self.assertEqual([d["failed"] for d in result["details"]], [True, False, False])

    def test_first_release_uses_previous_tag_outside_window(self):
        result = cfr_entrega([release(1, "v2.0.1", "2026-01-05T12:00:00Z", previous_tag_name="v1.9.0"),
                              release(2, "v2.1.0", "2026-01-06T12:00:00Z")], END)
        self.assertFalse(result["details"][0]["corrective"])
        result = cfr_entrega([release(1, "v2.0.1", "2026-01-05T12:00:00Z")], END)
        self.assertTrue(result["details"][0]["corrective"])

    def test_parallel_lines_compare_and_fail_within_their_own_line(self):
        # Como no kubernetes: patches de v1.34.x e v1.35.x intercalados com v1.36.0.
        result = cfr_entrega([release(1, "v1.35.4", "2026-01-05T10:00:00Z"),
                              release(2, "v1.34.7", "2026-01-05T11:00:00Z"),
                              release(3, "v1.36.0", "2026-01-06T12:00:00Z"),
                              release(4, "v1.36.1", "2026-01-08T12:00:00Z"),
                              release(5, "v1.35.5", "2026-01-20T12:00:00Z")], END)
        details = {d["tag_name"]: d for d in result["details"]}
        self.assertEqual([d["corrective"] for d in result["details"]], [True, True, False, True, True])
        # v1.34.7 seguida por v1.36.1 em 3 dias não falhou: a correção é de outra linha.
        self.assertFalse(details["v1.34.7"]["failed"])
        self.assertFalse(details["v1.35.4"]["failed"])
        self.assertEqual(details["v1.36.0"]["fixed_by_tag_name"], "v1.36.1")
        self.assertEqual(result["failed"], 1)

    def test_minor_after_other_line_is_compared_with_its_own_line(self):
        # Como no vscode: tags v0.44.x de outro produto entre as 1.x.
        result = cfr_entrega([release(1, "1.116.0", "2026-01-05T12:00:00Z"),
                              release(2, "v0.44.1", "2026-01-06T12:00:00Z"),
                              release(3, "1.117.0", "2026-01-07T12:00:00Z"),
                              release(4, "v0.44.2", "2026-01-08T12:00:00Z")], END)
        self.assertEqual([d["corrective"] for d in result["details"]], [False, True, False, True])
        self.assertEqual([d["fixed_by_tag_name"] for d in result["details"]], [None, "v0.44.2", None, None])

    def test_unordered_input_undated_and_empty(self):
        result = cfr_entrega([release(2, "v1.0.1", "2026-01-06T12:00:00Z"),
                              release(3, "v1.0.2", None), None,
                              release(1, "v1.0.0", "2026-01-05T12:00:00Z")], END)
        self.assertEqual([d["tag_name"] for d in result["details"]], ["v1.0.0", "v1.0.1"])
        self.assertEqual((result["releases"], result["ignored_missing_date"], result["failed"]), (4, 2, 1))
        empty = cfr_entrega(None, timestamp(END))
        self.assertEqual((empty["releases"], empty["change_failure_rate"]), (0, None))

    def test_invalid_window_end_raises(self):
        with self.assertRaises(ValueError):
            cfr_entrega([], None)


class ReworkRateTests(unittest.TestCase):
    """Rework rate (RQ 08): corretivas sobre releases avaliáveis, sem janela de 7 dias."""

    def first(self, tag="v1.0.0"):
        return release(1, tag, "2026-01-05T12:00:00Z", comparison_status="no_previous_release")

    def test_repository_without_corrective_releases_is_zero_not_empty(self):
        releases = [self.first(), release(2, "v1.1.0", "2026-01-10T12:00:00Z"),
                    release(3, "v1.2.0", "2026-01-15T12:00:00Z")]
        result = rework_rate(releases)
        self.assertEqual((result["evaluated"], result["corrective"], result["rework_rate"]), (2, 0, 0.0))

    def test_repository_with_only_corrective_releases_is_one(self):
        releases = [self.first("v1.0.1"), release(2, "v1.0.2", "2026-01-10T12:00:00Z"),
                    release(3, "v1.0.3", "2026-01-15T12:00:00Z")]
        result = rework_rate(releases)
        self.assertEqual((result["evaluated"], result["corrective"], result["rework_rate"]), (2, 2, 1.0))

    def test_first_release_of_the_history_is_left_out_and_counted(self):
        # v1.0.1 seria corretiva pelo próprio patch, mas não tem anterior para corrigir.
        releases = [self.first("v1.0.1"), release(2, "v1.1.0", "2026-01-10T12:00:00Z"),
                    release(3, "v1.1.1", "2026-01-15T12:00:00Z"), release(4, "v1.2.0", "2026-01-20T12:00:00Z")]
        result = rework_rate(releases)
        self.assertEqual((result["releases"], result["no_previous"], result["evaluated"]), (4, 1, 3))
        self.assertEqual((result["corrective"], result["rework_rate"]), (1, 1 / 3))

    def test_single_release_has_no_rate_instead_of_zero(self):
        result = rework_rate([self.first()])
        self.assertEqual((result["no_previous"], result["evaluated"], result["rework_rate"]), (1, 0, None))

    def test_no_releases_have_no_rate(self):
        for releases in (None, []):
            result = rework_rate(releases)
            self.assertEqual((result["releases"], result["evaluated"], result["rework_rate"]), (0, 0, None))

    def test_there_is_no_censoring_and_a_late_fix_still_counts(self):
        # v1.1.1 sai a 1 dia do fim da janela e v1.1.0 a 30 dias dela: o CFR (b) censura a
        # primeira e não marca falha na segunda; o rework rate conta a correção do mesmo jeito.
        releases = [self.first(), release(2, "v1.1.0", "2026-01-05T12:00:00Z"),
                    release(3, "v1.1.1", "2026-02-01T12:00:00Z")]
        result = rework_rate(releases)
        self.assertEqual((result["evaluated"], result["corrective"], result["rework_rate"]), (2, 1, 0.5))
        delivery = cfr_entrega(releases, timestamp(END))
        self.assertEqual((delivery["censored"], delivery["failed"]), (1, 0))

    def test_corrective_without_a_failure_before_it_differs_from_the_cfr(self):
        # A correção chega 20 dias depois: o CFR (b) não vê falha, o rework rate vê retrabalho.
        releases = [self.first(), release(2, "v1.1.0", "2026-01-06T12:00:00Z"),
                    release(3, "v1.1.1", "2026-01-26T12:00:00Z")]
        self.assertEqual(rework_rate(releases)["rework_rate"], 0.5)
        self.assertEqual(cfr_entrega(releases, timestamp(END))["failed"], 0)

    def test_undated_releases_are_counted_and_left_out(self):
        # Sem a release sem data, a v1.0.2 é comparada com a v1.0.0 e continua só de patch.
        releases = [self.first(), release(2, "v1.0.1", None), release(3, "v1.0.2", "2026-01-15T12:00:00Z")]
        result = rework_rate(releases)
        self.assertEqual((result["releases"], result["ignored_missing_date"], result["evaluated"]), (3, 1, 1))
        self.assertEqual(result["rework_rate"], 1.0)

    def test_failed_comparison_stays_in_the_denominator_like_the_cfr(self):
        releases = [self.first(), release(2, "v1.1.0", "2026-01-10T12:00:00Z"),
                    release(3, "v1.1.1", "2026-01-15T12:00:00Z", comparison_status="not_found")]
        result = rework_rate(releases)
        self.assertEqual((result["evaluated"], result["corrective"]), (2, 1))

    def test_non_semver_tags_are_decided_by_their_commits(self):
        releases = [self.first("2026-01-05"),
                    release(2, "2026-01-10", "2026-01-10T12:00:00Z", ["fix: crash"]),
                    release(3, "2026-01-15", "2026-01-15T12:00:00Z", ["feat: nova tela"])]
        result = rework_rate(releases)
        self.assertEqual((result["evaluated"], result["corrective"], result["rework_rate"]), (2, 1, 0.5))


if __name__ == "__main__":
    unittest.main()
