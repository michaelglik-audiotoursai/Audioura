# SUBMISSION — LOCAL-897 (Phan Thiet driving tour leftovers after 896)

Branch `LOCAL-897-route-tour-leftovers` on 91c86611 (`git merge-base --is-ancestor 91c86611 HEAD` = 0).
Ledger `LOCAL-897`: **$0.3390 of $0.45**. One live run, 367 meter rows. No second run.

## Verdict
- **Met live:** pins 5/8 or better (8/8 delivered), no filler, Stop 5 has the D760 disclosure, the legend uses the evidence's own words (the auditor marks it supported), and the 896 checks still pass.
- **NOT met live:**
  - **Body minutes: 1** (Stop 4).
  - **Stop 8 shipped with no body.**
  - **The 4 route-place pins are wrong.** They sit on the destination geocode, which landed on Phan Thiet, about 25 km from Ta Cu.
  - **Audit unsupported: 3 real** (the raw list has 24; see the audit row).
- I found and fixed all of these offline after the run (commit dac28a32). Those fixes are **not proven live**. LEAD decides whether to spend on another run.

## Live run (`-p local897`, ports 26300/26302/26303/56097, job f01e7557)
Harness: `run_local897_real_path.py` (the 896 harness, renamed, plus 897 rows and report lines).

| check | result |
|---|---|
| job status | completed |
| 8 stops, user order, user titles | PASS |
| header | `Caty Mui Ne Resort to Ta Cu Mountain - Driving Tour` PASS |
| off-region sentences (Fansipan/Sa Pa/1955/65/6:00) | 0 PASS |
| "Ham Tien" on stops 4–7 | none PASS |
| minutes/compass in Directions without both pins | none PASS |
| closing names origin + destination, no "city" | PASS |
| legend disclosed as legend | PASS (Stop 6, evidence wording) |
| **pins k/8** | **8/8 delivered** (D762 log `2/8`). **4 of the 8 are wrong**: see below |
| **Stop 5 case** | **disclosure**: the bundle has no cable-car facts for this destination (see below) |
| **filler count** | **0** |
| **body minutes count** | **1 — FAIL** (Stop 4: "about 40 minutes and Phan Thiet City") |
| **audit unsupported** | the raw list has **24**. 21 of them say "Supported by evidence: …" (gpt-4.1 put supported claims in the list). **3 are real**: two Stop 1 nuances (the "50 km coast" and "resorts and shops" wording) and the mangled Stop 4 sentence. The legend sentence is now marked supported. |
| **meter total** | **$0.3390** |

### Per-stop pin in/out lines (live log)
```
stop 1 'Leaving Mui Ne …'            model (10.981999,108.251183) INSIDE; final same (user_share_link)
stop 2 'Phan Thiet and the Ca Ty …'  model (10.9332,108.1062)     INSIDE; final same (serper)
stop 3 'Dragon fruit country …'      model (10.7591,107.9663)     INSIDE; final same (no reference, 896 exemption)
stop 4 'Arriving at Ta Cu …'         model (10.9304,108.1961)     INSIDE; final (10.928631,108.088493) (route_place)
stop 5 'The cable car ascent'        model (10.9426,108.2473)     INSIDE; final (10.928631,108.088493) (route_place)
stop 6 'Linh Son Truong Tho Pagoda'  model (10.813277,107.894085) INSIDE; final same (user_share_link)
stop 7 'The Reclining Buddha'        model (10.9352,108.2295)     INSIDE; final (10.928631,108.088493) (route_place)
stop 8 'The summit views …'          model (10.9402,108.2021)     INSIDE; final (10.928631,108.088493) (route_place)
```
- Diagnosis for 896's question: all eight model pins were **inside** the box this run. Stops 4, 5, 7 and 8 have model pins scattered between Mui Ne and Phan Thiet, not on the mountain. So the in-box exemption would not have made them right.
- The new route-place reference fired for stops 4, 5, 7 and 8. But the free geocode of the destination ("Ta Cu Mountain, Binh Thuan province") came back at **10.9286, 108.0885**. That is Phan Thiet, about 25 km from the listener's own pin for the pagoda on the mountain (10.813, 107.894).
- The four pins count toward 8/8, but they are wrong. Honestly that is **4/8 correct + 4 on a bad geocode**. The Directions written from them are wrong too ("Drive southwest for about 25 kilometers" from Stop 5 to Stop 6).

## What changed (code)
All of it lives in `route_content_896.py`, is name-free (D769), and only runs on a route (origin ≠ destination).

1. **Pins: route place as reference** (`stop_references`, `pin_snap.snap_poi_coordinates(route_refs=…)`).
   - `route_box` now remembers each placed route place's geocode.
   - A stop whose title names a route place uses that place's geocode as its reference, and so does every stop after the stop that names the destination. If the stop's model pin is within 3 km of it, the pin is kept; otherwise it snaps to the place.
   - One `[LOCAL-897] stop N …: model pin … INSIDE/OUTSIDE the route box; final pin …` line per stop.
   - *Post-run (offline):* a route place whose geocode lies within 5 km of another route place's geocode counts as a geocoder fallback and is not used. The destination then takes the listener's own pin of a stop at or after the arrival. Replayed on the live coordinates, stops 4–8 get the pagoda's user pin (10.813, 107.894).
2. **Stop 5 thin**: the bundle's cable-car evidence is entirely about another place (Fansipan, 4,626 ft, Sa Pa, Toc Tien). After the 894B strip, nothing is about this destination's cable car. The Ta Cu stop's own evidence says only "a modern cable car" (no length, base station or ride time). **So this is the disclosure case**: `cap_unsupported` writes the D760 honest body + disclosure in place of the mood-only text. Live: done.
3. **Filler** (`cap_unsupported`, run after 889). A sentence on a route stop is dropped when it has no content token in common with the stop's own evidence (other-place evidence removed first) or its title. The honest-body templates, the disclosure, a legend disclosure and the closing are exempt. Live: 0 filler.
4. **Body minutes/distances/compass** (`strip_body_travel`, run after 889 and again in the final delivery pass).
   - "N minutes/km away", "about N minutes", "N km from", "to the north of" are removed as a clause, or the whole sentence goes when the claim is its opening. Plain lengths ("7.2 kilometers long") and "Southeast Asia" are kept.
   - Live miss: Stop 4's sentence was "about 40 minutes from Ham Tien and Phan Thiet City". It also names Phan Thiet, a pinned route place, so my "both ends pinned" exception kept it. The final 896 locality strip then cut "from Ham Tien" and left "about 40 minutes and Phan Thiet City".
   - *Post-run fix:* a TIME claim ("N minutes", "a minute", hours) always leaves a body, because two pins measure distance, not time. The pass also runs after the locality strip now. Replay on the live text removes it.
5. **Legend** (`legend_disclosure` / `legend_sentences`). The disclosure is now the evidence's own sentence ("Linh Son Truong Tho Pagoda is steeped in a legend of healing that is still passed down among the locals."). A plain fact the evidence states about the same people (the royal recognition) is added as a fact. `is_legend_disclosure` accepts this form, so the 855B gate keeps it. Live: the auditor marks it **supported**.
6. **Pinned Directions with model minutes** (896 post-run fix).
   - Live: no Directions line had a digit-"N minutes" form, so the 896 rule never fired. Stop 4 → 5 said "Drive north for about a minute" and was not matched. **So the 896 fix is still not proven live.**
   - *Post-run:* `_MINUTES` now also matches "a minute" / "an hour". Replay: "Directions: Continue to The cable car ascent."

### Other live defects fixed offline (dac28a32)
- **Stop 8 shipped with an empty body.** The 884 pass wrote the honest body, but the delivered stop has only the closing. I could not rebuild the intermediate text to name the pass that removed it. I did find that `cap_unsupported` dropped the closing when it sat on the same line as the body. That is fixed: the closing is split off and never touched. In addition, `fill_empty_bodies` (final delivery pass) gives any empty route stop the D760 body before its Directions or closing.
- **"As you pass. The cable car ascent, …"**: the 635 broken-join repair split the template at the capitalised "The". `sensory_body` now lower-cases a leading article.
- **Stop 1 clause drop left "Mũi Né ward, borders …"**: grammatical but clumsy. Not fixed.

## Offline replay (896 bundle and 897 live text, `tests/test_local897_route_leftovers.py`)
- 896 replay: no "preservation and progress"; no "minutes" in any body; Stop 5 = D760 disclosure; Stops 6 and 7 keep their facts; 8 stops; closing intact. The 896 Directions/off-region checks still pass.
- 897 live text replay (`submission_artifacts/local897/tour_offline_replay_after_postrun_fixes.txt`): filler 0, body minutes 0, Stop 5 D760, Stop 8 has its honest body before the closing, no "As you pass.".
- Tests: 24 new (generic Alpha/Beta/Gamma fixtures plus the 896 replay). The 35 tests in `test_local896_route_content.py` still pass: 3 assertions changed to the new legend wording and nothing else. 59/59 total.
- Regression: grounding/conclusion/pin/itinerary/88x/89x/legend/route families: 852 passed, 13 failed. All 13 are in wallet / local378 / local604 / local666 / local88 files, and those same files show 26 failures on base 91c86611.

## Files
- `route_content_896.py`, `pin_snap.py`, `strict_grounding_gate.py`, `generate_tour_text.py`
- `tests/test_local897_route_leftovers.py`, `tests/test_local896_route_content.py` (legend wording)
- `run_local897_real_path.py`, `docker-compose.local897-proof.yml`
- `submission_artifacts/local897/{tour.txt,evidence_bundle.json,audit.json,tour_offline_replay_after_postrun_fixes.txt}`

Meter logs stay in `_local897_meterlogs/` and are not committed. The `-p local897` stack is down (volumes kept).

## For LEAD
The remaining budget ($0.11) is below one run (~$0.34), so the post-run fixes are **unproven, handing to LEAD**. What a next run would prove:
- the destination collapse guard (pins on the mountain, not Phan Thiet);
- body minutes 0;
- Stop 8 non-empty;
- "about a minute" in pinned Directions replaced.
