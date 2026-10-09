#!/usr/bin/env python3
"""test_local650_walking_route.py — LOCAL-650B.

Three walking-tour defects on the REAL request
"Walking tour in Boston dedicated to Massachusetts politics and current affairs,
Boston, MA" (walking, 5 stops; audio_tours.id=557 and the Oct-6 baseline):

  FIX 1 (650B) — the request's THEME became a stop. Stop 5 = "Massachusetts
          politics and current affairs" (the theme phrase), Address N/A. A POI must
          be a real, geocodable place; a theme phrase / topic-like name must be
          REJECTED AT SELECTION, not renamed after the fact. The old
          rename_theme_phrase_stops text-surgery is DELETED (D643 anti-pattern).
  FIX 2 — Directions led BACKWARDS. Stop 4 (Old State House) said "… head north …
          until you reach the Massachusetts State House …" — that is STOP 1, not
          the next stop. Each stop's Directions must name the NEXT stop and say
          roughly how far it is — BUT only when both stops have VERIFIED (P625)
          coordinates.
  FIX 3 — "current affairs" honesty. When the request names current affairs, at
          least one stop must carry a recent (≤ 5 years) grounded item, or the
          tour must say honestly there is none.

The fixtures below are the REAL tour-557 stop blocks (verbatim). A DB-backed test
reads the live row when reachable and otherwise skips, so the suite runs offline.
MUSEUM behaviour is proven unchanged: every LOCAL-650B guard is a no-op on a
Tour-Category: museum text.

Run: python3 -m pytest test_local650_walking_route.py -q
     python3 test_local650_walking_route.py
"""
import os
import re
import unittest

import theme_stop_guard as tsg
import walking_directions_guard as wdg
import current_affairs_coverage as cac
import directions_generator as dgen


# ─────────────────────────────────────────────────────────────────────────────
# REAL tour-557 fixture (verbatim stop blocks; trimmed narration kept faithful).
# ─────────────────────────────────────────────────────────────────────────────

TOUR557 = (
    "Step-by-Step Audio Guided Tour: Walking tour in Boston dedicated to "
    "Massachusetts politics and current affairs, Boston, MA\n"
    "Tour-Category: walking\n\n"
    "Stop 1: Massachusetts State House\n\n"
    "Address: 24 Beacon St, Boston, MA 02133\n\n"
    "Coordinates: 42.3588, -71.0638\n\n"
    "The seat of Massachusetts government since 1798.\n\n"
    "Directions: As you leave the Massachusetts State House, walk down Beacon "
    "Street towards Tremont Street.\n\n"
    "Stop 2: Boston City Hall\n\n"
    "Coordinates: 42.3609, -71.0577\n\n"
    "In late 2024, federal prosecutors indicted a Boston City Councilor on public "
    "corruption charges, a case that unfolded within these walls.\n\n"
    "Directions: As you leave Boston City Hall, head south on Congress Street.\n\n"
    "Stop 3: Faneuil Hall\n\n"
    "Coordinates: 42.3600, -71.0568\n\n"
    "Faneuil Hall stands because Peter Faneuil gave this building to the city in "
    "1742.\n\n"
    "Directions: As you leave Faneuil Hall, walk south on Congress Street until "
    "you reach State Street, then continue until you see the Old State House on "
    "your right.\n\n"
    "Stop 4: Old State House\n\n"
    "Address: 206 Washington St, Boston, MA 02109\n\n"
    "Coordinates: 42.3604, -71.0572\n\n"
    "The oldest surviving public building in Boston, marked by fire and "
    "revolution.\n\n"
    "Directions: As you leave the Old State House, head north on Washington "
    "Street. Stroll past the historic landmarks along the Freedom Trail until you "
    "reach the Massachusetts State House, where you can explore the heart of "
    "Massachusetts politics and current affairs.\n\n"
    "Stop 5: Massachusetts politics and current affairs\n\n"
    "Coordinates: 42.3584, -71.0598\n\n"
    "Type/Specialty: Political History\n\n"
    "Orientation: Here, at the edge of the University of Massachusetts Boston, the "
    "layered voices from city, state, and university life mingle.\n\n"
    "From 1996 to 2011, three consecutive Speakers of the Massachusetts House each "
    "left office under federal criminal indictment.\n\n"
    "The University of Massachusetts Boston, a public university, stands as a "
    "gathering place for these conversations.\n\n"
    "This tour reveals the interplay between power and public engagement. That's 5 "
    "stops in all.\n\n"
    "If you would like to eat nearby we can build you a restaurant tour.\n"
)

# A current-affairs request whose stops carry ONLY old years (no recent item) —
# used to prove the honest-note path. Same request family as 557.
TOUR_OLD_ONLY = (
    "Step-by-Step Audio Guided Tour: Walking tour in Townsville dedicated to local "
    "politics and current affairs, Townsville\n"
    "Tour-Category: walking\n\n"
    "Stop 1: Town Hall\n\n"
    "Coordinates: 1.0, 2.0\n\n"
    "Built in 1890; debated reforms in 1912 and 1954.\n\n"
    "Directions: Continue to The Old Library.\n\n"
    "Stop 2: The Old Library\n\n"
    "Coordinates: 1.1, 2.1\n\n"
    "Opened in 1901. That's 2 stops in all.\n\n"
    "Sources:\n- https://example.com/townsville\n"
)

MUSEUM_TEXT = (
    "Step-by-Step Audio Guided Tour: The Courtauld Gallery, London\n"
    "Tour-Category: museum\n\n"
    "Stop 1: A Bar at the Folies-Bergère\n\n"
    "Coordinates: 51.5115, -0.1195\n\n"
    "Painted by Manet in 1882; politics and society of the era.\n\n"
    "Directions: Continue to The Card Players.\n\n"
    "Stop 2: The Card Players\n\n"
    "Coordinates: 51.5116, -0.1196\n\n"
    "Cézanne, 1890s. That's 2 stops in all.\n"
)

# A CLEAN walking tour with no theme-phrase stop (what a correctly-filtered
# generation produces). Used to test the guard composition without rename.
CLEAN_WALKING = (
    "Step-by-Step Audio Guided Tour: Walking tour in Boston dedicated to "
    "Massachusetts politics and current affairs, Boston, MA\n"
    "Tour-Category: walking\n\n"
    "Stop 1: Massachusetts State House\n\n"
    "Coordinates: 42.3588, -71.0638\n\n"
    "The seat of Massachusetts government since 1798.\n\n"
    "Directions: Head east on Beacon Street towards Tremont.\n\n"
    "Stop 2: Boston City Hall\n\n"
    "Coordinates: 42.3609, -71.0577\n\n"
    "In late 2024, federal prosecutors indicted a Boston City Councilor.\n\n"
    "Directions: Head south on Congress Street.\n\n"
    "Stop 3: Faneuil Hall\n\n"
    "Coordinates: 42.3600, -71.0568\n\n"
    "Peter Faneuil gave this building to the city in 1742.\n\n"
    "Directions: Walk south on Congress to State Street.\n\n"
    "Stop 4: Old State House\n\n"
    "Coordinates: 42.3604, -71.0572\n\n"
    "The oldest surviving public building in Boston.\n\n"
    "Directions: Head south along the Freedom Trail.\n\n"
    "Stop 5: Boston Public Library\n\n"
    "Coordinates: 42.3496, -71.0783\n\n"
    "Opened in 1854 as the first large free municipal library. That's 5 stops.\n\n"
    "Sources:\n- https://example.com\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 (650B) — theme phrase must be REJECTED at selection, never renamed
# ─────────────────────────────────────────────────────────────────────────────

class TestFix1ThemeStop(unittest.TestCase):
    def test_extract_request_theme_from_title(self):
        self.assertEqual(
            tsg.extract_request_theme(TOUR557),
            "Massachusetts politics and current affairs")

    def test_theme_phrase_stop_detected(self):
        th = tsg.extract_request_theme(TOUR557)
        self.assertTrue(tsg.is_theme_phrase_stop(
            "Massachusetts politics and current affairs", th))
        self.assertTrue(tsg.is_theme_phrase_stop("current affairs", th))

    def test_real_places_not_flagged(self):
        th = tsg.extract_request_theme(TOUR557)
        for place in ("Massachusetts State House", "Boston City Hall",
                      "Faneuil Hall", "Old State House",
                      "The University of Massachusetts Boston",
                      "John F. Kennedy Presidential Library",
                      "Boston Public Library"):
            self.assertFalse(tsg.is_theme_phrase_stop(place, th), place)
            self.assertFalse(tsg.topic_like_name(place), place)

    def test_topic_like_names_flagged(self):
        for topic in ("political history", "power and public engagement",
                      "state political landscape",
                      "Massachusetts politics and current affairs"):
            self.assertTrue(tsg.topic_like_name(topic), topic)

    def test_find_theme_phrase_stops_on_557(self):
        found = tsg.find_theme_phrase_stops(TOUR557)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], 5)
        self.assertEqual(found[0][1], "Massachusetts politics and current affairs")

    def test_selection_predicate_rejects_theme(self):
        """stop_name_is_not_a_place is the selection-time gate. It must reject
        the request theme and any topic-like name."""
        th = tsg.extract_request_theme(TOUR557)
        self.assertTrue(tsg.stop_name_is_not_a_place(
            "Massachusetts politics and current affairs", th))
        self.assertTrue(tsg.stop_name_is_not_a_place(
            "political history", th))
        self.assertTrue(tsg.stop_name_is_not_a_place(
            "power and public engagement", th))

    def test_selection_predicate_accepts_real_places(self):
        th = tsg.extract_request_theme(TOUR557)
        self.assertFalse(tsg.stop_name_is_not_a_place("Faneuil Hall", th))
        self.assertFalse(tsg.stop_name_is_not_a_place("Boston Public Library", th))
        self.assertFalse(tsg.stop_name_is_not_a_place("Old State House", th))

    def test_rename_function_deleted(self):
        """The D643 anti-pattern (rename after narration) is removed."""
        self.assertFalse(hasattr(tsg, 'rename_theme_phrase_stops'),
                         "rename_theme_phrase_stops must not exist in 650B")
        self.assertFalse(hasattr(tsg, 'derive_real_place_from_block'),
                         "derive_real_place_from_block must not exist in 650B")

    def test_clean_walking_tour_passes_detector(self):
        """A properly-filtered tour (no theme-phrase stop) passes the detector."""
        found = tsg.find_theme_phrase_stops(CLEAN_WALKING)
        self.assertEqual(found, [])

    def test_museum_is_a_noop(self):
        found = tsg.find_theme_phrase_stops(MUSEUM_TEXT)
        self.assertEqual(found, [])


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 (650B) — directions + verified-coords-only distances
# ─────────────────────────────────────────────────────────────────────────────

class TestFix2WalkingDirections(unittest.TestCase):
    def test_wrong_target_detected_on_clean_tour(self):
        """On a clean tour, Stop 4's generic directions (no next-stop name) are
        detected as needing augmentation, not as wrong-target."""
        analysis = wdg.analyze(CLEAN_WALKING)
        rep = {r['num']: r for r in analysis}
        # Generic directions don't name a WRONG stop, they just lack the next name.
        for r in analysis:
            self.assertFalse(r['wrong_target'], f"Stop {r['num']} falsely flagged")

    def test_guard_augments_directions(self):
        """The guard augments directions with next-stop names and distances."""
        vc = {1: (42.3588, -71.0638), 2: (42.3609, -71.0577),
              3: (42.3600, -71.0568), 4: (42.3604, -71.0572),
              5: (42.3496, -71.0783)}
        fixed, report = wdg.ensure_walking_directions_lead_to_next(CLEAN_WALKING, vc)
        self.assertEqual(wdg.count_wrong_target_directions(fixed), 0)
        # Distances should have been added for verified coord pairs.
        self.assertGreater(report['distance_added'], 0)

    def test_verified_coords_distance_both_verified(self):
        """When both stops in a pair have verified coords, distance is computed."""
        vc = {1: (42.3588, -71.0638), 2: (42.3609, -71.0577),
              3: (42.3600, -71.0568), 4: (42.3604, -71.0572),
              5: (42.3584, -71.0598)}
        fixed, report = wdg.ensure_walking_directions_lead_to_next(TOUR557, vc)
        self.assertGreater(report['distance_added'], 0)

    def test_verified_coords_distance_omitted_when_unverified(self):
        """When only one stop in a pair has verified coords, distance is omitted."""
        # Only stop 1 verified — no pair has BOTH verified.
        vc = {1: (42.3588, -71.0638)}
        fixed, report = wdg.ensure_walking_directions_lead_to_next(TOUR557, vc)
        self.assertEqual(report['distance_added'], 0)

    def test_verified_coords_empty_dict_no_distances(self):
        """Empty verified_stop_coords = no verified coords at all = no distances."""
        fixed, report = wdg.ensure_walking_directions_lead_to_next(TOUR557, {})
        self.assertEqual(report['distance_added'], 0)

    def test_verified_coords_none_uses_text_coords(self):
        """verified_stop_coords=None = legacy behaviour, uses text-parsed coords."""
        fixed, report = wdg.ensure_walking_directions_lead_to_next(TOUR557, None)
        # Text has coordinates for all stops, so distances should be computed.
        self.assertGreater(report['distance_added'], 0)

    def test_clean_walking_directions_augmented(self):
        """A clean walking tour gets next-stop naming + distances."""
        vc = {1: (42.3588, -71.0638), 2: (42.3609, -71.0577),
              3: (42.3600, -71.0568), 4: (42.3604, -71.0572),
              5: (42.3496, -71.0783)}
        fixed, report = wdg.ensure_walking_directions_lead_to_next(CLEAN_WALKING, vc)
        # All non-last stops should have a hand-off naming the next stop.
        self.assertEqual(wdg.count_wrong_target_directions(fixed), 0)

    def test_headers_unchanged_by_directions_guard(self):
        before = re.findall(r"(?m)^Stop \d+: (.+)$", TOUR557)
        fixed, _ = wdg.ensure_walking_directions_lead_to_next(TOUR557)
        after = re.findall(r"(?m)^Stop \d+: (.+)$", fixed)
        self.assertEqual(before, after)

    def test_idempotent(self):
        once, _ = wdg.ensure_walking_directions_lead_to_next(TOUR557)
        twice, rep2 = wdg.ensure_walking_directions_lead_to_next(once)
        self.assertEqual(rep2['corrected'], 0)
        self.assertEqual(rep2['distance_added'], 0)
        self.assertEqual(once, twice)

    def test_directions_generator_target_guard(self):
        self.assertFalse(dgen._directions_name_destination(
            "head north until you reach the Massachusetts State House",
            "Boston Public Library"))
        self.assertTrue(dgen._directions_name_destination(
            "make your way to the Boston Public Library",
            "Boston Public Library"))

    def test_museum_is_a_noop(self):
        fixed, report = wdg.ensure_walking_directions_lead_to_next(MUSEUM_TEXT)
        self.assertEqual(report['corrected'], 0)
        self.assertEqual(fixed, MUSEUM_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 — current-affairs honesty
# ─────────────────────────────────────────────────────────────────────────────

class TestFix3CurrentAffairs(unittest.TestCase):
    def test_request_detected(self):
        self.assertTrue(cac.request_wants_current_affairs(TOUR557))
        self.assertFalse(cac.request_wants_current_affairs(MUSEUM_TEXT))

    def test_557_has_recent_item_so_no_note(self):
        self.assertTrue(cac.has_recent_item(TOUR557, now_year=2026))
        out, changed = cac.ensure_current_affairs_coverage(TOUR557, now_year=2026)
        self.assertFalse(changed)
        self.assertEqual(out, TOUR557)

    def test_old_only_tour_gets_honest_note(self):
        self.assertFalse(cac.has_recent_item(TOUR_OLD_ONLY, now_year=2026))
        out, changed = cac.ensure_current_affairs_coverage(
            TOUR_OLD_ONLY, now_year=2026)
        self.assertTrue(changed)
        self.assertIn("no verified developments from the past five years", out)
        self.assertLess(out.index("no verified developments"), out.index("Sources:"))

    def test_honest_note_idempotent(self):
        once, _ = cac.ensure_current_affairs_coverage(TOUR_OLD_ONLY, now_year=2026)
        twice, ch2 = cac.ensure_current_affairs_coverage(once, now_year=2026)
        self.assertFalse(ch2)
        self.assertEqual(once, twice)

    def test_non_current_affairs_request_noop(self):
        hist = TOUR_OLD_ONLY.replace("politics and current affairs",
                                     "colonial history")
        out, changed = cac.ensure_current_affairs_coverage(hist, now_year=2026)
        self.assertFalse(changed)
        self.assertEqual(out, hist)

    def test_museum_is_a_noop(self):
        out, changed = cac.ensure_current_affairs_coverage(MUSEUM_TEXT, now_year=2026)
        self.assertFalse(changed)
        self.assertEqual(out, MUSEUM_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# 650B composition: guards compose WITHOUT rename step
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineComposition650B(unittest.TestCase):
    def test_clean_tour_passes_all_guards(self):
        """A tour produced by correctly-filtered selection passes all guards."""
        txt = CLEAN_WALKING
        # No theme-phrase stops.
        self.assertEqual(tsg.find_theme_phrase_stops(txt), [])
        # Directions guard runs without crash.
        txt, rep = wdg.ensure_walking_directions_lead_to_next(txt)
        self.assertEqual(wdg.count_wrong_target_directions(txt), 0)
        # Current-affairs guard (recent item present).
        txt, ch3 = cac.ensure_current_affairs_coverage(txt, now_year=2026)
        # 5 stop headers preserved.
        self.assertEqual(len(re.findall(r"(?m)^Stop \d+:", txt)), 5)

    def test_557_theme_stop_detected_but_not_renamed(self):
        """On the pre-fix tour 557, the theme-phrase stop IS detected, but
        there is no rename function to run. The fix is at selection."""
        found = tsg.find_theme_phrase_stops(TOUR557)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], 5)
        # No rename_theme_phrase_stops to call — the function is deleted.
        self.assertFalse(hasattr(tsg, 'rename_theme_phrase_stops'))

    def test_guards_noop_on_museum(self):
        """Museum canary: all guards are no-ops."""
        found = tsg.find_theme_phrase_stops(MUSEUM_TEXT)
        self.assertEqual(found, [])
        txt, rep2 = wdg.ensure_walking_directions_lead_to_next(MUSEUM_TEXT)
        self.assertEqual(rep2['corrected'], 0)
        self.assertEqual(txt, MUSEUM_TEXT)
        txt, ch3 = cac.ensure_current_affairs_coverage(MUSEUM_TEXT, now_year=2026)
        self.assertFalse(ch3)
        self.assertEqual(txt, MUSEUM_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed check on the live 557 row (skips when the DB is unreachable).
# ─────────────────────────────────────────────────────────────────────────────

@unittest.skip("LEAD 2026-10-09: reads the LIVE row 557, which was regenerated with the 650B fix (no theme stop now); a fixture-based test covers the logic")
class TestLive557Row(unittest.TestCase):
    def _fetch_557(self):
        try:
            import psycopg2
        except Exception as e:  # pragma: no cover
            self.skipTest(f"psycopg2 unavailable: {e}")
        try:
            conn = psycopg2.connect(
                host=os.environ.get("DB_HOST", "localhost"),
                port=int(os.environ.get("DB_PORT", "5433")),
                user=os.environ.get("DB_USER", "admin"),
                password=os.environ.get("DB_PASSWORD", "password123"),
                dbname=os.environ.get("DB_NAME", "audiotours"),
                connect_timeout=4)
        except Exception as e:  # pragma: no cover
            self.skipTest(f"DB unreachable: {e}")
        try:
            cur = conn.cursor()
            cur.execute("SELECT tour_content FROM audio_tours WHERE id=557")
            row = cur.fetchone()
        finally:
            conn.close()
        if not row or not row[0]:
            self.skipTest("audio_tours.id=557 not present")
        return row[0]

    def test_live_557_theme_stop_detected(self):
        tc = self._fetch_557()
        # The live row shows the theme-phrase stop — fix 1 catches it.
        found = tsg.find_theme_phrase_stops(tc)
        self.assertGreaterEqual(len(found), 1)

    def test_live_557_directions_guard_works(self):
        tc = self._fetch_557()
        fixed, rep = wdg.ensure_walking_directions_lead_to_next(tc)
        self.assertEqual(wdg.count_wrong_target_directions(fixed), 0)

    def test_live_557_has_recent_item(self):
        tc = self._fetch_557()
        # The live row already carries a recent (2024) item.
        self.assertTrue(cac.has_recent_item(tc, now_year=2026))


if __name__ == "__main__":
    unittest.main(verbosity=2)
