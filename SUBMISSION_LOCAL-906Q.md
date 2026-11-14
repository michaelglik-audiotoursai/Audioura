# LOCAL-906Q — route-corridor scope, hollow refill, first leg from the origin, copy (offline, $0)

Branch `LOCAL-906Q-route-scope-copy`, base 12790d52 (verified ancestor). No live run, no paid call, no budget spent.

1. **Scope** (`route_scope_906q.py`, `_validate_stops_within_scope`, Phase 3A scope text): on a 909 A-to-B or rc896 route the
   scope is the corridor (origin, destination, region, padded A-to-B box). A stop inside the box, or whose address names the
   region/origin/destination, is in scope; the judge is asked about the corridor, not the destination. On a route tour scope memory
   is neither consulted nor written (log `[LOCAL-906Q] route-corridor rejection ... not recorded`).
2. **Hollow refill** (`generate_tour_text.py`, Phase 3A): when 0 < survivors < N, hollow candidates are appended in original
   order (deduped) up to N; logs `[LOCAL-906Q] hollow refill: k`. LEAD-910's all-hollow path is unchanged (its test passes).
3. **First leg** (`route_order_909.first_leg_from_origin`, run from `finalize_text`): Stop 1's Orientation/Directions sentences that
   start "From <destination>" or have a dangling "for," are dropped; Orientation names the origin as the start; an emptied
   Directions gets the origin leg.
4. **Copy** (`route_copy_906q.py`, hooked after 906P in `leftovers_906f`): restaurant plug (unless the stop is that venue),
   day-trip/operator copy, resort promo, no-fact filler, two-commune conflict (evidence decides), dangling "for,". A stop is never emptied.

Tests: `tests/test_local906q_route_scope_copy.py` (19). Usual set + new: 2628 passed, 4 skipped (`test_local88_tour_pollution.py` deselected).
Unverified: the corridor box uses the free Nominatim geocoder at run time (offline tests inject a box); no live proof.
