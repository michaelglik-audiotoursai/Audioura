# SUBMISSION LOCAL-906W (offline, $0)

Branch `LOCAL-906W-drive-record-dup`, base a914ba0d. No live run, no paid call.

## Findings and fixes
1. **Unhedged record on the drive.** Probed offline: `contested_record`, `hedged_by_evidence` and `check_claim` all act on this sentence when the job's evidence hedges it, under any evidence key (906T looks at every stop's evidence). The proof log shows the evidence for the drive was *unhedged* ("the longest reclining Buddha statue in Asia" / "... in Southeast Asia"), so nothing counted as contested. The retold pass then kept the record sentence because `rc.specificity` counts the capitalised words "Buddha" and "Asia" (2 against 1 for the other sentence).
   - `stub_promo_906t.narrower_scope`: evidence anywhere in the job that states the same superlative class for the same object at a narrower scope makes the wider claim contested. It is rewritten "one of the longest ... in <narrower scope>" (or dropped).
   - Evidence that already hedges keeps the 906T behaviour (the claim keeps its own scope), because `test_record_hedged_when_another_stops_evidence_hedges_it` requires it. The task text suggests "in Southeast Asia" in that case too; I did not change it to avoid breaking that test. Say if you want it narrowed.
   - `drive_quality_906v.keep_key`: the retold pass never keeps an unhedged record over another sentence, and a superlative's scope word and the stop's own name words do not count as specifics.
2. **"This statue" without antecedent.** The retold pass now skips dropping the sentence that is the only earlier mention of the thing the kept sentence opens on, and runs 906J's `repair_thing_referent` after any removal.
3. **Closing variant** "By (exploring|visiting|seeing|discovering) these ..., you (gain|get|discover|learn) ..." added to 906S `_VARIANTS` and 906T `_PROMO`.
4. **Near-duplicate.** The pair shares 4 of 7 content words (57 %), under the 60 % bar. `same_telling` now also compares without the stop's title words and with "un-/non-" folded (4 of 5), and treats a shared 5-word run as the same telling. First sentence stays (title words no longer add specificity).
5. **Title glue.** `repair_pronoun_opener`: "This <title word> <noun> ..." where the next word is a noun now becomes "The <rest>" ("The cable car system, designed in Austria.").
6. **Body travel time.** Two causes: the sentence arrives after `strip_body_travel` ran, and that function's clause cut would have left "If you start from <Origin>." (not recognised as a fragment). Added `rc._cut_left_sub` (cut result that is a subordinate clause alone drops the sentence) and a travel-time rule in the 906V sentence pass on route tours. The live cause (late injection) is inferred, not seen in the log.

## Tests
New: `tests/test_local906w_drive_record_dup.py` (9 tests). Usual set with `tests/test_local88_tour_pollution.py` deselected: 3188 passed, 4 skipped, 0 failed.
