# SUBMISSION LOCAL-905 — pool reuse runs the same guards as a fresh stop (offline, $0)

Branch `LOCAL-905-pool-reuse-guards` from subscribed ca403e62 (`git merge-base --is-ancestor ca403e62 HEAD` = 0).
No live run, no paid call, no DB write, no pool purge.

## What changed
1. **Reuse guards** — `pool_guards_905.py`, called in `stop_pool_orchestrator.maybe_generate_with_pool` right after the
   LOCAL-788 re-validation (non-contained tours; the body check also covers contained ones). A pooled row is rejected
   (skip-only, pool unchanged) for an empty/failed body, a pin outside the route box + 10 km, a pin farther than the 900B
   radius (BUILDING/CORRIDOR/DISTRICT 15 km, CITY 25 km, unknown precision 100 km) from the scope centre, or — on a
   DISTRICT/BUILDING scope with a verified place reference — farther than 15 km from it.
   Log: `[LOCAL-905] pool row '<title>' rejected: <reason>`. Scope context comes from `area_resolver.resolve_area`
   (best effort; `{}` on failure, so a lookup failure never empties a tour).
2. **Small tours skip the pool** — total_stops <= 2: `[LOCAL-905] pool skipped: <= 2 stops`. Writes unchanged.
3. **No empty stop is delivered** — `delivery_bodies_905.ensure_bodies`, run in `_apply_delivery_hours_guard` (every path,
   pool included): empty stop -> own evidence -> one clean same-site neighbour sentence -> honest D760 body; if none can
   be built the stop is removed (previous stop's hand-off dropped, closing paragraph kept, stops renumbered).
   "That's N stops in all." is set to the delivered `Stop N:` count.
4. **Pool tour pin** — returns `first_stop_pin(text)` (the first delivered stop's `Coordinates:`) instead of `(None, None)`.
5. **Required places survive**
   - `required_places_902._matches` has a core-token mode (structure words such as statue/mountain ignored). It is used
     only for a name with no strict match and only on a stop no other name claimed, so "<Mountain>" cannot be satisfied by
     "<Statue> Statue".
   - `identity_dedup`: two `_required_902` stops are never merged (location/QID and identity dedupe); a required stop that
     collides with an ordinary one wins.
   - The `poi_list[:_effective_cap]` trim (generate_tour_text) keeps required stops, and a re-check of the required
     places runs before narration (after the pre-writing scope check; the scope check already exempts `user_explicit`).
   - Test of the wave-50 shape: selection [<Statue> Statue], required [<Mountain>, <Statue>] -> delivered
     <Mountain>, <Statue> Statue.
6. **`local905_pool_audit.py`** — read-only (SELECT only, read-only session): per venue key, the rows the item 1 guards
   would reject (+ pin outliers against the key's median; `--geo` adds the scope test). Not run against any DB here.

## Which step removed the statue (honest status)
I could not reproduce the removal without a live run. What the code shows: the wave-50 delivery came from the POOL path
(`reused=1 new=1`), whose nested generation is called with `total_stops = N-K = 1`. 902's `ensure_required_stops` ran with
`max_stops=max(total_stops, len(required))=2`, but the later hard cap `poi_list[:_effective_cap]` used `total_stops=1` and
cut the second (required) stop. The dedupe path was a second candidate (two `user_explicit` stops of the same site collapse
by QID/identity). Both are fixed above; with item 2 the nested N-K=1 call no longer happens for a 2-stop request. This is
unproven live — LEAD's field run should confirm.

## Tests
`tests/test_local905_pool_reuse_guards.py` (21): far/empty pooled rows rejected and logged, route box, place reference,
orchestrator with a fake pool (bad rows not counted toward K), 2-stop skip, empty stop refilled / removed + count fixed,
pool tour pin, required matching/survival/dedupe, audit.
Regression: `tests/test_local89[6-9]*, test_local90*, test_local894*, test_local87*, test_local88[0-9]*, test_local89[0-3]*`
(deselect `test_local88_tour_pollution.py`): 1042 passed, 4 skipped. `-k "local590 or pool or local788 or local811"`:
138 passed, 18 skipped. No failures (the two known pre-existing ones did not appear).

## Not verified
Real `resolve_area` output on the cloud (mocked here); the live pool contents (audit script is for LEAD to run).
