#!/usr/bin/env python3
"""test_local580_fabrication_guard.py — Deliverable 3 (LOCAL-580).

LOCAL-577 added a hedged refill: a stop D1v2 dropped on a canonical-TITLE
mismatch ("no canonical match") is re-admitted (verified=False) so a museum tour
delivers the count the listener asked for. The intent was to rescue a REAL work
whose title merely did not line up with the venue's corpus
(Palais Lascaris / "The Adoration of the Magi").

The latent fabrication bug (LOCAL-580): "no canonical match" is ALSO exactly the
verdict a GPT-INVENTED title gets — the Griffin failure invented five generic
shows ("The American Dream", "The Human Condition", ...), all dropped with that
reason. As shipped, LOCAL-577 would re-admit those fabrications as hedged stops.
A fabrication must NEVER ship, hedged or not.

The guard (exists_fn): a title-mismatch drop is only re-admitted if its existence
is not DEFINITIVELY disproven. An invented title whose existence check returns
False is dropped; a real work whose existence check returns True is kept; an
inconclusive check (None) does not block (D162 — a search that didn't run is not
absence).

Run: python3 test_local580_fabrication_guard.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate_tour_text as gtt  # noqa: E402


def _poi(name):
    return {'name': name, 'address': ''}


# The five shows GPT invented for Griffin (0 SPARQL works) — none exist.
INVENTED_SHOWS = [
    'The American Dream',
    'The Human Condition',
    'Shadows and Light',
    'Portraits of a Nation',
    'Visions of Tomorrow',
]

# D1v2 drops every invented show on a canonical-title mismatch — the SAME verdict
# a real-but-unmatched work gets. That collision is the whole danger.
INVENTED_EVIDENCE = {
    name: {'status': 'DROPPED', 'reason': 'no canonical match'}
    for name in INVENTED_SHOWS
}


def _exists_none_of_the_invented(name):
    """Existence check: none of the invented titles exist (definitive False)."""
    return False


class TestFabricationGuardBlocksInventedTitles(unittest.TestCase):
    def test_five_invented_zero_readmitted(self):
        pool = gtt._title_mismatch_refill_pool(
            INVENTED_EVIDENCE,
            [_poi(n) for n in INVENTED_SHOWS],
            current_poi_list=[],
            venue_name='Griffin Museum of Photography',
            exists_fn=_exists_none_of_the_invented,
        )
        self.assertEqual(
            [], pool,
            f"fabrication guard let invented titles back in: {[p['name'] for p in pool]}"
        )

    def test_real_work_that_exists_is_still_readmitted(self):
        """The guard must NOT break LOCAL-577: a real work (existence True) that
        D1v2 dropped on a title mismatch is still re-admitted."""
        ev = {'The Adoration of the Magi': {'status': 'DROPPED', 'reason': 'no canonical match'}}
        pool = gtt._title_mismatch_refill_pool(
            ev,
            [_poi('The Adoration of the Magi')],
            current_poi_list=[],
            venue_name='Musée du Palais Lascaris',
            exists_fn=lambda name: True,   # this work genuinely exists
        )
        self.assertEqual(['The Adoration of the Magi'], [p['name'] for p in pool])
        self.assertIs(pool[0].get('verified'), False)
        self.assertTrue(pool[0].get('_title_mismatch_refill'))

    def test_inconclusive_existence_does_not_block(self):
        """D162: a search that didn't really run is not evidence of absence.
        exists_fn returning None must NOT disqualify a title-mismatch drop."""
        ev = {'The Adoration of the Magi': {'status': 'DROPPED', 'reason': 'no canonical match'}}
        pool = gtt._title_mismatch_refill_pool(
            ev,
            [_poi('The Adoration of the Magi')],
            current_poi_list=[],
            venue_name='Musée du Palais Lascaris',
            exists_fn=lambda name: None,   # inconclusive
        )
        self.assertEqual(['The Adoration of the Magi'], [p['name'] for p in pool],
                         "inconclusive existence must not block a real refill (D162)")

    def test_mixed_only_the_existing_survives(self):
        """Four invented (absent) + one real (exists) → only the real one back."""
        ev = dict(INVENTED_EVIDENCE)
        ev['The Adoration of the Magi'] = {'status': 'DROPPED', 'reason': 'no canonical match'}
        cands = [_poi(n) for n in INVENTED_SHOWS] + [_poi('The Adoration of the Magi')]

        def _exists(name):
            return name == 'The Adoration of the Magi'

        pool = gtt._title_mismatch_refill_pool(
            ev, cands, current_poi_list=[],
            venue_name='Mixed Venue', exists_fn=_exists,
        )
        self.assertEqual(['The Adoration of the Magi'], [p['name'] for p in pool])

    def test_guard_inert_without_exists_fn_preserves_local577(self):
        """Legacy callers (no exists_fn) keep LOCAL-577 behaviour exactly."""
        ev = {'The Adoration of the Magi': {'status': 'DROPPED', 'reason': 'no canonical match'}}
        pool = gtt._title_mismatch_refill_pool(
            ev, [_poi('The Adoration of the Magi')], current_poi_list=[],
            venue_name='Musée du Palais Lascaris',   # no exists_fn
        )
        self.assertEqual(['The Adoration of the Magi'], [p['name'] for p in pool])


if __name__ == '__main__':
    unittest.main(verbosity=2)
