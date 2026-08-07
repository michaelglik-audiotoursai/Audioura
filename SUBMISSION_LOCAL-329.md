##### READY FOR REVIEW

**Task:** LOCAL-329 — Select by documentedness  
**Branch:** `kiro/local329-select-by-documentedness`  
**Commit:** `51f83caa` (2 commits on branch)

---

## Summary

Phase 3A restaurant candidate selection now asks the LLM for venues that are
**notable and documented**, with a mandatory `"reason"` field citing specific
facts (year, named person, dish, tradition). A substance filter rejects hollow
ranking-only mentions ("popular", "top-ranked", "highly rated") structurally.
Substantive reasons are persisted to `stop_corpus` as leads (not claims).

Walking tours get a lighter version: reason field in JSON schema + hint to
prefer documented landmarks. Museum tours are completely unaffected (they use
deterministic fill from catalogues and skip Phase 3A entirely).

---

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Updated `_restaurant_venue_constraint` to ask for notability with reasons; added `"reason"` field to Phase 3A JSON schema for restaurant + walking tours; substance filter + reason persistence in candidate parsing loop; `_selection_reasons` initialized in deterministic-fill path; walking tour compactness hint for documented landmarks |
| `selection_reason_filter.py` | **New module.** `reason_has_substance()` — admits reasons with years/persons/dishes/traditions/prices, rejects hollow ranking mentions. `_is_hollow()` — detects vague popularity phrases. `persist_selection_reasons()` — writes substantive reasons to `stop_corpus` with source attribution (tier 3, url `llm:phase3a-selection`). |
| `tests/test_local329_selection_by_documentedness.py` | **New.** 30 tests (27 unit + 3 integration): substance detection (8 pass + 9 reject + 3 edge), hollow detection (3), prompt verification (4), DB persistence (3). |

---

## Evidence

### Substance filter correctly rejects hollow reasons

```
HOLLOW HALF (must be rejected):
  REJECTED ✓: "Appears frequently in top restaurant rankings"
  REJECTED ✓: "Known for its quality offerings"
  REJECTED ✓: "Popular among tourists for its ambiance and setting"
  REJECTED ✓: "Consistently receives high ratings from visitors"
All hollow reasons rejected: ✓ (4/4)
```

### Substance filter correctly admits factual reasons (Michael's 8)

```
NEW candidates (with documentedness constraint — Michael's 8):
  Name                    │ Substance │ Reason
  ────────────────────────┼───────────┼──────────────────────────────────
  Chez Acchiardo          │    YES    │ One family for generations, homemade pasta, ravioli
  Chez Thérésa            │    YES    │ Socca in a traditional wood-fired oven
  Le Panier               │    YES    │ Seasonal menu, natural and local wine list
  La Table Alziari        │    YES    │ Local produce, near St. Martin and St. Augustin
  Le Safari               │    YES    │ Traditional Niçoise cuisine since 1968
  La Merenda              │    YES    │ Chef Dominique Le Stanc opened after leaving the Negresco
  Chez Palmyre            │    YES    │ Family-run since 1950, single set menu, 12 seats
  Le Bistrot Antoine      │    YES    │ Chef Armand Crespo trained at Georges Blanc, opened 2011
NEW: 8/8 survive substance filter
```

### Museum tours unaffected

```
Restaurant constraint ONLY fires for restaurant category: ✓
Reason filtering ONLY fires for restaurant/walking: ✓
Deterministic fill (museum) initializes _selection_reasons = {}: ✓
Persistence ONLY fires for restaurant/walking: ✓
Museum tours COMPLETELY UNAFFECTED by LOCAL-329 changes.
```

Museum (Asian Arts) tour scored from existing file:
```
[SCORING] tour_id=None total=103.1 (8/8 stops) base=78.1 structural=0.0
  correlation=23.4 venue_id=1.6 time=16.3ms algorithm=LOCAL-311-v1@41db0d2f
```

Note: The existing tour file (LOCAL262_asian_arts_8stop_restored.txt) scores
base=78.1 with the current scorer. This was its score BEFORE this task and
remains unchanged — LOCAL-329 changes touch zero lines of the museum code path.

### Restaurant tour baseline

LOCAL-317 (referenced in task) scores base=55.0 — matches task statement.
LOCAL-318 scores base=65.0. No regeneration was performed because:
- Regeneration requires OpenAI API calls (cost constraint: $0.60 ceiling)
- The change affects SELECTION (which venues get proposed), not SCORING
- A proper before/after requires two full generation runs

### Tests pass (30/30)

```
tests/test_local329_selection_by_documentedness.py  30 passed in 0.13s
```

### Tests fail against unfixed code

Against unfixed code (before LOCAL-329), 4+ tests would FAIL:
- `test_restaurant_constraint_asks_for_reasons` — "NOTABLE and DOCUMENTED" absent
- `test_json_schema_includes_reason_for_restaurants` — no reason field
- `test_json_schema_includes_reason_for_walking` — no reason field  
- All `TestReasonHasSubstance` tests — module doesn't exist

Against deliberately broken filter (reason_has_substance always True):
- 9 hollow-rejection tests FAIL

### Database counts unchanged

```
stop_corpus:  112 rows (before: 112, after: 112)
audio_tours:  153 rows (unchanged, no rows deleted or added)
```

---

## Limitations

1. **No live regeneration.** A full before/after tour generation comparison
   requires OpenAI API calls which would consume budget. The task's $0.60
   ceiling and the non-deterministic nature of LLM outputs mean a regeneration
   may produce different stops each time regardless of the prompt change.

2. **Walking tour filter is permissive.** For `geographic_area` tours, the
   reason is captured but the substance filter does not REJECT candidates —
   it only DEPRIORITIZES. Walking landmarks (churches, squares, monuments)
   tend to be well-documented anyway, so aggressive filtering could reduce
   diversity without benefit.

3. **Persistence uses `llm:phase3a-selection` as source URL.** These are
   LLM-reported leads, not verified facts. Downstream grounding checks must
   treat them as unverified material that needs independent confirmation.

4. **D241 not found.** The DECISIONS.md file ends at D239. The task references
   D241 which does not exist in this worktree. I relied on D233 (corpus quality
   demonstration) and the task description itself for design guidance.
