#!/usr/bin/env python3
"""test_local650_walking_route.py — LOCAL-650.

Three walking-tour defects on the REAL request
"Walking tour in Boston dedicated to Massachusetts politics and current affairs,
Boston, MA" (walking, 5 stops; audio_tours.id=557 and the Oct-6 baseline):

  FIX 1 — the request's THEME became a stop. Stop 5 = "Massachusetts politics and
          current affairs" (the theme phrase), Address N/A. A POI must be a real,
          geocodable place; a theme phrase / topic-like name must be rejected and
          replaced by a real place that fits the theme.
  FIX 2 — Directions led BACKWARDS. Stop 4 (Old State House) said "… head north …
          until you reach the Massachusetts State House …" — that is STOP 1, not
          the next stop. Each stop's Directions must name the NEXT stop and say
          roughly how far it is.
  FIX 3 — "current affairs" honesty. When the request names current affairs, at
          least one stop must carry a recent (≤ 5 years) grounded item, or the
          tour must say honestly there is none.

The fixtures below are the REAL tour-557 stop blocks (verbatim). A DB-backed test
reads the live row when reachable and otherwise skips, so the suite runs offline.
MUSEUM behaviour is proven unchanged: every LOCAL-650 guard is a no-op on a
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


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1 — theme phrase must never be a stop
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
                      "John F. Kennedy Presidential Library"):
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

    def test_rename_derives_real_place_from_narration(self):
        fixed, changes = tsg.rename_theme_phrase_stops(TOUR557)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]['stop'], 5)
        # The replacement is a real place the stop's own narration names.
        self.assertIn("University of Massachusetts Boston", changes[0]['to'])
        # The theme phrase is gone from the Stop 5 header.
        self.assertNotRegex(
            fixed, r"(?m)^Stop 5: Massachusetts politics and current affairs\s*$")
        self.assertRegex(fixed, r"(?m)^Stop 5: .*University of Massachusetts Boston")
        # Coordinates and body are preserved.
        self.assertIn("Coordinates: 42.3584, -71.0598", fixed)
        self.assertIn("From 1996 to 2011", fixed)

    def test_rename_idempotent(self):
        once, _ = tsg.rename_theme_phrase_stops(TOUR557)
        twice, ch2 = tsg.rename_theme_phrase_stops(once)
        self.assertEqual(ch2, [])
        self.assertEqual(once, twice)

    def test_selection_predicate(self):
        th = tsg.extract_request_theme(TOUR557)
        self.assertTrue(tsg.stop_name_is_not_a_place(
            "Massachusetts politics and current affairs", th))
        self.assertFalse(tsg.stop_name_is_not_a_place("Faneuil Hall", th))

    def test_museum_is_a_noop(self):
        fixed, changes = tsg.rename_theme_phrase_stops(MUSEUM_TEXT)
        self.assertEqual(changes, [])
        self.assertEqual(fixed, MUSEUM_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2 — directions lead to the NEXT stop, with distance
# ─────────────────────────────────────────────────────────────────────────────

class TestFix2WalkingDirections(unittest.TestCase):
    def _after_rename(self):
        fixed, _ = tsg.rename_theme_phrase_stops(TOUR557)
        return fixed

    def test_wrong_target_detected_after_rename(self):
        # After Stop 5 is renamed to UMass Boston, Stop 4's Directions still name
        # the Massachusetts State House (Stop 1) — a wrong target.
        txt = self._after_rename()
        self.assertEqual(wdg.count_wrong_target_directions(txt), 1)
        rep = {r['num']: r for r in wdg.analyze(txt)}
        self.assertTrue(rep[4]['wrong_target'])

    def test_guard_corrects_wrong_target_and_adds_distance(self):
        txt = self._after_rename()
        fixed, report = wdg.ensure_walking_directions_lead_to_next(txt)
        self.assertEqual(wdg.count_wrong_target_directions(fixed), 0)
        self.assertGreaterEqual(report['corrected'], 1)
        # Stop 4's Directions now name the next stop (UMass Boston) and NOT the
        # Massachusetts State House as the destination.
        m = re.search(r"(?ms)^Stop 4:.*?^Directions:\s*(.+?)$.*?^Stop 5:", fixed)
        self.assertIsNotNone(m)
        s4_dir = m.group(1)
        self.assertIn("University of Massachusetts Boston", s4_dir)
        self.assertNotIn("until you reach the Massachusetts State House", s4_dir)
        # A distance phrase was added somewhere in the directions.
        self.assertRegex(fixed, r"(?i)(meters?|km|minute).{0,8}(away|walk)")

    def test_headers_unchanged_by_directions_guard(self):
        txt = self._after_rename()
        before = re.findall(r"(?m)^Stop \d+: (.+)$", txt)
        fixed, _ = wdg.ensure_walking_directions_lead_to_next(txt)
        after = re.findall(r"(?m)^Stop \d+: (.+)$", fixed)
        self.assertEqual(before, after)

    def test_blank_line_before_next_header_preserved(self):
        txt = self._after_rename()
        fixed, _ = wdg.ensure_walking_directions_lead_to_next(txt)
        # No stop header is glued onto a previous line (same physical line).
        self.assertNotRegex(fixed, r"(?m)^.+\bStop \d+:")
        self.assertRegex(fixed, r"\n\nStop 5:")

    def test_idempotent(self):
        txt = self._after_rename()
        once, _ = wdg.ensure_walking_directions_lead_to_next(txt)
        twice, rep2 = wdg.ensure_walking_directions_lead_to_next(once)
        self.assertEqual(rep2['corrected'], 0)
        self.assertEqual(rep2['distance_added'], 0)
        self.assertEqual(once, twice)

    def test_directions_generator_target_guard(self):
        # The 557 Stop-4 prose names the Massachusetts State House; the next stop
        # is the University of Massachusetts Boston — the target guard must reject.
        self.assertFalse(dgen._directions_name_destination(
            "head north until you reach the Massachusetts State House",
            "The University of Massachusetts Boston"))
        # Prose that names the next stop passes.
        self.assertTrue(dgen._directions_name_destination(
            "make your way to the University of Massachusetts Boston campus",
            "The University of Massachusetts Boston"))

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
        # The real 557 Boston City Hall stop carries a late-2024 indictment, so
        # the first clause of the requirement is already met — no note is added.
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
        # The note sits before the Sources block, never invents a year.
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
# End-to-end on the fixture: the three guards compose cleanly, museum untouched.
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineComposition(unittest.TestCase):
    def test_three_guards_compose_on_557(self):
        txt = TOUR557
        txt, ch1 = tsg.rename_theme_phrase_stops(txt)
        txt, rep2 = wdg.ensure_walking_directions_lead_to_next(txt)
        txt, ch3 = cac.ensure_current_affairs_coverage(txt, now_year=2026)
        # fix1 renamed Stop 5; fix2 corrected Stop 4; fix3 added nothing (recent).
        self.assertEqual(len(ch1), 1)
        self.assertEqual(wdg.count_wrong_target_directions(txt), 0)
        self.assertFalse(ch3)
        self.assertEqual(tsg.find_theme_phrase_stops(txt), [])
        self.assertEqual(len(re.findall(r"(?m)^Stop \d+:", txt)), 5)

    def test_three_guards_noop_on_museum(self):
        txt = MUSEUM_TEXT
        txt, ch1 = tsg.rename_theme_phrase_stops(txt)
        txt, rep2 = wdg.ensure_walking_directions_lead_to_next(txt)
        txt, ch3 = cac.ensure_current_affairs_coverage(txt, now_year=2026)
        self.assertEqual(ch1, [])
        self.assertEqual(rep2['corrected'], 0)
        self.assertFalse(ch3)
        self.assertEqual(txt, MUSEUM_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed check on the live 557 row (skips when the DB is unreachable).
# ─────────────────────────────────────────────────────────────────────────────

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

    def test_live_557_guards_fix_the_defects(self):
        tc = self._fetch_557()
        # The live row shows the theme-phrase stop and the backwards directions.
        self.assertEqual(len(tsg.find_theme_phrase_stops(tc)), 1)
        fixed, ch = tsg.rename_theme_phrase_stops(tc)
        self.assertEqual(len(ch), 1)
        fixed, rep = wdg.ensure_walking_directions_lead_to_next(fixed)
        self.assertEqual(wdg.count_wrong_target_directions(fixed), 0)
        # The live row already carries a recent (2024) item, so no note is added.
        _out, changed = cac.ensure_current_affairs_coverage(fixed, now_year=2026)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
