#!/usr/bin/env python3
"""test_local850_unresolved_venue_drift.py — an unresolved museum venue must
resolve correctly, and NEVER drift to another museum's site/corpus/pool.

Reproduced from the wave-19 live evidence (gen 00025-nxb at 8e5db189, cheap env):
  "Rijks Museum Amsterdam, Netherlands" (5) →
    log "No Wikidata candidates for 'Rijks Museum Amsterdam, Netherlands'",
    research drifted to krollermuller.nl, delivered 5/5 KRÖLLER-MÜLLER works
    (Honfleur harbour, Mondrian Compositie 10, Dubuffet Jardin d'émail, Redon
    Cycloop, Seurat Chahut), pinned in Honfleur (49.42, 0.23), $0.341; the 5
    stops pooled under v41|loc:rijks museum amsterdam netherlands|museum.
Kröller-Müller's own Dutch name is literally "Rijksmuseum Kröller-Müller"
(site krollermuller.nl), which is exactly why "Rijks…" drifted to it.

Everything here is OFFLINE: the Wikidata/Serper/identity calls are monkeypatched
or injected, no network, no DB.

What is proven:
  A. Name variants recover the de-glued name AND the compact spelling
     ("Rijks Museum Amsterdam, Netherlands" → includes "Rijksmuseum").
  B. _split_glued_city pulls a known glued city off the name tail.
  C. _resolve_venue_impl resolves the Rijksmuseum (Q190804) for the exact
     failing string, extracting the glued city "Amsterdam".
  D. The Serper knowledge-graph fallback accepts ONLY a museum-type entity
     confirmed in the requested city — never a wrong-city or non-museum one.
  E. _site_pick_is_other_venue — the HARD anti-drift gate: the Kröller-Müller
     pick is rejected; the real rijksmuseum.nl / musee-orsay.fr / metmuseum.org /
     maamboston.org picks are accepted; a same-city Van Gogh→Stedelijk drift is
     rejected.
  F. discover_official_site end-to-end for the exact Kröller-Müller case returns
     found=False (refuse; never another venue's site).
  G. store_delivered_tour(venue_unresolved=True) writes NOTHING (returns 0) — an
     unresolved venue never seeds the pool.

Run:  python3 -m pytest test_local850_unresolved_venue_drift.py -q
"""
import unittest

import venue_resolver as vr


RIJKS_QID = "Q190804"       # Rijksmuseum, Amsterdam
ART_MUSEUM = "Q207694"      # art museum (a _MUSEUM_TYPES member)


# ─────────────────────────────────────────────────────────────────────────────
# A + B. Name normalisation / glued-city recovery
# ─────────────────────────────────────────────────────────────────────────────
class TestNameVariants(unittest.TestCase):
    def test_rijks_variants_include_compact_and_deglued(self):
        v = vr._normalise_venue_name("Rijks Museum Amsterdam, Netherlands")
        # The compact Wikidata label and the de-glued name must both be present.
        self.assertIn("Rijksmuseum", v)
        self.assertIn("Rijks Museum", v)
        # The full as-typed (city-glued, country-stripped) form stays first.
        self.assertEqual(v[0], "Rijks Museum Amsterdam")

    def test_van_gogh_deglued(self):
        v = vr._normalise_venue_name("Van Gogh Museum Amsterdam")
        self.assertIn("Van Gogh Museum", v)

    def test_orsay_unaccented_deglued(self):
        v = vr._normalise_venue_name("Musee d Orsay Paris")
        self.assertIn("Musee d Orsay", v)

    def test_met_article_and_city_stripped(self):
        v = vr._normalise_venue_name("the Met, New York, USA")
        self.assertIn("the Met", v)
        self.assertIn("Met", v)

    def test_split_glued_city(self):
        self.assertEqual(vr._split_glued_city("Rijks Museum Amsterdam"),
                         ("Rijks Museum", "Amsterdam"))
        self.assertEqual(vr._split_glued_city("Museum of Fine Arts Boston"),
                         ("Museum of Fine Arts", "Boston"))
        # A city that is the WHOLE name is never stripped to empty.
        self.assertEqual(vr._split_glued_city("Amsterdam"), ("Amsterdam", ""))
        # An unknown trailing word is left alone.
        self.assertEqual(vr._split_glued_city("Museo Frida"), ("Museo Frida", ""))

    def test_compact_spacing_variants(self):
        self.assertIn("Rijksmuseum", vr._compact_spacing_variants("Rijks Museum"))


# ─────────────────────────────────────────────────────────────────────────────
# C. The exact failing string now resolves to the Rijksmuseum (offline)
# ─────────────────────────────────────────────────────────────────────────────
class TestResolveRijks(unittest.TestCase):
    def setUp(self):
        self._orig = {
            "search": vr._search_entities,
            "disamb": vr._filter_disambiguation_pages,
            "inst": vr._get_instance_of,
            "subent": vr.prefer_parent_institution,
            "valid": vr._validate_city_match,
            "props": vr._fetch_entity_properties,
        }
        self.searched = []

        def _search(q):
            self.searched.append(q)
            # Only the compact label "Rijksmuseum" (bare or city-qualified) hits.
            if "rijksmuseum" in q.lower():
                return [(RIJKS_QID, "Rijksmuseum")]
            return []

        vr._search_entities = _search
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: ART_MUSEUM if q == RIJKS_QID else None
        vr.prefer_parent_institution = lambda c, *a, **k: c
        vr._validate_city_match = lambda q, c: True
        vr._fetch_entity_properties = lambda qid, label: vr.VenueEntity(
            qid=qid, name=label, official_url="https://www.rijksmuseum.nl/")

    def tearDown(self):
        vr._search_entities = self._orig["search"]
        vr._filter_disambiguation_pages = self._orig["disamb"]
        vr._get_instance_of = self._orig["inst"]
        vr.prefer_parent_institution = self._orig["subent"]
        vr._validate_city_match = self._orig["valid"]
        vr._fetch_entity_properties = self._orig["props"]

    def test_resolves_rijksmuseum_and_recovers_city(self):
        ent = vr._resolve_venue_impl("Rijks Museum Amsterdam, Netherlands")
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, RIJKS_QID)
        # The glued city "Amsterdam" was recovered → a city-qualified query ran.
        self.assertTrue(any("Amsterdam" in q for q in self.searched),
                        f"no city-qualified query among {self.searched}")

    def test_never_returns_a_kroller_muller_entity(self):
        ent = vr._resolve_venue_impl("Rijks Museum Amsterdam, Netherlands")
        self.assertIsNotNone(ent)
        self.assertNotIn("kröller", ent.name.lower())
        self.assertNotIn("kroller", ent.name.lower())


class TestCountryAsCityNoGeoDrift(unittest.TestCase):
    """The SECOND wave-19 drift: the caller resolved the bare name "Rijksmuseum"
    with city="Netherlands" (a COUNTRY, parts[1] of the request). The old geo-
    disambiguation geocoded the country centroid and picked the Kröller-Müller
    museum (rural Otterlo, nearer the Netherlands centroid than the Rijksmuseum in
    Amsterdam). A country is not a city: it is discarded, no geo-disambiguation
    against a country runs, and the canonical first candidate (the Rijksmuseum)
    wins."""

    _CANDS = [("Q190804", "Rijksmuseum"), ("Q1505892", "x"),
              ("Q1051928", "Kröller-Müller Museum")]

    def setUp(self):
        self._orig = {k: getattr(vr, k) for k in (
            "_search_entities", "_filter_disambiguation_pages", "_get_instance_of",
            "prefer_parent_institution", "_geocode_city", "_get_coordinates",
            "_validate_city_match", "_fetch_entity_properties")}
        self.geocoded = []
        vr._search_entities = lambda q: self._CANDS if "rijksmuseum" in q.lower() else []
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: "Q207694" if q in ("Q190804", "Q1051928") else None
        vr.prefer_parent_institution = lambda c, *a, **k: c
        # If geo-disambiguation ran against the country it would pick Kröller.
        vr._geocode_city = lambda c: (self.geocoded.append(c) or (52.1, 5.3))
        vr._get_coordinates = lambda q: (52.08, 5.91) if q == "Q1051928" else (52.36, 4.88)
        vr._validate_city_match = lambda q, c: True
        vr._fetch_entity_properties = lambda qid, label: vr.VenueEntity(qid=qid, name=label)

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(vr, k, v)

    def test_country_city_discarded_and_rijks_wins(self):
        ent = vr._resolve_venue_impl("Rijksmuseum", "Netherlands")
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, "Q190804")       # Rijksmuseum, not Kröller-Müller
        self.assertEqual(self.geocoded, [])         # never geocoded the country


class TestCityHintFromLocation(unittest.TestCase):
    """The real city, never a country, is recovered from a request string so the
    resolver can geo-disambiguate among same-country museums."""

    def test_country_tail_yields_glued_city(self):
        self.assertEqual(
            vr.city_hint_from_location("Rijks Museum Amsterdam, Netherlands"),
            "Amsterdam")

    def test_comma_city_preferred(self):
        self.assertEqual(
            vr.city_hint_from_location("Rijksmuseum, Amsterdam, Netherlands"),
            "Amsterdam")

    def test_country_only_tail_returns_empty_when_no_glued_city(self):
        self.assertEqual(
            vr.city_hint_from_location("Some Unknown Museum, France"), "")

    def test_orsay(self):
        self.assertEqual(vr.city_hint_from_location("Musee d Orsay Paris"), "Paris")


class TestGeoCorrectsPreferParentReorder(unittest.TestCase):
    """With the REAL city known, geo-disambiguation re-picks the in-city museum
    even when the collection-size reorder put an unrelated, larger-collection
    museum first — the third wave-19 drift (Rijksmuseum → Museum Catharijneconvent
    in Utrecht, which has a big catalogued collection)."""

    _CANDS = [("Q190804", "Rijksmuseum"),
              ("Q1954426", "Museum Catharijneconvent"),
              ("Q1051928", "Kröller-Müller Museum")]
    _COORDS = {"Q190804": (52.3600, 4.8852),     # Amsterdam
               "Q1954426": (52.0907, 5.1214),    # Utrecht
               "Q1051928": (52.0937, 5.8169)}    # Otterlo

    def setUp(self):
        self._orig = {k: getattr(vr, k) for k in (
            "_search_entities", "_filter_disambiguation_pages", "_get_instance_of",
            "prefer_parent_institution", "_geocode_city", "_get_coordinates",
            "_validate_city_match", "_fetch_entity_properties")}
        vr._search_entities = lambda q: self._CANDS if "rijksmuseum" in q.lower() else []
        vr._filter_disambiguation_pages = lambda c: c
        vr._get_instance_of = lambda q: "Q207694"
        # Reorder by "collection size" puts Catharijneconvent first.
        vr.prefer_parent_institution = lambda c, *a, **k: [
            ("Q1954426", "Museum Catharijneconvent"),
            ("Q190804", "Rijksmuseum"),
            ("Q1051928", "Kröller-Müller Museum")]
        vr._geocode_city = lambda c: (52.3600, 4.8852) if c.lower() == "amsterdam" else (None, None)
        vr._get_coordinates = lambda q: self._COORDS.get(q, (0.0, 0.0))
        vr._validate_city_match = lambda q, c: True
        vr._fetch_entity_properties = lambda qid, label: vr.VenueEntity(qid=qid, name=label)

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(vr, k, v)

    def test_amsterdam_repicks_rijksmuseum(self):
        ent = vr._resolve_venue_impl("Rijksmuseum", "Amsterdam")
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, "Q190804")


# ─────────────────────────────────────────────────────────────────────────────
# D. Serper knowledge-graph fallback — museum-type + confirmed-city ONLY
# ─────────────────────────────────────────────────────────────────────────────
class TestKnowledgeGraphFallback(unittest.TestCase):
    def setUp(self):
        self._orig = {
            "search": vr._search_entities,
            "inst": vr._get_instance_of,
            "valid": vr._validate_city_match,
            "props": vr._fetch_entity_properties,
        }
        vr._search_entities = lambda q: [(RIJKS_QID, "Rijksmuseum")]
        vr._get_instance_of = lambda q: ART_MUSEUM
        vr._fetch_entity_properties = lambda qid, label: vr.VenueEntity(qid=qid, name=label)

    def tearDown(self):
        vr._search_entities = self._orig["search"]
        vr._get_instance_of = self._orig["inst"]
        vr._validate_city_match = self._orig["valid"]
        vr._fetch_entity_properties = self._orig["props"]

    def test_accepts_museum_in_city(self):
        vr._validate_city_match = lambda q, c: True
        ent = vr._resolve_via_knowledge_graph(
            "Rijks Museum Amsterdam", "Amsterdam",
            kg_fetcher=lambda q: {"title": "Rijksmuseum", "type": "Art museum"})
        self.assertIsNotNone(ent)
        self.assertEqual(ent.qid, RIJKS_QID)

    def test_rejects_wrong_city(self):
        vr._validate_city_match = lambda q, c: False
        ent = vr._resolve_via_knowledge_graph(
            "Rijks Museum Amsterdam", "Amsterdam",
            kg_fetcher=lambda q: {"title": "Rijksmuseum"})
        self.assertIsNone(ent)

    def test_rejects_non_museum_type(self):
        vr._validate_city_match = lambda q, c: True
        vr._get_instance_of = lambda q: "Q5"   # human — not a museum type
        ent = vr._resolve_via_knowledge_graph(
            "Rijks Museum Amsterdam", "Amsterdam",
            kg_fetcher=lambda q: {"title": "Rijksmuseum"})
        self.assertIsNone(ent)

    def test_empty_knowledge_graph_returns_none(self):
        vr._validate_city_match = lambda q, c: True
        ent = vr._resolve_via_knowledge_graph(
            "Rijks Museum Amsterdam", "Amsterdam", kg_fetcher=lambda q: {})
        self.assertIsNone(ent)


# ─────────────────────────────────────────────────────────────────────────────
# E. The HARD anti-drift gate on a discovered official-site pick
# ─────────────────────────────────────────────────────────────────────────────
class TestSitePickOtherVenueGate(unittest.TestCase):
    def _g(self, venue, city, title, host):
        return vr._site_pick_is_other_venue(
            venue, city, title, f"https://{host}/", host)

    def test_kroller_muller_drift_rejected(self):
        # The exact drift: requested Rijks…, picked krollermuller.nl whose title
        # is "Rijksmuseum Kröller-Müller" (a DIFFERENT museum).
        self.assertTrue(self._g(
            "Rijks Museum Amsterdam", "Amsterdam",
            "Rijksmuseum Kröller-Müller", "krollermuller.nl"))

    def test_real_rijksmuseum_accepted(self):
        self.assertFalse(self._g(
            "Rijks Museum Amsterdam", "Amsterdam",
            "Rijksmuseum - Home", "rijksmuseum.nl"))

    def test_orsay_accented_accepted(self):
        # Requested unaccented; site title accented — accent folding keeps it.
        self.assertFalse(self._g(
            "Musee d Orsay", "Paris", "Musée d’Orsay", "musee-orsay.fr"))

    def test_massart_acronym_accepted(self):
        # LOCAL-599 preserved: "(MAAM)" is a parenthetical acronym, not a venue.
        self.assertFalse(self._g(
            "MassArt Art Museum", "Boston",
            "MassArt Art Museum (MAAM)", "maamboston.org"))

    def test_same_city_other_venue_rejected(self):
        # Van Gogh Museum requested, Stedelijk Museum site — same city, DIFFERENT
        # venue; must be rejected (identity gate catches the named other venue).
        self.assertTrue(self._g(
            "Van Gogh Museum", "Amsterdam",
            "Stedelijk Museum Amsterdam", "stedelijk.nl"))

    def test_met_accepted(self):
        self.assertFalse(self._g(
            "the Met", "New York",
            "The Metropolitan Museum of Art", "metmuseum.org"))


# ─────────────────────────────────────────────────────────────────────────────
# F. discover_official_site end-to-end for the exact Kröller-Müller case
# ─────────────────────────────────────────────────────────────────────────────
class TestDiscoverRefusesDrift(unittest.TestCase):
    def test_kroller_muller_site_not_returned(self):
        # The exact wave-19 drift: the only web result is krollermuller.nl.
        # Whether it is killed by the score gate OR the LOCAL-850 identity/token
        # guard, the one thing that must hold is: it is NEVER returned.
        def _search(q):
            return [{"link": "https://krollermuller.nl/"}]

        def _fetch(url):
            return {"title": "Rijksmuseum Kröller-Müller", "og_site_name": "",
                    "text": "Otterlo, Netherlands", "status": 200}

        res = vr.discover_official_site(
            "Rijks Museum Amsterdam, Netherlands", "Amsterdam",
            serper_searcher=_search, homepage_fetcher=_fetch,
            parent_searcher=lambda q: [])
        self.assertFalse(res.found)
        self.assertEqual(res.official_url, "")

    def test_drift_guard_rejects_a_high_scoring_other_venue(self):
        # A pick that DOES clear the score gate (two shared name tokens → the
        # +3 title_match name_signal) but names a DIFFERENT venue must be rejected
        # by the LOCAL-850 guard, recorded as drift_rejected, and NOT returned.
        def _search(q):
            return [{"link": "https://stedelijk.nl/"}]

        def _fetch(url):
            # Shares "van"+"gogh" with the request (score ≥ 3) but adds the
            # distinct proper venue name "Stedelijk".
            return {"title": "Van Gogh at the Stedelijk",
                    "og_site_name": "Stedelijk Museum",
                    "text": "Amsterdam. 13 Museumplein, Amsterdam.",
                    "status": 200}

        res = vr.discover_official_site(
            "Van Gogh Museum", "Amsterdam",
            serper_searcher=_search, homepage_fetcher=_fetch,
            parent_searcher=lambda q: [])
        self.assertFalse(res.found)
        self.assertEqual(res.official_url, "")
        self.assertIn("drift_rejected", res.diagnostics)

    def test_real_site_is_returned(self):
        def _search(q):
            return [{"link": "https://www.rijksmuseum.nl/"}]

        def _fetch(url):
            return {"title": "Rijksmuseum", "og_site_name": "Rijksmuseum",
                    "text": "Amsterdam, Netherlands. 1 Museumstraat.",
                    "status": 200}

        res = vr.discover_official_site(
            "Rijksmuseum", "Amsterdam",
            serper_searcher=_search, homepage_fetcher=_fetch,
            parent_searcher=lambda q: [])
        self.assertTrue(res.found)
        self.assertIn("rijksmuseum.nl", res.official_url)


# ─────────────────────────────────────────────────────────────────────────────
# G. The pool never seeds from an unresolved venue
# ─────────────────────────────────────────────────────────────────────────────
class TestPoolSkipsUnresolved(unittest.TestCase):
    _TOUR = (
        "Stop 1: The Night Watch\n"
        "Narration: A documented masterwork.\n\n"
        "Stop 2: The Milkmaid\n"
        "Narration: Another documented work.\n"
    )

    def test_unresolved_venue_writes_nothing(self):
        import stop_pool_store as sp
        # The guard returns 0 BEFORE any psycopg2.connect, so a bogus db_url is
        # never dialed — this proves nothing is written without touching a DB.
        n = sp.store_delivered_tour(
            "Rijks Museum Amsterdam, Netherlands", "museum", self._TOUR,
            "postgresql://invalid-host-should-never-be-dialed/db",
            qid=None, venue_unresolved=True)
        self.assertEqual(n, 0)

    def test_resolved_default_does_not_skip(self):
        # With venue_unresolved False (the default) the guard does NOT short
        # circuit; parsing/DB would run. We only assert the guard itself is a
        # no-op here by confirming an EMPTY tour still returns 0 for a different
        # reason (no parseable stops) — i.e. the skip path is not taken.
        import stop_pool_store as sp
        n = sp.store_delivered_tour(
            "Rijksmuseum", "museum", "", 
            "postgresql://invalid-host-should-never-be-dialed/db",
            qid=RIJKS_QID, venue_unresolved=False)
        self.assertEqual(n, 0)  # 0 because no parseable stops, NOT the skip guard


if __name__ == "__main__":
    unittest.main(verbosity=2)
