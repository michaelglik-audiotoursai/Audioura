#!/usr/bin/env python3
"""test_local602_site_first_js_integration.py — LOCAL-602.

The JS-only / chain fallback wired into build_site_first_candidates:
a venue whose every structural listing is the SAME client-side shell still
yields candidate stops from the branch page's embedded JSON, each with a source
URL, with the no-other-city filter dropping another branch's installation.
Offline: fetcher + serper injected.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_site_first as sf


# A JS shell: SAME bytes for every /exhibitions-style path (structural extractor
# finds nothing), with a Boston branch page that ships embedded JSON.
_SHELL = '''<!doctype html><html><head><title>WNDR</title></head><body>
<div id="__next"></div><script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"shows":[]}}}
</script></body></html>'''

_BRANCH_BOSTON = '''<!doctype html><html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"installations":[
 {"@type":"ExhibitionEvent","name":"Infinity Mirror Room","url":"/boston/infinity","description":"An immersive mirrored room in Boston."},
 {"@type":"ExhibitionEvent","name":"The Confetti Room","url":"/boston/confetti","description":"A paper-filled room."},
 {"@type":"ExhibitionEvent","name":"Chicago Light Floor","url":"/chicago/lightfloor","description":"Only in Chicago."}
]}}}
</script></body></html>'''

_SITEMAP = ("<urlset><url><loc>https://wndrmuseum.com/boston</loc></url>"
            "<url><loc>https://wndrmuseum.com/chicago</loc></url></urlset>")


def _fetcher(url, timeout=15):
    root = 'https://wndrmuseum.com'
    if url.endswith('/sitemap.xml'):
        return _SITEMAP, [], {'status': 200, 'bytes': len(_SITEMAP)}
    if url.endswith('/robots.txt'):
        return '', [], {'status': 404, 'bytes': 0}
    if url.rstrip('/') == root + '/boston':
        return _BRANCH_BOSTON, [], {'status': 200, 'bytes': len(_BRANCH_BOSTON)}
    # Every other path (listing seeds, root) → the identical shell.
    return _SHELL, [], {'status': 200, 'bytes': len(_SHELL)}


class TestJsFallbackIntegration(unittest.TestCase):

    def setUp(self):
        self.diag = {}
        self.cands = sf.build_site_first_candidates(
            base_site_url='https://wndrmuseum.com',
            venue_language='en',
            total_stops=7,
            fetcher=_fetcher,
            fetch_detail_pages=False,
            diagnostics=self.diag,
            city='Boston',
        )

    def test_candidates_came_from_js_fallback(self):
        self.assertTrue(self.cands, "JS fallback must yield candidates")
        self.assertEqual(self.diag.get('via'), 'js_fallback')

    def test_identical_shell_detected(self):
        self.assertTrue(self.diag.get('identical_shell'),
                        "the identical client-side shell must be detected")

    def test_branch_page_used(self):
        self.assertEqual(self.diag.get('branch_url'), 'https://wndrmuseum.com/boston')

    def test_boston_installations_present_with_source_urls(self):
        names = {c['name'] for c in self.cands}
        self.assertIn('Infinity Mirror Room', names)
        self.assertIn('The Confetti Room', names)
        for c in self.cands:
            self.assertTrue(c.get('source_url'), f"{c['name']} needs a source URL")

    def test_other_city_installation_dropped(self):
        names = {c['name'] for c in self.cands}
        self.assertNotIn('Chicago Light Floor', names,
                         "a Chicago-only installation must not appear in a Boston tour")


if __name__ == '__main__':
    unittest.main(verbosity=2)
