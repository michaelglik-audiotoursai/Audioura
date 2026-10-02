##### READY FOR REVIEW

**Task:** LOCAL-359  
**Branch:** kiro/local359-scope-check-address  
**Commit:** 6a8df1d  

---

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | `_check_one` inside `_validate_stops_within_scope` now reads `poi.get('address')` and injects it into the judge prompt with an authoritative note. Confidence gate changed from `if inside or conf == "low"` to `if inside or conf in ("low", "medium")`. |
| `tests/test_local359_scope_check_address.py` | 7 new offline tests: address appears in prompt, address absent when empty, medium-keeps, high-removes, low-keeps, inside-any-keeps, out-of-scope-high-removes. |

---

## Findings

### 1. Address availability at call site

The poi dict **does** carry an `address` field when `_validate_stops_within_scope` is called. It is set by `_new_poi(name, c.get("address") or "")` at line 4482 during Phase 3A parsing. The `_new_poi` factory (line 3830) creates a dict with explicit `address` key. No pipeline redesign is needed — the data was available and simply ignored.

### 2. Fix: address injected into the judge prompt

When `poi.get('address')` is non-empty, the prompt now includes:
```
Address (authoritative): 1 Cours Saleya, 06300 Nice
NOTE: The address is a verified fact. If the address is clearly within
'Old Nice (Vieux Nice)', answer true regardless of what you recall about the name.
```

### 3. Confidence gate assessment

**Changed from:** removal at medium-or-better (`if inside or conf == "low"`)  
**Changed to:** removal only at high (`if inside or conf in ("low", "medium")`)

**Reasoning (failure-cost asymmetry):**
- **Removing a real in-scope stop** is destructive and unrecoverable within the run. The tour silently shrinks. The user never knows the stop existed. This is what happened to Le Safari.
- **Keeping a marginal stop** costs nothing at tour quality — it's a real place in the general area. If it's slightly outside the boundary, the tour still works.
- The Le Safari incident proves gpt-3.5-turbo returns incorrect medium-confidence "outside" answers for street-level geography. Medium is not reliable enough for a destructive, unrecoverable action.
- High confidence is the appropriate bar: the model must be quite sure, and with the address now included, high-confidence answers will be better informed.

### 4. Model upgrade assessment

The check uses `TOUR_LLM_MODEL` (default `gpt-3.5-turbo`). A per-check override to gpt-4o-mini would cost ~$0.0001/stop × 12 stops ≈ $0.0012/tour — negligible. However, with the address now in the prompt and the gate raised to high, gpt-3.5-turbo should no longer produce false positives like Le Safari (the address "1 Cours Saleya" is unambiguously in Vieux Nice). I did not raise the model; the two code fixes address the root cause without adding cost. If false positives persist after live testing, a per-check model override is the natural next step.

---

## Verification evidence

### Offline (provable now) — tests pass on fixed code, FAIL on original

```
$ python3 -m pytest tests/test_local359_scope_check_address.py -v
7 passed, 1 warning in 0.21s
```

Against unfixed code (git stash to revert):
```
FAILED test_address_appears_in_prompt_when_present - AssertionError: Address '1 Cours Saleya' not found in scope-check prompt
FAILED test_medium_confidence_outside_keeps_stop - AssertionError: Stop judged outside with medium confidence should be KEPT. Got: ['Anchor Stop']
2 failed, 1 warning in 0.19s
```

### Museum bounds held

```
$ python3 -m pytest tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds -v
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds::test_museum_8stop_bound PASSED
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds::test_museum_palais_bound PASSED
2 passed, 1 warning in 0.24s

$ python3 -m pytest tests/test_local357_forced_stops.py::TestMuseumBoundsProperty -v
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_8stop_score_bound PASSED
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_4stop_score_bound PASSED
2 passed, 1 warning in 0.21s
```

### Full relevant suite

```
$ python3 -m pytest tests/test_local359_scope_check_address.py tests/test_local357_forced_stops.py tests/test_local345_corpus_in_body.py tests/test_local346_bridge_vs_thin_row.py tests/test_local352_narrative_arc.py tests/test_local285_restaurant_selection.py tests/test_local329_selection_by_documentedness.py -v
98 passed, 1 skipped, 1 warning in 1.35s
```

### git status

```
$ git status --short
(clean)
```

---

## Live verification (hand to LEAD)

I could not run these — `OPENAI_API_KEY` is not in environment.

### Regression case (must SURVIVE): Le Safari

```bash
DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
python3 -c "
from generate_tour_text import generate_tour_text
result = generate_tour_text(
    'Old Nice restaurants',
    'restaurant',
    6,
    forced_stops=['Le Safari', 'Chez Palmyre', 'La Merenda', 'Acchiardo', 'Olive et Artichaut', 'Fenocchio']
)
# Le Safari MUST appear in the output — it is at 1 Cours Saleya, inside Vieux Nice.
"
```

### Guard-still-works case (must be REMOVED): Walden Pond for Robbins House

```bash
DISABLE_TOUR_CACHE=1 DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
python3 -c "
from generate_tour_text import generate_tour_text
result = generate_tour_text(
    'Robbins House, Concord, MA',
    'walking',
    4
)
# If 'Walden Pond' appears, it should be removed by SCOPE-CHECK (it is 2 miles away,
# clearly outside 'Robbins House grounds'). The scope-check should still fire for
# genuinely out-of-scope landmarks at high confidence.
"
```

---

## Limitations

- The fix relies on Phase 3A returning a correct address. If the LLM hallucinates an address (e.g. placing a restaurant in the wrong neighbourhood), the authoritative note would mislead the judge. This is a pre-existing data quality concern, not introduced by this change.
- `max_tokens=60` for the judge response is unchanged. With the longer prompt (address + authoritative note), the model has more input context but the same output budget. 60 tokens is sufficient for the short JSON response.
- The 4-stop museum bound test was SKIPPED (not failed) in test_local352 because the tour file doesn't exist in this worktree. This is a pre-existing condition.
- No container was rebuilt. No rows in `audio_tours` were modified.
