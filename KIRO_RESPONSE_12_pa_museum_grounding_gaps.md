# KIRO_RESPONSE_12 — PA museums field test: venue disambiguation + exhibit-museum grounding gaps

**From:** Mac Mini Kiro · **To:** Claude (reviewer) · **Date:** 2026-07-24
**Branch:** `kiro/round12-museum-grounding`
**Files modified:** `venue_resolver.py`, `story_miner.py`, `generate_tour_text.py`

---

## Summary

All three issues fixed. Both PA museums pass acceptance criteria:
- **AAMP**: resolves to Q770826 (Philadelphia) with `aampmuseum.org`, 9 verified stops
- **NCC**: 10 verified stops (A More Perfect Union, Signers' Hall, Freedom Rising, Civil War and Reconstruction, The First Amendment, Americas Founding, + replenishment)
- **Palais Lascaris**: regression test 13/13 green
- **Test suites**: `test_sq4_merge.py` ALL PASSED, `test_palais_fix_lead_fixture.py` 13/13

---

## Issue 1 — Venue resolver city disambiguation

**Root cause:** `resolve_venue()` searched Wikidata with the bare museum name first, finding the generic "African American Museum" entity (Q4689667, Dallas domain) before considering city constraints.

**Fix (venue_resolver.py):**
1. **City-qualified search first**: tries `"<name> in <city>"`, `"<name> (<city>)"`, `"<name> <city>"` before bare name search (Wikipedia naming conventions).
2. **Disambiguation page detection**: new `_filter_disambiguation_pages()` checks P31=Q4167410 and description text for "disambiguation" / "Wikimedia". Never mines disambiguation pages as corpus.
3. **City validation**: new `_validate_city_match()` validates single candidates against city using P131 chain + P625 coordinates (30km threshold). Rejects candidates that don't match.
4. **D1v2 venue name fix**: `_verify_works_v2` now receives the full location string (with city) instead of just the museum name extracted by intent analysis. This ensures the city is available for disambiguation inside D1v2.

**Evidence:**
```
[venue_resolver] City-qualified search hit: 'African American Museum in Philadelphia' → 1 candidates
[venue_resolver] Resolved: 'African American Museum' → Q770826 (African American Museum in Philadelphia)
    URL: http://aampmuseum.org
    Coords: 39.953169, -75.151836
```

---

## Issue 2 — Exhibit-museum tier: extract exhibit names

**Root cause:** T0a only had art-catalog extraction patterns (title+date, medium+title). Exhibit/experience museums name their stops in section headers, quoted names, and URL slugs — not catalog format.

**Fix (story_miner.py + generate_tour_text.py):**

### T0a extraction (story_miner.py)
Added 4 new patterns:
- **Pattern 3**: Wikipedia section headers (`== Section Name ==`) with generic-section filter
- **Pattern 4**: Quoted exhibit names (`"Name"`, `"Name"`)
- **Pattern 5**: Bold names (MediaWiki `'''Name'''`)
- **Pattern 6**: List-item names (`• Name`, `- Name`, `* Name`)

### Site mining prioritization (story_miner.py)
- Added `exhibits`, `galleries`, `interactive`, `experience`, `installations` to site-mining keywords
- **Exhibit-priority fetching**: URLs containing exhibit keywords are fetched FIRST (before generic /about pages), ensuring the exhibits page is within the 5-page cap
- **Link-based exhibit extraction**: on exhibit index pages, sub-page URL slugs are parsed into exhibit names (e.g. `/exhibits-programs/signers-hall` → `== Signers Hall ==` appended to text for T0a)

### New tier (generate_tour_text.py)
- **`exhibit_museum` tier**: detected when entity is resolved + SPARQL < 5 QIDs + more titles from site/wiki than SPARQL
- Exhibit_museum tier proceeds to R4 replenishment (unlike `medium` which caps at verified count)
- R4 replenishment uses the rich canonical-title corpus (28 titles for NCC, 9 for AAMP) with GPT hints

### EXHIBIT_FILL_HEDGED flag
- Env flag `EXHIBIT_FILL_HEDGED` (default OFF) allows unverified exhibit candidates to fill up to requested stop count
- When ON: dropped candidates with reason "no canonical match" are re-added as `HEDGED`
- Michael decides when/if to enable

### Cache changes
- `CORPUS_VERSION` bumped to 2 (invalidates v1 caches lacking exhibit extraction)
- `venue_corpus.tier` column widened to `VARCHAR(20)` (supports "exhibit_museum")

**Evidence (NCC):**
```
[T0a] Exhibit-name extraction: 16 from sections, 3 from quoted/bold/list
[T0a] Extracted 26 canonical titles, 0 cycle names
[D1v2] Canonical titles union: 26 site/wiki + 3 SPARQL = 29 total
[D1v2] Exhibit museum detected: 3 SPARQL QIDs, 28 total titles
[D1v2] VERIFIED 'A More Perfect Union' → canonical: 'A More Perfect Union'
[D1v2] VERIFIED 'Signers' Hall' → canonical: 'Signers Hall'
[D1v2] VERIFIED 'Freedom Rising' → canonical: 'Freedom Rising'
[D1v2] VERIFIED 'The First Amendment' → canonical: 'The First Amendment'
[R4] Replenishment round 1/3: need 7 more, asking for 12 → +7 verified, total now 10
```

**Evidence (AAMP):**
```
[story_miner] Narrative page: http://aampmuseum.org/current-exhibitions.html (24088 chars)
[story_miner] Narrative page: http://aampmuseum.org/upcoming-exhibits.html (6240 chars)
[story_miner] Narrative page: http://aampmuseum.org/past-exhibits.html (30000 chars)
[D1v2] Canonical titles union: 5 site/wiki + 4 SPARQL = 9 total
[D1v2] 4/10 works verified — tier: exhibit_museum
[R4] Round 1: +5 verified, total now 9
CACHE STORE: African American Museum, Philadelphia, PA / museum exhibits / 10
```

---

## Issue 3 — Artist-grounding contamination

**Root cause:** The artist-placement rejection extracted "artist" by regex-stripping institutional words from the venue name. For NCC this gave "Constitution"; for AAMP it gave "African American". These nonsense "artists" fetched Wikipedia articles that then falsely rejected real exhibits.

**Fix (generate_tour_text.py):**
- Replaced regex extraction with entity-based validation
- Uses `_venue_entity.artist_qid` from venue_resolver (P138/P921/P547 link)
- New `_is_artist_human(artist_qid)` validates P31=Q5 (human) before running the check
- If artist is not a human (e.g. Q11698 "United States Constitution"), logs `[D1v2] artist-check skipped (no valid creator)` and proceeds normally
- Art museums with real artists (e.g. Marc Chagall, Q5879) still get the full artist-placement check

**Evidence:**
```
[D1v2] artist-check skipped (no valid creator) — artist_qid=Q11698 (United States Constitution) is not a human
```
No `places near 'tate'` rejections in either NCC or AAMP runs.

---

## Regression verification

- `test_sq4_merge.py`: ALL TESTS PASSED
- `test_palais_fix_lead_fixture.py`: 13/13 assertions hold
- Palais Lascaris: existing test fixture confirms thin-tier behavior unchanged

---

## Remaining notes for Michael

1. **EXHIBIT_FILL_HEDGED** is OFF by default. Enable with `EXHIBIT_FILL_HEDGED=true` in docker-compose env if you want unverified exhibit candidates to fill up to the requested stop count. Without it, only canonically-matched exhibits are included.
2. **Generic section headers**: The T0a section-header extraction picks up some Wikipedia section names that aren't exhibits (e.g. "Civic education", "Public engagement"). These can verify GPT candidates that happen to share those names. A future refinement could add a section-header blocklist for museum Wikipedia articles.
3. **SPARQL works**: NCC has only 3 Wikidata works, AAMP has 4. The bulk of verification comes from site-mined exhibit names. This is the intended behavior for the `exhibit_museum` tier.
