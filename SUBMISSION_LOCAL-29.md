##### READY FOR REVIEW

## LOCAL-29: Catalogue Accuracy Fixes

**Branch:** `kiro/local29-catalogue-accuracy`  
**Base:** `storied`  
**Agent:** Mac Mini Kiro

---

### Defect A — Catalogue metadata cross-contamination between entries

**Root cause identified (3 layers):**

1. **HTML parser boundary failure** (`story_miner.py:_parse_catalogue_from_html`):
   The original regex used a lookahead `(?=<h2|</main>|</article>|</body>)` to delimit
   sections between h2 headings. On the live MAA page, this regex allowed body content
   from the Kannon section to bleed into Ganesh's section, causing `_extract_period()`
   to find "XIIe siècle" (Kannon's period) instead of "Xe siècle" (Ganesh's period).

2. **C5-1 corpus injection** (`generate_tour_text.py:4095`): Raw keyword search over the
   ENTIRE combined venue corpus (`_d1_venue_corpus.split('.')`) matched sentences from
   adjacent entries when they shared any 4+ character keyword.

3. **§4 story element injection** (`generate_tour_text.py`): Loose 8-character prefix
   matching (`_normalize(poi_name)[:8]`) could match works with similar name prefixes.

4. **fact_extractor.py** `_extract_corpus_for_poi`: Same loose 8-char prefix + `any()`
   keyword matching allowed cross-contamination.

**Fixes applied:**

| File | Change |
|------|--------|
| `story_miner.py` | Replaced lookahead regex with `re.split()` at h2 boundaries — clean non-overlapping sections |
| `generate_tour_text.py` (C5-1) | Replaced unbounded keyword search with bounded lookup from `evidence_log` (per-work `method='catalogue_work'` metadata) and `per_work_contexts` |
| `generate_tour_text.py` (§4) | Tightened matching: 10-char prefix + bidirectional containment + 60% word overlap threshold; `break` after first match |
| `fact_extractor.py` | Tightened prefix matching (10-char bidirectional) and changed keyword search from `any()` to `all()` of first 3 keywords |

**Provenance check for "Bengal":** The catalogue text for Ganesh explicitly states
"Provenant de la région du Bengale ou du Bihar" — so "Bengal" IS sourced from the
catalogue and correctly attributed. The fix ensures it only appears in Ganesh's stop.

---

### Defect B — French text delivered inside an English tour

**Root cause:** `_fetch_visitor_info_from_site()` extracted visitor info directly from
the French museum website and returned it verbatim. The `language` parameter existed
but was never passed at the call site, and the function had no translation logic.

**Fix applied:**

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `_translate_visitor_info_to_language()` function: deterministic pattern-based FR→EN translation for known museum-info patterns (days, "fermé/ouvert", "entrée gratuite", time formats "10h30"→"10:30") |
| `generate_tour_text.py` | Call site now passes `language="en"` explicitly |
| `generate_tour_text.py` | Translation is purely mechanical (no GPT) — preserves sourced factual content |

**Key design decision:** Translation is deterministic/rule-based, NOT GPT-based. This
means the data remains sourced (from the official museum website) while being presented
in the visitor's language. If the deterministic translator encounters patterns it doesn't
recognize, it falls back to the raw text (better than nothing, and the structured
extraction already captures the key patterns for French museums).

**Example:**
- Before: `Museum Information: Fermé le mardi. Entrée gratuite`
- After: `Museum Information: Closed on Tuesday. Free admission`

---

### Regression test

**File:** `tests/test_local29_catalogue_accuracy.py` — 25 tests, all passing.

Test classes:
- `TestPerWorkContextBoundary` — verifies adjacent entries don't bleed (Ganesh/Kannon)
- `TestC51BoundedLookup` — verifies evidence_log metadata is per-work
- `TestFactExtractorBoundedLookup` — verifies fact_extractor bounded matching
- `TestStoryMinerCatalogueExtraction` — verifies parser section boundaries (text + mocked HTML)
- `TestVisitorInfoTranslation` — verifies FR→EN translation of common patterns
- `TestMetadataBindingEndToEnd` — end-to-end metadata binding check

---

### Test results

```
tests/test_local29_catalogue_accuracy.py    — 25 passed
tests/test_local28_catalogue_extraction.py  — 22 passed
test_local12_fact_retrieval_fix.py          — 8 passed
test_spine_generator.py                     — 6 passed
test_attestation_log_only.py                — ERROR (pre-existing fixture issue)
test_contained_regression.py                — 0 collected (pre-existing)
```

---

### Acceptance checklist

- [x] Catalogue metadata cross-contamination fixed at parser level AND injection level
- [x] Each stop gets ONLY its own material/period/origin from catalogue
- [x] Regression test with two adjacent entries (different centuries) asserts no bleed
- [x] "Bengal" verified: IS stated in catalogue for Ganesh → correctly sourced
- [x] Museum Information still sourced from official website (not generated)
- [x] Museum Information rendered in English (translated from French at presentation time)
- [x] Translation is deterministic (no GPT) — data remains sourced
- [x] All existing tests pass (LOCAL-28, LOCAL-12, spine_generator)
- [x] Pre-existing failures unchanged (attestation_log_only, contained_regression)

---

### Files modified

1. `story_miner.py` — HTML catalogue parser boundary fix (re.split instead of lookahead)
2. `generate_tour_text.py` — C5-1 bounded lookup, §4 tightened matching, visitor info translation
3. `fact_extractor.py` — Bounded per-work context extraction
4. `tests/test_local29_catalogue_accuracy.py` — NEW: 25-test regression suite
