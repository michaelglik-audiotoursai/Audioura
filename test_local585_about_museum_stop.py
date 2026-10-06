#!/usr/bin/env python3
"""test_local585_about_museum_stop.py — LOCAL-585 unit tests.

A museum tour opens with the museum's OWN story (founder, why it exists, what it is
known for) as an "About <museum>" STORY stop — never framed as an artwork — placed
FIRST in the stop-pool assembly. For architecturally notable / architecture-named
requests the About stop also covers the building (the Boston Athenaeum case).

These tests are OFFLINE and deterministic: build_about_stop is driven with a FAKE
fetcher (fixtures / inline HTML) and an injectable wiki_provider, and the assembler
runs with no DB/network/LLM. They assert Michael's design rules:

  1. The Griffin founding content (Arthur Griffin, est. 1992, non-profit) appears
     as an About stop — and is NEVER framed as an artwork ("consists of a series
     of frames", "this work", "oil on canvas" …).
  2. The stop is sourced (venue domain + any wiki URLs) and carries no artist/year.
  3. Architecture coverage fires when the REQUEST names architecture (Athenaeum)
     or the building is architecturally notable (wiki flag).
  4. Count semantics: [LOCAL-592 SUPERSEDED] the About content is the opening
     SECTION of Stop 1, never a stop, so should_count_toward_n is always False
     and a request for N delivers exactly N stops.
  5. In the stop-pool building assembly the About content is FOLDED into Stop 1's
     opening section (never an extra stop — LOCAL-592); the pooled narration is
     still reused verbatim.

Run: python3 -m pytest test_local585_about_museum_stop.py -q
"""
import os
import re
import unittest

import about_museum_stop as am
import stop_pool_assembly as asm


# ── Inline fixtures ───────────────────────────────────────────────────────────

# A Griffin "About / history" page: the founding story that tour 391 wrongly
# framed as an artwork. Arthur Griffin, founded, non-profit since 1992.
_GRIFFIN_ABOUT_HTML = (
    "<html><body>"
    "<h1>About the Griffin Museum of Photography</h1>"
    "<p>The Griffin Museum of Photography was founded in 1992 by the photographer "
    "Arthur Griffin, and is dedicated to promoting the art of photography through "
    "exhibitions, lectures, and education.</p>"
    "<p>New England's Premier Photography Museum, est. 1992.</p>"
    "<p>The Griffin is a non-profit museum named for Arthur Griffin, a Winchester "
    "photographer whose archive the museum preserves.</p>"
    "<form><label>Yes, I would like to receive emails from the Griffin Museum.</label></form>"
    "</body></html>"
)

_BASE = "https://griffinmuseum.org"


def _griffin_fetcher(url):
    """A fake (html, links) fetcher: the About page under the story seeds, else ''."""
    u = url.rstrip("/")
    if u.endswith("about") or u.endswith("about-us") or u.endswith("about-the-museum") \
            or u.endswith("history") or u.endswith("mission") \
            or u.endswith("your-support-matters") or u == "https://griffinmuseum.org":
        return _GRIFFIN_ABOUT_HTML, []
    return "", []


# A Boston Athenaeum "the building / architecture" page: architect + style.
_ATHENAEUM_BUILDING_HTML = (
    "<html><body>"
    "<h1>About the Boston Athenaeum</h1>"
    "<p>The Boston Athenaeum, founded in 1807, is one of the oldest independent "
    "libraries in the United States.</p>"
    "<p>Its landmark building at 10 and a half Beacon Street was designed by the "
    "architect Edward Clarke Cabot in the Italianate Renaissance Revival style and "
    "opened in 1849.</p>"
    "<p>The granite facade and fifth-floor reading room are celebrated examples of "
    "nineteenth-century architecture.</p>"
    "</body></html>"
)

_ATH_BASE = "https://bostonathenaeum.org"


def _athenaeum_fetcher(url):
    u = url.rstrip("/")
    if u.endswith("about") or u.endswith("about-us") or u.endswith("the-building") \
            or u.endswith("architecture") or u.endswith("history") \
            or u == "https://bostonathenaeum.org":
        return _ATHENAEUM_BUILDING_HTML, []
    return "", []


# ── Griffin About stop ─────────────────────────────────────────────────────────

class TestGriffinAboutStop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            address="67 Shore Road, Winchester, MA",
            requested_stops=7,
            available_exhibition_stops=10,   # plenty of exhibitions → About is a bonus
            fetcher=_griffin_fetcher,
        )

    def test_about_stop_is_built(self):
        self.assertIsNotNone(self.about)
        self.assertFalse(self.about.is_empty())

    def test_tells_the_founding_story(self):
        low = self.about.narration.lower()
        self.assertIn("arthur griffin", low)      # the founder
        self.assertIn("1992", self.about.narration)  # the founding year
        self.assertTrue("non-profit" in low or "nonprofit" in low)

    def test_never_framed_as_artwork(self):
        # The core LOCAL-585 contract: the museum's story is NOT an object label.
        self.assertFalse(am.looks_like_artwork_framing(self.about.narration))
        low = self.about.narration.lower()
        self.assertNotIn("consists of a series of frames", low)
        self.assertNotIn("this work", low)
        self.assertNotIn("oil on canvas", low)

    def test_sourced_to_the_venue_domain(self):
        self.assertTrue(self.about.sources)
        self.assertTrue(any("griffinmuseum.org" in u for u in self.about.sources))

    def test_cruft_is_not_lifted(self):
        # The newsletter opt-in on the page must never become the story.
        self.assertNotIn("receive emails", self.about.narration.lower())
        self.assertNotIn("i would like", self.about.narration.lower())

    def test_unit_has_no_artwork_fields(self):
        unit = am.about_stop_unit(self.about)
        self.assertEqual(unit["title"], "About Griffin Museum of Photography")
        self.assertTrue(unit["_about_stop"])
        self.assertFalse(unit["_pool_reused"])
        for forbidden in ("artist", "year", "type_specialty", "specific_examples"):
            self.assertNotIn(forbidden, unit)

    def test_counts_toward_n_false_when_exhibitions_plenty(self):
        # 10 exhibitions available for a 7-stop request → About does not consume a slot.
        self.assertFalse(self.about.counts_toward_n)


class TestGriffinAboutStopCountsWhenThin(unittest.TestCase):
    def test_counts_toward_n_false_even_when_exhibitions_thin(self):
        # [LOCAL-592] SUPERSEDED: the About content folds into Stop 1's opening
        # section — it is never a stop — so even when exhibition material is thin
        # it does NOT count toward N. A request for N delivers exactly N stops.
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            requested_stops=5,
            available_exhibition_stops=3,   # only 3 exhibitions for a 5-stop ask
            fetcher=_griffin_fetcher,
        )
        self.assertIsNotNone(about)
        self.assertFalse(about.counts_toward_n)


# ── Architecture coverage (Athenaeum) ───────────────────────────────────────────

class TestAthenaeumArchitecture(unittest.TestCase):
    def test_architecture_covered_when_request_names_it(self):
        about = am.build_about_stop(
            venue_name="Boston Athenaeum",
            base_site_url=_ATH_BASE,
            request_text="Art and Architectual tour in Boston Athenaeum",
            locality="Boston, MA",
            requested_stops=5,
            available_exhibition_stops=5,
            fetcher=_athenaeum_fetcher,
        )
        self.assertIsNotNone(about)
        self.assertTrue(about.covers_architecture)
        low = about.narration.lower()
        self.assertIn("cabot", low)            # the architect, from the site
        self.assertTrue("italianate" in low or "renaissance revival" in low)
        self.assertFalse(am.looks_like_artwork_framing(about.narration))

    def test_architecture_covered_when_wiki_flags_notable(self):
        def _wiki(_name):
            return {
                "summary": "The Boston Athenaeum is a historic membership library founded in 1807.",
                "architect": "Edward Clarke Cabot",
                "inception": "1849",
                "architecturally_notable": True,
                "sources": ["https://en.wikipedia.org/wiki/Boston_Athenaeum"],
            }
        about = am.build_about_stop(
            venue_name="Boston Athenaeum",
            base_site_url=_ATH_BASE,
            request_text="art tour of the Boston Athenaeum",   # request does NOT name architecture
            fetcher=_athenaeum_fetcher,
            wiki_provider=_wiki,
        )
        self.assertIsNotNone(about)
        self.assertTrue(about.covers_architecture)     # notability alone triggers it
        self.assertIn("Edward Clarke Cabot", about.narration)
        self.assertTrue(any("wikipedia.org" in u for u in about.sources))

    def test_architecture_not_covered_for_plain_art_request_no_notability(self):
        # A plain art request at a non-notable building: no architecture section.
        def _wiki(_name):
            return {"summary": "A small photography museum.", "architecturally_notable": False}
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            request_text="art tour of the Griffin",
            fetcher=_griffin_fetcher,
            wiki_provider=_wiki,
        )
        self.assertIsNotNone(about)
        self.assertFalse(about.covers_architecture)


# ── No story → no About stop (never invent) ─────────────────────────────────────

class TestNoStoryNoStop(unittest.TestCase):
    def test_returns_none_when_no_story_sourced(self):
        def _empty_fetch(_url):
            return "<html><body><p>Buy tickets. Shop now. Join our newsletter.</p></body></html>", []
        about = am.build_about_stop(
            venue_name="Blank Museum",
            base_site_url="https://blank.example",
            fetcher=_empty_fetch,
        )
        self.assertIsNone(about)

    def test_returns_none_when_no_site_and_no_wiki(self):
        self.assertIsNone(am.build_about_stop(venue_name="Nowhere Museum"))


# ── Pure predicates ─────────────────────────────────────────────────────────────

class TestPredicates(unittest.TestCase):
    def test_request_wants_architecture(self):
        self.assertTrue(am.request_wants_architecture("Art and Architectual tour"))
        self.assertTrue(am.request_wants_architecture("architecture tour of X"))
        self.assertFalse(am.request_wants_architecture("art tour of X"))

    def test_looks_like_artwork_framing(self):
        self.assertTrue(am.looks_like_artwork_framing(
            "Griffin Museum Board Of Directors 2 consists of a series of frames."))
        self.assertTrue(am.looks_like_artwork_framing("This work is oil on canvas."))
        self.assertFalse(am.looks_like_artwork_framing(
            "The museum was founded in 1992 by Arthur Griffin."))

    def test_should_count_toward_n(self):
        # [LOCAL-592] SUPERSEDED: the About content is the opening SECTION of
        # Stop 1, never a standalone stop, so it can never count toward N. The
        # LOCAL-585 "thin exhibitions → count it" branch is gone; the function
        # now returns False for every input (a request for N delivers exactly N).
        self.assertFalse(am.should_count_toward_n(None, 0))
        self.assertFalse(am.should_count_toward_n(0, 0))
        self.assertFalse(am.should_count_toward_n(7, 10))   # enough exhibitions
        self.assertFalse(am.should_count_toward_n(7, 7))    # exactly enough
        self.assertFalse(am.should_count_toward_n(5, 3))    # too few → STILL not a stop

    def test_clean_venue_request_name(self):
        # A themed-in-building request resolves to the building name.
        self.assertEqual(
            am.clean_venue_request_name(
                "Art and Architectual tour in Boston Athenaeum, boston, ma"),
            "Boston Athenaeum")
        self.assertEqual(
            am.clean_venue_request_name("architecture tour of the Boston Athenaeum"),
            "the Boston Athenaeum")
        # A plain venue string keeps its leading segment.
        self.assertEqual(
            am.clean_venue_request_name("Griffin Museum of Photography, Winchester, MA"),
            "Griffin Museum of Photography")

    def test_default_wiki_provider_empty_name_is_none(self):
        self.assertIsNone(am.default_wiki_provider(""))


# ── Assembly places the About stop FIRST ────────────────────────────────────────

def _pooled(title, narration, **kw):
    d = {"title": title, "narration": narration, "orientation": "look here",
         "_pool_reused": True, "address": "1 Test St"}
    d.update(kw)
    return d


def _new(title, narration, **kw):
    d = {"title": title, "narration": narration, "orientation": "new look",
         "_pool_reused": False, "address": "1 Test St"}
    d.update(kw)
    return d


class TestAssemblyPlacesAboutFirst(unittest.TestCase):
    """[LOCAL-592] SUPERSEDED: the About content is no longer a standalone Stop 1.
    A legacy ``about_stop`` unit is now FOLDED into Stop 1's opening section (never
    an extra stop), so a request for N exhibition stops still delivers exactly N."""

    def setUp(self):
        self.about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            requested_stops=7,
            available_exhibition_stops=10,
            fetcher=_griffin_fetcher,
        )
        self.about_unit = am.about_stop_unit(self.about)
        self.pooled = [_pooled("Alpha", "Narration for Alpha pooled."),
                       _pooled("Beta", "Narration for Beta pooled.")]
        self.new = [_new("New One", "Fresh narration one.")]
        self.res = asm.assemble_building_tour(
            location="Griffin Museum of Photography, Winchester, MA",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Griffin Museum of Photography",
            new_stops=self.new, pooled_stops=self.pooled,
            about_stop=self.about_unit,
        )

    def test_no_standalone_about_stop(self):
        # The legacy about_stop is folded in, not placed as its own stop.
        self.assertNotIn("About Griffin Museum of Photography", self.res.order)
        self.assertEqual(self.res.about_stops, 1)   # reported for the ledger, 0 stops added
        # No stop header is titled "About …".
        self.assertNotRegex(self.res.tour_text, r"(?m)^Stop \d+:.*About")

    def test_order_is_new_then_pooled_exactly_n(self):
        self.assertEqual(self.res.order, ["New One", "Alpha", "Beta"])

    def test_about_content_folded_into_stop_1(self):
        stop1_block = self.res.tour_text.split("Stop 2:")[0]
        self.assertIn("Arthur Griffin", stop1_block)
        self.assertIn("1992", stop1_block)
        # Stop 1's own exhibition narration still follows the About material.
        self.assertIn("Fresh narration one.", stop1_block)

    def test_pooled_narration_still_reused_verbatim(self):
        for p in self.pooled:
            self.assertIn(p["narration"], self.res.tour_text)

    def test_about_block_has_no_artwork_fields_rendered(self):
        stop1_block = self.res.tour_text.split("Stop 2:")[0]
        self.assertNotIn("Type/Specialty:", stop1_block)
        self.assertNotIn("Specific Examples:", stop1_block)
        self.assertFalse(am.looks_like_artwork_framing(stop1_block))

    def test_backward_compatible_without_about_stop(self):
        # Omitting about_stop keeps the pre-LOCAL-585 behaviour (new before pooled).
        res = asm.assemble_building_tour(
            location="V", tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum", venue_name="V",
            new_stops=self.new, pooled_stops=self.pooled)
        self.assertEqual(res.about_stops, 0)
        self.assertEqual(res.order, ["New One", "Alpha", "Beta"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
