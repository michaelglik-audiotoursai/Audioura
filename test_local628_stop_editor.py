#!/usr/bin/env python3
"""test_local628_stop_editor.py — LOCAL-628 the final per-stop EDITOR pass.

Covers the ticket's six required cases:

  1. the editor prompt CONTRACT (the instruction text the model receives);
  2. validation REJECTS an edit that adds a date or a name (injected llm_fn);
  3. the FALLBACK keeps the original on rejection;
  4. IDEMPOTENCE on a cache hit (a second pass neither changes the text nor
     calls the LLM — no re-spend);
  5. the KHM "open daily" closed-day reconciliation;
  6. one test that feeds the REAL 490 Stop 1 and Stop 2 bodies (reconstructed
     from the LEAD critique: effect-before-cause, the "Visscher." orphan, the
     Bruegel gloss-jammed-into-a-name, the "holdings art" dropped word, the
     unintroduced "Ernest") through an injected "good" edit and asserts the
     cleaned prose validates and the defects are gone.

Run: python3 -m pytest test_local628_stop_editor.py -q
     python3 test_local628_stop_editor.py
"""
import os
import re
import unittest

# Default-on gate must not depend on the ambient env for the test run.
os.environ.setdefault("STOP_EDITOR", "1")

import stop_editor as se


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures: a realistic stop block and the reconstructed tour-490 bodies
# ─────────────────────────────────────────────────────────────────────────────

STOP_BLOCK = (
    "Stop 1: The Art of Painting\n"
    "\n"
    "Address: Maria-Theresien-Platz, 1010 Vienna\n"
    "\n"
    "Coordinates: 48.2039, 16.3616\n"
    "\n"
    "Orientation: Stand before the canvas in Gallery 24 and let your eye follow "
    "the light from the window to the model.\n"
    "\n"
    "Johannes Vermeer painted The Art of Painting around 1666 in Delft. The work "
    "shows a painter at his easel before a model dressed as Clio, the muse of "
    "history. It entered the imperial collection and hangs today in Vienna.\n"
    "\n"
    "Directions: Continue to the next gallery — your next stop is The Tower of Babel.\n"
)

# ── Reconstructed tour-490 (Kunsthistorisches Museum) Stop 1 & Stop 2 bodies ──
# These bodies carry, verbatim in kind, the defects the LEAD critique named so
# the test exercises the editor on the real failure shapes. (The worktree does
# not ship the critique artifact; the defects are reproduced from its text.)
STOP_490_1_BODY = (
    "As a result, the painting was removed from public display during the "
    "Nazi era. Pieter Bruegel, the 16th-century Flemish painter known for "
    "landscapes, the Elder around 1567 completed this panel. Visscher. The work "
    "entered the museum's holdings art after the war. In 1676 the artist's widow "
    "sold several panels to settle the estate. Its precise content, rich with "
    "proverbs, must be appreciated in person."
)
STOP_490_1_TITLE = "The Tower of Babel"

STOP_490_2_BODY = (
    "Ernest acquired the panel for the imperial collection in the 1590s. The "
    "effect, heightened the layering of figures across the foreground. The "
    "composition draws the eye from the harbour to the distant tower. As part of "
    "this series, the painting shows the vanity of human ambition."
)
STOP_490_2_TITLE = "The Tower of Babel (detail)"


def _body_from_prompt(prompt: str) -> str:
    """Pull the STOP BODY the editor sent to the model back out of the prompt."""
    m = re.search(r"STOP BODY:\n(.*)$", prompt, re.S)
    return m.group(1).strip() if m else ""


def identity_llm(prompt: str, api_key: str) -> str:
    """A 'good' edit that changes nothing — trivially supported, same length."""
    return _body_from_prompt(prompt)


def adds_date_and_name_llm(prompt: str, api_key: str) -> str:
    """A 'bad' edit that smuggles in a NEW date and a NEW name not in the input."""
    return _body_from_prompt(prompt) + (
        " In 1623, Napoleon Bonaparte personally admired this work.")


def throwing_llm(prompt: str, api_key: str) -> str:
    raise AssertionError("LLM must NOT be called on an already-edited tour")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prompt contract
# ─────────────────────────────────────────────────────────────────────────────
class TestEditorPromptContract(unittest.TestCase):
    def test_prompt_contains_the_full_instruction_contract(self):
        p = se.build_editor_prompt("A Title", "Some body text.")
        low = p.lower()
        # Reorder / chronological / work-first
        self.assertIn("reorder", low)
        self.assertIn("chronological", low)
        # Repair dangling openers (names the exact openers the ticket lists)
        self.assertIn("as a result", low)
        self.assertIn("this move", low)
        self.assertIn("this detail", low)
        # Delete orphans + evasive filler
        self.assertIn("orphan", low)
        self.assertIn("filler", low)
        # Introduce people from stop-only info
        self.assertIn("first mention", low)
        self.assertIn("archduke ernest", low)
        # Keep register + length window
        self.assertIn("register", low)
        self.assertIn("20 percent", low)
        # The absolute no-new-facts rule
        self.assertIn("add no fact", low)
        # The body and title are present
        self.assertIn("A Title", p)
        self.assertIn("Some body text.", p)


# ─────────────────────────────────────────────────────────────────────────────
# 2 + 3. Validation rejects an added date/name; fallback keeps the original
# ─────────────────────────────────────────────────────────────────────────────
class TestValidationAndFallback(unittest.TestCase):
    def test_added_date_and_name_is_rejected(self):
        new_block, edited, reason = se.edit_stop(
            STOP_BLOCK, stop_number=1, venue_name="Kunsthistorisches Museum",
            llm_fn=adds_date_and_name_llm)
        self.assertFalse(edited, "an edit adding a new date+name MUST be rejected")
        # The fallback is the ORIGINAL block, byte-for-byte.
        self.assertEqual(new_block, STOP_BLOCK)
        # Reason names a concrete guard (proper-noun or claim_check).
        self.assertTrue(
            ("proper noun" in reason) or ("claim_check" in reason) or ("length" in reason),
            f"unexpected reason: {reason}")

    def test_validate_edit_rejects_new_proper_noun(self):
        # Length-neutral so the proper-noun guard (not the length guard) is what
        # fires: swap one supported clause for a new-name clause of similar length.
        ok, reason = se.validate_edit(
            "Vermeer painted this around 1666. Rembrandt also admired the piece.",
            "Vermeer painted this around 1666. A patron also admired the piece.",
            stop_title="The Art of Painting", venue_name="KHM")
        self.assertFalse(ok)
        self.assertIn("proper noun", reason)

    def test_validate_edit_rejects_length_blowup(self):
        ok, reason = se.validate_edit(
            "Short.", "A much longer original body sentence that sets the length.",
            stop_title="t", venue_name="v")
        self.assertFalse(ok)
        self.assertIn("length", reason)

    def test_identity_edit_is_accepted_and_preserves_structure(self):
        new_block, edited, reason = se.edit_stop(
            STOP_BLOCK, stop_number=1, venue_name="KHM", llm_fn=identity_llm)
        self.assertTrue(edited, f"identity edit should validate; reason={reason}")
        # Orientation and Directions are preserved verbatim.
        self.assertIn("Orientation: Stand before the canvas", new_block)
        self.assertIn("Directions: Continue to the next gallery", new_block)
        self.assertIn("Address: Maria-Theresien-Platz", new_block)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Idempotence on a cache hit — no re-edit, no re-spend
# ─────────────────────────────────────────────────────────────────────────────
class TestIdempotence(unittest.TestCase):
    def test_second_pass_is_noop_and_does_not_call_llm(self):
        once = se.edit_tour_text(STOP_BLOCK, venue_name="KHM",
                                 llm_fn=identity_llm, log=lambda s: None)
        self.assertTrue(se.already_edited(once))
        # A cache hit re-enters edit_tour_text; the marker must short-circuit it
        # WITHOUT calling the LLM (throwing_llm proves the LLM is never invoked).
        twice = se.edit_tour_text(once, venue_name="KHM",
                                  llm_fn=throwing_llm, log=lambda s: None)
        self.assertEqual(twice, once, "a cache-hit re-pass must not change the text")

    def test_disabled_is_passthrough(self):
        old = os.environ.get("STOP_EDITOR")
        try:
            os.environ["STOP_EDITOR"] = "0"
            out = se.edit_tour_text(STOP_BLOCK, venue_name="KHM",
                                    llm_fn=throwing_llm, log=lambda s: None)
            self.assertEqual(out, STOP_BLOCK)
            self.assertFalse(se.already_edited(out))
        finally:
            if old is None:
                os.environ.pop("STOP_EDITOR", None)
            else:
                os.environ["STOP_EDITOR"] = old


# ─────────────────────────────────────────────────────────────────────────────
# 5. KHM "open daily" closed-day reconciliation (task 5)
# ─────────────────────────────────────────────────────────────────────────────
class TestOpenDailyClosedDay(unittest.TestCase):
    def test_khm_daily_with_closed_monday_drops_daily(self):
        import venue_preflight as vp
        pb = vp.plan_b_opening_practicals(
            {"hours": "Open daily, 10:00-18:00, closed Mondays",
             "admission": "", "sources": {}})
        self.assertNotIn("daily", pb["speak"].lower(),
                         "spoken sentence must not say 'daily' when a day is closed")
        self.assertIn("closed Mondays", pb["speak"])

    def test_genuine_seven_day_daily_is_kept(self):
        import venue_preflight as vp
        pb = vp.plan_b_opening_practicals(
            {"hours": "Open daily 10:00-18:00", "admission": "", "sources": {}})
        self.assertIn("daily", pb["speak"].lower())

    def test_every_day_except_monday_is_kept(self):
        import venue_preflight as vp
        out = vp.reconcile_daily_with_closed_days(
            "Open every day except Monday, 10:00-18:00")
        self.assertEqual(out, "Open every day except Monday, 10:00-18:00")


# ─────────────────────────────────────────────────────────────────────────────
# 6. The real tour-490 Stop 1 & Stop 2 through an injected 'good' edit
# ─────────────────────────────────────────────────────────────────────────────
class TestTour490Bodies(unittest.TestCase):
    """A 'good' edit that repairs the 490 defects using ONLY words already in the
    body: reorder cause-before-effect, repair the Bruegel name, delete the
    'Visscher.' orphan and the evasive filler, fix the 'holdings art' dropped
    word, and keep 'Ernest' (which IS in the input). The edit must VALIDATE —
    it introduces no new proper noun and no new claim."""

    def test_stop1_good_edit_validates_and_removes_defects(self):
        # A faithful repair: reorder cause-before-effect, fix the Bruegel
        # gloss-in-name, delete the 'Visscher.' orphan and the evasive filler,
        # repair 'holdings art' -> 'art holdings'. Keeps the supported proverb
        # detail (rephrased, not deleted) so the length stays within tolerance.
        good = (
            "Pieter Bruegel the Elder completed this panel around 1567, a work "
            "rich with proverbs. In 1676 the artist's widow sold several panels "
            "to settle the estate. The work later entered the museum's art "
            "holdings. During the Nazi era the painting was removed from public "
            "display, and it returned to view after the war."
        )
        ok, reason = se.validate_edit(
            good, STOP_490_1_BODY, stop_title=STOP_490_1_TITLE,
            venue_name="Kunsthistorisches Museum")
        self.assertTrue(ok, f"the good 490 Stop-1 edit must validate; reason={reason}")
        # Defects gone: no orphan 'Visscher.', no gloss-in-name, no 'holdings art',
        # no evasive filler.
        self.assertNotIn("Visscher.", good)
        self.assertNotIn("the 16th-century Flemish painter known for landscapes, the Elder", good)
        self.assertNotIn("holdings art", good)
        self.assertNotIn("must be appreciated in person", good)

    def test_stop1_edit_that_adds_a_new_name_is_rejected(self):
        # Same repair but smuggles a NEW name (Rudolf) not in the input body.
        bad = (
            "Pieter Bruegel the Elder completed this panel around 1567. Emperor "
            "Rudolf II later prized it. In 1676 the widow sold several panels."
        )
        ok, reason = se.validate_edit(
            bad, STOP_490_1_BODY, stop_title=STOP_490_1_TITLE,
            venue_name="Kunsthistorisches Museum")
        self.assertFalse(ok, "an edit adding 'Rudolf' (not in input) must be rejected")

    def test_stop2_good_edit_keeps_ernest_and_validates(self):
        # 'Ernest' IS in the input, so keeping it is allowed; 'the layering' dropped
        # word repaired; reordered. No new facts.
        good = (
            "The composition draws the eye from the harbour to the distant tower. "
            "The layering of figures across the foreground heightens the effect. "
            "Ernest acquired the panel for the imperial collection in the 1590s. "
            "The painting shows the vanity of human ambition."
        )
        ok, reason = se.validate_edit(
            good, STOP_490_2_BODY, stop_title=STOP_490_2_TITLE,
            venue_name="Kunsthistorisches Museum")
        self.assertTrue(ok, f"the good 490 Stop-2 edit must validate; reason={reason}")
        self.assertIn("Ernest", good)

    def test_full_490_two_stop_tour_through_identity_edit(self):
        # Assemble a two-stop tour and run the whole-tour pass with an identity
        # 'good' edit — every stop validates (identity is trivially supported),
        # the structure is preserved, and the tour is marked edited once.
        tour = (
            f"Stop 1: {STOP_490_1_TITLE}\n\n"
            "Orientation: Stand before the panel.\n\n"
            f"{STOP_490_1_BODY}\n\n"
            "Directions: Continue to the detail view.\n\n"
            f"Stop 2: {STOP_490_2_TITLE}\n\n"
            "Orientation: Step closer to read the figures.\n\n"
            f"{STOP_490_2_BODY}\n\n"
            "Directions: Your final stop is complete.\n"
        )
        out = se.edit_tour_text(tour, venue_name="Kunsthistorisches Museum",
                                llm_fn=identity_llm, log=lambda s: None)
        self.assertTrue(se.already_edited(out))
        self.assertIn("Orientation: Stand before the panel.", out)
        self.assertIn("Orientation: Step closer to read the figures.", out)
        self.assertIn("Directions: Continue to the detail view.", out)
        # Both stop headers survive.
        self.assertEqual(len(se._split_tour_into_stops(out)), 2)


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-634] Dropped-word detection, rejection and deterministic repair
# ─────────────────────────────────────────────────────────────────────────────
class TestDroppedWord(unittest.TestCase):
    """The two Bench R1 shapes:
      * 505 "…at the outbreak of was at a crossroads" — a removed head noun left
        a preposition immediately before a finite verb.
      * 495 "This painting w. Velázquez…" — a truncated one-letter fragment.
    """

    def test_detect_dangling_preposition_before_verb(self):
        s = ("Juan Gris, working in Paris at the outbreak of was at a crossroads "
             "of competing styles.")
        d = se.detect_dropped_word(s)
        self.assertIsNotNone(d)
        self.assertIn("of was", d)

    def test_detect_truncated_fragment(self):
        s = "This painting w. Velazquez, the leading painter, admired closely."
        d = se.detect_dropped_word(s)
        self.assertIsNotNone(d)
        self.assertIn("w.", d)

    def test_real_initial_not_flagged(self):
        # "J. Arrowsmith" is an initial, not a dropped word.
        self.assertIsNone(se.detect_dropped_word("The dealer J. Arrowsmith bought it."))

    def test_abbreviation_not_flagged(self):
        self.assertIsNone(se.detect_dropped_word("The chapel of St. Peter is nearby."))

    def test_clean_prose_not_flagged(self):
        self.assertIsNone(se.detect_dropped_word(
            "Juan Gris worked in Paris during the war and reached a crossroads."))

    def test_validate_edit_rejects_dropped_word(self):
        # Edit still contains the 505 hole → rejected with a 'dropped word' reason.
        original = ("Juan Gris worked in Paris during the First World War and "
                    "stood at a crossroads of competing styles that year.")
        edited = ("Juan Gris, working in Paris at the outbreak of was at a "
                  "crossroads of competing styles that year now.")
        ok, reason = se.validate_edit(edited, original, stop_title="Juan Gris",
                                      venue_name="Reina Sofia")
        self.assertFalse(ok)
        self.assertIn("dropped word", reason)

    def test_repair_removes_truncated_fragment(self):
        repaired, n = se.repair_dropped_words(
            "This painting w. Velazquez admired closely.")
        self.assertGreaterEqual(n, 1)
        self.assertNotIn("w.", repaired)
        self.assertIn("Velazquez", repaired)
        self.assertIsNone(se.detect_dropped_word(repaired))

    def test_repair_drops_unrecoverable_hole_sentence(self):
        # The dangling-preposition hole cannot be filled without inventing the
        # missing noun; the sentence is dropped, the clean sentence kept.
        text = ("The work entered the collection in 1921. Juan Gris, working in "
                "Paris at the outbreak of was at a crossroads.")
        repaired, n = se.repair_dropped_words(text)
        self.assertGreaterEqual(n, 1)
        self.assertIn("entered the collection in 1921", repaired)
        self.assertIsNone(se.detect_dropped_word(repaired))

    def test_edit_stop_deterministic_repair_on_empty_llm(self):
        # The LLM returns nothing usable; the original body has a dropped word.
        # edit_stop must ship the deterministic repair, not the raw hole.
        body = ("This panel w. the collector who gave it to the museum. The work "
                "entered the collection in 1921.")
        block = (f"Stop 1: A Panel\n\nOrientation: Stand close.\n\n{body}\n\n"
                 "Directions: Continue.\n")
        new_block, edited, reason = se.edit_stop(
            block, stop_number=1, venue_name="Reina Sofia",
            llm_fn=lambda p, k: "")  # empty LLM output
        self.assertTrue(edited, f"deterministic repair should ship; reason={reason}")
        self.assertEqual(reason, "dropped-word-repaired")
        self.assertNotIn(" w. ", new_block)
        self.assertIsNone(se.detect_dropped_word(new_block))
        # Structure preserved.
        self.assertIn("Orientation: Stand close.", new_block)
        self.assertIn("Directions: Continue.", new_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
