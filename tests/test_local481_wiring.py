#!/usr/bin/env python3
"""test_local481_wiring.py — LOCAL-481 Part 3 (the wiring, proved separately).

LOCAL-465's lesson: 27 green function tests and a NameError live, because nothing
proved the function was actually CALLED. So this file proves the wiring, not the
functions (those are in test_local481_place_shape.py / _centroid_collapse.py):

  A. The non-place rejection runs INSIDE _validate_stops_within_scope — the
     existing PHASE 5.6 gate — deterministically, before the LLM. With a
     deliberately invalid key (so the LLM branch fails open), the three 423
     non-places are still removed and Boston Bruins Bar survives. If the wiring
     were absent, the bad key would keep all four (fail-open), so this test is a
     genuine witness to the call.
  B. The approved Cimiez stops are NOT removed by that same path (the place-shape
     check passes them; the LLM fails open on the bad key). A bounce otherwise.
  C. AC4: a tour that loses a non-place to the check comes back at the requested
     count via replenish_to_count (D558) — the loop the task says to reuse.
  D. Source witnesses: the D559 geocode block calls repair_centroid_collapse and
     imports place_shape, and _validate_stops_within_scope imports
     classify_stop_name. Not a substitute for A–C — a belt-and-braces guard that
     the extension lives where the pipeline runs.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt  # noqa: E402
import scope_memory  # noqa: E402

BAD_KEY = {"Authorization": "Bearer INVALID-ON-PURPOSE"}

TOUR_423 = [
    {"name": "Boston Bruins Bar", "description": "A mapped sports bar."},
    {"name": "Art Exhibits at Logan Airport", "description": "Various art."},
    {"name": "Boston Logan Airport Virtual Tour", "description": "A virtual tour."},
    {"name": "Boston Logan Airport History Walk", "description": "A history walk."},
]

CIMIEZ_APPROVED = [
    {"name": "Matisse Museum", "description": "Art museum in Cimiez."},
    {"name": "Cimiez Monastery", "description": "Historic monastery."},
    {"name": "Musée Marc Chagall", "description": "Chagall museum."},
    {"name": "Roman Ruins of Cemenelum", "description": "Roman archaeological site."},
]


class TestNonPlaceRejectionIsWiredIntoPhase56(unittest.TestCase):
    """A: the deterministic non-place check runs inside the real gate."""

    def setUp(self):
        scope_memory.reset_cache()

    def test_423_nonplaces_removed_bruins_bar_survives(self):
        # protect_first=False so the gate can reject stop 0 too; we assert the
        # survivor by NAME, not by position.
        kept = gtt._validate_stops_within_scope(
            [dict(p) for p in TOUR_423], "Logan Airport, Boston",
            headers=BAD_KEY, protect_first=False)
        names = [p["name"] for p in kept]
        self.assertEqual(names, ["Boston Bruins Bar"],
                         f"non-place rejection is not wired into PHASE 5.6: {names}")

    def test_without_the_wiring_the_bad_key_would_keep_all_four(self):
        """Witness that the removal came from the place-shape check, not the LLM:
        a name the check passes but that is out of scope is KEPT here, because the
        bad key makes the LLM branch fail open. So the three removals above can
        only be the deterministic check firing."""
        only_places = [{"name": "Fenway Park", "description": "A ballpark."},
                       {"name": "Boston Common", "description": "A public park."}]
        kept = gtt._validate_stops_within_scope(
            only_places, "Logan Airport, Boston", headers=BAD_KEY,
            protect_first=False)
        self.assertEqual([p["name"] for p in kept], ["Fenway Park", "Boston Common"],
                         "the bad-key LLM branch must fail open — proving the 423 "
                         "removals were the deterministic place-shape check")


class TestCimiezApprovedNotRemovedByWiring(unittest.TestCase):
    """B: the approved Cimiez stops survive the wired gate (bounce otherwise)."""

    def setUp(self):
        scope_memory.reset_cache()

    def test_cimiez_stops_all_survive(self):
        kept = gtt._validate_stops_within_scope(
            [dict(p) for p in CIMIEZ_APPROVED], "Cimiez District, Nice",
            headers=BAD_KEY, protect_first=False)
        self.assertEqual([p["name"] for p in kept],
                         [p["name"] for p in CIMIEZ_APPROVED],
                         "an approved Cimiez stop was dropped — that is a bounce")


class TestReplenishmentRefillsAfterNonPlaceDropped(unittest.TestCase):
    """C / AC4: the loop refills to the requested count with real places."""

    def setUp(self):
        scope_memory.reset_cache()

    @staticmethod
    def _poi(name):
        return {"name": name, "description": ""}

    def test_a_nonplace_candidate_is_replaced_not_just_dropped(self):
        """Round 1 proposes a non-place (a category label); the loop must reject it
        and go round again, coming back at the requested count with a real place."""
        rounds = []

        def propose(need, seen):
            rounds.append(need)
            if len(rounds) == 1:
                return [{"name": "Restaurants in Nice", "why": "a category"}]
            return [{"name": "Cours Saleya", "why": "a real market square"}]

        poi_list = [self._poi("Matisse Museum"), self._poi("Cimiez Monastery")]
        added, rejected, n = gtt.replenish_to_count(
            poi_list, want=3, scope="Cimiez District, Nice", headers=BAD_KEY,
            propose=propose, make_poi=self._poi)

        names = [p["name"] for p in poi_list]
        self.assertEqual(len(poi_list), 3, f"tour came back short: {names}")
        self.assertNotIn("Restaurants in Nice", names, "the non-place was kept")
        self.assertIn("Cours Saleya", names, "the loop did not refill with a real place")
        self.assertEqual((added, rejected), (1, 1))
        self.assertGreaterEqual(n, 2, "one-shot behaviour — the loop did not re-run")


class TestSourceWitnesses(unittest.TestCase):
    """D: the extension lives where the pipeline runs. Belt-and-braces; A–C are
    the behavioural proof."""

    def _src(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "generate_tour_text.py")
        with open(p, encoding="utf-8") as f:
            return f.read()

    def test_d559_block_calls_repair_centroid_collapse(self):
        self.assertIn("repair_centroid_collapse", self._src(),
                      "centroid-collapse repair is not wired into the generator")

    def test_generator_imports_place_shape(self):
        src = self._src()
        self.assertIn("from place_shape import", src,
                      "place_shape is not imported anywhere in the generator")

    def test_validate_scope_uses_classify_stop_name(self):
        self.assertIn("classify_stop_name", self._src(),
                      "the scope gate does not consult the place-shape classifier")


if __name__ == "__main__":
    unittest.main(verbosity=2)
