# SUBMISSION_LOCAL-410.md

## Diagnosis

**The dropping hop: `generate_tour_text_service.py` → `generate_tour_text()`**

The four-step trace reveals a single, clear failure point:

1. **Queries issued**: `search_stories_for_stop` was **never called** from the real
   generation path. It only existed in acceptance test runners (`run_local402_acceptance.py`,
   `run_local409_acceptance.py`, etc.) which manually populated the module-level
   `_DIRECT_SNIPPETS_PER_STOP` dict before invoking `generate_tour_text()`.

2. **serp_results**: N/A — the call was never made on the real path.

3. **story_corpus / FACTS FIRST block**: The `_DIRECT_SNIPPETS_PER_STOP` dict started
   empty (line 1895: `_DIRECT_SNIPPETS_PER_STOP: dict = {}`) and was never populated
   by `generate_tour_async()`. The snippet injection code at line 8921 (`if
   _DIRECT_SNIPPETS_PER_STOP and poi_name:`) always found an empty dict, so the
   `[LOCAL-402]` snippet block was never appended to the prompt.

4. **Prompt slice**: "Picasso met Fernand Mourlot in October 1945" never appeared in the
   prompt because the snippet that contains it was never fetched on this code path.

**Why chain instrumentation didn't fire**: The `serp_results / elements_extracted /
beats_injected / beats_in_delivered_text` logging existed only in the acceptance runners.
`generate_tour_text.py` itself had no equivalent — there was nothing to "filter"; the
entire search phase simply did not exist on the real path.

## Fix

**Wire `search_stories_for_stop` into `generate_tour_text()` itself** (not just runners).

Location: After LOCAL-383 story beat extraction, before `_generate_description` is defined.

Conditions (guard):
- `STORIED_MODE=true`
- `tour_category == 'museum'`
- `_DIRECT_SNIPPETS_PER_STOP` is empty (don't override external population)
- `GENERATION_TIER != 'free'` (R6: free tier = zero SERP calls)

For each stop in `poi_list`:
- Build stop data dict from poi fields
- Call `search_stories_for_stop(stop_data, tour_type='contained', generation_tier=...)`
- Collect results into snippets
- Inject `credit_line` as a leading snippet (restores `Fridman`, `Broder`)
- Populate `_DIRECT_SNIPPETS_PER_STOP` with results
- Print chain instrumentation inline

Post-generation: print full chain log (`serp_results → snippets_injected → beats_in_delivered_text`).

Reset `_DIRECT_SNIPPETS_PER_STOP = {}` after return to prevent stale leaks.

## Files changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | Wire `search_stories_for_stop` into generation path; add chain instrumentation; add `global _DIRECT_SNIPPETS_PER_STOP` at function top; inject credit_line as snippet; reset after generation |
| `test_local410_serp_generation_wiring.py` | 5 unit tests guarding the wiring logic (red-on-revert count: 5) |
| `run_local410_acceptance.py` | Live acceptance test: generate → trace → verify |

## Red-on-revert count: 5

Reverting the LOCAL-410 change causes all 5 tests to fail:
- `test_generation_path_calls_search_stories_for_stop` — search call removed
- `test_serp_search_runs_when_snippets_empty` — guard condition removed
- `test_chain_instrumentation_fires_post_generation` — logging removed
- `test_snippets_reset_after_generation` — reset removed
- `test_credit_line_injected_as_snippet` — Fridman/Broder injection removed

Per D296: revert breaks the **logic** (search results never reach the prompt), not a symbol.

## Control (D302/D326)

Palais Lascaris / non-museum tours are unaffected:
- Guard condition `tour_category == 'museum'` prevents SERP calls on outdoor/distributed tours
- `_DIRECT_SNIPPETS_PER_STOP` starts empty and stays empty for non-museum tours
- No behavioral change for tours where `STORIED_MODE=false`
