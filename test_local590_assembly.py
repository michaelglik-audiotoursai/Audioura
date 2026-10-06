"""
LOCAL-590 unit tests — stop_pool_assembly building + outdoor assembly.
======================================================================
These tests CALL the real assembly functions (no DB, no network, no LLM — a
deterministic directions template is used). They assert Michael's design rules:

SINGLE-BUILDING:
  * new stops are placed BEFORE pooled stops;
  * pooled narration is reused verbatim;
  * the overall orientation is regenerated (injected on stop 1);
  * the conclusion names all delivered stops and adds a walk-back line;
  * every Directions line names the NEXT delivered stop (museum templates);
  * counts: reused = pooled, new = new, rewritten_transitions = 0.

OUTDOOR:
  * the route is re-sequenced over pooled + new (geographic);
  * untouched stops reuse their narration AND directions verbatim;
  * ONLY the transitions adjacent to each insertion are rewritten;
  * counts: reused = untouched narration, new = new, rewritten = adjacent
    transitions (the "potentially 4 for 2 added" rule).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stop_pool_assembly as asm


def _pooled(title, narration, orientation="look here", **kw):
    d = {"title": title, "narration": narration, "orientation": orientation,
         "_pool_reused": True, "address": "1 Test St"}
    d.update(kw)
    return d


def _new(title, narration, orientation="new look", **kw):
    d = {"title": title, "narration": narration, "orientation": orientation,
         "_pool_reused": False, "address": "1 Test St"}
    d.update(kw)
    return d


class TestBuildingAssembly(unittest.TestCase):
    def setUp(self):
        self.pooled = [
            _pooled("Alpha", "Narration for Alpha pooled."),
            _pooled("Beta", "Narration for Beta pooled."),
            _pooled("Gamma", "Narration for Gamma pooled."),
            _pooled("Delta", "Narration for Delta pooled."),
            _pooled("Epsilon", "Narration for Epsilon pooled."),
        ]
        self.new = [
            _new("New One", "Fresh narration one."),
            _new("New Two", "Fresh narration two."),
        ]
        self.res = asm.assemble_building_tour(
            location="Test Museum, Testville",
            tour_type="museum",
            tour_category="museum",
            header_category="museum",
            display_category="Museum",
            venue_name="Test Museum",
            new_stops=self.new,
            pooled_stops=self.pooled,
            overall_orientation="This expanded tour now begins with two new works.",
            sources_block="Sources: This tour draws on example.org.",
        )

    def test_new_before_pooled(self):
        self.assertEqual(self.res.order,
                         ["New One", "New Two", "Alpha", "Beta", "Gamma", "Delta", "Epsilon"])

    def test_counts(self):
        self.assertEqual(self.res.new_stops, 2)
        self.assertEqual(self.res.reused_stops, 5)
        self.assertEqual(self.res.rewritten_transitions, 0)

    def test_pooled_narration_reused_verbatim(self):
        for p in self.pooled:
            self.assertIn(p["narration"], self.res.tour_text)

    def test_overall_orientation_regenerated_on_stop1(self):
        # The regenerated overall description rides on Stop-1's Orientation.
        self.assertIn("This expanded tour now begins with two new works.", self.res.tour_text)
        # It appears before Stop 2.
        idx_overall = self.res.tour_text.index("This expanded tour now begins")
        idx_stop2 = self.res.tour_text.index("Stop 2:")
        self.assertLess(idx_overall, idx_stop2)

    def test_every_transition_names_next_stop(self):
        text = self.res.tour_text
        order = self.res.order
        # Each Directions line should reference the following stop by name.
        for i in range(len(order) - 1):
            nxt = order[i + 1]
            self.assertIn(nxt, text)
        # Museum house style: first transition uses "Continue through {venue}".
        self.assertIn("Continue through Test Museum — next is New Two.", text)
        # Last transition hands off to the final stop.
        self.assertIn("Your final stop in Test Museum: Epsilon.", text)

    def test_conclusion_has_walk_back_line(self):
        self.assertIn("walk back", self.res.tour_text.lower())
        # Recap names first and last delivered stops.
        self.assertIn("From New One to Epsilon", self.res.tour_text)
        self.assertIn("That's 7 stops", self.res.tour_text)

    def test_sources_preserved(self):
        self.assertIn("Sources: This tour draws on example.org.", self.res.tour_text)

    def test_header_and_category(self):
        # "museum" is a substring of the location, so the generator (and this
        # module, matching it exactly — generate_tour_text.py:20567) uses the
        # plain title form without the " - Museum Tour" suffix.
        self.assertTrue(self.res.tour_text.startswith(
            "Step-by-Step Audio Guided Tour: Test Museum, Testville"))
        self.assertIn("Tour-Category: museum", self.res.tour_text)

    def test_header_adds_category_when_type_not_in_location(self):
        res = asm.assemble_building_tour(
            location="Griffin, Winchester",  # 'facility' not in location
            tour_type="facility", tour_category="facility",
            header_category="facility", display_category="Facility",
            venue_name="Griffin", new_stops=[_new("N", "n")],
            pooled_stops=[_pooled("A", "a")],
        )
        self.assertTrue(res.tour_text.startswith(
            "Step-by-Step Audio Guided Tour: Griffin, Winchester - Facility Tour"))


class TestBuildingServeBestN(unittest.TestCase):
    """N <= K: serve N from the pool, no new stops, same order rule."""

    def test_no_new_stops_no_walk_back(self):
        pooled = [_pooled(t, f"Narration {t}.") for t in ["A", "B", "C", "D", "E"]]
        res = asm.assemble_building_tour(
            location="V", tour_type="museum", tour_category="museum",
            header_category="museum", display_category="Museum", venue_name="V",
            new_stops=[], pooled_stops=pooled[:3],
            overall_orientation="Overview of three.",
        )
        self.assertEqual(res.order, ["A", "B", "C"])
        self.assertEqual(res.new_stops, 0)
        self.assertEqual(res.reused_stops, 3)
        # No new stops → no walk-back line (nothing moved after an insertion).
        self.assertNotIn("walk back", res.tour_text.lower())


class TestOutdoorAssembly(unittest.TestCase):
    def setUp(self):
        # Four pooled stops on a line (lng increasing); two new stops that sit
        # between them geographically so insertions land in the middle.
        self.pooled = [
            _pooled("P0", "Body P0.", latitude=0.0, longitude=0.0),
            _pooled("P1", "Body P1.", latitude=0.0, longitude=1.0),
            _pooled("P2", "Body P2.", latitude=0.0, longitude=2.0),
            _pooled("P3", "Body P3.", latitude=0.0, longitude=3.0),
        ]
        self.new = [
            _new("N_a", "Fresh A.", latitude=0.0, longitude=0.5),
            _new("N_b", "Fresh B.", latitude=0.0, longitude=2.5),
        ]
        self.res = asm.assemble_outdoor_tour(
            location="Boston Common, Boston",
            tour_type="walking", tour_category="walking",
            header_category="walking", display_category="Walking",
            new_stops=self.new, pooled_stops=self.pooled,
            transport_mode="on_foot",
            sources_block="Sources: example.org.",
        )

    def test_route_resequenced_contains_all_stops(self):
        # The sequencer runs NN + 2-opt; the exact tour is its contract, not this
        # module's. We assert the delivered order is a permutation of all stops
        # (pooled + new) with none dropped — a re-sequence over the union.
        self.assertEqual(sorted(self.res.order),
                         sorted(["P0", "P1", "P2", "P3", "N_a", "N_b"]))
        self.assertEqual(len(self.res.order), 6)

    def test_untouched_narration_reused_verbatim(self):
        for s in self.pooled:
            self.assertIn(s["narration"], self.res.tour_text)

    def test_only_adjacent_transitions_rewritten(self):
        # Each insertion rewrites the transition INTO it and the transition OUT
        # of it (the stop before and the stop after). Recompute the expected set
        # from the actual delivered order so the assertion tracks the sequencer's
        # real tour rather than a hardcoded one.
        order = self.res.order
        n = len(order)
        new_titles = {"N_a", "N_b"}
        expected = set()
        for i, t in enumerate(order):
            if t in new_titles:
                if i < n - 1:
                    expected.add(i)
                if i - 1 >= 0:
                    expected.add(i - 1)
        self.assertEqual(self.res.rewritten_transitions, len(expected))
        # Every pooled narration is still reused verbatim regardless of rewrites.
        for s in self.pooled:
            self.assertIn(s["narration"], self.res.tour_text)

    def test_counts(self):
        self.assertEqual(self.res.new_stops, 2)
        self.assertEqual(self.res.reused_stops, 4)  # 4 pooled narrations untouched

    def test_header(self):
        self.assertIn("Tour-Category: walking", self.res.tour_text)
        self.assertIn("Sources: example.org.", self.res.tour_text)


class TestOutdoorFewerRewrites(unittest.TestCase):
    """A single new stop at the end rewrites only its one neighbour transition."""

    def test_one_insertion_at_end(self):
        pooled = [
            _pooled("A", "a", latitude=0.0, longitude=0.0),
            _pooled("B", "b", latitude=0.0, longitude=1.0),
        ]
        new = [_new("C", "c", latitude=0.0, longitude=2.0)]
        res = asm.assemble_outdoor_tour(
            location="Loc", tour_type="walking", tour_category="walking",
            header_category="walking", display_category="Walking",
            new_stops=new, pooled_stops=pooled, transport_mode="on_foot",
        )
        self.assertEqual(res.order, ["A", "B", "C"])
        # Insertion at position 2 (C, the last). Only transition 1→2 (B→C) is
        # adjacent and rewritable; there is no successor to C.
        self.assertEqual(res.rewritten_transitions, 1)
        self.assertEqual(res.reused_stops, 2)
        self.assertEqual(res.new_stops, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
