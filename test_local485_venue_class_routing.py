#!/usr/bin/env python3
"""LOCAL-485 — A Church Is Not A Museum.

Michael, build 26, 2026-09-16, requested a 2-stop tour of "Our Lady Help of
Christians, Catholic Church in Newton MA". It is a real, large, historic parish
church at 573 Washington St. The request ran 31s and was rejected with
"This venue could not be verified with enough works to generate a quality tour."

Root cause: the church was routed down the MUSEUM pipeline. Asked for *artworks*
and having none catalogued, the model answered with the two most famous religious
artworks on earth — the Sistine Chapel Ceiling (6,700 km away) and The Last Supper
(Milan) — then the museum gate (working exactly as designed) clean-failed the run
`unresolvable` because a parish church has no Wikidata artwork inventory.

Two defects, both fixed and proven here:

  1. Venue class must decide the stop type. A church/cathedral/synagogue/temple/
     courthouse/town-hall is a PLACE venue: its stops are places (nave, bell
     tower, war memorial, parish hall, cemetery), verifiable the way a walking
     tour's stops are — NOT catalogued works. It must route to the place-based
     (walking) path, the same path Michael's approved Cimiez tour used.

  2. The "not enough works" error was a catch-all `else` lying about the cause.
     `thin_evidence` now gets its own honest, venue-NAMED message.

Per LOCAL-465, the WIRING is proven separately from the FUNCTION: the pure
functions are unit-tested directly, and the integration into generate_tour_text()
and the service layer is guarded by SOURCE ASSERTIONS so a revert of the wiring
breaks a test even when the pure functions still pass.

Per D242, run it and paste the real output. `exit=0` proves nothing.

The venue-class detector is ONE mechanism shared with LOCAL-480's facility class:
_detect_facility_class is a thin wrapper over _detect_venue_class. AC5 is proven
by test_shared_mechanism_one_detector.
"""
import os
import re
import sys
import inspect
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import generate_tour_text as gtt


# ─────────────────────────────────────────────────────────────────────────────
# Faithful reproduction of the inline category-convergence logic in
# generate_tour_text(). We cannot call generate_tour_text() offline (it makes
# live LLM/SPARQL calls), so this mirror runs the EXACT sequence of category
# decisions the function applies after intent extraction, using the real module
# helpers. The source assertions below prove this mirror stays faithful: if the
# wiring is reverted, both the mirror's behaviour AND a source assertion go red.
# ─────────────────────────────────────────────────────────────────────────────
def route_category(location, tour_type="", venue_name=None, transport_mode="on_foot",
                   intent_ok=True):
    """Reproduce generate_tour_text()'s tour_category decision for a request.

    Models the three decision points the church defect passed through:
      S15 force-museum, _classify_tour_category, CLASSIFY-FIX, VENUE-CLASS GUARD.
    """
    _EXPLICIT_NON_MUSEUM_TOUR_RE = gtt._EXPLICIT_NON_MUSEUM_TOUR_RE
    _MULTI_BUILDING_INSTITUTION_RE = gtt._MULTI_BUILDING_INSTITUTION_RE

    tour_category = None
    if intent_ok:
        # S15 force-museum (with the LOCAL-485 worship/civic exclusion)
        if (venue_name and transport_mode == 'on_foot'
                and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location)
                and not _MULTI_BUILDING_INSTITUTION_RE.search(location)
                and not gtt._detect_worship_civic_class(location, tour_type)):
            tour_category = 'museum'
        else:
            _effective_tour_type = "" if (transport_mode != 'on_foot') else tour_type
            tour_category = gtt._classify_tour_category(location, _effective_tour_type)
            if tour_category == 'specialized':
                tour_category = 'book'
    else:
        _effective_tour_type = "" if (transport_mode != 'on_foot') else tour_type
        tour_category = gtt._classify_tour_category(location, _effective_tour_type)
        if tour_category == 'specialized':
            tour_category = 'book'

    # CLASSIFY-FIX (walking → museum on venue words)
    _VENUE_WORDS_FOR_CLASSIFY = {'museum', 'musée', 'musee', 'gallery', 'galleria', 'palais',
                                 'palazzo', 'palace', 'castle', 'château', 'house', 'mansion',
                                 'library', 'institute', 'villa'}
    if tour_category == 'walking':
        _loc_words = set(location.lower().split())
        if _loc_words & _VENUE_WORDS_FOR_CLASSIFY:
            tour_category = 'museum'

    # VENUE-CLASS GUARD (museum → walking for worship/civic, non-facility)
    if (tour_category == 'museum'
            and not gtt._detect_facility_class(location, tour_type)
            and gtt._detect_worship_civic_class(location, tour_type)):
        tour_category = 'walking'

    return tour_category


class TestVenueClassDetector(unittest.TestCase):
    """AC1/AC5: the shared detector recognises worship/civic venue classes."""

    def test_church_is_worship_civic(self):
        self.assertEqual(
            gtt._detect_venue_class(
                'tour of Our Lady Help of Christians Catholic Church located in Newton MA'),
            'worship_civic')

    def test_cathedral_basilica_synagogue_mosque_temple_courthouse_townhall(self):
        for loc in [
            "St. Patrick's Cathedral, New York",
            "Basilica of the National Shrine, Washington DC",
            "Temple Emanu-El, Manhattan",
            "Central Synagogue, New York",
            "Islamic Center mosque, Boston",
            "Middlesex County Courthouse, Cambridge MA",
            "Newton Town Hall, Newton MA",
            "Westminster Abbey, London",
        ]:
            self.assertEqual(gtt._detect_venue_class(loc), 'worship_civic',
                             f"expected worship_civic for {loc!r}")

    def test_cimiez_is_not_a_venue_class(self):
        """AC3: Cimiez names no venue class — detector returns None."""
        self.assertIsNone(
            gtt._detect_venue_class('Walking tour around Cimiez District, Nice, France'))

    def test_plain_museum_is_not_worship_civic(self):
        for loc in ["Museum of Fine Arts, Boston", "Louvre Museum", "Uffizi Gallery"]:
            self.assertIsNone(gtt._detect_venue_class(loc),
                              f"museum should not be a worship/civic class: {loc!r}")

    def test_facility_takes_priority_over_worship(self):
        """An airport chapel is a facility errand, not a worship-tour venue."""
        self.assertEqual(gtt._detect_venue_class('chapel at Logan Airport terminal'),
                         'facility')

    def test_no_false_match_inside_larger_words(self):
        # 'churchill', 'temperature' must not trip the word-boundary detector.
        self.assertIsNone(gtt._detect_venue_class('Churchill War Rooms, London'))
        self.assertIsNone(gtt._detect_venue_class('temperature museum'))


class TestSharedMechanism(unittest.TestCase):
    """AC5: one detector, not two — _detect_facility_class delegates to it."""

    def test_shared_mechanism_one_detector(self):
        # facility wrapper must be the shared detector's 'facility' verdict.
        for loc in ['Logan Airport', 'South Station terminal', 'Massachusetts General Hospital']:
            self.assertTrue(gtt._detect_facility_class(loc))
            self.assertEqual(gtt._detect_venue_class(loc), 'facility')
        # A worship/civic venue is NOT a facility.
        self.assertFalse(gtt._detect_facility_class(
            'tour of Our Lady Help of Christians Catholic Church, Newton MA'))
        # Source assertion: the wrapper is defined in terms of _detect_venue_class.
        src = inspect.getsource(gtt._detect_facility_class)
        self.assertIn('_detect_venue_class', src,
                      "_detect_facility_class must delegate to the shared detector")


class TestChurchRoutesToPlaceNotMuseum(unittest.TestCase):
    """AC1/AC2: the reported request routes to the place path, never museum."""

    LOC = 'tour of Our Lady Help of Christians Catholic Church located in Newton MA'

    def test_classify_returns_walking(self):
        self.assertEqual(gtt._classify_tour_category(self.LOC, ''), 'walking')

    def test_full_route_walking_even_when_s15_would_fire(self):
        # Reproduces build-26 conditions: intent extracted a venue_name, on_foot.
        # Before the fix this returned 'museum' (the defect). Now 'walking'.
        cat = route_category(self.LOC, '', venue_name='Our Lady Help of Christians',
                             transport_mode='on_foot', intent_ok=True)
        self.assertEqual(cat, 'walking',
                         "church must route to the place-based path, not the museum pipeline")

    def test_full_route_walking_when_intent_failed(self):
        cat = route_category(self.LOC, '', venue_name=None, intent_ok=False)
        self.assertEqual(cat, 'walking')

    def test_venue_class_guard_catches_a_forced_museum(self):
        # Even if some upstream branch set museum, the GUARD pulls it back.
        cat = route_category('St. Patrick Church, Newton MA', '',
                             venue_name='St. Patrick Church', intent_ok=True)
        self.assertEqual(cat, 'walking')


class TestMuseumRegression(unittest.TestCase):
    """AC3: a genuine museum still routes to the museum path."""

    def test_real_museums_route_to_museum(self):
        for loc in ["Museum of Fine Arts, Boston", "Louvre Museum, Paris",
                    "The Metropolitan Museum of Art, New York"]:
            self.assertEqual(gtt._classify_tour_category(loc, ''), 'museum',
                             f"{loc!r} must stay a museum tour")

    def test_museum_full_route_stays_museum(self):
        cat = route_category("Museum of Fine Arts, Boston", '',
                             venue_name="Museum of Fine Arts", intent_ok=True)
        self.assertEqual(cat, 'museum')

    def test_cimiez_walking_tour_unchanged(self):
        """AC3: Michael's approved Cimiez walking tour stays 'walking'.

        The request names no venue class and carries an explicit "walking tour"
        phrase; both the detector and the classifier must leave it untouched.
        """
        loc = 'Walking tour around Cimiez District, Nice, France'
        self.assertIsNone(gtt._detect_venue_class(loc))
        self.assertEqual(gtt._classify_tour_category(loc, ''), 'walking')
        self.assertEqual(route_category(loc, '', venue_name=None, intent_ok=True), 'walking')


class TestWiringSourceAssertions(unittest.TestCase):
    """LOCAL-465: guard the wiring so a revert goes red even if functions pass."""

    def setUp(self):
        self.src = inspect.getsource(gtt)

    def test_worship_civic_words_removed_from_museum_flip(self):
        # These words used to force walking → museum. They must be gone from the set.
        m = re.search(r'_VENUE_WORDS_FOR_CLASSIFY\s*=\s*\{(.*?)\}', self.src, re.DOTALL)
        self.assertIsNotNone(m, "could not find _VENUE_WORDS_FOR_CLASSIFY literal")
        block = m.group(1)
        for w in ('church', 'cathedral', 'basilica', 'temple', 'abbey'):
            self.assertNotIn(f"'{w}'", block,
                             f"worship/civic word {w!r} must not force walking→museum")

    def test_venue_class_guard_present(self):
        self.assertIn('VENUE-CLASS GUARD', self.src)
        self.assertIn('_detect_worship_civic_class(location, tour_type)', self.src)

    def test_s15_excludes_worship_civic(self):
        # The S15 force-museum condition must include the worship/civic exclusion.
        self.assertIn('and not _detect_worship_civic_class(location, tour_type)', self.src)

    def test_classifier_routes_worship_civic_to_place(self):
        csrc = inspect.getsource(gtt._classify_tour_category)
        self.assertIn('_detect_worship_civic_class', csrc)


class TestBreakTheRoutingGoesRed(unittest.TestCase):
    """AC6: break the routing and show a test go red.

    We monkeypatch the worship/civic detector to always return False (simulating
    a revert of the routing). The church then flows exactly as it did in build 26:
    S15 forces museum. This test asserts that breakage IS detected — i.e. under
    the break, the church routes to 'museum', which is the bug. It proves the
    routing is what protects the church: with the detector live it is 'walking';
    broken, it is 'museum'.
    """

    LOC = 'tour of Our Lady Help of Christians Catholic Church located in Newton MA'

    def test_break_routing_regresses_to_museum(self):
        # Sanity: with the real detector, the church is 'walking'.
        self.assertEqual(
            route_category(self.LOC, '', venue_name='Our Lady Help of Christians',
                           intent_ok=True),
            'walking')

        original = gtt._detect_worship_civic_class
        try:
            gtt._detect_worship_civic_class = lambda location, tour_type="": False
            broken = route_category(self.LOC, '', venue_name='Our Lady Help of Christians',
                                    intent_ok=True)
        finally:
            gtt._detect_worship_civic_class = original

        # Under the break, the fix is gone and the defect returns: museum pipeline.
        self.assertEqual(broken, 'museum',
                         "breaking the detector must re-expose the build-26 defect")
        # And critically: the two are different — the routing is load-bearing.
        self.assertNotEqual(broken, 'walking')


class TestServiceMessageNamesVenue(unittest.TestCase):
    """AC4: thin_evidence gets its own message, naming the venue.

    Verified by source assertion on generate_tour_text_service.py (the service
    cannot be imported offline without Flask/DB wiring), plus a check that the
    evidence dict now carries the venue name in generate_tour_text.py.
    """

    def _service_src(self):
        path = os.path.join(os.path.dirname(__file__), 'generate_tour_text_service.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_thin_evidence_branch_exists_and_is_not_the_catchall(self):
        s = self._service_src()
        self.assertIn('error_type") == "thin_evidence"', s,
                      "service must branch on thin_evidence explicitly")
        # The honest message and the neighbourhood-walking suggestion.
        self.assertIn('could not find enough verified material', s)
        self.assertIn('walking tour of the surrounding neighbourhood', s)
        # And it must name the venue, not use the museum catch-all string.
        self.assertRegex(s, r'thin_evidence[\s\S]{0,600}?_LAST_CLEAN_FAIL_EVIDENCE\.get\("venue"\)')

    def test_evidence_dict_carries_venue_name(self):
        gsrc = inspect.getsource(gtt)
        # Both thin_evidence clean-fail dicts must include a "venue" key.
        n = len(re.findall(r'"error_type":\s*"thin_evidence"', gsrc))
        self.assertGreaterEqual(n, 2, "expected the two thin_evidence clean-fail sites")
        n_venue = len(re.findall(r'"venue":\s*_museum_venue_name or location', gsrc))
        self.assertEqual(n_venue, n,
                         "every thin_evidence clean-fail must carry the venue name")


if __name__ == '__main__':
    unittest.main(verbosity=2)
