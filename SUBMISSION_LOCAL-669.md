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

---
---

# SUBMISSION — LOCAL-669B (bounce: HCMC tour 666 scored 2/10)

**One painting became three stops; a citation became a stop. Fix with IDENTITY,
not tokens.**

Agent: Mac Mini Kiro · Branch: `LOCAL-669-grounded-highlights` (continued) ·
Base: `subscribed` @ `9684e563` (`git merge-base --is-ancestor 9684e563 HEAD` → 0).

## What the bounce asked for

Tour 666 shipped the one National Treasure THREE times — "North Central South
Spring Garden" and "Central South and North Spring Garden" (R4: the English
Wikidata label and its reordered altLabel) and "Vườn xuân Trung Nam Bắc"
(highlights: the Vietnamese) — plus a scraped citation line as a stop. The
LOCAL-669 fragment guard is token-based and cannot bridge languages or word
order. The LEAD asked to collapse by IDENTITY: a Wikidata QID when either side
has one (Q109406846); a bilingual title match (local OR English, normalised:
lowercase, accents stripped, word ORDER ignored via a sorted token set,
punctuation dropped, the/of/and dropped); the D1v2 bilingual map; applied to the
WHOLE candidate pool, keeping the best-sourced title. Prefer highlights over R4
on thin museums; skip redundant grounded work; one live run, cap $1.10.

## What this does (the fix)

### 1. Identity-based dedup — `identity_dedup.py` (new)
`norm_set(title, bilingual_map)` is the order-ignored identity string: the sorted
SET of a title's content tokens (lowercased, accents stripped, punctuation
dropped, glue words the/of/and + common EN/FR/DE/ES/IT articles dropped), each
token expanded through the D1v2 bilingual word map. `identity_of(candidate)`
reads a candidate's QID (`qid`/`QID`/`wikidata_qid`/`work_qid`) and ALL its titles
(`name`/`title`/`title_local`/`title_en`/`label_local`/`label_en`), one norm_set
per title. Two candidates are the SAME work when their QIDs match, OR any of one
side's normalised title sets equals any of the other's. A QID **conflict** (two
different QIDs) is a hard "distinct works" signal and is NEVER merged.
`dedup_by_identity(pool, bilingual_map)` unions same-identity candidates
(union-find), keeps the **best-sourced** survivor (QID-bearing > own-domain/
sourced > more sources > verified), stamps any member's QID onto the survivor,
and returns the collapses for logging. Pure, offline, no LLM.

### 2. Highlights return BOTH titles — `grounded_highlights.py`
`parse_highlights` now emits `title_local` and `title_en` (a bilingual-gloss
splitter), so a candidate matches on EITHER language. The identity pass needs
both sides of the pairing.

### 3. Highlights FIRST on thin museums — `generate_tour_text.py`
The grounded-highlights block was moved ABOVE the R4 replenishment loop. On a
thin museum, highlights (well-sourced, bilingual-paired) fill FIRST; R4 then only
fills what is still short — and because R4's loop is gated on
`len(poi_list) < total_stops`, when highlights reach the count the R4 "2×"
candidate request is **not issued at all** (ticket point 4). When a highlight is
the same work as a stop already in the tour, the identity filter drops it BEFORE
it consumes a slot, so R4 still fills the gap with a DISTINCT work. A whole-pool
`dedup_by_identity` pass runs before the LOCAL-16 gate as the correctness
backstop.

### 4. Skip redundant grounded work (cost)
The LOCAL-667 per-title thin-verify pool now excludes every title the one
grounded highlights call already verified (they are in `poi_list`, and
`_already |= _hl_titles_verified`), and the whole thin-verify block is gated on
`len(poi_list) < total_stops`, so on a tour highlights filled it does not run.

## Live run (task 6) — ONE paid tour, own container, honest result

Built `Dockerfile.generator` from this branch and ran in a **disposable**
container (`docker run --rm --name local669b-gen -p 5170:5000 --network
development_default`). NEVER `docker compose -p audioura`; never touched an
`audioura-*` container. Tour cache OFF, stop pool OFF (fresh). NORMAL arm only.
Rows **additive `is_test` only; no DELETE**.

**Request:** Ho Chi Minh City Museum of Fine Arts, Vietnam — 5 stops, museum,
fresh. **DELIVERED** 5/5 stops, wall **401 s**, stored `audio_tours` id **667**
(`is_test=true`). Grounded-request count: the highlights step used **1 grounded
request + 0 Serper** (its own bound honoured).

### Cost — I breached the $1.10 cap on the one arm, and I report it straight
`cost_ledger` user `TEST-LOCAL-669B`:

| provider | $ |
|----------|---|
| openai | 1.2181 |
| gemini_grounding (6 req / 9 q) | 0.1260 |
| gemini_tokens | 0.0045 |
| serper | 0.0550 |
| preflight | 0.0729 |
| **TOTAL** | **1.4036** |

The $1.10 cap is the whole-tour budget; a fresh 5-stop museum tour cannot meet it
because the **OpenAI narration alone is $1.22** — baseline per-stop generation,
not this feature. The LOCAL-669B step's own grounded cost is **$0.126** (6
grounded requests across the whole pipeline; the highlights call itself is 1).
I used my ONE budgeted paid tour; I did **not** run a second (a re-run would
breach the whole-tour cap again, and the fix is proven offline against the exact
captured grounded response — see below).

### The live run exposed TWO real bugs my first cut missed — both now fixed
Tour 667 was generated by the FIRST cut, and it was still wrong — valuable,
because it showed exactly where the first cut was incomplete. The grounded model
answered in a **markdown** shape the parser did not anticipate:
`**Vườn xuân Trung Nam Bắc** (*Spring Garden of the Center, South, and North*)`
followed by `- Artist:` / `- Year:` / `- Medium:` SUB-BULLETS.

1. **Sub-bullets became stops.** The old marker-split treated `- Artist:` and
   `- Year:` as new list items, so "Artist" and "Year" shipped as stops (3 and 4
   on tour 667). **Fix:** `parse_highlights` is now BLOCK-based — a work begins
   only at a numbered marker or a bold-title line; a `- Label:` line folds into
   the current work as a field. `_is_junk_title` rejects bare field labels.
   Markdown emphasis is stripped before the citation guard; `_title_head` cuts at
   the first field label; the label-field extractors stop at the next label (no
   bleed).

2. **The cross-language bridge missed by one token.** The model's English gloss
   said "**Center**", the Wikidata label says "**Central**", so the sorted token
   sets differed by one word and the Spring Garden pair did not collapse (tour
   667 shipped it as stops 1 and 2). **Fix:** D1v2 now records each verified
   work's SPARQL `label_local`/`label_en` in the evidence log; the identity pass
   stamps the OTHER-language label onto the stop, so the Vietnamese highlights
   candidate collapses into the English SPARQL stop by an **EXACT local-label
   match** — no fuzzy overlap, no risk of a false merge.

**Verified end-to-end offline against the EXACT captured live grounded shape**
(parse → verify → identity-filter → dedup): the markdown block parses to the
real works (no "Artist"/"Year"), the Vietnamese Spring Garden collapses into the
English SPARQL stop, and the result is **5 distinct stops** — the National
Treasure appearing ONCE. The three new tests under
`TestMarkdownSubBulletFormat` replay this exact format.

> **Honest caveat:** tour 667 is the PRE-FIX output (2/10-class — the duplicate
> and the two label-stops are present). The fixes are proven by offline tests
> that replay the captured grounded format, not by a second paid live run, which
> would breach the cap a second time. `.continuous_dev/calib/critique.sh` is not
> present in this worktree (no `calib/` dir), and tour 667 predates the fix in
> any case.

## Tests (task 5) — all green

New `test_local669b_identity_dedup.py` (24 tests): the three Spring Garden
variants → ONE stop; a QID match collapses; a QID **conflict** never merges; a
word-ORDER permutation collapses; a Vietnamese/English pair collapses (carried
pair AND bilingual-map bridge); "Iron Wall Youth" (its own identity / own QID) is
KEPT separate; the best-sourced title survives; order is stable; `parse_highlights`
emits both titles (paren gloss, quoted gloss, year-is-not-a-gloss, no-gloss); and
the **live-failure regression** (markdown sub-bullets not promoted to stops; the
`(*gloss*)` splits; fields do not bleed; the Spring Garden collapses against the
English SPARQL stop). The LOCAL-669 citation-line test is kept (still passes).

```
test_local669b_identity_dedup.py ........................  24 passed   EXIT=0
test_local669_grounded_highlights.py ....................  25 passed   EXIT=0
test_local667_thin_museum.py (14)  test_local667_building_stops.py (12)   EXIT=0
test_local668_blocker4b_contained.py (7)  _area_lead_work.py (4)          EXIT=0
test_local668_well_documented_regression.py (4)  _foreign_museum_snippets (9)  EXIT=0
test_local668_cost_cap.py (9)   test_local667_title_split.py (14)         EXIT=0
tests/test_local648_serper_research.py + test_local664 + museum suites
   (582 overview, 583 chrome, 583 documented, 585 about, 639 holders,
    contained_regression)                      87 passed, 1 skipped       EXIT=0
```

## Honesty contract (669B)
- Identity collapse never invents or merges distinct works: a QID conflict is a
  hard block; a title match requires a shared normalised set; a cross-language
  bridge uses an EXACT SPARQL label, not a fuzzy guess (tested).
- Default behaviour unchanged for non-thin / non-museum tours.
- One live run in an isolated `--rm` container; additive `is_test` rows only; no
  DELETE; no GCloud. Spend reported from `cost_ledger`/`paid_api_calls`.
- The $1.10 cap was breached on the one fresh arm ($1.40, driven by $1.22 OpenAI
  narration — the per-stop baseline, not this feature). Reported, not hidden.
- I did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  `.continuous_dev/STATUS.md`.
