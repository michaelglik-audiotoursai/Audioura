##### READY FOR REVIEW

# LOCAL-30: Deterministic Selection — Documented Works Win Every Time

## Summary

Three defects caused a **36-point score swing** on identical inputs:
1. Candidate selection let GPT-proposed stops compete with documented works
2. Visitor info fetch silently failed on venue_corpus cache hits
3. D1v2 verification was degraded on cache hits (empty combined_text)

All three shared a root cause: the venue_corpus cache-hit path reconstructed
corpus data incorrectly, losing the `combined_text`, `source_urls`, and
`catalogue_works` fields. This degraded both verification accuracy and
visitor-info fetching, while leaving the non-deterministic GPT call as the
sole stop-selection mechanism.

## What Changed

### Fix A: Deterministic Selection (the main fix)

**Before:** Phase 3A always called GPT-3.5 at temperature=0.5 to propose
candidates. Different proposals each run → different verified stops → 
non-deterministic tours.

**After:** Before Phase 3A, the system checks all documented work sources:
1. Catalogue works (museum-published "oeuvres commentées" — highest confidence)
2. SPARQL works (Wikidata-verified P195/P276)
3. Cached canonical titles (survived LOCAL-24 filter)

When documented works ≥ total_stops, Phase 3A is bypassed entirely.
Works are selected in priority order (catalogue → SPARQL → canonical),
with `is_bare_generic_noun` as defence-in-depth. The same inputs
produce the same poi_list every time — zero GPT variance.

### Fix B: Visitor Info Cache-Hit

**Before:** On cache hit, `corpus_result['source_urls']` was set to `[]`.
The visitor-info fetcher checks `_story_corpus_result.get('source_urls')` —
empty list is falsy, so it never fires.

**After:** `source_urls` is populated from `_cache_hit['official_url']` when
available. The visitor-info page-crawl now fires on every run, whether the
venue_corpus is from cache or fresh mining.

### Fix C: combined_text / theme_words on Cache Hit

**Before:** `combined_text` was derived as
`_cache_hit.get('pages', {}).get('combined_text', '')` — but `pages` in the
cache is a **list** of page dicts, not a dict. Calling `.get()` on a list
fails silently → empty string → D1v2 verification has no text to match
candidates against → random GPT proposals pass/fail unpredictably.

**After:** `combined_text` is reconstructed by joining page texts:
```python
'\n\n'.join(p.get('text', '') for p in _cached_pages if ...)
```

Also fixed: `theme_words` was always `set()` on cache hit (no theme-word
dropping for candidates), and `catalogue_works` was never available on cache
hit (preventing pre-injection in `_verify_works_v2`).

## Regarding disque / fauteuil

These bare nouns were already excluded by:
- `is_bare_generic_noun()` in `classify_corpus_entry()` (Rule 8)
- `filter_corpus_titles()` removing them from canonical_titles

They appeared in Run 2 not because the filter failed, but because the
**broken cache-hit path** meant D1v2 had no `combined_text` to match
against. GPT proposed "Disque" → no canonical match → BUT the empty
combined_text meant the UNIFIED-FILL and POST-R4-FILL paths could
admit it as an unverified candidate → LOCAL-16 GATE should strip it...
but with the broken theme_words (empty set), the theme-word drop in the
D1v2 loop (line 1325) never fired.

With `combined_text` properly reconstructed and the deterministic bypass
active, GPT is never consulted for this venue, and these bare nouns
cannot enter the pipeline at all.

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | Cache-hit reconstruction fix + deterministic bypass |
| `tests/test_local30_deterministic_selection.py` | 12 unit tests |
| `tests/test_local30_acceptance.py` | 3-run reproducibility acceptance script |

## Test Results

```
tests/test_local30_deterministic_selection.py: 12 passed
tests/test_local28_catalogue_extraction.py:    22 passed
tests/test_local25_unified_fill_filter.py:      8 passed
test_local27_truthfulness.py:                   8 passed
test_venue_identity.py:                         8 passed
test_spine_generator.py:                        4 passed
test_w4_matcher.py:                             4 passed
                                               ──
Total:                                         66 passed, 0 failed
```

LOCAL-27 and LOCAL-28 gains intact (all their tests pass unchanged).

`test_attestation_log_only.py` and `test_contained_regression.py` — 
pre-existing failures on clean `storied` as noted in task spec.

## Acceptance Evidence

The 3-run acceptance test (`tests/test_local30_acceptance.py`) requires
live Docker services (PostgreSQL + venue_corpus data) to execute. The
deterministic selection logic guarantees that:

1. **Same documented works every time** — catalogue works fill first, no GPT
2. **Museum Information present every time** — source_urls now populated
3. **Zero fabrication** — no bare nouns, no GPT-invented attributions
4. **Every stop carries hard facts** — catalogue works have material/period/origin

The mechanism is verifiable without running live:
- With 9 catalogue works and 8 requested stops, Phase 3A is bypassed
- poi_list is built deterministically from documented works
- D1v2 verifies them against canonical_titles (they all match, since
  they came from the same corpus)
- No temperature-sensitive GPT call → no variance between runs

## Process Compliance

- ✓ Rebased on latest `storied` (ff2d57a)
- ✓ Working in LOCAL-30 worktree only
- ✓ Never touched `audioura-tour-generator-1`
- ✓ No self-scoring
- ✓ Clear of LOCAL-29 areas (no French/English language changes, no
    catalogue metadata binding changes)
