# SUBMISSION — LOCAL-848: Museum tours exceed 512 MiB in the generator (Cloud Run OOM)

**Branch:** `LOCAL-848-generator-memory`
**Base:** subscribed (`e042aa56`; `git merge-base --is-ancestor e042aa56 HEAD` exits 0)
**Budget:** `TASK_BUDGET_ID=LOCAL-848 TASK_BUDGET_USD=0.60`, meter contract honoured on every live run.

---

## TL;DR

The tour generator is a **warm, long‑lived Cloud Run container**. Each museum
request allocates large transient buffers (SPARQL JSON, Serper snippets,
per‑work Wikipedia extracts, LLM response strings). Python frees them, but
**glibc keeps the freed memory in its per‑thread arenas instead of returning it
to the OS** — so RSS only ever climbs, phase after phase and request after
request, until the 512 MiB cgroup OOM killer fires mid‑tour (the evidence:
`531 MiB used`, gens `00023-9zz` / `00016-62s`).

The fix returns that memory to the OS and caps glibc's arena sprawl, **without
changing a single byte of generated output**:

1. `mem_guard.release_memory()` = `gc.collect()` + `malloc_trim(0)` — run at
   every phase boundary and after every request.
2. `MALLOC_ARENA_MAX=2` in `Dockerfile.generator` — caps the thread‑pool arena
   explosion in the `story_first` phase (the dominant lever).
3. A cheap, always‑on per‑phase RSS guard so the trend is visible in cloud logs:
   `[LOCAL-848] peak RSS <phase> <MiB>`.

**Measured live (Rijks, 5 stops, `--memory=512m`, cheap arm, pool off,
`STORY_PASS_MODEL=gpt-4.1`):** single‑tour peak **297.5 MiB → 132.8 MiB (−55%)**,
and the cross‑request ratchet (the real OOM mechanism) is **eliminated** — a warm
second request stays flat at 121.8 MiB (ratchet −0.0 MiB). Every run finished
with peak well under the 350 MiB target.

---

## What was profiled (Do #1)

The generator (`generate_tour_text_service.py` → `generate_tour_text.py`, a
1.9 MB engine) produces **tour TEXT only** — there is no audio synthesis, no ZIP
build and no base64 copy in the generator. (The ZIP/base64 work the ticket asked
about lives in `tour_orchestrator_service.py` / `tour_worker_service.py`, which
is **not** the OOM path — the OOM log is `"Starting tour text generation…"`.) So
profiling targeted the real text phases.

A dedicated profiler (`run_local848_container.py`, tracemalloc ON) ran Rijks (5)
in the container and attributed the peak per phase. **Key finding:**

| metric | value |
|---|---|
| peak RSS (process / cgroup‑visible) | **462.9 MiB** |
| peak Python‑traced heap (tracemalloc) | **67.8 MiB** |

The ~395 MiB gap is **not live Python objects** — it is interpreter + imports +
transient C‑level churn that Python has freed but glibc retains. The top
tracemalloc sites are tiny (imports, `linecache`, a few `exhibition_checklist.py`
regex scratch buffers), which confirms there is **no single giant object to
trim** — the problem is allocator retention, so the fix must *return freed memory
to the OS*, not delete a data structure.

RSS climbs monotonically across phases (this profile run, tracemalloc ON):

```
intent 101 → poi_selection 154 → fact_sheets 195 → narration 206 →
external_lookups 271 → story_first 372 → packing 431 → verification 463
```

The biggest climb is `story_first`, which runs stops in a thread pool — exactly
where glibc spawns up to 8×CPU arenas, each retaining freed blocks.

> Note: tracemalloc roughly doubles allocation cost, so 463 MiB is **inflated**
> and must not be read as the production peak. The acceptance measurements below
> have tracemalloc OFF and reflect true memory.

## The cuts (Do #2) — all behaviour‑neutral

* **`mem_guard.py` (new).** `read_rss_mib()` (cheap, `/proc/self/statm` on Linux,
  `ru_maxrss` fallback, never raises); `PeakTracker` (per‑phase + overall peak);
  `release_memory()` = `gc.collect()` + `malloc_trim(0)` via `ctypes`
  (glibc‑only, no‑op elsewhere); `maybe_snapshot()` tracemalloc hook gated behind
  `LOCAL848_TRACEMALLOC`. Stdlib only, no new dependency.
* **`phase_timer.py`.** The existing `PhaseTimer` (LOCAL‑445‑B) already brackets
  every phase. Wired in: sample RSS at `start()`/`end()`, emit
  `[LOCAL-848] peak RSS <phase> <MiB>` per phase and
  `[LOCAL-848] peak RSS process <MiB>` in `summary()`, and call
  `release_memory()` at each phase boundary (gated by `LOCAL848_RELEASE`, default
  on). Import‑safe shims — a missing/broken `mem_guard` degrades to a silent
  no‑op and never disturbs timing or generation.
* **`generate_tour_text_service.py`.** A `finally` in `generate_tour_async`
  releases memory **after every request** and logs
  `[LOCAL-848] post-request release: RSS X -> Y MiB`. This is the key lever for a
  warm container: it stops RSS ratcheting across requests.
* **`Dockerfile.generator`.** `ENV MALLOC_ARENA_MAX=2` — caps glibc's per‑thread
  arenas so the `story_first` pool can't balloon RSS. The dominant single lever
  (see numbers below). Passed via `-e` in the run wrappers too, because the live
  harness bind‑mounts `/app` over the existing image (which predates the ENV).

Why no Wikipedia/JSON trimming was needed: the per‑work Wikipedia research
(`work_story_research.py`, LOCAL‑840) is **already bounded** (14 000 EN + 6 000
local chars, ≤ 8 passages × 600 chars) and the profiler showed it is not a
material allocator. Adding speculative trimming there would have been churn
without benefit.

## The guard (Do #3)

Always‑on, negligible cost (~10 `/proc/self/statm` reads per tour). One line per
phase, one process summary, plus the per‑request release line — a single
`grep '[LOCAL-848] peak RSS'` reconstructs the whole memory trend from Cloud Run
logs.

## Tests (Do #4)

* `test_local848_mem_guard.py` — 23 tests: RSS reader (incl. a forced‑failure
  path), `PeakTracker` max/order/reset, the tracemalloc env gate,
  `release_memory`/`malloc_trim` (calls gc + trim, swallows failures), and the
  `PhaseTimer` wiring (emits the guard lines; release on by default; disableable;
  survives a mem_guard failure).
* `test_local848_release_mechanism.py` — reproduces the arena‑retention mechanism
  (glibc‑gated strong assertion + a portable weaker invariant).
* **Regression (no behaviour change):** `826 / 826b / 826c / 837 / 840 / 842 /
  844 / 845` → **128 passed**. `test_local651_sub_timer.py` (the existing phase
  timer suite) → 8 passed. LOCAL‑848 suites → **31 passed, 1 skipped** (the
  glibc‑only mechanism assertion skips on the macOS dev box).

## Live — budget enforced (Do: Live)

Isolated throwaway postgres (project `local848` / `local848p`), seeded with the
REAL cached rows (Rijks `Q190804` + Orsay `Q23402`) from the shared LOCAL‑826B
fixture. `audioura-tour-generator:latest` image, **branch code bind‑mounted**,
`--memory=512m` to reproduce the Cloud Run limit. Meter contract: dedicated
ledger, `PYTHONPATH=/opt/meter`, every row tagged `METER_SERVICE=LOCAL-848`,
hard cap `$0.60`. Cheap museum arm, `DISABLE_STOP_POOL=1`,
`STORY_PASS_MODEL=gpt-4.1`. Never an `audioura-*` container, never the live DB.

| run | config | peak RSS | result | cost |
|---|---|---|---|---|
| profile (tracemalloc ON) | release on, no arena cap | 462.9 MiB *(inflated)* | top‑10 sites captured | $0.325 |
| after (single tour) | release on, no arena cap | **229.1 MiB** | 5 stops, **PASS** (≤ 350) | $0.358 |
| warm ×2 — **full fix** | `MALLOC_ARENA_MAX=2` + release | req1 **132.8** → 121.8; req2 warm **121.8** | ratchet **−0.0 MiB**, **PASS** | $0.36 |
| warm ×2 — **pre‑fix** | arenas default, per‑phase release off | single‑tour peak **297.5 MiB** | baseline | $0.35 |

Per‑phase trend, full fix vs pre‑fix (both tracemalloc OFF, 512m):

```
pre-fix : intent 64 → poi 74 → fact 83 → external 144 → story_first 295 → packing 297.5
full fix: intent 64 → poi 72 → fact 79 → external 88  → story_first 117 → packing 132.8
```

Harness: `run_local848_live.sh` (512 MiB acceptance, `before`/`after` tags; set
`MALLOC_ARENA_MAX=off` and `LOCAL848_RELEASE=0` for the pre‑fix baseline;
`SCRIPT=run_local848_warm.py` for the warm proof) and `run_local848_profile.sh`
(generous memory + tracemalloc for attribution). Reports:
`reports/local848/{profile_result,accept_after,accept_before,warm_result}.json`.

## Honest caveat on reproduction

Under the **prescribed single‑run cheap / pool‑off env**, a lone Rijks(5) tour
peaks ~170–300 MiB — comfortably under 512 — so a single local run does **not**
reproduce the production 512 MiB OOM by itself. The production OOM is a
**warm‑container, production‑config** phenomenon: the stop pool is on, the full
(not cheap) models return much larger response buffers, glibc defaults to 8×CPU
arenas, and the process serves many requests back‑to‑back. The evidence that the
OOM hit *mid‑tour* on already‑running revisions matches cross‑request RSS
ratcheting, not one tour needing 531 MiB in isolation.

This submission therefore proves the **mechanism** directly (profiler: 463 MiB
RSS vs 68 MiB live heap → allocator retention) and proves the **fix** against
that mechanism: the arena cap + release cut the single‑tour resident peak by 55%
(297.5 → 132.8 MiB) and flatten the cross‑request ratchet to zero in a warm
container. The D755 raise to 1 GiB remains a sensible stop‑gap; this change is
the structural reduction that makes 512 MiB safe again.

## Process / constraints

* Committed to `LOCAL-848-generator-memory`, no `git add -A` (explicit paths only).
* No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
  `.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, `legal/`,
  `GCLOUD_STORIED_START_HERE.md`, `TRAVEL_PROJECTS.md`.
* No `DELETE`, no writes to the live DB, no touching shared `audioura-*`
  containers (only disposable `local848*` ones).

## Files

**New:** `mem_guard.py`, `run_local848_container.py`, `run_local848_accept.py`,
`run_local848_warm.py`, `run_local848_profile.sh`, `run_local848_live.sh`,
`test_local848_mem_guard.py`, `test_local848_release_mechanism.py`.
**Modified:** `phase_timer.py`, `generate_tour_text_service.py`,
`Dockerfile.generator`.
