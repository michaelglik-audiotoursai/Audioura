#!/usr/bin/env python3
"""test_local592_about_in_stop1.py — LOCAL-592 unit tests.

Michael's rule (2026-10-06, binding):
    "If a user asks for x number of stops, we are supposed to generate exactly x
     number of stops. In Walking tours we have the Overall section and that
     section is the start of Stop 1. The stop itself is after this section but
     still part of Stop 1. The same must be true with museum, restaurant, etc.
     and other tours. It is very important to say when the museum opens, how much
     they charge for entrance, etc. but it has to be the first section of Stop 1."

LOCAL-585 (subscribed c9d4c47) adds "About <museum>" as an EXTRA stop: a 5-stop
request delivers 6, a 7-stop request delivers 8. LOCAL-592 folds the About content
AND the practical facts (opening hours, admission, closed days) into the OPENING
SECTION of Stop 1 — exactly like the walking-tour prolog — so N requested delivers
N, always. No stop is ever titled "About …".

These tests are OFFLINE and deterministic (fake fetcher, injectable wiki provider,
assembler with no DB/network/LLM). They are RED on c9d4c47 (the extra-stop
behaviour) and GREEN after the fold.

Run: python3 -m pytest test_local592_about_in_stop1.py -q
"""
import os
import re
import unittest

import about_museum_stop as am
import stop_pool_assembly as asm


# ── Fixtures (shared shape with the LOCAL-585 suite) ─────────────────────────

_GRIFFIN_ABOUT_HTML = (
    "<html><body>"
    "<h1>About the Griffin Museum of Photography</h1>"
    "<p>The Griffin Museum of Photography was founded in 1992 by the photographer "
    "Arthur Griffin, and is dedicated to promoting the art of photography through "
    "exhibitions, lectures, and education.</p>"
    "<p>New England's Premier Photography Museum, est. 1992.</p>"
    "<p>The Griffin is a non-profit museum named for Arthur Griffin, a Winchester "
    "photographer whose archive the museum preserves.</p>"
    "<h2>Hours</h2><p>Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.</p>"
    "<h2>Admission</h2><p>General Admission: $12 for adults.</p>"
    "</body></html>"
)
_BASE = "https://griffinmuseum.org"


def _griffin_fetcher(url):
    u = url.rstrip("/")
    if (u.endswith("about") or u.endswith("about-us") or u.endswith("about-the-museum")
            or u.endswith("history") or u.endswith("mission")
            or u.endswith("your-support-matters") or u.endswith("visit")
            or u.endswith("plan-your-visit") or u == "https://griffinmuseum.org"):
        return _GRIFFIN_ABOUT_HTML, []
    return "", []


_ATHENAEUM_BUILDING_HTML = (
    "<html><body>"
    "<h1>About the Boston Athenaeum</h1>"
    "<p>The Boston Athenaeum, founded in 1807, is one of the oldest independent "
    "libraries in the United States.</p>"
    "<p>Its landmark building at 10 and a half Beacon Street was designed by the "
    "architect Edward Clarke Cabot in the Italianate Renaissance Revival style and "
    "opened in 1849.</p>"
    "<h2>Hours</h2><p>Monday through Saturday: 9 AM to 5 PM. Closed: Sunday.</p>"
    "<h2>Admission</h2><p>Admission is free to the first floor.</p>"
    "</body></html>"
)
_ATH_BASE = "https://bostonathenaeum.org"


def _athenaeum_fetcher(url):
    u = url.rstrip("/")
    if (u.endswith("about") or u.endswith("about-us") or u.endswith("the-building")
            or u.endswith("architecture") or u.endswith("history")
            or u.endswith("visit") or u.endswith("plan-your-visit")
            or u == "https://bostonathenaeum.org"):
        return _ATHENAEUM_BUILDING_HTML, []
    return "", []


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


# ── 1. should_count_toward_n: the About content never consumes/adds a stop ───

class TestNeverCountsAsAStop(unittest.TestCase):
    """The About content is the opening SECTION of Stop 1, not a stop. It can
    never add to or subtract from the requested count — so should_count_toward_n
    is always False (the 'extra' / 'thin exhibitions' branch is gone)."""

    def test_always_false_regardless_of_exhibition_supply(self):
        self.assertFalse(am.should_count_toward_n(None, 0))
        self.assertFalse(am.should_count_toward_n(0, 0))
        self.assertFalse(am.should_count_toward_n(7, 10))   # plenty
        self.assertFalse(am.should_count_toward_n(7, 7))    # exactly enough
        self.assertFalse(am.should_count_toward_n(5, 3))    # thin — STILL not a stop
        self.assertFalse(am.should_count_toward_n(5, 0))    # none — STILL not a stop


# ── 2. The opening section carries About + practical facts ───────────────────

class TestOpeningSectionContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            address="67 Shore Road, Winchester, MA",
            requested_stops=7,
            available_exhibition_stops=10,
            fetcher=_griffin_fetcher,
            practical_facts="Closed on Monday. Noon–4 PM. $12",
        )

    def test_about_built(self):
        self.assertIsNotNone(self.about)
        self.assertFalse(self.about.is_empty())

    def test_opening_section_has_about_story(self):
        section = am.build_opening_section(self.about)
        low = section.lower()
        self.assertIn("arthur griffin", low)
        self.assertIn("1992", section)

    def test_opening_section_has_practical_facts(self):
        section = am.build_opening_section(self.about)
        self.assertIn("Monday", section)      # closed day
        self.assertIn("4 PM", section)        # hours
        self.assertIn("$12", section)         # admission

    def test_opening_section_never_artwork_framed(self):
        section = am.build_opening_section(self.about)
        self.assertFalse(am.looks_like_artwork_framing(section))

    def test_practical_facts_carried_on_about(self):
        # The gated practical facts string is carried on the AboutStop.
        self.assertIn("$12", self.about.practical_facts)
        self.assertIn("Monday", self.about.practical_facts)


# ── 3. Assembly folds the opening section INTO Stop 1 (no extra stop) ────────

class TestBuildingFoldAthenaeum5to5(unittest.TestCase):
    """Athenaeum: 5 exhibition stops requested → 5 stops delivered; Stop 1 opens
    with the About + practical section, then the first artwork's own narration."""

    def setUp(self):
        self.about = am.build_about_stop(
            venue_name="Boston Athenaeum",
            base_site_url=_ATH_BASE,
            request_text="Art and Architectual tour in Boston Athenaeum",
            locality="Boston, MA",
            requested_stops=5,
            available_exhibition_stops=5,
            fetcher=_athenaeum_fetcher,
            practical_facts="Closed on Sunday. 9 AM–5 PM. Admission is free",
        )
        self.opening = am.build_opening_section(self.about)
        self.new = [_new(f"Artwork {i}", f"Narration body for artwork {i}.")
                    for i in range(1, 6)]
        self.res = asm.assemble_building_tour(
            location="Art and Architectual tour in Boston Athenaeum, boston, ma",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Boston Athenaeum",
            new_stops=self.new, pooled_stops=[],
            opening_section=self.opening,
        )

    def test_exactly_five_stops(self):
        self.assertEqual(len(self.res.order), 5)
        # The last stop header is Stop 5; no Stop 6.
        self.assertIn("Stop 5:", self.res.tour_text)
        self.assertNotIn("Stop 6:", self.res.tour_text)

    def test_no_stop_titled_about(self):
        for t in self.res.order:
            self.assertNotIn("About", t)
        self.assertNotRegex(self.res.tour_text, r"(?m)^Stop \d+:.*About")

    def test_stop1_is_the_first_artwork(self):
        self.assertEqual(self.res.order[0], "Artwork 1")

    def test_stop1_opens_with_about_then_artwork(self):
        stop1 = self.res.tour_text.split("Stop 2:")[0]
        low = stop1.lower()
        # About content present...
        self.assertIn("cabot", low)                  # the architect, sourced
        # ...practical facts present...
        self.assertIn("Sunday", stop1)
        self.assertIn("5 PM", stop1)
        # ...and the first artwork's own narration follows, in Stop 1.
        self.assertIn("Narration body for artwork 1.", stop1)
        # The About material precedes the artwork narration.
        self.assertLess(low.index("cabot"),
                        low.index("narration body for artwork 1"))

    def test_about_stops_reported_as_folded(self):
        # Reported for the ledger, but it adds ZERO stops to the count.
        self.assertEqual(self.res.about_stops, 1)
        self.assertEqual(len(self.res.order), len(self.new))


class TestBuildingFoldGriffin7to7(unittest.TestCase):
    """Griffin: 7 exhibition stops requested → 7 delivered; opening section folded
    into Stop 1."""

    def setUp(self):
        self.about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            requested_stops=7,
            available_exhibition_stops=7,
            fetcher=_griffin_fetcher,
            practical_facts="Closed on Monday. Noon–4 PM. $12",
        )
        self.opening = am.build_opening_section(self.about)
        self.new = [_new(f"Photo {i}", f"Narration body for photo {i}.")
                    for i in range(1, 8)]
        self.res = asm.assemble_building_tour(
            location="Griffin Museum of Photography, Winchester, MA",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Griffin Museum of Photography",
            new_stops=self.new, pooled_stops=[],
            opening_section=self.opening,
        )

    def test_exactly_seven_stops(self):
        self.assertEqual(len(self.res.order), 7)
        self.assertIn("Stop 7:", self.res.tour_text)
        self.assertNotIn("Stop 8:", self.res.tour_text)

    def test_no_stop_titled_about(self):
        self.assertNotRegex(self.res.tour_text, r"(?m)^Stop \d+:.*About")

    def test_stop1_opens_with_about_and_practical(self):
        stop1 = self.res.tour_text.split("Stop 2:")[0]
        self.assertIn("Arthur Griffin", stop1)
        self.assertIn("1992", stop1)
        self.assertIn("Monday", stop1)
        self.assertIn("$12", stop1)
        self.assertIn("Narration body for photo 1.", stop1)


# ── 4. Pooled bodies verbatim; opening section regenerated (LOCAL-590) ───────

class TestPooledBodiesVerbatimOpeningRegenerated(unittest.TestCase):
    def test_pooled_narration_verbatim_and_opening_folded(self):
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography", base_site_url=_BASE,
            requested_stops=5, available_exhibition_stops=5,
            fetcher=_griffin_fetcher,
            practical_facts="Closed on Monday. Noon–4 PM. $12")
        opening = am.build_opening_section(about)
        pooled = [_pooled("Pooled A", "Verbatim pooled body A."),
                  _pooled("Pooled B", "Verbatim pooled body B.")]
        new = [_new("Fresh One", "Fresh body one.")]
        res = asm.assemble_building_tour(
            location="Griffin Museum of Photography, Winchester, MA",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Griffin Museum of Photography",
            new_stops=new, pooled_stops=pooled,
            overall_orientation="This regenerated overview introduces the fuller tour.",
            opening_section=opening,
        )
        # Exactly 3 stops (1 new + 2 pooled); opening folded into Stop 1.
        self.assertEqual(len(res.order), 3)
        self.assertEqual(res.order, ["Fresh One", "Pooled A", "Pooled B"])
        # Pooled bodies verbatim.
        self.assertIn("Verbatim pooled body A.", res.tour_text)
        self.assertIn("Verbatim pooled body B.", res.tour_text)
        # Opening section folded into Stop 1.
        stop1 = res.tour_text.split("Stop 2:")[0]
        self.assertIn("Arthur Griffin", stop1)
        self.assertIn("$12", stop1)

    def test_backward_compatible_without_opening_section(self):
        # Omitting opening_section keeps the pre-592 new-before-pooled behaviour,
        # exactly N stops, no About stop.
        res = asm.assemble_building_tour(
            location="V", tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum", venue_name="V",
            new_stops=[_new("New One", "n")], pooled_stops=[_pooled("A", "a")])
        self.assertEqual(res.about_stops, 0)
        self.assertEqual(res.order, ["New One", "A"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
