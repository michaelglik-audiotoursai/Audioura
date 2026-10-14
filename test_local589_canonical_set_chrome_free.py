#!/usr/bin/env python3
"""test_local589_canonical_set_chrome_free.py — LOCAL-589 Deliverable 3 (wiring).

ONE chrome filter, applied to the canonical SET that D1v2 verification, R4
replenishment, UNIFIED-FILL, POST-R4-FILL and LOCAL-577's refill all verify
against — not only to the copy written to the cache.

Field defect (tour 394): LOCAL-583 ran reject_chrome_titles on a LOCAL copy just
before the cache write. The in-memory `canonical_titles` set (and
`corpus_result['canonical_titles']`, which R4 reads) still held chrome, so R4
"VERIFIED" Function Rentals / Calls For Entry / Griffin Salon / Griffin Travel /
Exhibitions Closed / Arthur Griffin Archive as exhibition stops.

This test drives `_verify_works_v2` through its cache-hit path with a cache row
that contains BOTH chrome and real shows, and with the LOCAL-24 filter stubbed
to pass everything through (reproducing the field condition where LOCAL-24 did
not catch the chrome). It asserts:

  * `corpus_result['canonical_titles']` — the set R4/UNIFIED-FILL/POST-R4-FILL/
    LOCAL-577 verify against — contains NONE of the chrome labels, and
  * the real Griffin shows DO survive in that set,

so there is nothing chrome left in the canonical set for any downstream path to
"verify" a menu item against.

Run: python3 -m pytest test_local589_canonical_set_chrome_free.py -q
"""
import unittest

import generate_tour_text as g


VENUE = "Griffin Museum of Photography, Winchester, MA"
QID = "Q99108607"

CHROME = [
    "Function Rentals", "Calls For Entry", "Griffin Salon", "Griffin Travel",
    "Exhibitions Closed", "Arthur Griffin Archive",
    "Griffin Museum Board Of Directors 2",
]
REAL = [
    "Intertidal : Field Notes", "Earth, Wind & Fire", "TLC",
    "Lua Kobayashi | The Persistence of Memories",
]


class _FakeEntity:
    qid = QID
    language = "en"
    official_url = "https://griffinmuseum.org/"
    name = "Griffin Museum of Photography"
    artist_qid = ""
    artist_name = ""


class TestCanonicalSetChromeFree(unittest.TestCase):
    def setUp(self):
        # Monkeypatch the module-level imports _verify_works_v2 resolves at
        # runtime. _verify_works_v2 does `from venue_resolver import ...` and
        # `from story_miner import ...` INSIDE the function, so we patch the
        # source modules.
        import venue_resolver
        import story_miner

        self._saved = {}

        def _save(mod, name):
            self._saved[(mod, name)] = getattr(mod, name)

        for mod, name in [
            (venue_resolver, "resolve_venue"),
            (venue_resolver, "cache_get"),
            (venue_resolver, "fetch_venue_works"),
            (venue_resolver, "build_canonical_titles_from_works"),
            (story_miner, "filter_corpus_titles"),
            (story_miner, "extract_catalogue_works_from_pages"),
        ]:
            _save(mod, name)

        venue_resolver.resolve_venue = lambda *a, **k: _FakeEntity()
        venue_resolver.cache_get = lambda qid: {
            "canonical_titles": set(CHROME) | set(REAL),
            "sparql_works": [],
            "pages": [{"text": " ".join(CHROME + REAL)}],
            "official_url": "https://griffinmuseum.org/",
            "tier": "exhibit_museum",
        }
        venue_resolver.fetch_venue_works = lambda *a, **k: []
        venue_resolver.build_canonical_titles_from_works = lambda works: set()
        story_miner.extract_catalogue_works_from_pages = lambda pages: []

        # Reproduce the FIELD condition: LOCAL-24 did NOT strip the chrome, so
        # everything flows through as a "work". The LOCAL-589 chrome filter must
        # be what removes it.
        def _passthrough_filter(raw_titles, **kwargs):
            return {
                "works": set(raw_titles),
                "galleries": set(),
                "excluded": set(),
                "aliases": {},
            }

        story_miner.filter_corpus_titles = _passthrough_filter

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)

    def test_corpus_canonical_set_has_no_chrome_and_keeps_shows(self):
        poi_list = [{"name": name} for name in REAL]
        result = g._verify_works_v2(poi_list, VENUE)

        canon = set((result.corpus_result or {}).get("canonical_titles") or [])
        leaked = set(CHROME) & canon
        self.assertEqual(
            set(), leaked,
            f"Chrome survived in the canonical set R4/fills verify against: {sorted(leaked)}"
        )
        kept = set(REAL) & canon
        self.assertEqual(
            set(REAL), kept,
            f"Real shows were lost from the canonical set: expected {REAL}, got {sorted(canon)}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
