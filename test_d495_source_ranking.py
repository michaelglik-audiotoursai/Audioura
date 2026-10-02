#!/usr/bin/env python3
"""test_d495_source_ranking.py — D495: (d), the source-ranking hardening.

Five changes, each with its own section and each with a RED-CHECK note saying
what to break in production to see the assertion fail. A test that cannot fail
is not evidence (D242 standing check 1), and every section here was run against
the pre-D495 tree first.

  [1] the art-market source class, decided before any network call
  [2] the venue's own domain is tier1 for its own tour
  [3] Wikidata fail-open: "could not reach" != "not an institution"
  [4] the persistent disk cache, and what it refuses to persist
  [5] the production-fact bonus requires event company
      + the catalogue exemption is zero on museum tours

The case under [1] and [5] is the one D492 measured: the best action-bearing
sentence in 112 retrieved for the Miro stop was an auction lot line.
"""
import json
import os
import tempfile
import unittest

import snippet_ranker as sr
import work_story_searcher as w


# The sentence D492 found at the top of the pool. Note what it does NOT have:
# no lot number, no price, no dimensions — so `_is_catalogue_snippet` is blind
# to it, and before D495 it collected the production-fact bonus instead.
LOT_LINE = ("Le Lezard aux Plumes d'Or | c.1967 | Lithograph in Colors Printed "
            "on Japan Kochi Paper | Printed by Atelier Mourlot")
SPEC_SHEET = "Edition of 180 copies. Drypoint and lithograph on sheepskin. Set of 10."
SCHOLARLY = ("In 1971 Mourlot printed the forty lithographs in Paris for the "
             "publisher Louis Broder, on publisher vellum.")
CHECKLIST = ("Le Lezard aux plumes d or. Joan Miro. 1971. Illustrated book with "
             "forty lithographs. Gift of Boris Fridman.")


def snip(text, tier='', title=''):
    return {'title': title, 'snippet': text, 'url': 'https://example.test/x', 'tier': tier}


# ─── [1] the art-market class ────────────────────────────────────────────────
class TestArtMarketClass(unittest.TestCase):
    """RED-CHECK: delete `art_market_domains` from source_tier_rules.json, or
    remove the Step 0b block in `_classify_domain_quick`. All four go red."""

    def test_market_domains_classify_without_a_lookup(self):
        # The point is not only the verdict — it is that no network call is
        # needed to reach it. `_classify_domain_quick` returns None when it
        # cannot decide, which is what sends a domain to Wikidata.
        for d in ('invaluable.com', 'christies.com', 'sothebys.com',
                  'liveauctioneers.com', '1stdibs.com', 'mutualart.com',
                  'abebooks.com', 'drouot.com', 'artprice.com'):
            self.assertEqual(w._classify_domain_quick(d), w.TIER_MARKET, d)

    def test_artnet_and_artsy_are_no_longer_tier2(self):
        # Both sat in `tier2_news_domains` among 48 entries with the NYT and
        # JSTOR, scoring +1. Artnet is a price database; Artsy is a gallery
        # marketplace.
        for d in ('artnet.com', 'artsy.net'):
            self.assertEqual(w._classify_domain_quick(d), w.TIER_MARKET, d)
        rules = json.load(open(w.RULES_PATH))
        self.assertNotIn('artnet.com', rules['tier2_news_domains'])
        self.assertNotIn('artsy.net', rules['tier2_news_domains'])

    def test_market_subdomains_classify_too(self):
        self.assertEqual(w._classify_domain_quick('www.invaluable.com'), w.TIER_MARKET)

    def test_market_is_demoted_in_the_ranker(self):
        self.assertEqual(
            sr.score_snippet(snip(LOT_LINE, 'market')) + 5,
            sr.score_snippet(snip(LOT_LINE, '')),
            'market tier must move the score by MARKET_PENALTY')


# ─── [2] the venue's own domain ──────────────────────────────────────────────
class TestVenueDomainSeeding(unittest.TestCase):
    """RED-CHECK: remove the Step 0 block in `_classify_domain_quick`.
    `test_venue_domain_is_tier1` goes red; the unset test stays green, which is
    what tells you the test is reading the venue rule and not a seed entry."""

    def tearDown(self):
        w.set_venue_domain('')

    def test_venue_domain_is_tier1(self):
        w.set_venue_domain('https://www.mfa.org/')
        self.assertEqual(w._classify_domain_quick('mfa.org'), 'tier1')

    def test_collection_subdomain_is_tier1(self):
        w.set_venue_domain('https://www.mfa.org/')
        self.assertEqual(w._classify_domain_quick('collections.mfa.org'), 'tier1')

    def test_a_different_venue_gets_its_own_domain(self):
        # The seed list was 13 hardcoded museums. This must work for a venue
        # nobody has ever added to a list.
        w.set_venue_domain('https://www.museepicasso.paris.fr/')
        self.assertEqual(w._classify_domain_quick('museepicasso.paris.fr'), 'tier1')
        self.assertNotEqual(w._classify_domain_quick('mfa.org'), 'tier1')

    def test_unset_venue_grants_nothing(self):
        w.set_venue_domain('')
        # mfa.org is deliberately NOT in institutional_domain_seed — the whole
        # point of D495 is that it no longer needs to be.
        self.assertIsNone(w._classify_domain_quick('mfa.org'))

    def test_lookalike_domain_is_not_the_venue(self):
        w.set_venue_domain('https://www.mfa.org/')
        self.assertIsNone(w._classify_domain_quick('notmfa.org'))
        self.assertIsNone(w._classify_domain_quick('mfa.org.evil.test'))


# ─── [3] Wikidata fail-open ──────────────────────────────────────────────────
class TestWikidataFailOpen(unittest.TestCase):
    """RED-CHECK: change the dead-host short-circuit in `_check_wikidata_p856`
    back to `return 'tier3'`. `test_cold_host_is_unverified` goes red.

    This is the bug that produced the 6-point inversion: `batch_check_wikidata_p856`
    submits `_check_wikidata_p856` per domain, so the FIRST failure marked the
    host cold and every remaining domain in the run short-circuited to tier3."""

    def test_cold_host_is_unverified_not_tier3(self):
        import dead_host_breaker
        orig = dead_host_breaker.is_host_cold
        dead_host_breaker.is_host_cold = lambda *a, **k: True
        try:
            self.assertEqual(w._check_wikidata_p856('mfa.org'), w.TIER_UNVERIFIED)
        finally:
            dead_host_breaker.is_host_cold = orig

    def test_unverified_scores_zero(self):
        # Michael's ruling: a lookup we could not perform carries no information
        # about the source, so it must move the score by nothing.
        self.assertEqual(
            sr.score_snippet(snip(CHECKLIST, 'unverified')),
            sr.score_snippet(snip(CHECKLIST, '')),
            'unverified must be score-neutral')

    def test_successful_but_unknown_still_costs_five(self):
        # The other half of the ruling, and the half that stops SEO filler from
        # rising to meet the museums: a lookup that SUCCEEDED and found no
        # institutional class is still tier3.
        self.assertEqual(
            sr.score_snippet(snip(CHECKLIST, 'tier3')) + 5,
            sr.score_snippet(snip(CHECKLIST, '')))


# ─── [4] the persistent disk cache ───────────────────────────────────────────
class TestDiskCache(unittest.TestCase):
    """RED-CHECK: make `_disk_cache_put` accept every tier. The
    `refuses_to_persist_unverified` test goes red — and that is the assertion
    that matters, because caching one bad network minute would make it permanent."""

    def setUp(self):
        self._orig_path = w._DISK_CACHE_PATH
        self._tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        self._tmp.close()
        os.unlink(self._tmp.name)
        w._DISK_CACHE_PATH = self._tmp.name
        w._DISK_CACHE = {}

    def tearDown(self):
        w._DISK_CACHE_PATH = self._orig_path
        w._DISK_CACHE = {}
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_a_decisive_verdict_survives_the_process(self):
        w._disk_cache_put('mfa.org', 'tier1')
        w._DISK_CACHE = {}  # simulate the next tour, a fresh process
        self.assertEqual(w._disk_cache_load().get('mfa.org'), 'tier1')

    def test_refuses_to_persist_unverified(self):
        # Asserted against the FILE, not against `_disk_cache_load`. The loader
        # filters too, so a load-side assertion stays green even with the
        # put-side guard deleted — which is exactly what the red-check caught on
        # the first version of this test.
        w._disk_cache_put('mfa.org', w.TIER_UNVERIFIED)
        raw = {}
        if os.path.exists(w._DISK_CACHE_PATH):
            with open(w._DISK_CACHE_PATH) as fh:
                raw = json.load(fh)
        self.assertNotIn('mfa.org', raw,
                         'a network failure must never be written to the cache file')
        w._DISK_CACHE = {}
        self.assertIsNone(w._disk_cache_load().get('mfa.org'))

    def test_a_corrupt_cache_file_does_not_break_a_tour(self):
        with open(self._tmp.name, 'w') as fh:
            fh.write('{not json')
        w._DISK_CACHE = {}
        self.assertEqual(w._disk_cache_load(), {})


# ─── [5] production facts require event company ──────────────────────────────
class TestProductionFactBonus(unittest.TestCase):
    """RED-CHECK: drop the `and _is_event_snippet(text)` clause from the
    non-catalogue production-fact bonus. `lot_line_gets_no_bonus` and
    `spec_sheet_gets_no_bonus` both go red while `scholarly_note` stays green."""

    def test_the_measured_premise_still_holds(self):
        # If this ever fails, the rest of the section is testing something else:
        # the lot line reaches the NON-catalogue branch, because it carries no
        # lot number, no price and no dimensions.
        self.assertFalse(sr._is_catalogue_snippet(LOT_LINE))
        self.assertTrue(sr._has_production_fact_content(LOT_LINE))

    def _bonus_paid_on(self, text):
        """How many points the production-fact branch actually contributes.

        Measured by scoring the same text twice with `_has_production_fact_content`
        forced False and then left alone — so it pins the BRANCH, not the helper.
        The first version of these tests asserted on `_is_event_snippet` directly
        and stayed green when the `and _is_event_snippet(text)` clause was deleted
        from production. It was testing the helper, not the rule.
        """
        orig = sr._has_production_fact_content
        sr._has_production_fact_content = lambda t: False
        try:
            without = sr.score_snippet(snip(text, ''))
        finally:
            sr._has_production_fact_content = orig
        return sr.score_snippet(snip(text, '')) - without

    def test_lot_line_gets_no_production_bonus(self):
        self.assertTrue(sr._has_production_fact_content(LOT_LINE))
        self.assertEqual(self._bonus_paid_on(LOT_LINE), 0,
                         'an auction lot line must not be paid for naming its printer')

    def test_spec_sheet_gets_no_production_bonus(self):
        self.assertTrue(sr._has_production_fact_content(SPEC_SHEET))
        self.assertEqual(self._bonus_paid_on(SPEC_SHEET), 0)

    def test_scholarly_production_note_keeps_its_bonus(self):
        self.assertTrue(sr._has_production_fact_content(SCHOLARLY))
        self.assertEqual(self._bonus_paid_on(SCHOLARLY), 3,
                         'a production note with an actor still earns its bonus')

    def test_the_museum_beats_the_lot_after_d495(self):
        # The whole point, end to end. Before D495 this comparison was 8 to 7
        # the wrong way, on a cold-Wikidata run.
        lot = sr.score_snippet(snip(LOT_LINE, 'market', 'Joan Miro'), artist='Joan Miro',
                               category='museum')
        museum = sr.score_snippet(snip(CHECKLIST, 'unverified', 'Le Lezard'),
                                  artist='Joan Miro', category='museum')
        self.assertGreater(museum, lot,
                           f'museum={museum} lot={lot} — the inversion is back')

    def test_catalogue_exemption_is_zero_on_museum_tours(self):
        priced = LOT_LINE + ' | Lot 34 | Estimate: $3,000-5,000'
        self.assertTrue(sr._is_catalogue_snippet(priced))
        museum = sr.score_snippet(snip(priced, ''), category='museum')
        other = sr.score_snippet(snip(priced, ''), category='walking')
        self.assertEqual(other - museum, 3,
                         'museum tours must not pay the +3 catalogue exemption')

    def test_other_categories_are_unchanged(self):
        # `category=''` is the default for every caller that has not opted in.
        self.assertEqual(sr.score_snippet(snip(LOT_LINE, ''), category=''),
                         sr.score_snippet(snip(LOT_LINE, '')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
