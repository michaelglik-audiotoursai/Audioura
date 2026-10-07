# SUBMISSION — LOCAL-613: Test runs must be metered and capped

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-613-meter-test-runs`
**Base:** `subscribed` @ `33606ec`

> Michael, 2026-10-07: *"How many tours did we run during testing to burn $14?"*

Gemini's prepaid balance went $14.06 (2026-10-06 ~17:00) → $0 (2026-10-07 00:28,
402) in ~11 hours. The shared `cost_ledger` for that window holds only **14
`tour_generate` rows from the live stack, $1.05 total** (confirmed below). The
other ~$13 was spent by ~20 Kiro tasks' **isolated live runs**
(`docker run --rm --name localNNN-gen …`) that wrote **no ledger rows** and left
**no Gemini totals** — so the spend was unreconstructable. LOCAL-613 makes those
runs meter and cap themselves.

---

## What shipped

### 1. Shared meter — `tests/live_run_meter.py`
Every isolated live-run harness (and every future one) uses `LiveRunMeter` to
write **one** `cost_ledger` row per run:

- `user_id = 'TEST-<LOCAL-NNN>'` (e.g. `TEST-LOCAL-603`)
- `description = 'test run'`
- `operation_type = 'tour_generate'`
- `breakdown` = the LOCAL-609 fields:
  - `openai` — OpenAI dollars
  - `gemini_grounding` — `{usd, requests, queries}` (the invoice unit is queries;
    requests kept for the per-stop cap)
  - `gemini_tokens` — ungrounded Gemini token dollars
  - `serper` — Serper search dollars
  - `preflight` — venue-preflight grounding dollars (a **labelled subset** of
    `gemini_grounding`, surfaced for visibility, **not** re-added to the total)

`our_cost_usd` reconciles exactly: `openai + gemini_grounding.usd + gemini_tokens
+ serper`. `record()` **never raises** on a DB error (the original bug was runs
that produced no row — a crash here would recreate it) and is idempotent.

Harnesses opt in with **one line** via `auto_meter("LOCAL-NNN")`, which installs
the cap immediately and registers an `atexit` hook that reads the last
generation's cost (`generate_tour_text._LAST_GENERATION_COST` + the live
`story_leads` grounding counters) and writes the row on exit — even if the cap or
an error stopped the run.

### 2. Hard per-task cap — `TEST_GEMINI_MAX_USD` (default **$1.00**), enforced by the grounding counter
`story_leads` gained `set_grounding_cap_callback()` / `TestRunCapExceeded`. The
installed guard is consulted at the two grounding-counter sites:
- **before** a grounded request is issued (`_count_grounding_request`), and
- **after** a response's queries are counted (`_count_grounding_queries`).

When the run's **combined** spend (openai + gemini grounding + gemini tokens +
serper) reaches the cap, the next grounded step **raises and the run stops**
before the query that would cross the line is issued. **A task file's own cap
applies to all providers combined.** The guard is **off by default** — ordinary
live/production generation never installs it, so there is no behaviour change on
the live stack.

### 3. `cost_report_window.py` — "where did the money go?" in one command
```
python3 cost_report_window.py --from <ts> --to <ts> [--json] [--db-url ...]
```
Reads `cost_ledger` over `[from, to)` and prints totals **by provider** and **by
user_id**, with live users and `TEST-*` isolated runs split into their own groups
with subtotals. Read-only — no DELETE, no mutation. Timestamps accept ISO 8601
(`2026-10-06T20:56Z`) or `YYYY-MM-DD HH:MM` (naive = UTC).

### 4. Tests — `tests/test_local613_meter_and_cap.py` (14 tests, all pass)
- **The cap raises at the threshold:** a $0.10 cap stops the run at 8 queries
  ($0.112) — the first point combined spend reaches the cap — and never below;
  the cap counts all providers combined; it is off by default.
- **The helper writes a row:** proven DB-less (captured `record_operation`
  asserts `user_id=TEST-LOCAL-613`, `description='test run'`, the five breakdown
  fields, correct `our_cost_usd`), idempotent, never raises on DB error; and
  against a **real throwaway-schema DB** (`IsolatedSchema`, skips if Postgres is
  down) that proves the row lands and **zero** rows escape to `public`.
- **The report groups correctly:** by provider and by user with subtotals,
  reconciliation, and timestamp parsing.

---

## Verification

```
$ python3 -m pytest tests/test_local613_meter_and_cap.py -q
14 passed in 0.18s

$ python3 -m pytest tests/test_local603_meter_and_l2.py tests/test_local594_grounding_cost.py -q
15 passed, 1 warning in 0.27s          # no regression from the cap hook
```

All 15 wired harnesses compile (`py_compile`), and the inserted block was
verified to install the `story_leads` cap callback and emit the
`description='test run'` summary at exit (recording gracefully logs — not crashes
— when the DB is unreachable from the host).

---

## 5. Window report (no live run required)

The ticket asks for the window **2026-10-06 20:56Z → 2026-10-07 04:29Z**, which
covers only what the ledger already holds — and it does **not** contain the
isolated test runs that burned the Gemini balance, because those runs wrote
nothing. That is precisely the gap this ticket closes going forward. Run against
the dev ledger (`audiotours`, read-only):

```
========================================================================
COST LEDGER WINDOW REPORT  (LOCAL-613)
window : 2026-10-06T20:56:00+00:00  ->  2026-10-07T04:29:00+00:00
rows   : 63
total  : $1.1848   (live $1.1848  |  test $0.0000)
========================================================================

BY PROVIDER
------------------------------------------------------------------------
  openai             $1.1777
  tts                $0.0071
  unattributed       $0.0071

BY USER  (LIVE users first, then TEST-* isolated runs)
------------------------------------------------------------------------
  LIVE
    USER-1073427300              $1.0746   (49 row(s))
    (none)                       $0.1102   (12 row(s))
    LOCAL597-c5169e3a6a          $0.0000   (1 row(s))
    LOCAL597-4bfb3227e1          $0.0000   (1 row(s))
    — live subtotal —            $1.1848
========================================================================
```

**Reading it:**
- The ledger accounts for only **$1.18** across the whole window — of which the
  `tour_generate` rows are **14 rows / $1.0518** (direct SQL below), matching the
  ticket's "14 tour_generate rows … $1.05". The rest is `spine_generate` ($0.12),
  `tts_generate` ($0.007) and one `translation_generate`.
- **`test $0.0000`** — not one dollar of the overnight burn is attributed to
  `TEST-*` isolated runs, because none existed. The ~$13 of Gemini that is missing
  from this report is exactly the spend that left no ledger rows. From now on each
  isolated run writes a `TEST-<LOCAL-NNN>` row and is capped, so the same question
  next time is answered by this one command.
- `LOCAL597-*` are device user_ids (live, $0 cache-ish rows), **not** `TEST-*`
  rows — the split groups them under LIVE correctly.

Corroborating SQL (same window):
```
operation_type        rows   sum($)
tour_generate         14     1.0518
spine_generate        13     0.1222
tts_generate          35     0.0071
translation_generate   1     0.0036
```

---

## Files
- `story_leads.py` — cap hook (`set_grounding_cap_callback`, `TestRunCapExceeded`,
  enforcement at the grounding counter). Off by default.
- `tests/live_run_meter.py` — shared `LiveRunMeter` + `auto_meter` + cap.
- `cost_report_window.py` — the window report CLI.
- `tests/test_local613_meter_and_cap.py` — the tests.
- 15 isolated harnesses wired to `auto_meter`: 583, 585, 587, 590, 592, 593,
  593b, 594, 599, 599b, 599c, 600, 602b, 603, 607.
- `_wire_meter_into_harnesses.py` — the one-off editor, kept for provenance.

**No DELETE. No GCloud.** DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE.md /
.continuous_dev/STATUS.md were not touched.
