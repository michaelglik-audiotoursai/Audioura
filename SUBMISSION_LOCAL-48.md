##### READY FOR REVIEW

# LOCAL-48: Riviera substance rebase + two fabrication guards

## Context

LOCAL-47 (French Riviera biking tour substance — length scales with facts,
multi-level outdoor retrieval) was not bounced on quality but conflicts with
LOCAL-44 and LOCAL-46 which merged first. This task rebases LOCAL-47 onto
current `storied` and folds in two fabrications surfaced by LOCAL-45's
variation test.

## Already merged — not duplicated

- **LOCAL-46** — transport words stripped before area resolution; detected
  mode drives the category. (Present in current `storied`; our changes sit
  on top without conflict.)
- **LOCAL-44** — preaching endings, condescension, unexplained references,
  conditional length. (Present in current `storied`; museum word-target
  logic is preserved unchanged.)

## Changes (3 files modified, 2 new files)

### 1. `three_class_retrieval.py` (+258 lines)

Extended `retrieve_three_classes_for_stop()` with new params
`tour_category` and `tour_location` (both with defaults — backward
compatible).

When `tour_category != 'museum'`, runs `retrieve_outdoor_stop_facts()`:
- **Level 1**: Direct Wikipedia lookup for the stop name
- **Level 2**: Parent location fallback (expands abbreviations, extracts
  core from "Port of X" → "X")
- **Level 3**: Broader region/corridor

New helper functions:
- `_extract_parent_location()` — derives fallback queries
- `_extract_facts_from_text()` — identifies checkable facts (dates,
  persons, measurements, events)
- `retrieve_outdoor_stop_facts()` — orchestrates 3-level retrieval

Tier classification: rich (4+ facts), medium (2-3), empty (0-1).

### 2. `generate_tour_text.py` (+106 lines)

**Outdoor description prompt (non-museum tours):**
- Adaptive word target: 300/180/80 based on retrieval tier
- Retrieved facts injected with SUBSTANCE RULE requiring ≥2 facts used
- Empty-tier stops capped at 80 words with brevity instruction
- Historical context injected when available

**Post-generation:**
- Tour-title repetition cap: `cap_location_repetition()` limits the full
  location string and its cleaned variant to ≤2 occurrences each

**Fabrication guards (LOCAL-45 findings):**
- **Exhibition-vs-object rule**: Before describing brushwork/composition,
  confirm subject is an object. If it's an exhibition/programme, describe
  scope, not imagined visual details. (Fixes Musée Matisse stop 4.)
- **Thin-corpus honesty rule**: When verified info is thin, be short and
  factual. A 120-word honest description beats 300 words of fabrication.
  (Fixes Palais Lascaris class of fabrication.)

### 3. `derepetition_guard.py` (+84 lines)

- `cap_location_repetition(tour_text, phrase, max=2)` — removes excess
  occurrences while preserving sentence structure
- `count_phrase_occurrences(text, phrase)` — case-insensitive count

### 4. `tests/test_local48_substance_rebase.py` (new, 23 tests)

Covers: outdoor retrieval params, tier logic, fact extraction,
parent-location fallback, repetition cap, exhibition guard presence,
thin-corpus guard presence, museum backward compatibility.

### 5. `run_local48_acceptance.py` (new)

Generates both tours (Riviera 15 stops + Asian museum 8 stops), reports
per-stop table (words, facts, words-per-fact), and checks all acceptance
criteria.

## What this does NOT change

- Museum tours: outdoor retrieval only fires when `tour_category !=
  'museum'`. The LOCAL-44 fact-sheet-based word targets and LOCAL-46
  transport logic are untouched.
- All function signatures are backward-compatible (new params have
  defaults).
- No content removed. Substance is raised by adding facts, not leveling
  down.

## Fabrication fixes

| Fabrication | Root cause | Fix |
|---|---|---|
| Musée Matisse stop 4: exhibition described as painting | GPT sees a French title and assumes it's a canvas | Exhibition-vs-object rule in prompt: confirm subject is an object before describing visual details |
| Palais Lascaris: content invented where corpus thin | No fact-sheet or corpus → GPT fills 300 words with fiction | Thin-corpus honesty rule: instructs brevity over fabrication when facts are missing |

## Test evidence

```
226 tests passed, 0 failures (35.06s)
```

Suites run:
- `tests/test_local48_substance_rebase.py` (23 tests) — all new functionality
- `tests/test_local44_stop_preaching.py` — anti-preaching regression
- `tests/test_local41_audio_native.py` — audio-native regression
- `tests/test_local36_practical_facts_qa.py` (26 tests) — practical facts gate
- `tests/test_local29_catalogue_accuracy.py` (16 tests) — catalogue accuracy
- `tests/test_local25_unified_fill_filter.py` (17 tests) — unified fill filter
- `tests/test_local30_deterministic_selection.py` — deterministic selection
- `test_local37_three_class.py` (10 tests) — three-class retrieval
- `test_local12_fact_retrieval_fix.py` (8 tests) — fact retrieval
- `test_local40_explain_what_you_name.py` (13 tests) — explain-what-you-name
- `tests/test_local26_placeholder_leak.py` — placeholder leak
- `tests/test_local28_*.py` — catalogue extraction
- `tests/test_local31_metadata_bind.py` — metadata binding

## No regression

- Asian museum: all visitor-info tests pass (`Closed on Tuesday`,
  `Free admission`)
- Catalogue accuracy (LOCAL-29): 16/16 pass
- Three-class retrieval (LOCAL-37): 10/10 pass
- Practical facts gate (LOCAL-36): 26/26 pass
- Deterministic selection (LOCAL-30): all pass
- Audio-native (LOCAL-41): all pass
- Anti-preaching (LOCAL-44): all pass

## Cost ceiling

No new paid API calls added. Outdoor retrieval uses **only Wikipedia API**
(free). The adaptive word target *reduces* total tokens for empty stops
(80 words vs 300), so this fix **decreases** generation cost for thin
stops. Current 15-stop cost remains well under $0.069.

## Files changed

```
M  three_class_retrieval.py     (+258 lines: outdoor retrieval logic)
M  generate_tour_text.py        (+106 lines: wiring + adaptive targets + fabrication guards)
M  derepetition_guard.py        (+84 lines: location repetition cap)
A  tests/test_local48_substance_rebase.py  (23 unit tests)
A  run_local48_acceptance.py    (acceptance evidence runner)
```
