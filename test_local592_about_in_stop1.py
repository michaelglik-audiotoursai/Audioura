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


# ── 5. [r2] Four-part order inside Stop 1 (D611) ─────────────────────────────

class TestFourPartOrderInStop1(unittest.TestCase):
    """Michael (D611): the order INSIDE Stop 1 is (a) About the venue →
    (b) Visiting information → (c) the tour overview / Orientation → (d) Stop 1's
    own narration. The r1 fold put the About+visiting AFTER the Orientation (and,
    live, even after part of the first exhibition's narration). r2 renders the
    opening section FIRST, before the Orientation line."""

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
        self.new = [_new("Artwork 1", "Narration body for artwork one.",
                         orientation="Stand before the first case.")]
        self.res = asm.assemble_building_tour(
            location="Art and Architectual tour in Boston Athenaeum, boston, ma",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Boston Athenaeum",
            new_stops=self.new, pooled_stops=[],
            overall_orientation="You are about to explore the Boston Athenaeum. "
                                "Your first stop is Artwork 1.",
            opening_section=self.opening,
        )

    def test_stop1_renders_opening_before_orientation(self):
        stop1 = self.res.tour_text.split("Stop 2:")[0] if "Stop 2:" in self.res.tour_text \
            else self.res.tour_text
        low = stop1.lower()
        i_about = low.index("cabot")                     # (a) About (architect)
        i_visit = stop1.index("free")                    # (b) Visiting info (admission)
        i_orient = stop1.index("Orientation:")           # (c) the Orientation line
        i_overview = low.index("your first stop is")      # overview text (in Orientation)
        i_narr = low.index("narration body for artwork one")  # (d) stop narration
        # (a) and (b) both come BEFORE the Orientation line and the overview.
        self.assertLess(i_about, i_orient, "About must precede the Orientation line")
        self.assertLess(i_visit, i_orient, "Visiting info must precede the Orientation line")
        self.assertLess(i_orient, i_overview + 1, "overview rides on the Orientation line")
        # (c) overview precedes (d) the stop's own narration.
        self.assertLess(i_overview, i_narr, "overview must precede the stop narration")
        # Full chain: About → Visiting → Orientation/overview → narration.
        self.assertLess(i_about, i_visit)
        self.assertLess(i_visit, i_overview)
        self.assertLess(i_overview, i_narr)

    def test_opening_section_not_inside_orientation_or_narration(self):
        # The opening section is its own block, before 'Orientation:'; the About
        # text must not be glued into the Orientation value nor the narration body.
        stop1 = self.res.tour_text.split("Stop 2:")[0]
        before_orient = stop1.split("Orientation:")[0]
        self.assertIn("Cabot", before_orient)
        self.assertIn("free", before_orient)


# ── 6. [r2] Visiting-information fallback pointer (never invent) ──────────────

class TestVisitingInfoFallback(unittest.TestCase):
    """D611: hours/admission are "very important". When the venue's pages yield no
    gate-passing facts we must NOT invent them (D584) — the opening section carries
    a single honest website pointer instead."""

    def _about_no_facts(self, domain_base):
        return am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=domain_base,
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            requested_stops=7,
            available_exhibition_stops=7,
            fetcher=_griffin_fetcher,
            practical_facts="",   # nothing sourced/gated
        )

    def test_fallback_sentence_present_when_no_facts(self):
        about = self._about_no_facts(_BASE)
        section = am.build_opening_section(about)
        self.assertIn("Check opening hours and admission on", section)
        # [LOCAL-616 item 2 / D617] The pointer is domain-free — it points to
        # "the museum's website", never a spoken domain (which lives only in the
        # text-view Sources line).
        self.assertNotIn("griffinmuseum.org", section)
        self.assertIn("the museum's website", section)
        self.assertIn("before you go", section)

    def test_fallback_never_invents_hours_or_prices(self):
        about = self._about_no_facts(_BASE)
        section = am.build_opening_section(about)
        # No fabricated numbers/currency/times leaked in as "facts".
        self.assertNotRegex(section, r"\$\d")
        self.assertNotRegex(section, r"\d\s*(?:AM|PM|am|pm)")
        self.assertNotIn("€", section)

    def test_sourced_facts_preferred_over_fallback(self):
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography", base_site_url=_BASE,
            requested_stops=7, available_exhibition_stops=7,
            fetcher=_griffin_fetcher,
            practical_facts="Closed on Monday. Noon–4 PM. $12")
        section = am.build_opening_section(about)
        self.assertIn("$12", section)
        self.assertNotIn("Check opening hours and admission on", section)


# ── 7. [r2] Address provenance (D611) ────────────────────────────────────────

class TestAddressProvenance(unittest.TestCase):
    """The Griffin's Stop 1 showed '1 Washington St, Winchester, MA 01890' — a
    guessed address no source supports; the Griffin is at 67 Shore Road. A
    contained-venue stop's address is the venue's sourced address unless the stop's
    own page states a satellite gallery address."""

    _GRIFFIN_PAGE = (
        "We're located in Winchester. Main Gallery Address 67 Shore Road, "
        "Winchester, Ma 01890. Satellite Galleries Lafayette City Center Gallery "
        "2 Ave de Lafayette in Downtown Crossing, Boston.")

    def test_extract_venue_address_from_page(self):
        addr = am.extract_venue_address(self._GRIFFIN_PAGE)
        self.assertIn("67 Shore Road", addr)
        self.assertIn("Winchester", addr)
        self.assertRegex(addr, r"\bMA\b")   # state normalised to upper case

    def test_guessed_address_replaced_by_venue_address(self):
        # The LLM guess "1 Washington St" is on NO source → use the venue address.
        out = am.venue_bound_address(
            "1 Washington St, Winchester, MA 01890",
            "67 Shore Road, Winchester, MA 01890",
            stop_page_text="This exhibition shows photographs about labour.")
        self.assertEqual(out, "67 Shore Road, Winchester, MA 01890")

    def test_satellite_address_kept_when_on_stop_page(self):
        # When the stop's own page states the satellite address, keep it.
        out = am.venue_bound_address(
            "2 Ave de Lafayette, Boston",
            "67 Shore Road, Winchester, MA 01890",
            stop_page_text="Shown at the Griffin's Lafayette City Center Gallery, "
                           "2 Ave de Lafayette in Downtown Crossing, Boston.")
        self.assertIn("Lafayette", out)
        self.assertNotIn("Shore Road", out)

    def test_assembler_binds_contained_stops_to_venue_address(self):
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography", base_site_url=_BASE,
            requested_stops=3, available_exhibition_stops=3,
            fetcher=_griffin_fetcher,
            practical_facts="Closed on Monday. Noon–4 PM. $12")
        opening = am.build_opening_section(about)
        new = [_new("Show A", "Narration A.", address="1 Washington St, Winchester, MA 01890"),
               _new("Show B", "Narration B.", address="1 Washington St, Winchester, MA 01890"),
               _new("Show C", "Narration C.", address="1 Washington St, Winchester, MA 01890")]
        res = asm.assemble_building_tour(
            location="Griffin Museum of Photography, Winchester, MA",
            tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum",
            venue_name="Griffin Museum of Photography",
            new_stops=new, pooled_stops=[],
            opening_section=opening,
            venue_address="67 Shore Road, Winchester, MA 01890",
        )
        self.assertNotIn("1 Washington St", res.tour_text)
        self.assertIn("67 Shore Road", res.tour_text)


# ── 8. [r3] State the real hours AND admission the venue's own pages give ────

# The real Griffin case (tour 391, 2026-10-06): the live visiting section said only
# "Check opening hours and admission on griffinmuseum.org before you go." although
# the Griffin's own About page states BOTH hours and admission. The extractor read
# /plan-your-visit and /visit (hours, no price) and then DROPPED the result for
# being "too short". r3: read the About page too, MERGE hours + admission across
# the venue's pages, state what is known, and point to the site ONLY for what is
# missing.
#
# These fixtures mirror the committed tests/fixtures/griffin_about_2026.html: the
# About page carries both the hours ("Tuesday through Sunday: Noon to 4 PM. Closed:
# Every Monday …") and the admission ("General Admission: $12 for adults, $8 for
# seniors …"). The visit page carries ONLY hours (the live failure mode).

_GRIFFIN_ABOUT_FULL_HTML = (
    "<html><body>"
    "<h1>Visit Us - Griffin Museum of Photography</h1>"
    "<p>We're located in Winchester. Main Gallery Address 67 Shore Road, "
    "Winchester, MA.</p>"
    "<h2>Hours</h2>"
    "<p>Tuesday through Sunday: Noon to 4 PM. "
    "Closed: Every Monday, Easter, 4th of July, Thanksgiving, Christmas Eve, "
    "Christmas Day and New Year's Day.</p>"
    "<h2>Admission</h2>"
    "<p>General Admission: $12 for adults, $8 for seniors. "
    "Discounted: $8 for students, $8 for teachers.</p>"
    "</body></html>"
)
_GRIFFIN_VISIT_ONLY_HOURS_HTML = (
    "<html><body>"
    "<h1>Plan Your Visit</h1>"
    "<h2>Hours</h2>"
    "<p>Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.</p>"
    "</body></html>"
)


def _griffin_split_fetcher(url):
    """Hours-only on /visit and /plan-your-visit (the live failure mode); the full
    About page (both hours AND admission) on the About seeds and the home page."""
    u = url.rstrip("/").lower()
    if u.endswith("/visit") or u.endswith("/plan-your-visit"):
        return _GRIFFIN_VISIT_ONLY_HOURS_HTML, []
    if (u.endswith("/about") or u.endswith("/about-us")
            or u.endswith("/about-the-museum") or u.endswith("/history")
            or u.endswith("/mission") or u.endswith("/your-support-matters")
            or u == "https://griffinmuseum.org"):
        return _GRIFFIN_ABOUT_FULL_HTML, []
    return "", []


class TestVisitingInfoStatesKnownFacts(unittest.TestCase):
    """r3: the sourcing path surfaces the real hours AND admission the venue's own
    pages state — merged across the visit page (hours) and the About page
    (admission) — instead of dropping a hours-only result as 'too short'."""

    def setUp(self):
        import stop_pool_orchestrator as orch
        self.orch = orch

    def test_source_practical_facts_states_hours_and_admission(self):
        facts = self.orch._source_practical_facts(
            "Griffin Museum of Photography",
            "https://griffinmuseum.org",
            address="67 Shore Road, Winchester, MA",
            fetcher=_griffin_split_fetcher,
        )
        self.assertTrue(facts.strip(), "practical facts must not be empty")
        # Hours (from the visit page) are stated.
        self.assertRegex(facts, r"(?i)noon|12|4\s*PM", )
        # Admission (from the About page) is stated — the price, not dropped.
        self.assertIn("$12", facts)
        # Closed day stated.
        self.assertIn("Monday", facts)

    def test_hours_only_page_is_not_dropped_as_too_short(self):
        # Even when ONLY the hours-bearing page is reachable, the hours survive —
        # the "too short — omitting" rule is gone for the Stop-1 visiting section.
        def _hours_only(url):
            return _GRIFFIN_VISIT_ONLY_HOURS_HTML, []
        facts = self.orch._source_practical_facts(
            "Griffin Museum of Photography",
            "https://griffinmuseum.org",
            address="67 Shore Road, Winchester, MA",
            fetcher=_hours_only,
        )
        self.assertTrue(facts.strip(), "hours-only must still be stated")
        self.assertRegex(facts, r"(?i)noon|12|4\s*PM")

    def test_admission_only_page_is_not_dropped(self):
        _ADM_ONLY = (
            "<html><body><h2>Admission</h2>"
            "<p>General Admission: $12 for adults, $8 for seniors.</p>"
            "</body></html>")
        def _adm_only(url):
            return _ADM_ONLY, []
        facts = self.orch._source_practical_facts(
            "Griffin Museum of Photography",
            "https://griffinmuseum.org",
            address="67 Shore Road, Winchester, MA",
            fetcher=_adm_only,
        )
        self.assertTrue(facts.strip(), "admission-only must still be stated")
        self.assertIn("$12", facts)

    def test_opening_section_states_real_facts_end_to_end(self):
        facts = self.orch._source_practical_facts(
            "Griffin Museum of Photography",
            "https://griffinmuseum.org",
            address="67 Shore Road, Winchester, MA",
            fetcher=_griffin_split_fetcher,
        )
        about = am.build_about_stop(
            venue_name="Griffin Museum of Photography",
            base_site_url=_BASE,
            request_text="museum tour of the Griffin",
            locality="Winchester, MA",
            requested_stops=7, available_exhibition_stops=7,
            fetcher=_griffin_fetcher,
            practical_facts=facts,
        )
        section = am.build_opening_section(about)
        self.assertIn("$12", section)
        self.assertRegex(section, r"(?i)noon|4\s*PM")
        # Facts are stated, so NO website pointer is appended.
        self.assertNotIn("Check opening hours and admission on", section)


# ── 9. [r3] Partial pointer: point to the site ONLY for the missing field ────

class TestPartialPointerOnlyForMissing(unittest.TestCase):
    """D611 + r3: hours without a price (or a price without hours) is still worth
    saying. The website pointer must cover ONLY what is missing — never repeat the
    field the venue's page already gave."""

    def _about(self, practical_facts):
        return am.build_about_stop(
            venue_name="Griffin Museum of Photography", base_site_url=_BASE,
            request_text="museum tour of the Griffin", locality="Winchester, MA",
            requested_stops=7, available_exhibition_stops=7,
            fetcher=_griffin_fetcher, practical_facts=practical_facts)

    def test_hours_known_admission_missing_points_to_admission_only(self):
        # Hours+closed day stated, no price → pointer mentions admission, not hours.
        about = self._about("Closed on Monday. Noon–4 PM")
        section = am.build_opening_section(about)
        self.assertRegex(section, r"(?i)noon|4\s*PM")          # hours stated
        self.assertRegex(section, r"(?i)admission")            # pointer for the gap
        # The pointer must NOT ask the listener to check HOURS (we already have them).
        self.assertNotRegex(section, r"(?i)check (?:opening )?hours")
        self.assertRegex(section, r"(?i)admission (?:prices? |information )?(?:are |is )?(?:listed|available|on)")

    def test_admission_known_hours_missing_points_to_hours_only(self):
        about = self._about("$12 for adults, $8 for seniors")
        section = am.build_opening_section(about)
        self.assertIn("$12", section)                          # admission stated
        self.assertRegex(section, r"(?i)hours")                # pointer for the gap
        self.assertNotRegex(section, r"(?i)admission (?:prices?|information).{0,40}(?:listed|on griffin)")

    def test_both_known_no_pointer(self):
        about = self._about("Closed on Monday. Noon–4 PM. $12 for adults, $8 for seniors")
        section = am.build_opening_section(about)
        self.assertNotRegex(section, r"(?i)check .*on .*before you go")
        self.assertNotRegex(section, r"(?i)are listed on")

    def test_neither_known_full_pointer(self):
        about = self._about("")
        section = am.build_opening_section(about)
        self.assertIn("Check opening hours and admission on", section)
        # [LOCAL-616 item 2 / D617] domain-free pointer.
        self.assertNotIn("griffinmuseum.org", section)
        self.assertIn("the museum's website", section)


# ── 10. [r3] Extractor captures day-schedule hours, ignores phone/year digits ─

class TestDayScheduleHoursExtraction(unittest.TestCase):
    """r3: the venue's hours are often a weekday range + time range
    ("Monday-Thursday: 9 AM – 8 PM" — the live Boston Athenaeum). The extractor
    must capture that, and must NOT read a phone number ('(617) 720-7604') or a
    year as hours."""

    def test_day_schedule_hours_are_extracted(self):
        from visitor_facts_extractor import extract_visitor_facts_from_text
        page = ("Hours Monday-Thursday: 9 am – 8 pm Friday and Saturday: 9 am – 5 pm "
                "Sunday: Closed. Questions? Call (617) 720-7604 or email us.")
        f = extract_visitor_facts_from_text(page, 'en', venue_name="Boston Athenaeum")
        joined = " ".join(h["time"] for h in f.hours)
        self.assertRegex(joined, r"(?i)9\s*AM")
        self.assertRegex(joined, r"(?i)8\s*PM")

    def test_phone_number_is_not_read_as_hours(self):
        from visitor_facts_extractor import extract_visitor_facts_from_text
        # No real hours on the page — only a phone number. Nothing must be invented.
        page = ("Contact our membership team at (617) 720-7604 or email "
                "membership@example.org. We are at 10 Beacon Street.")
        f = extract_visitor_facts_from_text(page, 'en', venue_name="Boston Athenaeum")
        joined = " ".join(h["time"] for h in f.hours)
        self.assertNotIn("20–76", joined)
        self.assertNotIn("20-76", joined)

    def test_griffin_noon_to_4pm_still_extracted(self):
        from visitor_facts_extractor import extract_visitor_facts_from_text
        page = ("Hours Tuesday through Sunday: Noon to 4 PM. Closed: Every Monday.")
        f = extract_visitor_facts_from_text(page, 'en',
                                            venue_name="Griffin Museum of Photography")
        joined = " ".join(h["time"] for h in f.hours).lower()
        self.assertIn("4 pm", joined)
        self.assertRegex(joined, r"noon|12")


# ── 11. [r3] Home-page nav-link discovery reaches the real visiting page ─────

class TestVisitingLinkDiscovery(unittest.TestCase):
    """r3: the real visiting-facts page is a venue-specific slug the fixed seeds
    miss (the live Griffin uses /about-the-griffin-2026/). Discovery follows the
    home page's OWN navigation links by meaning (Visit / Hours / Admission / About)
    and stays on the venue's domain."""

    _HOME = (
        "<html><body><nav>"
        "<a href='/about-the-griffin-2026/'>Visit</a>"
        "<a href='/current-exhibitions/'>On View</a>"
        "<a href='https://facebook.com/x'>Follow us</a>"
        "<a href='/membership/'>Membership</a>"
        "</nav></body></html>")

    def setUp(self):
        import stop_pool_orchestrator as orch
        self.orch = orch

    def _fetch(self, url):
        if url.rstrip("/") == "https://griffinmuseum.org":
            return self._HOME, []
        return "", []

    def test_discovers_venue_specific_visit_slug(self):
        urls = self.orch._discover_visiting_urls("https://griffinmuseum.org", self._fetch)
        self.assertTrue(any("about-the-griffin-2026" in u for u in urls),
                        f"should follow the Visit nav link: {urls}")

    def test_stays_on_venue_domain(self):
        urls = self.orch._discover_visiting_urls("https://griffinmuseum.org", self._fetch)
        for u in urls:
            self.assertIn("griffinmuseum.org", u)
            self.assertNotIn("facebook.com", u)


if __name__ == "__main__":
    unittest.main(verbosity=2)
