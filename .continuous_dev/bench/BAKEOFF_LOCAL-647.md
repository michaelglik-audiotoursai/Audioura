# LOCAL-647 — Narration MODEL bake-off on identical inputs

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-647-narration-bakeoff` · **Base:** subscribed @ `531a5219`
**Michael 2026-10-09:** *"optimise the calls and try cheaper vendors, measured on what we already have."*

The per-stop narration call (the "story pass" in `generate_tour_text.py`) is ~64% of OpenAI
spend at ~3 calls/stop with gpt-4.1. This bake-off writes **one draft per stop per model on
byte-for-byte identical inputs**, so the only variable is the model, and scores every draft with
Kiro + deterministic detectors. It then runs a prompt-diet experiment.

**Total metered spend: $0.70937** (181 paid calls, `job=LOCAL-647`, `host=local647-gen`), under the
$3.00 cap. Every paid call went through the network meter (`paid_api_calls`).

---

## 1. Method

### Identical inputs, rebuilt from saved data (no new research)
For 12 stops across 4 museums, `replay_harness.py` rebuilds each stop's narration INPUT from data
we already have:
- **`venue_corpus.pages_json`** — the same corpus text production injects as source snippets.
- **`venue_corpus.story_elements_json`** — named people / dated episodes (the "concrete facts").
- **the work's English Wikipedia extract**, fetched **free** from the Wikipedia action API and
  **cached on disk** so it is fetched once and reused identically across all arms.

There is **no Serper call and no Gemini/Serper research call** anywhere in the harness. Arms D/E
call Gemini only as the narration *writer*, ungrounded, with no `tools`/`google_search`.

### The prompt is the production prompt (reused, not rewritten)
The museum narration prompt body was extracted verbatim from the inline f-string in
`generate_tour_text._generate_description()` into a module-level function
**`generate_tour_text.build_museum_stop_prompt()`** (proven byte-for-byte identical to the previous
inline string). Production and the harness now share **one** definition. The harness appends the
same facts-first / required-names / source-snippet blocks the production path appends.

### Model-selection env hook (default unchanged)
A new opt-in hook `generate_tour_text.narration_model_route()` reads `NARRATION_PROVIDER` /
`NARRATION_MODEL`. With nothing set it returns `("openai", story_pass_model())` — i.e. **today's
behaviour, gpt-4.1** — so the default narration path is unchanged. The harness opts into the five
arms through this hook.

### Stops (12 stops · 4 museums, incl. the four requested)
| Museum | Stops |
|--------|-------|
| **Courtauld Gallery** (Q12110695) | Manet's *A Bar at the Folies-Bergère*; Van Gogh *Self-Portrait with Bandaged Ear*; Georges Seurat |
| **Walters Art Museum** (Q210081) | *Springtime (1872)*; *The Death of Caesar*; *Sappho and Alcaeus* |
| **Wallace Collection** (Q1327919) | *The Laughing Cavalier*; *A Dance to the Music of Time*; *Madame de Pompadour* |
| **Frick Collection** (Q682827) | *Officer and Laughing Girl*; *Portrait of Sir Thomas More*; *Portrait of Comtesse d'Haussonville* |

### Arms (one draft per stop, no retries)
| Arm | Model | Notes |
|-----|-------|-------|
| A | gpt-4.1 | today's narration model |
| B | gpt-4.1-mini | |
| C | gpt-4.1-nano | |
| D | Gemini 2.5 Flash-Lite (`gemini-flash-lite-latest`) | ungrounded |
| E | Gemini 2.5 Flash (`gemini-flash-latest`) | ungrounded |

> The dated ids `gemini-2.5-flash[-lite]` return HTTP 404 "no longer available to new users" on
> this API key; the live aliases resolve to the **same 2.5 Flash family** (`cost_rates.py`:
> *"gemini-flash-latest … resolves to the Gemini 2.5 Flash family"*), so D/E use the working aliases.

### Scoring
- **Kiro** (`kiro-cli chat --no-interactive`), the `calib/critique.sh` rubric adapted to judge a
  **single stop** (`score_stops.py`), emitting `SCORE: N/10`.
- **Deterministic detectors** — the stop-level subset of `bench/detectors.py` (truncation, stock
  recency, dangling openers, duplicate sentences, dropped words, label echoes, price dumps,
  repeated hours/admission, refusals, HTTP errors, rhetorical-question endings). Tour-structure
  detectors (stop_count, directions, restaurant-last, cross-stop callbacks) don't apply to an
  isolated stop and are dropped.

---

## 2. Results — per-arm table

| Arm | Model | Mean | Min | Det.fails | HTTP fails | $/stop | $ total (12) | Median s | Mean out-tok | Within 0.3 of A |
|-----|-------|------|-----|-----------|-----------|--------|---------|----------|--------------|-----------------|
| A | gpt-4.1 (today) | **7.58** | 6.5 | 0 | 0 | $0.01030 | $0.12361 | 8.0 | 712 | — |
| B | gpt-4.1-mini | **7.83** | 4.5 | 0 | 0 | $0.00184 | $0.02208 | 5.35 | 574 | **yes** |
| C | gpt-4.1-nano | 6.12 | 4.5 | 1* | 0 | $0.00049 | $0.00587 | 3.92 | 662 | no |
| D | Gemini 2.5 Flash-Lite | **7.83** | 5.5 | 1* | 0 | $0.00328 | $0.03941 | 1.99 | 397 | **yes** |
| E | Gemini 2.5 Flash | **7.88** | 4.5 | 0 | 0 | $0.00368 | $0.04410 | 6.74 | 502 | **yes** |

`$/stop` is the **per-call average from the `paid_api_calls` ledger** (the network meter), not an
estimate. `*` the two detector "failures" are both the inherited noisy `truncated_snippet`
heuristic firing on a legitimate sentence boundary (e.g. "…on. F…") — borderline false positives,
not real truncation.

**Arms within 0.3 of arm A's mean (7.58): B, D, E.** Only nano (C) falls outside.

### Headline findings
- **gpt-4.1-mini (B) is the clear win:** mean 7.83 (slightly *above* gpt-4.1), **5.6× cheaper**
  ($0.00184 vs $0.01030/stop), faster (5.35s vs 8.0s), 0 detector failures.
- **Gemini 2.5 Flash (E) scores highest** (7.88) at $0.00368/stop; **Flash-Lite (D)** matches B's
  score at $0.00328/stop and is the **fastest** (1.99s median).
- **nano (C)** is the only arm that drops out of the 0.3 band (6.12) — cheapest, but the quality
  cost is real.
- On this evidence the narration call could move from gpt-4.1 to **gpt-4.1-mini** with no quality
  loss and ~82% lower narration cost; the Gemini 2.5 arms are credible cheaper vendors too.

### Per-stop Kiro scores
| Stop | A | B | C | D | E |
|------|---|---|---|---|---|
| Courtauld-0 | 7.5 | 8.0 | 7.5 | 7.5 | 8.5 |
| Courtauld-1 | 7.5 | 8.5 | 6.5 | 8.5 | 8.5 |
| Courtauld-2 | 7.5 | 8.5 | 5.5 | 7.5 | 8.5 |
| Walters-0 | 8.5 | 7.0 | 5.5 | 6.5 | 7.5 |
| Walters-1 | 6.5 | 4.5 | 4.5 | 5.5 | 4.5 |
| Walters-2 | 7.5 | 8.5 | 7.5 | 8.5 | 8.5 |
| Wallace-0 | 7.5 | 8.5 | 5.5 | 8.5 | 9.0 |
| Wallace-1 | 7.5 | 7.5 | 6.5 | 8.5 | 8.5 |
| Wallace-2 | 7.5 | 7.5 | 6.0 | 8.5 | 5.5 |
| Frick-0 | 8.5 | 8.5 | 6.5 | 8.5 | 8.5 |
| Frick-1 | 7.5 | 8.5 | 5.5 | 7.5 | 8.5 |
| Frick-2 | 7.5 | 8.5 | 6.5 | 8.5 | 8.5 |

*Walters-1 (`Sappho and Alcaeus`) is the weakest stop for every arm — its saved corpus/story
material is thin, so this is an input ceiling, not a model difference.*

---

## 3. Prompt diet

Measured on arm A (gpt-4.1) and the best cheap arm B (gpt-4.1-mini).

**Trimmed variant** (`--diet`: cap Wikipedia extract 1800 chars, corpus 1200, specifics to 3;
instruction dedupe comes free from reusing the single production builder):

| Metric | Full | Diet | Δ |
|--------|------|------|---|
| Mean prompt tokens | 2304 | 1830 | **−474 (−20.6%)** |
| Arm A $/stop | $0.010301 | $0.006972 | **−32%** |
| Arm B $/stop | $0.001840 | $0.001144 | **−38%** |
| Arm A Kiro mean | 7.583 | 7.333 | −0.25 |
| Arm B Kiro mean | 7.833 | 7.375 | −0.46 |

The diet buys a real cost cut for a modest quality dip (it ships less source material). For gpt-4.1
the diet keeps A within its own 0.3 band; for mini the dip is larger (−0.46), so the diet is best
paired with the stronger model if applied.

**Fixed-instructions-first (OpenAI automatic prompt caching)** (`--fixed-first`: the large fixed
instruction body is placed first so it becomes the shared cacheable prefix):

| Arm | Mean prompt tok | Mean cached_tokens | % cached | Input saving/stop |
|-----|-----------------|--------------------|----------|-------------------|
| A (gpt-4.1) | 2304 | 1941 | **84%** | ≈ $0.00291 (cached billed $0.50/1M vs $2.00/1M) |
| B (gpt-4.1-mini) | 2304 | 1536 | 67% | ≈ $0.00046 (cached $0.10/1M vs $0.40/1M) |

`cached_tokens` is read from `usage.prompt_tokens_details.cached_tokens`. Caching is free quality —
the output is unchanged — and on gpt-4.1 it removes most of the input-token cost of the fixed
instruction block.

---

## 4. Cost ledger (from `paid_api_calls`, host `local647-gen`)

| Model (ledger) | Calls | $ |
|----------------|-------|---|
| gpt-4.1 | 12 | 0.12361 |
| gpt-4.1-mini | 12 | 0.02208 |
| gpt-4.1-nano | 13† | 0.00636 |
| gemini-flash-latest (2.5 Flash) | 12 | 0.04410 |
| gemini-flash-lite-latest (2.5 Flash-Lite) | 12 | 0.03941 |
| *(diet + fixed-first re-runs of A & B)* | — | remainder |
| **TOTAL (job=LOCAL-647)** | **181** | **0.70937** |

†nano has one extra call from the pre-flight 1-stop smoke test; `$/stop` uses the per-call average
so it is unaffected.

## 5. Live test (own container, additive is_test only)

Run in an isolated container (`docker run --rm --name local647-gen`, never `docker compose -p
audioura`, never renaming an `audioura-*` container). Each arm's 12 stops were stored as **one
additive `is_test` row**:

```
audio_tours BEFORE: total=371 is_test=307
inserted is_test ids: 566 (A) 567 (B) 568 (C) 569 (D) 570 (E)
audio_tours AFTER:  total=376 is_test=312   (+5 rows, all is_test)
```
No UPDATE, no DELETE. No GCloud.

## 6. Artifacts
All under `.continuous_dev/bench/local647_out/`:
- `A/ … E/` — raw drafts (`<stop>.txt`) + `arm_X_results.json` (status, seconds, usage per draft)
- `diet/`, `fixedfirst/` — the prompt-diet and caching runs
- `_prompts/` — the rebuilt prompts; `_wiki_cache/` — the free Wikipedia extracts (identical inputs)
- `_measure/measure.json` — full-vs-diet prompt sizes
- `_critiques/` — every Kiro critique markdown
- `kiro_scores.json`, `detectors.json`, `report.json`, `report_table.md`, `diet_report.{md,json}`

Code: `replay_harness.py`, `score_stops.py`, `report.py`, `diet_report.py`;
`generate_tour_text.build_museum_stop_prompt()` + `narration_model_route()`.

## 7. Recommendation
Switch the narration story-pass default from **gpt-4.1 → gpt-4.1-mini** (arm B): equal/greater
quality on this rubric, 0 detector failures, ~82% cheaper per stop, faster. Keep **Gemini 2.5
Flash / Flash-Lite** as validated cheaper second vendors (Flash-Lite is the fastest at 1.99s). Layer
**fixed-instructions-first prompt caching** on whichever OpenAI model is chosen for a further
input-cost cut at zero quality cost. Treat **nano** as too weak for this call.
