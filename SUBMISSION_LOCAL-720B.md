# SUBMISSION — LOCAL-720B: re-run the Claude replay fairly (D674)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-720B-fair-replay` · **Base:** subscribed @ `d4e7855b`
**Merged in:** `origin/LOCAL-720-claude-bakeoff-run` (the invalid LOCAL-720 outputs + 5.5 harness fixes).
**Code SHA at submission (before this doc's commit):** `cfd20db1d4a935f0f36e4dddfa1c2bb3436af946`
**Base ancestry check:** `git merge-base --is-ancestor d4e7855b HEAD` → exit 0 (PASS).

## What LOCAL-720 got wrong, and the fix
LOCAL-720 ran every arm at `max_tokens=1000`. Claude's tokenizer gives ~3 characters per token (vs ~5 for
`gpt-4.1-mini`) and Opus still spends tokens thinking, so Claude hit the cap mid-sentence on most stops
(Opus 10/12). The judges scored **truncation, not writing**, and Opus came last. This re-run sets
**`max_tokens = 2500` for every arm** and records the provider's `stop_reason`/`finish_reason` per stop.

**Acceptance: zero stops ended on `max_tokens`/`length`.** All 48 stops finished naturally
(`finish_reason` = `stop` for gpt-4.1-mini, `end_turn` for all Claude arms). No arm needed the 4000 fallback.

## Code changes (all committed on `LOCAL-720B-fair-replay`)
- **`replay_harness.py`** — shared `MAX_TOKENS = 2500` (overridable via `BENCH_MAX_TOKENS`, used by the
  openai/gemini/anthropic arms); `call_openai`/`call_gemini`/`call_anthropic` now return
  `(text, usage, status, finish)`; `run_arm` records `finish_reason`, `truncated`, `chars`, `max_tokens` per
  stop into each `arm_X_results.json` and prints a `*** TRUNCATED ***` warning + end-of-arm truncation count.
  LOCAL-720's thinking controls kept unchanged (Haiku `disabled`, Sonnet `between_tools`, Opus `adaptive` +
  `output_config.effort=low`); no `temperature` on the 5.5 models.
- **`report.py`** — adds **mean characters delivered** and **$ per 1,000 delivered characters** (a
  per-listener-minute price, not per-token), plus a **truncations** column; falls back to `len(output)` on
  older records.
- **`score_stops.py`** — new `non_narration_reply` detector (fails a draft that asks the requester to
  choose/authorize or promises to produce the stop later instead of narrating — LEAD review item #3); new
  `unblind` command remaps the blind-labelled judge scores back to real arms via `_blind/blind_key.json` so the
  blind double-judge pipeline is fully reproducible.
- **Tests** — `tests/test_local712_anthropic_provider.py`, `tests/test_local712b_current_claude.py` updated for
  the 4-tuple return, `max_tokens=2500`, and `stop_reason` capture. **32 harness tests pass.**

## Commands run (in order)
Replay (inside own container `local720b-gen`; one arm at a time so the meter is checked after each):
```
docker run -d --rm --name local720b-gen --hostname local720b-gen --network development_default \
  --env-file .env -e DB_HOST=postgres-2 -e DB_NAME=audiotours -e DB_USER=admin -e DB_PASSWORD=*** \
  -e DB_PORT=5432 -e PYTHONPATH=/app -e WIKI_CACHE=/app/.continuous_dev/bench/local720b_out/_wiki_cache \
  -v "$PWD":/app -w /app audioura-tour-generator:latest sleep infinity

docker exec local720b-gen python3 replay_harness.py build-only --out /app/.continuous_dev/bench/local720b_out/_prompts
docker exec local720b-gen python3 replay_harness.py run --arm B --out /app/.continuous_dev/bench/local720b_out/B
docker exec local720b-gen python3 replay_harness.py run --arm H --out /app/.continuous_dev/bench/local720b_out/H
docker exec local720b-gen python3 replay_harness.py run --arm I --out /app/.continuous_dev/bench/local720b_out/I
docker exec local720b-gen python3 replay_harness.py run --arm J --out /app/.continuous_dev/bench/local720b_out/J
```
Judging (blind, double):
```
docker exec local720b-gen python3 score_stops.py detectors --dir /app/.continuous_dev/bench/local720b_out --arms BHIJ
docker exec local720b-gen python3 score_stops.py blind     --dir /app/.continuous_dev/bench/local720b_out --arms BHIJ --seed 720
docker exec local720b-gen python3 score_stops.py gpt       --dir /app/.continuous_dev/bench/local720b_out/_blind --arms ABCD   # judge 2 (gpt-4.1)
KIRO_CLI=/opt/homebrew/bin/kiro-cli python3 score_stops.py kiro --dir .continuous_dev/bench/local720b_out/_blind --arms ABCD   # judge 1 (host)
python3 score_stops.py unblind --dir .continuous_dev/bench/local720b_out
python3 report.py --dir .continuous_dev/bench/local720b_out --host local720b-gen --arms BHIJ --baseline B
```
Blind key (seed 720): `D→B, C→H, A→I, B→J`.

## Meter, cap and row counts
- **Generation meter (the $1.00 hard cap), host `local720b-gen`, status 200:** **$0.778112 over 48 calls**
  (12 per arm, one draft per stop, no retries). **Under the $1.00 cap (PASS).** Per model:
  `gpt-4.1-mini $0.01683 · claude-haiku-5-5 $0.00918 · claude-sonnet-5-5 $0.20708 · claude-opus-5-5 $0.54502`.
- **gpt-4.1 judge calls are NOT on this ledger.** The container was launched with `PYTHONPATH=/app`, which
  overrode the image's `/opt/meter` auto-meter; `score_stops.py` does not bootstrap the meter the way
  `replay_harness.py` does, so the 48 judge calls went unmetered. Estimated from critique sizes at gpt-4.1 rates
  ($2/1M in, $8/1M out): **≈ $0.22** (~63k input tokens, ~11k output tokens). This is a measurement cost, not
  generation spend; the $1.00 hard cap is defined on `paid_api_calls` where `host='local720b-gen'` = $0.778112.
  Disclosed here for honesty. The **Kiro judge** runs via `kiro-cli` (subscription), not a metered API call.
- **`audio_tours` row count: 498 before and 498 after.** No writes (the `store` command was never run; only
  `run`/`build-only`/detectors/blind/judges/report, none of which touch `audio_tours`).

## Verbatim command exits
- `replay_harness.py run --arm B` → `[B] wrote 12 stop results … (truncations=0)`, all `finish=stop`.
- `… --arm H` → `(truncations=0)`, all `finish=end_turn`.
- `… --arm I` → `(truncations=0)`, all `finish=end_turn`.
- `… --arm J` → `(truncations=0)`, all `finish=end_turn`.
- `score_stops.py detectors … --arms BHIJ` → `arm B: 0 … arm H: 4 … arm I: 4 … arm J: 1 total failures`.
- `score_stops.py blind … --seed 720` → `wrote 4 blind arms … (labels: ['A', 'B', 'C', 'D'])`.
- `score_stops.py gpt … _blind --arms ABCD` → per-blind-arm means printed (A 7.62, B 8.47, C 7.35, D 7.92 g).
- `score_stops.py kiro … _blind --arms ABCD` → per-blind-arm means printed (A 6.94, B 7.88, C 6.33, D 6.83 K).
- `score_stops.py unblind` → `kiro_scores.json: remapped A->I, B->J, C->H, D->B`; same for `gpt_scores.json`.
- `report.py … --host local720b-gen --arms BHIJ --baseline B` →
  `Within 0.3 of baseline under Kiro: ['I']` · `Within 0.3 of baseline under gpt-4.1: ['I']`.

## Result (fair, `max_tokens=2500`, truncations=0 every arm)
| Arm | Model | Kiro mean/min | gpt-4.1 mean/min | Det | Trunc | $/stop | $/1k chars | Median s | Mean chars |
|-----|-------|---------------|------------------|-----|-------|--------|------------|----------|------------|
| B | gpt-4.1-mini | 6.83 / 4.5 | 7.92 / 5.5 | 0 | 0 | $0.00140 | $0.00049 | 4.12 | 2868 |
| H | Claude Haiku 5.5 | 6.33 / 0.0 | 7.35 / 2.0 | 4 | 0 | $0.00077 | $0.00030 | 5.59 | 2555 |
| I | Claude Sonnet 5.5 | 6.94 / 0.0 | 7.62 / 2.0 | 4 | 0 | $0.01726 | $0.00553 | 10.61 | 3122 |
| J | Claude Opus 5.5 | 7.88 / 2.5 | 8.47 / 3.0 | 1 | 0 | $0.04542 | $0.01345 | 18.4 | 3378 |

**Opus 5.5 beats today's `gpt-4.1-mini` under BOTH judges; Sonnet 5.5 is within 0.3 of baseline under both.**
In the invalid LOCAL-720 table Opus was last (5.62/6.17) purely because the 1000-token cap truncated it. The
H/I detector failures are all on the three empty-/wrong-source Walters stops (Springtime, Sappho, Death of
Caesar), where Haiku/Sonnet refuse or add a note to the operator rather than invent — caught by the new
`non_narration_reply` detector.

## Deliverables
- `.continuous_dev/bench/local720b_out/` — raw drafts, `arm_X_results.json` (with `finish_reason`/`truncated`/
  `chars`/`max_tokens`), `_prompts/`, `_wiki_cache/`, `_blind/` (+ `blind_key.json`, `_critiques_gpt/`),
  `_critiques/` (Kiro), `kiro_scores.json`, `gpt_scores.json`, `detectors.json`, `report.json`,
  `report_table.md`. (`.continuous_dev` is gitignored; committed with `git add -f`.)
- "LOCAL-720B results" section prepended to `.continuous_dev/bench/BAKEOFF_LOCAL-712.md` (full per-arm metrics,
  per-stop scores, verbatim samples, and 5 plain lines for Michael).

## Scope / safety
No full tours run (LOCAL-720's live tour was the wrong config and blew the budget; this task runs none). Own
container only (`local720b-gen`), never touched any `audioura-*` container. Keys verified by length only
(OPENAI 164, ANTHROPIC 106, GEMINI 53), never printed. No `audio_tours` writes. No phones. No edits to
`DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`, or `.continuous_dev/` outside `.continuous_dev/bench/`.
