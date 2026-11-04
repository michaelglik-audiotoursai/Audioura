# SUBMISSION LOCAL-866 — user stop lost its Coordinates/Type lines after the 540/474 retry

Branch `LOCAL-866-user-stop-header` (base e0cc5f43, `merge-base --is-ancestor` = 0).

## Cause
1. **LOCAL-540 fired on a false positive.** Re-scoring the saved 862C tour (`tour_quality.score_tour`) gives `self_contradiction: numeric_conflict (height_m): "It is roughly 100 meters away." vs "Directions: Cycle north for about 1000 meters…"`. `_NUMERIC_CLASSES` treats `meters`/`feet` as a *height*; a cycling tour states travel distances in every Directions line, so any two legs "contradict". Fix: `tour_quality._find_numeric_conflict` skips height classes when the sentence has a travel/distance frame (away, cycle, walk, head, reach, Directions, from here…). A real conflict ("100 meters tall" vs "300 meters tall") is still caught (test).
2. **Nothing protected the header lines.** The 540 retry splices an LLM rewrite over the whole `Stop N` block (header lines included); "keep the labels" was only a prompt request. The last stop's block also contains the epilog.

## Fix
- New `stop_headers.restore_stop_headers(text, poi_list)`: for every stop, `Coordinates:` always equals the poi coordinate (inserted/replaced); `Address:`, `Type/Specialty:`, `Specific Examples:` are inserted when missing/empty, never overwritten. Idempotent. A listener-pinned stop's address goes through `_clean_user_stop_address` first so a "15 Đ." stub is never re-introduced.
- Applied: inside `score_and_retry` after the splice and before the re-score (`repair_text=`), after the LOCAL-628 editor pass, and just before the file write.

## Tests — `tests/test_local866_stop_header.py` (6) + 862/540/541 suites: 103 passed
Includes: a retry that returns a block with no header lines keeps `Coordinates` equal to the poi coordinate; wrong coordinate replaced; clean text unchanged; every stop restored in order; real height conflict still detected; the 862C tour no longer self-contradicts.

## Live (one run, 7-stop Sophia, TASK_BUDGET_ID=LOCAL-866, cap $0.30, Mac-local, no DB/shared containers)
LiveRunMeter total **$0.2615** (openai 0.2255 + serper 0.0360). **PASS: 7/7 stops carry a Coordinates line, each 0 m from its input pin** (`submission_artifacts/local866/live_tour_7stops.txt`). Stop 7 Acoustic Bar: `10.781195, 106.689920` + `Type/Specialty: Live music bar`.

## Honest caveats
- In the live run 540 fired on `repeated` (stop-1 orientation), **not** numeric_conflict, so the false positive was proven offline on the saved 862C text, not re-observed live. After that retry `[LOCAL-866] restored stop header lines on stop(s) [3,4,5,6,7]` fired. I do not know which labels it added: the label detail was added to the log *after* the run, and a second run would exceed the budget. Final output has no `Address:` lines on any stop, as in 862C, so whatever was restored there was later removed or was a coordinate correction.
- The Address stub guard and the label-detail log line were added after the live run; covered by unit test only.
- **"271w → 57w" not reproduced.** That shrink is the LOCAL-474 post-gate count (deletion gates removing sentences, earlier than 540), not a 540 rewrite. This run shows the same gates shrinking every user stop (e.g. Acoustic Bar 141w → 67w, Rambutan 203w → 101w). I did not change those gates; whether they over-delete is a separate question. 474 does not touch header lines (they are assembled from the poi), so the header loss came from the 540 splice.
- Type/Specialty is absent on Rambutan, A Star is Born and Longan: the poi has none (same as 862C), so there is nothing to restore.
