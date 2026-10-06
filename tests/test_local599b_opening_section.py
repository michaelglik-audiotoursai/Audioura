"""test_local599b_opening_section.py — LOCAL-599B r2 (D611 opening section).

Michael, D611: a museum tour's Stop 1 must OPEN with the museum's own story + the
visiting facts (address, hours with days, admission). For MassArt — which has NO
Wikidata entity — r1's Stop 1 had none of that: resolve_venue() returned None, so
stop_pool_orchestrator._build_opening_section had no site URL and produced nothing.

These tests lock the r2 fix:
  1. _build_opening_section reuses the LOCAL-599 Wikidata-independent official-site
     discovery when resolve_venue returns None, reaches maam.massart.edu's own
     /visit and /about pages, and folds the opening section.
  2. The folded section states the venue hours WITH DAYS and the free admission —
     from the venue's own compact "12 – 8p" / "Always free" page text — never
     invented.
  3. _resolve_venue_address lifts the venue's real street address (621 Huntington
     Avenue) via the same discovery.

All OFFLINE: venue_resolver.resolve_venue is stubbed to None (no Wikidata entity),
discover_official_site is stubbed to the MAAM site, and every fetch is served from
the saved MAAM fixtures.

Run: python3 -m pytest tests/test_local599b_opening_section.py -q
"""
import os
import unittest

import about_museum_stop as am
import stop_pool_orchestrator as orch
import venue_resolver
from venue_resolver import SiteDiscovery

_FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'maam')


def _read(name):
    with open(os.path.join(_FIX, name), encoding='utf-8') as fh:
        return fh.read()


def _page_for(url):
    u = url.lower()
    if 'visit' in u:
        return _read('visit.html')
    if 'about' in u:
        return _read('about.html')
    if url.rstrip('/') == 'https://maam.massart.edu':
        return _read('home.html')
    return ''


class TestOpeningSectionNoWikidata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._prev_pool = os.environ.get('DISABLE_STOP_POOL')
        os.environ['DISABLE_STOP_POOL'] = '1'
        cls._prev_resolve = venue_resolver.resolve_venue
        cls._prev_disc = venue_resolver.discover_official_site
        cls._prev_fetch = am._default_fetcher
        cls._prev_wiki = am.default_wiki_provider
        # No Wikidata entity for MassArt.
        venue_resolver.resolve_venue = lambda *a, **k: None
        # Discovery finds the MAAM site (as LOCAL-599 does live).
        venue_resolver.discover_official_site = lambda vs, city="", **k: SiteDiscovery(
            official_url='https://maam.massart.edu/', source='web_search',
            language='en')
        am._default_fetcher = lambda url: (_page_for(url), [])
        am.default_wiki_provider = lambda name: None  # offline

    @classmethod
    def tearDownClass(cls):
        venue_resolver.resolve_venue = cls._prev_resolve
        venue_resolver.discover_official_site = cls._prev_disc
        am._default_fetcher = cls._prev_fetch
        am.default_wiki_provider = cls._prev_wiki
        if cls._prev_pool is None:
            os.environ.pop('DISABLE_STOP_POOL', None)
        else:
            os.environ['DISABLE_STOP_POOL'] = cls._prev_pool

    def test_opening_section_is_built_for_no_wikidata_venue(self):
        section = orch._build_opening_section(
            'MassArt Art Museum, Boston, MA', 'museum',
            request_text='MassArt Art Museum, Boston, MA',
            available_exhibition_stops=7, requested_stops=7)
        self.assertTrue(section and section.strip(),
                        "no opening section for a no-Wikidata venue")

    def test_opening_section_has_hours_with_days(self):
        section = orch._build_opening_section(
            'MassArt Art Museum, Boston, MA', 'museum',
            request_text='MassArt Art Museum, Boston, MA',
            available_exhibition_stops=7, requested_stops=7)
        # Hours bound to days (D611 / LOCAL-592 r4) — from the venue's own page.
        self.assertRegex(section, r'(?i)Thursday')
        self.assertRegex(section, r'(?i)\d\s*PM')

    def test_opening_section_states_free_admission(self):
        section = orch._build_opening_section(
            'MassArt Art Museum, Boston, MA', 'museum',
            request_text='MassArt Art Museum, Boston, MA',
            available_exhibition_stops=7, requested_stops=7)
        self.assertRegex(section, r'(?i)\bfree\b')

    def test_practical_facts_are_sourced_not_invented(self):
        facts = orch._source_practical_facts(
            'MassArt Art Museum', 'https://maam.massart.edu/',
            '621 Huntington Avenue, Boston, MA 02115',
            fetcher=lambda u: (_page_for(u), []))
        self.assertIn('PM', facts)       # day-bound hours
        self.assertRegex(facts, r'(?i)free')
        # The page states 12–8p Thursday; a fabricated 9 AM must never appear.
        self.assertNotIn('9 AM', facts)

    def test_venue_address_is_the_building(self):
        addr = orch._resolve_venue_address('MassArt Art Museum, Boston, MA')
        self.assertIn('621 Huntington', addr)


if __name__ == '__main__':
    unittest.main()
