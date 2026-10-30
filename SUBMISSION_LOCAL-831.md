# LOCAL-831 — The repeated-fact remover (D533) deletes a WHOLE stop, and the delivery check ships the gap (stops numbered 1, 2, 4, 5)

**Branch:** `LOCAL-831-derepetition-stop-loss`
**Base:** subscribed — `git merge-base --is-ancestor c5f3abbd HEAD` exits 0.

## The defect

Evidence — LOCAL-826C live run (Rijks Museum, cheap arm, real cache):
`~/Audioura/reports/local826c/gen_rijks_826c_live.log` (~line 1983) and
`tour866_826c_live_delivered.txt`.

A D533 guard logged `removed: Stop 3: Het melkmeisje (The Milkmaid)` — it deleted
a WHOLE stop block (header **and** body) while stripping a repeated fact — and the
tour shipped four stops numbered `[1, 2, 4, 5]`. LOCAL-826B's `check_stop_delivery`
DID report `NON_SEQUENTIAL`, but the gap still shipped.

## Two root causes (both found with the exact log strings)

1. **A whole stop was deleted.** The `removed: Stop 3:` line is emitted by
   `story_fact_guard.repair_role_mismatches` (also tagged `[D533]`). Its
   `split_sentences` does not break on a newline, so a stop body ending with no
   final period runs on into the next `Stop 3:` header and its `Address:` line.
   The Dutch postal code `1071 DJ Amsterdam` was then read as a
   `(person='DJ Amsterdam', year=1071)` pair, a birth-year/role "mismatch" was
   "found", and removing that span deleted the entire Stop 3 block.

2. **The delivery check could not repair the gap.** `check_stop_delivery` only
   *detects*. Its repair, LOCAL-801's `dedupe_and_fix_stop_count`, renumbers
   **only when it removed an artifact** (preview header / spliced body /
   duplicate / over-count trim). Here the stop was already gone — nothing was
   removed — so it hit the strict no-op branch (`renumbered: False`) and the
   `[1, 2, 4, 5]` gap shipped.

## The fix

### 1. D533 guards may remove repeated SENTENCES, never a header or a whole stop

* `derepetition_guard.strip_repeated_facts` — added `_STOP_HEADER_LINE` and
  `_body_sentence_count`. A removal candidate that contains a `Stop N:` header is
  refused, and a removal that would leave a stop body with **zero** narration
  sentences is refused (never empty a body). The floor is 1 (never empty), not 2,
  on purpose — documented in code — so the legitimate LOCAL-668 cross-stop
  near-duplicate strip (a two-sentence thin-museum body → one distinct sentence)
  still runs; all 25 existing derepetition tests pass.
* `story_fact_guard` — added `_HEADER_LINE` / `_FIELD_LINE` and `_narration_only()`.
  `find_role_mismatches` now splits **narration only** (headers and house field
  lines, including addresses, removed), so a postal code in an `Address:` line is
  never read as a person+year and a candidate can never span a header.
  `repair_role_mismatches` additionally refuses, at the point of mutation, to
  remove any span carrying a `Stop N:` header. The verbatim Gautier birth-year
  fabrication case (`tests/test_d533_fact_guard.py`) still flags and repairs.

### 2. A gap-closing renumber that works even when no artifact was removed

`tour_conclusion.renumber_stops_sequential` rewrites the surviving `Stop N:`
header numbers to `1..k` in document order — touching only the integer, titles
and bodies byte-for-byte preserved. Strict no-op (byte-identical) on a clean
tour; idempotent. `[1, 2, 4, 5] → [1, 2, 3, 4]`.

`repair_stop_delivery` / `finalize_stop_delivery` run `normalise_stop_headers` →
`renumber_stops_sequential` → re-check, log each repair action, and log
`[LOCAL-831] DELIVERY DEFECT <kind>` for any residual (e.g. an `EMPTY_BODY` the
renumber cannot invent a body for). The honest shortfall line keys on
`count_delivered_stops`, which now reflects the real delivered count.

### 3. The delivery check + repair is the LAST text transform before write/store — on every path

| Path | File:line | Placement |
|---|---|---|
| Fresh (museum / walking / places) | `generate_tour_text.py:~30510` | `finalize_stop_delivery(complete_tour, …)` immediately before the primary `open(output_file)` write (`~30545`), after the structured-render block, for **every** `tour_category`. |
| Fresh — museum belt-and-braces | `generate_tour_text.py:~30765` | the LOCAL-826B block now calls `finalize_stop_delivery` (replacing the LOCAL-801 dedupe that could not close the gap) and rewrites `output_file`. |
| Service delivery | `generate_tour_text_service.py:~977` | `finalize_stop_delivery(tour_text, …)` after the whole BLOCKER4c QA loop (whose LOCAL-722 corrective can DROP a stop) and before `shutil.copy2(temp_path, output_path)`; the repaired text is written back to `temp_path`. |
| Pool reuse | `stop_pool_orchestrator.py:_emit_result (~1407)` | `finalize_stop_delivery(result.tour_text, …)` before `_write` and `store_delivered_tour`; mutating `result.tour_text` so the pooled rows get the repaired text. Every pool delivery (first-tour, N≤K served-from-pool, N>K assemble) funnels through `_emit_result`. |

## Tests

`tests/test_local831_derepetition_stop_loss.py` — 12 tests, all pass:

* **D533 header-removal fixture** — header never a removal candidate; every header
  and the stop count preserved; refusal when a removal would empty a one-sentence
  body.
* **Non-sequential fixture** — `renumber_stops_sequential` closes `[1,2,4,5]` →
  `[1,2,3,4]` with no stop removed; strict byte-identical no-op on clean;
  idempotent; a title with a colon and a year is preserved.
* **Empty-body fixture** — the repair closes the numbering and the honest shortfall
  sentence is built from the REAL delivered count (4), not the requested 5; an
  `EMPTY_BODY` stop is surfaced as a residual `[LOCAL-831] DELIVERY DEFECT`.
* **Role-guard header safety** — the `1071 DJ Amsterdam` postal-code case never
  deletes a stop; a genuine birth-year fabrication in narration is still caught.

Regression sweep green: 66 tests across the D533/D534 derepetition suites, the
fact-guard suite, LOCAL-668/636/660, LOCAL-826B/C delivery, and the new suite; a
further 88 `tour_conclusion`-importing tests and 32 root-level tests — no
regressions.

## Live — BUDGET ENFORCED

`TASK_BUDGET_ID=LOCAL-831 TASK_BUDGET_USD=0.50`, meter contract, cheap arm
(`gpt-4.1-mini`), `DISABLE_STOP_POOL=1`, real cached rows seeded into a disposable
`local831-postgres`. One tour: "Rijks Museum, Amsterdam, Netherlands" (5).

Harness: `run_local831_live.sh` → `run_local831_container.py` (disposable
`local831-*` project, meter tagged `LOCAL-831`). The shared `audioura-*`
containers and the live DB were never touched; the disposable containers were
cleaned up on exit.

**Result (`~/Audioura/reports/local831/gen_rijks_831_live.log`, 1880 lines;
delivered tour `~/Audioura/reports/local831/tour_rijks_831_live_delivered.txt`):**

* requested 5, **delivered 5**, numbers `[1, 2, 3, 4, 5]` — sequential, no gap.
* The Milkmaid stop (Stop 3) is **no longer deleted**.
* each stop ≥ 2 complete sentences (13, 11, 8, 4, 14).
* `check_stop_delivery` → `[]`.
* `[D533] Person-year role guard: no mismatches` — the role guard no longer
  misfires on the postal code.
* `honest_count = True`.
* metered **$0.1664 / $0.50**.
* **=== LOCAL-831 OVERALL: PASS ===**

The first live run (before the `story_fact_guard` fix) independently proved the
delivery net: the role guard still deleted Stop 3, but the LOCAL-831 gap-closing
renumber shipped `[1, 2, 3, 4]` with `check_stop_delivery = []`. Defense in depth
holds even if a future upstream pass drops a stop.

## Files

Modified: `derepetition_guard.py`, `story_fact_guard.py`, `tour_conclusion.py`,
`generate_tour_text.py`, `generate_tour_text_service.py`,
`stop_pool_orchestrator.py`.
Added: `tests/test_local831_derepetition_stop_loss.py`,
`run_local831_container.py`, `run_local831_live.sh`, `SUBMISSION_LOCAL-831.md`.
