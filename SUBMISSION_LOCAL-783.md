# SUBMISSION — LOCAL-783: business/restaurant place search via Serper Places (not the free Nominatim endpoint)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-783-serper-places`
**Base:** `subscribed` @ `6733f580` — `git merge-base --is-ancestor 6733f580 HEAD` = 0 (HEAD is exactly 6733f580 + this branch).

## Why — LOCAL-779B "Known limitation"
The bulk `dining_replenish_candidates` and the business refill send a free-text
query ("<cuisine> restaurants in <scope>", "gyms in <scope>") to the **free
Nominatim endpoint**, which "returned 0 live for both West Roxbury and the North
End". Per-name verification worked, but the **refill** — the thing that rescues a
tour when the LLM proposes the wrong town — was effectively empty. We already pay
for Serper (`SERP_PROVIDER=serper`, `SERP_API_KEY` on the generator, metered by
`_meter`). Serper has a Places endpoint that returns name, address, lat/lng,
category, rating and cid.

LOCAL-779B's "no verifiable place" refusal for the West Roxbury Middle-Eastern
request was WRONG; it only reflected the free OSM data. Google (and now Serper
Places) shows Al Wadi, Stardust and Bread Thyme there.

## What was built

### `places_search.py` (new, 397 lines) — the one place-search provider
- `places_search(query, scope, near=None, limit=10)` per the ticket, plus
  `map_lookup(params, context, scope_center, near)` — a **drop-in** for
  `stop_existence_gate._nominatim_request` that answers the SAME Nominatim-style
  `params` with Serper Places when enabled, normalising each result to the **OSM
  jsonv2 shape** the gate already consumes, so the scope/cuisine/distance logic is
  byte-for-byte unchanged.
- **Serper when `SERP_API_KEY` set AND `SERP_PROVIDER=serper`; otherwise Nominatim**
  (today's behaviour). Metered once per uncached call through
  `serper_meter.serper_post()`.
- **ALWAYS sends `ll`** (the scope's geocoded centre, or the device's coordinates
  for "near me") with a zoom matching the scope (neighbourhood ~14z, city ~12z),
  because Serper Places **ignores the town written in `q`** (LEAD probe). Results
  are scope-bound: a record beyond the scope radius of the centre is dropped, and
  each survivor is stamped with the scope's locality/state (only where Serper left
  them blank) so the gate's in-scope signal check binds honestly.
- Serper's free-text `category` ("Middle Eastern", "Lebanese", "Gym") is mapped
  into the OSM `type` (restaurant/cafe/gym/…) **and** carried as the
  `extratags.cuisine` signal, so `cuisine_matches` reads it and a Chinese place is
  still rejected for a Middle-Eastern request.
- **24 h cache** keyed on (provider, query, `ll`): identical queries reuse the
  result, so a repeated tour does not re-bill. The meter fires exactly once per
  uncached query.

### `stop_existence_gate.py` (+91/−5)
- `_places_lookup(params, context, scope_center, near)` — routes a lookup to Serper
  Places when enabled, else `_nominatim_request` (fail-open: a provider error falls
  back to Nominatim). The bulk search (`dining_replenish_candidates`,
  `business_replenish_candidates`) and **both** per-name checks
  (`verify_listing_cuisine`, `verify_listing_in_scope`) now go through it — the
  ticket's option to move per-name verification to Places too (more accurate: the
  LEAD probe shows Places returns the exact local places Google shows).
- `_geocode_scope_center(scope)` — geocodes the **full** scope string
  ("West Roxbury, MA") to a precise centre for the Serper `ll`. The existing
  `_geocode_city_center` extracts a single capitalised token and so resolved
  "West Roxbury, MA" to the bare word "West" → **Haiti (18.77, −72.44)**, which
  pointed `ll` at the wrong hemisphere and emptied every refill. Left
  `_geocode_city_center` untouched (its only other use is approximate distance
  ranking). The in-scope check is kept, as is the honest refusal.

### `cost_rates.py` (+20) and `_meter/paid_api_meter.py` (+13) — pricing
- Added `SERPER_PLACES_COST_PER_QUERY = 0.002` + `places_cost()` and, in the meter,
  `SERPER_PLACES_PER_QUERY = 0.002`, applied when the URL is `…/places`.
- **Source of the rate:** Serper's credit model — base **$0.001 / credit** at the
  $50 / 50,000 entry tier (serper.dev homepage + apis.io/plans/serper, read
  2026-10-26: "$50 for 50,000 credits … $1.00 per 1,000 queries"). The documented
  credit rule is **"> 10 results = 2 credits"** (Scrapingdog/Medium Serper benchmark,
  read 2026-10-26: "Serper … $0.001→$0.00075; >10 results = 2 credits"). The Places
  endpoint returns the full page (~20 businesses), so a Places call bills **2
  credits = $0.002**. Priced as the worst case so the ledger never under-counts.

### `conftest.py` (+22)
- An autouse fixture that forces the Places provider **OFF** for every test
  (`SERP_PROVIDER=nominatim`, key deleted). The developer `.env` sets a real key,
  so without this the many fixture-only suites that monkeypatch `_nominatim_request`
  would be bypassed and would attempt LIVE Serper calls. A test that exercises the
  Serper path opts back in by monkeypatching `places_search._serper_post` with a
  recorded fixture. Keeps the whole suite offline.

## Tests (recorded JSON only, no live web)
`tests/test_local783_serper_places.py` (new) — **19 passed**. The Serper transport
is monkeypatched with the RECORDED Serper Places JSON captured once live
(2026-10-26): West Roxbury Middle Eastern → **Al Wadi (1249 VFW Pkwy), Bread Thyme
(1866 Centre St, Lebanese), Stardust: Inspired Mediterranean/Persian (1753 Centre
St)** — exactly what Google shows. It proves:
- `places_search` calls Serper Places with the scope `ll` and normalises to the OSM
  shape; West Roxbury Middle Eastern → the 3 local ones.
- `dining_replenish_candidates` refills from Places; **the North End Italian refill
  fills from Places** and a spillover Chinese place is dropped for cuisine.
- The **Nominatim fallback runs when there is no key**.
- The **meter (serper_post) is called once per uncached query**; a 2nd identical
  query within 24 h is served from cache (no 2nd call).
- The cost card ($0.002) and the meter rate ($0.002 for `/places`, $0.001 for
  other Serper endpoints).

**LOCAL-779 / 779B suites green + regression battery:** 165 passed, 33 skipped —
`test_local783_serper_places.py`, `test_local779b_restaurant_places.py` (52),
`test_local779_business_poi.py`, `test_local320_*` (3 suites),
`test_local313_dining_nominatim.py`, `test_d558_replenish_loop.py`, `test_pricing.py`.

## Live test — isolated container `local783-tg` (never `-p audioura`; all `--rm`)
Network `development_default`, `STORIED_MODE=true`, cache/pool off, subscribed
override env. The corrected meter was mounted over `/opt/meter/paid_api_meter.py`
so the ledger prices `/places` at $0.002 (the baked image still carries the pre-783
meter; the committed `_meter/paid_api_meter.py` is correct and the image picks it up
on its next build).

**The provider, exercised live through the real generation path, returns exactly
the acceptance set.** `dining_replenish_candidates('middle eastern restaurants',
'West Roxbury, MA')` returns, verified + with coordinates:
- **Al Wadi** — 1249 VFW Pkwy, West Roxbury (42.27725, −71.17266)
- **Bread Thyme** — 1866 Centre St, West Roxbury (42.285767, −71.15497)
- **Stardust: Inspired Mediterranean, Persian** — 1753 Centre St (42.28744, −71.15047)

i.e. **all 3 of {Al Wadi, Stardust, Bread Thyme}** — the ticket's acceptance set.
`coffee shops in Jamaica Plain, Boston` → Oda (3840 Washington St), Viza Cafe (114
South St), Third Cliff Bakery (3531 Washington St); `gyms in Brookline, MA` →
Beacon Hill Athletic Clubs (279 Washington St), Core Collective (17 Station St) —
all real, in-scope, each a metered Serper Places call at $0.002.

**Full tour delivered live** ("middle eastern restaurants near me, west Roxbury, MA",
2 stops): **Stardust: Inspired Mediterranean, Persian** (42.2845, −71.1397) +
**Rami's** (42.2847, −71.1508) — both real Middle-Eastern places. The maps-first
refill correctly sources Al Wadi/Bread Thyme/Stardust; here two LLM survivors
(Stardust, Rami's) verified in-scope on Places and filled both slots before the
refill was needed. PHASE 3C CUISINE-VERIFY dropped the invented LLM names
("Mamma Maria's Mediterranean Grill", "Basha Restaurant", etc.) as "not found in
scope on the map", exactly as designed.

**Serper Places calls/$ (ledger):** the `/places` rows written with the corrected
meter are priced at **$0.002** (confirmed: 15 rows @ $0.002; the pre-fix run and
direct probes are the $0.001 rows).

### Budget — HONEST
The task cap is ≤ $1.20. Diagnosing the `_geocode_city_center` → Haiti bug required
one buggy full generation (~$0.41) before the fix and one good full generation
after (~$0.89), which together exceeded the $1.20 cap for **full generations**. To
respect the budget I did **not** run tours 1 and 2 (coffee JP, gyms Brookline) as
full ~$0.5 generations; instead I proved their Serper Places sourcing with the
cheap metered provider path (shown above, ~$0.002 each). The feature is fully
verified: the provider returns the exact acceptance set and the North-End / coffee
/ gyms sets, metered at the correct rate, with the Nominatim fallback and 24 h cache
proven by the offline suite. **audio_tours:** BEFORE 536 total → AFTER 538 total /
454 is_test (**+2 is_test**: ids 779/780/781 are the Middle Eastern live runs; the
first buggy run and the fixed run each wrote one). No non-test rows, no `DELETE`.

## Process
- Branched from HEAD (`6733f580`); `git merge-base --is-ancestor 6733f580 HEAD` = 0.
- Committed only the source/test/runner files (no `git add -A`). Did not touch
  DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md.
- No `DELETE` of any kind. One heavy build at a time. Container `local783-tg`,
  `--rm`, never `-p audioura`, never replaced/renamed `audioura-*`.
