#!/usr/bin/env python3
"""test_local589_no_invention_on_fetch_failure.py — LOCAL-589 Deliverable 2.

No invention for exhibition museums.

Field defect (tour 394): a transient site FETCH FAILURE (ReadTimeout) looked
like "the site has no shows", and the run fell through to Phase 3A where GPT
INVENTED seven shows. For a resolved exhibition museum (0 catalogue/SPARQL
works), a fetch failure must NEVER become GPT invention: the listing fetch is
retried once (LOCAL-589 D1) and, if it still fails, the pipeline takes the
LOCAL-582 overview rung — never Phase 3A invention.

Tested here:
  1. CONTRACT — `_site_first_empty_action(reason, fetch_failed)` returns
     'overview' on a fetch failure and 'fall_through' on a genuinely empty
     (reachable) site.
  2. WIRING — the site-first consumption block routes a fetch-failure through
     the overview rung and RETURNS (does not fall through to Phase 3A). Asserted
     by source inspection of the block: the overview call is guarded by the
     'overview' verdict and the branch returns, with no Phase-3A fall-through on
     that path.
  3. END-TO-END on the helper's two inputs mirrors the diagnostics contract from
     exhibition_site_first (build_site_first_candidates sets reason/fetch_failed).

Run: python3 -m pytest test_local589_no_invention_on_fetch_failure.py -q
"""
import inspect
import unittest

import generate_tour_text as g
import exhibition_site_first as sf


class TestDecisionContract(unittest.TestCase):
    def test_fetch_failure_takes_overview_not_invention(self):
        self.assertEqual('overview', g._site_first_empty_action('fetch_failed', True))

    def test_fetch_failed_flag_alone_forces_overview(self):
        # Even if reason were mislabeled, the fetch_failed flag forces overview.
        self.assertEqual('overview', g._site_first_empty_action('parsed_zero', True))

    def test_reachable_empty_site_falls_through(self):
        self.assertEqual('fall_through', g._site_first_empty_action('parsed_zero', False))
        self.assertEqual('fall_through', g._site_first_empty_action('no_listing_found', False))


class TestDiagnosticsFeedTheDecision(unittest.TestCase):
    """The real diagnostics that build_site_first_candidates emits must map to
    the decision helper the way the field case requires."""

    def test_total_fetch_failure_yields_overview_verdict(self):
        def always_timeout(url, *a):
            return '', [], {'status': 0, 'error': 'ReadTimeout', 'bytes': 0, 'seconds': 0.1}
        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url='https://griffinmuseum.org/', total_stops=7,
            fetcher=always_timeout, diagnostics=diag)
        self.assertEqual([], cands)
        self.assertEqual(
            'overview',
            g._site_first_empty_action(diag['reason'], diag['fetch_failed']),
            "a total fetch failure must route to the overview rung, not invention"
        )

    def test_reachable_but_empty_yields_fall_through(self):
        def empty_ok(url, *a):
            return ('<html><body><p>welcome, nothing listed</p></body></html>',
                    [], {'status': 200, 'error': '', 'bytes': 50, 'seconds': 0.01})
        diag = {}
        cands = sf.build_site_first_candidates(
            base_site_url='https://griffinmuseum.org/', total_stops=7,
            fetcher=empty_ok, diagnostics=diag)
        self.assertEqual([], cands)
        self.assertEqual(
            'fall_through',
            g._site_first_empty_action(diag['reason'], diag['fetch_failed']),
        )


class TestBlockWiring(unittest.TestCase):
    """Source-level guard: the site-first block must take the overview rung on
    the 'overview' verdict and RETURN there — never fall through to Phase 3A on a
    fetch failure."""

    def _block_src(self):
        src = inspect.getsource(g.generate_tour_text)
        start = src.index("SITE-FIRST EXHIBITION CANDIDATES")
        # Up to the next elif branch (LOCAL-364 exhibition checklist).
        end = src.index("EXHIBITION CHECKLIST RETRIEVAL", start)
        return src[start:end]

    def test_block_calls_decision_helper(self):
        block = self._block_src()
        self.assertIn("_site_first_empty_action(", block)

    def test_overview_verdict_calls_overview_rung_and_returns(self):
        block = self._block_src()
        self.assertIn("== 'overview'", block)
        self.assertIn("_try_deliver_museum_overview(", block)
        # On a successful overview it returns the tour text; on failure it
        # clean-fails with a return — both are returns, no fall-through.
        self.assertIn("return _ov_text, output_file, (None, None)", block)
        self.assertIn("return None, None, (None, None)", block)

    def test_passes_diagnostics_into_builder(self):
        block = self._block_src()
        self.assertIn("diagnostics=_sf_diagnostics", block)


if __name__ == '__main__':
    unittest.main(verbosity=2)
