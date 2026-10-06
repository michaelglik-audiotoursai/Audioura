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
                                   classify_exhibition_status,
                                   extract_exhibition_works)
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
    def test_no_past_show_is_ever_selected(self):
        # [LOCAL-599C] r3: the exhibition list holds BOTH on-view and past shows
        # (3 + 3 on the index). A listener standing in the museum must never be
        # sent to a show that is off the walls — no past show may be a stop.
        diag = {}
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            diagnostics=diag, today=TODAY)
        self.assertTrue(cands)
        for c in cands:
            self.assertNotEqual(c['status'], 'past',
                                f"a PAST show leaked in as a stop: {c['name']}")
        self.assertEqual(diag['status_counts']['past'], 0)
        # None of the known MAAM past shows may appear as a stop.
        names = {c['name'].lower() for c in cands}
        for past in ('masako miki', 'press & pull', "freedom baird m'16",
                     'generations'):
            self.assertNotIn(past, names)

    def test_current_shows_split_into_works(self):
        # [LOCAL-599C] Each on-view show is split into the works/rooms its own
        # detail page names: the show (artist + named title) as the primary stop,
        # then specific named works ("Robert Lazzarini: American flag").
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            today=TODAY)
        kinds = {c['kind'] for c in cands}
        self.assertIn('exhibition', kinds)
        self.assertIn('work', kinds, "no per-work stop was produced")
        names = {c['name'] for c in cands}
        # The three current shows are present as primary (artist) stops.
        self.assertIn('Robert Lazzarini', names)
        self.assertIn('Banu Cennetoğlu', names)
        self.assertIn('Baseera Khan', names)
        # And at least one specific named work, credited "Artist: Work".
        work_names = {c['name'] for c in cands if c['kind'] == 'work'}
        self.assertTrue(any('American flag' in w for w in work_names),
                        f"expected a named work split from a show; got {work_names}")
        for w in work_names:
            self.assertIn(':', w)  # "Artist: Work"

    def test_every_stop_is_on_view_with_source_url(self):
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            today=TODAY)
        for c in cands:
            self.assertEqual(c['status'], 'on_view')
            self.assertTrue(c['source_url'])
            self.assertIn('/exhibition/', c['source_url'])  # a real detail page
            self.assertNotIn('/event/', c['source_url'])    # never the program

    def test_honest_shortfall_not_padded_with_past(self):
        # [LOCAL-599C] On-view material (3 shows + 2 named works) honestly reaches
        # 5, short of 7. The list is simply shorter — never padded to 7 with past
        # shows (the r2 behaviour, withdrawn). Don't pad (D611).
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=7, fetcher=_fetcher,
            today=TODAY)
        self.assertLess(len(cands), 7)        # honest shortfall, not padded
        self.assertGreaterEqual(len(cands), 4)  # the real on-view material
        self.assertTrue(all(c['status'] != 'past' for c in cands))

    def test_no_invention_when_short(self):
        # Asking for far more than exist yields only the real ON-VIEW shows/works —
        # never padded, never a past show, never an invented title.
        cands = build_site_first_candidates(
            'https://maam.massart.edu/', total_stops=50, fetcher=_fetcher,
            today=TODAY)
        names = {c['name'].lower() for c in cands}
        self.assertNotIn('make with maam', names)
        for c in cands:
            self.assertIn('/exhibition/', c['source_url'])
            self.assertNotEqual(c['status'], 'past')


class TestExhibitionWorks(unittest.TestCase):
    """[LOCAL-599C] extract_exhibition_works splits ONE show's detail page into
    its own named title + the specific NAMED WORKS it credits."""

    def test_robert_lazzarini_yields_title_and_work(self):
        works = extract_exhibition_works(
            _read('ex_robert.html'), artist='Robert Lazzarini')
        kinds = [(w['kind'], w['name']) for w in works]
        # The show's own named title ("metes and bounds") first.
        self.assertIn(('exhibition_title', 'metes and bounds'), kinds)
        # A specific named work credited "Robert Lazzarini. American flag , 2022."
        work_names = [w['name'] for w in works if w['kind'] == 'work']
        self.assertIn('American flag', work_names)

    def test_caption_prefix_detail_of_is_stripped(self):
        # "Baseera Khan. Detail of Second Skin, Half Column 3 , 2022." → the work
        # is "Second Skin, Half Column 3" (the "Detail of" caption prefix dropped).
        works = extract_exhibition_works(
            _read('ex_baseera.html'), artist='Baseera Khan')
        work_names = [w['name'] for w in works if w['kind'] == 'work']
        self.assertIn('Second Skin, Half Column 3', work_names)
        for n in work_names:
            self.assertFalse(n.lower().startswith('detail of'))

    def test_provenance_lines_are_not_works(self):
        # Installation-view / photo-credit / collection lines are furniture, not
        # a work a visitor can stand in front of.
        for fn in ('ex_robert.html', 'ex_banu.html', 'ex_baseera.html'):
            for w in extract_exhibition_works(_read(fn)):
                low = w['name'].lower()
                self.assertNotIn('installation view', low)
                self.assertNotIn('photo', low)
                self.assertNotIn('collection', low)


if __name__ == '__main__':
    unittest.main()
