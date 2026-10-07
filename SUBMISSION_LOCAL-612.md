# SUBMISSION — LOCAL-612: the honest shortfall sentence (D616) on EVERY tour type

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-612-shortfall-everywhere`
**Base:** `subscribed` @ `33606ec` (verified `git merge-base --is-ancestor 33606ec HEAD` → exit 0)

---

## Problem

D616's honest sentence — *"…so this tour has X stops rather than the Y you asked
for"* — was only emitted on the **site-first / exhibition museum** path (LOCAL-600:
the stop-pool orchestrator's site-first branch and the museum-overview path).

Field cases:
- **Vietnam National Museum of Fine Arts** (tour 402): delivered **4 of 5**, no word.
- **Harvard** (tour 400): delivered **6 of 7**, no word.

Both are *verified-works* museums whose stops flow through the **main delivery
loop** in `generate_tour_text.py` (source `checklist`/`partial`), **not** the
site-first path — so no shortfall sentence was ever built. The same silence hit
every **walking / biking / driving / by-reference** tour that fell short of the
requested count.

## Fix (summary)

1. **One builder, widened — never a second.**
   `about_museum_stop.build_shortfall_sentence(...)` gains a `mode` parameter:
   - `mode="museum"` (default) — the exact D616 exhibition phrasing, **byte-identical**
     to LOCAL-600 (`"<Museum> currently has 3 exhibitions on view, so this tour has
     5 stops rather than the 7 you asked for."`). Existing callers are unchanged.
   - `mode="outdoor"` — the route phrasing, **no museum vocabulary**:
     `"We could confirm 4 stops along this route, so this tour has 4 stops rather
     than the 5 you asked for."`
   The shortfall tail (`"…so this tour has X stops rather than the Y you asked for."`)
   is identical on every path. Returns `""` whenever the ask was met (delivered ≥
   requested — D611 exact-N) or the counts are not positive.

2. **Wired into the non-pool main delivery loop** (`generate_tour_text.py`).
   The listener's original ask (`_requested_stop_count_original`, captured before any
   gate) versus the delivered count (`len(poi_list)`) is the universal chokepoint —
   the same truth the D536/D530 blocks already compute. When delivered < requested,
   one sentence is built from those real counts and **leads Stop 1's opening
   section** (injected into the `Orientation:`-prefixed opening, before the prolog, at
   `i == 0`). Museum/facility tours use `mode="museum"` (venue named, delivered works
   as the count); all other types use `mode="outdoor"`.

3. **Wired into the outdoor stop-pool reuse path.**
   `stop_pool_assembly.assemble_outdoor_tour(...)` gains a `shortfall_sentence`
   parameter and places it on the first walked stop's `_opening_section`, so
   `_render_stop_block` renders it before the Orientation line (the identical
   mechanism the museum opening section already uses). The orchestrator computes the
   outdoor shortfall for its `N > K` outdoor branch and passes it in.

4. **Exactly once — no double-emission.**
   The orchestrator runs the main loop as a *nested* generation for contained
   venues, then re-assembles and folds the shortfall into Stop 1 itself. A dedicated
   module flag `generate_tour_text._SUPPRESS_INLINE_SHORTFALL`, set by the
   orchestrator's `_suppress_inline_shortfall()` context manager around **both**
   nested `generate_fn` calls, keeps the main loop silent during those runs. The main
   loop also skips the site-first source (`_exhibition_stops_source == 'site_exhibition'`),
   which the orchestrator/overview already own.
   `DISABLE_STOP_POOL` was deliberately **not** reused as the discriminator — live
   runners set it for legitimate direct runs.

## Count correctness (deliverable 2) — verified, no change needed

- **Tour row `stops_count`** = `ACTIVE_JOBS[job_id]["actual_stops"]`
  = `len(audio_files_in_zip)` (files matching `audio_\d+\.mp3`), i.e. **one audio file
  per delivered stop** → `stops_count == delivered`.
  (`tour_orchestrator_service.py:1320, 1327, 1502`.)
- **App shown count** (`audio_tour_app/lib/screens/home_screen.dart`): the list card
  shows the backend row's `stops_count` (line 872); on save/listen it uses
  `backendStopsCount = resolutionData['stops_count']` when `> 0` (line 1641/1759),
  else `_countTourStops(zipBytes)`, which counts `tour.json` stops / `.mp3` files
  (line 3568+). **Both equal the delivered number.**

The count is correctly the **delivered** number (the D536 / LOCAL-394 invariant); the
D616 sentence is what explains *why* delivered < requested. A regression-pin test
locks the backend derivation.

## Files changed

| File | Change |
|------|--------|
| `about_museum_stop.py` | `build_shortfall_sentence(..., mode="museum"\|"outdoor")`; museum default unchanged |
| `generate_tour_text.py` | `_SUPPRESS_INLINE_SHORTFALL` flag; compute `_inline_shortfall` once from `_requested_stop_count_original` vs `len(poi_list)`; lead Stop 1 with it |
| `stop_pool_orchestrator.py` | `_suppress_inline_shortfall()` context manager around both nested `generate_fn` calls; outdoor shortfall for the `N>K` outdoor branch |
| `stop_pool_assembly.py` | `assemble_outdoor_tour(..., shortfall_sentence="")` → Stop 1 `_opening_section` |
| `tests/test_local612_shortfall_everywhere.py` | new per-path suite (21 tests) |

## Tests

### New per-path suite — present at 4/5, absent at 5/5, appears once
`tests/test_local612_shortfall_everywhere.py` — **21 passed**. Covers:
- builder outdoor mode: present 4/5, absent 5/5, singular grammar, no museum
  vocabulary, museum default byte-identical, explicit `mode="museum"` == default;
- outdoor assembly path: sentence appears **once** in Stop 1, before `Orientation:`,
  absent when the ask is met;
- museum opening-section path: once, after the About story, absent at 5/5;
- `stops_count == delivered` source-pin (`actual_stops = len(audio_files_in_zip)`);
- wiring in the engine, orchestrator and assembler; single-builder-only guard.

### Required suites (exits captured)

| Suite | Result | Exit |
|-------|--------|------|
| `tests/test_local60*` (pytest) | 147 passed | **0** |
| `test_local590_assembly.py test_local590_orchestrator.py test_local590_pool_store.py` (pytest) | 42 passed | **0** |
| `test_local592_about_in_stop1.py test_local592_r4_dayrange_spoken.py` (pytest) | 51 passed | **0** |
| `test_sq4_merge.py` (pytest) | *no tests collected — script-style* | 5 |
| `test_sq4_merge.py` (direct: `python3 test_sq4_merge.py`) | **ALL TESTS PASSED** | **0** |

> `test_sq4_merge.py` is a script-style test (`run_tests()` + `if __name__ == "__main__"`),
> so pytest collects 0 items (exit 5, "no tests ran"); run directly it passes with
> exit 0.

Raw output:

```
$ python3 -m pytest tests/test_local60* -q
147 passed, 1 warning in 6.67s          # exit 0

$ python3 -m pytest test_local590_assembly.py test_local590_orchestrator.py test_local590_pool_store.py -q
42 passed, 1 warning in 13.54s          # exit 0

$ python3 -m pytest test_local592_about_in_stop1.py test_local592_r4_dayrange_spoken.py -q
51 passed in 0.35s                      # exit 0

$ python3 -m pytest test_sq4_merge.py -q
no tests ran in 0.11s                    # exit 5 (script-style; not pytest-discoverable)

$ python3 test_sq4_merge.py
...
ALL TESTS PASSED                         # exit 0

$ python3 -m pytest tests/test_local612_shortfall_everywhere.py -q
21 passed                                # exit 0
```

## Live run

None. The logic is deterministic (pure builder + text assembly, no LLM in the
shortfall path), verified offline by the suites above. **No DELETE. No GCloud.**

## Process

- Branch `LOCAL-612-shortfall-everywhere` created from HEAD (`subscribed` @ `33606ec`);
  ancestry re-verified before committing.
- A commit after each step (see `git log origin/subscribed..HEAD`).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
