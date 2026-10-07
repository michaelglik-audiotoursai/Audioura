#!/usr/bin/env python3
"""test_local602_r2_junk_stops.py — LOCAL-602 r2 defect #1 (junk stops).

The r1 live run (tour 397, WNDR Boston) delivered two pages that are NOT stops:

    Stop 6: Buy Gift Cards - WNDR Boston   /tickets/boston/gift-cards
    Stop 2: WNDR Museum Boston             /location/boston   (the branch page)

A stop must be an installation, work, room or exhibition. These tests pin the
deterministic path-only rule in exhibition_site_js.is_stop_url /
reject_non_stop_urls so the two WNDR junk URLs are rejected and real installation
URLs survive.

Run: python3 -m pytest tests/test_local602_r2_junk_stops.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import exhibition_site_js as js


class TestIsStopUrl(unittest.TestCase):

    def test_wndr_r1_junk_urls_are_rejected(self):
        # The exact two pages the r1 run shipped as stops.
        self.assertFalse(
            js.is_stop_url('https://wndrmuseum.com/tickets/boston/gift-cards',
                           city='Boston'))
        self.assertFalse(
            js.is_stop_url('https://wndrmuseum.com/location/boston', city='Boston'))

    def test_real_installation_urls_survive(self):
        for u in (
            'https://wndrmuseum.com/installations/boston/flex',
            'https://wndrmuseum.com/installations/boston/speak-up',
            'https://wndrmuseum.com/installations/boston/mpo-1-time-machine',
            'https://wndrmuseum.com/installations/boston/wndrwall',
            'https://example.org/exhibitions/mirror-room',
        ):
            self.assertTrue(js.is_stop_url(u, city='Boston'),
                            f"should be a stop: {u}")

    def test_transactional_and_nav_pages_rejected(self):
        for u in (
            'https://x.com/shop/mug',
            'https://x.com/store',
            'https://x.com/membership',
            'https://x.com/events/summer-party',
            'https://x.com/faq',
            'https://x.com/visit',
            'https://x.com/contact-us',
            'https://x.com/about',
            'https://x.com/cart',
            'https://x.com/checkout',
            'https://x.com/account',
            'https://x.com/careers',
            'https://x.com/press',
            'https://x.com/blog/why-we-opened',
            'https://x.com/news/2026',
            'https://x.com/privacy',
            'https://x.com/terms',
            'https://x.com/search?q=foo',
            'https://x.com/donate',
            'https://x.com/private-events',
        ):
            self.assertFalse(js.is_stop_url(u, city='Boston'),
                             f"should NOT be a stop: {u}")

    def test_gift_cards_underscore_and_hyphen_both_rejected(self):
        self.assertFalse(js.is_stop_url('https://x.com/gift-cards'))
        self.assertFalse(js.is_stop_url('https://x.com/gift_cards'))
        self.assertFalse(js.is_stop_url('https://x.com/giftcards'))

    def test_branch_index_rejected_many_shapes(self):
        # The branch page itself, however the chain shapes it, is not a stop.
        for u in (
            'https://wndrmuseum.com/boston',
            'https://wndrmuseum.com/location/boston',
            'https://wndrmuseum.com/locations/boston',
            'https://wndrmuseum.com/cities/boston',
        ):
            self.assertFalse(js.is_stop_url(u, city='Boston'),
                             f"branch index should be rejected: {u}")

    def test_bare_domain_and_home_rejected(self):
        self.assertFalse(js.is_stop_url('https://wndrmuseum.com'))
        self.assertFalse(js.is_stop_url('https://wndrmuseum.com/'))
        self.assertFalse(js.is_stop_url('https://wndrmuseum.com/home'))

    def test_empty_url_is_not_rejected_here(self):
        # No URL → judged by other means, not dropped by this gate.
        self.assertTrue(js.is_stop_url(''))
        self.assertTrue(js.is_stop_url(None))

    def test_city_slug_segment_in_a_real_stop_still_passes(self):
        # The city appears as a path segment but there IS a residual stop slug.
        self.assertTrue(
            js.is_stop_url('https://x.com/installations/boston/flex', city='Boston'))


class TestRejectNonStopUrls(unittest.TestCase):

    def _wndr_items(self):
        return [
            {'title': 'Flex | WNDR Museum Boston',
             'detail_url': 'https://wndrmuseum.com/installations/boston/flex',
             'source_url': 'https://wndrmuseum.com/installations/boston/flex'},
            {'title': 'WNDR Museum Boston',
             'detail_url': 'https://wndrmuseum.com/location/boston',
             'source_url': 'https://wndrmuseum.com/location/boston'},
            {'title': 'Speak Up! | WNDR Museum Boston',
             'detail_url': 'https://wndrmuseum.com/installations/boston/speak-up',
             'source_url': 'https://wndrmuseum.com/installations/boston/speak-up'},
            {'title': 'Buy Gift Cards - WNDR Boston',
             'detail_url': 'https://wndrmuseum.com/tickets/boston/gift-cards',
             'source_url': 'https://wndrmuseum.com/tickets/boston/gift-cards'},
            {'title': 'WNDRWall | WNDR Museum Boston',
             'detail_url': 'https://wndrmuseum.com/installations/boston/wndrwall',
             'source_url': 'https://wndrmuseum.com/installations/boston/wndrwall'},
        ]

    def test_drops_both_wndr_junk_stops_keeps_installations(self):
        kept = js.reject_non_stop_urls(self._wndr_items(), city='Boston')
        titles = [i['title'] for i in kept]
        self.assertNotIn('Buy Gift Cards - WNDR Boston', titles)
        self.assertNotIn('WNDR Museum Boston', titles)  # the /location/boston index
        self.assertEqual(len(kept), 3)
        for t in ('Flex | WNDR Museum Boston',
                  'Speak Up! | WNDR Museum Boston',
                  'WNDRWall | WNDR Museum Boston'):
            self.assertIn(t, titles)

    def test_item_without_url_is_kept(self):
        items = [{'title': 'Some Room', 'detail_url': '', 'source_url': ''}]
        self.assertEqual(len(js.reject_non_stop_urls(items, city='Boston')), 1)

    def test_falls_back_to_source_url_when_no_detail_url(self):
        items = [{'title': 'Gift Cards', 'detail_url': '',
                  'source_url': 'https://x.com/tickets/gift-cards'}]
        self.assertEqual(js.reject_non_stop_urls(items, city='Boston'), [])


if __name__ == '__main__':
    unittest.main()
