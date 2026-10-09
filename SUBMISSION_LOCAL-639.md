# SUBMISSION — LOCAL-639: Reliability (Uffizi lost Stop 3's header; National Gallery refused at random)

**Branch:** `LOCAL-639-reliability` (from `subscribed` @ `cb99474`)
**Agent:** Mac Mini Kiro — **PARALLEL with LOCAL-640.**
**Scope owned:** stop assembly / header & transition code, the shortfall path, the
refusal gates, `venue_resolver.py`. Did NOT touch claim/G4 grounding or
`stop_editor.py` (LOCAL-640).

Base verified: `git merge-base --is-ancestor cb99474 HEAD` → exit 0.

---

## TL;DR

| # | Defect | Root cause | Fix |
|---|--------|-----------|-----|
| 1 | The Uffizi (488) delivers "2 of 3": only `Stop 1:`/`Stop 2:` headers, closing says "That's 2 stops" | The Stop 2→3 directions value was **empty**, so a label-only `Directions:` was emitted with **no trailing newline** and the next header was written straight after it: `…once more.\n\nDirections:Stop 3: Adamo ed Eva`. `normalise_stop_headers` only re-broke a header glued after sentence punctuation (`.!?`), and the LEAD empty-field sweep only drops a label **followed by a newline** — so the glued header hid from the line-start counter. | `normalise_stop_headers` now also drops an **empty field label** glued to a `Stop N:` header and re-breaks it; it runs **before the directions guarantee** and at the top of the conclusion step, so the shipped text's narrated-body count == header count == `stops_count` == the "That's N stops" close on every branch. |
| 2 | The National Gallery refused "We couldn't verify enough facts … to narrate it safely" (R8), yet R7 generated fine (random) | **Same lost-newline family.** The Stop 2 header lost its trailing newline and ran into its own body: `Stop 2: The Toilet of Venus ('The Rokeby Venus') Address: Trafalgar Square … Orientation: …`. The QA title-sanity (D3(a)) and grounding (D3(d), a **FACTUAL** check) measured the whole 320-word run-on line as the "title" → `FACTUAL_FAIL_COUNT > 0` → **immediate refusal** of a 389-work museum that `venue_resolver` had cleanly resolved to Q180788. On a later round the newline survived, so id 495 shipped 3 clean stops — hence "at random". | Measure the **true** title: `_stop_title_from_header` cuts a run-on header at its first embedded field label, so a cosmetic lost newline collapses to the real 7-word title (a genuine 20-word sentence-title, with no field label, is still caught). And **retry, don't refuse**: the service QA loop now has a deterministic header-formatting corrective (`_split_run_on_stop_headers` + `normalise_stop_headers`) that restores the lost newline and re-runs QA **before** the factual-refusal branch — the same corrective pattern as the existing G4 branch. |
| 3 | Uffizi membership guard drops works held by a sibling sub-collection (e.g. P195 ≠ Q51252) | The LEAD derived-holder rule only promotes a P195 collection that holds ≥ 10% of the venue's **own** SPARQL set, so a minority **sibling** sub-collection stayed rejected (log: `'Due storie di san Nicola di Bari'` P195=Q3683040; `'Ritratto di giovane donna'` P195=Q3756440). | `venue_resolver.fetch_collection_holder_qids(venue_qid)` runs **ONE cached SPARQL** returning the venue's related holder QIDs via part-of / parent-org / ownership (P361/P749/P127/P527/P1830 + siblings sharing one of those parents). `_apply_artwork_guards` merges them into `parent_qids`. A one-off foreign leak (Ophelia P195=Tate) and a different museum (Arringatore P195=the National Archaeological Museum) still fail the gate. |

---

## Evidence (what the logs actually showed)

- **Tour 488 (Uffizi), delivered text in the DB:**
  `…unfolds once more.\n\nDirections:Stop 3: Adamo ed Eva\n\nCoordinates: …` — the
  Stop 3 header is present but glued onto an empty `Directions:` label; `stops_count`
  = 2 and the closing read "That's 2 stops in all." `audio_tour_versions` for 488 all
  recorded `stops_count=3` while the live row showed 2 — the header was lost by a late
  render pass, not by generation.
- **National Gallery, generator log (job `a81b18e8`, the refusing round):**
  ```
  [BLOCKER4c] Loaded 9 story elements for G4 check
    PASS: D3(e) No duplicate stops (FACTUAL)
    PASS: G4 Prolog/epilog claims trace to story elements (FACTUAL)
  …
    FAIL: D3(a) Stop-title sanity — "'Stop 2: The Toilet of Venus ('The Rokeby
          Venus') Address: Tr...' (320 words — too long)"
    FAIL: D3(d) Grounding assertion — 1 suspicious title: "The Toilet of Venus
          ('The Rokeby Venus') Address: "
  [BLOCKER4c] FACTUAL QA FAILED (round 1): 1 factual failure(s)
  ```
  `venue_resolver` had already resolved it: `#3 collection dominates (389 vs 8) —
  collapsing to Q180788 (National Gallery)`. The refusal was a **formatting**
  artifact, not a verification shortfall.
- **Uffizi collection drops, generator log:**
  ```
  collection-membership dropped: ('Due storie di san Nicola di Bari',
      'wrong_collection (P195=Q3683040 excludes Q51252; …)')
  collection-membership dropped: ('Ritratto di giovane donna',
      'wrong_collection (P195=Q3756440 excludes Q51252; …)')
  ```

---

## The fixes (files)

- `tour_conclusion.py` — `normalise_stop_headers` gains `_LABEL_GLUED_STOP_HEADER`:
  an empty `Address|Directions|Coordinates|Orientation:` label glued to a `Stop N:`
  header is dropped and the header re-broken onto its own line (idempotent; the
  pre-existing sentence-glued `…once more.Stop 3:` case still works; clean tours
  unchanged).
- `generate_tour_text.py` — the final header guarantee: `normalise_stop_headers`
  runs **before** the directions guarantee (so the restored non-last stop gets its
  hand-off — the live 536 Stop 2 ends "Your final stop in Uffizi Gallery: Adamo ed
  Eva.") and at the top of the conclusion step on **every** branch, so the delivered
  text carries the restored header and all counts agree. Also: `_apply_artwork_guards`
  merges `fetch_collection_holder_qids(venue_qid)` into `parent_qids` (defect 3).
- `content_qa_runner.py` — `_stop_title_from_header` + `_EMBEDDED_FIELD_LABEL_RE`:
  D3(a)/D3(d) measure the true title (cut at the first embedded field label), so a
  lost-newline run-on header no longer refuses a tour on a FACTUAL gate. A genuine
  long sentence-title (no field label) is still measured in full and still caught.
- `generate_tour_text_service.py` — `_header_formatting_defect` +
  `_split_run_on_stop_headers`, and a corrective-retry branch in the QA loop that
  restores a lost newline and re-runs QA **before** the factual-refusal branch
  (retry, not refuse).
- `venue_resolver.py` — `fetch_collection_holder_qids(venue_qid)`: ONE cached SPARQL
  (P361/P749/P127/P527/P1830 + shared-parent siblings) returning related holder QIDs.

### Honest finding on "Ritratto di Agnolo Doni"

The ticket asked to check whether the Gallerie degli Uffizi / Palazzo Pitti parent
QIDs let the Agnolo Doni portrait (P195 = Q866498, Galleria Palatina / Palazzo Pitti)
in. Verified against **live Wikidata**: Q866498 carries **no** P361/P749/P127 edge to
the Uffizi (Q51252), and the two are not linked within the part-of/ownership graph
despite the 2015 administrative merger — only a shared `P131 = Florence`. So a work
held **only** at the Palazzo Pitti is still (correctly, by the data we have) treated
as a different collection; the derivation rescues every sub-collection the graph
**actually** relates (Q3683040, Q3756440, …), and rejects a genuinely different
museum (Arringatore, P195 = Q637237, the National Archaeological Museum) — **no
hard-coding, no unsafe over-admit.**

---

## Tests (task 4) — all exit 0

```
tests/test_local60* + test_local60*       203 passed                       ec=0
tests/test_local61* + test_local61*       244 passed                       ec=0
tests/test_local62* + test_local62*       227 passed                       ec=0
tests/test_local63* + test_local63*       189 passed, 1 skipped            ec=0
tests/test_lead_*   + test_lead_*            7 passed                       ec=0
tests/test_local590_* + test_local590_*     42 passed                       ec=0
python3 test_sq4_merge.py                  ALL TESTS PASSED                 ec=0
```

New regression tests, each grounded on the real failing input:
- `test_local639_lost_stop_header.py` — defect 1 (the exact 488 `Directions:Stop 3:` boundary).
- `test_local639_national_gallery_refusal.py` — defect 2 (the 495 round-1 run-on header; FACTUAL_FAIL_COUNT=0; genuine bad titles still caught).
- `test_local639_collection_holders.py` — defect 3 (sibling kept, foreign/other-museum dropped; live-gated assertion that Q51252 rescues Q3683040+Q3756440 and rejects Q637237).

---

## Live run (own container, cache + pool OFF, cap $1.30)

Built `Dockerfile.generator` → image `local639-gen-img`; ran a **disposable**
container `local639-gen` (`docker run --rm --name local639-gen -p 5097:5000
--network development_default`). **Never** `docker compose -p audioura`; **never**
renamed or replaced an `audioura-*` container; image + container removed on exit.
`DISABLE_TOUR_CACHE=1`, `DISABLE_STOP_POOL=1`. Cap $1.30 (`TEST_GEMINI_MAX_USD` /
`COST_HARD_LIMIT_USD`), per-tour **reserve gate** (0.55).

Harness: `run_local639_container.py`, `run_local639_live.sh`
(artifacts under `tours/local639_live/`, gitignored).

**Row counts (additive `is_test` only; no DELETE):**
`audio_tours` **340 → 344** total, `is_test` **277 → 281**. My rows are **536**
(Uffizi) and **538** (National Gallery). The other two (**535** Pinakothek, **537**
Ny Carlsberg) are the parallel **LOCAL-640** agent's — not mine.

**Both venues DELIVERED 3 stops.**

### Uffizi — tour 536 (3 stops) — the exact works that broke in 488
```
Stop 1: Leda col cigno
Directions: Continue through Uffizi Gallery — next is Adorazione dei Magi.
Stop 2: Adorazione dei Magi
  (ends) "Your final stop in Uffizi Gallery: Adamo ed Eva."
Stop 3: Adamo ed Eva
That's 3 stops in all.
```
Harness report: `HEADER COUNT: 3  count_delivered_stops: 3  stated "That's N stops": 3`;
`lost-newline header artifacts: label-glued=False run-on=False`. `tour_total=$0.7465`.
**Defect 1 gone on the exact failing scenario.**

### National Gallery — tour 538 (3 stops) — DELIVERED, not refused
```
Stop 1: The Supper at Emmaus
Stop 2: The Toilet of Venus ('The Rokeby Venus')
Stop 3: The Hay Wain
That's 3 stops in all.
```
Harness report: `OUTCOME: DELIVERED`; `HEADER COUNT: 3 = count = stated`;
`run-on=False`. `tour_total=$0.6154`. **Defect 2 gone — the famous museum is no
longer refused.**

### Cost (all providers combined, < $1.30)
```
[LIVE_RUN_METER] TEST-LOCAL-639  (cap $1.30)
  openai            $0.4256
  gemini_grounding  $0.1120
  gemini_tokens     $0.0286
  serper            $0.0330
  preflight         $0.0161
  TOTAL             $0.5992
```
Reserve gate: Uffizi first ($0.745 metered to the tour), then
`$0.745 + $0.55 = $1.295 ≤ $1.30`, so the National Gallery ran.

### Detectors + critique
```
$ python3 ~/Audioura/.continuous_dev/bench/detectors.py 536 3 "Uffizi Gallery"   → 536: 0 detector failure(s)
$ python3 ~/Audioura/.continuous_dev/bench/detectors.py 538 3 "National Gallery" → 538: 0 detector failure(s)
```
`critique.sh`: **536 → 6.5/10**, **538 → 6.5/10**. Both: 3/3 stops delivered, every
work genuinely at the venue (critique confirms **no wrong-museum attribution**), no
URLs, a real conclusion. The remaining critique items (provenance filler, admission
wording, conclusion synthesis) are **content/polish** owned by LOCAL-640 and prior
tickets — not the three LOCAL-639 reliability defects, all of which are verified
fixed above.

---

## Process notes

- Branched from `subscribed` @ `cb99474` (not `origin/*`). Committed after each step.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md` or
  `.continuous_dev/STATUS.md`.
- No GCloud. No DELETE (my only DB writes are the two additive `is_test` rows 536/538).
