# SUBMISSION — LOCAL-789

**Branch:** `LOCAL-789-map-tiles`
**Base:** `subscribed` @ `4c205cdc`. `git merge-base --is-ancestor 4c205cdc HEAD` → 0.
**Ruling:** LOCAL-789 + ADDENDUM (client place-alias map).
**Budget:** $0.00 (no AI / paid-API calls; tiles fetched directly from OSM; sim/emulator only).

Michael, iPhone TestFlight 2.4.35 (83), 2026-10-27 14:29: on entering Home the **top ~60 % of the map is plain grey** (markers drawn on it), the bottom ~40 % has tiles; after ~30 s the map redraws normally. Banner on top: "Showing tours near: Boston, Ma".

---

## 1. The bug — top band grey for ~30 s

### Symptom
The Home map opens with the tour/location markers but the **upper part of the map has no tiles** (grey), only the lower part is drawn. It heals ~30 s later. Markers draw regardless because `MarkerLayer` positions its points absolutely, independent of the tile grid.

### Why it happens
`screens/home_screen.dart` builds the Home map as `Column( header , Expanded(FlutterMap) )`. The header is **variable height**: the orange "Showing tours near: …" banner appears the instant a place search sets `_isUsingCustomLocation`, and the LOCAL-761 hide-on-scroll bar comes and goes. When the header grows **after** the map's first layout, the `Expanded` map changes size, so the tile range the `TileLayer` computed for the old viewport no longer covers the whole new viewport — the newly-exposed band has no tiles until the next camera/location event (~30 s later), exactly Michael's report.

### Root-cause correction to LOCAL-763 (important)
LOCAL-763 added `FirstLayoutTileLayer`, which drove **flutter_map's `TileLayer(reset:)` stream** to reload tiles on a size change. While wiring the LOCAL-789 fix I found that **the `reset` stream does nothing in flutter_map 6.2.1**: in `tile_layer.dart` the subscription is

```dart
late final _resetSub = widget.reset?.listen((_) { … removeAll … reload … });
```

a `late final` that is **only ever read in `dispose()`** (to cancel it). Because Dart initialises a `late final` lazily on first *read*, and nothing reads `_resetSub` during the widget's life, the listener is **never attached** — firing `reset` has no effect. I proved this with a throwaway probe: a plain `TileLayer` given a `reset` stream requests **zero** new tiles when the stream fires at a constant size.

So LOCAL-763's reset-only mechanism never actually reloaded tiles; the "blank map heals after a pinch" it fixed was healed by the **camera event the gesture produces** (flutter_map's working `mapEventStream` path), not by `reset`. The same is true of the ~30 s self-heal here: the next location/camera event reloads the grid.

### Fix (library-version-independent, no timers)
`lib/widgets/first_layout_tile_layer.dart` now reloads by **rebuilding the wrapped `TileLayer` with a changing `ValueKey`** (an `int _epoch` bumped on each trigger, applied via `KeyedSubtree`). A fresh `TileLayer` `State` runs `didChangeDependencies` against the **current** camera and requests **every visible tile**, so the whole viewport — including the previously-grey band — is covered. Triggers, all coalesced to **at most one rebuild per frame** so a burst cannot thrash the grid:

1. the first post-frame after build (first settled layout — the LOCAL-763 case);
2. a `MapEventNonRotatedSizeChange` (when flutter_map does emit it); and
3. an **`externalReset`** stream a parent fires from a `LayoutBuilder` around the `FlutterMap` when its `BoxConstraints` change — the banner / scroll-bar case flutter_map may not emit a size event for in time.

`home_screen.dart` wraps the map:

```dart
Expanded(
  child: LayoutBuilder(
    builder: (context, constraints) {
      final h = constraints.maxHeight;
      if (_lastMapHeight != null && h.isFinite &&
          (h - _lastMapHeight!).abs() > 0.5 && !_mapSizeReset.isClosed) {
        _mapSizeReset.add(null);           // laid-out height changed
      }
      if (h.isFinite) _lastMapHeight = h;
      return FlutterMap( … children: [
        FirstLayoutTileLayer(
          externalReset: _mapSizeReset.stream,
          builder: (reset) => TileLayer(
            urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            userAgentPackageName: 'com.audioura.audiotours',  // §3
            reset: reset,                   // forwarded (forward-compat)
          ),
        ), … ]);
    },
  ),
)
```

The `reset` stream is still passed through (harmless, and forward-compatible if flutter_map fixes the subscription), but the **key bump** is what heals the map. The `_mapSizeReset` broadcast controller is a `_HomeScreenState` field, closed in `dispose()`.

---

## 2. User agent (§3 of the ticket)

Every `TileLayer` in `lib/` now uses `userAgentPackageName: 'com.audioura.audiotours'`. Only `home_screen.dart` still had the generic `com.example.audiotours` (OSM throttles/blocks generic `com.example` agents → slow tiles); `organiser_audio_tour_screen.dart` and `tour_map_screen.dart` were already correct. A grep for `com.example` in `lib/` now returns only a code comment.

---

## 3. Client place-alias map (ADDENDUM)

LOCAL-793's live run: with the server `/geocode` not deployed, "Saigon Vietnam" ends at "Nothing found" (Nominatim returns only POIs literally named Saigon). `lib/utils/place_geocoder.dart` gains a pure, unit-tested `applyPlaceAliases(query)` applied **before** geocoding in `home_screen.dart._geocodeLocation`:

- Historic → modern, per the LEAD list: Saigon → Ho Chi Minh City; Bombay → Mumbai; Peking → Beijing; Calcutta → Kolkata; Madras → Chennai; Rangoon → Yangon; Canton → Guangzhou.
- **Whole-word**, **case- and diacritic-insensitive** (folds "Sàigòn" → matches): the query is split into word / non-word runs so only an exact whole token is rewritten and separators (", Vietnam") are preserved. "Saigons", "New Bombayville" are left untouched.

The existing LOCAL-793 `_safeMapMove` helper (swallows the transient "controller disposed during the loading spinner" error) is unchanged and still used by `_useCustomLocation` after the aliased query resolves.

---

## Tests

**New / changed Flutter test files — all green (14 tests):**

- `test/home_map_grey_top_local789_test.dart` (2): with a counting, offline `TileProvider` — (a) firing `externalReset` reloads the tiles (the top-band heal path); (b) a banner growing **above** the map shrinks it, and the `LayoutBuilder → externalReset` path reloads the tiles for the new viewport, with **no gesture and no timer**.
- `test/place_alias_local789_test.dart` (one group, 11 expectations across cases): "Saigon Vietnam" → "Ho Chi Minh City Vietnam"; every historic name maps; case/diacritic folding; whole-word (no false positives); punctuation/spacing preserved; empty and no-op queries unchanged.
- `test/home_map_tiles_first_layout_local763_test.dart` (2, LOCAL-763): still pass against the corrected widget.

**flutter analyze:** `No issues found!` on the three changed `lib/` files and both new test files. (`home_screen.dart` carries only pre-existing `prefer_const_constructors` info lints, unrelated to this change.)

**Full `flutter test` vs baseline:** my branch `+1191 −8`; a fresh baseline worktree at `4c205cdc` `+1179 −8`. **Same 8 pre-existing failures, in the same 3 files**, zero new ones:
`local109_swipe_e2e_test.dart` (6 — needs a live server), `storied_compat_guard_test.dart` (1 — pre-existing raw call in `services/failure_reporter.dart`, a file I did not touch), `storied_compat_screens_404_test.dart` (1). My branch adds +12 passing.

---

## Live test (sim + emulator only — never Michael's phones)

I reproduced the **exact bug state** on both the Android emulator (`emulator-5554`, `sdk gphone64 arm64`, API 34 — **not** the physical Pixel 4) and the iOS simulator (iPhone 17 — **not** Michael's iPhone): Home with the "Showing tours near: Boston, MA" banner, the map grey. The Boston custom-location state was seeded via SharedPreferences (so cold start lands on it) plus `simctl location`.

**Environment blocker on tile *rendering* (documented, not a code defect).** Both the simulator and the emulator **cannot reach `tile.openstreetmap.org`** from inside this sandbox: every tile request fails with `SocketException: Connection attempt cancelled` / `Connection closed before full header was received`, while the **host** machine fetches the *identical* tile URLs with **HTTP 200** (verified with `curl` and the app's own User-Agent). General egress works (`api.audioura.com` returns 401 — reached, auth-gated); only OSM's CDN is blocked for the VM. So the map is grey on **any** build, fixed or baseline — a tiles-visible screenshot is not obtainable here.

**What the live run DID verify (logcat):** after my epoch-driven reload the `TileLayer` requests the **entire visible tile grid** — the full y-range covering the **top and bottom** of the viewport (e.g. iOS `z=13 x=1308–1312 y=3163–3168`), which is precisely the behaviour that cures the grey top band — and it does so with exactly **two bounded epoch bumps** at startup (first-layout + size event, ~20 ms apart), **no runaway loop**. The widget tests pin the same guarantee deterministically offline.

Screenshots in `audio_tour_app/docs/local789/`:
- `android_home_boston_t1.png` — bug state reproduced on the Android emulator (Boston banner, grey map; OSM unreachable in-sandbox).
- `ios_home_boston_fix.png` — fix build at Home with the Boston banner on the iOS simulator (same OSM-unreachable grey).

**Safety / process:** one heavy build at a time; emulator and simulator shut down afterward. No `-p audioura`; no `DELETE`. Paid-API cap $0.00. The local `android/app/debug.keystore` used to sign the debug build is **gitignored** and not committed. None of the protected files (DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md) were touched.

---

## Files

**New**
- `audio_tour_app/test/home_map_grey_top_local789_test.dart`
- `audio_tour_app/test/place_alias_local789_test.dart`
- `audio_tour_app/docs/local789/android_home_boston_t1.png`
- `audio_tour_app/docs/local789/ios_home_boston_fix.png`
- `SUBMISSION_LOCAL-789.md`

**Changed**
- `audio_tour_app/lib/widgets/first_layout_tile_layer.dart` (epoch/key reload + `externalReset`; corrected root-cause note)
- `audio_tour_app/lib/screens/home_screen.dart` (LayoutBuilder → `_mapSizeReset`; user agent; `applyPlaceAliases` before geocoding; controller field + dispose)
- `audio_tour_app/lib/utils/place_geocoder.dart` (`kHistoricPlaceAliases` + `applyPlaceAliases`)
