#!/usr/bin/env python3
"""test_local589_site_first_observable.py — LOCAL-589 Deliverable 1.

Observable, retried, honest site-first.

Field defect (tour 394): the site-first path logged "ELIGIBLE" then, 90 s later,
"Site-first found no current exhibitions" with NOTHING in between — the fetch had
failed (ReadTimeout) and the error was swallowed, so the run could not tell a
genuine empty site from a transient network failure, and fell through to GPT
invention. Ten minutes later the SAME call returned 9 shows.

This test asserts the three new behaviours, all without network:

  1. OBSERVABLE: every fetch is logged with URL, status, bytes, seconds and
     (on failure) the exception — captured here through a diagnostics channel.
  2. RETRIED: a listing fetch that fails once (timeout/5xx) is retried; if the
     retry succeeds, the exhibitions are returned (the intermittent-failure
     case that bit Griffin).
  3. HONEST REASON: build_site_first_candidates reports WHY it returned nothing —
     'fetch_failed' when the listing could not be fetched, vs 'parsed_zero'
     when it was fetched but held no exhibitions, vs 'no_listing_found' when no
     seed URL yielded usable HTML. 'ok' when candidates were produced.

Run: python3 -m pytest test_local589_site_first_observable.py -q
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

BASE = 'https://griffinmuseum.org/current-exhibitions/'


def _meta(status=200, error='', seconds=0.01):
    return {'status': status, 'error': error, 'seconds': seconds}


class TestObservableReason(unittest.TestCase):
    def test_reason_ok_when_candidates_found(self):
        def fetch(url):
            return _LISTING_HTML, [], _meta(200)
        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=fetch, diagnostics=diag)
        self.assertTrue(cands, "expected candidates from the Griffin fixture")
        self.assertEqual('ok', diag['reason'])
        self.assertFalse(diag['fetch_failed'])

    def test_reason_fetch_failed_when_listing_errors(self):
        # Every listing fetch raises/5xx — this is the Griffin ReadTimeout case.
        def fetch(url):
            return '', [], _meta(status=0, error='ReadTimeout')
        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=fetch, diagnostics=diag)
        self.assertEqual([], cands)
        self.assertEqual('fetch_failed', diag['reason'])
        self.assertTrue(diag['fetch_failed'])

    def test_reason_parsed_zero_when_fetched_but_empty(self):
        # Listing fetches fine (200, bytes) but holds NO exhibitions.
        def fetch(url):
            return '<html><body><p>Welcome. No shows listed here.</p></body></html>', [], _meta(200)
        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=fetch, diagnostics=diag)
        self.assertEqual([], cands)
        self.assertIn(diag['reason'], ('parsed_zero', 'no_listing_found'))
        self.assertFalse(diag['fetch_failed'])

    def test_every_fetch_is_logged_with_url_status_bytes_seconds(self):
        def fetch(url):
            return _LISTING_HTML, [], _meta(200, seconds=0.02)
        diag = {}
        sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=fetch, diagnostics=diag)
        self.assertIn('fetches', diag)
        self.assertTrue(diag['fetches'], "no fetch records captured")
        rec = diag['fetches'][0]
        for key in ('url', 'status', 'bytes', 'seconds'):
            self.assertIn(key, rec, f"fetch record missing '{key}': {rec}")


class TestRetryOnTransientFailure(unittest.TestCase):
    def test_listing_fetch_retried_once_then_succeeds(self):
        # First call to the listing fails (timeout); the retry succeeds. The
        # exhibitions must come back — the intermittent failure must NOT be
        # reported as an empty site.
        state = {'listing_calls': 0}

        def fetch(url):
            # The listing URL is the one that carries the fixture.
            if url.rstrip('/').endswith('current-exhibitions') or url.rstrip('/') == 'https://griffinmuseum.org':
                state['listing_calls'] += 1
                if state['listing_calls'] == 1:
                    return '', [], _meta(status=0, error='ReadTimeout')
                return _LISTING_HTML, [], _meta(200)
            return '', [], _meta(404)

        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=fetch, diagnostics=diag)
        self.assertTrue(cands, "retry should have recovered the exhibitions")
        self.assertEqual('ok', diag['reason'])
        self.assertGreaterEqual(state['listing_calls'], 2, "listing fetch was not retried")


class TestBackwardCompatibility(unittest.TestCase):
    def test_two_tuple_fetcher_still_works(self):
        # Legacy fetchers return (html, links) — must still be accepted.
        def legacy_fetch(url):
            if url.rstrip('/').endswith('current-exhibitions') or url.rstrip('/') == 'https://griffinmuseum.org':
                return _LISTING_HTML, []
            return '', []
        cands = sf.build_site_first_candidates(
            base_site_url=BASE, total_stops=5, fetcher=legacy_fetch)
        self.assertTrue(cands, "legacy 2-tuple fetcher must still yield candidates")


if __name__ == '__main__':
    unittest.main(verbosity=2)
