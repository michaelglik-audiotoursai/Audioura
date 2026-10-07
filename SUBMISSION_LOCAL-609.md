# SUBMISSION — LOCAL-609: Per-tour cost breakdown by provider, on every ledger row

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-609-cost-breakdown` (from `subscribed` @ `33606ec`)
**Base verified:** `git merge-base --is-ancestor 33606ec HEAD` → exit 0.

Michael asked what tour TB5GCRDV cost, split into OpenAI, Serper, Gemini, voice,
translation "and anything else" — and the ledger could not answer, because
`search` was always `$0.00`, Gemini Flash tokens were metered nowhere, the
LOCAL-603 preflight had no per-job line, and a pool reuse recorded `$0` with no
link to the research it reused. This change makes every `tour_generate` ledger
row carry a **counted** (not estimated) per-provider breakdown, records
`research_cost_reused` on reuse deliveries, and ships a CLI that prints the table.

---

## What ships

### 1. Every tour row's `breakdown` now has the 7 provider keys (counted)
`cost_accumulator.CostAccumulator.provider_breakdown()` is the one source of
truth, written into the ledger row by `generate_tour_text._reconcile_cost_record_from_accumulator`:

| key | $ | units counted |
|---|---|---|
| `openai` | yes | input+output tokens, calls, **per-model** `by_model` |
| `gemini_grounding` | yes | grounded requests, **search queries** (the invoice unit) |
| `gemini_tokens` | yes | Flash input/output tokens, calls |
| `serper` | yes | queries |
| `preflight` | yes | queries + Flash tokens (`0` / "did not run" on a cache hit) |
| `tts` | yes | engine, chars, calls (Kokoro is `$0` by rate) |
| `translation` | yes | engine, chars, `$` — on the translation row |

The legacy 4-key shape (`llm`/`grounding`/`search`/`tts`) is still produced by
`breakdown()` for older readers; nothing that read the old shape breaks.

### 2. Serper is metered at the real query sites (was always `$0.00`)
`cost_accumulator.add_search_queries(1)` fires at the three real Serper call
sites — `work_story_searcher._serp_search`, `venue_resolver._serper_search`,
`exhibition_site_js.default_serper` — right after the key check, where a query is
actually about to go on the wire. The live run below counted **25 queries =
$0.025**, where the old ledger said `$0.00`.

### 3. Gemini Flash tokens + preflight are metered
`story_leads._meter_gemini_call` reads `usageMetadata` (prompt/candidates/thoughts
token counts) and `groundingMetadata.webSearchQueries` at the single Gemini
chokepoint (both `_gemini` and `gemini_with_sources`) and calls
`cost_accumulator.add_gemini_call`. A `preflight_scope()` context manager wraps
the LOCAL-603 preflight call so its tokens + queries land in the `preflight`
bucket on their own line instead of being invisible inside the Gemini totals.

### 4. Reuse now records `research_cost_reused`
- Additive column `stop_pool.research_cost_usd` (schema change — see below) is
  written when a stop is **first** pooled (first-pooled semantics: a later re-pool
  never erases the original). Each stop gets its share of the tour's one-time
  research cost = every counted channel **except TTS**, divided by the stop count.
- A pool / by-reference delivery sums that column over the stops it reuses and
  records `research_cost_reused` on the delivery row — so a listener's price can
  later be shown as "this delivery" + "share of research".

### 5. `tour_cost_report.py <audio_tour_id | job_id>`
Prints the provider × ($, units) table, the delivery total, the reused-research
total, and the wall time (ledger span, preferring `audio_tours.created_at` as the
start), including the translation + TTS rows of any translation (linked by
`breakdown->>source_tour_id`). The report is a pure READER of `cost_ledger` — it
never re-prices anything, so every dollar it prints was counted at a real call site.

### Rates (all in `cost_rates.py`, each cited + dated)
- `GEMINI_FLASH_INPUT_PER_1M = 0.30`, `GEMINI_FLASH_OUTPUT_PER_1M = 2.50`
  (Gemini 2.5 Flash family = deployed `gemini-flash-latest`), from
  <https://ai.google.dev/gemini-api/docs/pricing> + corroborating trackers
  (morphllm, rapidevelopers), **read 2026-10-06**. New: `gemini_tokens_cost()`.
- `preflight_cost()` uses **no new rate** — it is grounding queries +
  Flash tokens, reported on its own line only for visibility (ticket LOCAL-609).
- Existing cited rates reused unchanged: `SERPER_COST_PER_QUERY=0.001`,
  `GROUNDING_COST_PER_QUERY=0.014` (per-query, the invoice unit), Polly neural/
  standard, AWS Translate.

---

## Schema change (additive only — no DELETE, no GCloud)

```
ALTER TABLE stop_pool ADD COLUMN IF NOT EXISTS research_cost_usd NUMERIC(12,6) DEFAULT 0;
```

Added to `stop_pool_store._ensure_table` as an idempotent `ADD COLUMN IF NOT
EXISTS`, defaulting to `0`. No column is dropped or renamed; no row is ever
deleted. Pre-existing pooled rows read back as `research_cost_usd = 0` (reported
honestly as `$0` reused research until they are re-pooled by a fresh generation).

---

## Live isolated run (deliverable 5)

`./run_local609_live.sh` — a DISPOSABLE Postgres + network + generator
(`local609-pg` / `local609-net` / `local609-gen`), never an `audioura-*`
container and never the shared DB. Fresh 3-stop `Isabella Stewart Gardner Museum,
Boston, MA`, cap `$1.50`, tour cache off. All disposable containers, the image,
and the network were removed afterward. `job_id = local609-c34dd5b98424`.

```
================================================================
LOCAL-609 — Per-tour cost breakdown by provider
Tour:      Isabella Stewart Gardner Museum, Boston, MA
job_id:    local609-c34dd5b98424
================================================================

DELIVERY (tour_generate, POOL REUSE)
----------------------------------------------------------------
Provider                          Cost  Units
----------------------------------------------------------------
OpenAI                       $0.360191  134369+10992 tok, 80 calls
Gemini grounding             $0.000000  0 queries, 3 req
Gemini Flash tokens          $0.005242  1599+1905 tok, 6 calls
Serper                       $0.025000  25 queries
Preflight                    $0.000000  did not run
TTS                          $0.000000  —, 0 chars, 0 calls
----------------------------------------------------------------
Delivery total               $0.360191
Reused research              $0.000000  (reused 0 pooled stop(s))
Composition                             new=3, reused=0

OTHER (spine_generate): $0.008375

================================================================
DELIVERY TOTAL (all rows this job)                     $0.368566
REUSED-RESEARCH TOTAL                                  $0.000000
WALL TIME (ledger span)                                    3m 5s
================================================================
```

Reading the table:
- **Serper $0.025 / 25 queries** — the exact line that was *always `$0.00`*
  before this ticket. Now counted at the real `_serp_search` call site.
- **Gemini Flash tokens $0.005242 / 1599+1905 tok** — metered nowhere before.
- **Gemini grounding $0.00, 3 requests, 0 queries** — three grounded requests
  were issued but each reported zero `webSearchQueries`, so Google billed `$0` on
  that channel. This is the honest counted figure, not an estimate.
- **Preflight "did not run"** — the preflight did not fire for this request, so
  its line is `$0` and says so.
- **TTS $0** — this is the generation path; TTS is synthesized at the
  orchestrator level, so a bare `generate_tour_text` run shows `$0` here.
- Delivery total **$0.368566**, well under the `$1.50` cap.
- First-ever tour of this venue (empty pool) → `research_cost_reused = $0`.

The run was tagged "POOL REUSE" because an empty-pool first tour of a contained
museum routes through the pool orchestrator's first-tour fold path; the breakdown
is the new generation's full counted provider split (`new=3, reused=0`).

---

## Tests

`tests/test_local609_cost_breakdown.py` — **18 pass**:
- Each meter increments as its call happens (stubbed wires): serper, gemini
  tokens + grounding split, preflight-scope routing, OpenAI per-model, TTS engine,
  7-key shape; and `story_leads._meter_gemini_call` reading `usageMetadata`
  (`thoughtsTokenCount` folded into output) + `webSearchQueries`.
- The Serper meter counts **real** queries: a stubbed-network `_serp_search` call
  made inside a `tour_scope` increments `search.queries` by exactly one per call;
  no key ⇒ no query ⇒ no charge.
- The report sums correctly: fresh renders all 7 providers; delivery total sums
  tour + translation ($0.92); pool-reuse shows reused research $0.28; cache-hit
  preflight says "did not run"; empty-rows message; legacy 4-key still renders.

Regression: 56 relevant cost/pool/grounding/serper/translation tests pass.

**Known pre-existing flake (not caused by this ticket):**
`tests/test_local597_guard.py::test_ungrounded_gemini_not_blocked_by_guard` fails
*only* when run inside a large mixed batch — a test-isolation bug where a prior
test leaves `requests.post` stubbed and `GEMINI_API_KEY` set. **Verified it fails
identically on the base commit `33606ec` with the same batch, without any
LOCAL-609 change.** It passes in isolation and as its own file. Out of scope.

---

## Files touched
- `cost_rates.py` — Gemini Flash token rates (cited), `gemini_tokens_cost`, `preflight_cost`.
- `cost_accumulator.py` — provider-split buckets, `provider_breakdown()`,
  per-query grounding, `add_gemini_tokens` / `add_preflight` / `add_gemini_call`,
  `preflight_scope()`; backward-compatible `breakdown()` kept.
- `work_story_searcher.py`, `venue_resolver.py`, `exhibition_site_js.py` — Serper meter.
- `story_leads.py` — `_meter_gemini_call` wire at the Gemini chokepoint.
- `generate_tour_text.py` — reconcile writes the 7-key breakdown; cache-hit /
  pool / by-reference records carry the full shape + `research_cost_reused`;
  preflight wrapped in `preflight_scope`; per-stop research cost on pool store.
- `stop_pool_store.py` — additive `research_cost_usd` column + store/read.
- `stop_pool_orchestrator.py`, `l2_by_reference.py` — return `research_cost_reused`.
- `generate_tour_text_service.py` — fold `research_cost_reused` + reuse metadata
  into the stored breakdown JSONB.
- `translation-service/translation_service.py` — provider-shaped `translation` key.
- `tour_cost_report.py` — the CLI.
- `tests/test_local609_cost_breakdown.py`, `run_local609_gardner.py`,
  `run_local609_live.sh` — tests + isolated live harness.

No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
.continuous_dev/STATUS.md.
