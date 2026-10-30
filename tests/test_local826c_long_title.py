"""test_local826c_long_title.py — LOCAL-826C.

The Rijksmuseum "Merry Drinker" stop lost its body and shipped as "This stop".

Root cause (LEAD, Mac, 826B code, real cache — tour866_v2.txt / gen_rijks_v2.log):
LOCAL-791B composed a 21-word bilingual title

    A Militiaman Holding a Berkemeyer, Known as the 'Merry Drinker'
    (Een schutter die een berkenmeier vasthoudt, bekend als 'De vrolijke drinker')

(log ~2603). The downstream F3 corruption guard (_F3_MAX_TITLE_WORDS = 15)
word-truncated it at [:12] into the fragment "…(Een schutter" (log ~4005); that
fragment became a headerless orphan body, and 826B's de-splice promotion titled
the lost-header stop "This stop" (delivered: "Continue to This stop." /
"Stop 3: This stop").

Three layers are proven here with the EXACT strings:
  1. SOURCE — the title is capped (English name kept, over-long local gloss
     dropped) so a 150-char header never reaches F3, and the F3 shortener drops
     the gloss instead of word-cutting a real title into a fragment.
  2. PROMOTION — a title-fragment orphan is never promoted; a lost-header stop is
     never titled "This stop"/"Next stop".
  3. DELIVERY — check_stop_delivery reports PLACEHOLDER_TITLE and FRAGMENT_BODY.

Pure/offline/deterministic. No network, no model.

Run:
    python3 -m pytest tests/test_local826c_long_title.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The EXACT strings from the ticket / log (curly quotes U+2018/U+2019 preserved).
_EN = "A Militiaman Holding a Berkemeyer, Known as the \u2018Merry Drinker\u2019"
_LOCAL = ("Een schutter die een berkenmeier vasthoudt, bekend als "
          "\u2018De vrolijke drinker\u2019")
_FULL_791B = f"{_EN} ({_LOCAL})"              # the 21-word bilingual title (log ~2603)
_F3_FRAGMENT = "A Militiaman Holding a Berkemeyer, Known as the \u2018Merry Drinker\u2019 (Een schutter"


# ───────────────────────── 1. SOURCE: title cap + F3 shortener ────────────────
class TestTitleCappedAtSource(unittest.TestCase):
    def test_full_bilingual_title_is_21_words(self):
        # Pin the exact failing length so the ticket's root cause is documented.
        self.assertEqual(len(_FULL_791B.split()), 21)

    def test_format_place_title_drops_long_local_gloss(self):
        from place_title_naming import format_place_title
        got = format_place_title(_EN, _LOCAL)
        # The English title alone — a complete, recognisable name. No "(Een …".
        self.assertEqual(got, _EN)
        self.assertNotIn("(", got)

    def test_short_bilingual_title_keeps_the_gloss(self):
        from place_title_naming import format_place_title
        # A SHORT local gloss is still shown (no regression to LOCAL-791B).
        self.assertEqual(
            format_place_title("Jade Emperor Pagoda", "Ch\u00f9a Ng\u1ecdc Ho\u00e0ng"),
            "Jade Emperor Pagoda (Ch\u00f9a Ng\u1ecdc Ho\u00e0ng)")

    def test_title_for_candidate_caps_serper_bilingual(self):
        from place_title_naming import title_for_candidate
        cand = {"name": _FULL_791B, "serper_title": _EN, "label_local": _LOCAL}
        self.assertEqual(title_for_candidate(cand, "en"), _EN)

    def test_shorten_long_title_drops_gloss_never_word_cuts(self):
        from place_title_naming import shorten_long_title
        got = shorten_long_title(_FULL_791B)
        self.assertEqual(got, _EN)
        # NEVER the F3 word-truncation fragment.
        self.assertNotEqual(got, _F3_FRAGMENT)
        self.assertFalse(got.endswith("(Een schutter"))

    def test_shortened_title_is_f3_safe(self):
        from place_title_naming import shorten_long_title
        from generate_tour_text import f3_name_is_corrupt
        got = shorten_long_title(_FULL_791B)
        # The shortened title passes the F3 ceiling → F3 never fires on it again.
        self.assertFalse(f3_name_is_corrupt(got, verified=True))

    def test_shorten_leaves_short_title_unchanged(self):
        from place_title_naming import shorten_long_title
        for t in ("The Night Watch", "Het melkmeisje (The Milkmaid)",
                  "De grote golf bij Kanagawa (The Great Wave off Kanagawa)"):
            self.assertEqual(shorten_long_title(t), t)

    def test_f3_truncation_fragment_was_the_old_bug(self):
        # Document that the OLD behaviour (' '.join(split()[:12])) produced the
        # exact fragment seen in the delivered tour, so the regression is pinned.
        old = " ".join(_FULL_791B.split()[:12]).rstrip(".,;:!?")
        self.assertEqual(old, _F3_FRAGMENT)

    def test_bilingual_display_title_caps_long_pair(self):
        from identity_dedup import bilingual_display_title
        cand = {"label_en": _EN, "label_local": _LOCAL}
        got = bilingual_display_title(cand)
        # Ship ONE complete title (the English/ASCII side), never the long pair.
        self.assertEqual(got, _EN)
        self.assertNotIn("(Een schutter", got)

    def test_bilingual_display_title_keeps_short_pair(self):
        from identity_dedup import bilingual_display_title
        cand = {"label_en": "The Milkmaid", "label_local": "Het melkmeisje"}
        got = bilingual_display_title(cand)
        self.assertIn("The Milkmaid", got)
        self.assertIn("Het melkmeisje", got)


# ───────────────────────── 2. PROMOTION never ships "This stop" ───────────────
class TestPromotionNeverPlaceholder(unittest.TestCase):
    def test_title_fragment_orphan_is_not_a_body(self):
        from stop_dedup_collision_guard import (_orphan_is_title_fragment,
                                                _orphan_has_narration_body)
        frag = f"\n{_F3_FRAGMENT}\n"
        self.assertTrue(_orphan_is_title_fragment(frag))
        self.assertFalse(_orphan_has_narration_body(frag))

    def test_real_narration_orphan_still_promotes_with_real_handoff(self):
        from stop_dedup_collision_guard import (_orphan_has_narration_body,
                                                _promote_orphan_to_stop)
        body = ("\nCoordinates: 52.3592, 4.8852\n\n"
                "Orientation: Stand close to observe the militiaman.\n\n"
                "Frans Hals painted the Merry Drinker around 1628 to 1630, "
                "capturing a convivial moment. The loose brushwork conveys "
                "spontaneity and warmth.\n")
        self.assertTrue(_orphan_has_narration_body(body))
        got = _promote_orphan_to_stop(body, _EN)
        self.assertIsNotNone(got)
        self.assertTrue(got.startswith(f"Stop 0: {_EN}"))

    def test_placeholder_handoff_refuses_to_promote(self):
        from stop_dedup_collision_guard import _promote_orphan_to_stop
        body = ("\nOrientation: Stand close to observe the militiaman. "
                "Frans Hals painted the Merry Drinker around 1628.\n")
        for cue in ("This stop", "this stop", "Next stop", "the next stop", ""):
            self.assertIsNone(_promote_orphan_to_stop(body, cue),
                              f"promoted under placeholder cue {cue!r}")

    def test_is_placeholder_title(self):
        from stop_dedup_collision_guard import _is_placeholder_title
        for t in ("This stop", "this stop.", "Next stop", "the next stop", ""):
            self.assertTrue(_is_placeholder_title(t))
        for t in (_EN, "The Night Watch", "Jade Emperor Pagoda"):
            self.assertFalse(_is_placeholder_title(t))

    def test_end_to_end_glued_orphan_never_titled_this_stop(self):
        """The real failure shape: a Directions hand-off degraded to the
        placeholder 'This stop' (the title was truncated upstream), followed by a
        headerless orphan body. normalise_stop_headers must NOT ship a stop titled
        'This stop' — the orphan is dropped and survivors renumber sequentially."""
        from tour_conclusion import (normalise_stop_headers, check_stop_delivery,
                                     count_delivered_stops)
        glued = (
            "Step-by-Step Audio Guided Tour: Rijks Museum, Amsterdam, Netherlands\n"
            "Tour-Category: museum\n\n"
            "Stop 1: De Nachtwacht (The Night Watch)\n\n"
            "Coordinates: 52.3659, 4.8852\n\n"
            "Orientation: Stand back from The Night Watch. Rembrandt finished it in 1642.\n\n"
            "Directions: Continue to This stop.\n\n"
            "Coordinates: 52.3592, 4.8852\n\n"
            "Orientation: Stand close to observe the militiaman holding his glass.\n\n"
            "Frans Hals painted the Merry Drinker around 1628 to 1630. The loose "
            "brushwork conveys spontaneity.\n\n"
            "Directions: Your final stop in Rijksmuseum: De grote golf bij Kanagawa "
            "(The Great Wave off Kanagawa).\n\n"
            "Stop 3: De grote golf bij Kanagawa (The Great Wave off Kanagawa)\n\n"
            "Coordinates: 52.3592, 4.8852\n\n"
            "Orientation: Stand close to the print. Hokusai made it in 1831.\n\n"
            "Sources: x.\n")
        out = normalise_stop_headers(glued)
        self.assertNotIn("Stop 2: This stop", out)
        self.assertNotIn(": This stop", out)
        self.assertEqual(check_stop_delivery(out), [])
        # Sequentially numbered survivors (the placeholder orphan is dropped).
        import re
        nums = [int(m.group(1)) for m in re.finditer(r'(?m)^Stop (\d+):', out)]
        self.assertEqual(nums, list(range(1, len(nums) + 1)))


# ───────────────────────── 3. DELIVERY check reports the defects ──────────────
class TestDeliveryCheckNewViolations(unittest.TestCase):
    def test_delivered_tour866_v2_flags_placeholder_title(self):
        """The EXACT delivered evidence (tour866_v2.txt) must be caught: Stop 3 is
        titled 'This stop'. Skips cleanly if the LEAD report is not on this box."""
        from tour_conclusion import check_stop_delivery
        path = os.path.expanduser("~/Audioura/reports/local826c/tour866_v2.txt")
        if not os.path.exists(path):
            self.skipTest("LEAD report tour866_v2.txt not present on this machine")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        viol = check_stop_delivery(text)
        self.assertTrue(any(v.startswith("PLACEHOLDER_TITLE") for v in viol),
                        f"expected PLACEHOLDER_TITLE, got {viol}")

    def test_placeholder_title_violation(self):
        from tour_conclusion import check_stop_delivery
        text = (
            "Stop 1: The Night Watch\n\n"
            "Orientation: Look here. Rembrandt painted it in 1642.\n\n"
            "Stop 2: This stop\n\n"
            "Orientation: Stand close. Frans Hals painted it in 1628.\n\n"
            "Sources: x.\n")
        viol = check_stop_delivery(text)
        self.assertIn("PLACEHOLDER_TITLE: Stop 2 is titled 'This stop'", viol)

    def test_fragment_body_violation(self):
        from tour_conclusion import check_stop_delivery
        # A stop whose only prose is the truncated-title fragment (no sentence).
        text = (
            "Stop 1: The Night Watch\n\n"
            "Orientation: Look here. Rembrandt painted it in 1642.\n\n"
            "Stop 2: " + _EN + "\n\n"
            "Coordinates: 52.3592, 4.8852\n\n"
            + _F3_FRAGMENT + "\n\n"
            "Sources: x.\n")
        viol = check_stop_delivery(text)
        self.assertTrue(any(v.startswith("FRAGMENT_BODY: Stop 2") for v in viol),
                        f"expected FRAGMENT_BODY for Stop 2, got {viol}")

    def test_well_formed_tour_has_no_new_violations(self):
        from tour_conclusion import check_stop_delivery
        text = (
            "Stop 1: The Night Watch\n\n"
            "Orientation: Stand back. Rembrandt finished it in 1642.\n\n"
            "Stop 2: " + _EN + "\n\n"
            "Orientation: Stand close. Frans Hals painted it around 1628.\n\n"
            "Sources: x.\n")
        self.assertEqual(check_stop_delivery(text), [])

    def test_terse_single_sentence_body_is_not_a_fragment(self):
        """The 826B contract: a terse but COMPLETE single sentence is a valid
        body (FRAGMENT_BODY must not regress it)."""
        from tour_conclusion import check_stop_delivery
        text = (
            "Stop 1: A\n\n"
            "Orientation: look at A.\n\n"
            "Stop 2: B\n\n"
            "Orientation: look at B.\n\n"
            "Sources: x.\n")
        self.assertEqual(check_stop_delivery(text), [])

    def test_corrupt_rijks_fixture_still_caught(self):
        """The 826B corrupt fixture (two Stop 4 headers) is still reported."""
        from tour_conclusion import check_stop_delivery
        fx = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "fixtures", "local826b", "tour866_corrupt_rijks.txt")
        if not os.path.exists(fx):
            self.skipTest("826B corrupt fixture not present")
        with open(fx, encoding="utf-8") as f:
            viol = check_stop_delivery(f.read())
        self.assertTrue(any(v.startswith("DUPLICATE_NUMBER") for v in viol))
        self.assertTrue(any(v.startswith("NON_SEQUENTIAL") for v in viol))


if __name__ == "__main__":
    unittest.main()
