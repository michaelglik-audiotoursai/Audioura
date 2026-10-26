# SUBMISSION — LOCAL-779: Business POI tours ("gyms near me") fail

**Branch:** `LOCAL-779-business-poi-verification`
**Base:** `subscribed` @ `572a4844` (`git merge-base --is-ancestor 572a4844 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

---

## The bug

A business tour — "walking tour: gyms near me, west Roxbury, MA" — failed with
*"no stops could be generated"*. Three separate defects stacked up, all rooted in
one wrong assumption: **every walking/outdoor stop is a Wikipedia-style landmark.**

1. **Existence gate can't verify a business.** A gym/café/shop is rarely on
   Wikipedia/Wikidata, so the walking-tour existence path
   (`_check_walking_stop_existence`, Wikidata P625 / OSM landmark) found *"no
   evidence"* and dropped every stop. Restaurants already had a working path
   (LOCAL-281/313 — a maps/places lookup via OpenStreetMap/Nominatim); businesses
   did not.

2. **PHASE 3A hollow-reason filter wiped businesses before the gate even ran.**
   The LOCAL-329 substance filter demands a selection reason with "a specific
   date, person, or event". A gym legitimately has none ("a popular gym chain
   known for affordable memberships"), so all five candidates were rejected and
   the run clean-failed at *"no usable POIs after parsing"* for **$0.0006** — the
   gate never searched the web. *(Found during the live test; fixed.)*

3. **PHASE 3C compared the address to the WHOLE request string.** For
   "middle eastern restaurants near me, west Roxbury, MA" the containment guard
   tested each address against the entire request, not the resolved scope, and
   removed every restaurant (`REMOVED 'Al Wadi' … not in 'middle eastern
   restaurants near me, west Roxbury, MA'`). A compounding bug: the
   neighbourhood→city alias rewrote "west roxbury" to "boston" **before** a direct
   match, so a West Roxbury address failed against a "West Roxbury" scope.

Plus the location stripping that turned the request into the junk neighborhood
`': gyms near me'` in the area resolver, and PHASE 4 accepting an Italian
restaurant ("Mamma Maria") for a Middle-Eastern request.

---

## The fix

### `stop_existence_gate.py` — generalize the restaurant maps path to businesses
- **`classify_business_vs_landmark(poi_type) → 'business' | 'dining' | 'landmark'`**
  — a small keyword list (gym, fitness, café, coffee, bakery, bar, brewery, spa,
  climbing, yoga, shop, store, bookstore, …) plus the existing dining
  classification. Deterministic; the generator layers the LLM intent on top.
- **`_check_business_existence(stop_title, venue_name, city_signals) →
  (verified, evidence, coords)`** — the dining `_check_dining_nominatim` path
  generalized: an OpenStreetMap/Nominatim listing whose **name matches** and whose
  **address lies inside the scope**, with a broad business category set
  (amenity/leisure/shop/craft/office). **Coordinates come straight from the
  listing.** A fabricated name (no listing) or a right-named place in the wrong
  city returns unverified → dropped by ENFORCE, exactly as a fabricated landmark is.
- **`_classify_venue_kind(..., poi_type=…)`** now returns `'business'` for a
  business poi_type **even when `tour_category='walking'`** — the signal is the
  poi_type, not the category.
- **`verify_stop_existence(..., poi_type=…)`** adds a `'business'` branch →
  `_check_business_existence`, sets `result['coords']` and `source='business_maps'`.
  `run_existence_gate(..., poi_type=…)` threads it through.
- **`business_replenish_candidates(poi_type, scope, needed, …)`** — business
  replenishment asks the maps provider for `"<poi_type> in <scope>"` **directly**
  (not an LLM, which invents branches), takes the verified listings with real
  addresses + coordinates, and **ranks by distance** (device coordinates when the
  app sends them for "near me", else the scope centre via `_geocode_city_center`).

All OSM calls go through the existing `_nominatim_request` seam, so a throttled /
failed lookup is **UNKNOWN** (kept, retried), never searched-and-absent (D162) —
and the tests monkeypatch it with recorded JSON (no live web).

> On provider choice: the ticket says *"the Serper places/maps search the
> restaurant path uses, or the same provider"*. The restaurant path's maps lookup
> **is** OpenStreetMap/Nominatim (no Serper places helper exists in the tree), so
> businesses use the same provider the restaurant path already uses.

### `generate_tour_text.py`
- **`_scope_from_request(location, intent)`** — prefers `intent.geographic_scope`;
  otherwise strips a leading `"<type>:"` label and leading poi/"near me" segments
  to recover the bounded place ("West Roxbury, MA").
- **PHASE 3C** now compares the address against this **resolved scope**, not the
  whole request string (both the first pass and the Part-C replacement check).
- **`_address_matches_location`** checks the **raw** address token against the
  location **before** the neighbourhood→city alias, so a West Roxbury address
  matches a "West Roxbury" scope (the alias stays a fallback for a "Boston"-phrased
  request).
- **PHASE 3A LOCAL-329**: a **business** poi_type is **exempt** from the
  hollow-reason substance filter — a business's existence is proven by a maps
  listing downstream, not by a notable-reason sentence.
- **Existence gate call site** passes the poi_type and **attaches the
  `business_maps` coordinates** to the matching stop (`coordinates` /
  `latitude` / `longitude`).
- **LOCAL-290 replenishment** uses `business_replenish_candidates` (maps-direct)
  for a business tour before falling back to the GPT→gate loop.
- **Area resolution** is run on `_scope_from_request(...)` so the resolver gets
  "West Roxbury, MA", not "gyms near me".
- **PHASE 4** (`verify_poi_matches_type`) now states that a cuisine/sub-type
  qualifier must match, with a worked "Mamma Maria is Italian, not Middle Eastern"
  example — so a wrong-cuisine place is a non-match.

### `area_resolver.py`
- `_parse_location` strips a leading `"<type>:"` label and a `"near me"` phrase
  before parsing (defense-in-depth), so a direct caller also gets "West Roxbury, MA"
  instead of neighborhood `': gyms near me'`.

### Narration (task 4 of the ticket)
There is **no** hardcoded "landmark" opening template — narration is built from the
stop name, the poi_type hint, and verified facts, so a gym is never called a
landmark. The existing D-rule fabrication gates (unsupported-claim, practical-facts,
contradicted-claim — all visible in the live logs) prevent invented
prices/hours/reviews. No deep narration refactor was needed.

---

## Tests — red first, fixtures only (no live web)

`tests/test_local779_business_poi.py` (36 tests, all green) monkeypatches
`_nominatim_request` with recorded Nominatim JSON:

- **classification** — gyms/cafés/shops/bars/spas/bookstores → `business`;
  restaurants → `dining`; landmarks/museums/filming → `landmark`.
- **business existence** — a real gym verifies with coordinates **inside the
  scope**; a fabricated business is dropped; a right-named gym in the wrong city is
  dropped (proximity binds).
- **gate ENFORCE end-to-end** — two gyms verify, one fabricated gym is dropped;
  the verified verdicts carry coords and `source='business_maps'`.
- **landmark tour unchanged** — a landmark poi_type never routes to the business
  path.
- **PHASE 3C scope** — `_scope_from_request` yields the bounded place; an in-scope
  West Roxbury restaurant address PASSES and an out-of-scope North End address is
  REJECTED against the scope.
- **area resolver** — "West Roxbury, MA" is parsed out of the junk request.
- **business replenishment** — maps-direct, ranked by distance, wrong-city excluded.
- **PHASE 4 cuisine** — the type-verification prompt now carries the cuisine rule
  and the Mamma Maria example.

### Regression (base vs branch, all green)
- `test_sq4_merge.py` — PASS (script)
- `test_palais_fix_lead_fixture.py` — PASS (script)
- `tests/test_local557_named_restaurant.py`, `test_local281_dining_venue_kind.py`,
  `test_local320_nondining_regression.py`, `test_local662_walking_v9_defects.py`,
  `test_local351_us_address_parsing.py`, `test_local751_area_parse_danvers.py`,
  `test_contained_regression.py`, `test_local591_contained_venue.py`,
  `test_local668_blocker4b_contained.py`, `test_local772_retire_gpt35_subscribed.py`
  — all green.

> **Pre-existing failure, NOT caused by this change:**
> `test_local480_facility_category.py::TestWiring` (6 tests) fail on the base
> commit `572a4844` too — they introspect `generate_tour_text`'s source for strings
> that have drifted. Verified by `git stash` on the base. Left untouched.

---

## Live test — own isolated container, STORIED_MODE=true, budget ≤ $1.50

Each tour ran in its **own** throwaway container (crash isolation), never touching
`audioura-*`:

```
docker run --rm --name local779-tg --network development_default \
  -e DATABASE_URL=postgresql://admin:***@postgres-2:5432/audiotours \
  -e DB_HOST=postgres-2 -e DB_PORT=5432 \
  -e OPENAI_API_KEY=*** -e GEMINI_API_KEY=*** -e SERPER_API_KEY=*** \
  -e STORIED_MODE=true -e TEST_GEMINI_MAX_USD=1.50 -e COST_HARD_LIMIT_USD=1.50 \
  -v "$PWD":/app -w /app audioura-tour-generator \
  python -u run_local779_container.py <0|1|2>
```

**`audio_tours` row count: 523 → 526 (+3 is_test rows, one per tour). No DELETE.**

| # | Request | Stops delivered | Evidence | $ |
|---|---------|-----------------|----------|---|
| 767 | `walking tour: gyms near me, west Roxbury, MA` (2) | **Fitness Together in West Roxbury** (42.2848, -71.1365), **Planet Fitness** (42.2842, -71.1433) | Planet Fitness `nominatim_osm: 'Planet Fitness' … 1870 Centre Street, boston`; Fitness Together/YMCA `venue_corpus canonical_title(geo)`. **Gold's Gym** + **'The Club by George Foreman III'** dropped UNVERIFIED, replenished to 2. | $0.23 |
| 768 | `coffee shops in Harvard Square, Cambridge MA` (3) | **Tatte Bakery & Cafe** (1288 Massachusetts Ave), **Starbucks** (1 Harvard Sq), **Crema Cafe** | Tatte `nominatim_osm: 'Tatte Bakery & Cafe' … 420 Harvard Street`; 5 unverified cafés dropped, replenished to 3. | $0.38 |
| 769 | `Freedom Trail, Boston` (3) — **LANDMARK control** | **Massachusetts State House** (24 Beacon St), **Park Street Church** (1 Park St), **King's Chapel** (58 Tremont St) | Normal landmark path — **no `business_maps`**, behaviour unchanged. | $0.41 |

**Before the business fix**, the gyms request clean-failed at PHASE 3A for $0.0006
("no usable POIs after parsing"); after the fix it delivers 2 verified stops with
coordinates. The landmark control is byte-identical in shape to a normal Freedom
Trail tour.

**Spend:** final 3 production tours = **$1.02**; total metered including debug
iterations = **$1.199** — under the **$1.50** cap (enforced by
`tests/live_run_meter.py`, all providers combined).

Driver: `run_local779_container.py` (single-tour mode via `argv[1]` so one crash
can't lose the others).

---

## Files

| File | Change |
|------|--------|
| `stop_existence_gate.py` | `classify_business_vs_landmark`, `_check_business_existence`, `business_replenish_candidates`, `_haversine_km_local`; `_classify_venue_kind` / `verify_stop_existence` / `run_existence_gate` take `poi_type`; `business` venue-kind + `coords` in the verdict. |
| `generate_tour_text.py` | `_scope_from_request`; PHASE 3C compares against the resolved scope; `_address_matches_location` raw-token-first; PHASE 3A business exempt from the hollow-reason filter; gate call passes poi_type + attaches `business_maps` coords; business replenishment; area resolution on the clean scope; PHASE 4 cuisine match. |
| `area_resolver.py` | `_parse_location` strips a leading `"<type>:"` label and `"near me"`. |
| `tests/test_local779_business_poi.py` | **New** — 36 fixtures-only tests. |
| `run_local779_container.py` | **New** — isolated live-run driver (3 tours, metered + capped). |

## Process
- Branched from `subscribed` @ `572a4844`; `git merge-base --is-ancestor 572a4844 HEAD` → 0.
- No `git add -A`; only the files above were staged. No `DELETE` of any kind.
- No edits to DECISIONS.md / CLAUDE.md / BACKLOG.md / WORK_QUEUE / `.continuous_dev/` /
  SUBSCRIBED_COMMUNICATION_01.MD / `legal/` / GCLOUD_STORIED_START_HERE.md.
- One heavy build at a time; `audioura-*` containers never touched.
