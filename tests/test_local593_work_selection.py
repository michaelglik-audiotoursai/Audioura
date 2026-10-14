#!/usr/bin/env python3
"""test_local593_work_selection.py — Deliverable 4 (LOCAL-593).

The Harvard tour's 7 stops were the first 7 works ALPHABETICALLY — A Courtier,
Autumn Landscape, Autumn Sunset, A Sea-Spell, Album Leaf, Amusements, Annual
Events — the museum's obscure holdings, not its highlights. That order came from
the collection source: the deterministic selector sorted by source tier only,
so within a tier the order fell back to insertion/alphabetical.

The fix ranks documented works by PROMINENCE (Wikidata sitelinks + corpus/
Wikipedia mention count + on-site highlight flag), using alphabetical order ONLY
to break ties.

This test proves:
  * the OLD order is alphabetical (reproduced from the baseline sort key);
  * the NEW order is prominence-first (a high-sitelinks work beats an
    alphabetically-earlier obscure one);
  * alphabetical is still the tie-break when prominence is equal.

Run: python3 -m pytest tests/test_local593_work_selection.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt


# A representative Harvard documented-work set: the obscure alphabetically-early
# works LEAD saw, plus genuine highlights that carry Wikidata sitelinks.
# (sitelinks are illustrative but realistic: well-known works have many Wikipedia
# language editions, obscure scrolls have none.)
HARVARD_WORKS = [
    {'title': 'A Courtier', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'A Sea-Spell', 'source': 'sparql', 'sitelinks': 3},
    {'title': 'Album Leaf', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'Amusements', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'Annual Events', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'Autumn Landscape', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'Autumn Sunset', 'source': 'sparql', 'sitelinks': 0},
    {'title': 'Self-Portrait Dedicated to Paul Gauguin', 'source': 'sparql', 'sitelinks': 18},
    {'title': 'The Lamentation', 'source': 'sparql', 'sitelinks': 7},
    {'title': 'Mother and Child', 'source': 'sparql', 'sitelinks': 12},
    {'title': 'Three Dancers', 'source': 'sparql', 'sitelinks': 9},
]


def _baseline_order(works):
    """The OLD deterministic key: source tier only, stable → alphabetical within
    a tier (because the list is iterated in alphabetical order here)."""
    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
    xs = sorted(works, key=lambda d: d['title'].lower())  # how they entered
    xs.sort(key=lambda d: _priority.get(d['source'], 9))  # old sort, stable
    return [d['title'] for d in xs]


def _new_order(works, corpus=""):
    """The NEW key used in generate_tour_text: (source, -prominence, title)."""
    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
    xs = sorted(works, key=lambda d: d['title'].lower())
    xs.sort(key=lambda d: (
        _priority.get(d['source'], 9),
        -gtt._work_prominence_score(d, corpus),
        d['title'].lower(),
    ))
    return [d['title'] for d in xs]


class TestWorkSelection(unittest.TestCase):
    def test_old_order_is_alphabetical(self):
        """Prove the complained-of alphabetical order came from the source."""
        before = _baseline_order(HARVARD_WORKS)[:7]
        self.assertEqual(
            ['A Courtier', 'A Sea-Spell', 'Album Leaf', 'Amusements',
             'Annual Events', 'Autumn Landscape', 'Autumn Sunset'],
            before,
            "baseline order must be the first 7 ALPHABETICALLY")

    def test_new_order_is_prominence_first(self):
        """The new order leads with the high-sitelinks highlights, not the
        alphabetically-earliest obscure works."""
        after = _new_order(HARVARD_WORKS)[:7]
        # The three most prominent (18, 12, 9 sitelinks) must be at the front.
        self.assertEqual('Self-Portrait Dedicated to Paul Gauguin', after[0])
        self.assertEqual('Mother and Child', after[1])
        self.assertEqual('Three Dancers', after[2])
        # At least one obscure alphabetical-early work must have been displaced
        # out of the top 7's leading positions.
        self.assertNotEqual('A Courtier', after[0])

    def test_prominence_scorer_uses_sitelinks(self):
        hi = {'title': 'Famous', 'source': 'sparql', 'sitelinks': 20}
        lo = {'title': 'Aardvark', 'source': 'sparql', 'sitelinks': 0}
        self.assertGreater(gtt._work_prominence_score(hi),
                           gtt._work_prominence_score(lo))

    def test_prominence_scorer_uses_corpus_mentions(self):
        corpus = ("the lamentation is the museum's signature work. "
                  "the lamentation draws crowds. ")
        mentioned = {'title': 'The Lamentation', 'source': 'sparql', 'sitelinks': 0}
        silent = {'title': 'Album Leaf', 'source': 'sparql', 'sitelinks': 0}
        self.assertGreater(gtt._work_prominence_score(mentioned, corpus),
                           gtt._work_prominence_score(silent, corpus))

    def test_alphabetical_is_only_a_tiebreak(self):
        """Two equal-prominence works keep alphabetical order between them."""
        works = [
            {'title': 'Zephyr', 'source': 'sparql', 'sitelinks': 5},
            {'title': 'Aurora', 'source': 'sparql', 'sitelinks': 5},
        ]
        self.assertEqual(['Aurora', 'Zephyr'], _new_order(works))

    def test_sort_key_wired_into_source(self):
        """The production file must sort by prominence, not source-only."""
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, 'generate_tour_text.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('_work_prominence_score', src)
        # The old source-only sort must be gone.
        self.assertNotIn("_det_documented.sort(key=lambda d: _priority.get(d['source'], 9))", src)

    def test_sparql_fetches_sitelinks(self):
        """venue_resolver's SPARQL must request wikibase:sitelinks."""
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, 'venue_resolver.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('wikibase:sitelinks', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
