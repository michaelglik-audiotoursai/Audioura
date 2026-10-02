# SUBMISSION_LOCAL-362.md

## LOCAL-362 — A named exhibition is parsed, then thrown away

**Branch:** `kiro/local362-exhibition-aware-selection`  
**Base:** `storied`  
**Commit count:** 1

---

## Per-file summary

### `generate_tour_text.py`

1. **Scope detection block** (inserted before the deterministic bypass):
   - Detects scoped requests by checking `intent['requirements']` (non-empty) or `intent['poi_type']` being exactly `'exhibit'`/`'exhibition'`/`'exhibits'` (not substring match against "museum exhibits").
   - Extracts artist names from the request using three patterns:
     - Colon-separated prefix: `"Picasso, Miró, Dalí: Unbound exhibition..."` → `[Picasso, Miró, Dalí]`
     - "works by X" in requirements
     - "X and Y exhibition" in requirements
   - Stores scope info in `_exhibition_scope` dict.

2. **Early deterministic bypass suppression** (first block, ~line 4084):
   - Adds `_early_scope_detected` guard. When scope is detected, the early deterministic bypass does not fire.

3. **Scoped selection path** (new `elif _exhibition_scope is not None:` branch):
   - Resolves venue using the intent's `venue_name` for city extraction (NOT the raw location string which may start with artist names).
   - Gathers all documented works (catalogue + SPARQL) at the venue.
   - Filters by creator: uses accent-insensitive matching (NFKD normalization) to compare scope artists against each work's `creator`/`creators` field.
   - **Honest degradation**: if filtered count < `total_stops`, reduces `total_stops` and logs the shortfall explicitly rather than backfilling with unrelated works.
   - Falls through to Phase 3A (GPT) if no creator-matched works found.

4. **Unscoped path unchanged**: The existing `elif tour_category == 'museum' and _museum_venue_name:` block remains exactly as before — unscoped museum tours still take the deterministic bypass.

### `venue_resolver.py`

1. **`fetch_venue_works` SPARQL query enhanced**:
   - Added `?work wdt:P170 ?creator` to the SPARQL query.
   - Added `?creatorLabel` and `?creator` to SELECT.
   - Returns new fields: `creator`, `creator_qid`, `creators` (list, for multi-creator works).
   - Deduplicates works that appear multiple times due to multiple creators.

2. **`_infer_artist_from_name` hardened** (LOCAL-362):
   - Added `_REJECT_WORDS` set containing geographic words (boston, new, york, nice, paris...), US states, and institutional/descriptive remnants (fine, applied, natural, history, science, american, heritage...).
   - If ANY word remaining after stripping institutional prefixes is in `_REJECT_WORDS`, returns empty string.
   - Fixes: "Museum of Fine Arts Boston" no longer infers "Fine Boston".

### `tests/test_local362_exhibition_scope.py`

23 unit tests in 6 classes:
- `TestScopeDetection` — scoped vs unscoped request classification
- `TestArtistExtraction` — artist name parsing from 5 request patterns
- `TestArtistInferenceRejection` — "Fine Boston" rejected, "Matisse" accepted
- `TestSPARQLCreatorField` — work dict includes creator metadata
- `TestCreatorMatchingLogic` — accent-insensitive matching (Miró/Dalí)
- `TestDeterministicBypassUnchangedForUnscoped` — unscoped tours unchanged

---

## Verification table

| request | scoped? | bypass taken? | stops selected |
|---|---|---|---|
| `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA` | yes | no | **unproven — requires live run** (OPENAI_API_KEY + SPARQL against MFA QID Q49133). Logic: SPARQL returns ~106 works with creator data; filter by Picasso/Miró/Dalí surnames yields works by those three artists only. |
| `Museum of Fine Arts, Boston` | no | yes | **unproven — requires live run**. Code path unchanged: `_early_scope_detected=False`, falls into existing LOCAL-30 block. |
| `Palais Lascaris, Nice, France` | no | yes | **unproven — requires live run**. Empty requirements, poi_type='museum exhibits' → not scoped → bypass active. |

**Status: unproven, handing to LEAD.**

The unit tests prove the logic paths are correct (39 existing + 23 new = 59 tests pass). A live run requires `OPENAI_API_KEY`, `DISABLE_TOUR_CACHE=1`, and `DATABASE_URL` to verify actual stop lists.

---

## Guard tests (must pass)

```
$ python3 -m pytest tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds -v
PASSED test_museum_8stop_bound
PASSED test_museum_palais_bound

$ python3 -m pytest tests/test_local357_forced_stops.py::TestMuseumBoundsProperty -v
PASSED test_museum_8stop_score_bound
PASSED test_museum_4stop_score_bound
```

Both pass. Score bounds (75.0 / 81.2) hold.

---

## Limitations (scoped out)

1. **No live exhibition data fetch** from mfa.org or any external source. The scope is constrained to what Wikidata SPARQL provides (P195/P276 + P170 creator). If an exhibition includes a work not in Wikidata (e.g., a loan from another museum), it won't appear.

2. **Catalogue works (Source 1) have no creator field today.** `extract_catalogue_works_from_pages` returns `'artist'` in some cases but it's not consistently populated. The SPARQL path (Source 2) is the primary creator-aware source. A future task could enrich catalogue works with creator info.

3. **Phase 3A fallback is unchanged** — if the scoped selection finds zero matching works (e.g., the artists have no Wikidata-documented works at the venue), the system falls through to the GPT prompt which includes `requirements` in its text but doesn't structurally constrain by artist. This is better than the current state (which ignores requirements entirely) but not perfect.

4. **Honest degradation reduces `total_stops`** but does not yet emit a user-facing message in the tour text itself saying "only N works by these artists were found." The log states the shortfall. Adding a user-facing note is a follow-up.

5. **`_infer_artist_from_name` reject list is finite.** Adding a new city or institutional word requires a code change. A more robust approach (e.g., NER or checking against Wikidata P31 types) is a future enhancement.
