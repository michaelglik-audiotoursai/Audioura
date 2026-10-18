# SUBMISSION — LOCAL-712: Claude as narration/story model (provider hook + bake-off arms, D674)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-712-claude-bakeoff` · **Base:** subscribed @ `18028ba8`
**Status:** steps 1–3 built and unit-tested. **AWAITING `ANTHROPIC_API_KEY`** — the live bench did NOT run (key gate, see §5). LEAD runs the bench once Michael adds the key.

## What Michael asked (D674)
*"Substitute OpenAI and/or Gemini with Amazon Q or Claude. Can you experiment and tell me if the quality of the tour, generation time and price would increase?"*

Per the D674 ruling: **Amazon Q is not a candidate** (it is an assistant product, not a pipeline text API; Amazon's route to these models is Bedrock, a later option only if Claude wins). **Claude is the candidate, through the Anthropic API.** This task wires Claude in as a narration/story-pass provider and sets up the bake-off arms, reusing the LOCAL-647 harness exactly as D674 directs.

## 1. The `anthropic` provider (build step 1)
- **Narration hook** `generate_tour_text.narration_model_route()` gains an `anthropic` branch:
  `NARRATION_PROVIDER=anthropic` → `("anthropic", NARRATION_MODEL or "claude-haiku-4-5-20251001")`.
  **The default is byte-for-byte unchanged:** with nothing set the hook still returns `("openai", story_pass_model())` (today's OpenAI story pass). Verified by test and by direct call (`('openai', 'gpt-4o')` with the env clean).
- **The call** (`replay_harness.call_anthropic`) is plain HTTPS (`requests`) to `https://api.anthropic.com/v1/messages`, headers `x-api-key` and `anthropic-version: 2023-06-01`. No SDK was added to the images.
  - The **system message goes in the top-level `system` field** (not a message); the user prompt is the single user message.
  - `max_tokens` (required by Anthropic) = 1000 and `temperature` = 0.7 **mirror the OpenAI arm**, so the only variable across arms stays the model.
  - Token usage is read from the response (`usage.input_tokens` / `output_tokens`, plus `cache_read_input_tokens`) and normalised to the OpenAI-shaped keys the report already aggregates.
- **Metering:** the existing network paid-API meter (`_meter/paid_api_meter.py`, the `paid_api_calls` ledger) now recognises `api.anthropic.com` as `kind="anthropic"`, prices it from the official Claude rates (input / output / cache-read), and writes one row per call the same way OpenAI calls are metered. A non-200 is still recorded (attributable) at `$0`, exactly like the OpenAI path.

## 2. Rates (build step 2) — `cost_rates.py` + the meter
Added to `cost_rates.LLM_RATES` **and** the meter's rate table, both with the source URL and read-date inline:

| Model | Input $/MTok | Output $/MTok | Cache-read $/MTok |
|-------|-------------:|--------------:|------------------:|
| Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | 1.00 | 5.00 | 0.10 |
| Claude Sonnet 5 (`claude-sonnet-5`) | 2.00 | 10.00 | 0.20 |

**Source:** <https://docs.anthropic.com/en/docs/about-claude/pricing> — **read 2026-10-18.** Both prices are confirmed from the official page (the "Additional models" block of the Model-pricing table); **no price was guessed.**

> Note for LEAD: the live docs page now also lists a newer lineup (Haiku 5.5, Sonnet 5.5) — a time skew on the page. The two D674 arm models (Haiku 4.5, Sonnet 5) are the ones named in the ticket and both appear with the prices above. The narration call sends no `cache_control`, so only the base input/output rates normally apply; the cache-read rate is carried so a future cached run is priced correctly.

## 3. Harness arms + blind double-judging (build step 3)
- **Arms** (`replay_harness.ARMS`), on the SAME 12 stored stops with identical inputs, next to today's `gpt-4.1-mini`:
  - `B` = `gpt-4.1-mini` (today's narration model — the baseline)
  - `F` = `claude-haiku-4-5-20251001`
  - `G` = `claude-sonnet-5`
  - `D674_ARMS = ("B","F","G")`; `run-all` and `store` default to these three. Pass `--arms ABCDE` to reproduce the original five-arm LOCAL-647 run.
- **Blind judging, twice** (`score_stops.py`):
  - `blind` relabels the arms to random labels, scrubbing the model name from the per-stop files, and writes the real→blind key to a **separate** file (`_blind/blind_key.json`) the judges never read.
  - `kiro` — judge 1, the usual Kiro single-stop rubric.
  - `gpt` — judge 2, a **gpt-4.1 judge** given the SAME rubric (plain `requests.post` to OpenAI, so the meter prices it inside the ≤ $3 budget). Needed because Kiro itself runs on Claude; a Claude "win" must hold under a non-Claude judge too.
- **Report** (`report.py`) prints per-arm **mean, min, $/stop (from the ledger), median seconds** under **each** judge, and flags which arms are within 0.3 of the baseline (arm B) under both. `$/stop` comes from `paid_api_calls` (host `local712-gen`), not an estimate.

## 4. Tests (stubbed HTTP, no network, no DB)
`tests/test_local712_anthropic_provider.py` — **16 tests, all green.** They cover exactly the five things the ticket lists:
- **request shape** — system in the top-level `system` field, model, `max_tokens`, `temperature`, and the `x-api-key` / `anthropic-version` headers;
- **usage → cost** — `cost_rates.llm_cost` and the meter's `_anthropic_cost` both price Claude usage (cache-read included) from the official rates;
- **meter row written** — a 200 response writes one `kind="anthropic"` row with model/usage/$;
- **error/timeout → same fallback as OpenAI** — an HTTP error returns `[HTTP n] …` with no usage; a timeout propagates; a non-200 meter row is `$0`;
- **unset provider → unchanged** — the default route equals `story_pass_model()`; `anthropic`/`gemini` branches opt in.

Regression: the narration/cost/meter suites stay green — **95 passed** across `test_d370_story_pass_model`, `test_pricing`, `test_d515_replay`, `test_local678_meter_httpx_aiohttp`, `test_local197`, `test_local143`, `test_local594`, `test_local609`; plus `test_local60/613/615/707/603` and the new suite = **97 passed** in that batch. The only failures seen (4, in `tests/test_local326_phase_boundary_cost.py`) are **pre-existing** — they fail identically with these changes stashed and need the `postgres-2` DB host + a cost-ceiling env that is not present on this host. They are unrelated to LOCAL-712.

## 5. Key gate — AWAITING `ANTHROPIC_API_KEY`
`ANTHROPIC_API_KEY` is **empty** (checked by length only, never printed) in both the shell environment **and** `~/Audioura/.env`. Per the ticket, steps 1–3 are finished with stub tests and **I STOPPED before any real call.** No live 12-stop replay, no judging, no full tours, $0 spent.

**LEAD runs the bench once Michael adds the key.** The commands are:
```
# in the generator container (meter + keys + DB), own container only, cache/pool OFF:
python3 replay_harness.py run-all --out /app/bench_out --arms BFG     # 12 stops × B,F,G
python3 score_stops.py detectors  --dir /app/bench_out --arms BFG
python3 score_stops.py blind      --dir /app/bench_out --arms BFG
python3 score_stops.py kiro       --dir /app/bench_out --arms BFG     # judge 1
python3 score_stops.py gpt        --dir /app/bench_out --arms BFG     # judge 2 (gpt-4.1)
python3 report.py                 --dir /app/bench_out --host local712-gen --arms BFG --baseline B
```
Then 3 full tours per arm (Courtauld, Walters, Faneuil Hall walking) in an own container on a spare port, cache + pool OFF, is_test rows only, **budget cap $3.00 total — stop and report if reached.** Fill the tables in `.continuous_dev/bench/BAKEOFF_LOCAL-712.md`.

## 6. Files changed
- `generate_tour_text.py` — `narration_model_route()` `anthropic` branch (default unchanged).
- `cost_rates.py` — Claude Haiku 4.5 / Sonnet 5 rates + source/date.
- `_meter/paid_api_meter.py` — `anthropic` host kind, `ANTHROPIC` rate table, `_anthropic_cost()`, `_record()` branch.
- `replay_harness.py` — arms F/G, `D674_ARMS`, `call_anthropic()`, dispatch, `run-all`/`store` defaults.
- `score_stops.py` — gpt-4.1 judge (`gpt_judge_one` + `run_gpt_judge` driver), `blind` relabel, arms A–G.
- `report.py` — both-judge table, Claude arm labels, anthropic dated-id match, baseline arm B.
- `tests/test_local712_anthropic_provider.py` — new stub-HTTP unit suite (16 tests).
- `.continuous_dev/bench/BAKEOFF_LOCAL-712.md` — method + table scaffolds (awaiting the live run).

**Nothing changes in production** — the default narration path is untouched until Michael sees the table (D674).
