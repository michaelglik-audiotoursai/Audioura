# SUBMISSION LOCAL-906U (offline, $0)

Branch `LOCAL-906U-geocode-orientation-headlines`, from a5301367. No live run, no paid call. Tests run with
`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`. Fixtures use generic names (D769). The proof log was not copied or committed.

## Result
- New tests: `tests/test_local906u_geocode_orientation_headlines.py` (45 pass).
- The task's regression set (3038 passed, 4 skipped, `test_local88_tour_pollution.py` deselected): no failures.
- Other geocoder-related test files: 3 failures (`test_local320_nondining_regression::test_dining_does_call_nominatim`, 2 in
  `test_local351_us_address_parsing::TestNiceUnchanged`). They fail identically on a5301367.
- Replaying the three proof texts through `final_906u.run_pass` with no evidence removes items 2, 3, 5, 6, 8, 9, 10, 11 and 7
  (see "Not proven live").

## Findings and fixes
1. **Geocoder 429s.** `nominatim_throttle_906u.py` is one process-wide gate: at most 1 request per second (floor, not configurable
   below 1.0), `Retry-After` honoured and capped at 30 s, 2 retries (3 requests), per-job cache including empty answers, and a
   failure ledger. An errored lookup is cached for 60 s as FAILED, separately from "no result". `geocode_stops` (search, detailed,
   candidates, reverse, land check), `area_resolver._nominatim_bbox` and `pin_fallback_906d._default_search_rows` use it;
   `stop_existence_gate._nominatim_request` also waits on the shared slot and honours `Retry-After`. The cache is reset at the start of
   each `generate_tour_text`. `tests/conftest.py` resets it per test and removes the sleeps.
   - **Source of 10.935967, 108.146020:** `pin_fallback_906d.last_resort_pins`. Stop 2's model pin was outside the province box,
     all its lookups had returned 429, so it was "moved to stop=1's in-province reference 10.9360,108.1460 (approximate)". Stop 1's
     reference (Poshanu) sits 4.8 km from where the lighthouse pin ended up; the real site is about 30 km away.
   - **Fix:** if the stop's own lookups errored (`lookup_failed_for(name)`), it gets `_no_coordinate` + `coordinates_approximate`, is not
     moved onto another stop, and `[LOCAL-906U] stop=N ... does not inherit another stop's coordinates` is logged. A stop whose lookups
     simply found nothing follows the old rule.
2. **A-to-B Orientation** (`final_906u.fix_ab_orientation`): drops "Leave <Destination> ..." directions, the route steps that follow
   them, the "Each stop on this journey ..." template and a second route sentence; keeps exactly one "The route starts at <Origin>; ..."
   (synthesised when the model wrote none). Origin and destination come from the tour header.
3. **Headlines / operator copy** (`headline_reason`): Title-Case (>= 60% of non-connector words capitalised) with "&", or ending in
   Tour/Tours/Trip/Package, or starting Discover/Explore/Book; plus "recommended routes", "travel tips", "plan your visit".
4. **Refill rejected for one stop, delivered on another.** Path: `leftovers_906f.refill_thin_stops` (906I) calls
   `refill_quality_906k.reject_logged(..., own_evidence=True)`, and `own_evidence` skips the `about_stop` check. The sentence sat in
   Stop 6's evidence blob (a search snippet), so the 906K bar never saw it as off-topic (Stop 8's path used `own_evidence=False`).
   - **Fix:** `refill_reject` rejects, on every path and even with `own_evidence`, a sentence that names a landform (beach, island, lake,
     bay, desert, dune, lagoon, waterfall, canyon) that the stop's title and type do not name and that does not mention the stop.
     `final_906u.bar_pass` re-applies the bar to any body sentence that is verbatim evidence (added after generation).
   - I first tried removing the `own_evidence` exemption for snippets. `test_thin_stop_is_refilled_from_the_evidence` showed it drops
     legitimate own-evidence sentences, so it stays.
5. **One disclosure per stop** (`one_disclosure`), including a second one on its own paragraph after the last stop's body.
6. **"Among its ..." as the first sentence** is rewritten to "Among <Title>'s ..." (`Title'` after an s).
7. **Two distances** from the same reference city in one stop: the encyclopedia's (an article sentence), else the first, is kept; the
   other sentence is dropped and logged. On the proof text there was no evidence, so the first (31 km) was kept.
8. **Sensory colour / material** (`colour_reason`): a sensory sentence naming a colour or material that the stop's evidence does not
   carry or contradicts is dropped. "From the vehicle, ..." becomes "From here, ..." on a stop whose arriving Directions say Walk.
   Side effect: with an empty evidence entry every sensory colour sentence on that stop is dropped (the Poshanu "brick towers ... ocher
   glow" Orientation sentence went too).
9. **"lies / stands / is located from <X>"** with no measure is dropped as a fragment.
10. **"<Name>, the tallest <X> in <Country>"** is hedged to "one of the tallest <X>s in <Country>" unless one evidence sentence states it
    unhedged. Cause of the miss: 906T's record path needs rank >= 3 or a contradicting evidence sentence, and `check_claim`'s token
    overlap fails for a long sentence.
11. **Hours / season copy** ("is open all year round", "opens at 8 am", "closed on Mondays", "opening hours") is dropped.
12. **Escalated fact lost on Stop 5** (log 2468 -> 3081/3129/3132). The only drop is `thin_stop_delivery.narrate_stop_body`:
    `[LOCAL-873C] rejected (not traceable): The cable car climbs at an angle of 37 degrees.` The traceability rule needs 3 shared content
    tokens (>= 4 letters). A one-sentence fact has at most 4 such tokens, so a reworded narration of it fails. 855B, 860, 890 and 897
    did not drop it (897 dropped a different sentence, "The ascent lasts no less than 28 minutes ...").
    - **Fix:** for a fact with <= 4 content tokens, the narration passes with 2 shared tokens when it states a number and every number it
      states is the fact's own. A longer fact keeps the 3-token rule.
    - When no narrated sentence is traceable, `[LOCAL-906U] ... N escalated sourced fact(s) not narrated: no candidate sentence was
      traceable to them (first fact: "...")` is logged.
    - I cannot see the fact's text in the log (only "1 sourced fact(s)"), so I cannot prove the 37-degree sentence would now pass.

## Wiring
`delivery_bodies_905.ensure_bodies` calls `final_906u.last_word` after the 906S last word. It runs the pass, refills or discloses a stop
the pass emptied (906S `factless_stops`), then runs the pass once more.

## Not proven live
Offline only. The replay of the three proof texts with empty evidence logged the expected drops, but nothing was checked against a
real run with evidence, a real 429 or the live geocoder. Item 12's fix depends on the unseen fact text. LEAD should re-run the
"<Origin> to <Mountain>" drive and 551 with the geocoder rate unchanged to confirm the 429 count and the pins.

## Files
New: `nominatim_throttle_906u.py`, `final_906u.py`, `tests/test_local906u_geocode_orientation_headlines.py`.
Edited: `geocode_stops.py`, `area_resolver.py`, `stop_existence_gate.py`, `pin_fallback_906d.py`, `refill_quality_906k.py`,
`thin_stop_delivery.py`, `delivery_bodies_905.py`, `generate_tour_text.py` (job reset), `tests/conftest.py`.
