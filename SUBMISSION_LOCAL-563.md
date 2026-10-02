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

---

## Item 3 — Gemini question list

`tests/fixtures/local563/gemini_questions.jsonl` — **157 lines, one per grounded
Gemini call** (every charged, grounded call across the 20 recordings; the 7 ungrounded
calls in the `.gemini.jsonl` files are excluded). Each line carries:

```
tour, run, call_site, purpose, grounded, charged, model,
prompt (exact), response (exact text),
grounding_sources [ {domain, uri}, … ],   # de-duplicated, order-stable
grounding_queries [ … ], ts, wall_s
```

The recorder tags every call with the same `site` (`story_leads.gemini_with_sources`
or `story_leads._gemini`), so the real call site is the `caller` field
(`<file>:<fn>:<line>`), which is what `call_site` and the de-dup below use.

**Purpose mapping** (brief's categories):

| caller | purpose |
|---|---|
| `story_production_loop.py:run_for_stop:263` / `:302` | D545 story facts |
| `generate_tour_text.py:_generate_tour_text_impl:12106` | story leads |
| `restaurant_practicals.py:_gemini:153` / `venue_still_operating:328` | restaurant practicals |
| `stop_knowledge_fallback.py:_gemini_facts:233` / `:251` | stop facts |
| `venue_parts.py:default_ask:360` / `default_ask_grounded:371` | stop facts |

### De-duplicated count per call site

(`gemini_questions_dedup.json`.) `total` = grounded calls from that site;
`distinct prompts` = unique prompt strings (de-duplicated).

| call site | purpose | total | distinct prompts |
|---|---|---|---|
| `stop_knowledge_fallback.py:_gemini_facts:233` | stop facts | 36 | 25 |
| `story_production_loop.py:run_for_stop:263` | D545 story facts | 32 | 32 |
| `story_production_loop.py:run_for_stop:302` | D545 story facts | 31 | 30 |
| `venue_parts.py:default_ask_grounded:371` | stop facts | 20 | 17 |
| `restaurant_practicals.py:_gemini:153` | restaurant practicals | 13 | 8 |
| `restaurant_practicals.py:venue_still_operating:328` | restaurant practicals | 9 | 6 |
| `generate_tour_text.py:_generate_tour_text_impl:12106` | story leads | 8 | 4 |
| `stop_knowledge_fallback.py:_gemini_facts:251` | stop facts | 8 | 4 |
| **total** | | **157** | |

Rolled up by purpose: **D545 story facts 63** · **stop facts 64** · **restaurant
practicals 22** · **story leads 8**. The two story-production sites (`run_for_stop`)
almost never repeat a prompt (32/32 and 30/31 distinct) — each stop gets its own
question — whereas the restaurant and fallback sites repeat heavily (e.g. the restaurant
`_gemini` extractor is called 13 times with only 8 distinct prompts), because those
prompts are templated on a small, re-visited set of venues.

---

## Item 4 — facts per Gemini answer (for scoring step 2)

`tests/fixtures/local563/gemini_facts.json`. Each grounded response was split into
atomic facts with `sentence_split.split_sentences` (the required deterministic
splitter; code fences stripped first, fragments under 12 chars dropped). Every fact is
tagged with the domains its `groundingSupports` cite and a reliability tier.

**1431 atomic facts** across the 20 answers. Each `facts[]` row:
`{tour, run, call_site, fact, cited_domains, tiers, wikipedia_only, discovery_tier}`.

**Domain attribution.** When a fact's text overlaps a `groundingSupports[].text`
span, the fact is tagged with exactly that span's source domains; when no span matches
(the model's prose doesn't quote the support verbatim), the fact falls back to the
answer's full source set. 301 facts carry **no** domain at all — they come from answers
whose grounding returned empty sources (chiefly the restaurant practical extractor,
whose sources list is often empty), and so rest on nothing citable.

**Reliability tier** (from `_reliability_tiers` in `SERPER_AB_ANSWER_KEY.json`):
`high` = Wikipedia/Wikidata, established papers/magazines, `.gov`/`.edu`;
`medium` = Michelin / Eater / Boston Magazine / Atlas Obscura;
`discovery` = blogs, forums, review sites, niche/community pages. A domain not on the
high/medium allow-list is treated as **discovery** — the conservative reading, since
an unlisted official site cannot be distinguished generically from a blog, and the key
says a discovery fact counts only once a high-tier source corroborates it.

### Per tour

| tour | atomic facts | distinct domains | Wikipedia-only facts | Wiki-only share | discovery-tier facts | discovery share |
|---|---|---|---|---|---|---|
| sail_loft | 43 | 13 | 0 | 0.0% | 36 | 83.7% |
| buttermilk | 44 | 15 | 0 | 0.0% | 40 | 90.9% |
| chart_house | 53 | 14 | 0 | 0.0% | 29 | 54.7% |
| sycamore | 93 | 18 | 0 | 0.0% | 73 | 78.5% |
| la_maree | 40 | 14 | 0 | 0.0% | 37 | 92.5% |
| logan | 80 | 36 | 0 | 0.0% | 47 | 58.8% |
| our_lady | 254 | 34 | 10 | 3.9% | 183 | 72.1% |
| lascaris | 359 | 32 | 25 | 7.0% | 86 | 24.0% |
| riviera_bike | 223 | 56 | 0 | 0.0% | 215 | 96.4% |
| faneuil | 242 | 36 | 4 | 1.7% | 108 | 44.6% |

**Reading.** Almost nothing rests on Wikipedia *alone* — the maximum Wikipedia-only
share is 7% (lascaris), and six tours have zero Wikipedia-only facts. That is the
behaviour the answer key rewards: discovery over encyclopaedia. The flip side is how
much rests on the discovery tier: riviera_bike (96%), la_maree (93%) and buttermilk
(91%) draw nearly all their facts from blogs / forums / review / unlisted sites, which
under the key's rule count **only once corroborated by a high-tier source**. lascaris
is the healthiest profile — the richest answer set (359 facts) with the *lowest*
discovery share (24%), because the Palais Lascaris museum and departement06 / nice.fr
official pages carry most of its claims. chart_house, logan and faneuil sit in between.
This per-tour split is the input a corroboration check (scoring step 2) would run next.

---

## Item 5 — answer-key check of the Gemini runs

`tests/fixtures/local563/answer_key_check.json`. For each keyed tour: was each `must`
fact stated (in the tour text or a Gemini answer), did any `must_not` appear, did any
`unverified` claim appear and with what source. A `must` fact counts as *stated* when a
distinctive probe from its value (a year, a proper-name run, or a ≥5-char token)
appears in the combined text. The one short value, `status: open`, is read as *stated*
only when the venue reads as operating — i.e. "open" appears **and** the venue was not
given a D538 "permanently closed" verdict (`method: operating_inference`).

| tour | must facts stated | must_not appeared | unverified appeared | notes |
|---|---|---|---|---|
| sail_loft | opened ✓, reservations ✓, address ✓, **status(open) ✓** | — | — | all four met |
| buttermilk | chef ✓, opened ✓, address ✓, **status(open) ✗** | — | — | **status fails: D538 called it "permanently closed" in run1** (wrong — key says open) |
| chart_house | building ✓, history ✓, address ✓, **status(open) ✗** | — | — | **status fails: D538 called it "permanently closed" in both runs** — the pipeline matched the *Weehawken NJ* Chart House closure, not Boston's Long Wharf one |
| sycamore | status ✓, address ✓, opened ✓, chef_owner ✓, hours ✓, reservations ✓ | — (no "closed" on Sycamore) | — | all six met; **the D544 auto-FAIL did NOT fire** — the only closed verdict was for *The Local*, a replenished neighbour stop, not Sycamore |
| la_maree | status(CLOSED 2020) ✓ | **status=open did NOT appear ✓** | — | correctly presented as permanently closed; the must_not ("open") never appeared |
| logan | named_for ✓, opened ✓, renamed ✓, dedication ✓ | — | **"Governor Channing Cox" appeared** | appeared in both runs' tour text via `venue_parts.py:default_ask_grounded`; **no grounding support span backs it** — the exact "may appear only with a cited source" case the key flags |

### Findings

- **Two wrong "permanently closed" verdicts cost `must: status=open`.** buttermilk and
  chart_house are both open per the key, but D538 dropped them as permanently closed
  (buttermilk once, chart_house both runs). chart_house is a name-collision failure:
  the closed source is the *Weehawken, New Jersey* Chart House ("riverfront staple …
  closed as of May 14"), not Boston's Long Wharf location. This is the same
  false-closed failure family the key warns about with Sycamore (D544).
- **Sycamore itself passed its must_not.** Despite the D544 risk the key calls out,
  neither Sycamore run produced a "closed" verdict for Sycamore — the run1 closed
  verdict named *The Local*, a replenished neighbour, so Sycamore's `status: OPEN`
  must-fact holds and the auto-FAIL did not trigger.
- **la_maree is correct in the hard direction:** it is stated as permanently closed
  (2020, Port Palace Hotel lease dispute) and the `must_not: status=open` never
  appeared — the pipeline did not re-open a closed venue.
- **One unverified claim surfaced unsourced.** logan's "Governor Channing Cox" appears
  in both runs' tour text, but no `groundingSupports` span carries it
  (`backed_by_grounding_support_span: false`). Under the key this may appear only with
  a cited source; here it is stated with none. (`answer_domains_when_appeared` lists the
  answer's whole source set, but none of those spans actually mention Channing — the
  fallback, not a citation.)

---

## Reproduce

```
python3 tests/fixtures/local563/analyze_baseline.py
```

Regenerates `baseline_summary.json`, `gemini_questions.jsonl`,
`gemini_questions_dedup.json`, `gemini_facts.json` and `answer_key_check.json` from the
recordings. No network, no generation, no API calls — reads only the saved
`.txt` / `.json` / `.log` / `.gemini.jsonl` files, `tour_quality.score_tour`,
`sentence_split.split_sentences`, and `SERPER_AB_ANSWER_KEY.json`.
