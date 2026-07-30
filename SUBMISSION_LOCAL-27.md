##### READY FOR REVIEW

# LOCAL-27: Content Truthfulness — Sourced-or-Omit

## Summary of Changes

**Problem**: The `Museum Information`, `Type/Specialty`, and `Specific Examples` fields
were fabricated by GPT in Phase 3B. Three runs produced three different "facts" —
wrong closing day, wrong admission fee, contradicting type/period declarations.

**Fix**: For museum tours, these fields are now **sourced from verified data or omitted entirely**.

## Changes Made

### `generate_tour_text.py` (261 insertions, 12 deletions)

1. **Phase 3B prompt (museum tours)**: Removed `type_specialty`, `specific_examples`,
   and `operational_details` from the JSON schema requested from GPT. Non-museum tours
   retain the original prompt unchanged.

2. **Phase 3B merge logic**: For museum tours, these three fields are explicitly set
   to empty strings during the merge step — GPT cannot populate them even if it
   volunteers the data.

3. **Corpus-sourced `type_specialty`** (new block after Phase 3B): Uses
   `story_corpus_result.per_work_contexts` to find medium/technique mentions
   (e.g., "oil on canvas", "gouache", "mosaic") in corpus sentences about each work.
   Only populates the field if a match is found in sourced text.

4. **`_fetch_visitor_info_from_site()`** (new module-level function): Fetches the
   venue's official hours/tariffs page (tries known URL patterns like
   `/tarifs-et-horaires`, `/infos-pratiques`, `/plan-your-visit`, etc.).
   Extracts structured hours and admission data using regex patterns for French and
   English. Returns sourced text or empty string.

5. **Visitor info wiring**: After Phase 3B, if the official site yields visitor info,
   it populates `operational_details` on stop 1 only. If not found, all stops have
   `operational_details = ''` — the field is absent from output.

6. **`_check_type_prose_contradiction()`** (new module-level function, Phase 5.8):
   Checks that each stop's declared `type_specialty` period/era is consistent with
   its prose description. If "Contemporary art" appears on a stop whose prose
   repeatedly mentions the Tang Dynasty, the `type_specialty` is cleared.

### `test_local27_truthfulness.py` (new)

Regression test that verifies:
- Museum Information is sourced (has time/day/price patterns) or absent
- Type/Specialty doesn't contain known fabricated filler phrases
- No self-contradictions between declared type and prose
- Specific Examples doesn't contain generic filler
- Museum Information only appears on stop 1

## Scope Containment

- Changes are confined to `generate_tour_text.py` (the description/assembly path)
  and a new test file.
- `story_miner.py` is NOT modified (LOCAL-28 territory).
- Non-museum tours are completely unaffected — the `_is_museum_tour` flag gates
  all changes.
- All existing tests pass (23/23 palais fixture, all SQ3, SQ4, spine, W4, corpus filter).

## Evidence

### Unit test: self-contradiction checker
```
Test 1 (contradiction): 1 warning(s)
  Stop 'Test Work': type_specialty says 'contemporary art' but prose references ancient (2 mentions)
  PASS: type_specialty cleared
Test 2 (no contradiction): 0 warning(s)
  PASS: type_specialty preserved
Test 3 (empty type): 0 warning(s)
  PASS: empty type ignored
All unit tests PASS
```

### Existing test suite (verbatim exits)
```
test_palais_fix_lead_fixture.py: 23/23 assertions hold — All tests passed.
test_sq3_fixtures.py: ALL TESTS PASSED
test_sq4_merge.py: ALL TESTS PASSED
test_spine_generator.py: 18 PASS, 0 FAIL — ALL TESTS PASSED
test_w4_matcher.py: All W4 tests completed.
test_local24_corpus_filter.py: 21 PASS, 0 FAIL
```

### Pre-existing failures (not addressed per instructions)
```
test_attestation_log_only.py: 0 PASS, 4 FAIL (gateway not running — pre-existing)
test_contained_regression.py: REGRESSION DETECTED — exit 1 (service not running — pre-existing)
```

## How This Prevents the Bug

| Before | After |
|--------|-------|
| GPT invents "Open daily 10am-6pm, closed Mondays" | Field is blank (no visitor info page found) OR sourced from venue's official `/tarifs-et-horaires` page |
| GPT invents "Contemporary art" on a Tang Dynasty stop | `_check_type_prose_contradiction()` detects mismatch, clears the field |
| GPT invents "Modern artistic expressions in various forms" | Phase 3B no longer asks for this field; corpus derivation only populates if medium/technique found in sourced text |
| Three runs produce three different "Museum Information" values | Field is deterministic: either sourced from a static page (stable) or absent (stable) |

## Remaining Work for Live Verification

The live 8-stop regeneration in container (with `tour_cache` deletion, CACHE MISS,
3x stability check) requires a running Docker environment with API keys configured.
This is documented as acceptance evidence in the task but requires container execution
that this agent cannot perform in the current worktree-only context.
