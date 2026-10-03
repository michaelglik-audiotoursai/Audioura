# LOCAL-568 — Does the story retry pay? Retry-yield analysis

**Agent:** Mac Mini Kiro **Branch:** LOCAL-568-retry-yield **Base:** subscribed (02aa094)
**Mode:** offline. No OpenAI / Gemini / Serper / Polly calls. All numbers are
reconstructed from recorded logs on disk.

Fixture: [`tests/fixtures/local568/retry_yield.json`](tests/fixtures/local568/retry_yield.json)
(reproducible: `parse_logs.py` rebuilds `parsed_trajectories.json` from the raw
logs; `gen_retry_yield.py` rebuilds `retry_yield.json` from that).

---

## 1. What the loops do (code read)

All citations are `generate_tour_text.py` on this branch.

**The loop.** Every stop description is generated inside one retry loop:
`_max_retries = 4` (**:14236**) and `for _attempt in range(_max_retries + 1)`
(**:14239**) → **5 attempts maximum**, numbered 1..5 in the logs as `attempt K/5`.

**LOCAL-432 story retry** (trigger block **:14560–14672**). After a draft is
produced, if the tour is `_storied_mode and tour_category == 'museum'`, the text
is real prose (not a `[`-prefixed fallback), `_attempt < _max_retries`, **and**
`_l431_story_count < 3` (**:14577** — threshold is **3 story sentences**;
`min_story_sentences = 3` in `story_gate.py:382/530`, counted by
`extract_story_sentences`), the loop:
  - **re-sends the entire stop**: it *appends* a reinforcement user message to
    `description_data["messages"]` naming the exact deficit, listing the
    sentences that failed the classifier with reasons, and listing available
    people from the beats, then bumps temperature and `continue`s. Each attempt
    is a **full rewrite** of the whole stop, re-scored from scratch.
  - prints `[LOCAL-432] … STORY RETRY — story_count=C < 3 … (attempt K/5)` (**:14660**).

**LOCAL-417 positive gate** (**:14340–14455**). Independent of the story count:
a draft fails if it doesn't name its subject, carries no concrete fact (date /
measurement / material / provenance verb), or contains operator-directed
language. On failure it `continue`s (retries) within the same 5-attempt loop;
on exhaustion it calls `resolve_final_description`. Word-floor (LOCAL-393),
missing-beat (LOCAL-391) and metadata-binding (LOCAL-98) retries share the loop
too — so not every attempt is a *story* retry.

**Which attempt is kept — the LAST, not the best.** On the normal success path
the function returns the *current* attempt's text:
`return idx, orientation, description, word_count, tokens_used, call_cost`
(**:14980**). There is **no keep-best-by-story_count logic** on the story path.
The only "best" selection is `resolve_final_description` (**:5739**, returns
`_best[1]` at **:5782**) and `_best_description`, and both pick the attempt with
the **longest word count**, not the highest story_count — and only on the
gate-failure / API-failure / loop-exhaustion fallback branches, never on the
story-retry success path.

**Consequence — later attempts frequently score *lower*.** Because the kept
attempt is the last one, and each rewrite is re-rolled at higher temperature,
the pipeline regularly ships a draft worse than one it already produced. In the
logs, **24 of 42** story-retry episodes contained at least one attempt whose
story_count was strictly *below* a prior attempt's, and in **12 of 42** the
shipped (last) attempt scored below an earlier attempt's observed count. Example
(`local566_after`, stop 2): story_count went `1 → 0 → 2 → 1` and attempt 4's
`1` was shipped, discarding attempt 3's `2`.

---

## 2. Yield table

**Scope.** LOCAL-432 only fires for `tour_category == 'museum'`. The restaurant
and airport tours in the sources (chart_house, logan_airport) retried for other
gates and never for story count, so they are excluded. The story-retry dataset
is **n = 42 stop-episodes** — one stop within one generation pass (the recorded
logs replay ~2 passes per tour; each is an independent instance of the loop):

| Tour | Episodes | Source runs |
|---|---|---|
| Palais Lascaris (Nice) | 35 | local560 recordings, local563 run1+run2, local566 before+after |
| MFA Boston | 7 | local566 LOCAL518 |

Per-stop `story_count` after each attempt and writer $ are in the fixture
(`yield_table_per_stop`, 42 rows). Representative rows (writer $ = sum of the
per-attempt gpt-4o `Stop N API call cost` lines, priced at the model actually
used per D370):

| tour / run | stop | sc@1 | sc@2 | sc@3 | sc@4 | sc@5 | first meets 3 | writer $ |
|---|---|---|---|---|---|---|---|---|
| palais / local560 | 4 | 2 | 1 | 1 | 2 | — | never | 0.224 |
| palais / local560 | 1 | 1 | 0 | 2 | 3 | — | **4** | 0.173 |
| palais / local563_run1 | 1 | 2 | 3 | — | — | — | **2** | 0.075 |
| palais / local563_run2 | 3 | 0 | 0 | 0 | 1 | — | never | 0.228 |
| palais / local566_after | 3 | 1 | 2 | 3 | — | — | **3** | 0.132 |
| palais / local566_after | 2 | 1 | 0 | 2 | 1 | — | never | 0.214 |
| MFA / LOCAL518 | 3 | 1 | 3 | — | — | — | **2** | 0.082 |
| MFA / LOCAL518 | 1 | 0 | 2 | 1 | 0 | — | never | 0.203 |

`sc@5 = —` means the loop reached attempt 5 and the final count is not logged
(the last attempt is shipped regardless). **First attempt to meet the 3-sentence
threshold, across all 42:**

| first meets threshold at | k=1 | k=2 | k=3 | k=4 | k=5 | never |
|---|---|---|---|---|---|---|
| count | 0 | 4 | 3 | 10 | 0 | **25** |

**59.5% (25/42) never reach 3 story sentences even after all 5 attempts.** k=1
is 0 by construction (an episode exists only because attempt 1 was short).

---

## 3. Marginal value per attempt

| attempt k | P(threshold first met at k) | mean story_count gain vs k−1 | mean $ on attempt k | n ran k |
|---|---|---|---|---|
| 2 | 9.5% (4/42) | +0.35 | $0.0419 | 42 |
| 3 | 7.1% (3/42) | +0.03 | $0.0438 | 38 |
| 4 | 23.8% (10/42) | +0.43 | $0.0456 | 35 |
| 5 | **0.0% (0/42)** | n/a (no new meets) | $0.0471 | 25 |

Attempt 5 earns its money **zero** times. Attempt 3's rewrite moves the count by
0.03 sentences on average — indistinguishable from zero.

**Counterfactual — final story_count and writer $ per stop under each cap,
keeping the best attempt so far:**

| cap | mean final story_count | % stops ≥ 3 | mean writer $ / stop | mean writer $ / 4-stop tour |
|---|---|---|---|---|
| 1 | 1.22 | 0% | $0.040 | $0.16 |
| 2 | 1.76 | 9.5% | $0.082 | $0.33 |
| 3 | 1.90 | 16.7% | $0.122 | $0.49 |
| 4 | **2.24** | 40.5% | $0.160 | $0.64 |
| 5 (today) | **2.24** | 40.5% | $0.188 | $0.75 |

cap-4 and cap-5 are **identical** on story_count — attempt 5 is pure waste.

---

## 4. Recommendation

**The LOCAL-563 noise floor in story_count is ≈ 1.5 sentences:** for the same
request run twice (local563 run1 vs run2), attempt-1 story_count differed by a
mean of 1.5 (max 2) across the four Palais stops, and the attempt-to-attempt
swing of a forced rewrite averages 1.43 (max 3) — a rewrite moves the count
about as much as simply re-running the prompt. Against that floor, **every cap
from 2 upward loses story_count that is within noise versus today's cap of 5**
(cap-4 Δ=0.00, cap-3 Δ=0.33, cap-2 Δ=0.48, all ≤ 1.5). The cap that saves the
most money while staying inside the noise floor is **cap = 2**, saving ≈
**$0.11/stop (~$0.42 on a 4-stop museum tour, ~56% of the retry spend)** for a
0.48-sentence drop that the baseline's own run-to-run noise already exceeds. The
safe-and-obvious floor, if 0.48 feels too aggressive, is **cap = 4**: free
money ($0.028/stop, ~$0.11/tour) at exactly zero story_count cost. But the
larger finding is that **the retry barely works at all** — 59.5% of stops never
reach the bar, attempt 3 and attempt 5 each add essentially nothing, and because
the loop ships the *last* attempt rather than the best (code §1), 12/42 stops
shipped text measurably worse than a draft already in hand. So the highest-value
change is not just a cap but a rule: **keep the best attempt by story_count, and
stop as soon as an attempt fails to beat the running best** (equivalently, cap at
2–3 with keep-best). That captures nearly all the yield the loop ever delivers,
stops paying gpt-4o to make stops worse, and removes the attempt-5 spend that
buys nothing.

**Confidence — honest and low-to-moderate.** n = 42 is small and dominated by a
single venue: 35 of 42 episodes are Palais Lascaris (a French instrument
collection that is genuinely story-poor — thin sourced material, which is *why*
it retries), and only 7 are MFA. The counts come from the production classifier
as logged, and the final attempt's story_count is unobserved when the loop runs
to 5/5 (we never credit it with meeting the bar). The direction is robust and
consistent across all five source runs — attempt 5 never pays, the retry rarely
clears the bar, keeping-last ships regressions — but the exact dollar figures
should be treated as directional, not definitive, until a wider venue sample
(more museums, not more Palais runs) confirms them.

---

### Method / provenance

Sources read read-only via `git show` from branch tips (no checkout of stale
trees):

- `LOCAL-560-checker-model@d92bbb7` → `tests/fixtures/local560/recordings/palais_lascaris_nice.log`
- `LOCAL-563-gemini-baseline@707e303` → `tests/fixtures/local563/runs/lascaris_run{1,2}.log`
- `LOCAL-566-writer-cost@255f826` → `tests/fixtures/local566/measure/palais_{before,after}.log` and `LOCAL518_museum_of_fine_arts_boston_ma.log`

Per-attempt signal: each `Stop N API call cost: $X (T tokens, model=gpt-4o)` line
is one attempt; a following `[LOCAL-432] … story_count=C … (attempt K/5)`
annotates attempt K−1 with count C; `Stop N description word count: W words`
closes the loop (last attempt kept). Cost reconciles in magnitude with
`cost_record.breakdown.llm` in the local563 summaries.

No production files changed. No DB writes, no GCloud, no deletes, no generation calls.
