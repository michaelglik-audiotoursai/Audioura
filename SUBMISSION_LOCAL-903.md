# SUBMISSION LOCAL-903 — single-place pin agreement (offline, $0)

Branch `LOCAL-903-single-place-pin-agree`, base 239ccd31 (verified ancestor). No live run, no paid call, no DB write.

## Changes
1. **Geocoder hit validation** — `area_resolver.geocoder_hit_verdict / pick_geocoder_hit`; `first_named_place_reference`'s
   geocoder branch now takes up to 5 Nominatim hits (`geocode_stops.geocode_candidates`), rejects settlement /
   administrative / boundary hits for a name with a feature word (small generic table: mountain/peak/hill, pagoda/temple,
   lake/waterfall/…, default = any non-administrative feature), logs
   `[LOCAL-903] geocoder hit '<display_name>' rejected: <class>/<type>`, prefers the top hit whose display name holds the
   name's core token (diacritics folded). An injected point-returning `geocode_fn` keeps the old contract.
2. **Snapped point supersedes the reference** — `single_place_903.repin_to_snapped_place`: the stop titled as the first named
   place, snapped to a verified point (serper/wikidata/nominatim/landmark), re-pins any other `coordinates_approximate`
   stop sitting on the old reference. Logs `[LOCAL-903] stop=N re-pinned to the snapped place '<name>' (was the place reference, <km> km off)`.
3. **Single-place agreement** — `agree_single_place`: ≤ 2 stops, DISTRICT/BUILDING scope, > 15 km apart → the unverified
   stop moves to the verified one, flagged approximate; Directions then normalise to "Walk on to <next>." (898 rule, checked in a test).
4. **Tour pin** — the orchestrator takes it from the generator's return value `first_poi_coordinates`, which
   `generate_tour_text.py` extracted at "Extracted first POI coordinates" BEFORE the 791C snap. It is now re-read from the first
   stop's final pin right after the snap/re-pin/agreement (`single_place_903.tour_pin`, logged `[LOCAL-903] tour pin A -> B`).
5. **Address check** — `pin_snap.address_agrees` keeps the address when any district-level token (after Huyện/District/Quận/
   Thị xã/Xã/Thị trấn/Phường, folded) is in the reverse geocode; province mismatch not decisive.

Hook: `generate_tour_text.py`, right after `_snap791c(...)` and before `verify_addresses`.

## Tests
`tests/test_local903_single_place_pin_agree.py` (12): city rejected / peak accepted, core-token preference, validated place
reference, sibling re-pin, agreement + "Walk on to", tour pin, address keep/drop, generic replay (both pins and tour pin < 3 km from the snap point).

Required sets: 1012 passed, 4 skipped. `-k "local791 or local802 or snap or pin"`: 366 passed, 1 failed = pre-existing
`test_local666…no_pin_and_no_archive_is_v1`. No new failures.

## Not verified
Not run live: real Nominatim class/type values for the 552 mountain (table is from OSM conventions); whether the live
snap row's `source` string for serper begins with "serper" (taken from the proof log `(serper)`).
