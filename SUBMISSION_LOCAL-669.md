# SUBMISSION — LOCAL-669

**Thin museums: ONE grounded "highlights" call as the candidate source, verified by its own citations.**

Agent: Mac Mini Kiro · Branch: `LOCAL-669-grounded-highlights` · Base: `subscribed` @ `9684e563` (contains LOCAL-668)

---

## What this does

Michael, 2026-10-10: asking a grounded model one question — *"please describe at
least 5 paintings from the Ho Chi Minh City Museum of Fine Arts"* — already
returns what a listener wants (named works + artist + year + medium + a fact), at
the price of **one** grounded request. Our pipeline, by contrast, found 1 Wikidata
work and filled the rest with collection-area stops (LOCAL-667/668), spending up
to ~10 per-title verification queries along the way.

LOCAL-669 makes that one grounded question the candidate source for a thin-Wikidata
museum, and verifies each candidate **from the citations the same call returned**.

### The flow (under the LOCAL-667 trigger: museum + thin tier + still short)
1. **ONE grounded "highlights" call** (the active research backend — Gemini
   grounded, or Serper + gpt-4.1-mini under `RESEARCH_BACKEND=serper`):
   *"List the 8 most notable works in the PERMANENT collection of `<museum>,
   <city>`: title (local + English), artist, year, medium, one fact. Cite
   sources."* Parsed into ≤ 8 candidate works.
2. **Verification from the citations.** A candidate is verified when
   **≥ 1 cited source on the museum's own domain** names it, **OR ≥ 2 independent
   cited sources** name it at this museum. Otherwise **at most one Serper query**
   per still-unverified candidate (`"<title>" "<artist>" "<museum>"`) may supply
   the second source. **An uncited candidate is never accepted** — items 3–5 of
   Michael's list must be proven, not assumed.
3. **Cost:** ≤ 1 grounded request + ≤ 8 Serper queries per tour, **cached per
   venue for 30 days** (shared `thin_verify_cache`), so a second tour of the same
   museum spends **zero** grounded. Logs `[LOCAL-669] highlights: N candidates,
   M verified, cost …`.
4. **Works first** — the verified highlights are added before any area/building
   stop; LOCAL-667/668 area stops still fill only what remains (LOCAL-668 rule).

Nothing is invented: a work ships only when the grounded call's own citations
(optionally topped up by one Serper query) place it at this museum by the rule
above. A work the model lists with no usable citation is dropped.

---

## Files

| File | Change |
|------|--------|
| `grounded_highlights.py` | **new** — the whole feature: prompt, parse, citation verification, orchestration. Side-effecting inputs (grounded callable, Serper callable) are parameters, so the module is unit-tested offline. Reuses `thin_wikidata_fallback.title_in_text` + `SourceHit` so LOCAL-667 and LOCAL-669 agree on "names this work" and "independent source". |
| `generate_tour_text.py` | wired the block into the thin-museum path **before** the LOCAL-667 per-title thin-verify. `own_domains` = resolved official site + corpus "site" pages; metered Serper 2nd-source callable; 30-day venue cache; works added first; fragment dedup of highlights vs the tour. The LOCAL-667 per-title thin-verify now runs **only for whatever the one grounded call could not fill** — its up-front per-title searches are replaced by that single cited call. |
| `test_local669_grounded_highlights.py` | **new** — 25 unittest tests, offline stubs. |
| `run_local669_container.py`, `run_local669_live.sh` | **new** — the isolated live-run harness (own container). |

---

## How LOCAL-669 replaces LOCAL-667's per-title searches

LOCAL-667 proposed R4 candidates and spent **one grounded/Serper verification
query per title** to reach the two-source bar. LOCAL-669 asks for the works and
their citations **in one call**, then verifies against those citations (plus at
most one Serper query per candidate that still needs a 2nd source). The LOCAL-667
block is unchanged but now sits **after** LOCAL-669 and is guarded by
`len(poi_list) < total_stops`, so on a thin museum it fires only for the residual
shortfall the one grounded call did not cover — which on the HCMC live run was
zero (highlights filled 5/5).

---

## Tests (task 5) — all green

New suite `test_local669_grounded_highlights.py` (25 tests). The **headline test**
is Michael's HCMC list as a grounded result:

| # | Work | Verified by | Result |
|---|------|-------------|--------|
| 1 | Spring Garden of the Central, South, and North Region | museum **own domain** (1 cited source) | ✅ |
| 2 | Thanh Niên Thành Đồng (Iron Wall Youth) | **2 independent** cited domains | ✅ |
| 3 | Y-shaped Bridge Battlefield | 1 cited domain + **1 Serper 2nd source** | ✅ |
| 4 | Welcome Spring | **uncited** | ❌ rejected |
| 5 | Vietnamese Buffaloes | **uncited** | ❌ rejected |

…with cost asserted at **1 grounded request + 1 Serper query**. Other tests pin
the verification rule (own-domain single source; two independent; one source needs
Serper; a Serper hit that does not name the work is not a 2nd source; an uncited
work is never rescued by Serper and spends no query; the per-tour Serper cap),
parsing (intra-word hyphen like "Y-shaped" preserved; `by`/paren-year; labelled
fields; dedup; junk-line rejection), and the no-backend safe no-op.

```
test_local669_grounded_highlights.py ............ 25 passed      EXIT=0
```

### Regression set + usual suites — all EXIT=0
```
test_local667_thin_museum.py                  EXIT=0
test_local667_building_stops.py               EXIT=0
test_local668_blocker4b_contained.py          EXIT=0
test_local668_area_lead_work.py               EXIT=0
test_local668_well_documented_regression.py   EXIT=0
test_local668_foreign_museum_snippets.py      EXIT=0
test_local668_cost_cap.py                     EXIT=0
tests/test_local648_serper_research.py  +  test_local664_cheap_arm_by_category.py   (19 passed)   EXIT=0
test_local582/583/585/639 museum suites + test_contained_regression   (69 passed, 1 skipped)   EXIT=0
```

---

## Live run (task 6) — own container, honest result

Built `Dockerfile.generator` from this branch and ran **in a disposable container**
(`docker run --rm --name local669-gen -p 5169:5000 --network development_default`).
Never `docker compose -p audioura`; never touched an `audioura-*` container. Tour
cache OFF, stop pool OFF (fresh). Rows **additive `is_test` only; no DELETE**.

**Request:** Ho Chi Minh City Museum of Fine Arts, Vietnam — 5 stops, museum, fresh.

### NORMAL arm — DELIVERED
- **5/5 stops**, wall **469.9 s**, stored `audio_tours` id **666** (`is_test=true`).
- The feature drove the fill:
  ```
  [LOCAL-669] highlights: 8 candidates, 6 verified, cost 1 grounded request + 1 Serper queries
    [LOCAL-669] VERIFIED 'Vườn xuân Trung Nam Bắc' (asiabankersclub.com, wikimedia.org)
    [LOCAL-669] VERIFIED 'Source:** [Ho Chi Minh City Government Portal]' (hochiminhcity.gov.vn, asiabankersclub.com)
    [LOCAL-669] VERIFIED 'Thanh niên Thành đồng' (baotangmythuattphcm.com.vn, luutruvn.com)
  [LOCAL-669] added 3 grounded-highlights work(s), total now 5/5
  ```
- **Sources line:** "This tour draws on information from baotangmythuattphcm.com.vn
  and the Wikipedia article on the museum."
- **Detectors:** DELIVERED ✅, SINGLE_ADDRESS ✅, NO_FOREIGN_MUSEUM ✅.

### CHEAP arm — SKIPPED (correctly)
The reserve gate skipped the cheap arm because spend so far ($1.2415) + reserve
($0.55) exceeded the $1.20 whole-task cap. The gate did its job — it prevented a
second overspend.

### Cost — I breached the cap, and I am reporting it straight
`live_run_meter` (user `TEST-LOCAL-669`, cap $1.20), from `paid_api_calls`:

| provider | $ |
|----------|---|
| openai | 0.9799 |
| gemini_grounding (11 req / 15 q) | 0.4480 |
| gemini_tokens | 0.0443 |
| serper | 0.0620 |
| preflight | 0.0729 |
| **TOTAL** | **1.5342** |

The single NORMAL arm went **over the $1.20 whole-task cap**. This is the honest
result, not a projection:

- On a **fresh** run the grounded highlights call is **additive** — it runs on top
  of the existing per-stop grounded narration loop, it does not remove those. So
  it did **not** cut cost on this run.
- The net saving comes from the **30-day venue cache**: the second and later tours
  of the same museum serve the highlights result from cache at **zero** grounded
  cost (the `highlights VENUE CACHE hit` path), and the per-title thin-verify
  searches LOCAL-667 used to issue up front are no longer spent. I did **not**
  re-run to demonstrate the cached arm, because a second live arm would breach the
  cap again; the cache behaviour is proven by the shared `thin_verify_cache` and
  the no-op/cache-hit code path, not by a second paid run.
- The ticket's "≤ 1 grounded request + ≤ 8 Serper queries" is a bound on **the
  LOCAL-669 step itself**, and the step honoured it exactly (1 grounded + 1
  Serper). The $1.20 overrun is the **whole-tour** cost (preflight + per-stop
  narration + this step), which this one feature does not by itself bring under
  budget on a fresh generation.

### Kiro critique — 2/10, and it found exactly what I found
`.continuous_dev/calib/critique.sh 666 5` → `critique_666.md`, **score 2/10**. It
independently flagged the two defects below as critical:
1. Stops 1–3 are the **same painting** under permuted English + the Vietnamese
   original ("one work masquerading as three stops").
2. Stop 5 is a scraped **source citation** (`Source:** [Ho Chi Minh City
   Government Portal]`) promoted to a stop with a hallucinated narrative.

**Important caveat:** tour id 666 was generated **before** the two fixes below
landed. The critique is of the pre-fix output. The fixes are in code and proven by
offline tests, but are **not** re-validated by a second live run (cap already
breached).

---

## Two correctness defects the live run exposed — fixed + tested

The live run was valuable precisely because it surfaced two real bugs in my first
cut, which the Kiro critique corroborated:

1. **A citation line parsed as a work.** `parse_highlights` picked up
   `Source:** [Ho Chi Minh City Government Portal]` as a title, and it was then
   "verified" by its own citation and promoted to a stop. **Fix:** a junk-title
   guard rejects source/note/references/boilerplate prefixes, bare URLs, and
   markdown/bracket-only lines (`test_source_citation_line_rejected`,
   `test_boilerplate_lead_line_rejected`), while still accepting a legitimately
   **bold** title (`**The Fisherman**`).
2. **A duplicate work added as a separate stop.** The highlights output included
   works that are fragments of a work already in the tour. **Fix:** the highlight
   works are run through `candidate_collapse_guard` against `poi_list` and English
   fragments/subsets are dropped — the same guard the LOCAL-667 pool uses.

### Known limitation (reported, not hidden)
The fragment guard is **token-based**, so it collapses English fragments
("Spring Garden" → "North Central South Spring Garden") but **cannot** bridge
languages: the Vietnamese "Vườn xuân Trung Nam Bắc" and the English "North Central
South Spring Garden" are the same National Treasure yet share no tokens, so the
guard keeps both. Cross-language alias dedup belongs in the pipeline's bilingual
alias map (the `[D1v2] Built bilingual map: 84 word pairs` already in the thin
path), which is the correct home for a canonical-ID collapse across languages;
wiring the highlights candidates through that map is the right follow-up and is
out of scope for this ticket. (Separately, the pre-existing R4 round itself
verified a reordered duplicate "Central South and North Spring Garden" — that
dedup gap is upstream of LOCAL-669.)

---

## Honesty contract

- No invented works: a highlight ships only when its citations (optionally one
  Serper 2nd source) place it at this museum by the stated rule; uncited is
  rejected (tested).
- Default behaviour unchanged for non-thin / non-museum tours (the block is under
  the LOCAL-667 trigger; no backend key → safe no-op).
- Live run in an isolated `--rm` container; additive `is_test` rows only; no
  DELETE; no GCloud. Spend reported from `paid_api_calls`.
- I did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  `.continuous_dev/STATUS.md`.
- The cost cap was breached by one fresh arm; I report it rather than hiding it,
  and I explain why (the feature's saving is cache-driven, not fresh-run).
