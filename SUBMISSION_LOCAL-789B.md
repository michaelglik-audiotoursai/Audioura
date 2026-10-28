# SUBMISSION — LOCAL-789B

**Home map STILL grey on entry in iOS build 84 (fully grey now); one pinch fixes it at once.**

Base: subscribed (642bf8a3). Branch: `LOCAL-789B-map-tiles-real`.
Paid-API spend: **$0** (OSM tiles only; no paid geocoder/server call made).

---

## TL;DR

The grey map was **self-inflicted tile cancellation**, not a network/sandbox limit. LOCAL-789's
fix rebuilt the `TileLayer` with a new `ValueKey` on every layout/size trigger; in flutter_map
6.2.1 that **disposes the TileLayer's network client mid-load and aborts every in-flight tile
request**. Because the Home header settles over several frames, the resets formed a **storm** that
cancelled tiles faster than they loaded — leaving the map fully grey until a pinch stopped it. (That
same cancellation is exactly what LOCAL-789's submission saw in the simulator and mislabelled a
"sandbox limit".)

The fix keeps **one stable `TileLayer`** (never disposed mid-load) and reloads after the size
settles with an **imperceptible camera nudge** (zoom ± 1e‑4) — the programmatic equivalent of the
pinch that already heals the map. Plus: a legacy custom-location label is **re-resolved once** on
startup so the banner shows a real place name instead of raw typed text.

---

## The LEAD's hypothesis — checked

**1. Can the simulator reach OSM?** YES. Proven directly:

```
$ xcrun simctl spawn "iPhone 17 Pro" /usr/bin/curl -sS -w "HTTP %{http_code}, %{size_download} bytes\n" \
      https://tile.openstreetmap.org/3/4/2.png
HTTP 200, 6987 bytes
$ file /tmp/osm_tile_sim.png
PNG image data, 256 x 256, 8-bit colormap, non-interlaced
```

The simulator fetches the very tile the app couldn't draw. So the app was cancelling its own
requests — **not** a sandbox limit. The LEAD's hypothesis is confirmed; LOCAL-789's "sandbox"
claim is disproved.

**2. Instrumentation — reset fires, TileLayer rebuilds, tile cancellations.** See the root-cause
mechanism below (read out of flutter_map 6.2.1's own source) and the new counting regression test
`home_map_no_reset_storm_local789b_test.dart`, which proves the fix never disposes the tile
provider under a burst of 20 resets (0 disposals while mounted) and nudges at most once per settled
size (no loop).

---

## Root cause (flutter_map 6.2.1, verified in `~/.pub-cache`)

LOCAL-789 wrapped the tile layer in `KeyedSubtree(key: ValueKey(_epoch))` and bumped `_epoch` on
every reload trigger. A `ValueKey` change **disposes** the old `TileLayer` and builds a new one.
But:

- The default tile provider is `NetworkTileProvider` (`tile_layer.dart:294`), which **does not
  support cancellation** (`getImage`, not `getImageWithCancelLoadingSupport`) and holds a
  `RetryClient`.
- `TileLayer.dispose()` (`tile_layer.dart:499`) calls `widget.tileProvider.dispose()`, and
  `NetworkTileProvider.dispose()` calls `httpClient.close()` — which **aborts every in-flight tile
  HTTP request** on that client (surfacing as `SocketException: Connection attempt cancelled`).
- `TileImage.dispose()` (`tile_image.dart:243`) also completes `cancelLoading`, abandoning the tile.

Triggers that bumped the epoch: the first post-frame, `didChangeDependencies`,
`MapEventNonRotatedSizeChange`, and the `externalReset` fired by a `LayoutBuilder` in
`home_screen.dart` on **every** laid-out height delta > 0.5 px. On a real device the header settles
over several frames (loading spinner → map, the async `_loadCustomLocation` `setState` that flips
the orange banner, the LOCAL-761 hide-on-scroll bar), so the epoch was bumped again and again — each
bump killing the previous layer's tiles. That is the **reset storm**: grey until a user gesture
changes the camera, no more resets fire, and the last layer finally keeps its tiles. The key
rebuild is strictly more destructive than LOCAL-763's reset-only attempt, which is exactly why
build 84 was **fully** grey where build 83 was only partly grey.

Also relevant: in 6.2.1 the `TileLayer.reset` stream is effectively dead — its subscription is a
`late final` only ever read in `dispose()` (`tile_layer.dart:384,497`), so it never actually
listens during the layer's life. Firing `reset` does nothing. The fix therefore cannot rely on it.

---

## The fix

### 1. `lib/widgets/first_layout_tile_layer.dart` — stable layer + camera nudge

- **Removed the `KeyedSubtree`/`ValueKey` epoch rebuild entirely.** `build()` now returns the
  wrapped `TileLayer` directly, so it is **stable for the life of the map** — never disposed
  mid-load, its network client never closed, its in-flight tiles never cancelled.
- Added an optional `mapController` parameter. After the size settles, the widget performs a single
  **camera nudge**: `controller.move(center, zoom ± 1e-4)`. A real `move()` emits a `MapEventMove`
  that the live `TileLayer`'s `_tileUpdateSubscription` recomputes its visible tile range from — so
  the whole (correct-size) viewport loads, with **nothing disposed**. 1e‑4 at the Home zooms is far
  below one pixel, so it is invisible. This is the programmatic equivalent of the pinch that already
  heals the map (the LEAD's fallback #3).
- **No loop, at most one nudge per settled size.** Triggers are coalesced to one post-frame
  callback; a nudge is only performed when the camera's `nonRotatedSize` signature differs from the
  size last nudged for. The nudge changes *zoom*, not the laid-out *size*, so it can never
  re-trigger itself. A burst of same-size triggers nudges once. The nudge sign alternates so two
  consecutive settled sizes each produce a genuine (non-no-op) camera change.
- Guards: `controller.camera` may throw if the controller is detached (the LOCAL-793 loading-spinner
  window) — caught; the pre-layout size sentinel `(-1,-1)` / non-finite sizes are skipped.
- The `reset` stream is still forwarded for forward-compat (harmless in 6.2.1).

### 2. `lib/screens/home_screen.dart` — wire the controller + banner re-resolution

- Passed `mapController: _mapController` to `FirstLayoutTileLayer`.
- **Banner:** added a `custom_location_resolved` bool pref. `_saveCustomLocation` sets it true on
  save (every save comes from a geocoder-resolved name). `_loadCustomLocation` reads it; for a
  legacy entry (flag absent — saved before LOCAL-793 as raw typed text like the typo
  "Hi Chi Minh, Vietnam"), it calls `_reResolveLegacyCustomLocation`, which runs the saved label
  through the **existing** `_geocodeLocation` (alias → Nominatim place pick → server fallback) and,
  on success, updates the banner text and coordinate and re-saves it marked resolved. **Non-
  destructive**: if geocoding returns nothing, the saved value is left untouched. No new raw server
  call is introduced (reuses existing helpers).

---

## Verification

### Unit / widget tests

- `test/home_map_no_reset_storm_local789b_test.dart` (**new**) — the core regression proof:
  - a burst of **20** external resets at a constant size disposes the tile provider **0 times**
    (the storm, and the tile cancellation, are gone);
  - camera nudges are **bounded** (≤ 2, not one-per-reset) — no loop;
  - on unmount the provider is disposed **exactly once** (normal cleanup).
- `test/home_map_grey_top_local789_test.dart` (updated) — a size change / banner-grow drives a
  camera nudge that heals the grid (observed as a `MapEventMove` sourced from the controller).
- `test/home_map_tiles_first_layout_local763_test.dart` (updated) — tiles requested on first settled
  layout with no gesture; a size change reloads.

Full suite vs clean baseline (my 5 files stashed at HEAD 642bf8a3):

| | passing | failing |
|---|---|---|
| clean baseline | 1195 | 8 |
| with fix | 1197 | 8 |

**Same 8 pre-existing failures in both, none map-related** — `storied_compat_screens_404_test.dart`
(Storied gateway), `storied_compat_guard_test.dart` (flags `services/failure_reporter.dart`, not my
file), `local109_swipe_e2e_test.dart` ×6 (`SocketException: Connection refused` to localhost — needs
a live backend). **Zero new failures**; +2 net new passing (the no-reset-storm cases).

### Device evidence — `docs/local789b/`

Cold start into Home with a saved custom location, **no gesture**:

- **iOS simulator** (iPhone 17 Pro, iOS 26.4):
  - `ios_boston_3s.png` — within 3 s, **whole map tiled** (Boston); banner re-resolved
    "Boston" → "Boston, Suffolk County, Massachusetts, United States".
  - `ios_hochiminh_resolved_3s.png` — whole map tiled (Ho Chi Minh City); banner re-resolved to
    "Ho Chi Minh City, Vietnam".
  - `ios_hochiminh_3s.png` — seeded with Michael's exact typo "Hi Chi Minh, Vietnam": whole map
    tiled; the banner keeps the typo (it does not resolve via Nominatim and the server `/geocode`
    is not deployed in this sandbox) — the intended **non-destructive** fallback.
- **Android emulator** (AVD `local715_test`, Android 14):
  - `android_boston.png` — **whole map tiled** (Boston), no gesture; banner re-resolved
    "Boston, MA" → "Boston, Suffolk County, Massachusetts, United States".
  - `android_boston_3s.png` + `android_boston_7s.png` — honest timeline: the emulator's cold-start +
    network tile latency exceeds 3 s to the first app frame (independent of this fix). The fix is
    proven by the whole viewport tiling with **no gesture and no permanent grey** — versus the
    real-device bug, which was permanent grey until a pinch.

The red "Audioura couldn't connect securely" banner in the shots is the backend being unreachable in
this sandbox (401/connection) — it does not affect OSM tiles, which load straight from
tile.openstreetmap.org.

Simulator and emulator were shut down after capture.

---

## Files changed

```
audio_tour_app/lib/widgets/first_layout_tile_layer.dart     (rewrite: stable layer + camera nudge)
audio_tour_app/lib/screens/home_screen.dart                 (pass controller; legacy-label re-resolve)
audio_tour_app/test/home_map_no_reset_storm_local789b_test.dart  (new regression test)
audio_tour_app/test/home_map_grey_top_local789_test.dart    (updated to nudge mechanism)
audio_tour_app/test/home_map_tiles_first_layout_local763_test.dart (updated to nudge mechanism)
docs/local789b/*.png                                        (cold-start screenshots)
```
