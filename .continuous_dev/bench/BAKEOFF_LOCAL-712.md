# BAKEOFF_LOCAL-712 — Claude as the tour writer (D674)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-712-claude-bakeoff` · **Base:** subscribed @ `18028ba8`
**Michael (D674):** *"Substitute OpenAI and/or Gemini with Amazon Q or Claude. Can you experiment and tell me if the quality of the tour, generation time and price would increase?"*

> **STATUS: AWAITING `ANTHROPIC_API_KEY`.** The provider, rates, arms, both judges and the unit tests are
> built and green, but `ANTHROPIC_API_KEY` is empty on this host (checked by length, never printed), so by the
> D674/ticket key-gate **no real Anthropic or OpenAI call was made** — the tables below are scaffolds. LEAD runs
> the bench once Michael adds the key ($10 prepaid, no auto-recharge; experiment budget ≤ $3). The numbers here
> are placeholders (`—`) until then.

## Method (reused from LOCAL-647 — see BAKEOFF_LOCAL-647.md)
- **Identical inputs, no new research.** The 12 stored stops across 4 museums are rebuilt from saved data only
  (`venue_corpus.pages_json` + `story_elements_json`, and the work's free, disk-cached English Wikipedia extract).
  No Serper, no grounded Gemini call anywhere. One draft per stop per arm, no retries.
- **The production prompt is reused**, through `generate_tour_text.build_museum_stop_prompt()` and the
  `narration_model_route()` env hook — the same hook production uses, so the arms are the production call with
  only the model swapped.
- **Arms** (on the same 12 stops, identical inputs):
  | Arm | Model | Role |
  |-----|-------|------|
  | B | `gpt-4.1-mini` | today's narration model — the **baseline** |
  | F | `claude-haiku-4-5-20251001` | Claude Haiku 4.5 (Anthropic API) |
  | G | `claude-sonnet-5` | Claude Sonnet 5 (Anthropic API) |
- **Blind, double-judged.** Arms are relabelled to random letters (key kept in a separate file the judges never
  read). Every stop is scored twice with the SAME rubric: once by **Kiro** and once by a **gpt-4.1 judge**.
  Kiro itself runs on Claude, so the gpt-4.1 judge is the bias guard — **a "win" must hold under both judges.**
- **Noise floor** (COST_TIME_RESULTS_2026-10-09): the same code scores up to **2 points apart** on a single tour,
  so the **12-stop replay decides**, not single tours.

## 1. Per-arm replay table — JUDGE 1 (Kiro rubric) · AWAITING KEY
| Arm | Model | Mean | Min | Det.fails | HTTP fails | $/stop | $ total (12) | Median s | Mean out-tok | Within 0.3 of B |
|-----|-------|------|-----|-----------|-----------|--------|--------------|----------|--------------|-----------------|
| B | gpt-4.1-mini | — | — | — | — | — | — | — | — | (baseline) |
| F | Claude Haiku 4.5 | — | — | — | — | — | — | — | — | — |
| G | Claude Sonnet 5 | — | — | — | — | — | — | — | — | — |

## 2. Per-arm replay table — JUDGE 2 (gpt-4.1 judge, same rubric) · AWAITING KEY
| Arm | Model | Mean | Min | $/stop | Median s | Within 0.3 of B |
|-----|-------|------|-----|--------|----------|-----------------|
| B | gpt-4.1-mini | — | — | — | — | (baseline) |
| F | Claude Haiku 4.5 | — | — | — | — | — |
| G | Claude Sonnet 5 | — | — | — | — | — |

`$/stop` is the per-call average from the `paid_api_calls` ledger (network meter, host `local712-gen`), not an
estimate. Median seconds and mean output tokens come from each arm's `arm_X_results.json`.

## 3. Per-stop scores (both judges) · AWAITING KEY
| Stop | B (Kiro) | F (Kiro) | G (Kiro) | B (gpt) | F (gpt) | G (gpt) |
|------|----------|----------|----------|---------|---------|---------|
| Courtauld-0 | — | — | — | — | — | — |
| Courtauld-1 | — | — | — | — | — | — |
| Courtauld-2 | — | — | — | — | — | — |
| Walters-0 | — | — | — | — | — | — |
| Walters-1 | — | — | — | — | — | — |
| Walters-2 | — | — | — | — | — | — |
| Wallace-0 | — | — | — | — | — | — |
| Wallace-1 | — | — | — | — | — | — |
| Wallace-2 | — | — | — | — | — | — |
| Frick-0 | — | — | — | — | — | — |
| Frick-1 | — | — | — | — | — | — |
| Frick-2 | — | — | — | — | — | — |

## 4. Full-tour live test (3 tours per arm) · AWAITING KEY
Own container only (never `-p audioura`, never rename `audioura-*`), spare port, **cache + pool OFF** as in the
10-09 A/B. Tours Courtauld, Walters, Faneuil Hall (walking). is_test rows only — never DELETE anything.
**Budget cap $3.00 total across all providers — stop and report if reached.**

| Venue | Arm | Kiro | gpt-4.1 | $ (meter) | end-to-end s | tour id (is_test) |
|-------|-----|------|---------|-----------|--------------|-------------------|
| Courtauld | B | — | — | — | — | — |
| Courtauld | F | — | — | — | — | — |
| Courtauld | G | — | — | — | — | — |
| Walters | B | — | — | — | — | — |
| Walters | F | — | — | — | — | — |
| Walters | G | — | — | — | — | — |
| Faneuil Hall (walking) | B | — | — | — | — | — |
| Faneuil Hall (walking) | F | — | — | — | — | — |
| Faneuil Hall (walking) | G | — | — | — | — | — |

## 5. Two sample stops per arm (verbatim) · AWAITING KEY
To be filled from the raw drafts under `.continuous_dev/bench/local712_out/<arm>/`, two stops per arm, quoted
exactly as the model wrote them.

### Arm B — gpt-4.1-mini
> _(verbatim stop 1 — awaiting key)_
>
> _(verbatim stop 2 — awaiting key)_

### Arm F — Claude Haiku 4.5
> _(verbatim stop 1 — awaiting key)_
>
> _(verbatim stop 2 — awaiting key)_

### Arm G — Claude Sonnet 5
> _(verbatim stop 1 — awaiting key)_
>
> _(verbatim stop 2 — awaiting key)_

## 6. Recommendation · AWAITING KEY
_To be written in plain language after the run:_ does Claude (Haiku 4.5 or Sonnet 5) write **better** tours than
today's `gpt-4.1-mini`, and at what **time** and **price** — stated as a clear "yes / no / only if", holding under
**both** judges, and read against the 2-point single-tour noise floor. Nothing changes in production until Michael
sees this table (D674).

## How to run (LEAD, once the key is present)
```
# inside the generator container (meter + keys + DB), OWN container, cache/pool OFF
python3 replay_harness.py run-all --out /app/bench_out --arms BFG
python3 score_stops.py detectors  --dir /app/bench_out --arms BFG
python3 score_stops.py blind      --dir /app/bench_out --arms BFG     # relabel; key in _blind/blind_key.json
python3 score_stops.py kiro       --dir /app/bench_out --arms BFG     # judge 1
python3 score_stops.py gpt        --dir /app/bench_out --arms BFG     # judge 2 (gpt-4.1)
python3 report.py                 --dir /app/bench_out --host local712-gen --arms BFG --baseline B
```
Then the 3 full tours per arm (own container, spare port, cache/pool OFF, is_test), honouring the $3.00 cap.

## Artifacts (created by the run)
Under `.continuous_dev/bench/local712_out/`: `B/ F/ G/` raw drafts + `arm_X_results.json`; `_prompts/`,
`_wiki_cache/` (identical inputs); `_blind/` (blind tree + `blind_key.json`); `_critiques/` (Kiro) and
`_critiques_gpt/` (gpt-4.1); `kiro_scores.json`, `gpt_scores.json`, `detectors.json`, `report.json`,
`report_table.md`.

Code: `replay_harness.py` (arms F/G + `call_anthropic`), `score_stops.py` (gpt-4.1 judge + blind),
`report.py` (both-judge table); `generate_tour_text.narration_model_route()` anthropic branch;
`cost_rates.py` + `_meter/paid_api_meter.py` Claude rates/metering. Tests:
`tests/test_local712_anthropic_provider.py`.


---

# ADDENDUM 2 — LOCAL-712B: the CURRENT Claude lineup (D674 addendum 2)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-712B-current-claude` · **Base:** subscribed @ `e51247b4`
**Why:** LOCAL-712 wired the Anthropic provider with **Haiku 4.5** and **Sonnet 5**. Anthropic's pricing page now
lists a newer lineup; this addendum adds those three as extra bake-off arms **without removing** the LOCAL-712
arms or changing the baseline (`gpt-4.1-mini`, arm B). Everything else — identical inputs, the reused production
prompt, the blind double-judging, the key gate — is unchanged from LOCAL-712.

> **STATUS: AWAITING `ANTHROPIC_API_KEY`.** As with LOCAL-712, the provider/rates/arms/judges/tests are built
> and green, but by the D674 key-gate **no real Anthropic or OpenAI call is made without a key** (the harness
> reads `os.environ['ANTHROPIC_API_KEY']`; absent, it raises before any HTTP call — proven by
> `test_call_anthropic_requires_key_env`). The numbers below stay placeholders (`—`) until LEAD runs the bench
> with the key present, honouring the ≤ $3 experiment budget.

## New model rates (source of truth)
Source: `https://docs.anthropic.com/en/docs/about-claude/pricing` (model IDs from the Models-overview page,
`.../about-claude/models/overview`). **Read: 2026-10-18.** Base tokens, standard tier, USD per 1M tokens:

| Model | Claude API ID | Input | Output | Cache hit | Notes |
|-------|---------------|-------|--------|-----------|-------|
| Claude Haiku 5.5 | `claude-haiku-5-5` | **$0.10** (≤100k) | **$0.50** (≤100k) | $0.01 | **>100k tier: $0.50 in / $2.50 out.** Our prompts are ~3k tokens, so only the ≤100k tier ever applies. Cheaper than `gpt-4.1-mini` ($0.40/$1.60). |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2.00 | $10.00 | $0.10 | — |
| Claude Opus 5.5 | `claude-opus-5-5` | $4.00 | $20.00 | $0.20 | Opus "fast mode" ($8/$40) is **not** used. |

These are keyed into `cost_rates.LLM_RATES` and the meter's `ANTHROPIC` table at the ≤100k rate, each with the
source URL + read date and the Haiku-5.5 >100k tier recorded as a note. The LOCAL-712 rows (Haiku 4.5 $1/$5,
Sonnet 5 $2/$10) are left exactly as they were. Longest-key-wins resolution keeps `claude-sonnet-5-5` from
colliding with `claude-sonnet-5` (unit-tested both in `cost_rates` and the meter).

## Arms (added to the existing set)
| Arm | Model | Role |
|-----|-------|------|
| B | `gpt-4.1-mini` | today's narration model — the **baseline** (unchanged) |
| F | `claude-haiku-4-5-20251001` | Claude Haiku 4.5 (LOCAL-712, kept) |
| G | `claude-sonnet-5` | Claude Sonnet 5 (LOCAL-712, kept) |
| **H** | `claude-haiku-5-5` | **Claude Haiku 5.5 (new)** |
| **I** | `claude-sonnet-5-5` | **Claude Sonnet 5.5 (new)** |
| **J** | `claude-opus-5-5` | **Claude Opus 5.5 (new)** |

`D674_ARMS` is now `("B","F","G","H","I","J")`. The new arms route through the **same** `call_anthropic()` the
LOCAL-712 arms use (it is model-agnostic: same `/v1/messages` endpoint, system in the top-level `system` field,
`max_tokens=1000`, `temperature=0.7`), so the only variable across every arm remains the model string.

## Per-arm replay table — JUDGE 1 (Kiro rubric) · AWAITING KEY
| Arm | Model | Mean | Min | Det.fails | HTTP fails | $/stop | $ total (12) | Median s | Mean out-tok | Within 0.3 of B |
|-----|-------|------|-----|-----------|-----------|--------|--------------|----------|--------------|-----------------|
| B | gpt-4.1-mini | — | — | — | — | — | — | — | — | (baseline) |
| H | Claude Haiku 5.5 | — | — | — | — | — | — | — | — | — |
| I | Claude Sonnet 5.5 | — | — | — | — | — | — | — | — | — |
| J | Claude Opus 5.5 | — | — | — | — | — | — | — | — | — |

## Per-arm replay table — JUDGE 2 (gpt-4.1 judge, same rubric) · AWAITING KEY
| Arm | Model | Mean | Min | $/stop | Median s | Within 0.3 of B |
|-----|-------|------|-----|--------|----------|-----------------|
| B | gpt-4.1-mini | — | — | — | — | (baseline) |
| H | Claude Haiku 5.5 | — | — | — | — | — |
| I | Claude Sonnet 5.5 | — | — | — | — | — |
| J | Claude Opus 5.5 | — | — | — | — | — |

## Recommendation · AWAITING KEY
_To be written after the run:_ does any CURRENT Claude model — especially **Haiku 5.5**, which on list price is
**cheaper than today's `gpt-4.1-mini`** — write **better** tours than the baseline, and at what **time** and
**price**, stated as "yes / no / only if", holding under **both** judges and read against the 2-point single-tour
noise floor. Nothing changes in production until Michael sees the numbers (D674).

## How to run (LEAD, once the key is present)
```
# inside the generator container (meter + keys + DB), OWN container, cache/pool OFF
python3 replay_harness.py run-all --out /app/bench_out --arms BHIJ
python3 score_stops.py detectors  --dir /app/bench_out --arms BHIJ
python3 score_stops.py blind      --dir /app/bench_out --arms BHIJ     # relabel; key in _blind/blind_key.json
python3 score_stops.py kiro       --dir /app/bench_out --arms BHIJ     # judge 1
python3 score_stops.py gpt        --dir /app/bench_out --arms BHIJ     # judge 2 (gpt-4.1)
python3 report.py                 --dir /app/bench_out --host local712-gen --arms BHIJ --baseline B
```
To run the whole D674 field (LOCAL-712 + current lineup) in one pass, use `--arms BFGHIJ` (the default for
`run-all`). Then the 3 full tours per arm (own container, spare port, cache/pool OFF, is_test), honouring the
$3.00 cap.

## Code + tests (LOCAL-712B)
- `cost_rates.py` + `_meter/paid_api_meter.py`: the three current-lineup rates (above), LOCAL-712 rows untouched.
- `replay_harness.py`: arms H/I/J, extended `D674_ARMS`, updated docstring + `run-all` default; `call_anthropic`
  unchanged (model-agnostic).
- `score_stops.py` (`ARMS` A–J) and `report.py` (`ARMS` A–J, `ARM_LABEL` H/I/J) so the blind/judge/report flow
  carries the new arms. `report._model_matches` verified not to cross `claude-sonnet-5` with `claude-sonnet-5-5`.
- Tests: `tests/test_local712b_current_claude.py` (23 stubbed-HTTP tests: rates, substring non-collision, meter
  rows, request shape, key-gate, scorer/report arm tables). The existing `tests/test_local712_anthropic_provider.py`
  stays green (one `D674_ARMS` assertion updated to the extended set; the F/G arm checks are unchanged).
