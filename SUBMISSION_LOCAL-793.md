# SUBMISSION — LOCAL-793: Home place search lands in the wrong place (Saigon → Paris) and shows "0 tours" next to tours

**Branch:** `LOCAL-793-home-search-geocode`
**Base:** subscribed (`7e2db321`) — verified `git merge-base --is-ancestor 7e2db321 HEAD` exits 0.
**Found by:** Michael, iPhone TestFlight 83, 2026-10-27 19:42.

## The bug

The Home search box geocoded a typed place with Nominatim `…/search?q=<query>&format=json&limit=1`
and blindly used `result[0]`. The LEAD reproduced the exact calls:

- **"Saigon Vietnam"** → a restaurant named "Saigon Vietnam" on Rue de Turin, **Paris** (48.88, 2.32).
  The map opened on Paris.
- **"Hi Chi Minh, Vietnam"** (typo) → a bus stop "Jabil Vietnam" in Thu Duc (10.836, 106.813),
  ~11 km from District 1 → **"0 tours in this map area"** although 4 HCMC tours were 7–12 mi away
  (zooming out by hand revealed them).
- **"Ho Chi Minh, Vietnam"** → the city (fine).

Two independent faults: (1) the geocoder picked a POI over the obvious place; (2) after a jump that
landed a few km off, the map declared "0 tours" instead of reaching the nearby tours.

## The fix

### 1. Geocoder prefers a PLACE over a POI (client)
`lib/utils/place_geocoder.dart` (new, pure, no Flutter imports) — `pickBestPlace()` takes the parsed
Nominatim results and returns the best **place** (OSM `class=place` city/town/village/suburb/… or
`boundary=administrative`), ranked by `importance`, then `place_rank`, then a type-preference order
(country → city → suburb). A POI can win **only** when no place exists at all.

`home_screen.dart` `_geocodeViaNominatim()` now asks for `limit=8`, `accept-language=en`, and a real
`User-Agent: com.audioura.audiotours/1.0 (support@audioura.com)` (Nominatim usage policy). It accepts
the pick **only when a place exists**; a POI-only result returns null so the server fallback runs.
So "Saigon Vietnam" resolves to Ho Chi Minh City, never the Paris restaurant.

### 2. Server-side geocoder fallback for typos (server, no key in the app)
`map_delivery_service.py` adds `GET /geocode?q=<text>`:
- **Serper Places** via the metered door (`serper_meter.serper_post`, ~$0.001/query, **one** query per
  lookup — cap-friendly) when a key is configured. Serper is typo-tolerant, so "Hi Chi Minh" resolves
  to Ho Chi Minh City.
- **Nominatim fallback** (free, real User-Agent, place-preferring) when Serper is off or finds nothing.

No API key ships in the app. Gateway route `/geocode` added to **both**
`api-gateway/gateway_routes.yaml` and `api-gateway/gateway_routes.subscribed.yaml` (both parse; 29 and
90 routes respectively). The client calls it only when Nominatim yields no place.

### 3. Never "0 tours" when a tour is close — auto zoom-out (client)
`lib/utils/map_zoom.dart` (new, pure) — `decideZoomOut(tourInView, nearestTourKm)`:
- tour already in view → keep;
- nearest tour within **50 km** (`kMaxZoomOutRadiusKm`) → **zoom out** to a level whose view radius
  covers it (`zoomForRadiusKm`); a tour within 25 km is therefore always shown;
- nearest tour beyond 50 km → **"Nearest tours: N km away"** with a *Show* button (don't zoom the world).

`home_screen.dart` `_useCustomLocation()` — after relocating, if `_loadedTours` is empty, it queries
`/tours-near` within 50 km for the nearest tour and acts on the decision.

### 4. Banner shows the resolved place name (client)
The geocoder returns a `GeoResult { location, name }`; `_dispatchTextSearch` passes `place.name`
(the resolved `display_name` / Serper name) to the banner instead of the raw typed text, so a wrong
match is visible at a glance.

## Files changed
- `audio_tour_app/lib/utils/place_geocoder.dart` — NEW, pure place-picker.
- `audio_tour_app/lib/utils/map_zoom.dart` — NEW, pure zoom-out decision.
- `audio_tour_app/lib/screens/home_screen.dart` — geocoder rewrite (+ server fallback), `GeoResult`,
  resolved-name banner, auto zoom-out / nearest-tour recovery.
- `map_delivery_service.py` — NEW `/geocode` endpoint (Serper metered → Nominatim fallback).
- `api-gateway/gateway_routes.yaml`, `api-gateway/gateway_routes.subscribed.yaml` — `/geocode` route.
- `audio_tour_app/test/place_geocoder_local793_test.dart` — NEW unit tests.
- `audio_tour_app/test/zoom_out_local793_test.dart` — NEW unit + widget tests.

## Tests

New tests (16, all pass):
- **place_geocoder** with the three LEAD payloads: "Saigon Vietnam" → Ho Chi Minh City (restaurant never
  chosen); "Ho Chi Minh" → the city; "Hi Chi Minh" typo → POI-only, no place (so the widget falls back
  to the server geocoder); plus degenerate inputs.
- **zoom-out**: a tour 12 km away with none in view → zoom-out shows it (widget test asserts the UI does
  NOT render "0 tours"); a tour within 25 km is never "0 tours"; a tour 120 km away → "Nearest tours:
  120 km away".

Full suite vs baseline:
- Baseline (before the change): **+1148 / −8**.
- After the change: **+1164 / −8** (+16 new passing tests; the same **8** failures).
- All 8 failures are `SocketException: Connection refused` live-server tests (local109_swipe_e2e,
  storied_compat_guard, storied_compat_screens_404) — the documented known-network baseline. **No new
  failures.**

`flutter analyze` on the changed files: **0 errors** (only pre-existing style `info`/`warning`).
`python3 -m py_compile map_delivery_service.py`: OK. Both gateway YAMLs parse.

## Live test
Not run in this session (no simulator/emulator launched; one-heavy-build rule). The fix is validated by
the unit + widget tests above, which encode the exact LEAD-reproduced Nominatim payloads and the 12 km
zoom-out case. A live pass would search "Saigon Vietnam", "Hi Chi Minh, Vietnam", "Mui Ne" on the iOS
simulator / Android emulator and screenshot Vietnam with the HCMC / Mui Ne tours.

## Cost
Server geocoder makes at most **one** Serper Places query per lookup, via the metered door; no live
paid calls were made during this change (code + unit tests only). Well under the $0.50 cap.
