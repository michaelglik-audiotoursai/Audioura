# SUBMISSION LOCAL-909 — "A to B" driving tour: order, offshore pin, missing coordinates, transit junk, leg minutes

Branch `LOCAL-909-route-order-pins` (base 7d952b39). Offline, $0: no live run, no paid API call, every lookup mocked.

## Where each defect came from (drive_proof log)
1. **Order.** "Mui Ne to Ta Cu Mountain" is not a "from X to Y" description, so the 896 route state stayed off. `[ROUTE-ORDER] Only 0 stops with coordinates` skipped routing. LOCAL-576 pinned only the END anchor and left the model's order for the rest (lighthouse first). Nothing ordered by position.
2. **Pin in the sea.** The model's coordinate. No reference was found (`left unsnapped (no in-scope reference)`). It lay inside the padded province box, so 906D did not flag it.
3. **Last stop without coordinates.** `[LOCAL-870] user stop has only a model coordinate and no reference — announced with no pin` cleared it. The delivered stop then had no `Coordinates:` line, so `topic_picker.leg_minutes` returned None for its leg.
4. **Leg minutes.** `114.6` = 50 km straight × 1.3 ÷ 35 km/h, from the offshore pin. The Directions' own "roughly 51.4 km" was never read.

## Changes
- `route_order_909.py` (new, pure, injected lookups):
  - `parse_route_request` reads "A to B[, region]" from the grammar alone.
  - `order_stops` / `order_poi_list` sort by projection on the A→B line, destination last. A stop with no pin or a water pin keeps its place. Largest step back is ≤ 20 %.
  - `water_pins` marks an unverified model pin with no land address (`geocode_stops.reverse_is_land`, a new function). A failed lookup returns None and is never read as water.
  - `restore_pins` gives every stop a pin, best source first: snap / place reference → route place reference → Wikidata / pool → destination geocode → in-box model pin (approximate) → point between its neighbours on the route (approximate). It logs `[LOCAL-909] Stop N delivered without coordinates -> <fix>`.
  - `finalize_route_pins` runs after 791C / 906D: water check, restore, then re-order on the FINAL pins. It re-orders only when the order doubles back more than 20 % or the destination is not last.
  - `finalize_text` is the delivery safety net. It restores a missing `Coordinates:` line from the final pin and starts the first Directions at the origin ("From <Origin>, head <compass> to <Stop 1> — roughly N km away.").
- `generate_tour_text.py` wiring (all non-fatal, A-to-B only):
  - request and mode state after `[TRANSPORT]`;
  - first order after the LOCAL-576 anchor pin (skipped for a user stop list, D867/894);
  - the pin pass before `_n_snapped_791c`;
  - the delivery pass on both final paths.
- `leftovers_906f.py`: `drop_driving_practical`, called from `run_pass` on a driving tour only. It drops bus/metro/train numbers, "from the mall", "heading in the right direction", "morning or afternoon depending on your schedule" and "you can take a cable car or walk" advice. A walking tour is untouched (test).
- `topic_picker.py`: rural car speed 35 → 45 km/h. New `leg_minutes_source` returns (minutes, source). A stated road km is not inflated.
- `fillings_payload.py`: parses "roughly N km" from the Directions sentence that names the next stop → `leg_distance_km`. Logs `[LOCAL-909] leg N M min (source: ...)`.
- `tests/test_local907_topic_library.py`: 3 expectations updated for the 45 km/h rural speed (40.1 → 31.2 min; the 35 km leg uses 45 km).

## Tests
`tests/test_local909_route_order_pins.py` (11 tests) replays the logged shape with generic names:
- stops in A→B order, the largest step back ≤ 20 %;
- the offshore pin replaced by the reference, the last stop's pin restored (logged);
- every stop block has Coordinates, and the first Directions start at the origin;
- no bus / schedule / "cable car or walk" sentences on a driving tour, the orientation facts kept;
- a walking tour keeps "Take bus 4 ...";
- fillings for every leg ≥ 8 min; the logged 51.4 km leg is 68 min (60–75 expected), not 114.6.

The 906/907/896-899/90x/894/87x/88x/89x/905/791 files plus the new file: 2150 passed, 4 skipped.
The `-k "ground or conclusion or pin or itinerary or snap or pool or route or leg"` sweep (excluding `test_local88_tour_pollution.py`): 987 passed, 12 failed. All 12 fail without my changes too (`test_local604_plan`, `test_local666_*`, `test_local824_route_parity`, `test_local378`, `test_local500/520` cache key). The 3 wallet-route failures appear only in the combined run and pass in isolation.

## Not proven (needs the field test, no live run was made)
- The real reverse-geocode answer for open water (Nominatim "Unable to geocode" assumed).
- The second ordering runs after the bodies are written, so a re-ordered tour keeps its text; the hand-off Directions are rewritten by the 882 guard.
- Origin / destination geocodes use the free Nominatim host (`geocode_stops.geocode`), not a paid call.
