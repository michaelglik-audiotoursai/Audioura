#!/usr/bin/env python3
"""test_local600_order_and_shortfall.py — LOCAL-600 (D616).

Two listener-facing defects from the LOCAL-599 r3 MassArt live run:

  1. ORDER. The gate chain reordered the site-first POIs by KIND, so the two WORK
     stops led and their SHOWS came after — Stop 1 was "Robert Lazzarini: American
     flag" while its show "Robert Lazzarini" was Stop 3, two stops later. Stop 1's
     orientation then said "Your first stop is Robert Lazzarini", not matching the
     delivered title.
  2. A SILENT SHORTFALL. The listener asked for 7 stops and got 5 with no word of
     explanation.

The fix (D616):
  * generate_tour_text._regroup_site_first_stops re-groups the delivered site-first
    stops so each exhibition stop leads its own works, preserving the route/story
    order BETWEEN shows. Stop 1 is therefore always a show, and the orientation
    (built from poi_list[0]) names that show.
  * about_museum_stop.build_shortfall_sentence builds one honest sentence from the
    real counts (exhibitions on view, delivered stops, requested) — present when
    delivered < requested, absent when the ask is met (D611 exact N).

These tests exercise:
  - grouping order on a fixture with 3 shows and 2 works (MAAM);
  - the shortfall sentence present at 5/7 and absent at 7/7;
  - Griffin, which reaches N with shows alone, is UNCHANGED (regroup is a no-op and
    no shortfall sentence is emitted).

All OFFLINE. Run: python3 -m pytest tests/test_local600_order_and_shortfall.py -q
"""
import os
import unittest

from about_museum_stop import build_shortfall_sentence, build_opening_section, AboutStop
from exhibition_site_first import build_site_first_candidates
from generate_tour_text import _regroup_site_first_stops

# Reuse the MAAM fixture fetcher + date from the 599B suite.
from tests.test_local599b_maam_exhibitions import _fetcher, TODAY


def _poi(name, kind, group_key, order, status='on_view'):
    """A minimal site-first POI as generate_tour_text tags it."""
    return {
        'name': name, 'source': 'site_exhibition',
        '_sf_kind': kind, '_sf_status': status,
        '_sf_group_key': group_key, '_sf_order': order,
    }


class TestGroupingOrder(unittest.TestCase):
    """D616 deliverable 1: each exhibition's stop first, then its works."""

    def test_regroup_fixes_r3_works_first_defect(self):
        # The exact r3 delivered order: two WORK stops first, three SHOWS after.
        pois = [
            _poi('Robert Lazzarini: American flag', 'work', 'u/robert', 2),
            _poi('Baseera Khan: Second Skin, Half Column 3', 'work', 'u/baseera', 4),
            _poi('Robert Lazzarini', 'exhibition', 'u/robert', 1),
            _poi('Banu Cennetoğlu', 'exhibition', 'u/banu', 0),
            _poi('Baseera Khan', 'exhibition', 'u/baseera', 3),
        ]
        out = [p['name'] for p in _regroup_site_first_stops(pois)]
        # Each show leads its own works; inter-show order (by _sf_order) preserved:
        # Banu(0) -> Robert(1) -> Baseera(3).
        self.assertEqual(out, [
            'Banu Cennetoğlu',
            'Robert Lazzarini',
            'Robert Lazzarini: American flag',
            'Baseera Khan',
            'Baseera Khan: Second Skin, Half Column 3',
        ])

    def test_stop1_is_a_show_not_a_work(self):
        pois = [
            _poi('Robert Lazzarini: American flag', 'work', 'u/robert', 2),
            _poi('Robert Lazzarini', 'exhibition', 'u/robert', 1),
        ]
        out = _regroup_site_first_stops(pois)
        self.assertEqual(out[0]['_sf_kind'], 'exhibition')
        self.assertEqual(out[0]['name'], 'Robert Lazzarini')
        # The work immediately follows its show.
        self.assertEqual(out[1]['name'], 'Robert Lazzarini: American flag')

    def test_work_immediately_follows_its_own_show(self):
        # Interleave two shows+works; each work must sit right after ITS show,
        # never after a different show.
        pois = [
            _poi('A: w1', 'work', 'u/a', 1),
            _poi('B: w1', 'work', 'u/b', 3),
            _poi('A', 'exhibition', 'u/a', 0),
            _poi('B', 'exhibition', 'u/b', 2),
        ]
        out = [p['name'] for p in _regroup_site_first_stops(pois)]
        self.assertEqual(out, ['A', 'A: w1', 'B', 'B: w1'])

    def test_regroup_on_real_maam_fixture_three_shows_two_works(self):
        # The real MAAM fixtures: 3 on-view shows, 2 of them split into one named
        # work each (Banu's detail page names no work). Simulate a gate chain that
        # hoisted works to the front, then regroup and assert show-leads-works.
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher, today=TODAY)
        self.assertEqual(len(cands), 5)  # 3 shows + 2 works
        tagged = [
            {'name': c['name'], 'source': 'site_exhibition',
             '_sf_kind': c['kind'], '_sf_status': c['status'],
             '_sf_group_key': (c.get('detail_url') or '').strip(), '_sf_order': i}
            for i, c in enumerate(cands)
        ]
        works = [p for p in tagged if p['_sf_kind'] == 'work']
        shows = [p for p in tagged if p['_sf_kind'] != 'work']
        scrambled = works + shows  # the r3 failure shape
        out = _regroup_site_first_stops(scrambled)
        names = [p['name'] for p in out]
        for p in out:
            if p['_sf_kind'] == 'work':
                idx = names.index(p['name'])
                prev = out[idx - 1]
                self.assertEqual(prev['_sf_group_key'], p['_sf_group_key'],
                                 f"work {p['name']} not placed after its own show")
        self.assertEqual(out[0]['_sf_kind'], 'exhibition')  # Stop 1 is a show
        self.assertEqual(len(out), len(scrambled))          # nothing dropped/dup'd


class TestRegroupSafety(unittest.TestCase):
    def test_non_site_first_list_is_untouched(self):
        pois = [
            {'name': 'X', 'source': 'catalogue', '_sf_kind': 'work',
             '_sf_group_key': 'u', '_sf_order': 0},
            {'name': 'Y', 'source': 'site_exhibition', '_sf_kind': 'exhibition',
             '_sf_group_key': 'u', '_sf_order': 1},
        ]
        self.assertEqual([p['name'] for p in _regroup_site_first_stops(pois)],
                         ['X', 'Y'])

    def test_empty_list(self):
        self.assertEqual(_regroup_site_first_stops([]), [])

    def test_museum_space_keeps_position(self):
        pois = [
            _poi('Show A', 'exhibition', 'u/a', 0),
            _poi('Lobby', 'museum_space', '', 1, status='space'),
            _poi('A: work', 'work', 'u/a', 2),
        ]
        out = [p['name'] for p in _regroup_site_first_stops(pois)]
        # The work rejoins its show; the space keeps its own position by order.
        self.assertEqual(out, ['Show A', 'A: work', 'Lobby'])


class TestShortfallSentence(unittest.TestCase):
    """D616 deliverable 2: one honest sentence, from the real counts."""

    def test_present_at_five_of_seven(self):
        s = build_shortfall_sentence('MassArt Art Museum, Boston, MA', 3, 5, 7)
        self.assertEqual(
            s,
            'MassArt Art Museum currently has 3 exhibitions on view, so this tour '
            'has 5 stops rather than the 7 you asked for.')

    def test_absent_at_seven_of_seven(self):
        self.assertEqual(build_shortfall_sentence('MassArt Art Museum', 3, 7, 7), '')

    def test_absent_when_over_delivered(self):
        self.assertEqual(build_shortfall_sentence('X Museum', 9, 8, 7), '')

    def test_absent_with_bad_counts(self):
        self.assertEqual(build_shortfall_sentence('X', 3, 0, 7), '')
        self.assertEqual(build_shortfall_sentence('X', 3, 5, 0), '')
        self.assertEqual(build_shortfall_sentence('X', 3, 5, None), '')

    def test_singular_grammar(self):
        self.assertEqual(
            build_shortfall_sentence('Tiny Gallery', 1, 1, 3),
            'Tiny Gallery currently has 1 exhibition on view, so this tour has '
            '1 stop rather than the 3 you asked for.')

    def test_folded_into_opening_section_after_about(self):
        about = AboutStop(
            museum_name='MassArt Art Museum',
            narration="The MassArt Art Museum is Boston's only free contemporary art museum.",
            practical_facts='', site_domain='maam.massart.edu', as_of='October 2026')
        sentence = build_shortfall_sentence('MassArt Art Museum', 3, 5, 7)
        section = build_opening_section(about, shortfall_sentence=sentence)
        self.assertIn(sentence, section)
        # The shortfall note comes AFTER the About story.
        self.assertLess(section.index('only free contemporary'),
                        section.index('currently has 3 exhibitions'))

    def test_opening_section_omits_sentence_when_none(self):
        about = AboutStop(
            museum_name='MassArt Art Museum',
            narration="The MassArt Art Museum is Boston's only free contemporary art museum.",
            practical_facts='', site_domain='maam.massart.edu', as_of='October 2026')
        section = build_opening_section(about, shortfall_sentence='')
        self.assertNotIn('rather than', section)


class TestGriffinUnchanged(unittest.TestCase):
    """Griffin reaches N with shows alone — no works split, delivered == requested.
    The regroup is a no-op and NO shortfall sentence is emitted."""

    def test_regroup_noop_when_all_shows_in_order(self):
        pois = [_poi(f'Show {i}', 'exhibition', f'u/{i}', i) for i in range(5)]
        before = [p['name'] for p in pois]
        after = [p['name'] for p in _regroup_site_first_stops(pois)]
        self.assertEqual(before, after)

    def test_no_shortfall_when_shows_reach_n(self):
        self.assertEqual(build_shortfall_sentence('Griffin Museum of Photography',
                                                  5, 5, 5), '')

    def test_no_shortfall_when_more_shows_than_asked(self):
        self.assertEqual(build_shortfall_sentence('Griffin Museum of Photography',
                                                  7, 5, 5), '')


class TestWiring(unittest.TestCase):
    """Prove the fix is wired into the engine and the orchestrator, not only the
    pure helpers mirrored here."""

    @classmethod
    def setUpClass(cls):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(here, 'generate_tour_text.py'), encoding='utf-8') as fh:
            cls.gen = fh.read()
        with open(os.path.join(here, 'stop_pool_orchestrator.py'), encoding='utf-8') as fh:
            cls.orch = fh.read()

    def test_regroup_called_in_engine(self):
        self.assertIn('_regroup_site_first_stops(poi_list)', self.gen)

    def test_counts_recorded_in_engine(self):
        self.assertIn('_LAST_SITE_FIRST_COUNTS', self.gen)
        self.assertIn("'exhibitions_on_view'", self.gen)

    def test_shortfall_wired_in_orchestrator(self):
        self.assertIn('build_shortfall_sentence', self.orch)
        self.assertIn('shortfall_sentence=', self.orch)


if __name__ == '__main__':
    unittest.main(verbosity=2)
