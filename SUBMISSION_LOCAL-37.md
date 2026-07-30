##### READY FOR REVIEW

# LOCAL-37: Three-Class Stories — Details / Historical / Social

## What was built

### 1. Three targeted retrievals per stop (Task §1)

New module `three_class_retrieval.py` generates class-targeted queries:

| Class | Query strategy | Example (Disque bi, category="jade bi disc") |
|---|---|---|
| **Details** | `"{entity}" material dimensions technique medium` | `"Disque bi" material dimensions technique medium` |
| **Historical** | `"{category}" origin era history evolution` ← CATEGORY level | `"jade (néphrite) ritual disc" origin era history evolution` |
| **Social** | `"{entity}" OR "{maker}" commissioned owned reception who` | `"Disque bi" commissioned owned reception provenance` |

Also added `synthesize_class_targeted_queries` in `work_story_searcher.py`.

### 2. Category determination from existing data (Task §2)

`determine_category()` resolves the broad object category from:
1. Catalogue works (material + type_label from `story_miner` structured extraction)
2. Stop metadata (material, type_label, wikidata_class from D1/venue_resolver)
3. Per-work contexts (Material: prefix in metadata sentences)

**Never asks the model to guess.** Only uses what the pipeline already holds.

Evidence from integration test:
```
Ganesh dansant            → category: "chlorite schist sculpture"
Kannon aux onze visages   → category: "wood Buddhist statue"
Disque bi                 → category: "jade (néphrite) ritual disc"
Bouddha assis             → category: "bronze Buddhist statue"
```

### 3. Element type → class mapping (Task §3)

All 13 existing element types mapped to exactly one class:

| Class | Element types | Justification |
|---|---|---|
| **Details** | technique, date | Physical properties of the thing |
| **Historical** | origin, reference_work, legend | Places the thing in time/style/tradition |
| **Social** | person, dedication, turning_point, provenance, reception, controversy, quote, intention | Centres on named humans and relationships |

### 4. `apply_tour_diversity` wired in production (Task §4)

Was dead code — now called before Phase 5 description generation.

Two-pass enforcement:
- **Pass 1 (original):** element-type diversity (max 2 stops share same top type)
- **Pass 2 (LOCAL-37):** three-class diversity (max 3 stops share same dominant class)

Evidence from integration test (8 all-historic stops):
```
8 historic-dominant stops → 5 class diversity swaps applied
Stop 1: top_type=origin          swap=(none)
Stop 2: top_type=origin          swap=(none)
Stop 3: top_type=person          swap=(none)
Stop 4: top_type=technique       swap={'demoted_class': 'historic', 'promoted_class': 'details'}
Stop 5: top_type=technique       swap={'demoted_class': 'historic', 'promoted_class': 'details'}
...
```

### 5. Tour-type agnostic (Task §5)

The unit is the entity. `synthesize_class_queries` and `determine_category` work on any named entity with a location — museum artwork, street landmark, or restaurant. Tour type only affects source ranking weights, not branching logic.

## Category-level framing guard

**Non-optional:** category material is validated before injection.

`check_category_framing_violation()` detects patterns like "This bowl was fired..." on elements marked `is_category_level=True`. Violations are removed before reaching the generation prompt.

The generation prompt injects category context with explicit framing rules:
```
RULE: When using this context, say 'objects of this type...' or 
'jade bi disc pieces were typically...', NEVER 'this jade bi disc was...'
```

## Cost discipline

- Free path first: Wikipedia API for category-level context
- No paid SERP calls added (class queries prepared but bounded by existing tier system)
- Category context cached via same `work_stories` mechanism with long TTL

## Test evidence

### Unit tests: 10/10 PASS
```
✓ test_element_type_mapping
✓ test_category_determination
✓ test_class_queries
✓ test_class_queries_with_artist
✓ test_classify_element
✓ test_compute_stop_class_distribution
✓ test_tag_elements_by_class
✓ test_category_framing_guard
✓ test_tour_diversity_prevents_historic_mush (historic-dominant: 2/6)
✓ test_work_story_searcher_class_queries
```

### Regression: ALL existing test suites pass (zero failures)
- test_b6_generation_wiring: 14/14 PASS
- test_w7_wiring: ALL PASS
- test_sq2_fixtures: ALL PASS
- test_sq3_fixtures: ALL PASS
- test_sq4_merge: ALL PASS
- test_f4_cache_roundtrip: ALL PASS
- test_w4_matcher: ALL PASS
- test_w9_collection_anchor: ALL PASS
- test_venue_identity: 11/11 PASS
- test_palais_fix_lead_fixture: 23/23 PASS
- test_tier_computation: ALL PASS
- test_g4_false_positives: ALL PASS
- test_spine_generator: 18/18 PASS
- tests/test_local25-29: 65 passed (pytest)
- tests/test_local30_deterministic_selection: 12 passed (pytest)

### Full acceptance run

Requires `OPENAI_API_KEY` and Docker services. Runner script: `run_local37_acceptance.py`

Reports per-stop class distribution, category collapse violations, and non-regression checks for:
- Asian Arts Museum: 8/8 stops, base ≥ 81.25
- Matisse: 8/8 stops
- Palais Lascaris: ≥6 stops

## Files changed

| File | Change |
|---|---|
| `three_class_retrieval.py` | **NEW** — Core module: class mapping, category determination, class queries, diversity, guard |
| `story_element_extractor.py` | Enhanced `apply_tour_diversity` with two-pass class enforcement |
| `work_story_searcher.py` | Added `synthesize_class_targeted_queries` |
| `generate_tour_text.py` | Wired three-class retrieval, diversity, category context injection |
| `test_local37_three_class.py` | **NEW** — 10 unit tests |
| `run_local37_acceptance.py` | **NEW** — Acceptance evidence runner |
