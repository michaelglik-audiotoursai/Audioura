# SUBMISSION — LOCAL-712B: the CURRENT Claude lineup as bake-off arms (D674 addendum 2)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-712B-current-claude` · **Base:** subscribed @ `3cd84e88`
**Status:** build + unit tests done and green. **AWAITING `ANTHROPIC_API_KEY`** — no live bench ran (key gate, §5). LEAD runs the bench once Michael adds the key.

## What this adds
LOCAL-712 wired the Anthropic provider with **Haiku 4.5** and **Sonnet 5**. Anthropic's pricing page now lists a
newer lineup. This addendum adds those three — **Haiku 5.5, Sonnet 5.5, Opus 5.5** — as **extra** bake-off arms,
**keeping** the LOCAL-712 arms (Haiku 4.5 / Sonnet 5) and today's `gpt-4.1-mini` baseline. The blind
double-judging, identical inputs, reused production prompt and the key gate are all unchanged from LOCAL-712.

**Haiku 5.5 is the arm that matters most:** on list price it is **cheaper than our `gpt-4.1-mini`**
($0.10/$0.50 vs $0.40/$1.60 per MTok for prompts ≤100k), so it is the first real chance to lower narration cost
*and* possibly raise quality.

## 1. Model IDs — confirmed, not guessed
Model IDs read from the Anthropic **Models-overview** page (`.../about-claude/models/overview`); prices from the
**Pricing** page (`.../about-claude/pricing`). **Read 2026-10-18.** All three IDs are confirmed on the overview
page's "Claude API ID" row, so no arm was left out.

| Model | Claude API ID | Input $/MTok | Output $/MTok | Cache-hit $/MTok |
|-------|---------------|-------------:|--------------:|-----------------:|
| Claude Haiku 5.5 | `claude-haiku-5-5` | **0.10** (≤100k) | **0.50** (≤100k) | 0.01 |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 2.00 | 10.00 | 0.10 |
| Claude Opus 5.5 | `claude-opus-5-5` | 4.00 | 20.00 | 0.20 |

**Haiku 5.5 >100k tier:** above 100,000 prompt tokens the rate rises to **$0.50 in / $2.50 out**. Our narration
prompts are ~3k tokens, so only the ≤100k tier ever applies; the ≤100k rate is keyed and the >100k tier is
recorded as a note in both rate tables. **Opus "fast mode" ($8/$40) is NOT used.**

## 2. Rates — `cost_rates.py` + the meter
The three rates are added to `cost_rates.LLM_RATES` **and** the meter's `ANTHROPIC` table, each with the source
URL + read date inline and the Haiku-5.5 >100k tier noted. **The LOCAL-712 rows (Haiku 4.5 $1/$5, Sonnet 5
$2/$10) are left exactly as they were.**

A subtlety handled and unit-tested: `claude-sonnet-5` is a substring of `claude-sonnet-5-5`. Both resolvers use
**longest-key-wins**, so `claude-sonnet-5-5` prices at the 5.5 rate and the older `claude-sonnet-5` still prices
at the Sonnet-5 rate — no cross-contamination (same for Haiku). The meter's `_anthropic_cost` and
`cost_rates._resolve_model_rates` are both covered.

## 3. Harness arms + judging
- **New arms** (`replay_harness.ARMS`), on the SAME 12 stored stops with identical inputs:
  - `H` = `claude-haiku-5-5`
  - `I` = `claude-sonnet-5-5`
  - `J` = `claude-opus-5-5`
- The LOCAL-712 arms `F`/`G` and the `A`/`B`/`C`/`D`/`E` arms are untouched.
- `D674_ARMS` is now `("B","F","G","H","I","J")` — baseline + both the LOCAL-712 and current Claude arms.
  `run-all`/`store` default to this set; pass `--arms BHIJ` for only the current lineup, `--arms BFG` for only
  the original LOCAL-712 comparison.
- The new arms route through the **same, model-agnostic** `call_anthropic()` (same `/v1/messages` endpoint,
  system in the top-level `system` field, `max_tokens=1000`, `temperature=0.7`), so the only variable across
  every arm stays the model string. **Blind double-judging (Kiro + gpt-4.1) is exactly as in LOCAL-712** —
  `score_stops.py` `ARMS` and `report.py` `ARMS`/`ARM_LABEL` carry A–J.

## 4. Tests (stubbed HTTP, no network, no DB)
`tests/test_local712b_current_claude.py` — **23 tests, all green.**
- **rates** — the three current rates in `cost_rates.LLM_RATES` and the meter; `llm_cost` and `_anthropic_cost`
  price each correctly, cache-read included; Haiku 5.5 confirmed cheaper than `gpt-4.1-mini`.
- **substring non-collision** — `claude-sonnet-5-5` vs `claude-sonnet-5` resolve to their own rates in both the
  cost module and the meter; `report._model_matches` does not cross them in the ledger.
- **meter row** — a 200 response for a current model writes one `kind="anthropic"` row with model/usage/$.
- **request shape** — a current-arm call (Opus 5.5) sends the identical request shape as the LOCAL-712 arms.
- **key gate** — with `ANTHROPIC_API_KEY` unset, `call_anthropic` raises `KeyError` **before any HTTP call**
  (the stubbed `requests.post` asserts it is never reached).
- **arm tables** — `score_stops.ARMS` and `report.ARM_LABEL` include H/I/J and keep A–G.

**Existing LOCAL-712 suite stays green:** `tests/test_local712_anthropic_provider.py` passes; the only edit there
is one assertion updated from `D674_ARMS == ("B","F","G")` to the extended set (the F/G arm-definition checks are
unchanged). Running the two Claude suites together: **32 passed.** Running every suite that touches the changed
modules (cost_rates / meter / harness / report / score_stops across LOCAL-60/143/197/323/578/594/603/609/613/615/
673/678/707/712/712B): **159 passed.**

One test-isolation fix was required and is worth noting: the project has **two** modules named `report`
(`./report.py` and `./canary/report.py`). In the full suite, whichever test imports first wins
`sys.modules['report']`, so a plain `import report` in my test could pick up the canary module (no `ARM_LABEL`).
The two report-touching tests therefore load the project-root `report.py` **by file path**, making them immune to
suite ordering. With that fix, **zero** LOCAL-712/712B tests fail in the full suite run.

## 5. Key gate — AWAITING `ANTHROPIC_API_KEY`
The key gate is unchanged from LOCAL-712: `call_anthropic` reads `os.environ['ANTHROPIC_API_KEY']` and raises
before any request if it is absent (length-checked, never printed). **No real Anthropic or OpenAI call was made;
$0 spent.** LEAD runs the bench once Michael adds the key:
```
# in the generator container (meter + keys + DB), own container only, cache/pool OFF:
python3 replay_harness.py run-all --out /app/bench_out --arms BHIJ     # 12 stops × B,H,I,J
python3 score_stops.py detectors  --dir /app/bench_out --arms BHIJ
python3 score_stops.py blind      --dir /app/bench_out --arms BHIJ
python3 score_stops.py kiro       --dir /app/bench_out --arms BHIJ     # judge 1
python3 score_stops.py gpt        --dir /app/bench_out --arms BHIJ     # judge 2 (gpt-4.1)
python3 report.py                 --dir /app/bench_out --host local712-gen --arms BHIJ --baseline B
```
Use `--arms BFGHIJ` to run the whole D674 field (LOCAL-712 + current lineup) in one pass. Then 3 full tours per
arm (own container, spare port, cache/pool OFF, is_test rows only), **budget cap $3.00 total — stop and report if
reached.** Fill the tables in `.continuous_dev/bench/BAKEOFF_LOCAL-712.md` (Addendum 2).

## 6. Files changed
- `cost_rates.py` — Claude Haiku 5.5 / Sonnet 5.5 / Opus 5.5 rates + source/date + Haiku 5.5 >100k note (712 rows untouched).
- `_meter/paid_api_meter.py` — the same three in the `ANTHROPIC` rate table with cache-read tier.
- `replay_harness.py` — arms H/I/J, extended `D674_ARMS`, updated docstring + `run-all` default (`call_anthropic` unchanged).
- `score_stops.py` — `ARMS` A–J.
- `report.py` — `ARMS` A–J, `ARM_LABEL` H/I/J.
- `tests/test_local712b_current_claude.py` — new stub-HTTP unit suite (23 tests).
- `tests/test_local712_anthropic_provider.py` — one `D674_ARMS` assertion updated to the extended set.
- `.continuous_dev/bench/BAKEOFF_LOCAL-712.md` — Addendum 2 (current-lineup method + table scaffolds, awaiting the live run).

**Nothing changes in production** — the default narration path is untouched; these are measurement-only arms until Michael sees the numbers (D674).
