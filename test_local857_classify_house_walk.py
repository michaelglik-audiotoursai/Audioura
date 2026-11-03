#!/usr/bin/env python3
"""LOCAL-857 — "house" must not turn a city walk into a museum tour.

Field defect (GCloud_Storied_1, 2026-11-03, gen 00029-plj, request 331, job
c6afda0b): "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City" was
REFUSED. Two defects chained:

  1. CLASSIFY-FIX's bag-of-words venue scan saw the word "house" (Saigon Opera
     HOUSE) and promoted the walking request to 'museum':
       [CLASSIFY-FIX] Location contains venue word 'house' — overriding walking → museum
  2. The museum path's BLOCKER4b address-scatter guard then rejected the five
     correct landmarks as a "city-wide museum tour", and the tour was refused —
     two of the best-known places in Ho Chi Minh City.

The fix (two parts, proven here):

  A. CLASSIFY-FIX matches on TOKEN SEQUENCES, not a bag of words. A venue word
     does NOT promote walking->museum when
        (a) the request asks for a multi-place walk/stroll/ride/drive/"tour of"
            (walking signal, comma list, or "X and Y" list of named places), or
        (b) the venue word belongs to a COMPOUND BUILDING NAME that is not a
            collection ("Opera House", "Custom House", "State House", "Coffee
            House", "Guest House", "Public House", "Town House", "Market", ...).
     A single-venue house museum ("House of the Seven Gables") still promotes.

  B. Safety net: when the museum path's BLOCKER4b sees >=3 distinct real
     addresses across a CITY and the request was ORIGINALLY classified walking,
     the run falls back to the walking path and logs
        [LOCAL-857] museum->walking fallback (address scatter, N addresses)
     instead of refusing.

Per LOCAL-465 / D242: the pure functions are unit-tested directly, and the inline
WIRING is guarded by SOURCE ASSERTIONS so a revert of the wiring goes red even if
the functions still pass. The CLASSIFY-FIX decision is reproduced by a faithful
mirror that calls the REAL module helpers; a source assertion keeps it faithful.
"""
import os
import re
import sys
import inspect
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import generate_tour_text as gtt


# The venue-word set lives inside _generate_tour_text_impl() (a local). Mirror it
# here; test_venue_word_set_unchanged below asserts the real literal still matches
# so this copy cannot silently drift.
_VENUE_WORDS_FOR_CLASSIFY = {'museum', 'musée', 'musee', 'gallery', 'galleria', 'palais',
                             'palazzo', 'palace', 'castle', 'château', 'house', 'mansion',
                             'library', 'institute', 'villa'}


def classify_fix_category(location, tour_type=""):
    """Faithful mirror of generate_tour_text()'s category decision AFTER the
    LOCAL-857 CLASSIFY-FIX guard. Calls the REAL module helpers so the mirror
    cannot drift from the inline behaviour without a source assertion going red.
    """
    tour_category = gtt._classify_tour_category(location, tour_type)
    if tour_category == 'specialized':
        tour_category = 'book'
    if tour_category == 'walking':
        _loc_words = set(location.lower().split())
        _matched = _loc_words & _VENUE_WORDS_FOR_CLASSIFY
        if _matched:
            _promote = [w for w in sorted(_matched)
                        if gtt._classify_fix_should_promote_to_museum(location, tour_type, w)]
            if _promote:
                tour_category = 'museum'
    return tour_category


class TestReportedFieldRequest(unittest.TestCase):
    """The exact field string must classify walking, never museum."""

    LOC = "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"

    def test_field_request_is_walking(self):
        self.assertEqual(classify_fix_category(self.LOC), 'walking',
                         "a city walk naming Opera House must not become a museum tour")

    def test_classifier_alone_is_walking(self):
        # The base classifier already sees the walk signal; CLASSIFY-FIX must not undo it.
        self.assertEqual(gtt._classify_tour_category(self.LOC, ''), 'walking')

    def test_guard_holds_on_house(self):
        # The venue word 'house' must NOT justify promotion for this request.
        self.assertFalse(
            gtt._classify_fix_should_promote_to_museum(self.LOC, '', 'house'))


class TestSydneyOperaHouseNeverRefused(unittest.TestCase):
    """"Sydney Opera House" alone -> walking or venue-tour, never museum-refused.

    It carries no walking signal, but "Opera House" is a compound building name,
    not a collection, so CLASSIFY-FIX must not promote it into the museum pipeline
    (whose BLOCKER4b refused the field request).
    """

    def test_sydney_opera_house_not_promoted_to_museum(self):
        self.assertEqual(classify_fix_category("Sydney Opera House"), 'walking')

    def test_opera_house_is_a_compound(self):
        self.assertTrue(gtt._classify_fix_venue_word_is_compound("Sydney Opera House", 'house'))


class TestCompoundBuildingNames(unittest.TestCase):
    """Compound "<X> House" / "Market" building names are not collections."""

    COMPOUNDS = [
        "Sydney Opera House",
        "Custom House, Dublin",
        "Customs House, Shanghai",
        "Massachusetts State House, Boston",
        "The Coffee House, Hanoi",
        "Guest House on Main St",
        "The Crown Public House",
        "Old Town House, Cape Town",
        "County Court House",
        "Ben Thanh Market",
    ]

    def test_compounds_not_promoted(self):
        # The point is that a compound building word never flips the request into
        # the museum pipeline (whose BLOCKER4b refused the field request). A
        # café-style "Coffee House" legitimately routes 'restaurant' (a places
        # request); what must never happen is 'museum'.
        for loc in self.COMPOUNDS:
            cat = classify_fix_category(loc)
            self.assertNotEqual(cat, 'museum',
                                f"{loc!r} is a compound building/market, not a museum: got {cat}")


class TestMuseumCasesUnchanged(unittest.TestCase):
    """The five museum cases named in the ticket stay museum."""

    MUSEUMS = [
        "Palais Lascaris, Nice",
        "Isabella Stewart Gardner Museum",
        "Frick Collection",
        "Hearst Castle",
        "House of the Seven Gables",  # a single-venue house museum
    ]

    def test_museum_cases_stay_museum(self):
        for loc in self.MUSEUMS:
            self.assertEqual(classify_fix_category(loc), 'museum',
                             f"{loc!r} must stay a museum tour")

    def test_house_museum_still_promotes(self):
        # "House of the Seven Gables": 'house' leads the name (not a compound),
        # and there is no multi-place walk signal -> promotion is allowed.
        self.assertTrue(
            gtt._classify_fix_should_promote_to_museum("House of the Seven Gables", '', 'house'))
        self.assertFalse(
            gtt._classify_fix_venue_word_is_compound("House of the Seven Gables", 'house'))


class TestMultiPlaceWalkDetection(unittest.TestCase):
    """A multi-place walk/stroll/ride/drive/tour-of stays on the walking path."""

    def test_walk_word(self):
        self.assertTrue(gtt._classify_fix_requests_multi_place_walk(
            "Saigon Opera House walk", ""))

    def test_stroll_word(self):
        self.assertTrue(gtt._classify_fix_requests_multi_place_walk(
            "A stroll past the State House and the Gardens", ""))

    def test_tour_of_several(self):
        self.assertTrue(gtt._classify_fix_requests_multi_place_walk(
            "tour of the Opera House and the Market", ""))

    def test_and_list_of_places(self):
        self.assertTrue(gtt._classify_fix_requests_multi_place_walk(
            "Ben Thanh Market and Saigon Opera House, Ho Chi Minh City", ""))

    def test_ride_drive(self):
        self.assertTrue(gtt._classify_fix_requests_multi_place_walk(
            "A drive past the Opera House and the harbour", ""))

    def test_single_house_museum_is_not_a_multi_place_walk(self):
        self.assertFalse(gtt._classify_fix_requests_multi_place_walk(
            "House of the Seven Gables", ""))
        self.assertFalse(gtt._classify_fix_requests_multi_place_walk(
            "Palais Lascaris, Nice", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Part B: the BLOCKER4b museum->walking fallback decision.
# ─────────────────────────────────────────────────────────────────────────────
def blocker4b_fallback_decision(category_before_classify_fix, scatter_n, scope_precision):
    """Mirror of the inline BLOCKER4b fallback gate (LOCAL-857). Returns True when
    the run should FALL BACK to walking instead of refusing."""
    _orig_walking = (category_before_classify_fix == 'walking')
    _scope_is_city = (scope_precision or '').upper() not in ('BUILDING', 'CORRIDOR')
    return _orig_walking and scatter_n >= 3 and _scope_is_city


class TestBlocker4bFallback(unittest.TestCase):
    def test_fallback_when_originally_walking_and_scattered_in_city(self):
        self.assertTrue(blocker4b_fallback_decision('walking', 5, 'CITY'))
        self.assertTrue(blocker4b_fallback_decision('walking', 3, 'DISTRICT'))
        self.assertTrue(blocker4b_fallback_decision('walking', 5, ''))

    def test_no_fallback_when_originally_museum(self):
        # A genuine museum request that scatters must still be refused (Palais etc.).
        self.assertFalse(blocker4b_fallback_decision('museum', 6, 'BUILDING'))
        self.assertFalse(blocker4b_fallback_decision('museum', 6, 'CITY'))

    def test_no_fallback_below_three_addresses(self):
        self.assertFalse(blocker4b_fallback_decision('walking', 2, 'CITY'))

    def test_no_fallback_for_single_building_scope(self):
        self.assertFalse(blocker4b_fallback_decision('walking', 5, 'BUILDING'))


# ─────────────────────────────────────────────────────────────────────────────
# Wiring source assertions (LOCAL-465): a revert of the inline wiring goes red.
# ─────────────────────────────────────────────────────────────────────────────
class TestWiringSourceAssertions(unittest.TestCase):
    def setUp(self):
        self.src = inspect.getsource(gtt)
        self.impl = inspect.getsource(gtt._generate_tour_text_impl)

    def test_classify_fix_consults_the_guard(self):
        self.assertIn('_classify_fix_should_promote_to_museum', self.impl,
                      "CLASSIFY-FIX must gate promotion through the LOCAL-857 guard")

    def test_classify_fix_no_longer_blind_pop(self):
        # The old bag-of-words pop (".pop()") that caused the defect must be gone.
        self.assertNotIn("_VENUE_WORDS_FOR_CLASSIFY).pop()", self.impl,
                         "the blind bag-of-words promotion must be gone")

    def test_venue_word_set_unchanged(self):
        # The mirror's copy of the set must match the real inline literal.
        m = re.search(r'_VENUE_WORDS_FOR_CLASSIFY\s*=\s*\{(.*?)\}', self.impl, re.DOTALL)
        self.assertIsNotNone(m, "could not find _VENUE_WORDS_FOR_CLASSIFY literal")
        real = set(re.findall(r"'([^']+)'", m.group(1)))
        self.assertEqual(real, _VENUE_WORDS_FOR_CLASSIFY,
                         "mirror set drifted from the real literal — update the mirror")

    def test_blocker4b_fallback_present(self):
        self.assertIn('museum→walking fallback (address scatter,', self.impl)
        self.assertIn('_category_before_classify_fix', self.impl)

    def test_category_recorded_before_classify_fix(self):
        # The pre-override snapshot must be taken, and taken BEFORE the override.
        self.assertIn('_category_before_classify_fix = tour_category', self.impl)
        snap = self.impl.index('_category_before_classify_fix = tour_category')
        override = self.impl.index("overriding walking → museum")
        self.assertLess(snap, override,
                        "the category snapshot must be taken before the CLASSIFY-FIX override")


# ─────────────────────────────────────────────────────────────────────────────
# Break-the-fix: with the guard neutralised, the field request regresses to the
# defect (museum). Proves the guard is load-bearing (LOCAL-485 AC6 pattern).
# ─────────────────────────────────────────────────────────────────────────────
class TestBreakTheGuardGoesRed(unittest.TestCase):
    LOC = "Ben Thanh Market and Saigon Opera House walk, Ho Chi Minh City"

    def test_break_guard_regresses_to_museum(self):
        # With the real guard, the field request is walking.
        self.assertEqual(classify_fix_category(self.LOC), 'walking')

        original = gtt._classify_fix_should_promote_to_museum
        try:
            gtt._classify_fix_should_promote_to_museum = (
                lambda location, tour_type, matched_word: True)
            broken = classify_fix_category(self.LOC)
        finally:
            gtt._classify_fix_should_promote_to_museum = original

        self.assertEqual(broken, 'museum',
                         "neutralising the guard must re-expose the build defect")
        self.assertNotEqual(broken, 'walking')


if __name__ == '__main__':
    unittest.main(verbosity=2)
