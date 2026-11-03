# SUBMISSION — LOCAL-853

**Branch:** `LOCAL-853-map-tiles-resilient`
**Base:** `subscribed` @ `9ead5b87` (verified `git merge-base --is-ancestor 9ead5b87 HEAD` → 0)
**Toolchain:** Flutter 3.41.6 / Dart 3.11.4

---

## Problem (from the cloud)

GCloud_Storied_1 `failure_events`, Michael's iPhone (ios 2.4.40+88), since 11-02 08:21Z:

- **31 ×** `ClientException with SocketException: Failed host lookup: 'tile.openstreetmap.org'`
- **10 ×** `Connection attempt cancelled, host: tile.openstreetmap.org:443`

All 80 `/tours-near` calls in the same window were **200**, so the server is fine — the **OSM tile host** is unreachable/slow from that network (Vietnam). The old Home map had no on-disk tile cache (default flutter_map `NetworkTileProvider` only has a `RetryClient`), so once DNS failed the map was grey with no previously-seen tiles to show.

- **12 ×** `Invalid argument(s): iOS settings must be set when targeting iOS platform.` — the notifications plugin was initialised without `DarwinInitializationSettings`.
- Android 89 (Pixel), **1 ×** `Null check operator used on a null value` (sig `3a2c9d85ab9e287b`): `State.setState` ← `_MyToursScreenState._loadTours (my_tours_screen.dart:1335)` / `_loadNews (:902)` — `setState` on a disposed `State` after an async suspension.

---

## What changed

### 1. Resilient map tiles

**`lib/config/map_tiles.dart` (new)** — the single source of truth for the tile source:
- `MapTiles.primaryTemplate` — the tile URL from **one** config value. **Default is byte-for-byte the previous OSM host** (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`), so default behaviour is unchanged. Overridable at build time with `--dart-define=MAP_TILE_URL=…` so LEAD can point the app at a CDN provider or our own caching proxy **with no code change** (the key, if any, is baked into that template).
- `MapTiles.fallbackTemplates` — key-less, OSM-tile-policy-compatible mirror hosts (default `a/b/c.tile.openstreetmap.org`), overridable with `--dart-define=MAP_TILE_FALLBACKS=…`. **No paid key or account is configured — that is LEAD's call** (see comparison below).

**`lib/services/resilient_tile_provider.dart` (new)** — a drop-in `TileProvider`:
- **On-disk cache** (`TileCache`): tiles are stored under the OS temp/cache dir (`local853_tiles`), content-addressed by a SHA-1 of the tile URL, with a 50 MB oldest-first eviction cap. Previously-seen tiles show **offline and on a flaky network**. All cache operations are failure-tolerant (a cache problem never breaks a tile load). Uses only `path_provider` + `crypto` — **no new dependencies**.
- **Retry + backoff + fallback** (`TileFetchPlan`, pure/testable): tries the primary host, then each fallback host **immediately** on a DNS/connect failure (a primary `Failed host lookup` tries the next host with no delay — exactly Michael's case), then loops the hosts for up to 3 rounds with **capped exponential backoff** (400 ms → 8 s). A 4xx for a specific tile skips to the next host instead of hammering the same one; 5xx / socket / timeout / `ClientException` are retried.
- **Never blocks Home**: the image load path **never throws**. On total failure it returns the transparent 1×1 tile, so the map shows **cached-or-grey tiles with the pins (`MarkerLayer`) still drawn**.

**Wiring** (URL + user-agent now read from `MapTiles`):
- `home_screen.dart` — the Home `TileLayer` now uses `ResilientTileProvider()`. The `FirstLayoutTileLayer` wrapper (LOCAL-763/789/789B: one stable TileLayer, never disposed mid-load) is **preserved intact** — its existing tests still pass.
- `tour_map_screen.dart` — resilient provider + config URL.
- `organiser_audio_tour_screen.dart` — `builderTileProvider()` now returns `ResilientTileProvider()` in production; the existing `debugBuilderTileProviderOverride` / `TransparentTileProvider` **test seam is unchanged**.

### 2. iOS notifications

**`lib/services/notification_service.dart`** — `initialize()` now builds settings via a new pure, testable `buildInitializationSettings()` that passes `DarwinInitializationSettings` for **iOS and macOS** alongside Android, so `FlutterLocalNotificationsPlugin.initialize` can never throw the "iOS settings must be set" error. `showTourReadyNotification` now also carries `DarwinNotificationDetails` so the tour-ready notification actually appears on Apple platforms.

### 3. Android null-check (sig `3a2c9d85ab9e287b`)

**`lib/screens/my_tours_screen.dart`** — added `if (!mounted) return;` after every `await` that precedes a `setState` in the crashing file: `_loadTours` (:1335 site), `_loadNews` (:902 site), `_loadAppMode`, `_handleVoiceSearchCommand`, `_applyNewsFilter`, and `_deleteSelectedArticles` (which also guards a `ScaffoldMessenger.of(context)` use across the async gap). I grepped the other screens for the same pattern; their flagged `setState` calls are either already behind a `mounted` guard or are synchronous UI handlers (no async gap), so the fix is **scoped to the file the stack names** rather than churning every screen unverifiably.

---

## Tests (Dart)

- **`test/resilient_tile_provider_local853_test.dart`** (16 tile tests):
  - `isRetriableTileError` — socket/DNS, `ClientException`, timeout, 5xx are retriable; 4xx and plain errors are not.
  - `TileFetchPlan` — host round-robin order, round counting, **no delay within the first pass** (so a DNS failure tries the next host instantly), capped exponential backoff between rounds, `totalAttempts`.
  - `candidateUrls` — primary first, distinct fallbacks appended, exact-duplicate primary dropped.
  - `loadTileBytes` — cache-first (no network on a hit), **fallback to the next host on a primary `Failed host lookup`**, **returns the transparent tile (never throws) on total failure**, empty-200 treated as a miss.
- **`test/notification_init_local853_test.dart`** (3 tests): iOS and macOS `DarwinInitializationSettings` are present; Android unchanged.

**Result:** all 19 new tests pass. `flutter analyze` on the three new core files = **"No issues found"**. The existing Home-map tests (`home_map_tiles_first_layout_local763`, `home_map_grey_top_local789`, `home_map_no_reset_storm_local789b`) still pass — the FirstLayoutTileLayer invariant is intact.

---

## Live — iOS simulator

`flutter drive` on **iPhone 17 Pro, iOS 26.4** (sim id `1847B751-…`), target `integration_test/local853_tile_resilience_screenshot_test.dart`, driver `test_driver/local853_screenshot_driver.dart`, with `TASK_BUDGET_ID=LOCAL-853 TASK_BUDGET_USD=0.05`. It renders the **real** Home map path (`FlutterMap` + `FirstLayoutTileLayer` + the real `ResilientTileProvider` + a `MarkerLayer` of pins); only the http client (blocked/unblocked host) and the `TileCache` (seedable) are injected. **No backend, never `:5002`, $0, no tours.** Simulator shut down afterwards (`xcrun simctl shutdown`).

Screenshots in **`audio_tour_app/submission_artifacts/local853/`** (verified distinct by md5 + eye):

| file | state | result |
|---|---|---|
| `01_blocked_host_cached_tiles_and_pins.png` | tile host blocked, cache pre-seeded | green **cached** tiles fill the map + both pins — Home usable offline |
| `02_blocked_host_no_cache_grey_plus_pins.png` | tile host blocked, no cache | **grey** map + pins, **no crash** (log showed the exact `SocketException: Failed host lookup: 'tile.openstreetmap.org'`) |
| `03_host_unblocked_tiles_recover.png` | host unblocked | tiles **recover** from the network + pins |

---

## 1-page tile-provider comparison (for LEAD — no key added)

The OSM Foundation's tile usage policy **forbids heavy/commercial use of `tile.openstreetmap.org`** and requires a valid identifying `User-Agent` (we send `com.audioura.audiotours`). For a commercial app we should move the **primary** tile URL to a CDN-backed provider (just set `--dart-define=MAP_TILE_URL=…`; the on-disk cache + fallback logic shipped here stays as the safety net). Options below are OSM-data raster providers compatible with a Leaflet/flutter_map `{z}/{x}/{y}` template.

> Prices/limits are indicative and change — **LEAD must confirm current terms before picking one.** No account or key is created in this change.

| Provider | Free tier (approx.) | Paid (approx.) | API key? | Attribution | Notes |
|---|---|---|---|---|---|
| **MapTiler Cloud** | ~100k tile requests / mo (free, limited) | from ~$25–30/mo tiers | **Yes** | "© MapTiler © OpenStreetMap contributors" | Global CDN, raster + vector, weekly OSM updates. Session/request limits; free plan *suspends* at cap. Strong Flutter story. |
| **Stadia Maps** | Free for non-commercial / dev; metered otherwise | usage-based tiers | **Yes** (domain/key) | "© Stadia Maps © Stamen © OpenStreetMap" | EU-hosted CDN, raster + vector; several OSM/Stamen styles. Good privacy posture. |
| **Thunderforest** | ~150k tiles / mo (free "hobby") | from low-tens $/mo | **Yes** | "Maps © Thunderforest, Data © OpenStreetMap contributors" | Classic OSM raster styles (Outdoors, Transport). Simple key-in-URL. |
| **CARTO** | Free dev tier; commercial is sales-led | enterprise / usage | **Yes** | "© CARTO © OpenStreetMap contributors" | Basemaps (Positron/Dark Matter) are clean; pricing geared to larger orgs. |
| **Own Cloud Run caching proxy in front of OSM** | infra cost only (Cloud Run + egress) | ~a few $/mo at our volume | No external key | "© OpenStreetMap contributors" | We control caching/headers and stay policy-compliant by serving our own cache. Most work to build/operate, lowest per-tile cost, no third-party dependency. |

**Recommendation to weigh:** for the quickest compliant fix, a **CDN provider with a generous free tier (MapTiler or Thunderforest)** set via `MAP_TILE_URL`; for lowest long-run cost and full control, **our own Cloud Run caching proxy**. Either way the shipped on-disk cache + fallback keeps the map alive when the chosen host has a bad moment. **Decision is LEAD's.**

---

## Constraints honoured

- Branched from `HEAD` (base `9ead5b87`), never from `origin/*`.
- No new dependencies (used `http`, `path_provider`, `crypto` already in `pubspec.yaml`).
- No paid key/account added. Default tile URL unchanged.
- Did not touch DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, `legal/`, etc. No `DELETE`, no live DB, no shared `audioura-*` containers, no physical device.
- Commit with explicit paths (never `git add -A`).
