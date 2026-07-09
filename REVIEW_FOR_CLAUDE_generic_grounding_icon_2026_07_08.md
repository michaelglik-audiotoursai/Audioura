# Code Review Request — Generic Grounding + I-CON Evaluator (2026-07-08)

**Reviewer:** Claude.AI  
**Branch:** `storied` (commits `72b91d1` → `3929970`)  
**Author:** Services Kiro  

## What was built (two interleaved tasks)

### 1. 🌍 Generic Grounding Phase 1 (wdvrdawcyx) — Zero per-venue configuration

**Problem:** Tours required hardcoded per-venue config (works lists, site URLs, coordinates). Adding any new museum meant code changes.

**Solution:** Runtime Wikidata entity resolution + SPARQL works query replaces ALL hardcoded config.

**New file:** `venue_resolver.py` (~600 LOC)
- Wikidata search API → candidate QIDs
- P31 entity-type filter (museum/gallery) BEFORE geo-disambiguation
- Haversine geo-disambiguation using city coordinates
- P131 fallback for entities without P625 coordinates
- P856 (official URL), P625 (coords), P17 (country→language), P571 (inception)
- P138/P921/P547 artist-link union + name inference fallback
- SPARQL works query (P195/P276) with bilingual labels (local + English)
- `build_dynamic_aliases()` — W4 numeral-aware alias map from SPARQL results
- `build_canonical_titles_from_works()` — includes aliases for cross-language matching

**Modified:** `story_miner.py`
- DELETED: `_KNOWN_WORKS_BY_VENUE` (74 entries across 2 venues)
- DELETED: `CANONICAL_ALIASES` (11 hardcoded Chagall entries)
- DELETED: Chagall-specific narrative URLs
- ADDED: generic `language` parameter to `fetch_venue_narrative_corpus()`
- ADDED: localized narrative keywords per language (fr/it/de/es)
- ADDED: EN Wikipedia ALWAYS fetched (with city validation to reject wrong-city articles)
- ADDED: retry + redirect following on page fetches (15s timeout, 1 retry)
- ADDED: HTTPS fallback when HTTP P856 times out

**Modified:** `generate_tour_text.py`
- `_verify_works_v2()` wired to venue_resolver: canonical titles = union(SPARQL + site + wiki)
- Dynamic aliases injected per-request from SPARQL results
- Removed all hardcoded heuristic fallback URLs
- Fixed misleading "falling back to legacy D1" log messages

**Extended:** `test_w4_matcher.py` — 3 new tests for SPARQL-built dynamic aliases

### 2. 📊 I-CON Evaluator (wdvrdawexa) — Per-stop informational-context scoring

**Problem:** No objective measure of tour content quality. Low-information tours (aesthetic wallpaper) delivered without detection.

**Solution:** Hybrid evaluator (deterministic signals + GPT-4o-mini) scores every paragraph.

**New file:** `icon_evaluator.py` (~400 LOC)
- 7 deterministic signals: date/noun density, story-element traces, prolog overlap, unanswered questions, content-outsourcing detector, generic-filler lexicon, unused-element check
- GPT-4o-mini LLM pass (temperature=0, few-shot calibrated from real tour)
- Deterministic caps: outsourcing→1, filler≥3→1, no-specifics demotion 5→3
- Stop score = paragraph mean; tour score = stop mean + min
- Class distribution (details/historic/social) per paragraph, i-con-weighted
- Advisory gate (logs PASS/FAIL, never rejects — thresholds pending confirmation)
- `prompt_hash` stored for version tracking

**New file:** `icon_migration.sql`
- `stop_metrics` table (additive, nullable columns — Beta parity)
- `audio_tours.i_con_avg` and `i_con_min` columns

**Modified:** `generate_tour_text_service.py`
- I-CON evaluator wired AFTER QA corrective loop (evaluates DELIVERED text)
- `_persist_icon_metrics()` stores results in Postgres
- `i_con_avg` included in job response payload
- Non-blocking: errors logged, never abort delivery

### 3. G4 QA Check (wdvrdawbj4 close-out)

**Modified:** `content_qa_runner.py`
- New FACTUAL check: dated/causal claims in prolog/epilog must trace to story_elements.json
- Extracts sentences with years or causal verbs (became/created/founded/etc.)
- Each must have ≥40% content-word overlap with story elements
- Ungrounded claims → FACTUAL_FAIL_COUNT (release-blocking)

## Review focus areas

1. **venue_resolver.py** — Is the Wikidata API usage correct? Any edge cases in geo-disambiguation? Is the SPARQL query efficient?

2. **story_miner.py changes** — Is the EN Wikipedia city-validation logic sound? Could the retry loop cause unexpected delays?

3. **icon_evaluator.py** — Is the deterministic demotion cap logic correct? Is the LLM prompt well-structured for 4o-mini? Any issues with the paragraph parsing?

4. **Service wiring** — Is `_persist_icon_metrics()` safe for concurrent requests? Could the evaluator call block tour delivery?

5. **content_qa_runner.py G4 check** — Is the 40% overlap threshold reasonable? Could legitimate claims fail?

## Files to review

- `venue_resolver.py` (new, ~600 LOC)
- `icon_evaluator.py` (new, ~400 LOC)
- `icon_migration.sql` (new, schema)
- `story_miner.py` (modified — fetch logic, deleted hardcoded lists)
- `generate_tour_text.py` (modified — _verify_works_v2 wiring)
- `generate_tour_text_service.py` (modified — I-CON wiring after QA)
- `content_qa_runner.py` (modified — G4 check)
- `test_w4_matcher.py` (extended — 3 SPARQL alias tests)

## Known issues (documented, not bugs)

- Chagall P856 (`www.musee-chagall.fr`) is genuinely down — site migrated to `musees-nationaux-alpesmaritimes.fr/chagall/`. Wikidata entry is stale.
- I-CON calibration: held-out Stop 3 scores 2/4 (demotion cap catches some but not all 5→3 splits). Training set is 9/9 perfect.
- Chagall coverage from Docker: 5/10 (limited by dead P856). Production (GCloud) may perform better if redirects work.
