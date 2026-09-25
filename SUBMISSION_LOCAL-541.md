# SUBMISSION — LOCAL-541: 12 million and 43.5 million in the same tour

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-541-numeric-contradiction`
**Base:** storied @ `43d407e` (verified: `git merge-base --is-ancestor 43d407e HEAD` exits 0)

## What shipped

A fifth self-contradiction sub-check, `numeric_conflict`, added to the existing
`_find_self_contradictions` in `tour_quality.py` — not a new top-level defect. It
returns the same `(subcheck, description, quote_a, quote_b)` shape as the other
four, so both offending sentences stay inspectable.

`round9/LOGAN_1.txt` states its annual passenger throughput twice and disagrees
with itself:

- stop 1: *"…the architectural design facilitates the efficient flow of **nearly
  12 million passengers annually**"*
- stop 3: *"Boston Logan International Airport, which saw a **record 43.5 million
  passengers in 2024**"*

Both are the airport's annual passenger total; 12M and 43.5M cannot both be it.
No knowledge of the world is needed — the tour refutes itself.

## The hard part: what "the same quantity" means

The check keys on **the unit and the measured noun, never on the number**, and adds
two more gates learned from the corpus. All three are required to hit the ticket's
false-positive bar.

1. **Unit + noun, grouped into classes** (`_NUMERIC_CLASSES`): `passengers`,
   `acres`, `height_ft` (feet), `height_m` (metres), `runways`, `terminals`,
   `flights_air`, `operations`, `workforce`, `stories`. Two figures are only ever
   compared inside one class. So *285 feet* and *400,000 flights* are different
   units and never compared; *413,409 aircraft operations* and *43.5 million
   passengers* are different nouns and never compared. A year (1943), a street
   number and a count of stops carry no measured-noun unit, so they are not
   measurements at all and never enter the comparison. A year label on a real
   measurement (*annually* vs *in 2024*) does **not** split it — both are annual
   totals of the same noun, so the 12M/43.5M pair still collides.

2. **Venue-aggregate metrics only, never event counts** (`_EVENT_FRAME`).
   *"43.5 million passengers [the airport] saw"* is a whole-of-venue total.
   *"over 850 parishioners gathered"* / *"1,000 marched"* / *"1,500 attended his
   farewell"* are attendances at **distinct events** — different measurements, all
   correct, exactly the ticket's own *"1923 opening vs 1959 Massport: different
   events"* principle. Event verbs (gathered, attended, marched, filled, packed,
   rose, present, …) exclude them, so a church tour reciting three different crowds
   stays clean.

3. **Same subject** (`_AIRPORT_NAME`, `_COMPARISON_FRAME`, `_OWN_DEICTIC`).
   A Logan tour may legitimately cite Atlanta for scale: *43.5 million passengers in
   2024* (Boston) beside *106.3 million passengers in 2025* (Hartsfield–Jackson
   Atlanta). Two airports, two measurements. A figure whose sentence names a foreign
   airport, or is framed as a comparison (Atlanta / Hartsfield / "world's busiest" —
   a superlative Boston Logan never claims), is bucketed to that subject and never
   compared with the venue's own figures. Subject is resolved on the sentence
   itself; the next sentence is consulted only when the number is orphaned (no
   airport, no own-deictic) **or** the next sentence opens with an anaphoric
   demonstrative naming a foreign place ("…3 million passengers in 2025. **This
   Atlanta hub**…"), which is how the corpus's mangled sentence-splices attach the
   identifying place. This is what separates the real conflict in `round9/LOGAN_1`
   (both figures the venue's own) from the six other multi-value Logan tours (second
   figure is Atlanta's).

The check never decides which number is right — the contradiction itself is the
finding (D577). It fires only when it can produce both quotes.

## Acceptance — evidence

### Verbatim regression tests (`test_local541_numeric_conflict.py`, 11 tests)

Every offending string is asserted **present in the real `round9/LOGAN_1.txt`**
before being fed to the checker, so the test cannot drift from the evidence.

- `test_verbatim_quotes_are_present_in_the_real_file` — the two passenger
  sentences and the negative-control strings (285 feet, 400,000 flights, 1943 ×3)
  are confirmed in the file.
- `test_numeric_conflict_is_found_in_logan_1` — the 12M/43.5M pair fires, class
  `passengers`, both sentences reported verbatim.
- `test_score_tour_reports_numeric_and_attribution_conflict` — `score_tour()` on
  `round9/LOGAN_1.txt` reports **both** `numeric_conflict` and the pre-existing
  `attribution_conflict`; adding the new one does not remove the old one.

### Negative controls (all stay clean — the real test)

- `test_height_and_flights_do_not_conflict` — *285 feet* vs *400,000 flights*
  (same stop, verbatim sentences): different unit and noun. Clean.
- `test_repeated_consistent_year_is_not_a_conflict` — *1943* stated three times
  with the same value: repetition of a consistent figure, and a year is not a
  measurement. Clean.
- `test_different_events_different_years_do_not_conflict` — *1923* opening vs a
  later event year: different events, both correct. Clean.
- `test_operations_and_passengers_are_different_quantities` — *413,409 aircraft
  operations* vs *43.5 million passengers*: same airport, same year, different
  measured noun. Clean.
- `test_event_crowd_counts_do_not_conflict` — a church tour with 400 / 850 / 1,000
  parishioners at distinct events. Clean.
- `test_comparison_to_another_airport_does_not_conflict` — 43.5M (Boston) beside
  106.3M (Hartsfield–Jackson Atlanta). Clean.

### Measured false-positive rate — all 48 tour files in `TOURS_FOR_REVIEW/`

`test_numeric_conflict_fires_on_exactly_one_file_across_the_corpus` walks every
`.txt` under `TOURS_FOR_REVIEW/` (48 files) and asserts `numeric_conflict` fires on
**exactly one**: `round9/LOGAN_1.txt`. **Zero false positives.**

| # | File | Hit? | Sentence A | Sentence B | Verdict |
|---|------|------|-----------|-----------|---------|
| 1 | `round9/LOGAN_1.txt` | **YES** | "…the efficient flow of nearly 12 million passengers annually." | "…Boston Logan International Airport, which saw a record 43.5 million passengers in 2024." | **TRUE** — same annual passenger total, 12M ≠ 43.5M, both the venue's own |
| — | other 47 files | no | — | — | — |

Multi-value passenger figures that were correctly **suppressed** (subject/scope
gates), and why:

- `LOGAN_handoff_1`, `LOGAN_storyfirst_1`, `round2/LOGAN_1` — second figure is
  *106.3 million … Hartsfield–Jackson Atlanta* (foreign subject).
- `round4/LOGAN_1`, `LOGAN_tour_2` — second figure is a sentence-splice fragment of
  Atlanta's *106.3 million … in 2025*, identified by the following *"This Atlanta
  hub"* / *"world's busiest"* (foreign subject).
- Church tours with 400/850/1,000/1,500 parishioners — event attendances at
  distinct occasions (event frame).
- `acres` (2,384), `runways` (six), `terminals` (four), `flights`, `operations`,
  `workforce` (16,000) — internally consistent within every tour; no cross-value
  pair exists.

This **matches LOCAL-536's standard** (its survey gave 2 hits across 48 with zero
false positives); this survey gives 1 hit with zero false positives.

### No regressions

- `test_local536_self_contradiction.py` — 10/10 pass (the four earlier sub-checks
  still fire and both round-9 tours still report `self_contradiction`).
- `test_local541_numeric_conflict.py` — 11/11 pass.
- All tour_quality-dependent suites together — **116/116 pass**
  (`test_local527`, `test_local530`, `test_local537`, `test_local539`, `d585`,
  `local494`, plus the two above).

## Files

- `tour_quality.py` — added `_find_numeric_conflict` and its helpers
  (`_NUMERIC_CLASSES`, `_MEASURE`, `_EVENT_FRAME`, `_AIRPORT_NAME`,
  `_COMPARISON_FRAME`, `_OWN_DEICTIC`, `_venue_tokens`, `_sentence_subject`); wired
  it into `_find_self_contradictions` as the fifth sub-check `numeric_conflict`.
- `test_local541_numeric_conflict.py` — new regression + survey tests.

No changes to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md,
`.continuous_dev/STATUS.md`, or any tour file.
