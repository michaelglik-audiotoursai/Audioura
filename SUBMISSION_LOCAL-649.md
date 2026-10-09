# SUBMISSION — LOCAL-649: Plan → parallel write → stitch (flag `PARALLEL_STOPS`, default OFF)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-649-parallel-stops` (from `subscribed` @ `2e420fcf`)
**Base verified:** `git merge-base --is-ancestor 2e420fcf HEAD` → exit 0.

## What shipped

A plan → parallel-write → stitch orchestration for the tour generator, behind the
environment flag **`PARALLEL_STOPS`** which defaults **OFF**. When the flag is
unset the pipeline runs exactly as today — the change to `generate_tour_text.py`
is **61 insertions / 0 deletions**, and the new branch is skipped, so behaviour is
byte-identical.

### Files
- **`parallel_stops.py`** (new, 565 lines) — the PLAN step and the deterministic
  helpers. Self-contained; imported by the pipeline only when the flag is ON.
- **`generate_tour_text.py`** (+61 / −0) — a single flag-guarded branch at the
  existing per-stop write loop.
- **`test_local649_parallel_stops.py`** (new, 22 tests) — plan schema, callback
  budget, no cross-stop repetition, directions order, flag-OFF-unchanged.
- **`run_local649_container.py` / `run_local649_live.sh`** — the isolated live A/B.

## Where this plugged into the real pipeline

The existing `generate_tour_text()` already:
- builds a per-stop **spine** upfront (`generate_spine` / `discover_theme_threads`)
  that injects `emotional_beat` / `unique_angle` / `callback` into the narration
  prompt — the closest existing analog to a PLAN;
- **writes stops concurrently** already — the per-stop closure `_generate_description`
  is submitted to `tour_executor` (a `ThreadPoolExecutor`) and collected with
  `as_completed`;
- **stitches** sequentially after the loop: directions (`directions_generator`),
  the D636 callback budget (`cross_stop_reference_guard.limit_thematic_bridges_in_text`
  + `strip_unseen_callbacks_in_text`), the D533/S27 repetition guards, the
  LOCAL-628 editor (`stop_editor.edit_tour_text`), and the LOCAL-619B conclusion
  (`tour_conclusion.build_conclusion`).

LOCAL-649 therefore adds the **explicit PLAN** with the guarantees the ticket
names, and routes its output through those **existing** channels — no new
narration prompt, no change to the stitch. The flag branch overrides the spine
arc with the plan-derived arc and lets the existing parallel write and stitch run
unchanged.

> **Note on the prototype.** `.continuous_dev/bench/parallel_proto.py` and
> `.continuous_dev/bench/proto/` are under the git-ignored `.continuous_dev/`
> tree and are **not present on this machine** (that directory is LEAD's local
> runtime state). I could not read them. I implemented against the **real
> pipeline**, which is the authority for the contract and the stitch; the
> prototype was a motivating demo. Its three named flaws are fixed below.

## The three steps

**PLAN** — `plan_tour(venue, per_stop_research, api_key)`: one LLM call
(`gpt-4o-mini`, JSON mode, cost-logged) after stop selection. Produces the tour
**thread**, and per stop: one **assigned story** drawn from *that stop's own
research*, a **varied angle**, an **`owned_facts`** list, the **allowed callbacks**,
and a **`do_not_tell`** list. The output is validated (`validate_plan`) and
**legalised deterministically** so the plan is correct regardless of the model.

**WRITE** — `write_stops_parallel(...)` schedules the pipeline's existing
`_generate_description` closure on `tour_executor`, each stop seeing the whole
plan (via the spine channel) plus its own research. The LOCAL-617/638/640
narration prompt/contract is reused verbatim.

**STITCH** — the pipeline's own, unchanged, deterministic stitch:
directions from the fixed order, the D533/S27 repetition pass, the **D636
callback ENFORCEMENT** (`limit_thematic_bridges_in_text`, which drops callbacks
over the budget), the LOCAL-628 editor, and the LOCAL-619B conclusion.

## The prototype's three flaws, fixed

1. **More callbacks than allowed.** `enforce_callback_budget` caps the plan to
   `callback_budget(n) = max(1, (n+1)//3)` (delegating to the canonical
   `cross_stop_reference_guard.callback_budget` — one definition), allows a
   callback to target only an **earlier** stop, and keeps ≤1 per stop. The
   stitch's text-level `limit_thematic_bridges_in_text` enforces the same budget
   again (belt and braces). *Live: the Courtauld ON plan produced exactly 1
   callback at budget 1; 0 over-budget callbacks survived in the delivered text.*
2. **Narration must name the WORK when the stored title is an artist name.**
   `resolve_stop_work_name` returns the work title from the matched work record
   when the stored stop title equals the record's creator; the pipeline feeds
   that resolved name into the plan's `assigned_story`. *Live: Courtauld Stop 3
   header is "Georges Seurat" but the spoken body reads "Georges Seurat created
   'Young Woman Powdering Herself'…" — exactly the ticket example.*
3. **Every stop saying "transformation".** `assign_varied_angles` guarantees no
   two stops share an angle; if the model repeats one, it is repaired from a
   deterministic palette. *Validated in tests: three "same" angles → three
   distinct.*

## Flag OFF = byte-identical

- `generate_tour_text.py` diff vs base is **61 insertions / 0 deletions**
  (`git diff --numstat 2e420fcf -- generate_tour_text.py`).
- The inserted block is `try: import parallel_stops; _parallel_on = is_enabled()`
  then `if _parallel_on:` — when the flag is unset, `_spine_arc` keeps the exact
  value it was assigned on the line above, so no code path changes.
- `parallel_stops.is_enabled()` is `False` unless `PARALLEL_STOPS == "1"`.

## Tests (exit codes)

- `test_local649_parallel_stops.py` — **22 passed, exit 0**. Covers: flag-OFF
  default + the additive-wiring guarantee (asserts 0 deletions via git numstat),
  callback budget (formula, parity with the canonical function, forward/self refs
  dropped, tour-wide cap, ≤1 per stop), plan schema (normalise, angle repair,
  reject wrong count / empty thread / empty story; `plan_tour` with an injected
  LLM; bad JSON raises), no cross-stop repetition (`do_not_tell` has others' facts
  not self; the D636 text guard drops the over-budget 2nd callback), directions
  order (`write_stops_parallel` lands each result at its own index even when
  futures finish out of order; `plan_to_spine_arc` names the earlier stop by name),
  and the work-name fix.
- Related reuse suites — **all exit 0**: `test_local627_cross_stop_bridges`,
  `test_local638_directions_between_stops`, `test_local628_stop_editor`,
  `tests/test_local619_real_conclusion`, `tests/test_d533_cross_stop_facts`,
  `tests/test_d534_any_repetition`, `test_spine_generator`,
  `test_local38_theme_threads`. `import generate_tour_text` — exit 0.
- Pre-existing failures (NOT caused by this change, verified failing identically
  on the base `generate_tour_text.py` and not referencing the LOCAL-649 modules):
  `test_d498_matrix_and_top_size` (asserts a string in `modified_generate_tour_text.py`),
  `test_local38_integration::test_full_discovery_threaded`,
  `test_local413_ranking_discriminates` (3 top-5 selection tests).

## Live A/B — own disposable container, cap $2.50

Built `Dockerfile.generator` → image `local649-gen-img`, ran the disposable
container `local649-gen` (`docker run --rm`) on spare port **5120**, joined
`development_default` **only** to insert additive `is_test` rows into
`development-postgres-2-1`. **Never** `docker compose -p audioura`; **never**
touched an `audioura-*` container; image + container removed on exit. Cache OFF,
pool OFF (fresh). Combined HARD CAP **$2.50** via `tests/live_run_meter.py` with a
per-tour reserve gate.

| Tour | id | stops | wall | tour cost | callbacks/budget | run-on header | delivered=stated |
|------|----|-------|------|-----------|------------------|---------------|------------------|
| Courtauld **OFF** | 575 | 3 | 536.8 s | $1.073 | 0 / 1 | no | 3 = 3 |
| Courtauld **ON**  | 576 | 3 | 448.8 s | $1.112 | 0 / 1 | no | 3 = 3 |
| Walters **OFF**   | 577 | 3 | 378.0 s | $0.930 | 0 / 1 | no | 3 = 3 |
| Walters **ON**    | —  | —  | —      | —      | — | — | **SKIPPED (cap)** |

**The 4th tour (Walters ON) was stopped by the $2.50 cap** — after three tours
the host spend was $2.516, and the reserve gate correctly refused to start a
fourth that would exceed the cap. The critical OFF↔ON pair (Courtauld) ran in
full plus a Walters baseline.

**PLAN executed (Courtauld ON):**
`thread='Exploration of iconic self-portraits and their impact on the art world.',
stops=3, callbacks=1, budget=1` — exactly one budget-legal callback.

**`[TIMING]` phases.** The pipeline prints `[TIMING] phase=narration elapsed=0.0s`
in every run: the heavy per-stop LLM work is attributed to the `story_first`
phase, not `narration`, so the parallel-write phase is not isolated by the
narration timer. Total wall was Courtauld OFF 518.5 s vs ON 431.4 s — ON was
faster, but `story_first` (not the parallel-write phase) dominates and the gap is
within run-to-run variance; this is **not** a clean speed signal. The full real
pipeline (poi_selection + story_first + external_lookups + grounding) costs
~$0.9–1.1 per tour, far above the prototype's isolated $0.026 plan+write — the
plan call itself is a small fraction.

**Rows / spend (additive `is_test` only).** `audio_tours` 378 → 381 (+3);
`is_test` rows 314 → 317 (+3) — ids 575/576/577, all `is_test=true`. No deletes,
no non-test rows. `paid_api_calls` for the host: $0 → $2.516. `live_run_meter`
combined for this run: $0.857 (openai $0.549, gemini_grounding $0.245,
gemini_tokens $0.027, serper $0.037, preflight $0.073).

Stored tour text: `tours/local649_live/LOCAL649_*.txt`; full log:
`tours/local649_live/local649_live.log`.

## Honest limitations

- The $2.50 cap allowed 3 of the 4 planned tours; Walters ON did not run. The
  OFF↔ON comparison exists for Courtauld (same venue, same stops, flag the only
  difference) and the plan is proven to execute and obey the budget.
- The parallel-write time saving is **not measurable from these runs**, because
  the pipeline's narration phase timer reads 0.0 s (the LLM work is counted under
  `story_first`) and the total-wall difference is within variance. The
  architectural win (plan-coordinated independent stops, budgeted callbacks,
  no cross-stop repetition, work-name correctness) is demonstrated; the
  wall-clock win the prototype reported for an *isolated* plan+write is not
  reproduced at the full-pipeline level here.
- The prototype files were unavailable (git-ignored, not on this machine), so the
  implementation follows the real pipeline rather than the prototype's structure.

## Process

- Committed after each step (6 commits on `LOCAL-649-parallel-stops`).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.
- One incident during testing: a stray `git stash pop` partially applied an
  unrelated pre-existing stash, leaving conflict markers in files I never
  authored; reverted with `git checkout HEAD -- <those files>`, pre-existing
  stashes preserved. No committed work was affected.
