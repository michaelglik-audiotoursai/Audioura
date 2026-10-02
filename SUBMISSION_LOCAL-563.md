# LOCAL-563B — Gemini baseline: summary, noise floor, question list

**Agent:** Mac Mini Kiro **Branch:** `LOCAL-563-gemini-baseline` **Base:** `3af65a5`

Analysis only. No tour was generated; no Gemini / OpenAI / GCloud call was made.
Everything below is computed from the recordings in `tests/fixtures/local563/runs/`
(the 10 tours × 2 runs captured under LOCAL-563, commit `3af65a5`).

All artifacts are reproduced by one deterministic script:

```
python3 tests/fixtures/local563/analyze_baseline.py
```

which writes, into `tests/fixtures/local563/`:

| file | item |
|---|---|
| `baseline_summary.json` | 1 (per-tour run1 vs run2) + 2 (`noise_floor`) |
| `gemini_questions.jsonl` + `gemini_questions_dedup.json` | 3 |
| `gemini_facts.json` | 4 |
| `answer_key_check.json` | 5 |
| `SERPER_AB_ANSWER_KEY.json` | copied from the main checkout (tiers + keys) |

**Method notes**
- *Story score / defects*: `tour_quality.score_tour` re-run on the **saved tour text**
  (`<slug>_<run>.txt`), as the brief asks. This runs offline (no `provenance`, no
  `geocoder`), so it reports the *shape* defects `score_tour` can see without a live
  source pool. That is why `unsourced_person_event` fires on `logan` / `our_lady` here
  even though those runs were clean at generation time — offline there is no pool to
  clear the person-at-venue-on-a-date shape. The run-time measures are preserved in
  each `<slug>_<run>.json` and echoed in `baseline_summary.json` under
  `gate_removals_json` for cross-check.
- *Gate-deleted sentences*: counted directly from the `.log`, one count each from the
  `[LOCAL-235]` R10 summary ("N sentences deleted"), the `[LOCAL-229]` block summary
  ("N group(s) blocked"), and the per-entity `[LOCAL-472] UNGROUNDED entity` lines.
- *Restaurant practicals / closed verdict*: from the `[D538]` lines in the `.log`
  (`'<name>' via <provider>: hours=… reservation=… price_band=…` and the
  `⚠️ DROPPED '<name>' — reported permanently closed:` lines).
- *Grounded request count & cost*: from each run's `cost_record` / `gemini_calls`.
- *Wall time*: `wall_s` from each run json.

**Totals across all 20 runs:** 157 grounded requests · LLM $4.13 · grounding $5.50
· combined $9.62. (The 157 grounded requests and the $5.50 grounding spend match the
LOCAL-563 session total exactly.)

---

## Item 1 — per-tour baseline summary (run1 vs run2)

Story score column: `clean` = `score_tour` reported no required-clean defect on the
saved text; defects listed are the offline `score_tour` keys. Gate columns are the
log-counted deletions (235 / 229 / 472 / total). Practicals columns count stops with
hours / reservation / price-band present; **closed** names any stop given a D538
"permanently closed" verdict. Cost in USD, wall in seconds.

### Restaurant tours

| tour | run | story | defects | people | stops | 235 | 229 | 472 | gate Σ | hrs | res | price | closed verdict | grnd | $ llm | $ grnd | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sail_loft | 1 | clean | no_story | 0 | 1/1 | 1 | 0 | 2 | 3 | 1 | 1 | 1 | — | 3 | 0.054 | 0.105 | 126.0 |
| sail_loft | 2 | clean | no_story | 0 | 1/1 | 0 | 0 | 3 | 3 | 1 | 1 | 1 | — | 3 | 0.057 | 0.105 | 149.2 |
| buttermilk | 1 | clean | — | 3 | 1/1 | 0 | 0 | 6 | 6 | 1 | 1 | 1 | **Buttermilk & Bourbon** | 2 | 0.060 | 0.070 | 104.0 |
| buttermilk | 2 | clean | — | 3 | 1/1 | 1 | 0 | 7 | 8 | 1 | 1 | 1 | — | 3 | 0.060 | 0.105 | 127.0 |
| chart_house | 1 | clean | no_story | 0 | 1/1 | 0 | 1 | 6 | 7 | 1 | 1 | 1 | **Chart House** | 2 | 0.059 | 0.070 | 135.2 |
| chart_house | 2 | clean | no_story | 0 | 1/1 | 2 | 0 | 5 | 7 | 1 | 1 | 1 | **Chart House** | 2 | 0.059 | 0.070 | 163.0 |
| sycamore | 1 | **FAIL** | repeated | 2 | 2/2 | 0 | 0 | 10 | 10 | 1 | 1 | 1 | The Local¹ | 7 | 0.116 | 0.245 | 216.1 |
| sycamore | 2 | clean | — | 4 | 2/2 | 2 | 0 | 7 | 9 | 1 | 1 | 1 | — | 8 | 0.109 | 0.280 | 189.4 |
| la_maree | 1 | clean | no_story | 0 | 1/1 | 1 | 1 | 3 | 5 | 1 | 0 | 0 | — | 2 | 0.062 | 0.070 | 102.4 |
| la_maree | 2 | **FAIL** | distance | 3 | 1/1 | 3 | 0 | 5 | 8 | 0 | 0 | 0 | — | 2 | 0.059 | 0.070 | 109.1 |

¹ The D538 "permanently closed" verdict named **The Local**, a *replenished neighbour
stop*, not Sycamore itself. Sycamore was never given a closed verdict in either run —
so the D544 auto-FAIL case did **not** fire (see Item 5).

### Museum / facility / walking tours

| tour | run | story | defects | people | stops | 235 | 229 | 472 | gate Σ | grnd | $ llm | $ grnd | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| logan | 1 | clean² | unsourced_person_event | 5 | 4/4 | 0 | 0 | 12 | 12 | 4 | 0.286 | 0.140 | 194.2 |
| logan | 2 | clean² | unsourced_person_event | 7 | 4/4 | 1 | 0 | 17 | 18 | 4 | 0.212 | 0.140 | 213.6 |
| our_lady | 1 | clean² | unsourced_person_event | 6 | 4/4 | 2 | 0 | 13 | 15 | 10 | 0.180 | 0.350 | 226.4 |
| our_lady | 2 | clean² | unsourced_person_event | 8 | 4/4 | 2 | 0 | 21 | 23 | 9 | 0.196 | 0.315 | 310.7 |
| lascaris | 1 | clean | — | 3 | 4/4 | 1 | 2 | 4 | 7 | 39 | 0.830 | 1.365 | 617.2 |
| lascaris | 2 | **FAIL** | dangling_reference; thin | 3 | 3/4 | 0 | 3 | 2 | 5 | 40 | 0.950 | 1.400 | 614.6 |
| riviera_bike | 1 | clean | — | 7 | 4/4 | 5 | 1 | 11 | 17 | 4 | 0.189 | 0.140 | 374.8 |
| riviera_bike | 2 | **FAIL** | offsite_entity; thin | 3 | 3/4 | 4 | 1 | 16 | 21 | 4 | 0.202 | 0.140 | 328.1 |
| faneuil | 1 | clean | — | 5 | 4/4 | 2 | 2 | 9 | 13 | 5 | 0.203 | 0.175 | 361.6 |
| faneuil | 2 | clean | thin | 4 | 3/4 | 3 | 4 | 4 | 11 | 4 | 0.181 | 0.140 | 372.6 |

² `clean` under `REQUIRED_CLEAN`: `unsourced_person_event` is flagged but is not a
required-clean defect, so `score_tour` returns `clean=True` while still reporting the
shape. This is the offline reading (no source pool). See method note above.

---

## Item 2 — noise floor per measure

Run-to-run instability on identical inputs, measured as `|run1 − run2|` per tour, then
the **mean** and **max** of that absolute delta across the 10 tours. `max tour` names
the tour that produced the maximum delta. Full per-tour deltas are in
`baseline_summary.json → noise_floor.<measure>.per_tour_abs_delta`.

| measure | mean \|Δ\| | max \|Δ\| | max tour |
|---|---|---|---|
| story_defect_count | 0.6 | 2 | lascaris |
| named_people | 1.4 | 4 | riviera_bike |
| stops_delivered | 0.3 | 1 | lascaris |
| gate_deleted_total | 2.8 | 8 | our_lady |
| gate_235 (R10 deletions) | 1.2 | 2 | chart_house |
| gate_229 (contradiction blocks) | 0.5 | 2 | faneuil |
| gate_472 (specificity removals) | 3.3 | 8 | our_lady |
| rp_hours_count | 0.1 | 1 | la_maree |
| rp_reservation_count | 0.0 | 0 | — |
| rp_price_band_count | 0.0 | 0 | — |
| rp_closed_verdict | 0.2 | 1 | buttermilk |
| grounded_requests | 0.5 | 1 | buttermilk |
| cost_llm (USD) | 0.0258 | 0.1204 | lascaris |
| cost_grounding (USD) | 0.0175 | 0.0350 | sycamore |
| wall_s | 27.14 | 84.3 | our_lady |
| chars | 744.9 | 2395 | faneuil |
| dates | 2.3 | 9 | lascaris |

**Reading the floor.** The practical-fact extractions are the quietest signal in the
set: `reservation` and `price_band` never differed between runs (Δ = 0 everywhere),
`hours` moved once (la_maree, where run2 produced no practicals at all), and the
closed verdict flipped on exactly one tour (buttermilk: dropped as closed in run1,
kept in run2). Grounded-request count is nearly fixed too (mean 0.5, max 1), so the
pipeline asks Gemini almost the same number of questions each time.

The gates are the noisiest internal measure — `gate_472` alone averages 3.3 and
spikes to 8 on our_lady — which means the *specificity* judgement, not the retrieval,
is where two identical requests diverge most. That instability propagates: the tours
whose story score flipped between pass and fail (sycamore, la_maree, lascaris,
riviera_bike) are the same tours where a stop was dropped or a defect appeared on only
one of the two runs. So on this baseline a single run is **not** a reliable verdict for
a borderline tour; the pass/fail itself has a noise floor of up to 2 defects and 1
dropped stop. `named_people` (max Δ 4) and `chars` (max Δ 2395) confirm the narrative
body varies substantially run to run even when the score does not.
