# SUBMISSION — LOCAL-906D (pin fallback inside the province + same event twice)

Branch `LOCAL-906D-pin-fallback-same-fact`, from `b99db205` (ancestor check exits 0). Offline, $0: no live run, no paid call, every lookup mocked, run as `env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`. Fixtures are generic (D769); the DO_NOT_COMMIT log was not copied or committed.

## What changed

| Item | Where |
|---|---|
| 1 place reference retry | `area_resolver.first_named_place_reference` calls `pin_fallback_906d.place_reference_retry` after the 901 miss. Wikidata `wbsearchentities` in the country's language (P17→P37, wider language map in `pin_fallback_906d.local_language`; `_detect_language` untouched) then English, matching labels AND aliases, folded and diacritic-insensitive. Then the geocoder with `<core name>, <province>` (and `, <country>`), `natural=peak` preferred for mountain/peak. A hit is accepted only inside the province box. Logs `[LOCAL-906D] place reference '<name>' -> <lat,lng> via <path>`. |
| 2 province box | `pin_fallback_906d.province_box`: the geocoder's ADMINISTRATIVE row (`featuretype=state`; a same-named railway station is skipped), fallback Wikidata P625 + P2046 area as a square. `generate_tour_text` (791C block) fetches it only when the city-level bbox was not obtained and uses it as the snap `bbox`; `flag_far_pins` logs `[LOCAL-906D] stop=N model pin outside <province> (<km> km)`. The snap `scope_center` stays None on purpose: a province centre would let 791C's 15 km sanity refuse a real site 26 km from it. |
| 3 facility = approximate reference | `pin_snap.snap_pin(province_box=, stop_type=)`: for a natural-feature/area stop, a reference named "<core name> + facility word" inside the box is accepted, flagged `coordinates_approximate`, logs `[LOCAL-906D] approximate reference '<ref>' accepted for '<stop>' (facility of the same place)`. Every other name mismatch (City Hall) still hits the 791E refusal. The 902 acceptance also applies to a model pin outside the box on tours of any size. |
| 4 last resort | `last_resort_pins` after the snap: a far unverified pin moves to its own approximate facility reference, else the best in-province reference of another stop (verified snap first), else the province centre (`_pin_province_centre_906d`, approximate). The tour pin is recomputed from stop 1 (`single_place_903.tour_pin`). |
| 5 address follows the pin | `address_follows_pin`: for a moved / approximate-facility stop, parts other than the stop name, province and country are dropped unless the reverse geocode of the new pin confirms them: "<Mountain>, <Province>, <Country>". Runs after 902's `verify_addresses`. |
| 6 same event | `route_content_896.same_event` (used by `same_fact`): same 4-digit year AND same person (capitalised multi-token name, or Master/Monk/King/… `<Name>`) AND the stop's title token in both. 906B's `drop_within_stop_duplicates` keeps the more specific sentence; 904's refill `ok()` already calls `same_fact`, so the refill never appends it. |

New module: `pin_fallback_906d.py`. Edited: `area_resolver.py`, `pin_snap.py`, `generate_tour_text.py`, `route_content_896.py`.

## Tests
- New `tests/test_local906d_pin_fallback_same_fact.py`: 29 passed (retry miss→local-language/alias hit, wrong-province hit refused, geocoder retry query + peak type, province box admin vs station and Wikidata fallback, far-pin log, facility vs City Hall table, full pin-chain replay: facility accepted, both pins inside, tour pin follows, address dropped; no-reference → province centre flagged; verified pins untouched; same-event pair caught, different events not caught, duplicate pass keeps one).
- Required suites (`test_local906*`, `89[6-9]`, `90*`, `894*`, `87*`, `88[0-9]*`, `89[0-3]*`, `test_lead905*`, `791*`, excluding `test_local88_tour_pollution.py`): 1558 passed, 4 skipped, 0 failed.
- `-k "ground or conclusion or pin or itinerary or snap or pool"` (same deselect): 689 passed, 3 failed — all pre-existing: `test_local378…case_sensitive_surname`, `test_local378…mentions_person_case_sensitive`, `test_local666…no_pin_and_no_archive_is_v1`.

## Not proven / caveats (handing to LEAD)
- Not run live (budget $0). The wiring in `generate_tour_text` (province box, last resort, address) is exercised only through the module functions and `pin_snap`, not an end-to-end generation; syntax-checked only.
- The facility rule needs the 791E name check to have refused first; in my replay that shape is title "<X> Mountain" vs "<X> Cable Car Station". Where the real names already pass the 791E check, the pin is accepted as before.
- Province box is only used when no city-level bbox exists, so ordinary city tours are unaffected. In the default (non-injected) path, retry does network lookups only after a 901 miss.
- `_pin_far_906d`/`_pin_moved_906d` poi flags are new private keys.
