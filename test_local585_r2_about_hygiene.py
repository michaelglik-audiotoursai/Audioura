#!/usr/bin/env python3
"""test_local585_r2_about_hygiene.py — LOCAL-585 r2 listener-facing defects.

LEAD review (2026-10-06): tours/local585_live/LOCAL585_ATHENAEUM.txt stop 1 shipped
four listener-facing defects. These tests pin the EXACT strings so they are red on
5a2b4bd and green after the r2 fix:

  1. Truncated sentence — "…a group of Bostonians who produced a magazine called."
     A sentence whose object was cut (final token is a verb/preposition expecting an
     object: "called"/"named"/"titled"/"known as"/"such as"/…) must be completed
     from the source or DROPPED. Never shipped mid-thought.
  2. Duplicate sentence — "Designed by Edward Clarke Cabot, the building opened in
     1849, with a sculpture gallery…" appeared TWICE (once in the history, again in
     the "A word about the building…" architecture section). Cross-section dedup of
     near-identical (normalised) sentences must leave exactly one.
  3. Raw request locality in narration — "here is the story of Boston Athenaeum in
     boston, ma itself". The lowercase request locality must be replaced by a
     properly-cased, state-expanded locality ("Boston, Massachusetts").
  4. Raw request string in Directions — "Continue through Art and Architectual tour
     in Boston Athenaeum — next is …". Directions must NAME the venue ("Continue
     through the Boston Athenaeum — next is …"), never the raw request string. This
     is asserted on BOTH transition composers (stop_pool_assembly._museum_transition
     and the generator's venue-name derivation).

Run: python3 -m pytest test_local585_r2_about_hygiene.py -q
"""
import re
import unittest

import about_museum_stop as am
import stop_pool_assembly as asm


# The real Athenaeum building/history page content as the composer saw it: the
# source DOES carry the dangling "...produced a magazine called." sentence (the
# object "The Monthly Anthology" lived in a later clause the extractor dropped),
# AND the architect sentence that the architecture section repeats verbatim.
_ATHENAEUM_HTML = (
    "<html><body>"
    "<h1>About the Boston Athenaeum</h1>"
    "<p>The Boston Athenaeum, founded in 1807, is one of the oldest independent "
    "libraries in the United States.</p>"
    "<p>Founded in 1807, the Boston Athenaeum evolved out of an organization known "
    "as the Anthology Society, formed in 1805 by a group of Bostonians who produced "
    "a magazine called.</p>"
    "<p>Designed by Edward Clarke Cabot, the building opened in 1849, with a "
    "sculpture gallery on the first floor, the book collection on the second, and a "
    "painting gallery on the skylit third floor.</p>"
    "</body></html>"
)

_ATH_BASE = "https://bostonathenaeum.org"


def _ath_fetcher(url):
    u = url.rstrip("/")
    if u.endswith(("about", "about-us", "the-building", "architecture", "history")) \
            or u == "https://bostonathenaeum.org":
        return _ATHENAEUM_HTML, []
    return "", []


def _build(locality="boston, ma", request_text="Art and Architectual tour in Boston Athenaeum"):
    return am.build_about_stop(
        venue_name="Boston Athenaeum",
        base_site_url=_ATH_BASE,
        request_text=request_text,
        locality=locality,
        requested_stops=5,
        available_exhibition_stops=5,
        fetcher=_ath_fetcher,
    )


class TestNoTruncatedSentence(unittest.TestCase):
    """Defect 1: a sentence whose object was cut must be dropped or completed."""

    def test_dangling_called_sentence_not_shipped(self):
        about = _build()
        self.assertIsNotNone(about)
        # The exact truncated string must not appear.
        self.assertNotIn("produced a magazine called.", about.narration)
        # No sentence may END on a dangling object-expecting token.
        self.assertFalse(
            am.has_dangling_object_sentence(about.narration),
            f"narration ends a sentence mid-thought:\n{about.narration}")

    def test_dangling_detector_pure(self):
        self.assertTrue(am.has_dangling_object_sentence(
            "They produced a magazine called."))
        self.assertTrue(am.has_dangling_object_sentence(
            "An organization known as."))
        self.assertTrue(am.has_dangling_object_sentence("A sculpture titled."))
        # A complete sentence is fine.
        self.assertFalse(am.has_dangling_object_sentence(
            "They produced a magazine called The Monthly Anthology."))
        self.assertFalse(am.has_dangling_object_sentence(
            "The building opened in 1849."))


class TestNoDuplicateSentence(unittest.TestCase):
    """Defect 2: the architect sentence must appear at most once."""

    def test_cabot_sentence_appears_once(self):
        about = _build()
        self.assertIsNotNone(about)
        n = about.narration.lower().count("designed by edward clarke cabot")
        self.assertEqual(n, 1,
                         f"architect sentence appears {n}× (want 1):\n{about.narration}")

    def test_dedup_helper_removes_near_identical(self):
        sents = [
            "Designed by Edward Clarke Cabot, the building opened in 1849.",
            "The library was founded in 1807.",
            "Designed by Edward Clarke Cabot, the building opened in 1849.",  # dup
        ]
        out = am.dedupe_sentences(sents)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0], sents[0])
        self.assertEqual(out[1], sents[1])


class TestNoRawLocalityInNarration(unittest.TestCase):
    """Defect 3: the lowercase request locality must not leak into narration."""

    def test_raw_lowercase_locality_absent(self):
        about = _build(locality="boston, ma")
        self.assertIsNotNone(about)
        self.assertNotIn("boston, ma", about.narration)
        self.assertNotIn("in boston, ma itself", about.narration.lower())

    def test_properly_cased_locality_present(self):
        about = _build(locality="boston, ma")
        self.assertIsNotNone(about)
        # State is expanded and the city is properly cased.
        self.assertIn("Boston, Massachusetts", about.narration)

    def test_locality_normaliser_pure(self):
        self.assertEqual(am.normalise_locality("boston, ma"), "Boston, Massachusetts")
        self.assertEqual(am.normalise_locality("Boston, MA"), "Boston, Massachusetts")
        self.assertEqual(am.normalise_locality("winchester, ma"),
                         "Winchester, Massachusetts")
        # Non-US / unknown tails are title-cased but not expanded.
        self.assertEqual(am.normalise_locality("nice, france"), "Nice, France")
        self.assertEqual(am.normalise_locality(""), "")


class TestDirectionsNameVenueNotRequest(unittest.TestCase):
    """Defect 4: Directions name the venue, never the raw request string."""

    _RAW = "Art and Architectual tour in Boston Athenaeum"

    def test_pool_assembly_transition_names_venue(self):
        # The assembler derives the venue from the themed request; the first
        # transition must read "Continue through <venue>", not the raw request.
        venue = asm._venue_name(f"{self._RAW}, boston, ma")
        line = asm._museum_transition(0, 6, "Boys Come Over Here You're Wanted", venue)
        self.assertNotIn(self._RAW, line)
        self.assertIn("Boston Athenaeum", line)

    def test_venue_name_strips_theme_prefix(self):
        self.assertEqual(
            asm._venue_name(f"{self._RAW}, boston, ma"), "Boston Athenaeum")

    def test_generator_venue_derivation_strips_theme_prefix(self):
        # generate_tour_text must clean the venue the same way before it is woven
        # into "Continue through {venue} — next is …".
        from about_museum_stop import clean_venue_request_name
        cleaned = clean_venue_request_name(f"{self._RAW}, boston, ma")
        self.assertEqual(cleaned, "Boston Athenaeum")
        self.assertNotIn("tour in", cleaned.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
