# SUBMISSION LOCAL-906E — province box sanity (offline only, $0)

Base 39c5b19a (906D). Branch `LOCAL-906E-province-box-sanity`. No live run, no paid call; every lookup mocked.

## Cause (from the logged run)
906D used the first administrative geocoder row as the "province box". After a 2025 reform a city ward carries the old
province's name, so the box was ~12 x 11 km. Pre-906D (no bbox) LEAD-905 accepted the right reference (2.1 km from the
site); with the ward box it was refused as "outside the scope", both pins went to the ward centre (25 km off), and the
address adopted a street from the reverse geocode of that centre.

## Changes
1. `pin_fallback_906d.province_box` sanity check: province/state level only (`admin_level` 4, or `addresstype`
   state/province; city/ward/suburb/municipality rejected), area >= 1,000 km2, must contain the area resolver's coarse
   centre when one exists. A failed geocoder row falls through to the Wikidata entity (P625 + P2046; a dissolved province
   keeps both; every hit is tried, biggest first) as a square, same checks. Else no box (pre-906D behaviour) and
   `[LOCAL-906E] province box rejected: <why>`. `generate_tour_text` passes the coarse centre.
2. Fallback only: the box is padded by 20 km (`pad_box`) before it is used for the snap and the last resort, and
   `snap_poi_coordinates(scope_bbox_is_fallback=True)` makes a reference within the coarse-centre radius (the
   LEAD-905 / 902 rule) in scope whatever the box says. Authority (Wikidata/landmark) rules unchanged.
3. `last_resort_pins`: moves only when the pin is outside the padded box AND the move does not go farther from the stop's
   own reference; the province-centre move happens only when no stop has an accepted reference.
4. `address_follows_pin`: for an approximate pin (province centre, or moved onto another stop's reference) nothing is
   adopted from the reverse geocode; the address becomes "<Stop name>, <Province>, <Country>".
5. Stop 2 content:
   - `leftovers_906c.repair_pronoun_opener` (in `final_pass` and `content_pass`): a first body sentence opening with
     Its/It/They/Their/This/These becomes "The <Title>'s ..." / "The <Title> ...". A "This <noun>" whose noun is not in the
     title is left alone.
   - **Why the 49 m / 7 m sentence vanished** (log): D533 `strip_repeated_facts` removed the Stop 2 telling because
     Stop 1 (the mountain) told it first ("this reclining Buddha is the longest …", kp/meters-high). Then the 883/891
     grounding gate dropped Stop 1's copy as off-topic ("supported only by context … names the stop only in passing"), and
     Stop 2's own later copies were dropped CONTRADICTED/unsupported. Told nowhere. Not a bad rule dropping a grounded
     fact, but the dedupe keeping the copy at the wrong stop. Fix: `strip_repeated_facts` keeps a cross-stop fact at the
     stop whose title the sentence names (>= half of the title's words) when the first telling names the later stop's
     title and not its own; the first telling is removed instead (`owner_swapped_906e`).
   - Not fixed, reported: the later 883 CONTRADICTED verdicts on the 49 m statements (evidence also says built 1962 vs
     1966, and "longest in SE Asia" vs "one of the largest"); that is the grounding gate's judgement call, not a rule bug.

## Tests
`tests/test_local906e_province_box_sanity.py` (27): ward box rejected + logged; admin_level 6 / suburb / municipality
rejected; coarse-centre check; dissolved-province Wikidata fallback; tiny/far Wikidata rejected; replay of the logged
shape (ward-sized box slipping through still accepts the 2.1 km reference, no centre move); padded box; sane province box
still catches a far pin; no centre move with an accepted reference elsewhere / farther from own reference; address not a
street for approximate pins; pronoun-opener repair; size fact stays at the stop it names.

Required set (`test_local906* 89[6-9]* 90* 894* 87* 88[0-9]* 89[0-3]* lead905* 791*`, deselect local88_tour_pollution):
1612 passed, 4 skipped. `-k "ground or conclusion or pin or itinerary or snap or pool or d533 or derepetition or local660"`:
720 passed; 3 failed, all on the known pre-existing list (`test_local378…case_sensitive` x2, `test_local666…no_pin_and_no_archive_is_v1`).
Run with `env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`.

Unproven live (no budget used): the real geocoder row for the real province was not queried.
