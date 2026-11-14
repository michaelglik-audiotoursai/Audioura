# SUBMISSION LOCAL-906X (offline, $0)

Branch `LOCAL-906X-rise-dates-orphans`, base 938f083e (`git merge-base --is-ancestor` exit 0). No live run, no paid call.

## Changes
1. **Length stated as a rise** (`rise_dates_906x.rise_pass`, new). A "rises / climbs / ascends / gains / covers ... N m" sentence is dropped
   when N exceeds every elevation the tour or any evidence states. When N equals a stated "N m long / in length" and the verb is a rise
   verb, it is rewritten to "The line is about N meters long." only if that evidence sentence names a cable car / line / route, else
   dropped. "covers N m" with N a stated length stays (it is a length). "rises 649 meters above sea level" stays. With no elevation
   known nothing is dropped.
2. **Conflicting statue dates** (`rise_dates_906x.year_pass`, new). The 906F cross-stop check never linked the two stops (titles share no
   distinctive word; "statue"/"buddha" are generic heads). The new pass works from the evidence: a built-object sentence whose year is in
   no evidence text, while an evidence sentence about the same object noun states another year, is dropped and logged with both years.
   Needs evidence; with none it does nothing.
3. **Orphan "After his death"** (`leftovers_906f._persony_names`). Root cause: `repair_person_pronoun` already existed, but "the Lower
   Pagoda, Long Doan" made the appositive place name look like a person, so the stop counted as having a person. A name after
   "<place noun>," is now a place. Result: "After Tran Huu Duc's death in 1887 ...".
4. **Leftovers** (`drive_quality_906v.sweep_reason`): "Visitors often combine ...", "local attractions and activities like ...", "jeep tours".
5. **Foreign comparison** (`stub_promo_906t.comparative_unsupported`). It passed for two reasons: `_CMP_CUE` lacked "smaller/shorter/lower/
   younger/narrower/shallower than", and it only read names AFTER the cue ("than this one" has none). Names before the cue now count
   when the cue is followed by this/that/it/the; the stop's own title words and the sentence opener are excluded. It needs an evidence
   sentence with a comparative cue naming one of them. The call site passes the stop title.
6. **Tri vs Y**: within 551 only "Tri" appears, so 906N has nothing to unify; the Tri/Y split is across tours (out of scope). No change.

## Wiring
`rise_dates_906x.run_pass` runs at the end of `leftovers_906f.run_pass` and in `drive_quality_906v.last_word` before the final sweep
(a refill can bring a sentence back). `last_word` still ends in `return final_sweep(...)`.

## Tests
`tests/test_local906x_rise_dates_orphans.py` (16 tests). The usual set, with `tests/test_local88_tour_pollution.py` deselected:
3235 passed, 4 skipped, 0 failed.

## Limits
- Elevations are the maximum over all stated heights in the tour and evidence, not per mountain: a taller mountain elsewhere in the
  job lets a bad rise claim through (chosen so a true claim is never dropped).
- A dropped year sentence loses its other facts too (the "pagoda built in 1861" clause went with the 1972 clause).
- Unproven on a live tour; handing to LEAD for a Mac run.
