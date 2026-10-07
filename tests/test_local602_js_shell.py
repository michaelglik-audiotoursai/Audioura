#!/usr/bin/env python3
"""test_local602_js_shell.py — LOCAL-602 root causes #1 and #2.

JS-only (identical-shell) detection, sitemap/robots URL discovery, branch-page
pick for a chain, embedded-JSON extraction, Serper site:<domain> <city>, and the
no-other-city filter. All offline (fetch/serper injected).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_site_js as js


# A tiny Next.js-style shell: identical bytes for every route, with __NEXT_DATA__.
_SHELL = '''<!doctype html><html><head><title>WNDR</title></head><body>
<div id="__next"></div>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"locations":[
  {"@type":"Place","name":"WNDR Museum Boston","url":"/boston","city":"Boston"},
  {"@type":"Place","name":"WNDR Museum Chicago","url":"/chicago","city":"Chicago"}
],"exhibits":[
  {"@type":"ExhibitionEvent","name":"Infinity Mirror Room","url":"/boston/infinity","description":"An immersive room."},
  {"@type":"ExhibitionEvent","name":"Chicago-only Light Floor","url":"/chicago/lightfloor","description":"Chicago installation."}
]}}}
</script></body></html>'''


class TestIdenticalShell(unittest.TestCase):

    def test_same_shell_different_paths_is_detected(self):
        recs = [
            {'url': 'https://x.com/exhibitions', 'html': _SHELL},
            {'url': 'https://x.com/current', 'html': _SHELL},
            {'url': 'https://x.com/exhibition', 'html': _SHELL},
        ]
        self.assertTrue(js.detect_identical_shell(recs))

    def test_distinct_pages_are_not_flagged(self):
        recs = [
            {'url': 'https://x.com/a', 'html': _SHELL},
            {'url': 'https://x.com/b', 'html': _SHELL.replace('Boston', 'Nowhere') + '<p>'*50},
        ]
        self.assertFalse(js.detect_identical_shell(recs))

    def test_fingerprint_ignores_whitespace(self):
        # Runs of whitespace collapse to a single space, so two copies that differ
        # only in the LENGTH of whitespace runs fingerprint identically.
        a = js.shell_fingerprint('<html>   <body>hi</body>   </html>' + 'x' * 100)
        b = js.shell_fingerprint('<html> <body>hi</body> </html>' + 'x' * 100)
        self.assertEqual(a, b)


class TestSitemapAndBranch(unittest.TestCase):

    def test_sitemap_and_robots(self):
        pages = {
            'https://wndr.com/robots.txt': "User-agent: *\nSitemap: https://wndr.com/sitemap.xml\n",
            'https://wndr.com/sitemap.xml': (
                "<urlset><url><loc>https://wndr.com/boston</loc></url>"
                "<url><loc>https://wndr.com/chicago</loc></url>"
                "<url><loc>https://other.com/x</loc></url></urlset>"),
        }
        fetch = lambda u: (pages.get(u, ''), [])
        urls = js.sitemap_urls('https://wndr.com', fetch)
        self.assertIn('https://wndr.com/boston', urls)
        self.assertIn('https://wndr.com/chicago', urls)
        self.assertNotIn('https://other.com/x', urls)  # off-domain dropped

    def test_pick_branch_from_sitemap(self):
        urls = ['https://wndr.com/chicago', 'https://wndr.com/boston',
                'https://wndr.com/about']
        self.assertEqual(
            js.pick_branch_url('https://wndr.com', 'Boston', urls),
            'https://wndr.com/boston')

    def test_pick_branch_seed_when_not_in_sitemap(self):
        # No candidate list → conventional /<slug> seed on the root.
        self.assertEqual(
            js.pick_branch_url('https://wndr.com', 'Boston', []),
            'https://wndr.com/boston')

    def test_branch_seed_slug_variants(self):
        seeds = js.branch_url_seeds('https://x.com', 'San Diego')
        self.assertIn('https://x.com/san-diego', seeds)
        self.assertIn('https://x.com/locations/san-diego', seeds)


class TestEmbeddedJson(unittest.TestCase):

    def test_extracts_titles_and_urls_from_next_data(self):
        items = js.extract_embedded_json(_SHELL, 'https://wndr.com/boston',
                                         city='Boston')
        titles = {it['title'] for it in items}
        self.assertIn('Infinity Mirror Room', titles)
        self.assertIn('WNDR Museum Boston', titles)
        # Relative URLs resolved against base_url.
        infinity = next(it for it in items if it['title'] == 'Infinity Mirror Room')
        self.assertEqual(infinity['detail_url'], 'https://wndr.com/boston/infinity')
        self.assertEqual(infinity['source'], 'embedded_json')

    def test_empty_html_yields_nothing(self):
        self.assertEqual(js.extract_embedded_json('', 'https://x.com'), [])


class TestSerperSiteCity(unittest.TestCase):

    def test_on_domain_results_only(self):
        def serper(q):
            self.assertEqual(q, 'site:wndr.com Boston')
            return {'organic': [
                {'title': 'Boston Exhibits', 'link': 'https://wndr.com/boston/x',
                 'snippet': 'In Boston.'},
                {'title': 'Review', 'link': 'https://news.com/wndr',
                 'snippet': 'off domain'},
            ]}
        out = js.serper_site_city('wndr.com', 'Boston', serper)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['detail_url'], 'https://wndr.com/boston/x')
        self.assertEqual(out[0]['source'], 'serper_site_city')

    def test_no_key_or_bad_serper_returns_empty(self):
        self.assertEqual(js.serper_site_city('x.com', 'Boston', None), [])
        self.assertEqual(
            js.serper_site_city('x.com', 'Boston', lambda q: (_ for _ in ()).throw(RuntimeError())),
            [])


class TestNoOtherCityFilter(unittest.TestCase):

    def test_other_city_only_item_is_dropped(self):
        items = [
            {'title': 'Infinity Mirror Room', 'detail_url': 'https://wndr.com/boston/infinity',
             'snippet': 'A Boston room.'},
            {'title': 'Chicago-only Light Floor', 'detail_url': 'https://wndr.com/chicago/lightfloor',
             'snippet': 'Chicago installation.'},
            {'title': 'Generic Room', 'detail_url': 'https://wndr.com/room', 'snippet': ''},
        ]
        kept = js.filter_other_city(items, 'Boston')
        names = {k['title'] for k in kept}
        self.assertIn('Infinity Mirror Room', names)
        self.assertIn('Generic Room', names)         # no city → kept
        self.assertNotIn('Chicago-only Light Floor', names)  # other city only → dropped

    def test_item_mentioning_both_is_kept(self):
        items = [{'title': 'Boston & Chicago opening', 'detail_url': '', 'snippet': ''}]
        self.assertEqual(len(js.filter_other_city(items, 'Boston')), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
