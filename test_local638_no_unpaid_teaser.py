#!/usr/bin/env python3
"""test_local638_no_unpaid_teaser.py — LOCAL-638 Note 2.

Michael listened to Frick tour 523 (D640):
    "It ends with 'unexpected details hint at the deeper stories beneath the calm';
     I wish it says something about these deeper stories."

A stop must not end on an UNPAID teaser — a closing gesture at a story the stop
never tells ("deeper stories", "hint at", "more to discover", "secrets",
"beneath the calm", "waiting to be discovered"). The editor (LOCAL-628) must
DELIVER the story the teaser points to (from the stop's own sources — the prompt
asks for it) or DROP the teaser. This is in the editor prompt and its validation,
and in a universal text-level delivery guard for the cache/pool/by-reference paths.

Run: python3 -m pytest test_local638_no_unpaid_teaser.py -q
"""
import os
import unittest

import stop_editor as se


# The exact 523 ending.
_UNPAID = ("Holbein painted Sir Thomas More in 1527. The portrait is rendered with "
           "extraordinary precision. Its unexpected details hint at the deeper "
           "stories beneath the calm.")

# A paid version: the final sentence names a concrete fact (a consequence), so it
# DELIVERS rather than merely gestures.
_PAID = ("Holbein painted Sir Thomas More in 1527. More refused to acknowledge "
         "Henry the Eighth as head of the Church, and was executed in 1535 — a "
         "consequence the portrait's steady gaze now seems to foretell.")


class TestDetector(unittest.TestCase):
    def test_detects_unpaid_teaser(self):
        self.assertTrue(se.ends_on_unpaid_teaser(_UNPAID))

    def test_paid_consequence_is_not_flagged(self):
        self.assertFalse(se.ends_on_unpaid_teaser(_PAID))

    def test_no_teaser_phrase_not_flagged(self):
        self.assertFalse(se.ends_on_unpaid_teaser(
            "Holbein painted Sir Thomas More in 1527."))

    def test_secrets_with_concrete_payoff_kept(self):
        # Names a year and a cause in the same sentence → delivered, not a teaser.
        self.assertFalse(se.ends_on_unpaid_teaser(
            "The frame hid a secret compartment, which held a 1527 letter from More."))


class TestDrop(unittest.TestCase):
    def test_drops_only_the_teaser_sentence(self):
        new, did = se.drop_unpaid_teaser(_UNPAID)
        self.assertTrue(did)
        self.assertNotIn("deeper stories", new)
        self.assertIn("Holbein painted Sir Thomas More in 1527", new)
        self.assertIn("extraordinary precision", new)
        # New ending is a real sentence it told.
        self.assertFalse(se.ends_on_unpaid_teaser(new))

    def test_paid_body_unchanged(self):
        new, did = se.drop_unpaid_teaser(_PAID)
        self.assertFalse(did)
        self.assertEqual(new, _PAID)

    def test_idempotent(self):
        once, _ = se.drop_unpaid_teaser(_UNPAID)
        twice, did2 = se.drop_unpaid_teaser(once)
        self.assertFalse(did2)
        self.assertEqual(twice, once)


class TestPromptCarriesTheRule(unittest.TestCase):
    def test_prompt_mentions_unpaid_teaser_deliver_or_drop(self):
        p = se.build_editor_prompt("Sir Thomas More", _UNPAID)
        low = p.lower()
        self.assertIn("teaser", low)
        self.assertIn("deliver", low)
        # It names the forbidden gesture vocabulary.
        self.assertIn("deeper stories", low)


class TestTextLevelGuard(unittest.TestCase):
    """The universal delivery guard drops a trailing unpaid teaser from every stop
    body (works even when the editor is disabled)."""

    _TOUR = """Step-by-step audio guided tour of The Frick Collection, museum tour.

Stop 1: Sir Thomas More

Holbein painted Sir Thomas More in 1527. Its unexpected details hint at the deeper stories beneath the calm.

Directions: Continue to St. Francis in the Desert.

Stop 2: St. Francis in the Desert

Bellini shows St. Francis in the morning light. There is more to discover here.

That's 2 stops in all.
"""

    def test_guard_drops_teasers_from_bodies(self):
        fixed, n = se.strip_unpaid_teaser_in_text(self._TOUR)
        self.assertEqual(n, 2)
        self.assertNotIn("deeper stories beneath the calm", fixed)
        self.assertNotIn("more to discover", fixed)

    def test_guard_preserves_directions_and_conclusion(self):
        fixed, _ = se.strip_unpaid_teaser_in_text(self._TOUR)
        self.assertIn("Directions: Continue to St. Francis in the Desert.", fixed)
        self.assertIn("That's 2 stops in all.", fixed)
        self.assertIn("Holbein painted Sir Thomas More in 1527.", fixed)
        self.assertIn("Bellini shows St. Francis in the morning light.", fixed)

    def test_guard_idempotent(self):
        once, _ = se.strip_unpaid_teaser_in_text(self._TOUR)
        twice, n2 = se.strip_unpaid_teaser_in_text(once)
        self.assertEqual(n2, 0)
        self.assertEqual(twice, once)


class TestEditStopDropsTeaser(unittest.TestCase):
    """edit_stop applies the deterministic drop when the LLM edit still ends on an
    unpaid teaser, and when the edit is rejected the original's teaser is dropped."""

    _BLOCK = """Stop 1: Sir Thomas More

Orientation: You are in the West Gallery.

Holbein painted Sir Thomas More in 1527. Its unexpected details hint at the deeper stories beneath the calm.

Directions: Continue to St. Francis in the Desert.
"""

    def setUp(self):
        os.environ["STOP_EDITOR_ENABLED"] = "1"

    def test_llm_edit_still_teasing_gets_trimmed(self):
        # Fake LLM returns the body unchanged (still ends on the teaser).
        def _echo(prompt, api_key):
            # Return just the body portion (after STOP BODY:) unchanged.
            return ("Holbein painted Sir Thomas More in 1527. Its unexpected "
                    "details hint at the deeper stories beneath the calm.")
        new_block, edited, reason = se.edit_stop(
            self._BLOCK, stop_number=1, venue_name="The Frick Collection",
            llm_fn=_echo, api_key="sk-test")
        self.assertTrue(edited)
        self.assertNotIn("deeper stories beneath the calm", new_block)
        # Orientation and Directions preserved.
        self.assertIn("Orientation: You are in the West Gallery.", new_block)
        self.assertIn("Directions: Continue to St. Francis in the Desert.", new_block)

    def test_rejected_edit_still_drops_original_teaser(self):
        # Fake LLM returns empty → edit rejected → original body ships, teaser-free.
        def _empty(prompt, api_key):
            return ""
        new_block, edited, reason = se.edit_stop(
            self._BLOCK, stop_number=1, venue_name="The Frick Collection",
            llm_fn=_empty, api_key="sk-test")
        self.assertNotIn("deeper stories beneath the calm", new_block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
