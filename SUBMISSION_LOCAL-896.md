# SUBMISSION — LOCAL-896 (Phan Thiet driving tour content; follow-up to 894/894B)

Branch `LOCAL-896-route-tour-content` on efa88f68 (`git merge-base --is-ancestor efa88f68 HEAD` = 0).
Ledger `LOCAL-896`: **$0.3314 of $0.45** (one live run, metered, 375 meter rows). No second run.

## Verdict
- **Fixed and seen live:** items 1, 2, 4, 5, 6 (below). Item 7 (filler) is only partly fixed.
- **Item 3 (pins) is NOT met: 4/8 in the delivered text, target ≥ 5/8.** Up from 1/8 (894B). Handing the rest to LEAD.
- One post-run offline fix is not live-proven: pinned-directions minutes (see "Not proven live").

## Live run (`-p local896`, ports 26200/26202/26203/55996, job 415ddeee)
Harness: `run_local896_real_path.py` (the 894B harness, renamed, plus the 896 rows). All rows from 894B still pass.

| check | result |
|---|---|
| job status | completed |
| 8 stops, user order, user titles | PASS |
| header | `Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour` / `Tour-Category: driving` PASS |
| **pins k/8** | **4/8 delivered** (stops 1, 2, 3, 6); D762 log line `2/8` — **FAIL vs target 5/8** |
| **off-region sentence count** | **0** (Fansipan / Sa Pa / Toc Tien / 1955 / 65 passengers / 6:00 a.m.) |
| "Ham Tien" on stops 4–7 | none (PASS) |
| minutes / compass in Directions with no pin | none (PASS) |
| closing | "From Caty Mui Ne Resort to Ta Cu Mountain, this route is the one you chose — your own path, in your own order. That's 8 stops in all." No "city", no 3-stop list (PASS) |
| **legend disclosure** | Stop 6: "Local legend ties Linh Son Truong Tho Pagoda to healing associated with Empress Dowager Tu Du, a story told by locals rather than documented history." (PASS) |
| filler "tides meet / threshold where" | gone (PASS); **another filler sentence is still in Stop 8** (see below) |
| **audit unsupported count** | **1** (894B: 4). It is the legend sentence itself: the auditor says the evidence presents the story as a historical event, so "only a legend" is "unsupported". |
| per-stop sentences | 3 · 7 · 4 · 3 · 2 · 5 · 5 · 5 |
| **meter total** | **$0.3314** |

## What changed (code) — all in commit 8e12be77 unless marked
New module `route_content_896.py` (name-free, D769; state set per generation from `derive_request_place`).

1. **Other-place evidence → every sentence only it backed goes** (`sentences_backed_by`, hooked in `strict_grounding_gate.ground_tour_text`).
   - Word-level, not proper-name matching: a sentence is dropped when ≥ 2 distinctive tokens (or any number, e.g. "6:00") are shared with the dropped evidence and the stop's kept evidence / title / route places do not explain them.
   - A stop emptied this way gets the honest non-factual body + D760 disclosure, written in place.
   - Live: Stop 5 lost "climate changes rapidly", "leave the coastal heat" and two more re-narrated variants; no ticket-office line this time.
2. **Origin locality** (`strip_origin_locality`, final delivery pass in `generate_tour_text`). With a route, every stop after the first whose title does not name the locality loses "in Ham Tien, Mui Ne" / "this quiet corner of Ham Tien". An unrepairable sentence is dropped. The route's own place names ("Caty Mui Ne Resort") and "the drive back to Mui Ne" are not touched.
3. **Directions** (`simplify_directions`, same final pass). A pin on both ends is required for anything but `Continue to <next>.`
4. **Closing** (`tour_conclusion.py`). Route → "From <origin> to <destination>, this route is the one you chose…". The origin/destination are allowed through the 864B/652 name checks (they are the listener's words).
5. **Legend** (`legend_disclosure`, end of `ground_tour_text`; route only). If a sentence of the stop's own evidence that names the stop calls its story a legend, ONE sentence "Local legend ties X to …, a story told by locals rather than documented history." is added. `[LOCAL-855B]` no longer drops this form (`is_legend_disclosure`). Other legend sentences are still dropped.
6. **Filler on the user-list path** (`key_fact_coverage.finalize_stop(user_list=…)`). The no-evidence branch used to skip the cap. It now caps the stop's own sentences (the closing riding on the last block is left alone) and pads with the plain look-around body + D760 disclosure rather than leaving silence. Extra reflective patterns: "a threshold where", "past … future", "converge".
7. **Pins — route region as the scope box:**
   - `route_content_896.route_box`: origin + through + destination geocoded inside the request's region (free Nominatim; queries are always region-qualified, a bare "<name> Mountain" resolved to another continent; outliers > 150 km are ignored; 25 km margin).
   - D762 preview: orchestrator sends `route_places/route_region/route_fallbacks`; generator `/preview-stops` passes them to `itinerary_import.preview_stops`, whose city check (`_in_city`) then uses the route box instead of a 25 km radius.
   - 858B early landmark pass and pin-snap scope = the route box.
   - `pin_snap.snap_poi_coordinates(route_box=…)`: a model pin **inside** the route region is not collapsed by the LOCAL-870 "model coordinate, no reference" rule or the cluster rule. Identical-point and marked-fallback collapse still apply.

## Why pins are 4/8 and not 5/8 (diagnosis from the live log)
- The route box was built (3 route places placed): `[10.70, 11.17, 107.85, 108.50]`. The preview used it.
- D762 resolved **2/8** (by the pin precision: stops 1 and 6). Stops 2 and 3 carry 4-decimal model pins; the log shows my "model pin inside the route region is kept" rule firing for stop 3 only, and I did not capture how stop 2's pin survived.
- 858B lookups found "no in-scope authority" for 6 stops, even with the route box (Wikidata + Serper/Nominatim empty).
- LOCAL-870 then cleared the model pins of stops 4, 5, 7, 8 ("only a model coordinate and no reference"). My exemption did not fire for them, so those model pins were **outside** the box (or absent). I did not capture those coordinates, so I cannot say which. Stops 5 and 8 name no place, by design.
- Next step for LEAD: log each stop's model pin + inside/outside in the exemption, or lower the bar for "Ta Cu"-type names by resolving the destination's own Nominatim hit as a reference for stops that name it. I did not re-run.

## Still wrong in the delivered tour (live)
- Stop 8 still has "This tension between preservation and progress is etched into the land … where the quiet mountain meets the restless sea." My patterns did not match it. The cap only fires on flagged reflective patterns.
- Stop 5 is now two atmospheric sentences (no facts): honest, but thin.
- Stop 2 is one very long sentence block from the Cham-prince evidence; Stop 4 says "You are about 40 minutes away" in the BODY (the directions rule covers Directions lines only).
- The auditor flags the legend sentence (above). If LEAD wants the audit count at 0, the framing needs to follow the evidence ("steeped in a legend of healing" is in the evidence; so is Emperor Tu Duc's recognition as fact).

## Not proven live (added after the run, offline-tested)
- `simplify_directions` with pins on both ends: a model-written "N minutes" is replaced by "Continue to X, about D km away." (straight line). On the live tour, Stop 2 → Stop 3 said "about 10 minutes" for pins 1.2 km apart; the replay now gives "Continue to Dragon fruit country – the plantations along the road." The live Directions lines were otherwise as required.

## Tests (offline)
- `tests/test_local896_route_content.py`: 35 tests. Generic fixtures (Alpha/Beta/Gamma…) for every rule, plus a replay of the 894B bundle through gate → closing → 889 → locality → directions: no Fansipan/1955/65 passengers/6:00/ticket office, no "Ham Tien" on stops 4–7, no minutes/compass, closing names both ends, legend disclosed, no tides/threshold, Stop 5 honest and non-empty.
- Regression: the 1,055 tests in the grounding / conclusion / pin / itinerary / 88x / 89x families give the same 16 failures before and after my change (pre-existing: local373, local378, local520, local88_tour_pollution).

## Files
`route_content_896.py` (new), `strict_grounding_gate.py`, `key_fact_coverage.py`, `tour_conclusion.py`, `user_stop_narration.py`, `pin_snap.py`, `itinerary_import.py`, `generate_tour_text.py`, `generate_tour_text_service.py`, `tour_orchestrator_service.py`, `run_local896_real_path.py`, `docker-compose.local896-proof.yml`, `tests/test_local896_route_content.py`, `submission_artifacts/local896/{tour.txt,evidence_bundle.json,audit.json}`.
Meter logs stay in `_local896_meterlogs/` (not committed). Stack `-p local896` brought down (volumes kept).
