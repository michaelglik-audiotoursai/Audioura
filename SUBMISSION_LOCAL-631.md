# SUBMISSION — LOCAL-631

**Concurrency: two tours generated at once must never share facts.**

- **Branch:** `LOCAL-631-concurrency-isolation`
- **Base:** `subscribed` @ `2e79f7f` (verified `git merge-base --is-ancestor 2e79f7f HEAD` → exit 0)
- **Agent:** Mac Mini Kiro
- Did **not** edit `practical_facts_gate.py` (LOCAL-630) or the selection modules (LOCAL-632).
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, `.continuous_dev/STATUS.md`.

---

## 1. Root cause

`generate_tour_text_service.py` runs **each generation job in its own
`threading.Thread`** inside ONE process (`threading.Thread(target=generate_tour_async)`,
service line ~1107). Several modules carried **per-job results in plain module-level
globals** that the engine wrote *during* a run and the service read back *after*
`generate_tour_text()` returned.

A module global is **one object shared by every thread in the process**. Two tours
generated at the same moment therefore overwrote each other's holders — whichever
job wrote last won, and the other job read the winner's facts. That is exactly the
bench-R0 symptom: the **Musée Rodin (tour 498) spoke the Rijksmuseum's (tour 499)
hours and admission** ("Open daily … 9:00 AM to 5:00 PM. Adult admission is €25;
entry is free…"), while Rodin's own preflight log said `venue='Musée Rodin' … hours=y`.

The cost accumulator (`cost_accumulator.py`) and the dead-host breaker
(`dead_host_breaker.py`) had already solved the identical problem per tour with
`contextvars`; this ticket generalises that pattern to the remaining holders.

---

## 2. Audit — every module-level mutable a job writes during generation

`file:line` of the shared, per-job-in-meaning state (as it was before the fix):

### `content_qa_runner.py` — written in `run_qa()`, read back by the service
| name | line | how it raced |
|---|---|---|
| `PASS_COUNT` | 33 | `global` write in `check()` |
| `FAIL_COUNT` | 34 | `global` write in `check()`; service reads `content_qa_runner.FAIL_COUNT` |
| `FACTUAL_FAIL_COUNT` | 35 | `global`; service reads it to gate release (svc ~690/694) |
| `G4_UNGROUNDED_SENTENCES` | 125 | `global`; service reads it for the G4 corrective pass (svc ~695–697) |
| `run_qa._story_elements_override` | (func attr, 163) | process-shared function attribute set at the top of `run_qa` and read lower down — one job's story elements could be read by another |

### `generate_tour_text.py` — "populated after generation so the service can read it", all raced
`_LAST_CLEAN_FAIL_EVIDENCE` (4214), `_LAST_TOUR_KIND` (4224), `_LAST_DELIVERY_PATH` (4230),
`_LAST_TOUR_SUGGESTION` (4234), `_LAST_OVERVIEW_SOURCES` (4238), `_LAST_POI_LIST` (4241),
`_LAST_VERIFICATION_TIER` (4244), `_LAST_GENERATION_COST` (4425), `_LAST_SITE_FIRST_SOURCES` (4431),
`_LAST_SITE_FIRST_COUNTS` (4442), `_SUPPRESS_INLINE_SHORTFALL` (4454), `_LAST_SCORE_RECORD` (4461),
`_LAST_STOP_COUNT_NOTICE` (4471), `_LAST_VENUE_PREFLIGHT` (4479) **(the preflight result holder — the hours/admission that bled)**, `_LAST_PREFLIGHT_COST` (4488), `_DIRECT_SNIPPETS_PER_STOP` (4732).

The service reads these back via cross-module attribute access across ~40 sites
(`generate_tour_text._LAST_*`, svc lines 248–922).

### `story_leads.py` — per-job grounding counters feeding the cost ledger
| name | line |
|---|---|
| `_GROUNDING_REQUESTS` | 109 |
| `_GROUNDING_QUERIES` | 110 |

`generate_tour_text` resets these at the start of a generation and reads them at the
end (they feed the cache-path `_LAST_GENERATION_COST` grounding line).

### Already correct (left unchanged)
- `cost_accumulator.py` — `CostAccumulator` is already scoped per tour via a
  `contextvars.ContextVar` + `tour_scope()`, with executor-context propagation into
  worker threads. **Cost accumulation stays per-job** (verified by the live run: the
  two concurrent tours reported independent totals $0.3606 and $0.4529).
- `dead_host_breaker.py` — per-tour cold-host set via `tour_scope()`.

---

## 3. Fix — per-job state via `contextvars`

New module **`job_scoped_state.py`**. It backs a set of module-level names with a
single `contextvars.ContextVar` holding a per-context `{name: value}` dict, exposed
through a `JobScopedNamespace` object (`_J`). Because the service starts each job as
a **fresh `threading.Thread`**, that thread runs with a context in which the
ContextVar holds its **default** — a thread never sees another thread's `set()`.
So every job thread gets its own values and can never observe another job's.

`attach_to_module(name, {name: factory})`:
1. removes the plain module global for each name (so stale shared values can't be
   resurrected and so PEP 562 `__getattr__` is consulted for cross-module reads);
2. installs a module `__getattr__` that resolves `module.NAME` reads to the current
   job's value — **the service and test-runner reads need no change**;
3. reclasses the module to a `ModuleType` subclass whose `__setattr__` routes
   cross-module **writes** (`generate_tour_text._DIRECT_SNIPPETS_PER_STOP = …` in the
   acceptance runners, `gtt._SUPPRESS_INLINE_SHORTFALL = True` in
   `stop_pool_orchestrator.py`) into the same per-job scope.

Within each owning module, engine code uses `_J.NAME` for reads, writes **and
in-place mutation** (`_J._DIRECT_SNIPPETS_PER_STOP.setdefault(...)`,
`_J._LAST_CLEAN_FAIL_EVIDENCE.update(...)`), so the racy `global NAME` statements
are gone (a `global` write would bypass any proxy and hit the shared `__dict__`).

Wired modules:
- **`content_qa_runner.py`** — `PASS_COUNT`, `FAIL_COUNT`, `FACTUAL_FAIL_COUNT`,
  `G4_UNGROUNDED_SENTENCES` are now job-scoped; the racy
  `run_qa._story_elements_override` function attribute was removed and the
  `story_elements` **parameter** is read directly instead.
- **`story_leads.py`** — `_GROUNDING_REQUESTS`, `_GROUNDING_QUERIES` job-scoped;
  `reset_grounding_requests()`/`get_*()` keep their signatures.
- **`generate_tour_text.py`** — all 16 holders job-scoped (16 `global` declarations
  removed, 16 module-level definitions replaced by one `attach_to_module(...)` call,
  133 internal references converted to `_J.*`).

Why `contextvars` and not `threading.local`: a `global NAME = v` writes to the shared
module `__dict__` regardless of thread, so thread-local storage alone would not help
without redirecting the name's storage; `contextvars` also matches the pattern the
cost accumulator already relies on and inherits correctly into pooled worker threads.

---

## 4. Offline concurrency test

`test_local631_concurrency_isolation.py` — runs 2 and 3 `generate_tour_text`-level
jobs concurrently in threads for distinct venues (Rodin / Rijksmuseum / Orsay) with
offline stubs, forces the writes to interleave with a `Barrier` + sleep, then reads
the holders back **through the service's cross-module attribute interface** and
asserts no venue's hours, admission, stops, QA/G4 state or grounding counts appear
in another's. A `test_control_shared_global_would_bleed` case proves a plain module
global DOES bleed, so the suite is not vacuous.

**Proof it detects the bug:** the test was run against the pre-fix
`generate_tour_text.py` (restored from backup) → **FAILED (2 failures)**; against the
fix → **3 passed**.

```
Ran 3 tests in 0.5s — OK
```

---

## 5. Live test — Rodin + Rijksmuseum generated AT THE SAME TIME

Own disposable container, built from this branch and removed at the end — never a
`docker compose -p audioura`, never renaming/replacing an `audioura-*` container:

- image `local631-gen-img`, container `local631-gen` (`docker run --rm`), network
  `development_default`, DB `development-postgres-2-1`.
- `run_local631_container.py` launches both venues on **two threads released together
  by a `Barrier`** — true simultaneous generation in one process.
- `DISABLE_TOUR_CACHE=1`, `DISABLE_STOP_POOL=1` (cache + pool OFF, fresh), 2 stops each.
- **HARD CAP $1.20 combined**, enforced by the reserve gate
  (`spend_so_far + reserve ≤ cap`, read from `paid_api_calls` for this host) and the
  `live_run_meter` all-providers cap.

### Each tour spoke its OWN venue's practical facts

**Musée Rodin** (`audio_tours` id **501**, $0.3606):
> The museum is open **Tuesday to Sunday, from 10:00 a.m. to 6:30 p.m.** (last admission at 5:45 p.m.; closed Mondays, …). admission is **Standard general admission is €14** at the desk (€15 online …). Admission is free for visitors under 18, EU/EEA residents aged 18–25, …

**Rijksmuseum** (`audio_tours` id **502**, $0.4529):
> The museum is open **Open daily from 9:00 AM to 5:00 PM** (the on-site shop and café remain open until 6:00 PM). admission is **Adults: €25**; Youth (ages 18 and under): Free; …

### Cross-contamination check — PASS
Programmatic assertion in the runner **and** direct `grep` on the delivered texts:
- Rodin tour contains **0** occurrences of `€25` or `9:00 AM to 5:00 PM` (the exact
  Rijksmuseum facts that bled into Rodin in bench R0).
- Rijksmuseum tour contains **0** occurrences of `€14` or `Tuesday to Sunday`.

```
================= CROSS-CONTAMINATION CHECK =================
  PASS: no venue's hours/admission appear in the other's tour.
```

### Cost + rows
- Combined spend **$0.9277 < $1.20** cap; reserve gate honoured.
- `audio_tours` row count **BEFORE = 306**, **AFTER = 308** — exactly **+2 additive
  `is_test` rows** (ids 501, 502). **No DELETE.**

Full log + both delivered tour texts committed under `submission_artifacts/`
(`local631_live.log`, `LOCAL631_RODIN.txt`, `LOCAL631_RIJKS.txt`).

---

## 6. Required test suites — exit codes

All run with `pytest 8.4.2`, Python 3.9. (Only warning is the pre-existing urllib3
LibreSSL notice.)

| suite | result | exit |
|---|---|---|
| `tests/test_local60*` `tests/test_local61*` `tests/test_local62*` | 378 passed | **0** |
| `test_local62*` (top-level) | 160 passed | **0** |
| `test_local590_*` (top-level) | 42 passed | **0** |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | **0** |
| `test_local60*` `test_local61*` (top-level, bonus) | 118 passed | **0** |
| `test_local631_concurrency_isolation.py` (new) | 3 passed | **0** |

---

## 7. Files changed

| file | change |
|---|---|
| `job_scoped_state.py` | **new** — per-job contextvars scoping infrastructure |
| `content_qa_runner.py` | QA counters + G4 job-scoped; removed racy `_story_elements_override` |
| `story_leads.py` | grounding counters job-scoped |
| `generate_tour_text.py` | 16 `_LAST_*`/`_DIRECT_*`/`_SUPPRESS_*` holders job-scoped |
| `test_local631_concurrency_isolation.py` | **new** — offline concurrency regression test |
| `run_local631_container.py` | **new** — concurrent live runner |
| `run_local631_live.sh` | **new** — disposable-container driver |
| `submission_artifacts/` | live log + delivered Rodin/Rijksmuseum texts |
