#!/usr/bin/env python3
"""test_local799_named_place_reconcile.py — LOCAL-799 (D562 refinement).

Tour 467 (Subscribed Preview), request
    "Mui Ne sights: Fairy Stream, Red Sand Dunes, White Sand Dunes, fishing
     village (by car)"
SHIPPED 5 stops: Red Canyon, Red Sand Dunes, Mui Ne Fishing Village, Mui Ne
Market, Fairy Stream. Yet Stop 1's Orientation announced, one sentence per name:
    "We could not confirm Fairy Stream, so it is not part of this tour.
     We could not confirm Red Sand Dunes, so it is not part of this tour.
     We could not confirm White Sand Dunes, so it is not part of this tour.
     We could not confirm fishing village, so it is not part of this tour."
Three of those four ARE stops (Fairy Stream = Fairy Stream; Red Sand Dunes = Red
Sand Dunes; "fishing village" ⊂ "Mui Ne Fishing Village"). Only White Sand Dunes
was really missing. Michael: "bizarre — it obviously made the tour and the stops
are here".

The LOCAL-751 announcement was decided too EARLY — against the discovered-landmark
set, before replenish/dedup/renaming — and emitted one sentence per name inside a
stop's Orientation line. LOCAL-799:

  1. `reconcile_named_place_announcement(named, final_pois, …)` decides the
     announcement against the FINAL stop list (normalized/diacritic-folded token
     match, e.g. "fishing village" ⊂ "Mui Ne Fishing Village", or a 300 m
     geocode). It also tries an injected `places_search_fn` ONCE for an uncovered
     name (LOCAL-790/788B), so a transient source failure is not a false negative.
  2. `build_named_place_intro_sentence(uncovered)` returns ONE natural sentence.
  3. `screen_work_tour.inject_named_place_after_welcome(text, sentence)` places it
     AFTER the welcome, never inside a stop's Orientation line.

RED before LOCAL-799: `reconcile_named_place_announcement`,
`build_named_place_intro_sentence`, and `inject_named_place_after_welcome` do not
exist (AttributeError/ImportError).

Run: python3 -m pytest test_local799_named_place_reconcile.py -q
"""
import unittest

import area_resolver as ar
import screen_work_tour as swt


# The five stops tour 467 actually delivered (renamed/replenished FINAL list).
FINAL_467 = [
    {"name": "Red Canyon"},
    {"name": "Red Sand Dunes"},
    {"name": "Mui Ne Fishing Village"},
    {"name": "Mui Ne Market"},
    {"name": "Fairy Stream"},
]

# The four places the listener named (intent.named_places / request clause).
NAMED_467 = ["Fairy Stream", "Red Sand Dunes", "White Sand Dunes", "fishing village"]


# A delivered walking tour in the field shape: a tour-level welcome/prolog opens
# Stop 1 after the Orientation line.
DELIVERED_467 = """Tour-Category: walking

Stop 1: Red Canyon

Address: Mui Ne, Binh Thuan, Vietnam

Coordinates: 10.9462, 108.2203

Orientation: As you arrive at Red Canyon, look up at the ribboned walls of ochre and cream.

You are about to embark on a journey through the sunbaked coast of Mui Ne, where fishing boats, dunes, and streams braid together the story of this seaside town. From the carved canyon to the working fishing village, each stop opens a chapter of the place.

Red Canyon is a narrow gorge carved into soft sandstone by seasonal rains.

Directions: Follow the track north toward the dunes.

Stop 2: Red Sand Dunes

Address: Mui Ne, Binh Thuan, Vietnam
"""


class TestReconcileAgainstFinalStops(unittest.TestCase):
    def test_467_only_white_sand_dunes_uncovered(self):
        uncovered = ar.reconcile_named_place_announcement(NAMED_467, FINAL_467)
        self.assertEqual(
            ["White Sand Dunes"], uncovered,
            "only White Sand Dunes was really missing; the other three ARE stops",
        )

    def test_fishing_village_token_subset_is_covered(self):
        # "fishing village" ⊂ "Mui Ne Fishing Village" — normalized token match.
        self.assertEqual(
            [], ar.reconcile_named_place_announcement(["fishing village"], FINAL_467))

    def test_exact_and_renamed_matches_are_covered(self):
        self.assertEqual(
            [], ar.reconcile_named_place_announcement(
                ["Fairy Stream", "Red Sand Dunes"], FINAL_467))

    def test_all_four_covered_when_white_sand_dunes_also_shipped(self):
        final = FINAL_467 + [{"name": "White Sand Dunes"}]
        self.assertEqual(
            [], ar.reconcile_named_place_announcement(NAMED_467, final),
            "every named place now has a final stop → nothing to announce",
        )

    def test_red_vs_white_are_not_confused(self):
        # Red Sand Dunes is a stop; White Sand Dunes is NOT — the colour token
        # must keep them distinct (no false "covered").
        final = [{"name": "Red Sand Dunes"}]
        self.assertEqual(
            ["White Sand Dunes"],
            ar.reconcile_named_place_announcement(
                ["Red Sand Dunes", "White Sand Dunes"], final))

    def test_duplicate_named_places_collapse(self):
        uncovered = ar.reconcile_named_place_announcement(
            ["White Sand Dunes", "white sand dunes"], FINAL_467)
        self.assertEqual(["White Sand Dunes"], uncovered)


class TestGeocodeCoverage(unittest.TestCase):
    def test_within_300m_is_covered(self):
        final = [{"name": "Coastal Stop", "latitude": 10.9400, "longitude": 108.2500}]
        coords = {"White Sand Dunes": (10.9402, 108.2501)}  # ~ <300 m away
        self.assertEqual(
            [], ar.reconcile_named_place_announcement(
                ["White Sand Dunes"], final, name_coords=coords))

    def test_beyond_300m_is_not_covered(self):
        final = [{"name": "Coastal Stop", "latitude": 10.9400, "longitude": 108.2500}]
        coords = {"White Sand Dunes": (10.98, 108.30)}  # kilometres away
        self.assertEqual(
            ["White Sand Dunes"],
            ar.reconcile_named_place_announcement(
                ["White Sand Dunes"], final, name_coords=coords))


class TestPlacesSearchRescue(unittest.TestCase):
    def test_places_search_hit_suppresses_announcement(self):
        # A name no stop covers, but the map finds it (a transient Overpass/
        # Wikidata failure left it "unconfirmed"): do NOT announce a false negative.
        calls = []

        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            calls.append(name)
            return [{"name": name, "latitude": 10.95, "longitude": 108.3}]

        uncovered = ar.reconcile_named_place_announcement(
            ["White Sand Dunes"], FINAL_467, places_search_fn=fake_ps,
            scope="Mui Ne, Vietnam")
        self.assertEqual([], uncovered)
        self.assertEqual(["White Sand Dunes"], calls,
                         "places_search must be tried exactly once before announcing")

    def test_places_search_miss_still_announces(self):
        def fake_ps(name, scope="", scope_center=None, scope_bbox=None):
            return []  # genuinely not on the map

        uncovered = ar.reconcile_named_place_announcement(
            ["White Sand Dunes"], FINAL_467, places_search_fn=fake_ps,
            scope="Mui Ne, Vietnam")
        self.assertEqual(["White Sand Dunes"], uncovered)

    def test_places_search_exception_is_non_fatal(self):
        def boom(name, **kw):
            raise RuntimeError("serper down")

        uncovered = ar.reconcile_named_place_announcement(
            ["White Sand Dunes"], FINAL_467, places_search_fn=boom)
        self.assertEqual(["White Sand Dunes"], uncovered)


class TestOneSentence(unittest.TestCase):
    def test_no_names_is_empty(self):
        self.assertEqual("", ar.build_named_place_intro_sentence([]))

    def test_single_name_one_sentence(self):
        s = ar.build_named_place_intro_sentence(["White Sand Dunes"])
        self.assertIn("White Sand Dunes", s)
        self.assertEqual(1, s.count("."), f"must be exactly one sentence: {s!r}")
        self.assertIn("isn't included", s)

    def test_two_names_single_sentence_with_and(self):
        s = ar.build_named_place_intro_sentence(["White Sand Dunes", "Ghost Cave"])
        self.assertIn("White Sand Dunes and Ghost Cave", s)
        self.assertEqual(1, s.count("."), f"must be exactly one sentence: {s!r}")
        self.assertIn("aren't included", s)

    def test_three_names_single_sentence(self):
        s = ar.build_named_place_intro_sentence(["A Cave", "B Beach", "C Dune"])
        self.assertIn("A Cave, B Beach and C Dune", s)
        self.assertEqual(1, s.count("."), f"must be exactly one sentence: {s!r}")


class TestPlacementAfterWelcome(unittest.TestCase):
    def _delivered_467(self):
        uncovered = ar.reconcile_named_place_announcement(NAMED_467, FINAL_467)
        sentence = ar.build_named_place_intro_sentence(uncovered)
        return swt.inject_named_place_after_welcome(DELIVERED_467, sentence), sentence

    def test_sentence_lands_after_the_welcome_not_in_orientation(self):
        final, sentence = self._delivered_467()
        self.assertIn(sentence, final)

        # The Orientation LINE is left exactly as it was — the announcement is NOT
        # spliced into it (the tour-467 bug).
        self.assertIn(
            "Orientation: As you arrive at Red Canyon, look up at the ribboned "
            "walls of ochre and cream.", final)

        welcome_idx = final.index("You are about to embark on a journey")
        ann_idx = final.index(sentence)
        orient_idx = final.index("Orientation: As you arrive")
        # After the welcome, and after (not inside) the Orientation line.
        self.assertLess(welcome_idx, ann_idx,
                        "the announcement must come AFTER the welcome")
        self.assertLess(orient_idx, ann_idx)

    def test_announced_exactly_once(self):
        final, _ = self._delivered_467()
        self.assertEqual(1, final.count("White Sand Dunes"),
                         "White Sand Dunes must be announced exactly once")

    def test_idempotent(self):
        final, sentence = self._delivered_467()
        twice = swt.inject_named_place_after_welcome(final, sentence)
        self.assertEqual(final, twice, "placement must not double the sentence")

    def test_all_covered_delivers_no_announcement(self):
        final_pois = FINAL_467 + [{"name": "White Sand Dunes"}]
        uncovered = ar.reconcile_named_place_announcement(NAMED_467, final_pois)
        sentence = ar.build_named_place_intro_sentence(uncovered)
        self.assertEqual("", sentence)
        out = swt.inject_named_place_after_welcome(DELIVERED_467, sentence)
        self.assertEqual(DELIVERED_467, out,
                         "no uncovered name → delivered text is unchanged")
        self.assertNotIn("could not be confirmed", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
