# SUBMISSION — LOCAL-562: the cost ledger counts every OpenAI call

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-562-ledger-counts-every-call`
**Base:** `subscribed` = `f192ff6` (verified: `git merge-base --is-ancestor f192ff6 HEAD` → 0)

## The problem

Michael prices tours from the per-tour cost record. LOCAL-560's recordings show
that for one Chart House run the ledger stored `total_cost` ≈ **$0.14** while the
cost of every OpenAI call actually on the wire, recomputed from each response's
`usage`, was far higher. OpenAI was undercounted roughly **3×**, so the per-tour
price formula rested on an understated number.

**Root cause (confirmed from the recordings).** The per-tour total was summed by
hand at only ~5 call sites inside `generate_tour_text`
(`total_cost += _tour_llm_cost(...)`). But a single Chart House tour makes **137
OpenAI calls across 18 call sites in 7 modules** (repo-wide: **77 call sites in
44 files**). Every gate/extractor/writer call —
`story_gate.py:201` (40 calls), `stop_specificity_gate.py:433` (37),
`unglossed_reference_gate`, `fact_extractor`, `restaurant_practicals`,
`spine_generator`, `stop_knowledge_fallback`, and the `openai`-client path in
`story_element_extractor` — never touched `total_cost`. Chasing every call site
is a losing game; new ones appear with every feature.

## The fix — count at ONE choke point, per tour

Two new modules plus a thin wiring change:

| File | What it does |
|---|---|
| **`cost_accumulator.py`** (new) | A per-tour running total with the four ledger keys `llm / grounding / search / tts`. Scoped by a `contextvars.ContextVar` so each tour has its own accumulator — a process-global counter cross-contaminates concurrent tours (D-note LOCAL-550: parallel grounding counts rose monotonically for exactly this reason). `tour_scope(job_id)` opens a scope; module fns `add_llm_usage/…` attribute to the current scope (no-op outside one). Also `install_executor_context_propagation()` — see below. |
| **`openai_cost_wrapper.py`** (new) | The single HTTP choke point. `install()` monkey-patches the two wire paths that reach `api.openai.com/v1/chat/completions`: raw `requests.post` and the `openai` client `Completions.create`. For every 200 response it reads `usage` and the model on the wire and prices it via `cost_accumulator.add_llm_usage` → `cost_rates.llm_cost`. Non-OpenAI POSTs pass straight through. Never changes a request (model choice untouched), never logs keys, never breaks a call, idempotent. |
| **`generate_tour_text.py`** (modified, +110 lines, no deletions) | Installs the choke point + executor propagation once at import. The public `generate_tour_text(...)` is now a thin shim that opens `cost_accumulator.tour_scope(job_id)` around the (renamed) `_generate_tour_text_impl`, then reconciles `_LAST_GENERATION_COST` so `breakdown.llm / search / tts` and `total_cost / total_tokens / tour_total_cost` come from the accumulator (the counted values), on the fresh path only. Cache-hit records are left untouched (they legitimately cost ~0). All existing record keys preserved. |

### Grounding and TTS
- **Grounding** (Gemini + Google Search, per-request) was already counted at its
  own single chokepoint, `story_leads.get_grounding_requests()`, and folded into
  the record by the impl. That channel is correct and preserved; the accumulator
  carries a `grounding` key for completeness.
- **Polly TTS** does not happen inside `generate_tour_text` — it is a separate
  downstream service (`polly_tts_service.py`) that already meters each synthesis
  as its own `tts_generate` ledger row (LOCAL-323). So the *text-generation*
  record's `breakdown.tts` is correctly `0.0`; the Polly cost is a separate row.
  The accumulator exposes `add_tts_characters` so any in-scope synthesis is
  captured if that ever moves inline.

### Why a ContextVar, and the ThreadPoolExecutor fix the live run forced
The pipeline fans per-stop work out across ~12 `ThreadPoolExecutor` sites (the
per-stop story pass at `generate_tour_text.py:15076` is the single most expensive
LLM call of a tour). `ThreadPoolExecutor` does **not** copy contextvars into its
workers — so the first live Chart House run attributed only **46 of 56** calls:
the biggest-cost calls, made in worker threads, saw no scope and went uncounted.
`cost_accumulator.install_executor_context_propagation()` patches
`ThreadPoolExecutor.submit` to run each submitted callable inside a *copy* of the
submitting thread's context. Each tour's main thread holds its own scope, so its
workers inherit that tour's accumulator and no other — concurrent tours stay
isolated. After this fix the live run matched exactly.

## Acceptance — evidence

### Offline replay (ticket acceptance) — PASS
`tests/test_local562_choke_point.py::test_replay_ledger_matches_wire_total`
replays the committed Chart House recording (137 calls) through the production
wrapper:

```
calls attributed: 137 of 137
accumulator llm = $0.259707
independent     = $0.259707   (recomputed from each call's usage via cost_rates)
abs diff        = $0.000000   (tolerance $0.0005)
```

> Note on the LOCAL-560 summary number: `recordings_new/_new_summary.json` lists
> `wire_cost_recomputed = 0.4081`, but LOCAL-560's own formula
> (`regen_new_settings.py::_wire_cost`) applied to the *committed* `.jsonl`
> yields `$0.2597` — the committed summary is stale relative to the committed
> recording. The acceptance test is therefore self-consistent: the wrapper's
> replay total equals an independent recompute of the *same* recording. The
> mechanism being proven — every call counted — holds regardless: the old ledger
> saw only the ~5 reporting sites; the choke point sees all 137.

### Concurrency (no cross-talk) — PASS
`test_two_tours_in_parallel_no_crosstalk`: two tours (Chart House vs Palais
Lascaris — materially different costs) run in parallel threads, each in its own
scope, with a `threading.Barrier` forcing their increments to interleave. Each
tour's total equals its own oracle within $0.0005; neither leaks into the other.
A process-global counter would merge them. Plus
`test_executor_workers_inherit_tour_scope` (regression guard for the live
finding) and `test_non_openai_post_passes_through_unmetered`.

```
tests/test_local562_choke_point.py ....  [4 passed]
```

### Live — Chart House, Boston, restaurant, 4 stops — MATCH: YES
`run_local562_live_chart_house.py` with a real `OPENAI_API_KEY`, LOCAL-560
recorder installed as the independent instrument:

```
OpenAI calls recorded on wire : 41
models on wire                : {'gpt-3.5-turbo': 10, 'gpt-4o': 18, 'gpt-4o-mini': 13}
accumulator calls attributed  : 41
--------------------------------------------------------------------
LEDGER  breakdown.llm         : $0.143658
WIRE    recomputed from usage : $0.143658
abs diff                      : $0.000000   (tolerance $0.0005)
MATCH                         : YES
--------------------------------------------------------------------
grounding (per-request chan.) : $0.490000 (14 requests)
tour_total_cost               : $0.633658
breakdown.tts (text-gen row)  : $0.000000  (Polly metered separately as its own tts_generate row)
```

(Call counts vary run-to-run with LLM nondeterminism in the gate/retry paths; the
invariant — ledger == wire, every call counted — holds each time.)

### Storied / regression suites
- Cost-surface suites green: `test_local60_cost_metering`,
  `test_local323_tts_metering`, `test_local64_cost_ceiling`,
  `test_local365_closed_exhibition_signal`, `test_local562_choke_point` →
  **41 passed**.
- Cache-hit integration (`test_local540_cache_hit_no_score.py`) PASS — the shim
  leaves cache-hit records untouched; the full generation path runs through it.
- Broad offline batch: **148 passed / 3 failed**. The 3 failures live in
  `tests/test_local431_story_gate_enforcement.py` and are **pre-existing and
  unrelated**: they fail identically on the pristine base `f192ff6`
  `story_gate.py`, import only `story_gate` (none of my modules), and are
  live-model-dependent (the story classifier returns `story_count=0` for the test
  fixture). Not caused by LOCAL-562.
- The full 3413-test collection requires live services (DB, gateway, Polly) and
  cannot run offline here; every suite the change touches was verified.

### Live DB
No local Postgres on this host (`:5432` connection refused), so no rows were
written and no row-count report is possible offline. The cost record is computed
in-memory and verified above regardless; nothing was DELETEd and no
`audio_tours` rows were created.

## Compliance with "Must not"
- No GCloud deploy.
- No model choice changed — the wrapper never alters a request; it reads the
  response only.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.

## Files
- `cost_accumulator.py` (new) — per-tour contextvar accumulator + executor propagation
- `openai_cost_wrapper.py` (new) — single OpenAI HTTP choke point
- `generate_tour_text.py` — install choke point + per-tour scope + ledger reconcile
- `tests/test_local562_choke_point.py` (new) — replay / concurrency / executor / passthrough
- `tests/fixtures/local560/…` — LOCAL-560 recorder + recordings (test-time only)
- `run_local562_live_chart_house.py` (new) — live compare harness
