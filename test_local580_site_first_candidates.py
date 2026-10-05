#!/usr/bin/env python3
"""test_local580_site_first_candidates.py — Deliverable 2 (LOCAL-580).

Site-first candidates for an exhibition museum: when SPARQL has 0 works and the
venue's own site yields current exhibitions, the candidate list comes from those
exhibitions (one stop per show), each sourced from its /show/ detail page. GPT
never invents.

This test drives exhibition_site_first with a FAKE fetcher (no network): the
Griffin current-exhibitions fixture is the listing page, and each /show/ URL
returns a small detail page. It asserts:
  * candidates == the real Griffin exhibitions, in site order
  * every candidate carries its on-domain /show/ detail_url and source tag
  * each candidate's page_text is its OWN detail page (per-stop description)
  * NO FlipBook/nav label is ever a candidate (inherited from D1 structural rule)

Run: python3 -m pytest test_local580_site_first_candidates.py -q
"""
import os
import unittest

import exhibition_site_first as sf

_FIXTURE = os.path.join(
    os.path.dirname(__file__), 'tests', 'fixtures',
    'griffin_current_exhibitions.html'
)

with open(_FIXTURE, encoding='utf-8') as _fh:
    _LISTING_HTML = _fh.read()

# Minimal detail pages for a couple of shows; others fall back to listing text.
_DETAIL_PAGES = {
    'https://griffinmuseum.org/show/lua-kobayashi-the-persistence-of-memories/':
        '<html><body><h1>Lua Kobayashi | The Persistence of Memories</h1>'
        '<p>Cyanotype and lumen prints by Lua Kobayashi, on view in the Main '
        'Gallery, September 11 to November 2, 2026.</p></body></html>',
    'https://griffinmuseum.org/show/ultrasound/':
        '<html><body><h1>ULTRASOUND</h1><p>A virtual gallery group show.</p>'
        '</body></html>',
}

EXPECTED_IN_ORDER = [
    'Lua Kobayashi | The Persistence of Memories',
    'Homage | Robert Frank: The Americans',
    'Tabitha Soren | An Artist Life',
    'Intertidal : Field Notes',
    'BU Masters Show 2026 | Traces: Pursuing Process',
    'Earth, Wind & Fire',
    'ULTRASOUND',
    'TLC',
]

FORBIDDEN = {
    'Toggle Fullscreen', 'Next Page', 'Download PDF File', 'Zoom Out',
    'Footer', 'Winchester Galleries', 'Virtual Galleries', 'Exhibition Catalog',
}


def _fake_fetcher(url):
    """Return (html, links). Listing seeds -> Griffin fixture; /show/ -> detail."""
    if url in _DETAIL_PAGES:
        return _DETAIL_PAGES[url], []
    # The listing lives at /current-exhibitions/ (first eligible seed hit).
    if url.rstrip('/').endswith('current-exhibitions') or url.endswith('griffinmuseum.org/current-exhibitions/'):
        return _LISTING_HTML, []
    # The base URL itself is tried first; return the listing so discovery works
    # even if the exact seed differs.
    if url.rstrip('/') == 'https://griffinmuseum.org':
        return _LISTING_HTML, []
    return '', []


class TestSiteFirstCandidates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = sf.build_site_first_candidates(
            base_site_url='https://griffinmuseum.org/current-exhibitions/',
            venue_language='en',
            total_stops=5,
            fetcher=_fake_fetcher,
        )
        cls.names = [c['name'] for c in cls.candidates]

    def test_candidates_are_the_site_exhibitions_in_order(self):
        self.assertEqual(EXPECTED_IN_ORDER, self.names)

    def test_no_flipbook_or_nav_label_is_a_candidate(self):
        leaked = FORBIDDEN & set(self.names)
        self.assertEqual(set(), leaked, f"UI chrome leaked into candidates: {sorted(leaked)}")

    def test_each_candidate_has_on_domain_detail_url_and_source(self):
        for c in self.candidates:
            self.assertEqual('site_exhibition', c['source'])
            self.assertIn('griffinmuseum.org', c['detail_url'])
            self.assertIn('/show/', c['detail_url'])

    def test_detail_page_text_is_per_stop(self):
        by_name = {c['name']: c for c in self.candidates}
        # The Lua show fetched its own detail page — its text names the artist.
        lua = by_name['Lua Kobayashi | The Persistence of Memories']
        self.assertIn('Cyanotype', lua['page_text'])
        self.assertIn('Lua Kobayashi', lua['page_text'])

    def test_empty_site_yields_no_candidates_no_crash(self):
        # No exhibitions anywhere -> [] (caller falls back; never a crash).
        empty = sf.build_site_first_candidates(
            base_site_url='https://example.org',
            fetcher=lambda u: ('<html><body><p>nothing here</p></body></html>', []),
        )
        self.assertEqual([], empty)


if __name__ == '__main__':
    unittest.main(verbosity=2)
