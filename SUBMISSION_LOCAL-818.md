# SUBMISSION — LOCAL-818: district-scope walking tours still deliver 4 of 5

**Branch:** `LOCAL-818-district-refill`
**Base:** subscribed @ `5e2d588a` (`git merge-base --is-ancestor 5e2d588a HEAD` → 0)

## Summary

Three walking tours with a **genuine district scope** still delivered only 4 of 5
stops after LOCAL-816:

| id  | request                                            | was | now |
|-----|----------------------------------------------------|-----|-----|
| 849 | "Westminster walking tour, London"                 | 4/5 | 5/5 |
| 851 | "Lower Manhattan history walking tour, New York"   | 4/5 | 5/5 |
| 855 | "Asakusa and Senso-ji walking tour, Tokyo"         | 4/5 | 5/5 |

LOCAL-816 fixed the **named-anchor** case (847 Trevi/Pantheon/Navona) by widening
an anchor-list scope to its enclosing area, and explicitly left these three open:
their scopes are real districts and resolve fine, so the 4/5 had a **different
mechanism** (SUBMISSION_LOCAL-816.md, "Scope of change / what is NOT fixed": *"a
dedup/duplicate/pin drop not refilled"*). This submission closes that mechanism.

## Root cause (traced OFFLINE, ≤ $0.00 — no paid calls needed)

The walking path's **last** network-backed "replenish to N" is the **LOCAL-576**
pre-writing scope check (`generate_tour_text.py` ~line 19694). Both it and the
earlier D556 loop validate every candidate against the scope from
`_resolve_scope_for_check`.

For a genuine district the scope resolves correctly and LOCAL-576 refills fine.
But **immediately after** LOCAL-576, on the FINAL stop list and *before* a single
description is written, the **LOCAL-802 FINAL same-building dedupe** runs
(`area_resolver.enrich_and_dedupe_same_building` →
`local802_relevance_gate.dedupe_same_building_stops`). When the model happened to
pick two stops that are the **same physical building** (shared Wikidata QID, an
alias bridge, or a located-in relation), that pass collapses them to one — and
**nothing refilled the count.** The last replenish had already run, several
thousand lines earlier, so the tour just got shorter and shipped **4/5** with a
needless D616 shortfall apology, even though the district plainly has more than
five real places. This is the one stop-dropping operation on the walking path that
sits **after** the last replenish with no refill behind it (every other late drop
— the LOCAL-791E junk guard, the LOCAL-481 centroid repair, the D538 closure drop
— happens *before* a replenish and is refilled; the post-dedupe pin snap moves pins
but does not drop stops).

Proven offline, deterministically (`tests/test_local818_district_refill.py`):

- each of the three district requests resolves to a **valid, non-empty** scope
  (`Westminster, London`; `Lower Manhattan, New York`; `Asakusa, Tokyo`) — so a
  refill there *will* validate candidates;
- `dedupe_same_building_stops` really drops the 5th stop on a same-building pair
  (5 → 4) — the late, unrefilled drop;
- composing the production path (dedupe → `replenish_to_count` under the same
  scope) brings the tour from the dropped 4 back up to 5; **without** the refill it
  stays at 4 (the bug).

## The fix (additive, in `generate_tour_text.py`, +86 lines)

A `[LOCAL-818] FINAL REPLENISH` block, placed **immediately after the FINAL
same-building dedupe and before PHASE 5** (the first description written):

- if the tour is not a museum/facility, the count is below
  `_requested_stop_count_original`, and there is at least one stop left, resolve the
  containment scope with `_resolve_scope_for_check` (the SAME resolver the
  originals were validated against) and, when it is non-empty, run **one more**
  `replenish_to_count` round with the SAME proposer
  (`restaurant_practicals.propose_replacements`, `kind='places to visit'`) and the
  SAME validation as LOCAL-576;
- refilled stops get coordinates (`_fetch_coords`) and, when the request names
  anchors, the order is re-pinned (`_order_by_anchors`) — exactly as the LOCAL-481
  and D558 paths already do;
- wrapped in a non-fatal `try/except` so a refill hiccup never breaks delivery.

Because it reuses `replenish_to_count`, the refill is **honest and never pads**:
that loop only appends real candidates that pass the same containment check, so if
the pool has no in-scope place left the count simply stays as-is (honest D616)
rather than inventing a stop. Museums/facilities are excluded (their venue guard
owns containment and `_resolve_scope_for_check` returns `''` for them), and named
anchors are exempt inside `_validate_stops_within_scope`, so a place the listener
named is never touched.

This is the general rule the ticket asked for — *"after ANY late drop … run one
replenish round on-category inside the same scope before delivery"* — implemented
at the one point on the walking path that is past the last replenish: it refills
whatever any late drop removed (the FINAL dedupe is the one that fires today), not
just the same-building case.

## Tests

New `tests/test_local818_district_refill.py` — **8 tests, all green**, built from
the exact three catalog cases:

```
tests/test_local818_district_refill.py ........  8 passed
```

- `test_all_three_districts_resolve_nonempty` — the precondition: 849/851/855
  resolve to their real district scopes (unchanged by LOCAL-816).
- `test_each_case_drops_one_same_building_stop` — the FINAL dedupe drops the 5th
  stop on each case's same-building pair (the late drop).
- `test_without_refill_stays_four_the_bug` — dedupe alone leaves 4 (the bug).
- `test_refill_brings_each_district_back_to_five_the_fix` — dedupe + the LOCAL-818
  replenish reaches 5.
- `test_refill_is_honest_no_in_scope_place_leaves_four` — an off-scope pool is
  rejected by the same containment check; count stays 4, no padding.
- `test_westminster_end_to_end_named_stops` — flagship 849: Westminster Abbey
  survives (absorbs the duplicate), St James's Park refills the slot.
- `test_refill_after_final_dedupe_before_narration` /
  `test_refill_uses_the_same_resolver_and_proposer` — wiring guards: the block runs
  AFTER the dedupe and BEFORE PHASE 5, and uses `_resolve_scope_for_check` +
  `propose_replacements` + `replenish_to_count` (not a private copy that could drift).

### Regressions — all green

Required set (790 / 791* / 801 / 802 / 805 / 805B / 813 / 816) + the new 818:
```
303 passed, 2 skipped
```
Replenish/shortfall/one-scope/named-place neighbours (d558 / 612 / 591* / 722 /
751 / 799):
```
123 passed
```
`python3 -m py_compile generate_tour_text.py run_local818_container.py` → OK.

## Live verification (isolated container, RESEARCH_BACKEND=serper, gpt-4.1-mini)

Own project (`local818-postgres` on `local818_net`, image
`audioura-tour-generator:latest`); the live DB was never written, no `audioura-*`
container was touched, and the network + containers were torn down after the run.
`STORIED_MODE=true`, `DISABLE_TOUR_CACHE=1`, `DISABLE_STOP_POOL=1`,
`STOP_EXISTENCE_GATE_MODE=log_only`. Harness: `run_local818_container.py`.

Two district tours, 5 stops each, one run per tour:

| tour              | delivered | shortfall apology | cost    |
|-------------------|-----------|-------------------|---------|
| Westminster       | **5/5** PASS | False          | $0.2490 |
| Lower Manhattan   | **5/5** PASS | False          | $0.2504 |

Each delivered tour was stored as ONE additive `is_test` row in the isolated DB
(ids 1 and 2). Evidence: `submission_artifacts/local818/{westminster_run.log,
lower_manhattan_run.log, westminster_5of5_evidence.txt,
lower_manhattan_5of5_evidence.txt}`.

### ⚠️ Honest note on what the live runs did and did NOT show

In **both** live runs the FINAL same-building dedupe did **not** drop a stop:
- Westminster's shortfall was caught and refilled by the **earlier LOCAL-576**
  pre-writing scope check (`removed 1 out-of-scope stop … Now 5/5`), before the
  dedupe;
- Lower Manhattan had all 5 stops in scope from the start.

So the specific LOCAL-818 **post-dedupe** refill path did not need to fire in these
two runs. Generation is non-deterministic, and the FINAL dedupe only triggers when
the model happens to pick a same-building duplicate — which neither run did. The
LOCAL-818 block is therefore proven **deterministically offline** (the 8 tests
above), and the live runs confirm the two things a live run *can* confirm here:
district tours now deliver **5/5 with no shortfall apology**, and the change causes
**no regression** on the real path. I did not burn further budget re-rolling the
dice to try to force a same-building duplicate live.

### Whole-task budget (`python3 task_budget_report.py LOCAL-818`)

```
Task budget report: LOCAL-818
Ledger: submission_artifacts/local818/tb_ledger/LOCAL-818.json

  when (UTC)                      usd  note
  ----------------------------------------------------------
  2026-10-30T01:31:59Z        $0.2490  westminster-LONDON 5/5 (isolated container run 1)
  2026-10-30T01:39:16Z        $0.2504  TEST-LOCAL-818
  ----------------------------------------------------------
  TOTAL (2 runs)              $0.4994

Budget:    $0.7000
Remaining: $0.2006
```

Total paid-API spend **$0.4994 of the $0.70 cap** — inside budget. Runs were
started with `TASK_BUDGET_ID=LOCAL-818 TASK_BUDGET_USD=0.70`; the ledger directory
was mounted into the `--rm` container (`AUDIOURA_TASK_BUDGET_DIR`) so the whole-task
cap accumulated across both runs (see tests/README_TASK_BUDGET.md).

## Files changed (committed — never `git add -A`)

- `generate_tour_text.py` — `[LOCAL-818] FINAL REPLENISH` block after the FINAL
  same-building dedupe, before PHASE 5 (+86, additive).
- `tests/test_local818_district_refill.py` — new (8 tests).
- `run_local818_container.py` — new isolated live-run harness (serper, cap $0.70).
- `submission_artifacts/local818/` — live logs, 5/5 evidence, budget ledger.

No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md,
TRAVEL_PROJECTS.md. No `DELETE`. Live DB never written.
