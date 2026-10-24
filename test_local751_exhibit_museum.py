#!/usr/bin/env python3
"""test_local751_exhibit_museum.py — LOCAL-751 part A (exhibit museums).

A museum whose stops are EXHIBITS / ROOMS / PRESENTATIONS, not catalogued
artworks (the Salem Witch Museum's dioramas; the Torture Museum's rooms), must
still generate a tour. On baseline 027584b0 the Salem Witch Museum field run
(2026-10-23) produced:

    [D1v2] SPARQL source: 0 canonical titles
    [D1v2] Canonical titles union: 28 site/wiki + 0 SPARQL = 28 total
    [LOCAL-625] rejected room/space titles from canonical SET: 28 → 21
    [D1v2] DROPPED 'The Witch Trials of 1692' — no canonical title match   (all 4)
    [D1v2] 0 works verified — tier: unresolvable
    [D1] Tier: unresolvable — clean fail (rung 4; no usable site)

The site WAS reachable and named exhibits; the generator only knew how to match
catalogued ARTWORK titles, so every exhibit was dropped and the tour clean-failed.

LOCAL-751 design (fail-closed kept — no invented exhibits):
  * Detect an EXHIBIT MUSEUM: 0 SPARQL works AND the venue's own site / Wikipedia
    article describes exhibits (there are site/wiki titles).
  * For such a venue the verified stop set is the EXHIBITS the site names — this
    INCLUDES the room/space titles LOCAL-625 would otherwise reject — plus
    sourced subjects the site says the museum presents (e.g. "the 1692 trials").
  * ≥ 2 verified exhibits → a (possibly shorter) tour, tier 'exhibit_museum',
    never a refusal. < 2 → refuse (today's message).

This test drives `_verify_works_v2` through a Salem-Witch-Museum-shaped fixture:
0 SPARQL, a reachable site whose canonical titles are exhibit/room names, and
4 candidate exhibit stops. `match_candidate_to_canonical` is stubbed to match a
candidate iff its name is in the canonical set the verifier presents OR appears
in the combined site text — i.e. it reproduces the real matcher's contract
without its internals, so the test measures whether the FIX puts the exhibit
names into the set the matcher sees.

RED on 027584b0: LOCAL-625 strips the room-shaped exhibit names before matching
and the subject candidate never matches the (now-empty) set → 0 verified →
tier 'unresolvable'. GREEN after the fix: ≥ 2 verified, tier 'exhibit_museum'.

Run: python3 -m pytest test_local751_exhibit_museum.py -q
"""
import unittest

import generate_tour_text as g


VENUE = "The Salem Witch Museum, Salem, MA"
QID = "Q113541747"

# Space/room-shaped titles the site lists. These are exactly what the LOCAL-625
# room/space guard strips from the canonical SET on an ART museum — and exactly
# the exhibit material the ticket says must be KEPT for an EXHIBIT museum. They
# are bare space designations so `room_candidate_guard.is_room_or_space_title`
# rejects them on baseline.
EXHIBIT_ROOM_TITLES = [
    "Gallery 1",   # bare numbered gallery → LOCAL-625 drops on baseline
    "Hall II",     # bare numbered hall    → LOCAL-625 drops on baseline
]
# Sourced SUBJECTS the site says the museum presents (prose, not catalogued
# artwork titles). The baseline matcher has no route that verifies these, so on
# 027584b0 they are DROPPED 'no canonical match'.
SUBJECTS_IN_TEXT = ["The Witch Trials of 1692", "The Salem Village Witchcraft"]

SITE_TEXT = (
    "The Salem Witch Museum presents the story of the Witch Trials of 1692 "
    "through a dramatic stage presentation, and a second self-guided exhibit on "
    "The Salem Village Witchcraft hysteria. Visitors move through Gallery 1 and "
    "Hall II. The museum has educated visitors about the 1692 trials since 1972. "
    * 20
)


class _FakeEntity:
    qid = QID
    language = "en"
    official_url = "https://salemwitchmuseum.com/"
    name = "Salem Witch Museum"
    artist_qid = ""
    artist_name = ""


class _ExhibitMuseumFixture(unittest.TestCase):
    """Shared Salem-shaped mocking harness (0 SPARQL, reachable exhibit site)."""

    def setUp(self):
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
            (story_miner, "fetch_venue_narrative_corpus"),
            (story_miner, "filter_corpus_titles"),
            (story_miner, "extract_catalogue_works_from_pages"),
            (story_miner, "match_candidate_to_canonical"),
        ]:
            _save(mod, name)

        venue_resolver.resolve_venue = lambda *a, **k: _FakeEntity()
        venue_resolver.cache_get = lambda qid: None          # no cache → fresh mine
        venue_resolver.fetch_venue_works = lambda *a, **k: []  # 0 SPARQL works
        venue_resolver.build_canonical_titles_from_works = lambda works: set()

        _site_titles = set(EXHIBIT_ROOM_TITLES) | set(SUBJECTS_IN_TEXT)

        def _corpus(*a, **k):
            return {
                "canonical_titles": set(_site_titles),
                "combined_text": SITE_TEXT,
                "pages": [{"text": SITE_TEXT, "url": _FakeEntity.official_url}],
                "cycle_names": set(),
                "theme_words": set(),
                "source_urls": [_FakeEntity.official_url],
                "per_work_contexts": {},
                "catalogue_works": [],
                "title_sources": {},
                "story_elements": None,
            }

        story_miner.fetch_venue_narrative_corpus = _corpus
        story_miner.extract_catalogue_works_from_pages = lambda pages: []

        # LOCAL-24 passthrough: every site title is a "work" (reproduces the field
        # condition where the work/non-work filter did not remove exhibit names).
        def _passthrough_filter(raw_titles, **kwargs):
            return {
                "works": set(raw_titles),
                "galleries": set(),
                "excluded": set(),
                "aliases": {},
            }

        story_miner.filter_corpus_titles = _passthrough_filter

        # BASELINE matcher contract: a candidate matches ONLY when its exact name
        # is still in the canonical set presented to the verifier. There is NO
        # "appears in the site text" route on 027584b0 — that subject route is the
        # LOCAL-751 fix. So once LOCAL-625 strips the room/space titles and the
        # subject candidates never match, the baseline verifies 0 → unresolvable.
        def _match(candidate, canonical_titles, combined_text):
            for ct in (canonical_titles or []):
                if candidate.strip().lower() == ct.strip().lower():
                    return (ct, "exhibit name on the venue site")
            return None

        story_miner.match_candidate_to_canonical = _match

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)


class TestExhibitMuseumVerifies(_ExhibitMuseumFixture):
    def test_exhibit_museum_yields_two_plus_verified_stops(self):
        poi_list = [
            {"name": "The Witch Trials of 1692"},
            {"name": "The Salem Village Witchcraft"},
            {"name": "Gallery 1"},
            {"name": "Hall II"},
        ]
        result = g._verify_works_v2(poi_list, VENUE)

        self.assertIsNotNone(result, "verifier returned None (hard fail)")
        self.assertEqual(
            "exhibit_museum", result.tier,
            f"expected tier 'exhibit_museum' for a 0-SPARQL museum with a reachable "
            f"exhibit site, got '{result.tier}'",
        )
        self.assertGreaterEqual(
            len(result.pois), 2,
            f"expected >= 2 verified exhibit stops, got {len(result.pois)}: "
            f"{[p.get('name') for p in result.pois]}",
        )


class TestExhibitMuseumCacheHit(unittest.TestCase):
    """A venue the FRESH path generated as an exhibit museum writes a
    venue_corpus cache row with tier='exhibit_museum' (its room/space titles
    already stripped). On a later cache HIT the exhibit second-chance must treat
    those cached titles as exhibit names so the venue generates again instead of
    clean-failing on the round-trip (the Salem re-run regression)."""

    def setUp(self):
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
            (story_miner, "match_candidate_to_canonical"),
        ]:
            _save(mod, name)

        _cached_titles = {"The Witch Trials of 1692", "City on a Hill"}
        _cached_text = (
            "The Salem Witch Museum presents the Witch Trials of 1692 and a "
            "City on a Hill presentation about the Puritans. " * 20)

        venue_resolver.resolve_venue = lambda *a, **k: _FakeEntity()
        venue_resolver.cache_get = lambda qid: {
            "canonical_titles": set(_cached_titles),
            "sparql_works": [],
            "pages": [{"text": _cached_text, "url": _FakeEntity.official_url}],
            "official_url": _FakeEntity.official_url,
            "tier": "exhibit_museum",
        }
        venue_resolver.fetch_venue_works = lambda *a, **k: []
        venue_resolver.build_canonical_titles_from_works = lambda w: set()
        story_miner.extract_catalogue_works_from_pages = lambda p: []
        story_miner.filter_corpus_titles = lambda raw_titles, **k: {
            "works": set(raw_titles), "galleries": set(),
            "excluded": set(), "aliases": {}}

        # Strict matcher: exact canonical only (as in the fresh test).
        def _match(candidate, canonical_titles, combined_text):
            for ct in (canonical_titles or []):
                if candidate.strip().lower() == ct.strip().lower():
                    return (ct, "exhibit name on the venue site")
            return None

        story_miner.match_candidate_to_canonical = _match

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)

    def test_cached_exhibit_museum_generates_on_hit(self):
        # One candidate matches a cached title exactly (main loop); the other is a
        # near-form that only the exhibit second-chance (cached titles as exhibit
        # names) re-admits. Together ≥ 2 → still an exhibit museum on the cache path.
        poi_list = [
            {"name": "The Witch Trials of 1692"},  # exact cached title
            {"name": "City on a Hill presentation"},  # near-form of a cached title
        ]
        result = g._verify_works_v2(poi_list, VENUE)
        self.assertIsNotNone(result)
        self.assertEqual(
            "exhibit_museum", result.tier,
            f"cached exhibit museum must not clean-fail on hit, got '{result.tier}'")
        self.assertGreaterEqual(
            len(result.pois), 2,
            f"expected >= 2 verified exhibit stops on cache hit, got "
            f"{[p.get('name') for p in result.pois]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
