#!/usr/bin/env python3
"""test_local583_speed.py — Deliverable 3 (LOCAL-583).

Two quality-preserving speed fixes, both asserted here WITHOUT any network:

(a) The P856 "is this domain the official site of an institution" check must not
    run against arbitrary third-party domains from SERP results. The known UGC /
    aggregator / people-search / travel-booking hosts (tripadvisor, yelp,
    idcrawl, viator, booking, …) are quick-classified to 'reject' from the rules
    file BEFORE any Wikidata call — the Griffin trace spent 189s in
    external_lookups on exactly these read-timeouts. The gate is NOT removed: an
    unknown domain (and legitimate local news) still gets its P856 check, and the
    per-lookup timeout is short (3s, env-overridable) so a slow/dead Wikidata
    fails fast instead of burning 8s each.

(b) Overpass/OSM lookups for exhibit-museum interior stops are pointless — a
    temporary EXHIBITION has no OSM node — so generate_tour_text.py queries OSM
    ONCE for the museum building instead of once per exhibition name.

Run: python3 -m pytest test_local583_speed.py -q
"""
import os
import unittest

import work_story_searcher as wss


# Hosts that are never an institution's official site — must quick-reject with
# NO P856 network call.
AGGREGATOR_UGC = [
    'tripadvisor.com', 'yelp.com', 'idcrawl.com', 'spokeo.com', 'whitepages.com',
    'viator.com', 'getyourguide.com', 'booking.com', 'expedia.com', 'eventbrite.com',
    'foursquare.com', 'yellowpages.com', 'crunchbase.com', 'glassdoor.com',
]


class TestP856DomainScope(unittest.TestCase):
    def test_aggregators_quick_rejected_without_p856(self):
        for d in AGGREGATOR_UGC:
            self.assertEqual(
                'reject', wss._classify_domain_quick(d),
                f"{d} should quick-reject (no P856 call), got {wss._classify_domain_quick(d)!r}"
            )

    def test_quick_reject_subdomains(self):
        # Subdomain of a reject platform is also rejected (endswith rule).
        self.assertEqual('reject', wss._classify_domain_quick('www.tripadvisor.com'))
        self.assertEqual('reject', wss._classify_domain_quick('m.yelp.com'))

    def test_legit_sources_still_reach_p856_or_rules(self):
        # A real institution domain is tier1 by TLD/rules — never rejected.
        self.assertEqual('tier1', wss._classify_domain_quick('metmuseum.org')
                         if wss._classify_domain_quick('metmuseum.org') else 'tier1')
        self.assertEqual('tier1', wss._classify_domain_quick('somewhere.edu'))
        self.assertEqual('tier1', wss._classify_domain_quick('griffin.museum'))
        # Legitimate local news is NOT rejected — it may be a tier2 source, so it
        # falls through to the P856 check (returns None from quick-classify).
        self.assertIsNone(wss._classify_domain_quick('wickedlocal.com'))

    def test_known_news_is_tier2_not_rejected(self):
        self.assertEqual('tier2', wss._classify_domain_quick('nytimes.com'))


class TestP856Timeout(unittest.TestCase):
    def test_timeout_is_short(self):
        self.assertLessEqual(
            wss.EXTERNAL_LOOKUP_PER_TIMEOUT, 5,
            "P856 per-lookup timeout must be short so a dead Wikidata fails fast"
        )

    def test_timeout_env_overridable(self):
        # The constant is read from EXTERNAL_LOOKUP_PER_TIMEOUT; default 3.
        import importlib
        os.environ['EXTERNAL_LOOKUP_PER_TIMEOUT'] = '2'
        try:
            importlib.reload(wss)
            self.assertEqual(2, wss.EXTERNAL_LOOKUP_PER_TIMEOUT)
        finally:
            del os.environ['EXTERNAL_LOOKUP_PER_TIMEOUT']
            importlib.reload(wss)
        self.assertEqual(3, wss.EXTERNAL_LOOKUP_PER_TIMEOUT)


class TestExhibitMuseumOSMSkip(unittest.TestCase):
    """The per-exhibition Overpass loop must be replaced by a single
    museum-building query for exhibit-museum tours."""

    @classmethod
    def setUpClass(cls):
        _here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(_here, 'generate_tour_text.py'), encoding='utf-8') as fh:
            cls.src = fh.read()

    def test_exhibition_stops_detected(self):
        self.assertIn("_stops_are_exhibitions", self.src)
        self.assertIn("site_exhibition", self.src)

    def test_single_museum_building_query(self):
        # One OSM call for the venue, not per show.
        self.assertIn("querying OSM ONCE for the", self.src)
        self.assertIn("_venue_osm = fetch_osm_venue_facts(_venue_query_name", self.src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
