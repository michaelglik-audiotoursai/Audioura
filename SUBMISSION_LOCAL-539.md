# LOCAL-539 — `offsite_entity`: a place framed as part of a tour that is not a stop

**Branch:** `LOCAL-539-offsite-entity-gate`
**Base:** `storied` (`eded48a`) — verified `git merge-base --is-ancestor eded48a HEAD` → exit 0.

## Summary

Added an `offsite_entity` defect to `tour_quality.py`, wired into `REQUIRED_CLEAN`
and `score_tour()`. It flags a named place that is **framed as part of the tour**
(an endpoint, a covered stop, the next stop) when that place is neither the venue
nor one of the tour's stops. The check keys on **framing, not distance** — it never
consults geography.

Both round-9 tours that scored CLEAN now report `offsite_entity`. Across all 48
`.txt` tours in `TOURS_FOR_REVIEW/`, the check fires exactly twice — both true
positives — for a **0% false-positive rate**.

## First question: does this need new code? (geo_refutation wiring)

The task said to check whether `geo_refutation` already answers this. It does not,
and here is the grep that settles it:

```
$ grep -rn "geo_refutation" --include='*.py'
user_stops_validate.py:6:  `geo_refutation` exist to judge that. ...
user_stops_validate.py:31: ... geo_refutation
user_stops_validate.py:95:      refute_km      distance threshold override for geo_refutation.
user_stops_validate.py:125:            import geo_refutation as gr
tour_quality.py:397:            from geo_refutation import refute_claims
sentence_split.py:17:  The same defect hit LEAD's own `geo_refutation` module ...
tests/test_local521_user_stops_validate.py:21: # ... geo_refutation fixtures
tests/test_d577_geo_refutation.py:4:import geo_refutation as gr
```

`geo_refutation` is imported by `tour_quality`, `user_stops_validate`, and
referenced in `sentence_split` — and **never by `generate_tour_text_service.py`**
(confirmed: `grep -n geo_refutation generate_tour_text_service.py` → no match).

More important than the wiring: `geo_refutation` is **the wrong instrument** for
this defect, by its own design. It refutes a **binding claim** — "a distant place
asserted as the location, jurisdiction or container OF the venue or stop" — using a
150 km distance threshold. LOCAL-539 is a different failure:

- The distinction here is **framing, not distance.** A tour may legitimately talk
  about anywhere on earth. `geo_refutation`'s own docstring makes this the point:
  *"a refuge for Irish Catholic immigrants" and "trained in Paris" are legitimate
  history in a Newton tour.* The defect is not that St Mary's Cathedral is far away
  — it is that the tour **claims it as one of its own endpoints.**
- The same place can be right and wrong in the same tour. In `round9/CHURCH_1`,
  "Mary Immaculate of Lourdes" is named correctly in stop 2 ("a short distance away
  in Newton Upper Falls") and wrongly in the epilog ("That's 4 stops — Mary
  Immaculate of Lourdes"). A distance test cannot separate these — they are the same
  distance. Only framing separates them.

So this is **new code** — a framing check — not a wiring job. `geo_refutation` is
left exactly as it was.

### Should `geo_refutation` be wired into `generate_tour_text`?

Out of scope here, but noted as the task requested. `geo_refutation` (and this new
check) score tours **after** generation; they do not gate the generation path.
Moving refutation into `generate_tour_text_service.py` so a refuted claim is caught
before it ships is a plausible improvement — but that is a generation-path change
with its own blast radius (it can suppress content mid-generation, and D577 governs
what may be suppressed vs hedged). **It belongs in its own dispatch with its own
evidence and is deliberately not done in this task.**

## The defect, verbatim

`TOURS_FOR_REVIEW/round9/LOGAN_1.txt`, stop-1 orientation:

> "The tour spans from the bustling Terminal A Main Concourse to the efficient
> Terminal A Baggage Claim, all within the same building. **St. Mary's Cathedral,
> dedicated by pioneer priest Fr John Therry**, and Gustave Eiffel's iconic Control
> Tower **mark the endpoints**."

St Mary's Cathedral and Fr John Therry are in Sydney, Australia. Nothing in the tour
is in Australia, and the previous sentence already named the real endpoints.

`TOURS_FOR_REVIEW/round9/CHURCH_1.txt`, epilog:

> "**That's 4 stops — Mary Immaculate of Lourdes** showcases collaborative stained
> glass art…"

Mary Immaculate of Lourdes is a different church, in Newton Upper Falls. The tour's
own stop 2 says so, and correctly frames it as elsewhere.

## Approach

A tour owns exactly two kinds of place: its **venue** (from the title line
`Step-by-Step Audio Guided Tour: <venue>, …`) and its **stops** (from `Stop N:`
headers). Everything else named in prose is fair game *unless it is put inside a
membership frame* — a phrase that asserts the place is on the itinerary:

| Frame | Example |
|---|---|
| `<Place> … mark(s) the endpoint(s)` | "St. Mary's Cathedral … mark the endpoints" |
| `That's N stops — <Place>` (first named place) | "That's 4 stops — Mary Immaculate of Lourdes" |
| `This tour covered/covers <Place>` | "This tour covered Control Tower and …" |
| `next stop, <Place>` / `next stop is <Place>` | navigation slot |

The place captured by a frame is a defect **iff** its tokens are not a subset (in
either direction) of the venue or any stop name. The subset test lets a partial
reference like "Concourse" resolve to the stop "Terminal A Main Concourse", while
"St. Mary's Cathedral" and "Mary Immaculate of Lourdes" match nothing and are
flagged. **Distance is never consulted.**

Why only the *first* named place after "That's N stops —"? Because that is the slot
a well-formed recap fills with one of its own stops; the rest of the recap is story
prose ("…renamed in 1943 to honor Major General Edward Lawrence Logan…") thick with
people and events that must not be read as itinerary. Scanning the whole recap tail
would manufacture dozens of false positives; scanning the itinerary slot finds the
one real defect. This was checked against every recap in the corpus (see below).

New symbols in `tour_quality.py`: `find_offsite_entities`, `_own_places`,
`_norm_place`, `_MEMBERSHIP_FRAMES`, `_OFFSITE_PLACE`, `_TOUR_TITLE`,
`_PLACE_LEADING_STOP`. `offsite_entity` added to `REQUIRED_CLEAN` and the module
docstring's defect list; the detection block added to `score_tour()`.

## Tests

`tests/test_local539_offsite_entity.py`. Every passage is **sliced from the real
files at runtime, never retyped** — the slice helper raises if a marker is absent,
so a test can never assert on a passage that is not in the file.

The core of the suite is one pair — the **same church, same tour, one right and one
wrong**:

- `test_church_epilog_passage_is_flagged` — the epilog "That's 4 stops — Mary
  Immaculate of Lourdes" is flagged (POSITIVE).
- `test_church_stop2_contrast_is_clean` — the stop-2 body "A short distance away in
  Newton Upper Falls… At Mary Immaculate of Lourdes…" is **clean** (NEGATIVE
  control). If the check ever keys on the place instead of the framing, this fails.
- `test_same_church_one_right_one_wrong_in_the_same_file` — on the real file, the
  church appears ≥2 times; the epilog frame is flagged, the contrast frame is not.

Plus: `score_tour()` gates both round-9 files; a bare mention of a distant place
("trained in Paris", St Mary's Cathedral named only as a stylistic example) stays
clean; and a recap slot filled with a real stop (incl. partial "Concourse") stays
clean.

```
$ python3 -m pytest tests/test_local539_offsite_entity.py tests/test_local527_fabricated_attribution.py -q
26 passed in 0.21s
```

No regressions across the scorer suite:

```
$ python3 -m pytest tests/test_d585_person_counter.py tests/test_local305_missing_stop_fairness.py \
    tests/test_local306_inflight_scoring.py tests/test_local339_corpus_and_person.py \
    tests/test_local345_corpus_in_body.py tests/test_local346_bridge_vs_thin_row.py \
    tests/test_local352_narrative_arc.py tests/test_local357_forced_stops.py \
    tests/test_local530_verb_object_dropped.py tests/test_d584_person_cap.py -q
139 passed, 3 skipped, 5 warnings in 2.88s
```

(The 5 warnings are pre-existing `return`-instead-of-`assert` style warnings in
`test_local306_inflight_scoring.py`, unrelated to this change.)

## False-positive measurement — all tours in `TOURS_FOR_REVIEW/`

Scanned **every** `.txt` tour under `TOURS_FOR_REVIEW/` with `find_offsite_entities`.
The task text says "46 tours"; the directory actually holds **48** `.txt` files, so
all 48 were measured (nothing excluded).

**48 files scanned · 2 hits · 2 true positives · 0 false positives · FP rate 0%.**

| File | Place flagged | Frame (sentence) | Verdict |
|---|---|---|---|
| `round9/LOGAN_1.txt` | `St. Mary's Cathedral` | "St. Mary's Cathedral, dedicated by pioneer priest Fr John Therry, and Gustave Eiffel's iconic Control Tower **mark the endpoints**" | **TRUE** — cathedral is in Sydney; stops are Main Concourse, Jetbridge, Control Tower, Baggage Claim. Framed as an endpoint but is neither venue nor stop. |
| `round9/CHURCH_1.txt` | `Mary Immaculate of Lourdes` | "**That's 4 stops —** Mary Immaculate of Lourdes showcases collaborative stained glass art…" | **TRUE** — a different church in Newton Upper Falls; stops are Nave, Stained Glass Windows, Altar, Narthex. Framed as a covered stop but is not one. |

No other tour in any round produced a hit — including the 46 that recap their stops
in the same "That's N stops — …" / "This tour covered …" epilog form, because in
every one of those the framed place is an actual stop.

## Files changed

- `tour_quality.py` — new `offsite_entity` detector + wiring.
- `tests/test_local539_offsite_entity.py` — new regression suite.
- `SUBMISSION_LOCAL-539.md` — this file.

No tour files, `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
`.continuous_dev/STATUS.md` were edited.
