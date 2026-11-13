# SUBMISSION LOCAL-906M — anchor evidence for generic stop titles, promo/review copy, closing variant, destination pin

Branch `LOCAL-906M-anchor-evidence`, based on subscribed 70c596ea (`git merge-base --is-ancestor 70c596ea HEAD` = 0).
Budget: $0. No live run, no paid call (`env -u OPENAI_API_KEY -u SERPER_API_KEY THIN_STOP_SEARCH=0`).

## Finding: which search / pages fed "The cable car ascent" (LEAD 906L log, read only, not committed)
- Stop 5's thin-stop escalation (LOCAL-873) searched the bare title + city (4 queries). With no place in the title the
  engine returned another country's cable-car pages (an Aiguille-du-Midi page, a nationwide cable-car list, a Facebook
  group post). Snippets of two of them became "sourced facts" and the 880/881 signature stories ("world record for the
  highest vertical climb").
- The D556 lore path (`fetch_stop_knowledge(..., focus='place')`) searched `"<bare title>" history famous people` with no
  location at all (the log shows Half Dome pages for that stop).
- The 873 geo-gate only drops a page that names a famous same-name place elsewhere AND never names the city; it did not
  reject pages that simply never mention the tour's place.

## Changes
1. `anchor_evidence_906m.py` (new, pure): `is_generic_title`, `anchors_for` (request destination -> area -> previous /
   next NAMED stop), `anchored_queries`, `mentions` (folded: case, diacritics, trailing kind word, spacing),
   `reject_evidence` (logs `[LOCAL-906M] Stop N evidence rejected: no '<anchor>' in <url>`).
2. `thin_stop_search.escalate_thin_stop(anchors=, stop_num=)`: every query carries the anchor; a fetched page (and a
   snippet fallback) that does not name the anchor is rejected for that stop. `stop_knowledge_fallback`
   (`fetch_stop_knowledge` / `_web_evidence`, `anchors=`): query carries the anchor, results without it dropped, the model
   is told "<title>, <anchor>". `generate_tour_text`: `_anchors906m()` feeds both call sites; a stop that names itself
   passes no anchor and is searched exactly as before.
3. Delivery: `drop_other_site_landmarks` (run inside `leftovers_906f.run_pass`, so every delivery path) applies 906K
   `other_landmark` to EVERY body sentence of a generic-title stop. "Known" = all titles + other stops + this stop's own
   keyed lines + this stop's evidence; never the stop's own body.
4. Promo / review copy added to `leftovers_906f._PROMO` ("Many tour operators in X (heavily) advertise…", "You can join
   (private) (day) tours…", "Many tours combine…", "flexible options available for … tours", "within walking distance
   from some hotels", "If you stay nearby, some hotel rooms offer…", "Getting to X was an adventure, and it was worth
   it", "We/I loved|enjoyed…", "I would recommend…"). The 906K refill bar uses `is_promo`, so refills inherit it.
5. Closing: `route_leftovers_906._FILLER_CLOSING` generalized: "Together|All in all|Taken together|In all|Overall, these|the
   stops …" and "These stops (together) highlight|showcase|capture|…".
6. Pin: `route_order_909.set_dest_reference / destination_reference / dest_reference`. `_pick_reference` takes the destination
   place reference (901 area ref when it names the destination, else the 906D retry via
   `area_resolver.first_named_place_reference`) before route refs / wikidata / pool and long before the "destination
   geocode" last resort; `endpoints_pts` uses it as the route's far end. Wired in `generate_tour_text` just before
   `endpoints_pts`. Log: `[LOCAL-906M] destination '<X>' place reference lat,lng`.
   Which source won in the LEAD log: `[LOCAL-909] Stop 3 delivered without coordinates -> restored from destination
   geocode 10.9286,108.0885` (the `endpoints_pts` street geocode), because the snap row had no reference
   ("left unsnapped (no in-scope reference)") and the 901/906D reference had not been carried to the route phase.
7. Directions: `trim_directions` (also in `run_pass`) drops sentences of Stop N's Directions naming Stop N+2 or later
   (not when the name is part of Stop N's or N+1's own title; a block keeps at least one sentence).

## Tests
- New `tests/test_local906m_anchor_evidence.py` (42 tests): generic-title / anchor rules; anchored queries and the
  rejected other-mountain page (logged) vs accepted anchored page; knowledge-fallback gate; generic body drops other-site
  landmarks (real fact kept, evidence-backed landmark kept, named stop untouched); each promo/review pattern dropped with
  a real fact kept; closing variants; destination pin takes the place reference (and the geocode stays the last resort);
  Directions naming a later stop dropped.
- Required set (`tests/test_lead906l* 909* 906* 907* 89[6-9]* 90* 894* 87* 88[0-9]* 89[0-3]* lead905* 791*`, minus
  `test_local88_tour_pollution`): 1787 passed, 1 failed. The failure `test_local902_single_place_pin::
  test_lead905_far_model_pin_snaps_to_in_scope_reference` fails identically on the untouched base in the combined run
  (order-dependent; passes alone with and without my change).
- `-k "ground or conclusion or pin or itinerary or snap or pool or route or derepetition or thin"`: 11 failed on the base
  and the same 11 after (identical FAILED lists; the known-list files); 1063 passed after vs 1061 before.

## Not proven / notes
- No live run: the query anchoring and page gate are proven with injected serp/fetch only. The 906D destination retry is
  only exercised through an injected resolver offline.
- Directions rule is applied literally (N+2 or later). In the sampled text, Stop 1's Directions name Stop 2 (the next
  stop), which the rule keeps; the sentence is left to the origin-leg logic.
- A closing that names stops is also dropped when it matches the template ("Together, these stops …"); the "That's N
  stops in all." line stays.
