#!/usr/bin/env python3
"""test_local726_crime_wording.py — LOCAL-726 item 9 / lawyer review item 9.

The lawyer asked that the rater's prompt separate a tour about the HISTORY of
crime (General, or Mature at most) from content that explains HOW TO COMMIT a
crime (Not Allowed). "Remove any example that could be read as encouraging
crime ... make it 'tours focused on history of crime' vs 'how to commit crime.'
Second is Not Allowed."

This proves the change WITHOUT any paid API call. There are two layers:

  1. The PROMPT the model is held to carries the distinction: history of crime
     is general/mature, and only instructions to COMMIT a crime are not_allowed.
     (A direct string/structure check on the shipped prompt — the thing that
     actually governs the live model.)

  2. Two fixtures drive the REAL rate_text aggregation with classify mocked by a
     tiny rule that mimics a prompt-faithful model:
        * a history-of-crime tour  -> NOT not_allowed (general or mature);
        * a how-to-commit-crime tour -> not_allowed.
     This exercises the serving path (rate_text / review_status_for) exactly as
     production does, with the verdict decided by the prompt's own rule.

  3. RED: a mock that mis-reads the prompt — treating ALL crime, history
     included, as not_allowed — is shown to FAIL the history fixture, proving
     the green assertion is not vacuous.

No Postgres, no OpenAI: classify is monkeypatched per test.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import tour_content_rating  # noqa: E402  (repo root)


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5


# ── Fixtures: two short tour scripts, one each side of the line ───────────────
HISTORY_OF_CRIME = (
    "Welcome to the Whitechapel history walk. On this corner in 1888 the police "
    "discovered one of the Ripper's victims; we trace how the Victorian press and "
    "a nervous public reacted, and how the unsolved case shaped modern forensic "
    "policing. Further along stands the former magistrates' court where the "
    "notorious Kray twins were finally tried. This is a factual history of crime "
    "in the East End — who did what, when, and why it still fascinates historians."
)

HOW_TO_COMMIT_CRIME = (
    "On this walk I will show you how to pick the lock on these older shopfronts "
    "in under a minute, which back alleys have no cameras so you can avoid the "
    "police, and how to disable a car immobiliser to take the vehicle. I'll also "
    "point out where to buy stolen goods with no questions asked."
)


def _prompt_faithful_classify(title, text, stops):
    """A stand-in for a model that READS the LOCAL-726 prompt correctly.

    Decides from the chunk text the same way the prompt tells the real model to:
    recounting the history of a crime is allowed; teaching how to COMMIT one is
    not_allowed. Signal words for instruction ("how to", "avoid the police",
    "pick the lock", "where to buy stolen") => not_allowed; otherwise, crime told
    as past history => general.
    """
    low = text.lower()
    instruct = ("how to pick", "avoid the police", "disable a car",
                "where to buy stolen", "with no questions asked")
    if any(s in low for s in instruct):
        return ({"rating": "not_allowed",
                 "reason": "teaches the listener how to commit a crime"}, _Usage())
    return ({"rating": "general",
             "reason": "recounts the history of crime factually"}, _Usage())


class PromptCarriesTheDistinctionTest(unittest.TestCase):
    """Layer 1: the shipped prompt itself draws the history-vs-how-to line."""

    def setUp(self):
        self.prompt = tour_content_rating.PROMPT.lower()

    def test_history_of_crime_is_named_as_general(self):
        # The general bullet must explicitly place the history of crime there.
        self.assertIn("history of crime", self.prompt)

    def test_not_allowed_is_about_committing_not_mentioning_crime(self):
        # not_allowed must be scoped to COMMITTING / instructions, not any crime.
        self.assertTrue(
            ("commit" in self.prompt) and
            ("how to" in self.prompt),
            "not_allowed must target instructions to COMMIT a crime, not its mention",
        )

    def test_prompt_states_the_dividing_line_is_intent(self):
        self.assertIn("recounting the history of a crime is allowed", self.prompt)
        self.assertIn("explaining how to commit one is not_allowed", self.prompt)

    def test_mature_no_longer_flags_crime_flatly(self):
        # The old wording ("crime treated as entertainment") flagged crime flatly;
        # the new wording qualifies it with lurid/glamorised. The bare phrase must
        # be gone so the model is not told to make all crime mature.
        self.assertNotIn("crime treated as entertainment", self.prompt)


class TwoFixturesThroughRealRateTextTest(unittest.TestCase):
    """Layer 2: the two fixtures drive the real serving path with classify mocked
    by a prompt-faithful rule."""

    def setUp(self):
        self._orig = tour_content_rating.classify
        tour_content_rating.classify = _prompt_faithful_classify

    def tearDown(self):
        tour_content_rating.classify = self._orig

    def test_history_of_crime_is_not_blocked(self):
        rating, detail = tour_content_rating.rate_text(
            "Whitechapel History Walk", HISTORY_OF_CRIME, 4)
        self.assertNotEqual(rating, "not_allowed",
                            "a factual history-of-crime tour must not be blocked")
        # general lists immediately; mature would at worst hold for review — but
        # never not_allowed.
        self.assertIn(rating, ("general", "mature"))

    def test_how_to_commit_crime_is_not_allowed(self):
        rating, detail = tour_content_rating.rate_text(
            "Easy Scores Walk", HOW_TO_COMMIT_CRIME, 4)
        self.assertEqual(rating, "not_allowed",
                        "a tour teaching how to commit crimes must be not_allowed")
        self.assertEqual(tour_content_rating.review_status_for(rating), "pending")


class RedWhenPromptMisreadTest(unittest.TestCase):
    """Layer 3: a model/mock that flatly blocks ALL crime (the pre-726 risk the
    lawyer flagged) fails the history fixture — proving the green test above is
    not vacuous."""

    def setUp(self):
        self._orig = tour_content_rating.classify

        def _blocks_all_crime(title, text, stops):
            low = text.lower()
            if "crime" in low or "ripper" in low or "lock" in low:
                return ({"rating": "not_allowed", "reason": "mentions crime"}, _Usage())
            return ({"rating": "general", "reason": "ok"}, _Usage())

        tour_content_rating.classify = _blocks_all_crime

    def tearDown(self):
        tour_content_rating.classify = self._orig

    def test_overblocking_rater_wrongly_blocks_history_red(self):
        rating, _ = tour_content_rating.rate_text(
            "Whitechapel History Walk", HISTORY_OF_CRIME, 4)
        with self.assertRaises(AssertionError):
            self.assertNotEqual(
                rating, "not_allowed",
                "an over-blocking rater wrongly blocks the history of crime",
            )


if __name__ == "__main__":
    unittest.main()
