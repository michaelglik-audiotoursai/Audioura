#!/usr/bin/env python3
"""test_local602_r3_exhibit_allowlist.py — LOCAL-602 r3 (allow-list).

r2 shipped a BLOCK-list: a page became a stop unless a path segment was on
NON_STOP_SEGMENTS. A block-list can only reject the junk it has already seen, so
the Meow Wolf Santa Fe LIVE run (r2) delivered two pages whose junk words were
simply not on the list:

    Stop 1: Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out
            https://meowwolf.com/adulti-verse/santa-fe          (an event)
    Stop 2: Santa Fe City Guide: Top Attractions & Restaurants Near …
            https://meowwolf.com/destinations/santa-fe-city-guide   (a blog/guide)

r3 inverts the rule into an ALLOW-LIST: a page becomes a stop ONLY when it is
POSITIVELY identified as an exhibit / installation / room / work — by its URL
path segment, its JSON-LD @type, or an exhibit-list heading. These tests use the
exact Meow Wolf r2 candidates as fixtures: the two junk pages are dropped because
they match NO positive signal, and real exhibits (by URL segment or by JSON-LD
type) survive.

Run: python3 -m pytest tests/test_local602_r3_exhibit_allowlist.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_site_js as js


# ── the exact two pages the Meow Wolf r2 LIVE run shipped as stops ────────────
MEOW_WOLF_JUNK = [
    {'title': 'Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out',
     'detail_url': 'https://meowwolf.com/adulti-verse/santa-fe',
     'source_url': 'https://meowwolf.com/adulti-verse/santa-fe',
     'source': 'serper'},
    {'title': 'Santa Fe City Guide: Top Attractions & Restaurants Near …',
     'detail_url': 'https://meowwolf.com/destinations/santa-fe-city-guide',
     'source_url': 'https://meowwolf.com/destinations/santa-fe-city-guide',
     'source': 'serper'},
]

# Real Meow Wolf Santa Fe exhibits — positively identified by URL path segment
# (/exhibitions/, /installations/) or by JSON-LD @type.
MEOW_WOLF_REAL = [
    {'title': 'House of Eternal Return',
     'detail_url': 'https://meowwolf.com/exhibitions/santa-fe/house-of-eternal-return',
     'source_url': 'https://meowwolf.com/exhibitions/santa-fe/house-of-eternal-return',
     'source': 'embedded_json'},
    {'title': 'The Selig Gallery',
     'detail_url': 'https://meowwolf.com/installations/santa-fe/selig',
     'source_url': 'https://meowwolf.com/installations/santa-fe/selig',
     'source': 'embedded_json'},
    {'title': 'Numina',
     'detail_url': 'https://meowwolf.com/santa-fe/numina',
     'source_url': 'https://meowwolf.com/santa-fe/numina',
     'jsonld_type': 'VisualArtwork',
     'source': 'embedded_json'},
]


class TestMeowWolfR2JunkIsExcluded(unittest.TestCase):
    """The two r2 live-run stops are NOT exhibits and must not survive."""

    def test_adulti_verse_event_is_not_a_stop(self):
        self.assertFalse(js.is_exhibit_stop(MEOW_WOLF_JUNK[0], city='Santa Fe'),
                         "an event ('21+ Night Out') is not an exhibit")

    def test_city_guide_blog_is_not_a_stop(self):
        self.assertFalse(js.is_exhibit_stop(MEOW_WOLF_JUNK[1], city='Santa Fe'),
                         "a city-guide/blog page is not an exhibit")

    def test_allowlist_drops_both_junk_keeps_all_real(self):
        kept = js.reject_non_stop_urls(
            MEOW_WOLF_JUNK + MEOW_WOLF_REAL, city='Santa Fe',
            venue_domain='meowwolf.com')
        titles = [k['title'] for k in kept]
        self.assertEqual(len(kept), 3)
        self.assertNotIn('Adulti-Verse at Meow Wolf Santa Fe | 21+ Night Out', titles)
        self.assertNotIn('Santa Fe City Guide: Top Attractions & Restaurants Near …',
                         titles)
        for t in ('House of Eternal Return', 'The Selig Gallery', 'Numina'):
            self.assertIn(t, titles)


class TestPositiveURLSegments(unittest.TestCase):
    """A URL whose path carries an exhibit segment is positively a stop."""

    def test_exhibit_segments_pass(self):
        for seg in ('installations', 'installation', 'exhibits', 'exhibit',
                    'exhibitions', 'exhibition', 'rooms', 'room', 'artworks',
                    'artwork', 'works', 'collection', 'collections', 'gallery',
                    'galleries'):
            item = {'title': 'X', 'detail_url': f'https://v.com/{seg}/the-thing'}
            self.assertTrue(js.is_exhibit_stop(item),
                            f"/{seg}/ should be positively an exhibit")

    def test_non_exhibit_segments_fail(self):
        # Events, nights, guides, blogs, press, tickets, destinations — none match.
        for seg in ('adulti-verse', 'destinations', 'events', 'nights',
                    'blog', 'news', 'press', 'tickets', 'gift-cards', 'shop',
                    'visit', 'about', 'faq', 'contact', 'city-guide'):
            item = {'title': 'X', 'detail_url': f'https://v.com/{seg}/thing'}
            self.assertFalse(js.is_exhibit_stop(item),
                             f"/{seg}/ must NOT be positively an exhibit")


class TestPositiveJsonLdType(unittest.TestCase):
    """A JSON-LD @type can positively identify an item even off an exhibit URL."""

    def test_exhibit_types_pass(self):
        for t in ('ExhibitionEvent', 'VisualArtwork', 'Artwork', 'Installation',
                  'CreativeWork', 'Exhibition'):
            item = {'title': 'X', 'detail_url': 'https://v.com/foo/bar',
                    'jsonld_type': t}
            self.assertTrue(js.is_exhibit_stop(item),
                            f"@type={t} should be positively an exhibit")

    def test_type_lookup_is_case_insensitive(self):
        item = {'title': 'X', 'detail_url': 'https://v.com/foo',
                'jsonld_type': 'EXHIBITIONEVENT'}
        self.assertTrue(js.is_exhibit_stop(item))

    def test_place_type_only_on_venue_domain(self):
        on = {'title': 'Room', 'detail_url': 'https://meowwolf.com/foo',
              'jsonld_type': 'Place'}
        off = {'title': 'Room', 'detail_url': 'https://someblog.com/foo',
               'jsonld_type': 'Place'}
        self.assertTrue(js.is_exhibit_stop(on, venue_domain='meowwolf.com'))
        self.assertFalse(js.is_exhibit_stop(off, venue_domain='meowwolf.com'))

    def test_plain_type_is_not_evidence(self):
        # A generic/navigational type is not positive exhibit evidence.
        item = {'title': 'Buy Tickets', 'detail_url': 'https://v.com/foo',
                'jsonld_type': 'WebPage'}
        self.assertFalse(js.is_exhibit_stop(item))


class TestPositiveHeading(unittest.TestCase):
    """An item lifted from the branch page's own exhibit-list heading passes."""

    def test_from_exhibit_heading_flag(self):
        item = {'title': 'Mystery Room', 'detail_url': 'https://v.com/foo',
                'from_exhibit_heading': True}
        self.assertTrue(js.is_exhibit_stop(item))

    def test_exhibit_heading_string_recognised(self):
        for h in ('Installations', 'Current Exhibitions', 'On View', 'Our Rooms',
                  'Galleries', 'Artworks'):
            item = {'title': 'Mystery', 'detail_url': 'https://v.com/foo',
                    'exhibit_heading': h}
            self.assertTrue(js.is_exhibit_stop(item), f"heading {h!r} should pass")

    def test_non_exhibit_heading_rejected(self):
        item = {'title': 'Mystery', 'detail_url': 'https://v.com/foo',
                'exhibit_heading': 'Plan Your Visit'}
        self.assertFalse(js.is_exhibit_stop(item))

    def test_is_exhibit_heading_helper(self):
        self.assertTrue(js.is_exhibit_heading('Current Exhibitions'))
        self.assertTrue(js.is_exhibit_heading('INSTALLATIONS'))
        self.assertFalse(js.is_exhibit_heading('Buy Gift Cards'))
        self.assertFalse(js.is_exhibit_heading(''))


class TestNoUrlContract(unittest.TestCase):
    """r2 contract preserved: an item with NO URL is judged elsewhere (kept)."""

    def test_item_without_url_is_kept(self):
        item = {'title': 'Some Room', 'detail_url': '', 'source_url': ''}
        self.assertTrue(js.is_exhibit_stop(item))
        self.assertEqual(len(js.reject_non_stop_urls([item], city='Boston')), 1)

    def test_item_with_url_but_no_evidence_is_dropped(self):
        item = {'title': 'Some Page', 'detail_url': 'https://v.com/random-page',
                'source_url': 'https://v.com/random-page'}
        self.assertFalse(js.is_exhibit_stop(item))
        self.assertEqual(js.reject_non_stop_urls([item], city='Boston'), [])


class TestExtractEmbeddedJsonCarriesType(unittest.TestCase):
    """extract_embedded_json must propagate @type so the allow-list can use it."""

    def test_jsonld_type_is_on_each_item(self):
        html = (
            '<script type="application/ld+json">'
            '{"@type":"VisualArtwork","name":"Numina",'
            '"url":"https://meowwolf.com/santa-fe/numina",'
            '"description":"an immersive work"}'
            '</script>')
        items = js.extract_embedded_json(html, 'https://meowwolf.com',
                                         city='Santa Fe')
        self.assertTrue(items)
        self.assertEqual(items[0]['jsonld_type'], 'visualartwork')
        # And that type alone makes it a positive stop.
        self.assertTrue(js.is_exhibit_stop(items[0], venue_domain='meowwolf.com'))


if __name__ == '__main__':
    unittest.main()
