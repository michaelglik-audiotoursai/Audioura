# SUBMISSION LOCAL-906O — anchor scope, destination reference, other-city stop, practical copy, closing, measure ($0, offline)

Branch `LOCAL-906O-anchor-scope-dest-ref`, base 3da68042 (LOCAL-906N-cloud-551-nits). No live run, no paid call.

## Root causes and fixes
1. **Anchor too narrow** — `anchor_evidence_906m.anchors_for` used the neighbour's WHOLE title (`_core`), and the generate
   wrapper `_anchors906m` passed only `route().destination` (empty on a described route, never the region).
   Now anchors are place names only: `name_cores()` (proper-name runs: "Phan Thiet and the Ca Ty River" -> "Phan Thiet",
   "Ca Ty River"), destination (r909 / rc896 / `_J._ROUTE_INFO`), province + country from the region. A topic-like title
   (`is_topic_like`: generic, no landmark noun — a crop, a dish) is anchored by province, country, then destination and
   neighbours; a page naming ANY anchor is accepted (existing `mentions`).
2. **Destination reference never fired** — it did run (`_res906m`), but called `first_named_place_reference` without
   `city_qid` / country, so 906D's local-language Wikidata step never ran ("retry ... found nothing"). The reference also
   arrived AFTER `endpoints_pts` had cached the geocoded far end. Fixes: `city_qid`, country and a province fallback from
   the request region are passed; `set_dest_reference` refreshes the cached endpoints; every outcome logs
   `[LOCAL-906O] destination '<X>' -> lat,lng via <source>` (or `-> no place reference`). Pin of the destination stop and the
   far end already prefer `dest_ref` (906M); unchanged.
3. **Other-city stop / order** — new `scope_906o.py`: `claims_other_place`, `reject_stops` (selection: own text says another
   city AND pin outside the padded box/none -> rejected or `replace_fn`; user stops/destination protected; wired before
   `finalize_route_pins`), `drop_other_city_sentences` (delivery: "actually/in fact located in <X>" with no tour-region name
   is never delivered). `route_order_909.dest_substops` + `order_stops(..., sub_idx)`: a stop on/at the destination goes after
   the ordinary stops, before the destination, in both `order_poi_list` and `reorder_on_pins`.
4. **Practical copy** — `scope_906o.is_practical`: "Tickets to <X> cost ...", opening-hours with times, queue/waiting-period
   warnings, "as part of a half-day tour". Dropped on a route/drive (`run_pass`, from `leftovers_906f.run_pass`).
5. **Closing on the route path** — `drop_template_closing` lived only in `route_leftovers_906.content_pass`, whose
   `in_scope` is `rc.active() or <= 2 stops`; a plain "A to B" request (r909) is neither, so it never ran. It is now also
   called from `scope_906o.run_pass` (route / driving / rc-active), reached through `leftovers_906f.run_pass` ←
   `delivery_bodies_905.ensure_bodies` on every path.
6. **Measure conflict** — `resolve_measure_conflicts` skipped a stop whose own evidence has no article value for the
   dimension. It now falls back to the other stops' ARTICLE evidence about the same object (>= 2 shared object words,
   one distinct value) and logs `[LOCAL-906O]`.

## Tests
`tests/test_local906o_scope.py` (22): anchors (province/country, no whole title, dragon-fruit page accepted), destination chain
mocked + logged + cached-endpoint refresh + pin, other-city sentence/stop, sub-stop order, practical sentences (+negatives),
closing on r909 path (not rc-active, 3 stops), measure fallback.
Usual set (command in the task, `tests/test_local88_tour_pollution.py` deselected): **2479 passed, 4 skipped, 0 failed.**

## Not verified / limits (no live run)
- The real Wikidata local-language hit for the destination (10.8167, 107.8833 in the 552 job) is not re-proved offline; the
  chain is mocked. The fix is that the inputs the 906D retry needs are now passed.
- `reject_stops` at selection only sees text the stop dict carries (name/address/description/narration keys); the delivery
  sentence drop is the guarantee. A pool replacement hook (`replace_fn`) exists but is not wired to a live pool.
- The other 906 `content_pass` guards still do not run on a plain r909 A-to-B tour with > 2 stops (not changed; only the
  closing was wired).
