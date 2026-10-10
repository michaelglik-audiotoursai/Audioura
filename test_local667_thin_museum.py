#!/usr/bin/env python3
"""test_local667_thin_museum.py — LOCAL-667 thin-Wikidata verification.

A real museum with a thin Wikidata catalogue (HCMC Museum of Fine Arts: one
SPARQL work) must not stop at "1 of 5". The model proposes genuine works
(The Fisherman, Lotus Pond, …) that the thin canonical set cannot verify; this
module re-verifies them against the museum's own site, Wikipedia (local + EN),
and a grounded search, admitting a work ONLY when two independent sources name it
at this museum. These tests pin that rule — including that one source, or zero,
is never enough, and that nothing is invented.

Run: python3 -m pytest test_local667_thin_museum.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from thin_wikidata_fallback import (  # noqa: E402
    verify_thin_candidates,
    corpus_hits_for_title,
    grounded_hits_for_title,
    title_in_text,
)

_VENUE = "Ho Chi Minh City Museum of Fine Arts"


def _pages(site_text="", wiki_en="", wiki_vi=""):
    out = []
    if site_text:
        out.append({"url": "http://baotangmythuattphcm.com.vn/", "title": "Collection",
                    "text": site_text})
    if wiki_en:
        out.append({"url": "https://en.wikipedia.org/wiki/HCMC_Museum", "title": "Wikipedia",
                    "text": wiki_en})
    if wiki_vi:
        out.append({"url": "https://vi.wikipedia.org/wiki/Bao_tang", "title": "Wikipedia",
                    "text": wiki_vi})
    return out


class TestTwoSourceRule(unittest.TestCase):
    def test_two_corpus_sources_verify(self):
        pages = _pages(
            site_text="Among the highlights is The Fisherman by Nguyen Gia Tri.",
            wiki_en="The museum holds The Fisherman and other lacquer works.")
        verified, verdicts = verify_thin_candidates(
            [{"name": "The Fisherman"}], pages, _VENUE, research_fn=None)
        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["name"], "The Fisherman")
        self.assertTrue(verdicts[0].verified)
        self.assertGreaterEqual(verdicts[0].source_count, 2)

    def test_one_source_is_not_enough(self):
        pages = _pages(site_text="Among the highlights is The Fisherman.")
        verified, verdicts = verify_thin_candidates(
            [{"name": "The Fisherman"}], pages, _VENUE, research_fn=None)
        self.assertEqual(verified, [])
        self.assertFalse(verdicts[0].verified)
        self.assertEqual(verdicts[0].source_count, 1)

    def test_zero_sources_never_verifies(self):
        pages = _pages(site_text="The museum is in a historic mansion.")
        verified, verdicts = verify_thin_candidates(
            [{"name": "A Totally Invented Work"}], pages, _VENUE, research_fn=None)
        self.assertEqual(verified, [])
        self.assertFalse(verdicts[0].verified)
        self.assertEqual(verdicts[0].source_count, 0)

    def test_same_page_twice_counts_once(self):
        """Two mentions on the SAME page are one source, not two."""
        pages = _pages(
            site_text="The Fisherman is here. Again, The Fisherman is on view.")
        verified, verdicts = verify_thin_candidates(
            [{"name": "The Fisherman"}], pages, _VENUE, research_fn=None)
        self.assertEqual(verified, [])
        self.assertEqual(verdicts[0].source_count, 1)

    def test_corpus_plus_grounded_reaches_bar(self):
        """One corpus mention + one independent web domain = two sources."""
        pages = _pages(site_text="The Fisherman is a highlight of the collection.")

        def _stub_research(prompt):
            return {
                "text": "Yes, The Fisherman is held at the museum.",
                "sources": [{"domain": "artsandculture.google.com",
                             "url": "https://artsandculture.google.com/x"}],
                "supports": [{"text": "The Fisherman is held at the museum.",
                              "sources": [{"domain": "artsandculture.google.com",
                                           "url": "https://artsandculture.google.com/x"}]}],
                "queries": ["The Fisherman HCMC museum"],
                "error": "",
            }

        verified, verdicts = verify_thin_candidates(
            [{"name": "The Fisherman"}], pages, _VENUE, research_fn=_stub_research)
        self.assertEqual(len(verified), 1)
        self.assertGreaterEqual(verdicts[0].source_count, 2)
        origins = {s["origin"] for s in verified[0]["thin_sources"]}
        self.assertIn("site", origins)
        self.assertIn("artsandculture.google.com", origins)

    def test_grounded_error_is_ignored(self):
        pages = _pages(site_text="The Fisherman is a highlight.")

        def _err_research(prompt):
            return {"text": "", "sources": [], "supports": [], "queries": [],
                    "error": "no GEMINI_API_KEY"}

        verified, verdicts = verify_thin_candidates(
            [{"name": "The Fisherman"}], pages, _VENUE, research_fn=_err_research)
        self.assertEqual(verified, [])  # still only 1 source → not verified

    def test_never_invents_beyond_candidates(self):
        """Only proposed candidates are considered; the function returns no work
        that was not in the input pool."""
        pages = _pages(
            site_text="Lotus Pond and The Fisherman are on view.",
            wiki_en="Lotus Pond and The Fisherman hang in the lacquer gallery.")
        verified, _ = verify_thin_candidates(
            [{"name": "Lotus Pond"}], pages, _VENUE, research_fn=None)
        self.assertEqual([v["name"] for v in verified], ["Lotus Pond"])


class TestLanguageSources(unittest.TestCase):
    def test_site_and_local_wiki_are_independent(self):
        pages = _pages(
            site_text="Vườn xuân Bắc Trung Nam là tác phẩm nổi bật.",
            wiki_vi="Bảo tàng trưng bày Vườn xuân Bắc Trung Nam.")
        verified, verdicts = verify_thin_candidates(
            [{"name": "Vườn xuân Bắc Trung Nam"}], pages, _VENUE,
            venue_language="vi", research_fn=None)
        self.assertEqual(len(verified), 1)
        origins = {s["origin"] for s in verified[0]["thin_sources"]}
        self.assertEqual(origins, {"site", "wikipedia_local"})

    def test_wiki_en_and_wiki_local_distinct_origins(self):
        pages = _pages(wiki_en="The museum holds Spring Garden works.",
                       wiki_vi="Bảo tàng có Spring Garden.")
        hits = corpus_hits_for_title("Spring Garden", pages, venue_language="vi")
        origins = {h.origin for h in hits}
        self.assertEqual(origins, {"wikipedia_en", "wikipedia_local"})


class TestTitleInText(unittest.TestCase):
    def test_accent_insensitive(self):
        self.assertTrue(title_in_text("Vuon xuan", "Vườn xuân Bắc Trung Nam"))

    def test_single_word_requires_whole_word(self):
        # single content word 'garden' as substring of a bigger word must not hit
        self.assertFalse(title_in_text("Garden", "gardenia flowers everywhere"))
        self.assertTrue(title_in_text("Garden", "a quiet Garden scene"))

    def test_multiword_all_content_words(self):
        self.assertTrue(title_in_text("The Fisherman", "a lone fisherman at dawn"))
        self.assertFalse(title_in_text("The Fisherman", "a lone sailor at dawn"))


class TestGroundedHits(unittest.TestCase):
    def test_support_attribution_preferred(self):
        gres = {
            "text": "irrelevant text",
            "sources": [{"domain": "wrong.com", "url": "https://wrong.com"}],
            "supports": [{"text": "The Fisherman is at the museum.",
                          "sources": [{"domain": "right.org", "url": "https://right.org"}]}],
            "queries": [], "error": "",
        }
        hits = grounded_hits_for_title("The Fisherman", gres)
        self.assertEqual({h.origin for h in hits}, {"right.org"})

    def test_text_fallback_when_no_supports(self):
        gres = {
            "text": "The Fisherman is at the museum.",
            "sources": [{"domain": "a.com", "url": "https://a.com"},
                        {"domain": "b.com", "url": "https://b.com"}],
            "supports": [], "queries": [], "error": "",
        }
        hits = grounded_hits_for_title("The Fisherman", gres)
        self.assertEqual({h.origin for h in hits}, {"a.com", "b.com"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
