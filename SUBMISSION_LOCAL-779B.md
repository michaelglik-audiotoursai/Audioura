# SUBMISSION — LOCAL-779B (bounce of LOCAL-779): restaurant candidates from maps/places + refill + cuisine match

**Branch:** `LOCAL-779B-restaurant-places`
**Base:** `LOCAL-779-business-poi-verification` @ `f9ca9db0` (verified ancestor of HEAD)

## Problem (LEAD bounce of LOCAL-779)
Gyms/coffee/Freedom-Trail controls were good, but the restaurant case was never
live-tested. `"middle eastern restaurants near me, west Roxbury, MA"` still
`PHASE 3C rejected all stops`: the restaurant category took its candidates **only
from the LLM** (which put them in Newton/Boston, outside scope), and when PHASE 3C
emptied the list **nothing refilled from map listings**. The business path
(LOCAL-779 build step 3) does that refill, but a restaurant `poi_type` classifies
as `dining` and never reached it. PHASE 4 even "verified" a Chinese *Dumpling House*
as Middle Eastern.

## What was built

A restaurant (and any BUSINESS) `poi_type` now draws candidates from the **same
maps/places search the business path uses**, refills from map listings when
PHASE 3C / the existence gate leaves the list short, enforces cuisine/qualifier
match, and — when the area genuinely has no verifiable match — refuses cleanly
with a widen-the-area suggestion instead of inventing stops.

### `stop_existence_gate.py` (+446)
- `dining_replenish_candidates(poi_type, scope, needed, exclude, device_coords, cuisine)`
  — the dining analogue of `business_replenish_candidates`: asks the MAP for
  `"<cuisine> restaurants in <scope>"`, keeps dining listings **inside the scope**
  whose **cuisine matches**, ranked by distance to the device (`near me`) or the
  scope centre. Each candidate is verified-by-construction with a real address +
  coordinates.
- `cuisine_matches` / `cuisine_conflict` — cuisine/qualifier matching using the
  OSM `cuisine=` tag when present, otherwise the name/description. *Dumpling House*
  (chinese) is rejected for Middle Eastern; *Sofra* (Middle-Eastern bakery café) is
  accepted; the **"Mamma Maria is Italian" guard** is kept. `cuisine_conflict`
  drops only on a **positive different-cuisine signal** (sparse OSM tags → absence
  is UNKNOWN, kept — D162).
- `verify_listing_cuisine(name, scope, cuisine)` → `True/False/None` — vets an
  LLM survivor's cuisine against its own map listing.
- **`verify_listing_in_scope(name, scope)` → `True/False/None`** (added this
  session) — a pure **existence** check: does the map carry a listing by that name
  inside the scope? A successful-but-empty response is `False` (the place is not
  there); a network failure is `None` (UNKNOWN). This is what stops a fabricated
  restaurant with a plausible-looking address from surviving.
- `_extract_cuisine_qualifier` / `_cuisine_from_request` — recover the cuisine
  the live LLM intent often drops (it returns a bare `"restaurants"` for a
  `"middle eastern restaurants near me, …"` request).

### `generate_tour_text.py` (+317)
Three wiring points, all guarded so the museum/landmark paths are byte-for-byte
unchanged:
1. **PHASE 3C CUISINE-VERIFY + MAPS-FIRST top-up** (before Part C). For a
   cuisine-bearing dining request, a non-anchor / non-maps-verified LLM survivor
   is kept **only if its listing verifies inside the scope** — dropped when
   `verify_listing_in_scope` is `False` (invented / not in scope) **or**
   `verify_listing_cuisine` is `False` (wrong cuisine); a `None` from either is
   UNKNOWN and kept (D162). Removed slots refill from
   `dining_replenish_candidates` (`business_replenish_candidates` for a business
   `poi_type`). Part C (the LLM refill that re-introduced wrong-town names) is
   **skipped** for business/dining so the LLM is only ever an extra source.
2. **MAPS-FIRST refill when the list is empty** (after the existence gate) — the
   LOCAL-290 top-up only ran when `len(poi_list) > 0`; this refills from the map
   even from zero.
3. **DINING replenishment** in the LOCAL-290 block, parallel to the LOCAL-779
   business block, so a `dining` `poi_type` reaches a maps refill.
Maps-sourced stops are tagged `_maps_verified` and exempted from the
Wikipedia-shaped existence re-check (they are already map-verified in scope).

### `actionable_failure.py` (+63)
- New error code `no_matching_places_in_area` and `_widen_area_suggestion(...)`:
  a ready-to-fire request that **widens** the area (curated adjacency, e.g. West
  Roxbury → "West Roxbury and Roslindale") rather than retrying the same empty
  search.

## Tests (recorded JSON only, no live web)
`tests/test_local779b_restaurant_places.py` (471 lines) — **52 passed**:
- `dining_replenish_candidates` refills in-scope West Roxbury Middle-Eastern places;
  the Newton LLM candidates are excluded; a Chinese *Dumpling House* is rejected for
  cuisine; *Sofra* kept.
- A zero-match area returns `[]` → the caller refuses cleanly.
- `_extract_cuisine_qualifier` / `_cuisine_from_request`, `cuisine_matches`,
  `cuisine_conflict`, `verify_listing_cuisine`, and the new
  `verify_listing_in_scope` (6 cases: real→True, invented→False, empty→False,
  out-of-scope→False, network-fail→None, no-args→None).
- Routing: a restaurant `poi_type` classifies as `dining` and reaches the maps
  refill; the `no_matching_places_in_area` widen-area suggestion is produced.

### Regression battery (branch; named suites unchanged vs base → no regression)
- `test_local779_business_poi.py` + `test_local557_named_restaurant.py` +
  `test_local779b_restaurant_places.py` + `test_sq4_merge.py` +
  `test_local285_restaurant_selection.py` — **116 passed**.
- `test_palais_fix_lead_fixture.py` (script-style; run with `python3`, it calls
  `sys.exit(0)` at import so pytest cannot collect it) — **23/23 assertions pass**.
- `test_d538_restaurant_practicals.py` + `test_d557_scope_memory.py` — **16 passed**.

## Live test — isolated container `local779b-tg` (never `-p audioura`, all `--rm`)
Network `development_default`, `STORIED_MODE=true`, cache/pool off. One tour per
disposable container.

| # | Request | Result | $ (combined) |
|---|---------|--------|------|
| 0 | middle eastern restaurants near me, west Roxbury, MA (2) | **Clean refusal** | $0.0013 |
| 1 | Italian restaurants in the North End, Boston (3) | **3 stops delivered** | $0.6888 |
| 2 | walking tour: gyms near me, west Roxbury, MA (2) — control | **2 stops delivered** | $0.2392 |

**Cumulative = $0.9293 ≤ $1.20 cap.**

**Tour 0 (the bounce case) — honest refusal.** LLM proposed Al Wadi / Kebab House /
Safi Grill / Pita House / Basha, all with claimed West Roxbury addresses. PHASE 4
dropped Al Wadi; the PHASE 3C address guard passed the other four; **CUISINE-VERIFY
dropped all four** — `verify_listing_in_scope` = `False` ("not found in scope on
the map"); the maps-first search returned 0. Result: `error_code =
no_matching_places_in_area`, suggestion request `"restaurants in west Roxbury and
Roslindale"`. A direct live Nominatim probe confirms the refusal is correct: `"middle
eastern restaurants in West Roxbury, MA"` → 0 results, and a broad
`"restaurant West Roxbury"` returns only a Thai and an Italian place — **no
Middle-Eastern restaurant verifiably exists in West Roxbury**, so refusal (ticket
step 4) is the right answer. (The pre-fix artifact had *invented* "Mamma Maria's"
serving falafel and "West on Centre" — now eliminated.)

**Tour 1 — delivered, all real + in-scope + Italian:**
- Pizzeria Regina — 11 1/2 Thacher St, Boston, MA 02113 (42.3633, -71.0543)
- Mamma Maria — 3 North Square, Boston, MA 02113 (42.3645, -71.0544) — correctly Italian
- Carmelina's — 307 Hanover St, Boston, MA 02113 (42.3650, -71.0549)

Each LLM survivor verified individually on the map (`exists=True, cuisine_ok=True`).

**Tour 2 — business control, stayed green:**
- Planet Fitness (42.2842, -71.1485)
- YMCA of Greater Boston – West Roxbury (42.2860, -71.1428)

**audio_tours rows:** BEFORE 533 total / 449 is_test → AFTER 535 total / 451 is_test
(**+2 is_test**: id 777 Italian, id 778 gyms; the refused West Roxbury request wrote
0). No non-test rows, no `DELETE` of any kind.

## Known limitation (honest)
The bulk `dining_replenish_candidates` free-text query
(`"<cuisine> restaurants in <scope>"`) is sparsely answered by the free Nominatim
endpoint — it returned 0 live for both West Roxbury and the North End. The
**per-name** `verify_listing_in_scope` / `verify_listing_cuisine` lookups are
reliable and carry the delivered cases (the Italian tour is verified that way); the
bulk search is a best-effort refill fallback. With a richer places provider the
bulk refill would also populate; the verification and refusal behaviour is already
correct with what the current provider returns.

## Process
- Branched from HEAD (`f9ca9db0`); `git merge-base --is-ancestor f9ca9db0 HEAD` = 0.
- Committed only the source/test/runner files (no `git add -A`). Did not touch
  DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- No `DELETE`. One heavy build at a time. Containers all `--rm`.
