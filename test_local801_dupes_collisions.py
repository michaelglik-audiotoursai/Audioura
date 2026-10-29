#!/usr/bin/env python3
"""test_local801_dupes_collisions.py — LOCAL-801.

Offline unit tests on the EXACT P1 blind-scoring strings (Arm A = gpt-4.1, the
cloud default). The fixtures in tests/fixtures/local801/ are the verbatim A
texts for the five flagged requests:

  w1 Freedom Trail (5 requested) — Park Street Church delivered twice, a stray
     "Stop 3: Boston Common — it is roughly … away." preview header, and the
     closing line said "That's 6 stops in all."
  w3 Salem (4 requested) — The Witch House body spliced into Stop 2's Directions,
     a stray "Stop 4: Salem Witch Museum — it is roughly …" preview header,
     "That's 5 stops in all."
  w4 Old Saigon (5 requested) — Independence Palace's body spliced into Stop 1's
     Directions (headerless) AND emitted as the real Stop 2.
  d1 JP coffee (3 requested) — Stop 1's opening mid-clause collision: "This route
     takes you from J.P. These stops reflect … Jamaica Plain. Licks in June 2021
     … at J.P. Your first stop is J.P. Licks.P. Licks.P. Licks."
  d2 North End (3 requested) — a clean tour; the guard must leave it unchanged.

Each test first ASSERTS the defect is present in the raw fixture (so the fixture
really reproduces it), then asserts the guard / the wired finalize choke point
repairs it. Dedup must NOT collapse w3/w4's genuinely-distinct but coordinate-
clustered stops. The collision repair must KEEP the legitimate lawsuit sentence
("filed a lawsuit against J.P. Licks, demanding …").

Run: python3 -m pytest test_local801_dupes_collisions.py -q
     python3 test_local801_dupes_collisions.py
"""
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FIX = os.path.join(_HERE, "tests", "fixtures", "local801")

import stop_dedup_collision_guard as g
import tour_conclusion as tc

_REQUESTED = {
    "w1_freedom_trail": 5,
    "w3_salem": 4,
    "w4_old_saigon": 5,
    "d1_jp_coffee": 3,
    "d2_north_end": 3,
}


def _load(name):
    with open(os.path.join(_FIX, name + ".txt"), encoding="utf-8") as f:
        return f.read()


def _headers(text):
    return re.findall(r'(?m)^Stop (\d+):[ \t]*(.+?)\s*$', text)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures reproduce the defect (guard against a stale fixture)
# ─────────────────────────────────────────────────────────────────────────────

class TestFixturesReproduceDefect(unittest.TestCase):
    def test_w1_overcounts_and_duplicates(self):
        raw = _load("w1_freedom_trail")
        self.assertIn("That's 6 stops in all.", raw)
        # Park Street Church body appears twice (duplicate).
        self.assertEqual(raw.count("1 Park St, Boston, MA 02108"), 2)
        # Stray preview header present.
        self.assertRegex(raw, r"(?m)^Stop 3: Boston Common \u2014 it is roughly")

    def test_w3_overcounts_and_duplicates(self):
        raw = _load("w3_salem")
        self.assertIn("That's 5 stops in all.", raw)
        self.assertEqual(raw.count("310 Essex St, Salem, MA 01970"), 2)
        self.assertRegex(raw, r"(?m)^Stop 4: Salem Witch Museum \u2014 it is roughly")

    def test_w4_splices_next_body(self):
        raw = _load("w4_old_saigon")
        # Independence Palace body is spliced into Stop 1's Directions (headerless)
        # AND emitted as the real Stop 2 — the architect name appears in both.
        self.assertGreaterEqual(raw.count("Ngô Viết Thụ"), 3)

    def test_d1_mid_clause_collision(self):
        raw = _load("d1_jp_coffee")
        self.assertIn("Licks.P. Licks.P. Licks", raw)
        self.assertIn("This route takes you from J.P. These stops reflect", raw)

    def test_d2_is_clean(self):
        raw = _load("d2_north_end")
        self.assertIn("That's 3 stops in all.", raw)
        self.assertEqual(len(_headers(raw)), 3)


# ─────────────────────────────────────────────────────────────────────────────
# The guard repairs each defect
# ─────────────────────────────────────────────────────────────────────────────

class TestDedupAndCount(unittest.TestCase):
    def _assert_count(self, name):
        req = _REQUESTED[name]
        out, _rep = g.guard(_load(name), requested_stops=req)
        delivered = tc.count_delivered_stops(out)
        self.assertEqual(delivered, req,
                         f"{name}: delivered {delivered} != requested {req}")
        # Headers are renumbered 1..k with no gaps or repeats.
        nums = [int(n) for n, _ in _headers(tc.normalise_stop_headers(out))]
        self.assertEqual(nums, list(range(1, req + 1)))
        return out

    def test_w1_five_stops_no_duplicate(self):
        out = self._assert_count("w1_freedom_trail")
        # Park Street Church body now appears exactly once.
        self.assertEqual(out.count("1 Park St, Boston, MA 02108"), 1)
        # No stray preview header remains.
        self.assertNotRegex(out, r"(?m)^Stop \d+: .* \u2014 it is roughly")
        titles = [t for _, t in _headers(tc.normalise_stop_headers(out))]
        self.assertEqual(titles, ["Faneuil Hall", "Park Street Church",
                                  "Boston Common", "King's Chapel",
                                  "Massachusetts State House"])

    def test_w3_four_stops_distinct_places_kept(self):
        out = self._assert_count("w3_salem")
        titles = [t for _, t in _headers(tc.normalise_stop_headers(out))]
        # The Salem Witch Museum (~57 m from the Trials Memorial) is a DISTINCT
        # place and must survive — coordinate proximity alone must not drop it.
        self.assertIn("Salem Witch Museum", titles)
        self.assertIn("Salem Witch Trials Memorial", titles)
        # The Witch House appears once (the spliced headerless copy removed).
        self.assertEqual(out.count("310 Essex St, Salem, MA 01970"), 1)

    def test_w4_five_clustered_places_all_kept(self):
        out = self._assert_count("w4_old_saigon")
        titles = [t for _, t in _headers(tc.normalise_stop_headers(out))]
        # Five genuinely distinct District 1 places, all within ~50 m of each
        # other by the LLM's approximate coordinates — none may be merged.
        for expect in ["War Remnants Museum", "Independence Palace",
                       "Ben Thanh Market", "Nguyen Hue Walking Street",
                       "Bitexco Financial Tower"]:
            self.assertIn(expect, titles)

    def test_requested_cap_never_exceeds(self):
        # Even if dedup left more than requested, the cap trims to requested.
        for name, req in _REQUESTED.items():
            out, _ = g.guard(_load(name), requested_stops=req)
            self.assertLessEqual(tc.count_delivered_stops(out), req, name)


class TestCollisionGuard(unittest.TestCase):
    def test_d1_collision_repaired(self):
        out, rep = g.guard(_load("d1_jp_coffee"), requested_stops=3)
        # Welded repeat gone.
        self.assertNotIn("Licks.P. Licks", out)
        # Dangling debris fragments gone.
        self.assertNotIn("from J.P. These", out)
        self.assertNotIn("back rent at J.P. Your", out)
        # The collision guard logged a repair on Stop 1.
        self.assertGreaterEqual(rep["collision"]["repaired"], 1)
        self.assertIn("J.P. Licks", rep["collision"]["stops"])

    def test_d1_preserves_legitimate_lawsuit_sentence(self):
        out, _ = g.guard(_load("d1_jp_coffee"), requested_stops=3)
        # "against J.P. Licks, demanding" has no collision glue (Licks is the
        # completion, not a sentence-starter) and must be preserved intact.
        self.assertIn("filed a lawsuit against J.P. Licks, demanding", out)
        self.assertIn("Your first stop is J.P. Licks", out)

    def test_clean_prose_untouched(self):
        clean = ("Stop 1: Café\n\nOrientation: This is a calm café. We visited "
                 "St. Mary's church first. Dr. Lee runs the U.S. branch.\n\n")
        out, rep = g.repair_collisions(clean)
        self.assertEqual(rep["repaired"], 0)
        self.assertIn("St. Mary's church", out)
        self.assertIn("U.S. branch", out)

    def test_weld_repeat_collapse(self):
        txt = ("Stop 1: J.P. Licks\n\nOrientation: Your first stop is J.P. "
               "Licks.P. Licks.P. Licks. It opens at nine.\n\n")
        out, rep = g.repair_collisions(txt)
        self.assertNotIn("Licks.P. Licks", out)
        self.assertIn("Your first stop is J.P. Licks", out)
        self.assertGreaterEqual(rep["repaired"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# Wired choke point + idempotency + clean-tour safety
# ─────────────────────────────────────────────────────────────────────────────

class TestWiredChokePoint(unittest.TestCase):
    def test_count_delivered_stops_corrects_overcount(self):
        # count_delivered_stops routes through normalise_stop_headers, which now
        # carries the LOCAL-801 guard, so the raw defect fixtures already count
        # correctly with no extra call.
        self.assertEqual(tc.count_delivered_stops(_load("w1_freedom_trail")), 5)
        self.assertEqual(tc.count_delivered_stops(_load("w3_salem")), 4)
        self.assertEqual(tc.count_delivered_stops(_load("w4_old_saigon")), 5)
        self.assertEqual(tc.count_delivered_stops(_load("d1_jp_coffee")), 3)
        self.assertEqual(tc.count_delivered_stops(_load("d2_north_end")), 3)

    def test_normalise_is_idempotent_on_all_fixtures(self):
        for name in _REQUESTED:
            once = tc.normalise_stop_headers(_load(name))
            twice = tc.normalise_stop_headers(once)
            self.assertEqual(once, twice, f"{name}: normalise not idempotent")

    def test_clean_tour_unchanged(self):
        raw = _load("d2_north_end")
        out, rep = g.guard(raw, requested_stops=3)
        self.assertEqual(rep["dedup"]["dropped_preview"], 0)
        self.assertEqual(rep["dedup"]["despliced"], 0)
        self.assertEqual(rep["dedup"]["dropped_duplicate"], 0)
        self.assertEqual(rep["collision"]["repaired"], 0)
        self.assertEqual(out.strip(), raw.strip())

    def test_guard_idempotent(self):
        for name, req in _REQUESTED.items():
            out1, _ = g.guard(_load(name), requested_stops=req)
            out2, _ = g.guard(out1, requested_stops=req)
            self.assertEqual(out1, out2, f"{name}: guard not idempotent")

    def test_empty_and_headerless_inputs(self):
        self.assertEqual(g.guard("", requested_stops=3)[0], "")
        plain = "Just a paragraph with no stops at all."
        out, _ = g.guard(plain, requested_stops=3)
        self.assertIn("Just a paragraph", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
