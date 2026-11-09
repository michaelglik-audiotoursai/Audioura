#!/usr/bin/env python3
"""test_local879_city_context_fetch.py — LOCAL-879 §5.

The log still showed, after LOCAL-878 fixed the locality for the delivered text:

    [LOCAL-459] R5: Fetched 3003 chars from https://en.wikipedia.org/wiki/Saigon_Centre

The city-context retrieval path (three_class_retrieval) extracted city hints from
the tour location by splitting on commas and stripping tour keywords — so the
leading TOPIC segment "Saigon centre landmarks" became a "city" and the context
fetch searched Wikipedia for it, hitting the Saigon Centre office tower instead
of Ho Chi Minh City.

The fix: the city-context extractor reuses LOCAL-878's _is_topic_segment to drop
a topic/category segment, so the derived city ("Ho Chi Minh City") is used.

Run: python3 -m pytest tests/test_local879_city_context_fetch.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import three_class_retrieval as tcr

REQ_547 = "Saigon centre landmarks, Ho Chi Minh City, Vietnam"


class TestCityHintsSkipTopic(unittest.TestCase):

    def test_topic_segment_not_a_city_hint(self):
        hints = tcr._extract_city_hints_from_tour_location(REQ_547)
        self.assertNotIn("Saigon centre landmarks", hints)
        self.assertFalse(any("landmark" in h.lower() for h in hints),
                         f"no topic hint allowed: {hints}")

    def test_derived_city_is_a_hint(self):
        hints = tcr._extract_city_hints_from_tour_location(REQ_547)
        self.assertIn("Ho Chi Minh City", hints)
        # The city is preferred FIRST (it drives the disambiguation query).
        self.assertEqual(hints[0], "Ho Chi Minh City")

    def test_parent_location_drops_topic(self):
        fb = tcr._extract_parent_location("Independence Palace", REQ_547)
        self.assertFalse(any("landmark" in f.lower() for f in fb),
                         f"no topic in parent fallbacks: {fb}")
        self.assertTrue(any("Ho Chi Minh City" in f for f in fb),
                        f"the city must be a parent fallback: {fb}")

    def test_plain_place_location_unchanged(self):
        # Back-compat: an ordinary "City, Country" tour location is unchanged.
        hints = tcr._extract_city_hints_from_tour_location(
            "Nice, France walking tour")
        self.assertIn("Nice", hints)
        self.assertIn("France", hints)

    def test_no_saigon_centre_query_is_built(self):
        # The disambiguation query is "<stop> <city_hint>"; with the topic gone,
        # no query can resolve to the Saigon Centre building.
        hints = tcr._extract_city_hints_from_tour_location(REQ_547)
        for h in hints:
            self.assertNotIn("centre landmarks", h.lower())


class TestR5BannedWikiTitle(unittest.TestCase):
    """LOCAL-459 R5 still fetched /wiki/Saigon_Centre from a story-search snippet
    (the office tower named after the request TOPIC). The generator registers the
    topic as a banned R5 Wikipedia title; snippet_ranker.fetch_pages_for_top_snippets
    then refuses to fetch it, keeping /wiki/Saigon_Centre out of the log."""

    def setUp(self):
        import snippet_ranker as sr
        self.sr = sr
        sr.clear_banned_wiki_titles()

    def tearDown(self):
        self.sr.clear_banned_wiki_titles()

    def test_banned_title_skips_the_office_tower(self):
        import exhibition_checklist as ec
        self.sr.register_banned_wiki_title("Saigon centre landmarks")
        self.sr.register_banned_wiki_title("Saigon centre")
        _orig = getattr(ec, "_fetch_page", None)
        ec._fetch_page = lambda u: ("x" * 500, None)
        try:
            snips = [
                {"url": "https://en.wikipedia.org/wiki/Saigon_Centre",
                 "snippet": "Saigon Centre is a shopping mall and office tower."},
                {"url": "https://en.wikipedia.org/wiki/Independence_Palace",
                 "snippet": "Independence Palace is a landmark in Ho Chi Minh City."},
            ]
            out = self.sr.fetch_pages_for_top_snippets(snips, max_fetches=3)
        finally:
            if _orig is not None:
                ec._fetch_page = _orig
        self.assertNotIn("fetched_passage", out[0],
                         "the Saigon Centre office tower must not be fetched")
        self.assertIn("fetched_passage", out[1],
                      "a legitimate landmark page is still fetched")

    def test_fold_title_from_wiki_url(self):
        self.assertEqual(
            self.sr._fold_title("https://en.wikipedia.org/wiki/Saigon_Centre"),
            "saigon centre")



if __name__ == "__main__":
    unittest.main(verbosity=2)
