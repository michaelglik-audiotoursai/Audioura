#!/usr/bin/env python3
"""test_local599_official_site_discovery.py — LOCAL-599 Deliverable 4.

Wikidata-independent official-site discovery.

Field defect (2026-10-06): `MassArt Art Museum, Boston, MA`, 7 stops, clean-failed
in seconds. The museum has NO Wikidata item of its own — only its parent,
Q4381563 Massachusetts College of Art and Design, has one. Official-site
discovery ran ONLY through Wikidata P856 / the venue's own Wikipedia article, so
resolve_venue() returned None, no site was found, no corpus was built, and the
run failed. Gemini answered the same question at once from maamboston.org.

These tests drive venue_resolver.discover_official_site with Serper, the homepage
fetcher, and the parent-org Wikidata searcher ALL STUBBED (no network). They
assert the deterministic contract:

  1. MassArt picks maamboston.org over tripadvisor/wikipedia (aggregators are
     rejected; the pick is the domain whose homepage title matches the venue
     name and whose footer carries the city + street address).
  2. Aggregator domains never win, even when they rank first.
  3. The parent-org route recovers a site when the web search is inconclusive
     (MassArt -> Massachusetts College of Art and Design -> P856).
  4. A venue with NO discoverable site at all returns .found == False (the
     caller keeps the current clean fail — no invention).
  5. Scoring is deterministic and needs a NAME signal: a page that only mentions
     the city cannot win on its own.

Run: python3 -m pytest tests/test_local599_official_site_discovery.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import venue_resolver as vr


# ─── Stub fixtures ────────────────────────────────────────────────────────────

# Serper organic results for '"MassArt Art Museum" Boston official site'.
# tripadvisor and wikipedia rank ahead of the real site, as they do live.
_MASSART_ORGANIC = [
    {"link": "https://www.tripadvisor.com/Attraction_Review-massart.html",
     "title": "MassArt Art Museum (MAAM) - Tripadvisor"},
    {"link": "https://en.wikipedia.org/wiki/MassArt_Art_Museum",
     "title": "MassArt Art Museum - Wikipedia"},
    {"link": "https://maamboston.org/",
     "title": "MassArt Art Museum | MAAM"},
    {"link": "https://www.facebook.com/maamboston",
     "title": "MassArt Art Museum - Facebook"},
]

# Homepage HTML per host. maamboston.org carries the venue name in its <title>
# AND the city + street address in the footer. The aggregators would score low
# even if we fetched them (but they are rejected before fetch).
_HOMEPAGES = {
    "maamboston.org": {
        "status": 200,
        "title": "MassArt Art Museum | MAAM",
        "og_site_name": "MassArt Art Museum",
        "text": ("MassArt Art Museum (MAAM) is a free contemporary art museum in "
                 "Boston. 621 Huntington Avenue, Boston, MA 02115. Admission is "
                 "always free."),
        "error": "",
    },
}


def _fake_fetch(url):
    host = vr._registrable_host(url)
    if host in _HOMEPAGES:
        return _HOMEPAGES[host]
    return {"status": 0, "title": "", "og_site_name": "", "text": "", "error": "stubbed-miss"}


def _serper_massart(query):
    return list(_MASSART_ORGANIC)


def _serper_empty(query):
    return []


# Parent-org Wikidata stub: "Massachusetts College of Art and Design" -> Q4381563.
def _parent_search_massart(query):
    q = query.lower()
    if "massart" in q or "massachusetts college" in q:
        return [("Q4381563", "Massachusetts College of Art and Design")]
    return []


class TestMassArtWebSearchPick(unittest.TestCase):
    def setUp(self):
        self.sd = vr.discover_official_site(
            "MassArt Art Museum, Boston, MA",
            serper_searcher=_serper_massart,
            homepage_fetcher=_fake_fetch,
            parent_searcher=lambda q: [],   # force web-search to stand alone
        )

    def test_picks_maamboston_over_aggregators(self):
        self.assertTrue(self.sd.found)
        self.assertEqual("maamboston.org", vr._registrable_host(self.sd.official_url))
        self.assertEqual("web_search", self.sd.source)

    def test_aggregators_were_rejected_not_fetched(self):
        hosts = {c["host"]: c for c in self.sd.diagnostics["candidates"]}
        self.assertIn("tripadvisor.com", hosts)
        self.assertEqual("aggregator", hosts["tripadvisor.com"].get("rejected"))
        self.assertEqual("aggregator", hosts["en.wikipedia.org"].get("rejected"))
        self.assertEqual("aggregator", hosts["facebook.com"].get("rejected"))

    def test_pick_scored_on_title_city_and_address(self):
        pick = next(c for c in self.sd.diagnostics["candidates"]
                    if c["host"] == "maamboston.org")
        reasons = pick["reasons"]
        self.assertTrue(any(r.startswith("title_match") for r in reasons), reasons)
        self.assertIn("street_address", reasons)
        self.assertGreaterEqual(pick["score"], 3)


class TestParentOrgFallback(unittest.TestCase):
    def test_parent_org_recovers_site_when_web_search_inconclusive(self):
        # Web search returns ONLY aggregators -> no web-search pick -> parent-org.
        aggregator_only = [
            {"link": "https://www.tripadvisor.com/x", "title": "x"},
            {"link": "https://en.wikipedia.org/wiki/x", "title": "x"},
        ]
        # The parent org's P856 is fetched through _fetch_entity_properties, which
        # we stub by monkeypatching it to return an entity with a real site.
        class _Ent:
            official_url = "https://massart.edu/"
            language = "en"
        _orig = vr._fetch_entity_properties
        vr._fetch_entity_properties = lambda qid, label: _Ent()
        try:
            sd = vr.discover_official_site(
                "MassArt Art Museum, Boston, MA",
                serper_searcher=lambda q: aggregator_only,
                homepage_fetcher=_fake_fetch,
                parent_searcher=_parent_search_massart,
            )
        finally:
            vr._fetch_entity_properties = _orig
        self.assertTrue(sd.found)
        self.assertEqual("parent_org", sd.source)
        self.assertEqual("Q4381563", sd.parent_qid)
        self.assertEqual("massart.edu", vr._registrable_host(sd.official_url))


class TestNoSiteCleanFail(unittest.TestCase):
    def test_no_web_result_and_no_parent_returns_not_found(self):
        sd = vr.discover_official_site(
            "Nonexistent Private Collection, Nowhere",
            serper_searcher=_serper_empty,
            homepage_fetcher=_fake_fetch,
            parent_searcher=lambda q: [],
        )
        self.assertFalse(sd.found)
        self.assertEqual("", sd.official_url)
        self.assertEqual("", sd.source)


class TestDeterministicScoring(unittest.TestCase):
    def test_city_only_page_cannot_win_without_name_signal(self):
        # A page on an unrelated domain that mentions Boston but NOT the venue
        # name must not be picked (no name signal). The real site is absent.
        organic = [
            {"link": "https://bostonplaces.example/", "title": "Things to do in Boston"},
        ]
        homes = {
            "bostonplaces.example": {
                "status": 200, "title": "Things to do in Boston",
                "og_site_name": "", "text": "Welcome to Boston, Massachusetts.",
                "error": "",
            }
        }
        sd = vr.discover_official_site(
            "MassArt Art Museum, Boston, MA",
            serper_searcher=lambda q: organic,
            homepage_fetcher=lambda u: homes.get(vr._registrable_host(u),
                                                 {"status": 0, "title": "", "og_site_name": "",
                                                  "text": "", "error": "miss"}),
            parent_searcher=lambda q: [],
        )
        self.assertFalse(sd.found,
                         "a page that only mentions the city must not be picked")

    def test_http_non_200_penalised(self):
        # The venue-named page is DOWN (503). Score drops below the threshold,
        # so it is not picked (no corpus from a dead homepage).
        organic = [{"link": "https://maamboston.org/", "title": "MassArt Art Museum"}]
        homes = {"maamboston.org": {"status": 503, "title": "", "og_site_name": "",
                                    "text": "", "error": "503"}}
        sd = vr.discover_official_site(
            "MassArt Art Museum, Boston, MA",
            serper_searcher=lambda q: organic,
            homepage_fetcher=lambda u: homes.get(vr._registrable_host(u),
                                                 {"status": 0, "title": "", "og_site_name": "",
                                                  "text": "", "error": "miss"}),
            parent_searcher=lambda q: [],
        )
        self.assertFalse(sd.found)


if __name__ == "__main__":
    unittest.main(verbosity=2)
