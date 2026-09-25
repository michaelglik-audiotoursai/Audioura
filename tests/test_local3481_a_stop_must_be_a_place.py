#!/usr/bin/env python3
"""test_local3481_a_stop_must_be_a_place.py — LOCAL-3481 acceptance.

LOCAL-3481 is the re-delivery of "A Stop Must Be A Place". The implementation it
verifies already lives on `storied` (LOCAL-481, commit ca52d84):

  * Part 1  geocode_stops.find_centroid_collapse / repair_centroid_collapse
  * Part 2  place_shape.classify_stop_name / is_a_place
  * Part 3  the extension inside generate_tour_text._validate_stops_within_scope
            (the existing PHASE 5.6 gate) plus replenish_to_count (D558)

This file is a single acceptance harness that binds the EXACT fixtures the ticket
names — the four tour-423 stops with their coordinates, and the six approved
Cimiez stops copied verbatim from TOUR_CIMIEZ_WALKING_20260830.md — to each of the
five acceptance criteria, and it CALLS the real functions (D418/D421: no grepping
source for a marker as the behavioural proof). Every criterion is one test:

  AC1  the four 423 names+coords are all flagged; Boston Bruins Bar survives the
       place-shape check and the other three do not.
  AC2  the six approved Cimiez stops are NEVER flagged (a bounce otherwise), and
       they survive the wired PHASE 5.6 gate under a deliberately invalid key.
  AC3  two artworks in one museum room are not flagged by the collision rule.
  AC4  a tour that loses a stop to the check comes back at the requested count via
       the replenishment loop.
  AC5  BREAK THE DETECTOR — with each half disabled the 423 fixture passes through
       UNFLAGGED, proving the suite can go red; re-enabled, it flags again.

Deterministic, no network, no key. The PHASE 5.6 tests pass an invalid key on
purpose: the LLM branch fails OPEN, so any removal there can only be the
deterministic place-shape check — a genuine witness that the wiring is live
(LOCAL-465: 27 green function tests and a NameError live, because nothing proved
the function was CALLED).
"""
import os
import sys
import unittest
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import place_shape as ps            # noqa: E402
import geocode_stops as g           # noqa: E402
import generate_tour_text as gtt    # noqa: E402
import scope_memory                 # noqa: E402


BAD_KEY = {"Authorization": "Bearer INVALID-ON-PURPOSE"}

# ── The tour-423 evidence, verbatim from the ticket ─────────────────────────────
# name, latitude, longitude, is_place, place-shape
TOUR_423 = [
    ("Boston Bruins Bar",                 42.3656, -71.0188, True,  "place"),
    ("Art Exhibits at Logan Airport",     42.3656, -71.0173, False, "category"),
    ("Boston Logan Airport Virtual Tour", 42.3656, -71.0096, False, "format"),
    ("Boston Logan Airport History Walk", 42.3656, -71.0189, False, "format"),
]


def _t423_pois():
    return [{"name": n, "coordinates": f"{lat}, {lng}"}
            for n, lat, lng, _, _ in TOUR_423]


def _t423_scope_pois():
    return [{"name": n, "description": "A stop on the Logan Airport tour."}
            for n, _, _, _, _ in TOUR_423]


# ── The approved Cimiez stops, copied verbatim from the tour file ──────────────
# Michael approved that tour; flagging any of these is a bounce (AC2).
CIMIEZ_APPROVED = [
    "Matisse Museum",
    "Cimiez Monastery",
    "Musée Marc Chagall",
    "Villa Leopolda",
    "Roman Ruins of Cemenelum",
    "Musée National du Sport",
]

# Two artworks in one museum room — legitimately co-located (AC3).
MUSEUM_ROOM = [
    {"name": "Mona Lisa",            "coordinates": "48.8600, 2.3376"},
    {"name": "The Wedding at Cana",  "coordinates": "48.8600, 2.3376"},
]


class AC1_TheFourStopsAreFlagged(unittest.TestCase):
    """AC1: all four 423 stops are flagged; Bruins Bar survives, the others don't."""

    def test_place_shape_flags_the_three_nonplaces_only(self):
        for name, _, _, is_place, shape in TOUR_423:
            res = ps.classify_stop_name(name)
            self.assertEqual(res["is_place"], is_place, f"{name!r} -> {res}")
            self.assertEqual(res["shape"], shape, f"{name!r} -> {res}")

    def test_bruins_bar_is_the_only_place(self):
        survivors = [n for n, _, _, _, _ in TOUR_423 if ps.is_a_place(n)]
        self.assertEqual(survivors, ["Boston Bruins Bar"], survivors)

    def test_centroid_collapse_flags_all_four_on_the_shared_latitude(self):
        rec = g.find_centroid_collapse(_t423_pois(), category="facility")
        self.assertEqual(rec["action"], "collision", rec)
        self.assertEqual(rec["colliding_indices"], [0, 1, 2, 3], rec)
        self.assertTrue(
            any(grp["axis"] == "lat" and abs(grp["value"] - 42.3656) < 1e-9
                for grp in rec["groups"]),
            f"the shared latitude 42.3656 is not the collision axis: {rec}")

    def test_wired_phase56_removes_the_three_nonplaces_bruins_bar_survives(self):
        """Part 3: the real gate, with a bad key so the LLM branch fails open —
        so the three removals can only be the deterministic place-shape check."""
        scope_memory.reset_cache()
        kept = gtt._validate_stops_within_scope(
            _t423_scope_pois(), "Logan Airport, Boston",
            headers=BAD_KEY, protect_first=False)
        self.assertEqual([p["name"] for p in kept], ["Boston Bruins Bar"],
                         [p["name"] for p in kept])


class AC2_ApprovedCimiezNeverFlagged(unittest.TestCase):
    """AC2: the six approved Cimiez stops are never flagged (bounce otherwise)."""

    def test_every_approved_cimiez_stop_classifies_as_a_place(self):
        # Test both Unicode normal forms: 'Musée' may arrive NFC or NFD (D243).
        for enc in ("NFC", "NFD"):
            for name in CIMIEZ_APPROVED:
                n = unicodedata.normalize(enc, name)
                res = ps.classify_stop_name(n)
                self.assertTrue(res["is_place"],
                                f"{enc}: approved stop {name!r} flagged: {res}")

    def test_no_approved_cimiez_stop_is_removed_for_being_a_nonplace(self):
        """The LOCAL-3481 concern is that the PLACE check never flags an approved
        stop. It must not be conflated with the unrelated scope-memory gate: the
        approved tour file itself flags Villa Leopolda as OUTSIDE Cimiez
        (Villefranche-sur-Mer, ~6 km east), and known_out_of_scope.json removes it
        deterministically (D557). That is a correct, separate removal. What would
        be a LOCAL-3481 bounce is any approved stop removed with a '[not-a-place]'
        reason — so we assert on the removal REASON, captured from the gate's own
        log, not merely on the survivor list."""
        import io
        import contextlib

        scope_memory.reset_cache()
        pois = [{"name": n, "description": "An approved Cimiez stop."}
                for n in CIMIEZ_APPROVED]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            gtt._validate_stops_within_scope(
                pois, "Cimiez District, Nice", headers=BAD_KEY, protect_first=False)
        log = buf.getvalue()

        nonplace_removals = [line for line in log.splitlines()
                             if "REMOVED" in line and "[not-a-place]" in line]
        self.assertEqual(nonplace_removals, [],
                         f"an approved Cimiez stop was removed as a non-place — a "
                         f"LOCAL-3481 bounce:\n{chr(10).join(nonplace_removals)}")


class AC3_MuseumCoLocationNotFlagged(unittest.TestCase):
    """AC3: two artworks in one museum room are not flagged by the collision rule."""

    def test_co_located_artworks_are_not_a_collision(self):
        # [D572] Co-location is innocent by the rule itself (identical on both
        # axes = same room), for every category, not only 'museum'.
        for category in ("museum", "walking", "facility", None):
            rec = g.find_centroid_collapse(MUSEUM_ROOM, category=category)
            self.assertEqual(rec["action"], "none",
                             f"co-located artworks flagged for {category!r}: {rec}")


class AC4_ReplenishmentRefillsToCount(unittest.TestCase):
    """AC4: a tour that loses a stop to the check comes back at the requested
    count via the replenishment loop (D558)."""

    @staticmethod
    def _poi(name):
        return {"name": name, "description": ""}

    def test_a_nonplace_candidate_is_rejected_and_a_real_place_refills(self):
        scope_memory.reset_cache()
        rounds = []

        def propose(need, seen):
            rounds.append(need)
            if len(rounds) == 1:
                # Round 1 offers a category label — a non-place, must be rejected.
                return [{"name": "Restaurants in Nice", "why": "a category label"}]
            # Round 2 offers a real market square — must be accepted.
            return [{"name": "Cours Saleya", "why": "a real market square"}]

        poi_list = [self._poi("Matisse Museum"), self._poi("Cimiez Monastery")]
        added, rejected, n = gtt.replenish_to_count(
            poi_list, want=3, scope="Cimiez District, Nice", headers=BAD_KEY,
            propose=propose, make_poi=self._poi)

        names = [p["name"] for p in poi_list]
        self.assertEqual(len(poi_list), 3, f"tour came back short: {names}")
        self.assertNotIn("Restaurants in Nice", names, "the non-place was kept")
        self.assertIn("Cours Saleya", names, "no real place refilled the count")
        self.assertEqual((added, rejected), (1, 1))
        self.assertGreaterEqual(n, 2, "one-shot behaviour — the loop did not re-run")


class AC5_BreakTheDetector(unittest.TestCase):
    """AC5: break the detector and show a test go red. With each half disabled,
    the 423 fixture passes through UNFLAGGED; re-enabled, it flags again. Same
    input, the knob decides — which is what proves the suite can distinguish
    fixed from broken."""

    # -- Part 1 half: the centroid-collapse detector --------------------------
    def setUp(self):
        self._min = g._COLLAPSE_MIN_STOPS
        self._fmt = ps._FORMAT_HEADS
        self._std = ps._STANDALONE_NONPLACE
        self._cat = ps._CATEGORY_HEADS

    def tearDown(self):
        g._COLLAPSE_MIN_STOPS = self._min
        ps._FORMAT_HEADS = self._fmt
        ps._STANDALONE_NONPLACE = self._std
        ps._CATEGORY_HEADS = self._cat

    def test_disabling_centroid_detector_lets_423_through_then_reenabled_flags(self):
        g._COLLAPSE_MIN_STOPS = 99          # [D572] the disable knob
        disabled = g.find_centroid_collapse(_t423_pois(), category="facility")
        self.assertEqual(disabled["action"], "none",
                         "disabled centroid detector must let 423 through — red state")

        g._COLLAPSE_MIN_STOPS = self._min
        enabled = g.find_centroid_collapse(_t423_pois(), category="facility")
        self.assertEqual(enabled["action"], "collision", enabled)
        self.assertEqual(enabled["colliding_indices"], [0, 1, 2, 3], enabled)

    def test_disabling_place_shape_rules_lets_423_nonplaces_through_then_reenabled_flags(self):
        ps._FORMAT_HEADS = set()
        ps._STANDALONE_NONPLACE = set()
        ps._CATEGORY_HEADS = set()
        broken = [n for n, _, _, _, _ in TOUR_423 if not ps.is_a_place(n)]
        self.assertEqual(broken, [],
                         "disabled place-shape rules must let every 423 name through "
                         "as a place — red state")

        ps._FORMAT_HEADS = self._fmt
        ps._STANDALONE_NONPLACE = self._std
        ps._CATEGORY_HEADS = self._cat
        flagged = [n for n, _, _, is_place, _ in TOUR_423
                   if not is_place and not ps.is_a_place(n)]
        self.assertEqual(flagged, [n for n, _, _, is_place, _ in TOUR_423 if not is_place],
                         "re-enabled place-shape rules must flag all three non-places")


if __name__ == "__main__":
    unittest.main(verbosity=2)
