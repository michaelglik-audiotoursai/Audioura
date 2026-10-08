#!/usr/bin/env python3
"""test_local626_highlight_first.py — LOCAL-626 item 4.

Tour 485 (The Courtauld Gallery, 3 stops) opened on a maiolica "Footed Bowl with
the Crucifixion" and a minor Cézanne still life, SKIPPING the museum's household
names: Manet's "A Bar at the Folies-Bergère", Renoir's "La loge", Van Gogh's
"Self-Portrait with Bandaged Ear". Highlight-first (LOCAL-593) was supposed to
make the famous works lead.

Root cause: the museum deterministic selector sorted by corpus-depth QUALITY
score first and used Wikidata prominence only as a tie-break. The bowl had more
harvested corpus (an earlier obscure tour mined it) than the famous paintings, so
it led. Fix: lead the sort with a SIGNATURE TIER (_prominence_tier) — a famous
work (sitelinks >= threshold, or on-site highlight) is tier 0 and always opens;
corpus depth only orders works WITHIN a tier.

The sitelink counts below are the REAL values from the live Courtauld catalogue
(Wikidata Q12110695, P195/P276), captured during this ticket:
    A Bar at the Folies-Bergère (Manet) ...... 39
    La loge (Renoir) .......................... 21
    Self-Portrait with Bandaged Ear (Van Gogh)  14
    Mont Sainte-Victoire with Large Pine ...... 9   (the top Cézanne)
    The Card Players (Cézanne) ................ 1
    Footed Bowl with the Crucifixion .......... 0   (the maiolica bowl that led 485)

Run: python3 -m pytest tests/test_local626_highlight_first.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_tour_text as gtt


# Real Courtauld documented works (subset) with their true Wikidata sitelinks.
COURTAULD_WORKS = [
    {'title': 'A Bar at the Folies-Bergère', 'source': 'sparql', 'sitelinks': 39},
    {'title': 'La loge', 'source': 'sparql', 'sitelinks': 21},
    {'title': 'Self-Portrait with Bandaged Ear', 'source': 'sparql', 'sitelinks': 14},
    {'title': 'Mont Sainte-Victoire with Large Pine', 'source': 'sparql', 'sitelinks': 9},
    {'title': 'The Card Players', 'source': 'sparql', 'sitelinks': 1},
    {'title': 'Footed Bowl with the Crucifixion', 'source': 'sparql', 'sitelinks': 0},
]


def _norm(s):
    return gtt._det_norm(s) if hasattr(gtt, '_det_norm') else s.strip().lower()


def _museum_sort(works, depth_map, corpus=""):
    """Reproduce the production museum deterministic sort key EXACTLY as wired in
    generate_tour_text (quality path): tier, -quality, source, -prominence, title."""
    _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
    xs = list(works)
    xs.sort(key=lambda d: (
        gtt._prominence_tier(d),
        -depth_map.get(_norm(d['title']), 0),
        _priority.get(d['source'], 9),
        -gtt._work_prominence_score(d, corpus),
        d['title'].lower(),
    ))
    return [d['title'] for d in xs]


class TestHighlightFirst(unittest.TestCase):
    def test_bowl_corpus_depth_reproduces_485_defect_without_tier(self):
        """Baseline (quality-first, NO tier): the well-mined bowl leads — the
        exact tour-485 ordering the owner flagged."""
        # The bowl has the deepest harvested corpus; the famous paintings have little.
        depth = {
            _norm('Footed Bowl with the Crucifixion'): 95.0,
            _norm('The Card Players'): 10.0,
            _norm('A Bar at the Folies-Bergère'): 5.0,
        }
        _priority = {'catalogue': 0, 'sparql': 1, 'canonical': 2}
        xs = list(COURTAULD_WORKS)
        xs.sort(key=lambda d: (  # OLD key: quality first, no tier
            -depth.get(_norm(d['title']), 0),
            _priority.get(d['source'], 9),
            -gtt._work_prominence_score(d),
            d['title'].lower(),
        ))
        self.assertEqual('Footed Bowl with the Crucifixion', xs[0]['title'],
                         "baseline must reproduce the 485 defect (bowl leads)")

    def test_famous_works_lead_with_tier(self):
        """Fixed key: the three household names lead, in sitelink order, even
        though the bowl has by far the deepest corpus."""
        depth = {
            _norm('Footed Bowl with the Crucifixion'): 95.0,
            _norm('The Card Players'): 10.0,
            _norm('A Bar at the Folies-Bergère'): 5.0,
        }
        order = _museum_sort(COURTAULD_WORKS, depth)
        self.assertEqual('A Bar at the Folies-Bergère', order[0])
        self.assertEqual('La loge', order[1])
        self.assertEqual('Self-Portrait with Bandaged Ear', order[2])
        # The maiolica bowl must NOT be in the opening three stops.
        self.assertNotIn('Footed Bowl with the Crucifixion', order[:3])

    def test_bowl_sorts_last_among_tail(self):
        """The 0-sitelink bowl is the least prominent long-tail work."""
        depth = {}
        order = _museum_sort(COURTAULD_WORKS, depth)
        self.assertEqual('Footed Bowl with the Crucifixion', order[-1])

    def test_prominence_tier_threshold(self):
        """A signature work is tier 0; a long-tail work is tier 1."""
        self.assertEqual(0, gtt._prominence_tier({'sitelinks': 39}))
        self.assertEqual(0, gtt._prominence_tier({'sitelinks': 14}))
        self.assertEqual(1, gtt._prominence_tier({'sitelinks': 1}))
        self.assertEqual(1, gtt._prominence_tier({'sitelinks': 0}))
        # On-site highlight flag promotes a low-sitelink work to tier 0.
        self.assertEqual(0, gtt._prominence_tier({'sitelinks': 0, 'highlight': True}))

    def test_production_sort_leads_with_tier(self):
        """The production file must lead BOTH museum deterministic sorts with the
        signature tier (not corpus-depth quality)."""
        _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(_here, 'generate_tour_text.py'), encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('_prominence_tier', src)
        # The quality-first-without-tier key must be gone.
        self.assertNotIn(
            "_det_documented.sort(key=lambda d: (\n"
            "                        -_depth_map.get(_det_norm(d['title']), 0),",
            src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
