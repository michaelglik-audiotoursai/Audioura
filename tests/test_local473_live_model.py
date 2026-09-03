#!/usr/bin/env python3
"""test_local473_live_model.py — LOCAL-473 bar item 3: the REAL model.

A stub cannot prove a judgement. LOCAL-472 shipped 18 green stubbed tests over a
gate that KEEPS the paragraph it exists to delete, because the stub answered the
way the author expected, not the way the model actually does. So the two verdicts
the task turns on are proven here against the real model:

  Bar 1  Michael's Example A is transferable=True at high confidence, with
         siblings ['Villa Leopolda','Musee Matisse'], with ['Cap Ferrat'], and
         with [] — the SAME verdict every time.
  Bar 2  The Cimiez Monastery paragraph is transferable=False (survives) with
         those same three sibling sets.

These make one network call per (paragraph, sibling-set) via the gate's real
default LLM path (llm_fn=None → _default_llm → OpenAI). They SKIP cleanly when no
OPENAI_API_KEY is present so CI stays deterministic; run them locally / in a keyed
job to satisfy the bar. Model is pinned via STOP_SPECIFICITY_MODEL (default
gpt-4o-mini), matching the wiring in generate_tour_text.py PHASE 5.152.

Run:  OPENAI_API_KEY=... python3 -m pytest tests/test_local473_live_model.py -s -v
The -s flag prints the actual verdicts so they can be pasted into the submission.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stop_specificity_gate as g

API_KEY = os.environ.get('OPENAI_API_KEY')
MODEL = os.environ.get('STOP_SPECIFICITY_MODEL', 'gpt-4o-mini')

EXAMPLE_A = (
    "Cycling on the French Riviera, stop at Cap d'Antibes to experience the "
    "enduring power of nature, inspiring creativity and stimulating the "
    "imagination while admiring panoramic views and soaking up the atmosphere "
    "of this everyday paradise."
)

CIMIEZ_MONASTERY = (
    "The Cimiez Monastery, with roots stretching back to the 9th century, stands "
    "as a silent witness to the passage of time and the resilience of faith. The "
    "Count of Savoy ordered the destruction of buildings, including the "
    "Franciscans' entire monastery, in a desperate act of defense. In 1546, a "
    "pivotal moment unfolded when Franciscan friars negotiated a property swap "
    "with Benedictine monks of Saint-Pons Abbey, acquiring a small chapel and "
    "plot of land in Cimiez. The French Revolution brought turmoil once more, as "
    "the monastery was seized and transformed into military barracks and an army "
    "hospital. Henri Matisse, whose affinity for Cimiez's luminous light is well "
    "known, rests in the cemetery nearby, a callback to the Musée Matisse you "
    "visited earlier."
)

SIBLING_SETS = (
    ['Villa Leopolda', 'Musee Matisse'],
    ['Cap Ferrat'],
    [],
)


@unittest.skipUnless(API_KEY, "OPENAI_API_KEY not set — live model test skipped")
class TestLiveModel(unittest.TestCase):

    def _run(self, paragraph, stop_name):
        out = []
        for siblings in SIBLING_SETS:
            res = g.check_paragraph_specificity(
                paragraph, stop_name, siblings,
                api_key=API_KEY, llm_fn=None, model=MODEL,
            )
            print(f"\n[LIVE {MODEL}] stop={stop_name!r} siblings={siblings} "
                  f"-> transferable={res['transferable']} "
                  f"conf={res['confidence']} kind={res.get('kind')} "
                  f"referent={res.get('referent')!r}\n   reason: {res['reason']}")
            out.append(res)
        return out

    def test_example_a_transferable_high_every_sibling_set(self):
        """Bar 1: Example A must be transferable=True at high confidence for all
        three sibling sets — the same verdict every time."""
        results = self._run(EXAMPLE_A, "Cap d'Antibes")
        for res, siblings in zip(results, SIBLING_SETS):
            self.assertTrue(res['transferable'],
                            f"siblings={siblings}: expected transferable, got {res}")
            self.assertEqual(res['confidence'], 'high',
                             f"siblings={siblings}: {res}")
        verdicts = {(r['transferable'], r['confidence']) for r in results}
        self.assertEqual(len(verdicts), 1,
                         f"verdict varied across sibling sets: {verdicts}")

    def test_cimiez_specific_every_sibling_set(self):
        """Bar 2: the Cimiez Monastery paragraph must survive (transferable=False)
        for all three sibling sets."""
        results = self._run(CIMIEZ_MONASTERY, "Cimiez Monastery")
        for res, siblings in zip(results, SIBLING_SETS):
            self.assertFalse(res['transferable'],
                             f"siblings={siblings}: expected specific, got {res}")

    def test_cimiez_survives_apply_gate_live(self):
        """Bar 2, end to end: through apply_stop_specificity_gate against the real
        model, the Cimiez paragraph is not removed, for each sibling shape."""
        sib_by_set = {
            0: [{'name': 'Villa Leopolda', 'description': 'Built in 1902.'},
                {'name': 'Musee Matisse', 'description': 'Opened in 1963.'}],
            1: [{'name': 'Cap Ferrat', 'description': 'A wooded peninsula.'}],
            2: [],
        }
        for idx in (0, 1, 2):
            tour = [{'name': 'Cimiez Monastery', 'description': CIMIEZ_MONASTERY}]
            tour += sib_by_set[idx]
            stats = g.apply_stop_specificity_gate(
                tour, api_key=API_KEY, model=MODEL)
            print(f"\n[LIVE apply set{idx}] removed={stats['paragraphs_removed']} "
                  f"stops_affected={stats['stops_affected']}")
            self.assertEqual(stats['paragraphs_removed'], 0,
                             f"set{idx}: Cimiez wrongly removed: {stats}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
