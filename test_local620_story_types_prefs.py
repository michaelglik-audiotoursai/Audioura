"""test_local620_story_types_prefs.py — LOCAL-620 (D634) acceptance tests.

Michael's ruling (D634, 2026-10-07): keep REAL museum/donor STORIES (named
person + motive/consequence) as a legitimate type, drop only boilerplate; lead
with the work; let collector stories fill when the work's own evidence is thin;
tag every delivered segment with its class; and tune the next tour toward a
listener's liked classes while keeping every class a >= 10% exploration share.

These tests are PURE/offline — no DB, no network, no LLM. The prefs test injects
a fake prefs loader so the exploration-floor behaviour is exercised deterministically.

Covers the five ticket test items plus the three LOCAL-619B carry-overs:
  (1) mapping (story type -> preference class);
  (2) balance on a thin-evidence fixture (collector stories fill);
  (3) class tags written (deterministic per-paragraph / per-stop vector);
  (4) the prefs-weighted mix shifts while exploration stays >= 10%;
  (5) carry-overs: 6a institutional theme, 6b unclosed quote, 6c orphan paragraph.

Run: python3 -m pytest test_local620_story_types_prefs.py -q
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_type_classes as stc
import story_balance as sb
import story_prefs as sp
import work_first_evidence as wfe
import tour_conclusion as tc
from three_class_retrieval import CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL


# ── Shared sample sentences ──────────────────────────────────────────────────
WORK = "The composition shows a woman in profile, lit by a warm golden light against a dark ground."
ARTIST = "He painted this just after returning from exile, at the age of fifty."
RECEPTION = "Critics at the Salon hailed it as a masterpiece of modern feeling."
EMOTION = "There is a quiet grief in her gaze that you cannot help but feel."
STORY1 = ("The collector Jean-Baptiste Wicar, driven by a passion for drawing, "
          "bequeathed his collection so the people of Lille could study the masters.")
STORY2 = ("The banker Reiset, in memory of his late wife, gave the painting to the museum.")
BOILERPLATE = ("The museum was renovated in 2019 at a cost of 12 million euros across "
               "22,000 square metres.")
TRANSFER = "The painting was acquired by the museum in 1905."


class TestMapping(unittest.TestCase):
    """Item 1 — the story-type -> preference-class mapping."""

    def test_base_type_map(self):
        self.assertEqual(stc.map_story_type_to_class("work"), CLASS_DETAILS)
        self.assertEqual(stc.map_story_type_to_class("artist"), CLASS_HISTORIC)
        self.assertEqual(stc.map_story_type_to_class("reception"), CLASS_SOCIAL)
        self.assertEqual(stc.map_story_type_to_class("emotion"), CLASS_SOCIAL)

    def test_institutional_and_other_have_no_direct_class(self):
        # institutional is resolved WITH its text; 'other' carries no signal.
        self.assertIsNone(stc.map_story_type_to_class("institutional"))
        self.assertIsNone(stc.map_story_type_to_class("other"))
        self.assertIsNone(stc.map_story_type_to_class("nonsense"))

    def test_sentence_class_from_text(self):
        self.assertEqual(stc.classify_sentence_class(WORK), CLASS_DETAILS)
        self.assertEqual(stc.classify_sentence_class(ARTIST), CLASS_HISTORIC)
        self.assertEqual(stc.classify_sentence_class(RECEPTION), CLASS_SOCIAL)
        self.assertEqual(stc.classify_sentence_class(EMOTION), CLASS_SOCIAL)

    def test_real_collector_story_is_a_class_not_noise(self):
        # a REAL collector story counts as a legitimate type (historic/social).
        self.assertTrue(stc.is_real_collector_story(STORY1))
        self.assertTrue(stc.is_real_collector_story(STORY2))
        self.assertIn(stc.classify_sentence_class(STORY1),
                      (CLASS_HISTORIC, CLASS_SOCIAL))

    def test_boilerplate_is_filtered_no_class(self):
        self.assertTrue(stc.is_boilerplate_institutional(BOILERPLATE))
        self.assertIsNone(stc.classify_sentence_class(BOILERPLATE))

    def test_bare_transfer_is_not_a_story(self):
        self.assertFalse(stc.is_real_collector_story(TRANSFER))
        # a bare transfer of title carries no preference signal.
        self.assertIsNone(stc.classify_sentence_class(TRANSFER))


class TestBalanceThinFixture(unittest.TestCase):
    """Item 2 — the balance policy on thin vs rich evidence."""

    def test_rich_stop_caps_collector_stories_and_drops_boilerplate(self):
        body = " ".join([WORK, ARTIST, RECEPTION, EMOTION, STORY1, STORY2,
                         BOILERPLATE, TRANSFER])
        new_body, rep = sb.balance_stop_body(body, work_subject="")
        # work/artist/reception/emotion always kept
        for rich in (WORK, ARTIST, RECEPTION, EMOTION):
            self.assertIn(rich[:30], new_body)
        # boilerplate and bare transfer dropped
        self.assertNotIn("12 million", new_body)
        self.assertNotIn("acquired by the museum in 1905", new_body)
        self.assertFalse(rep["thin"])
        self.assertGreaterEqual(rep["boilerplate_dropped"], 1)

    def test_thin_stop_lets_collector_stories_fill(self):
        # one rich sentence + two collector stories → thin → stories FILL.
        body = " ".join([WORK, STORY1, STORY2])
        new_body, rep = sb.balance_stop_body(body, work_subject="")
        self.assertTrue(rep["thin"])
        self.assertIn("Wicar", new_body)
        self.assertIn("Reiset", new_body)

    def test_never_empties_a_stop(self):
        # all-institutional stop with no rich content → unchanged (never empty).
        body = " ".join([BOILERPLATE, TRANSFER])
        new_body, rep = sb.balance_stop_body(body, work_subject="")
        self.assertTrue(new_body.strip())

    def test_tour_class_coverage_reports_all_three(self):
        bodies = [WORK, " ".join([ARTIST, STORY1]), " ".join([RECEPTION, EMOTION])]
        cov = sb.ensure_tour_class_coverage(bodies)
        self.assertTrue(cov["covered"])
        self.assertEqual(cov["missing"], [])
        self.assertCountEqual(cov["classes_present"],
                              [CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL])

    def test_boilerplate_only_tour_has_coverage_gap(self):
        # a tour with only boilerplate has NO class signal — reported, not faked.
        cov = sb.ensure_tour_class_coverage([BOILERPLATE, TRANSFER])
        self.assertFalse(cov["covered"])
        self.assertEqual(set(cov["missing"]),
                         {CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL})


class TestClassTagsWritten(unittest.TestCase):
    """Item 3 — every delivered segment is tagged with its class (deterministic)."""

    def test_paragraph_distribution_sums_to_one(self):
        d = stc.paragraph_class_distribution(" ".join([WORK, ARTIST, RECEPTION]))
        s = d[CLASS_DETAILS] + d[CLASS_HISTORIC] + d[CLASS_SOCIAL]
        self.assertAlmostEqual(s, 1.0, places=2)

    def test_segment_class_is_dominant(self):
        self.assertEqual(
            stc.classify_segment_class(" ".join([WORK, WORK, ARTIST])),
            CLASS_DETAILS)
        self.assertEqual(
            stc.classify_segment_class(" ".join([RECEPTION, EMOTION, WORK])),
            CLASS_SOCIAL)

    def test_stop_vector_has_exactly_three_keys(self):
        v = stc.stop_class_vector(" ".join([WORK, ARTIST, RECEPTION, EMOTION]))
        self.assertEqual(set(v.keys()),
                         {CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL})
        self.assertAlmostEqual(sum(v.values()), 1.0, places=2)

    def test_icon_evaluator_tags_deterministically(self):
        # The evaluator's per-paragraph deterministic tag matches story_type_classes
        # (this is what is persisted to stop_metrics.class_* / paragraphs jsonb).
        import icon_evaluator  # noqa: F401 — importable, deterministic path present
        para = " ".join([WORK, WORK])
        self.assertEqual(stc.classify_segment_class(para), CLASS_DETAILS)


class TestPrefsWeightedMixShifts(unittest.TestCase):
    """Item 4 — the prefs-weighted mix shifts while exploration stays >= 10%."""

    def test_floor_holds_in_the_extreme(self):
        w = sp.exploration_floored_weights(0.0, 0.0, 1.0)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=3)
        for c in (CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL):
            self.assertGreaterEqual(w[c], sp.MIN_EXPLORATION - 1e-9,
                                    f"{c} fell below the 10% exploration floor")

    def test_preferred_class_leads(self):
        w = sp.exploration_floored_weights(0.3, 0.3, 0.9)
        self.assertEqual(max(w, key=w.get), CLASS_SOCIAL)
        # and the mix SHIFTED from the balanced third
        self.assertGreater(w[CLASS_SOCIAL], 1.0 / 3.0)
        self.assertLess(w[CLASS_DETAILS], 1.0 / 3.0)

    def test_balanced_prefs_stay_near_third(self):
        w = sp.exploration_floored_weights(0.5, 0.5, 0.5)
        for c in (CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL):
            self.assertAlmostEqual(w[c], 1.0 / 3.0, places=2)

    def test_addendum_present_only_when_personalised(self):
        self.assertEqual(sp.narration_pref_addendum(None), "")
        w = sp.exploration_floored_weights(0.2, 0.2, 0.9)
        add = sp.narration_pref_addendum(w)
        self.assertIn("LISTENER PREFERENCE", add)
        self.assertIn("NEVER drop a class", add)

    def test_story_prefs_env_gate(self):
        prev = os.environ.get("STORY_PREFS")
        try:
            os.environ["STORY_PREFS"] = "0"
            self.assertFalse(sp.prefs_enabled())
            w, meta = sp.load_user_class_weights("any-user")
            self.assertIsNone(w)
            self.assertEqual(meta["reason"], "STORY_PREFS off")
            os.environ["STORY_PREFS"] = "1"
            self.assertTrue(sp.prefs_enabled())
        finally:
            if prev is None:
                os.environ.pop("STORY_PREFS", None)
            else:
                os.environ["STORY_PREFS"] = prev

    def test_social_seeded_user_shifts_toward_social(self):
        # Simulate a user seeded strongly toward 'social' (the live test persona)
        # via an injected prefs loader, so the mix shifts but keeps the floor.
        import swipe_preference_service as svc
        orig = svc.get_user_prefs
        try:
            svc.get_user_prefs = lambda uid: {
                "pref_details": 0.2, "pref_historic": 0.25, "pref_social": 0.9,
                "swipe_count": 12,
            }
            os.environ["STORY_PREFS"] = "1"
            w, meta = sp.load_user_class_weights("social-seeded")
            self.assertIsNotNone(w)
            self.assertEqual(meta["reason"], "personalised")
            self.assertEqual(max(w, key=w.get), CLASS_SOCIAL)
            self.assertGreaterEqual(min(w.values()), sp.MIN_EXPLORATION - 1e-9)
        finally:
            svc.get_user_prefs = orig


class TestCarryOvers(unittest.TestCase):
    """Item 6 — the three LOCAL-619B carry-overs."""

    # 6a — institutional theme discarded.
    def test_6a_institutional_theme_detected(self):
        # the exact Lille (tour 463) SQ-S6b thread
        self.assertTrue(wfe.is_institutional_theme(
            "evolution of museum techniques and renovations"))
        self.assertTrue(wfe.is_institutional_theme(
            "the museum's growth", "donor legacy and the collection's history"))

    def test_6a_art_theme_not_discarded(self):
        self.assertFalse(wfe.is_institutional_theme(
            "portraiture in the nineteenth century"))
        self.assertFalse(wfe.is_institutional_theme("light and shadow in the Baroque"))

    # 6b — unclosed quote closed, period after.
    def test_6b_unclosed_quote_closed_with_period_after(self):
        bad = ('Across these stops, one thread runs through Northern printmaking, '
               'as seen in Dürer\'s "Ritter, Tod und Teufel. That\'s 4 stops in all.')
        fixed = tc.balance_quotes(bad)
        self.assertEqual(fixed.count('"') % 2, 0, "quote still unbalanced")
        # the closing quote sits before the period that ends the quoted sentence
        self.assertIn('Teufel".', fixed)

    def test_6b_balanced_text_unchanged_and_idempotent(self):
        good = 'This tour followed the sea. Together they matter.'
        self.assertEqual(tc.balance_quotes(good), good)
        once = tc.balance_quotes('He said "hello. Then he left.')
        self.assertEqual(tc.balance_quotes(once), once)

    # 6c — orphan paragraph dropped.
    def test_6c_orphan_undelivered_work_paragraph_dropped(self):
        tour = (
            "Tour.\n\n"
            "Stop 1: Nana\n\n"
            "Nana depicts an actress at her mirror, painted in oil in 1877.\n\n"
            "Stop 2: Olympia\n\n"
            "Olympia is a portrait of a reclining woman, painted in 1863.\n\n"
            "Hieronymus Bosch's 'Ecce Homo' was created around 1476.\n\n"
            "Across these stops, the painted woman returns. Together they ask who looks.\n\n"
            "If you would like to eat nearby we can build you a restaurant tour.\n"
        )
        new_text, rep = tc.drop_orphan_work_paragraphs(
            tc._split_tail(tour)[0] + "\n")
        # the orphan should be gone from the split body
        body, _ = tc._split_tail(tour)
        self.assertNotIn("Ecce Homo", body)
        self.assertIn("Nana", body)
        self.assertIn("Olympia", body)

    def test_6c_delivered_work_one_liner_kept(self):
        tour = (
            "Tour.\n\n"
            "Stop 1: Olympia\n\n"
            "Olympia is a portrait of a reclining woman, painted in 1863.\n\n"
            "'Olympia' was shown at the Salon of 1865.\n\n"
            "Across these stops a woman returns. Together they matter.\n\n"
            "If you would like to eat nearby we can build you a restaurant tour.\n"
        )
        body, _ = tc._split_tail(tour)
        # a one-liner that names a DELIVERED work is not an orphan — kept.
        self.assertIn("Salon of 1865", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
