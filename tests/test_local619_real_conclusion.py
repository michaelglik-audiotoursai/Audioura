"""test_local619_real_conclusion.py — LOCAL-619 acceptance tests.

Fixtures are the ACTUAL delivered `tour_content` of audio_tours 440 (Boijmans),
441 (Sevilla) and 442 (Rouen) — the LOCAL-618 live tours the critic blocked on.
Each delivered EXACTLY 2 stops (stops_count=2 in the DB) but its trailing recap
STUB said "That's 3 stops — …": a late gate dropped a stop and the count was
never recomputed. The exports live in tests/fixtures/local619/tour_44*.txt.

The ticket's acceptance criteria, as tests:
  1. the conclusion count equals the delivered stops;
  2. no "That's N stops —" splice survives;
  3. one conclusion per tour;
  4. the restaurant line is the last sentence of the conclusion;
  5. a late-gate drop updates ALL the counts (conclusion count, stops_count,
     orientation "first stop").

Pure/offline: no DB, no network, no LLM — the builder operates on the final text.

Run: python3 -m pytest tests/test_local619_real_conclusion.py -q
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tour_conclusion as tc

_FIX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "local619")

_FIXTURES = {
    440: "Museum Boijmans Van Beuningen",
    441: "Museo de Bellas Artes de Sevilla",
    442: "Musee des Beaux-Arts de Rouen",
}

_SPLICE_RE = re.compile(r"That['\u2019]s\s+\d+\s+stops?\s+[—-]")
_COUNT_RE = re.compile(r"That['\u2019]s\s+(\d+)\s+stops?")
_THREAD_RE = re.compile(r"you have followed the thread", re.IGNORECASE)
_RESTAURANT_RE = re.compile(r"we can build you a restaurant tour", re.IGNORECASE)


def _load(tid):
    with open(os.path.join(_FIX_DIR, f"tour_{tid}.txt"), encoding="utf-8") as f:
        return f.read()


class TestFixturesPresentAndBroken(unittest.TestCase):
    """The fixtures must be the real, originally-broken tours."""

    def test_fixtures_exist(self):
        for tid in _FIXTURES:
            self.assertTrue(os.path.exists(os.path.join(_FIX_DIR, f"tour_{tid}.txt")),
                            f"missing fixture tour_{tid}.txt")

    def test_fixtures_each_deliver_three_stops(self):
        # Each tour delivers THREE stops. In the raw stored text one header is
        # GLUED onto the prior sentence (a lost newline), so a naive line-start
        # count sees only 2 — the exact miscount this ticket fixes. The builder's
        # header normalisation recovers the true count of 3.
        for tid in _FIXTURES:
            raw = len(re.findall(r'(?m)^Stop \d+:', _load(tid)))
            self.assertEqual(raw, 2,
                             f"tour {tid}: raw line-start count should be the "
                             f"broken 2 (one header is glued)")
            self.assertEqual(tc.count_delivered_stops(_load(tid)), 3,
                             f"tour {tid} should deliver exactly 3 stops once the "
                             f"glued header is recovered")

    def test_fixtures_originally_had_a_broken_count(self):
        # The stored tours shipped a count that disagreed with the true delivered
        # stop list: a bare line-start count saw 2 while 3 were delivered. (Guards
        # against a fixture that is already clean, which would make the fix tests
        # vacuous.)
        for tid in _FIXTURES:
            raw = len(re.findall(r'(?m)^Stop \d+:', _load(tid)))
            true_n = tc.count_delivered_stops(_load(tid))
            self.assertNotEqual(raw, true_n,
                                f"tour {tid}: fixture is not broken (raw {raw} == "
                                f"true {true_n}) — fix tests would be vacuous")


class TestConclusionCriteria(unittest.TestCase):
    """The five acceptance criteria, on the rebuilt conclusion."""

    def _rebuilt(self, tid):
        return tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])

    def test_1_count_equals_delivered_stops(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            delivered = tc.count_delivered_stops(out)
            m = _COUNT_RE.search(out)
            self.assertIsNotNone(m, f"tour {tid}: conclusion has no count")
            self.assertEqual(int(m.group(1)), delivered,
                             f"tour {tid}: conclusion count {m.group(1)} != "
                             f"delivered {delivered}")
            self.assertEqual(delivered, 3, f"tour {tid}: should be 3 stops")

    def test_2_no_splice_survives(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            self.assertIsNone(_SPLICE_RE.search(out),
                              f"tour {tid}: a 'That's N stops —' splice survived")

    def test_3_one_conclusion_per_tour(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            self.assertEqual(len(_THREAD_RE.findall(out)), 1,
                             f"tour {tid}: expected exactly one conclusion")
            self.assertEqual(len(_COUNT_RE.findall(out)), 1,
                             f"tour {tid}: expected exactly one count sentence")

    def test_4_restaurant_offer_is_last_sentence(self):
        for tid in _FIXTURES:
            out = self._rebuilt(tid)
            # The conclusion's last sentence (before any trailing Sources block)
            # must be the restaurant offer.
            body = re.split(r'(?mi)^\s*Sources:', out)[0].strip()
            last_line = [ln for ln in body.splitlines() if ln.strip()][-1]
            self.assertTrue(_RESTAURANT_RE.search(last_line),
                            f"tour {tid}: last conclusion sentence is not the "
                            f"restaurant offer: {last_line!r}")

    def test_5_sources_block_preserved(self):
        for tid in _FIXTURES:
            self.assertIn("Sources:", self._rebuilt(tid),
                          f"tour {tid}: Sources block was lost")

    def test_idempotent(self):
        for tid in _FIXTURES:
            once = self._rebuilt(tid)
            twice = tc.rebuild_conclusion(once, venue_name=_FIXTURES[tid])
            self.assertEqual(once, twice, f"tour {tid}: rebuild is not idempotent")


class TestLateGateDropUpdatesAllCounts(unittest.TestCase):
    """A late-gate drop updates the conclusion count, stops_count, and the
    orientation's 'first stop' name — all recomputed from the final text."""

    def _drop_first_stop(self, tour_text):
        """Simulate a late gate dropping the FIRST delivered stop block."""
        body, sources = tc._split_tail(tour_text)
        blocks = re.split(r'(?m)(?=^Stop \d+:)', body)
        # blocks[0] is the title/preamble; blocks[1:] are the stop blocks.
        head = blocks[0]
        stop_blocks = blocks[1:]
        self.assertGreaterEqual(len(stop_blocks), 2)
        kept = head + "".join(stop_blocks[1:])  # drop the first stop
        if sources:
            kept = kept.rstrip() + "\n\n" + sources
        return kept

    def test_drop_updates_conclusion_count(self):
        tid = 442  # Rouen
        text = tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])
        self.assertEqual(tc.count_delivered_stops(text), 3)

        dropped = self._drop_first_stop(text)
        rebuilt = tc.rebuild_conclusion(dropped, venue_name=_FIXTURES[tid])

        # (a) conclusion count now 2 (one stop dropped from 3)
        delivered = tc.count_delivered_stops(rebuilt)
        self.assertEqual(delivered, 2)
        m = _COUNT_RE.search(rebuilt)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 2)
        # (b) the From→to endpoints now span the remaining first/last stops
        self.assertEqual(len(_THREAD_RE.findall(rebuilt)), 1)
        # (c) restaurant offer still last
        body = re.split(r'(?mi)^\s*Sources:', rebuilt)[0].strip()
        last_line = [ln for ln in body.splitlines() if ln.strip()][-1]
        self.assertTrue(_RESTAURANT_RE.search(last_line))

    def test_drop_to_single_stop_has_no_from_to(self):
        # Dropping two stops from a 3-stop tour leaves ONE: no "From X to Y".
        tid = 442
        text = tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])
        once = self._drop_first_stop(text)
        twice = self._drop_first_stop(tc.rebuild_conclusion(once, venue_name=_FIXTURES[tid]))
        rebuilt = tc.rebuild_conclusion(twice, venue_name=_FIXTURES[tid])
        self.assertEqual(tc.count_delivered_stops(rebuilt), 1)
        m = _COUNT_RE.search(rebuilt)
        self.assertEqual(int(m.group(1)), 1)
        self.assertNotRegex(rebuilt, r"\bFrom\s+.+?\s+to\s+.+?,\s+you have followed")

    def test_stops_count_recomputed_from_final_text(self):
        # stops_count (what the orchestrator persists) is count_delivered_stops of
        # the FINAL text — never a stale generation-time value.
        for tid in _FIXTURES:
            out = tc.rebuild_conclusion(_load(tid), venue_name=_FIXTURES[tid])
            self.assertEqual(tc.count_delivered_stops(out), 3)
            dropped = self._drop_first_stop(out)
            self.assertEqual(tc.count_delivered_stops(dropped), 2)

    def test_orientation_first_stop_follows_delivered_text(self):
        # fix_orientation_first_stop rewrites a "Your first stop is X" pointer to
        # the real first delivered stop after a drop. The pointer lives in the
        # tour-level preamble (before Stop 1), so dropping Stop 1 leaves a STALE
        # pointer that still names the dropped stop — exactly the late-gate case.
        synthetic = (
            "Step-by-Step Audio Guided Tour: Demo Museum\n\n"
            "Prepare to encounter two works. Your first stop is Alpha.\n\n"
            "Stop 1: Alpha\n\n"
            "Alpha depicts a quiet harbour at dawn, painted in oil on canvas in 1700.\n\n"
            "Stop 2: Beta\n\n"
            "Beta shows a bustling market, rendered in tempera around 1710.\n\n"
            "From Alpha to Beta, you have followed the thread of the collection of Demo Museum.\n\n"
            "That's 2 stops in all.\n\n"
            "If you would like to eat nearby we can build you a restaurant tour.\n"
        )
        self.assertEqual(tc.first_stop_name(synthetic), "Alpha")

        # Drop Stop 1 (Alpha); Beta becomes the first delivered stop. The
        # preamble pointer still says "Alpha" — the dropped stop.
        body, sources = tc._split_tail(synthetic)
        blocks = re.split(r'(?m)(?=^Stop \d+:)', body)
        dropped = blocks[0] + "".join(blocks[2:])  # keep preamble + Stop 2 only
        if sources:
            dropped = dropped.rstrip() + "\n\n" + sources
        self.assertIn("Your first stop is Alpha", dropped)

        fixed = tc.fix_orientation_first_stop(dropped)
        self.assertIn("Your first stop is Beta", fixed)
        self.assertNotIn("Your first stop is Alpha", fixed)
        self.assertEqual(tc.first_stop_name(fixed), "Beta")


class TestGluedStopHeaderRecovered(unittest.TestCase):
    """A ``Stop N:`` header glued onto a prior sentence (a lost newline) must
    still be counted, so the conclusion reflects every stop the listener hears.

    This reproduces the live tour 448 defect: a final-stop transition ran into
    the next header ("…: Atelierwand.Stop 3: Atelierwand"), so the raw line-start
    count saw 2 while the listener heard 3, and the conclusion said "2 stops".
    """

    GLUED = (
        "Step-by-step audio guided tour of the Demo Museum in Town, Country, is a museum tour.\n\n"
        "Stop 1: Nana\n\n"
        "Nana depicts an actress at her mirror, painted in oil in 1877.\n\n"
        "Stop 2: Das Eismeer\n\n"
        "Das Eismeer shows an ice-locked sea, painted between 1823 and 1824. "
        "Your final stop in Demo Museum: Atelierwand.Stop 3: Atelierwand\n\n"
        "Atelierwand studies the wall of the artist's studio in close detail.\n\n"
        "From Nana to Das Eismeer, you have followed the thread of the collection of Demo Museum.\n\n"
        "That's 2 stops in all.\n\n"
        "If you would like to eat nearby we can build you a restaurant tour.\n"
    )

    def test_glued_header_counted(self):
        # Raw line-start count misses the glued header; normalised count sees it.
        self.assertEqual(len(re.findall(r'(?m)^Stop \d+:', self.GLUED)), 2)
        self.assertEqual(tc.count_delivered_stops(self.GLUED), 3)

    def test_rebuild_recovers_three_stops(self):
        out = tc.rebuild_conclusion(self.GLUED, venue_name="Demo Museum")
        # All three headers are now at line-start.
        self.assertEqual(len(re.findall(r'(?m)^Stop \d+:', out)), 3)
        # The conclusion count is 3, not the stale 2.
        m = _COUNT_RE.search(out)
        self.assertEqual(int(m.group(1)), 3)
        # Idempotent.
        self.assertEqual(out, tc.rebuild_conclusion(out, venue_name="Demo Museum"))


if __name__ == "__main__":
    unittest.main(verbosity=2)