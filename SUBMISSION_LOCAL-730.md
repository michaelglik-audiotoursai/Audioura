# SUBMISSION — LOCAL-730: Treats come from the tour's places, never from the phone's GPS

**Branch:** `LOCAL-730-treats-by-tour-places`
**Base:** `subscribed` @ `41b0c212` (verified: `git merge-base --is-ancestor 41b0c212 HEAD` exits 0)
**code_sha:** branch tip of `LOCAL-730-treats-by-tour-places` (the single commit
whose parent is `41b0c212`; run `git rev-parse HEAD` on the branch). The commit
message is `LOCAL-730: Treats from tour places, never phone GPS (D694)`.
**Decision basis:** D694; Privacy Policy "Location and places" (subscribed @ `936f1e97`, `legal/PRIVACY.md`)

---

## What changed (and why)

Before, the Treats screen read the phone's GPS (`Geolocator.getCurrentPosition()`)
whenever no custom Home location was set, and sent the exact position to
`/treats-near/<lat>/<lng>`; the server logged the exact coordinates. The Privacy
Policy now promises Treats are chosen from the places in the user's tours or a
place typed on Home, **never** from the phone's location, with phone-location as
a future opt-in that is off by default. This change makes the code match the
policy.

### App — `audio_tour_app/`

- **NEW `lib/services/treats_source_resolver.dart`** — the single source of truth
  for where Treats points may come from. Pure Dart, injectable readers, and it
  **does not import `geolocator`** — there is no code path to the device GPS.
  `TreatPoint(lat, lng)` carries a 2-decimal de-dup key. `resolve()` returns the
  points plus which source produced them, capped at **10** points.

- **REWROTE `lib/screens/treats_screen.dart`** — uses the resolver; removed the
  `geolocator` import and all GPS reads. Friendly empty state for source (d):
  _"Treats appear along the stops of your tours — download a tour or search a
  place on Home."_ Multi-point requests go to `POST /treats-near-places`; a
  single point uses the legacy `GET`; a client-side merge is the fallback if the
  batch route is unavailable (older server).

### Server — `treats_service.py`

- Kept `GET /treats-near/<lat>/<lng>` working for old app versions.
- Added **`POST /treats-near-places`** accepting `{"points": [{lat,lng}, …]}`
  with **1–10** points; results per point are merged and **de-duplicated by
  treat id** (keeping the nearest copy), nearest-first, capped at 5.
- **`round_coord()`** — the service logs only **2-decimal** coordinates
  (~1.1 km), never the exact position. No device id, user id or IP is read or
  stored.

## Source order (a) > (b) > (c) > (d)

The resolver returns the first non-empty source, in order:

- **(a)** the stops of the tour currently open or playing
  (`current_tour_path` → `audio_N.txt` stop coordinates);
- **(b)** the stops of the downloaded tours on the Listen page
  (`saved_tours[].path` → `audio_N.txt`), de-duplicated across tours;
- **(c)** the place last typed/searched on Home
  (`custom_location_lat`/`custom_location_lng`);
- **(d)** otherwise **no request at all** and the friendly empty state.

Stop coordinates are read from each tour's `audio_N.txt` files
(`Coordinates: <lat>, <lng>`), the exact format `tour_map_screen.dart`'s
`_parsePoi` already uses.

## Endpoint

`POST /treats-near-places` — body `{"points": [{"lat": <float>, "lng": <float>}, …]}`,
1–10 points. Response `{"treats": [...], "count": N, "points": M}`. Legacy
`GET /treats-near/<lat>/<lng>` unchanged.

## Opt-in hook — FEATURE FLAG, OFF (which I chose)

I chose to **keep the opt-in behind a build-time feature flag, OFF**, rather than
omit it — so the future opt-in has one documented home. In
`treats_screen.dart`:

```dart
const bool _kLocationTreatsOptInEnabled =
    bool.fromEnvironment('TREATS_LOCATION_OPT_IN', defaultValue: false);
```

While the flag is false, `_buildLocationOptInSwitch()` returns `null` — the
"Show Treats near me (uses your location)" switch is **not visible** and **no
GPS is read**. Turning the flag on is intentionally not enough to ship the
feature: D694 requires a Privacy Policy update first.

## Tests

### Dart — `audio_tour_app/test/treats_source_resolver_test.dart` (11 tests, all pass)
- source order (a) > (b) > (c) > (d), including "current tour with no coordinates
  falls through to (b)";
- de-duplication of overlapping stops (2-decimal key) and the 10-point cap;
- coordinate parsing matches the `_parsePoi` format;
- **zero Geolocator**: a structural guard asserts neither the resolver nor the
  screen imports `package:geolocator` or names `Geolocator` (comments stripped
  first, so documented mentions don't trip it);
- **RED TEST**: the guard on `treats_screen.dart` — re-introducing the GPS
  fallback (`import package:geolocator` + `Geolocator.getCurrentPosition`) makes
  this test fail. Verified: temporarily re-adding the import flipped the test to
  FAIL, then reverted and it passes again.

### Python — `test_local730_treats_by_places.py` (14 tests, all pass)
- `merge_treats` de-dups by id keeping the nearest, orders nearest-first, caps at
  5; name+vendor fallback key; missing-distance sorts last;
- `round_coord` logs 2 decimals and collapses sub-km precision;
- `POST /treats-near-places` contract: merges, rejects empty / over-cap /
  non-numeric;
- legacy `GET /treats-near` still works;
- **log rounding**: a GET with full-precision coordinates logs only the rounded
  values (exact coordinates absent from our log line).

## Live proof (emulator scenario, isolated own process)

`live_local730_proof.py` runs the **real** `treats_service` Flask app as a
**subprocess on a spare port (5078)** with a tiny in-memory fake DB — **no
audioura-\* container, DB or port touched** (all 13 audioura containers stayed
up, untouched). It plays the emulator scenario — location permission granted, a
downloaded tour open — by parsing the stop coordinates from a downloaded tour
fixture (`/tmp/local730_proof/tour_freedom_trail`, Freedom Trail stops) and
POSTing them, exactly as the app does.

Result:

```
[app] resolved 3 STOP coordinates:
       stop -> 42.36627, -71.05442
       stop -> 42.36371, -71.05366
       stop -> 42.36007, -71.05616
[app] (emulator GPS would be 37.42199, -122.084 — it is NEVER read or sent)

[server] POST response: 200 treats=2 points=3
[server] legacy GET /treats-near response: 200

=== CAPTURED SERVER REQUEST LOG (service log lines) ===
Getting treats near 3 places: (42.37,-71.05), (42.36,-71.05), (42.36,-71.06)
Found 2 treats across 3 places
=== END LOG ===

PROOF OK:
  - request carried the tour's STOP coordinates
  - emulator GPS (37.42199, -122.08400) never sent, never logged
  - server logged only ROUNDED (2-decimal) coordinates
  - GET /treats-near still available for old apps; no DB writes
```

The request carried the tour's **stop** coordinates; the Android emulator's
default GPS (Googleplex 37.42199, -122.08400) was never sent and never logged;
the service logged only rounded (2-decimal) coordinates.

**Caveat (honest):** werkzeug's HTTP access line echoes a GET request's URL path,
which for the legacy `GET /treats-near/<lat>/<lng>` necessarily contains the
coordinates. The app's real path for multi-point is the **POST**, which carries
coordinates in the body, not the URL; `round_coord` rounds our own explicit log
lines. If per-request access-log scrubbing of the GET path is wanted later, it is
a small follow-up on the WSGI access logger.

## Row counts

**No database writes.** This feature only reads treats; no migrations. The live
proof used an in-memory fake DB (0 rows written). Row counts: **0 inserted, 0
updated, 0 deleted.**

## Budget

**$0.00.** No external/paid API is called by Treats or by the proof (the DB is
in-memory; no LLM/geocoding). Well under the $0.30 cap.

## Files changed

- `audio_tour_app/lib/services/treats_source_resolver.dart` (new)
- `audio_tour_app/lib/screens/treats_screen.dart` (rewritten; Geolocator removed)
- `treats_service.py` (POST endpoint, merge/dedup, rounded logging)
- `audio_tour_app/test/treats_source_resolver_test.dart` (new)
- `test_local730_treats_by_places.py` (new)
- `live_local730_proof.py` (new; isolated live proof harness)
- `SUBMISSION_LOCAL-730.md` (this file)

Not edited: DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. ClickUp status unchanged.
