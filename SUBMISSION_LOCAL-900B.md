# SUBMISSION LOCAL-900B — wave 47 fixes (offline, $0)

Branch `LOCAL-900B-w47-fixes`, base be8fc75b. No live run, no paid call, no DB write.

## Root causes
- **Pin check used a province centroid.** On a 2-stop tour `_center_858` is never set (it is only built on the walking, >=3-stop path), so `generate_tour_text` fell back to `_area.center_lat/lng` from `area_resolver.resolve_area`, which returns the *city/province* entity's P625 (Binh Thuan, 11.0833,108.0833). `check_pins_against_scope` then "replaced" place pins with it.
- **791C snap had no scope guard.** `snap_pin` only bounds a reference by `scope_center`, and that bound is dark when the centre is None (and an authority P625 is trusted up to 150 km). The stop's own Wikidata P625 (same-named statue, another country) won.
- **Superlative drop cut a clause** (`_cut_clause`) and kept the stub ("is home to.", "…to, measuring 49 meters in length.").
- **Stop 5 rebuilt twice** because `finalize_898` runs twice (delivery pass with `None` evidence, post-gate pass with evidence); `rebuild_honest_bodies` was not idempotent, so the no-evidence pass overwrote the neighbour sentence.

## Changes
1. `place_names_900.check_pins_against_scope(..., ref_precision, ref_source)`: only a place-level reference may replace a pin: the stop's own verified P625, or a centre declared `place`. Coarser (district/city/region/country/unknown) -> `action=skipped_coarse_ref`. Logs `[LOCAL-900B] pin check reference: center precision source usable`. Caller passes source `area_resolver('<city>')` / `city_center_for_request` and precision (`district` if a neighbourhood resolved, else `region`/`city`).
2. `pin_snap.snap_poi_coordinates(..., scope_precision)`: a snap that moves the pin more than the scope radius (BUILDING/CORRIDOR/DISTRICT 15 km, CITY 25 km), or on a route lands outside route box + 10 km, is rejected: `[LOCAL-900B] snap rejected <title> <dist>m (outside scope)`; the shipped pin stays.
3. `route_content_896`: superlative drop removes the whole sentence; `is_fragment` / `drop_fragments` final guard (ends on preposition/article/dangling verb, opens with a comma or bare participle, empty clause between commas, "covers of the") over bodies *and* Orientation, run inside `finalize_898` (before and after the rebuilds) and on every path; `drop_unsupported_comparatives` ("larger than … at X" with names the evidence lacks -> whole sentence).
4. `_HONEST_DONE` memo makes `rebuild_honest_bodies` idempotent (a later pass with no/other evidence keeps a body an earlier pass built; a pass that newly has a neighbour sentence still adds it).
5. Single-place path: `apply_single_place_guards` (called from the every-path delivery guard) drops the "<X> is one you might carry with you." closer, drops fragments, and for tours of <= 2 stops runs `normalize_directions(force=True, max_km=100)`; a leg > 100 km logs `[LOCAL-900B] BUG SIGNAL …` and says "Continue to X." with no distance.

## Item 5 — why "11 meters high" / "built in 1963 by sculptor …" survived (honest report)
The cloud evidence for stop 7 is not in the fixtures, so I cannot say whether it held them. What I verified offline: with evidence that lacks them, `cap_unsupported_numbers` *does* drop "11 meters" (test). So on the cloud either (a) the evidence held "11" (wave 45 said 7 m, so the sources disagree), or (b) the cap did not run for that stop: it returns unchanged when `evidence_by_title` is empty, and skips a stop whose title is not a key (exact folded match only). The delivery pass calls `finalize_898(final, None)`, which never checks. Years and "by sculptor X" had no cap at all (898 `consistent_creators` only reconciles creators between stops). Added: `cap_unsupported_facts` (year / "by <role> <Name>" not in the stop's evidence or title -> clause/sentence dropped), fuzzy title lookup `_ev_for`, and a log `[LOCAL-900B] Stop N: no evidence entry under this title; … NOT checked` so the next cloud run shows which case it is. **Unproven on the cloud**; needs one run to read that log line.

## Not done
- "Use the geocode of the requested PLACE (location/destination)": no new geocode was added (offline task). The reference is the stop's own verified P625; otherwise nothing replaces a pin. With the 552 shape and no P625 the model pins are simply kept.
- Normalization of Directions on non-route tours is limited to <= 2 stops; longer non-route tours are untouched.

## Tests
`tests/test_local900b_w47.py` (42 tests) + fixtures `tests/fixtures/local900b_{tour551,tour551_input,tour552,gen_pin}.txt` (generic names). Two assertions in `tests/test_local900_leftovers.py` changed to the new contract (superlative drop is the whole sentence). Requested suite (`test_local89[6-9]*, 90*, 894*, 87*, 88[0-9]*, 89[0-3]*`, minus `test_local88_tour_pollution.py`): 943 passed, 4 skipped. `test_local893_preview_timeout` failed once under load and passes alone/on rerun (timing).
