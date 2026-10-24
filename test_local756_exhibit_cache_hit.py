#!/usr/bin/env python3
"""test_local756_exhibit_cache_hit.py — LOCAL-756 issue A.

The Salem Witch Museum (Q113541747) still clean-fails on the CACHE-HIT path,
although LOCAL-751 shipped the fresh exhibit-museum route. Field log
(2026-10-24, cache HIT):

    [venue_cache] HIT for Q113541747 (tier=exhibit_museum, …)
    [D1v2] Cache HIT: 8 canonical titles (tier=exhibit_museum) …
    [D1v2] DROPPED 'The Witch Trials of 1692' — theme/book word 'witch', not a work title
    [D1v2] DROPPED 'The Trial of Rebecca Nurse' — no canonical title match
    [D1v2] DROPPED 'The Witch's Curse' — no canonical title match
    [D1v2] DROPPED 'The Salem Witch Trials Exhibit' — theme/book word 'witch', not a work title
    [D1v2] 0 works verified — tier: unresolvable

The cached exhibit names (venue_corpus.canonical_titles_json, written by
LOCAL-751's own live run) are "The Trial of George Jacobs", "City on a Hill",
"Martha Corey and her Persecutors", "Arresting a Witch", "Witch Trial at Mount
Holly", "Discounts And Discount Partners", "The Witches", "Examination of a
Witch". The four LLM candidates match NONE of them, so the LOCAL-751 second
chance (which only re-admits a matching candidate, and only 'no canonical
match' drops) has nothing to admit; two candidates are dropped on the theme
word 'witch' and never reconsidered.

LOCAL-756 A fix (fail-closed kept):
  1. When the LLM candidates do not verify on an exhibit museum, build the
     candidate list FROM the sourced exhibit names and verify those — "Discounts
     And Discount Partners" is site chrome and must be dropped, never a stop.
  2. The second chance also reconsiders 'theme word' drops for an exhibit museum.
  >= 2 verified → a tour (tier exhibit_museum); < 2 → today's refusal.

RED on aeaae8f9: 0 verified → tier 'unresolvable'.
GREEN after the fix: >= 2 verified exhibit stops, tier 'exhibit_museum', and the
junk title "Discounts And Discount Partners" is never one of them. The same
request twice (fresh miss, then cache hit) both generate.

Run: python3 -m pytest test_local756_exhibit_cache_hit.py -q
"""
import unittest

import generate_tour_text as g


VENUE = "The Salem Witch Museum, Salem, MA"
QID = "Q113541747"

# The EXACT cached exhibit names from the field cache row (LOCAL-751 live run).
CACHED_TITLES = [
    "The Trial of George Jacobs",
    "City on a Hill",
    "Martha Corey and her Persecutors",
    "Arresting a Witch",
    "Witch Trial at Mount Holly",
    "Discounts And Discount Partners",  # site chrome — must never be a stop
    "The Witches",
    "Examination of a Witch",
]
CACHED_TEXT = (
    "The Salem Witch Museum presents the Witch Trials of 1692. Visitors see "
    "The Trial of George Jacobs, City on a Hill, Martha Corey and her "
    "Persecutors, Arresting a Witch, Witch Trial at Mount Holly, The Witches, "
    "and an Examination of a Witch. " * 20)

# The four LLM candidates from the field run — they match NONE of the cached
# titles (two of them trip the 'witch' theme word).
LLM_CANDIDATES = [
    {"name": "The Witch Trials of 1692"},       # theme-word drop on baseline
    {"name": "The Trial of Rebecca Nurse"},      # no canonical match
    {"name": "The Witch's Curse"},               # no canonical match
    {"name": "The Salem Witch Trials Exhibit"},  # theme-word drop on baseline
]


class _FakeEntity:
    qid = QID
    language = "en"
    official_url = "https://salemwitchmuseum.com/"
    name = "Salem Witch Museum"
    artist_qid = ""
    artist_name = ""


class _CacheHitHarness(unittest.TestCase):
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
            (story_miner, "extract_catalogue_works_from_pages"),
            (story_miner, "filter_corpus_titles"),
            (story_miner, "match_candidate_to_canonical"),
        ]:
            _save(mod, name)

        venue_resolver.resolve_venue = lambda *a, **k: _FakeEntity()
        venue_resolver.cache_get = lambda qid: {
            "canonical_titles": set(CACHED_TITLES),
            "sparql_works": [],
            "pages": [{"text": CACHED_TEXT, "url": _FakeEntity.official_url}],
            "official_url": _FakeEntity.official_url,
            "tier": "exhibit_museum",
        }
        venue_resolver.fetch_venue_works = lambda *a, **k: []
        venue_resolver.build_canonical_titles_from_works = lambda w: set()
        story_miner.extract_catalogue_works_from_pages = lambda p: []
        # Work/non-work passthrough (field condition: exhibit names are "works").
        story_miner.filter_corpus_titles = lambda raw_titles, **k: {
            "works": set(raw_titles), "galleries": set(),
            "excluded": set(), "aliases": {}}

        # STRICT field matcher: a candidate matches ONLY an exact canonical title.
        # The four LLM candidates match none → every one is DROPPED on baseline.
        def _match(candidate, canonical_titles, combined_text):
            for ct in (canonical_titles or []):
                if candidate.strip().lower() == ct.strip().lower():
                    return (ct, "exhibit name on the venue site")
            return None

        story_miner.match_candidate_to_canonical = _match

    def tearDown(self):
        for (mod, name), val in self._saved.items():
            setattr(mod, name, val)


class TestExhibitCacheHitGeneratesFromSourcedNames(_CacheHitHarness):
    def test_cached_exhibit_museum_generates_from_sourced_names(self):
        result = g._verify_works_v2(list(LLM_CANDIDATES), VENUE)
        self.assertIsNotNone(result, "verifier returned None (hard fail)")
        self.assertEqual(
            "exhibit_museum", result.tier,
            f"cached exhibit museum must not clean-fail on the HIT path when the "
            f"LLM candidates match no cached title — got tier '{result.tier}'")
        self.assertGreaterEqual(
            len(result.pois), 2,
            f"expected >= 2 verified exhibit stops from the sourced names, got "
            f"{[p.get('name') for p in result.pois]}")

    def test_junk_title_never_becomes_a_stop(self):
        result = g._verify_works_v2(list(LLM_CANDIDATES), VENUE)
        self.assertIsNotNone(result)
        _names = [(p.get('name') or '').strip().lower() for p in result.pois]
        self.assertNotIn(
            "discounts and discount partners", _names,
            "site chrome 'Discounts And Discount Partners' must never be a stop")


class TestSameRequestTwice(_CacheHitHarness):
    """The same request twice in a row (the cache HIT path both times here) must
    both generate — the regression is the SECOND (round-trip) run clean-failing
    a venue the first produced."""

    def test_two_consecutive_runs_both_generate(self):
        r1 = g._verify_works_v2(list(LLM_CANDIDATES), VENUE)
        r2 = g._verify_works_v2(list(LLM_CANDIDATES), VENUE)
        for i, r in enumerate((r1, r2), 1):
            self.assertIsNotNone(r, f"run {i} returned None")
            self.assertEqual("exhibit_museum", r.tier,
                             f"run {i} clean-failed (tier {r.tier})")
            self.assertGreaterEqual(len(r.pois), 2,
                                    f"run {i} produced < 2 stops")


if __name__ == "__main__":
    unittest.main(verbosity=2)
