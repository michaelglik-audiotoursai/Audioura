#!/usr/bin/env python3
"""test_local627_signature_first.py — LOCAL-627 defect 5.

The Uffizi tour had no Botticelli (Birth of Venus, Primavera), no Leonardo
Annunciation, no Titian Venus of Urbino; the Prado had no Las Meninas, no Goya, no
Bosch Garden of Earthly Delights. Two root causes, both fixed:

  1. INTAKE — fetch_venue_works issued `LIMIT 200` with NO `ORDER BY`, so for a
     large collection Wikidata returned an arbitrary 200 works and the signature
     works could be excluded before ranking ever ran. Now the SPARQL is
     `ORDER BY DESC(?sitelinks)` so the most prominent works are always fetched.
  2. RANKING — the museum deterministic sort LEADS with _prominence_tier (0 for a
     signature work), so a famous work opens the tour even when an obscure work
     has deeper harvested corpus (the LOCAL-626 fix, re-asserted here for both
     venues' real signature works).

Run: python3 -m pytest test_local627_signature_first.py -q
"""
import os
import unittest

import generate_tour_text as gtt
import venue_resolver as vr


def _norm(s):
    return gtt._det_norm(s) if hasattr(gtt, '_det_norm') else s.strip().lower()


def _museum_sort(works, depth_map, corpus=""):
    """The production museum deterministic sort key (quality path):
    tier, -quality, source, -prominence, title."""
    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
    xs = list(works)
    xs.sort(key=lambda d: (
        gtt._prominence_tier(d),
        -depth_map.get(_norm(d['title']), 0),
        _priority.get(d.get('source', 'sparql'), 9),
        -gtt._work_prominence_score(d, corpus),
        d['title'].lower(),
    ))
    return [d['title'] for d in xs]


# Real Uffizi signature works + a well-mined obscure work, with true-ish sitelinks.
UFFIZI_WORKS = [
    {'title': 'The Birth of Venus', 'source': 'sparql', 'sitelinks': 55},
    {'title': 'Primavera', 'source': 'sparql', 'sitelinks': 42},
    {'title': 'Annunciation', 'source': 'sparql', 'sitelinks': 30},
    {'title': 'Venus of Urbino', 'source': 'sparql', 'sitelinks': 25},
    {'title': 'Ognissanti Madonna', 'source': 'sparql', 'sitelinks': 6},
    {'title': 'A Minor Studiolo Panel', 'source': 'sparql', 'sitelinks': 0},
]

# Real Prado signature works + an obscure one.
PRADO_WORKS = [
    {'title': 'Las Meninas', 'source': 'sparql', 'sitelinks': 60},
    {'title': 'The Third of May 1808', 'source': 'sparql', 'sitelinks': 45},
    {'title': 'The Garden of Earthly Delights', 'source': 'sparql', 'sitelinks': 50},
    {'title': 'The Nude Maja', 'source': 'sparql', 'sitelinks': 20},
    {'title': 'An Obscure Court Portrait', 'source': 'sparql', 'sitelinks': 0},
]


class TestSparqlOrdersBySitelinks(unittest.TestCase):
    """INTAKE: the works SPARQL must ORDER BY sitelinks so signature works are
    never cut by LIMIT on a large collection."""

    def test_query_orders_by_sitelinks_desc(self):
        _here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(_here, 'venue_resolver.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('ORDER BY DESC(?sitelinks)', src)


class TestUffiziSignatureFirst(unittest.TestCase):
    def test_famous_three_lead_even_with_deep_obscure_corpus(self):
        # The obscure panel has by far the deepest harvested corpus.
        depth = {_norm('A Minor Studiolo Panel'): 99.0}
        order = _museum_sort(UFFIZI_WORKS, depth)
        self.assertEqual(order[:3],
                         ['The Birth of Venus', 'Primavera', 'Annunciation'])
        self.assertNotIn('A Minor Studiolo Panel', order[:3])


class TestPradoSignatureFirst(unittest.TestCase):
    def test_famous_three_lead(self):
        depth = {_norm('An Obscure Court Portrait'): 99.0}
        order = _museum_sort(PRADO_WORKS, depth)
        # The three highest-sitelink signature works lead (tier 0, sitelink order).
        self.assertEqual(
            order[:3],
            ['Las Meninas', 'The Garden of Earthly Delights', 'The Third of May 1808'])
        self.assertNotIn('An Obscure Court Portrait', order[:3])


class TestProminenceTier(unittest.TestCase):
    def test_signature_is_tier0(self):
        self.assertEqual(0, gtt._prominence_tier({'sitelinks': 55}))
        self.assertEqual(0, gtt._prominence_tier({'sitelinks': 25}))

    def test_obscure_is_tier1(self):
        self.assertEqual(1, gtt._prominence_tier({'sitelinks': 0}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
