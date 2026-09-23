# SUBMISSION — LOCAL-527: Fabricated builder/founder attribution

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-527-orientation-describes-another-stop` · **Base:** storied (65de385)

## Summary

`tour_quality.score_tour` scored both round-8 tours CLEAN even though each carried a
fabricated builder/founder claim. This change teaches the scorer to see the
attribution frame `<built|founded|constructed|established|erected> in <YEAR> by
<NAME>` and gate it as a new `fabricated_attribution` defect, added to
`REQUIRED_CLEAN` so it actually blocks a tour from being called clean.

Two kinds are distinguished:

1. **`dedication`** — the attributed "founder" is the venue's own dedication or
   patron saint (the church "Founded in 1868 by St. Mary Help of Christians"). This
   is caught **offline with certainty**: no church is founded by the saint it is
   dedicated to. Deterministic; always gates.
2. **`unverified`** — a plain builder/founder attribution nothing has confirmed
   (the airport "constructed in 1887–1889 by Gustave Eiffel"). **Offline this can
   only be flagged, not refuted** — proving Eiffel did *not* build it needs a
   source. An optional `verify_attribution(name, year, text)` callback is the
   grounded seam: when a source confirms the name the `unverified` frame clears. It
   **never** clears a `dedication` error.

## Can the fabrication be caught without a grounded call? (D577)

**Partly, and the split is the honest answer:**

- The **dedication-as-founder** case is fully catchable offline with certainty — it
  is a string relationship between the "founder" and the venue's own patron title,
  no external fact required.
- The **generic fabrication** (Eiffel) is catchable offline **only as *unverified***.
  The frame can be detected and flagged, but *refuting* it (declaring it false)
  requires a grounded source. Gemini is returning **HTTP 402 (prepayment credits
  depleted)**, so I did **not** run a grounded verification and did not fabricate
  one. The offline gate flags the frame; the `verify_attribution` hook is where a
  grounded check plugs in when credits are restored.

The defect moved between rounds — round 7 had Eiffel in a stop-1 **orientation**;
round 8 moved him into the stop-1 **body**. The gate targets the attribution frame
itself, not a section, so it holds regardless of where the sentence sits.

## Changes

**`tour_quality.py`**
- `REQUIRED_CLEAN` gains `'fabricated_attribution'`.
- `_ATTRIB_FRAME` — regex for `<verb> in <YEAR>[–<YEAR>] by [honorific] <NAME>`.
  Verbs are the founding/construction set `built|constructed|founded|established|
  erected`. **`designed` and `created` are deliberately excluded** — those are the
  normal verbs of legitimate art attribution ("Nu bleu IV, created in 1952 by Henri
  Matisse"), and including them produced a false positive on a real Matisse tour.
  The name capture keeps a dedication tail (`of Christians`) so "Mary Help of
  Christians" is captured whole rather than clipped.
- `_DEDICATION_CORES` — Marian/patronal title cores (`help of christians`,
  `our lady`, `perpetual help`, `sacred heart`, …).
- `_venue_title(text)` — reads the venue name from the tour's own first line
  (the scorer is not handed the venue name; the tour states it).
- `_find_fabricated_attributions(text)` — returns `(kind, verb, year, name)` per
  hit; `kind='dedication'` when the name carries a dedication core, else
  `'unverified'`. People-groups ("Irish immigrants") and venue-part nouns are
  filtered via the existing `_NOT_A_NAME` / `_NOT_PERSON` vocabularies.
- `score_tour(..., verify_attribution=None)` — new optional grounded-verify
  callback; sets `defects['fabricated_attribution']` and factors into `clean`.

**`tests/test_local527_fabricated_attribution.py`** — 16 tests (new).

## Evidence

All three real sentences verified verbatim in source (en-dash `–`, not hyphen):

| # | Source file | Line | Text | Classified |
|---|---|---|---|---|
| 1 | `TOURS_FOR_REVIEW/round7/LOGAN_1.txt` | 16 (orientation) | "…the iconic Control Tower, a historic structure constructed in 1887–1889 by Gustave Eiffel." | `unverified` |
| 2 | `TOURS_FOR_REVIEW/round8/LOGAN_1.txt` | 16 (body) | "As you traverse this bustling hub, built in 1887–1889 by Gustave Eiffel, you'll uncover…" | `unverified` |
| 3 | `TOURS_FOR_REVIEW/round8/CHURCH_1.txt` | 16 | "Founded in 1868 by St. Mary Help of Christians, this church echoes Monsignor Capik's…" | `dedication` |

Behaviour verified by running `score_tour` on the actual files that previously
scored CLEAN:

```
round8/LOGAN_1.txt   clean=False   fabricated_attribution: unverified "built in 1887 by Gustave Eiffel"
round8/CHURCH_1.txt  clean=False   fabricated_attribution: dedication  "Founded in 1868 by Mary Help of Christians"
round7/LOGAN_1.txt   clean=False   fabricated_attribution: unverified "constructed in 1887 by Gustave Eiffel"
round7/LOGAN_2.txt   clean=False   fabricated_attribution: unverified "constructed in 1887 by Gustave Eiffel"
```

`score_batch(round8 LOGAN_1 + CHURCH_1)` → `all_clean: False, 0/2 clean` (was
2/2 clean before).

**Tests:** `python3 -m pytest tests/test_local527_fabricated_attribution.py` → **16
passed**. Full attribution-related suite (new test + the two other tests that import
`tour_quality`, `test_d585_person_counter` and `test_local494_cache_key_buckets`) →
**46 passed**, no regressions. `test_local494 TestTrimScoresClean` (a tour expected
to score clean) still passes, confirming the clean path is intact.

**False-positive discipline** (offline scan of 105 tour files): 18 flagged — 16 are
the Eiffel/St.Mary defect reproduced across review rounds; 2 are genuine-but-
offline-unverifiable foundings (Fondation Maeght "founded in 1964 by Marguerite and
Aimé"; a 1927 restaurant). Those two are the intended D577 behaviour: a real
founding claim we cannot confirm offline is flagged as *unverified* and would be
cleared by the grounded `verify_attribution` hook. The Matisse artwork attribution
("created in 1952 by Henri Matisse") is **not** flagged — the founding-verb set
excludes art verbs by design.

## Not done / limitations

- **No grounded verification run.** Gemini is HTTP 402. The offline gate flags; the
  grounded refutation seam (`verify_attribution`) is implemented but unexercised
  against a live source.
- The gate is a **scorer** gate — it makes a fabricated attribution stop being
  reported CLEAN. It does not itself rewrite/drop the sentence during generation;
  hedging/dropping per D577 is a downstream consumer of this signal.
- The gate targets the venue-founding frame `in YEAR by NAME`; the reversed order
  (`by NAME in YEAR`) is out of scope for the three reported defects and not
  covered, to keep the false-positive surface small.
