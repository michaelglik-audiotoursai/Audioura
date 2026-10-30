"""test_local832_story_refill.py — [LOCAL-832] regression tests.

The story-quality gate (D511 / LOCAL-487, step 7a) rejects a museum stop that has
no valid story and — before this ticket — kept it storyless after its own retry
failed, shipping fewer-than-honest tours (LOCAL-828 / 828B live, Rijksmuseum
cheap arm: 5/5 stops storyless, tour shipped 3/5). This fix REPLACES a
still-storyless stop with the next verified work from the reserve, narrated and
re-gated, up to 2 rounds, before delivering it storyless.

These tests cover the PURE selection half (museum_story_refill), built directly
from the 828B log fixture — the five Rijksmuseum stops the gate flagged — plus
the yield-order, de-duplication, cap and round-exhaustion contracts. No network,
no DB, no LLM.

Run: python3 -m pytest test_local832_story_refill.py -q
 or: python3 -m unittest test_local832_story_refill -v
"""
import unittest

from museum_story_refill import (
    normalize_title,
    stop_titles,
    available_reserve,
    plan_refill_round,
    refill_log_line,
    RefillPlan,
    DEFAULT_ROUNDS,
)

# ---- Fixture: the five Rijksmuseum stops step 7a flagged in the 828B live log
# (submission_artifacts/local828b_live.log ~1283-1288). All five were storyless;
# step 7a's cap=1 retried only stop 1. The reserve is the venue's verified works
# in prominence/yield order (LOCAL-632 _museum_verified_reserve); its first
# entries repeat the works that are ALREADY stops, so a correct refill must skip
# those and reach the untried long tail.
RIJKS_STOPS = [
    {"name": "The Great Wave off Kanagawa (De grote golf bij Kanagawa)",
     "_story_index": 20},
    {"name": "The Night Watch", "_story_index": 55},
    {"name": "The Milkmaid", "_story_index": 44},
    {"name": "'Het Joodse bruidje'", "_story_index": 40},
    {"name": "View of Houses in Delft", "_story_index": 30},
]
RIJKS_RESERVE = [
    "The Night Watch",
    "The Milkmaid",
    "'Het Joodse bruidje'",
    "The Great Wave off Kanagawa (De grote golf bij Kanagawa)",
    "View of Houses in Delft",
    "Woman Reading a Letter",
    "Self-Portrait as the Apostle Paul",
    "Winter Landscape with Ice Skaters",
    "The Threatened Swan",
    "Still Life with Asparagus",
]


class TestNormalizeAndTitles(unittest.TestCase):
    def test_normalize_is_case_and_space_insensitive(self):
        self.assertEqual(normalize_title("  The  Night   Watch "),
                         "the night watch")
        self.assertEqual(normalize_title("THE MILKMAID"), "the milkmaid")

    def test_normalize_reads_dict_titles(self):
        self.assertEqual(normalize_title({"name": "The Milkmaid"}),
                         "the milkmaid")
        self.assertEqual(normalize_title({"title": "The Night Watch"}),
                         "the night watch")

    def test_stop_titles_from_dicts_and_strings(self):
        self.assertEqual(
            stop_titles([{"name": "A"}, "B", {"title": "C"}]),
            ["A", "B", "C"])


class TestAvailableReserve(unittest.TestCase):
    def test_skips_titles_already_stops(self):
        used = [s["name"] for s in RIJKS_STOPS]
        avail = available_reserve(RIJKS_RESERVE, used_titles=used)
        # The first five reserve entries ARE the current stops — all skipped.
        self.assertNotIn("The Night Watch", avail)
        self.assertNotIn("The Milkmaid", avail)
        self.assertEqual(avail[0], "Woman Reading a Letter")
        self.assertEqual(len(avail), 5)

    def test_skips_tried_titles(self):
        used = [s["name"] for s in RIJKS_STOPS]
        avail = available_reserve(
            RIJKS_RESERVE, used_titles=used,
            tried_titles=["Woman Reading a Letter"])
        self.assertNotIn("Woman Reading a Letter", avail)
        self.assertEqual(avail[0], "Self-Portrait as the Apostle Paul")

    def test_dedups_within_reserve_case_insensitively(self):
        avail = available_reserve(
            ["Woman Reading a Letter", "woman reading a letter", "Other"])
        self.assertEqual(avail, ["Woman Reading a Letter", "Other"])

    def test_preserves_yield_order(self):
        avail = available_reserve(RIJKS_RESERVE,
                                  used_titles=[s["name"] for s in RIJKS_STOPS])
        self.assertEqual(avail, [
            "Woman Reading a Letter",
            "Self-Portrait as the Apostle Paul",
            "Winter Landscape with Ice Skaters",
            "The Threatened Swan",
            "Still Life with Asparagus",
        ])


class TestPlanRefillRound(unittest.TestCase):
    def test_worst_first_paired_with_next_yield_work(self):
        # Caller passes storyless stops worst-first (by step-5 index): stop 0
        # (index 20) then stop 4 (index 30).
        plan = plan_refill_round([0, 4], RIJKS_STOPS, RIJKS_RESERVE)
        self.assertIsInstance(plan, RefillPlan)
        self.assertEqual(len(plan.assignments), 2)
        self.assertEqual(plan.assignments[0].stop_index, 0)
        self.assertEqual(plan.assignments[0].new_title, "Woman Reading a Letter")
        self.assertEqual(plan.assignments[1].stop_index, 4)
        self.assertEqual(plan.assignments[1].new_title,
                         "Self-Portrait as the Apostle Paul")
        self.assertEqual(plan.unfilled, [])

    def test_never_proposes_a_title_already_a_stop(self):
        plan = plan_refill_round([0, 1, 2, 3, 4], RIJKS_STOPS, RIJKS_RESERVE)
        proposed = {a.new_title for a in plan.assignments}
        current = {s["name"] for s in RIJKS_STOPS}
        self.assertEqual(proposed & current, set())

    def test_round_two_does_not_repeat_round_one_titles(self):
        p1 = plan_refill_round([0, 4], RIJKS_STOPS, RIJKS_RESERVE)
        p2 = plan_refill_round([0, 4], RIJKS_STOPS, RIJKS_RESERVE,
                               tried_titles=p1.tried_after)
        t1 = {a.new_title for a in p1.assignments}
        t2 = {a.new_title for a in p2.assignments}
        self.assertEqual(t1 & t2, set())
        self.assertEqual(p2.assignments[0].new_title,
                         "Winter Landscape with Ice Skaters")

    def test_reserve_exhaustion_marks_unfilled(self):
        # Only ONE untried reserve work; two storyless stops.
        small_reserve = ["The Night Watch", "The Milkmaid", "'Het Joodse bruidje'",
                         "The Great Wave off Kanagawa (De grote golf bij Kanagawa)",
                         "View of Houses in Delft", "Woman Reading a Letter"]
        plan = plan_refill_round([0, 2], RIJKS_STOPS, small_reserve)
        self.assertEqual(len(plan.assignments), 1)
        self.assertEqual(plan.assignments[0].new_title, "Woman Reading a Letter")
        self.assertEqual(plan.unfilled, [2])

    def test_cap_limits_stops_touched(self):
        plan = plan_refill_round([0, 1, 2, 3, 4], RIJKS_STOPS, RIJKS_RESERVE,
                                 cap=2)
        self.assertEqual(len(plan.assignments), 2)
        self.assertEqual([a.stop_index for a in plan.assignments], [0, 1])

    def test_cost_cap_implicit_one_work_per_stop(self):
        # No stop is offered more than one reserve work in a single round.
        plan = plan_refill_round([0, 2, 4], RIJKS_STOPS, RIJKS_RESERVE)
        per_stop = [a.stop_index for a in plan.assignments]
        self.assertEqual(len(per_stop), len(set(per_stop)))

    def test_empty_storyless_is_noop(self):
        plan = plan_refill_round([], RIJKS_STOPS, RIJKS_RESERVE)
        self.assertFalse(plan.has_work)
        self.assertEqual(plan.assignments, [])

    def test_empty_reserve_leaves_all_unfilled(self):
        plan = plan_refill_round([0, 2], RIJKS_STOPS, [])
        self.assertEqual(plan.assignments, [])
        self.assertEqual(plan.unfilled, [0, 2])


class TestTwoRoundExhaustionWalkthrough(unittest.TestCase):
    """End-to-end selection over DEFAULT_ROUNDS, mirroring the orchestrator loop:
    each round, a rejected candidate frees its slot, which carries to the next
    round and draws the next untried reserve work — until the reserve runs dry.
    """

    def test_default_rounds_is_two(self):
        self.assertEqual(DEFAULT_ROUNDS, 2)

    def test_two_rounds_consume_distinct_works(self):
        still = [0, 2]
        tried = []
        seen = []
        for _ in range(DEFAULT_ROUNDS):
            plan = plan_refill_round(still, RIJKS_STOPS, RIJKS_RESERVE,
                                     tried_titles=tried)
            tried = plan.tried_after
            seen.extend(a.new_title for a in plan.assignments)
            # Simulate: all rejected, slots carry forward.
            still = [a.stop_index for a in plan.assignments] + plan.unfilled
        self.assertEqual(len(seen), len(set(seen)))  # no title tried twice
        self.assertEqual(len(seen), 4)               # 2 stops x 2 rounds


class TestRefillLogLine(unittest.TestCase):
    def test_swap_line_names_both_works(self):
        line = refill_log_line("Rijksmuseum", "The Milkmaid",
                               "Woman Reading a Letter")
        self.assertEqual(
            line,
            "[LOCAL-832] story-gate refill Rijksmuseum "
            "'The Milkmaid' → 'Woman Reading a Letter'")

    def test_count_summary_line(self):
        self.assertEqual(
            refill_log_line("Orsay Museum", 2, 2),
            "[LOCAL-832] story-gate refill Orsay Museum 2 → 2")

    def test_list_forms_render(self):
        line = refill_log_line("Rijksmuseum", ["A", "B"], ["C", "D"])
        self.assertEqual(
            line,
            "[LOCAL-832] story-gate refill Rijksmuseum 'A', 'B' → 'C', 'D'")


if __name__ == "__main__":
    unittest.main()
