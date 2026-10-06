"""test_local599b_maam_exhibitions.py — LOCAL-599B r2.

MassArt Art Museum (maam.massart.edu) delivered 1/7 stops in r1, and that one
stop ("Make with MAAM") was a hands-on PROGRAM, not an exhibition — while the
site's own /exhibitions index publishes the real shows. These tests lock the r2
fix against fixtures of the REAL MAAM pages (saved under tests/fixtures/maam/):

  1. extract_classified_exhibitions reads the /exhibitions index as 3 on-view +
     3 past, with CLEAN titles (no "On View"/"Past" suffix bleed) and the correct
     /exhibition/<slug> detail URLs.
  2. The homepage's "Make with MAAM" (/event/make-maam-222) is a program, NOT an
     exhibition — it is EXCLUDED by the exhibition-museum path policy.
  3. discover_classified_exhibitions reaches the /exhibitions index (not the home
     page) and never returns the program.
  4. build_site_first_candidates fills to N current-first (current exhibitions,
     then past), supplements past shows from /exhibitions/past, carries a source
     URL per stop, and reaches 7 real exhibitions.
  5. The honest shortfall: when fewer than N are reachable, the list is shorter —
     never padded with a program or an invented title.

All OFFLINE: a fixture-backed fetcher maps each MAAM URL to its saved HTML.

Run: python3 -m pytest tests/test_local599b_maam_exhibitions.py -q
"""
import datetime
import os
import unittest

from exhibition_discovery import (extract_classified_exhibitions,
                                   extract_current_exhibitions,
                                   classify_exhibition_status)
from exhibition_site_first import (discover_classified_exhibitions,
                                   build_site_first_candidates,
                                   _is_exhibition_detail)

_FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'maam')

# A date inside the On View range (Sep 30 2026 – Feb 28 2027) so the current
# shows classify as on_view deterministically.
TODAY = datetime.date(2026, 11, 15)

_URL_TO_FILE = {
    'https://maam.massart.edu/': 'home.html',
    'https://maam.massart.edu': 'home.html',
    'https://maam.massart.edu/exhibitions': 'exhibitions.html',
    'https://maam.massart.edu/exhibitions/past': 'exhibitions_past.html',
    'https://maam.massart.edu/exhibition/banu-cennetoglu': 'ex_banu.html',
    'https://maam.massart.edu/exhibition/baseera-khan': 'ex_baseera.html',
    'https://maam.massart.edu/exhibition/robert-lazzarini': 'ex_robert.html',
    'https://maam.massart.edu/visit': 'visit.html',
    'https://maam.massart.edu/about': 'about.html',
}


def _read(name):
    with open(os.path.join(_FIX, name), encoding='utf-8') as fh:
        return fh.read()


def _fetcher(url, timeout=15):
    key = url if url in _URL_TO_FILE else url.rstrip('/')
    fn = _URL_TO_FILE.get(key) or _URL_TO_FILE.get(url.rstrip('/'))
    if not fn:
        return '', [], {'status': 404, 'error': '', 'bytes': 0, 'seconds': 0.0}
    html = _read(fn)
    return html, [], {'status': 200, 'error': '', 'bytes': len(html), 'seconds': 0.0}


class TestMaamExtraction(unittest.TestCase):
    def test_index_classifies_three_current_three_past(self):
        res = extract_classified_exhibitions(
            _read('exhibitions.html'), 'https://maam.massart.edu/exhibitions',
            today=TODAY)
        on_view = {e['title'] for e in res if e['status'] == 'on_view'}
        past = {e['title'] for e in res if e['status'] == 'past'}
        self.assertEqual(on_view,
                         {'Banu Cennetoğlu', 'Robert Lazzarini', 'Baseera Khan'})
        self.assertEqual(past,
                         {'Masako Miki', 'Press & Pull', "Freedom Baird M'16"})

    def test_titles_are_debleeded(self):
        # The past-section template renders "<h3><a>Masako Miki</a> Past</h3>".
        # The status suffix must never bleed into the title.
        titles = {e['title'] for e in extract_current_exhibitions(
            _read('exhibitions.html'), 'https://maam.massart.edu/exhibitions')}
        self.assertIn('Masako Miki', titles)
        self.assertNotIn('Masako Miki Past', titles)
        for t in titles:
            self.assertNotIn('On View', t)
            self.assertFalse(t.endswith('Past'))

    def test_detail_urls_are_exhibition_slugs(self):
        for e in extract_classified_exhibitions(
                _read('exhibitions.html'),
                'https://maam.massart.edu/exhibitions', today=TODAY):
            self.assertIn('/exhibition/', e['detail_url'])

    def test_program_is_not_an_exhibition(self):
        # The homepage's "Make with MAAM" links /event/make-maam-222 — a program.
        self.assertFalse(_is_exhibition_detail(
            'https://maam.massart.edu/event/make-maam-222'))
        self.assertTrue(_is_exhibition_detail(
            'https://maam.massart.edu/exhibition/banu-cennetoglu'))


class TestMaamDiscovery(unittest.TestCase):
    def test_discovery_prefers_index_over_homepage_and_excludes_program(self):
        diag = {}
        shows, listing = discover_classified_exhibitions(
            'https://maam.massart.edu/', fetcher=_fetcher, diagnostics=diag,
            today=TODAY)
        # Reached the /exhibitions index, not the home page.
        self.assertTrue(listing.endswith('/exhibitions'))
        # Program never appears.
        self.assertFalse(any('/event/' in e['detail_url'] for e in shows))
        self.assertFalse(any('make with maam' in e['title'].lower() for e in shows))
        # On-view shows come first.
        statuses = [e['status'] for e in shows]
        self.assertEqual(statuses[:3], ['on_view', 'on_view', 'on_view'])

    def test_r1_bug_homepage_event_no_longer_wins(self):
        # r1 returned ONLY "Make with MAAM" because the home page was tried first
        # and short-circuited. Now the real shows are found and the program is out.
        shows, _ = discover_classified_exhibitions(
            'https://maam.massart.edu/', fetcher=_fetcher, today=TODAY)
        self.assertGreaterEqual(len(shows), 6)


class TestMaamFillToN(unittest.TestCase):
    def test_fills_to_seven_current_first_with_source_urls(self):
        diag = {}
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            diagnostics=diag, today=TODAY)
        self.assertGreaterEqual(len(cands), 7)
        first7 = cands[:7]
        # First three are the current on-view exhibitions.
        self.assertEqual([c['status'] for c in first7[:3]],
                         ['on_view', 'on_view', 'on_view'])
        # Every delivered stop carries a source URL and is an exhibition detail
        # page (no program/event).
        for c in first7:
            self.assertTrue(c['source_url'])
            self.assertNotIn('/event/', c['source_url'])
        # No invented title, no program.
        names = {c['name'].lower() for c in cands}
        self.assertNotIn('make with maam', names)

    def test_past_supplemented_from_archive(self):
        # The main index lists 3 past; /exhibitions/past carries the full archive
        # (9). Fill reaches past shows beyond the index's three.
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            today=TODAY)
        past_names = {c['name'] for c in cands if c['status'] == 'past'}
        self.assertIn('GENERATIONS', past_names)  # from /exhibitions/past only

    def test_no_invention_when_short(self):
        # Asking for far more than exist yields only the real shows — never padded.
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=50, fetcher=_fetcher,
            today=TODAY)
        # 3 current + 9 archived past = 12 real exhibitions; nothing invented.
        self.assertLessEqual(len(cands), 12)
        for c in cands:
            self.assertIn('/exhibition/', c['source_url'])


if __name__ == '__main__':
    unittest.main()
