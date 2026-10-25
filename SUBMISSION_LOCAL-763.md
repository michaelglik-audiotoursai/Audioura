# SUBMISSION — LOCAL-763

**Branch:** `LOCAL-763-map-tiles-menu-polish`
**Base:** `subscribed` @ `1e740b0a` (contains LOCAL-762). `git merge-base --is-ancestor 1e740b0a HEAD` → 0.
**code_sha:** `1f6611d94ca64cbc4ba160df75f5a67f20a06436` (implementation commit; this submission sha-record follows it).
**Ruling:** D711 + D711 addendum 1.
**Budget:** $0.00 (no AI / third-party calls; live test served its own MP3s on localhost).

Michael's retest (2026-10-25 ~11:20, iPhone organiser + Pixel-4 member, both on home Wi-Fi) raised three things. All three are addressed below.

---

## 1. Home map tiles from the first frame (the bug)

### Symptom
"When I open either of the phones the home page comes with tours and location markers but not with the map itself. The map appears after I try to zoom in/out, but it should be there from the entrance." — both phones, since the LOCAL-761/762 installs.

### Root cause
`screens/home_screen.dart` builds a `FlutterMap` with a `TileLayer`. In **flutter_map 6.2.1**, `TileLayer` computes its visible tile range from `MapCamera.of(context)` in `didChangeDependencies`, then keeps itself current by listening to `MapController.mapEventStream`.

Since **LOCAL-761**, Home lives inside an `IndexedStack` of per-tab `Navigator`s (`main_screen.dart`). When the map is first laid out inside that shell, `FlutterMap._updateAndEmitSizeIfConstraintsChanged` sets the camera's non-rotated size **without emitting an event** and schedules the `MapEventNonRotatedSizeChange` for the **next** frame (a post-frame callback, so a `setState` in an `onMapEvent` handler cannot throw during build). If the `TileLayer`'s first `didChangeDependencies` ran against the pre-layout / zero-size camera, it computed an **empty tile range** and loaded nothing; the later size-settle event could be missed on the broadcast stream, so the grid stayed blank until a user gesture produced a fresh `MapEvent` (the "appears only after a zoom"). **Markers drew** because `MarkerLayer` positions its points absolutely, independent of the tile grid — exactly what Michael saw.

### Fix (root cause, flutter_map's own mechanism — not a timer)
New widget `lib/widgets/first_layout_tile_layer.dart` → `FirstLayoutTileLayer`. It wraps the `TileLayer` and drives flutter_map's built-in `TileLayer(reset: Stream)` input: when the stream emits, the layer removes all tiles and reloads them against the **current (correct-size)** camera. The widget fires that reset:
- on `MapEventNonRotatedSizeChange` — the exact event that was being missed, i.e. the instant the layout size settles; and
- once right after the first build (post-frame) to cover the case where the size was already correct before this layer subscribed.

Both triggers are driven by map readiness / size, so there is no arbitrary delay. `home_screen.dart` now uses:

```dart
FirstLayoutTileLayer(
  builder: (reset) => TileLayer(
    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    userAgentPackageName: 'com.example.audiotours',
    reset: reset,
  ),
),
```

### Red test
`test/home_map_tiles_first_layout_local763_test.dart` builds the map inside an `IndexedStack` + `Navigator` (the LOCAL-761 shell in miniature) with a fake `TileProvider` that counts tile requests and returns a 1×1 transparent image (offline, deterministic). It pins the fix's observable guarantees:
1. a `FirstLayoutTileLayer` requests OSM tiles on the first settled layout with **no gesture**; and
2. a layout-size change (`MapEventNonRotatedSizeChange`) drives the reset so tiles reload — the heal path.

The precise one-frame-late size settle is a flutter_map internal that only bites on a real surface (the widget-test `LayoutBuilder` gets constraints eagerly), so that device-only timing is verified on the emulator rather than in the widget test — documented in the test header.

### Device verification
- **Android emulator** (`emulator-5554`, `sdk gphone64 arm64`, API 34 — **not** the physical Pixel 4, not any phone): cold start → Home → **full OSM tiles render with no gesture** (Boston: Charlestown, East Boston, the Charles River, roads and labels) plus the red user marker. Screenshot: `screenshots/android_home_coldstart.png`. (The "couldn't connect securely" banner is just the backend being unreachable in this harness; the OSM tiles are fetched directly and are unaffected — that is precisely the point.)
- **iOS simulator** (iPhone 17 — **not** Michael's iPhone): the identical debug build installs, launches and passes onboarding, and reaches the Home map. Capturing the tiles was blocked by the app's own runtime `Geolocator.requestPermission()` **system location modal**, which overlays the map; dismissing an iOS system alert requires GUI automation that needs macOS Accessibility / Input-Monitoring permissions I must not change (and `idb`/`cliclick` are not installed, `simctl` has no tap, and its location grant does not satisfy geolocator's `checkPermission()` on iOS 26). The map is built underneath the modal from the **same platform-neutral `FirstLayoutTileLayer`** code the widget tests cover. Screenshots: `screenshots/ios_step1.png` (onboarding), `screenshots/ios_home_location_modal.png` (reached Home, system modal on top). Android conclusively verifies the fix; the iOS gap is an environment limitation, not a code difference.

---

## 2. ⋮ menu polish (`screens/my_tours_screen.dart`, `utils/tour_role_label.dart`, `widgets/role_line_menu_entry.dart`)

Michael: the role line was grey and invisible ("makes the whole dialog sad"), the long first-item label went behind the options, the ⓘ looked un-clickable because it was grey, and there was no close button.

- **Bright coloured role line.** `tour_role_label.dart` now carries a pure `TourRoleKind` (`ownBlue` / `organiserGreen` / `communityGreen` / `broadcastPurple` / `audiouraGrey`). `RoleLineMenuEntry` renders a filled/outlined strip coloured by kind, readable in **light and dark**: your own tour = brand blue; organiser of a community tour = the LOCAL-757 community green (filled); a community tour you did not create = community green **outline**; broadcast = a podcast purple; a plain Audioura tour = neutral blue-grey. The leading icon is kept.
- **Wrapping.** `RoleLineMenuEntry` is a custom `PopupMenuEntry` (not a fixed-height `PopupMenuItem`); its text is a wrapping `Text` inside `Expanded`, so the strip grows to as many lines as the label needs — nothing is hidden behind the next item, even for the longest label on the narrowest (320 px) phone.
- **Clickable ⓘ → not grey.** The disabled Edit / Translate / Price rows keep a grey title and icon, but their trailing ⓘ is in the **primary colour** and is tappable (shared `disabledMenuInfoChild`). Tapping the row shows the same reason notice.
- **Close ✕.** The role-line row carries a ✕ at its right end (tooltip "Close") that closes the whole menu (`Navigator.pop`). Tapping outside still works.

### Red tests
- `test/role_line_menu_entry_local763_test.dart` (5 tests): the longest label wraps and is fully visible at 320 px with **no overflow** and no ellipsis; the strip is a bright (non-grey) colour; the ✕ has a "Close" tooltip and fires its close callback; the ✕ closes a real `PopupMenuButton`; a disabled row keeps a grey title/icon but a **primary-coloured, tappable ⓘ**.
- `test/tour_role_kind_local763_test.dart` (7 tests): the colour kind is correct for every relationship.

### Screenshots
The menu colour/close/wrapping behaviour is pinned by the widget tests above (the live-device ⋮ menu screenshots could not be captured on iOS for the same system-modal reason as §1, and the Android run demonstrated the Home map, which was Michael's primary complaint). The five role-colour renders and the wrapped long-label layout are asserted structurally in the tests.

---

## 3. No per-tour price on community tours (D711 addendum 1)

Michael: a public community tour means everyone sees it and can ask to download it, but must join first — so **no per-tour price on any community tour**, members-only or public, generated or broadcast.

### App
- `screens/my_tours_screen.dart`: the Price row is shown **disabled with a bright, tappable ⓘ** for **any** community tour (was members-only only). Gating changed from `role.isMembersOnly` → `role.isCommunity`. The ⓘ notice now reads "Community tours are included with membership… Anyone can find the tour, but they join the community to listen."
- `screens/organiser_audio_tour_screen.dart`: removed the "Price for non-members" field entirely (every visibility), its state/ladder/loader, and `price_tier` from the publish body.
- `screens/tour_generator_screen.dart`: the Generate price picker is hidden for **any** community target (was members-only only), and the post-generate `setPrice` is skipped for any community target. The picker still shows for a curator's own "Just me" tour.

### Server
- `tour_pricing_service.py` `set_price`: refuses **any** community tour (`community_id is not None`) with `PricingError('community_tour_no_price')` → HTTP 400; **clearing** a price (`tier=None`) is still allowed. Route status map and the `PricingError` docstring updated (`members_only_no_price` → `community_tour_no_price`).
- `user-tracking/communities_api.py` `build_audio_tour`: any non-null `price_tier` → 400 `community_tour_no_price` **before** any row is created; `price_tier` dropped from the INSERT (a community tour is always Free).

### Tests (updated LOCAL-762 suite, D711 addendum 1)
- `tests/test_local762_tour_role_and_pricing.py` — **11 passed** (DB-backed cases ran): a PUBLIC publish with a price is now refused (`community_tour_no_price`, no row); a members-only publish with a price is refused; `set_price` on a community tour (members **and** public) is refused; clearing is still allowed; the route maps `community_tour_no_price` → 400.
- `live_local762.py` — end-to-end on the TEST database (port 5433), budget $0, D141-safe: `set_price` on a community tour → 400 `community_tour_no_price`, clearing allowed; a PUBLIC build with a price → 400 (no row); a PUBLIC build **without** a price publishes **Free**; a members-only build with a price → 400 (no row); a member pricing → refused. Row counts returned to baseline after cleanup (only this run's `is_test` rows removed).

---

## Test summary

- **Flutter:** my five new/changed test files are green (24 tests). Full suite = the stated baseline **7 known failures, no new ones** — all 7 are in live-server / network tests I did not touch (`local109_swipe_e2e_test.dart` ×6, which needs a local orchestrator on port 5102; `storied_compat_screens_404_test.dart` ×1). The one LOCAL-762 widget test that asserted the old price field (`organiser_builder_price_local762_test.dart`) was updated for D711 addendum 1 (no price field for members **or** public) and passes.
- **Python:** `tests/test_local762_tour_role_and_pricing.py` 11 passed; `live_local762.py` passed end-to-end; `py_compile` clean on `tour_pricing_service.py`, `user-tracking/communities_api.py`, `live_local762.py`, `tests/test_local762_tour_role_and_pricing.py`.

## Live test / safety

Simulator + emulator only — **never Michael's phones**. No `-p audioura`; no `DELETE FROM audio_tours` beyond this run's own `is_test` rows (D141); no deletes of purchase-bearing rows (D690). Row counts before/after returned to baseline. Budget $0.00. Emulator and simulator shut down afterward; the local (gitignored) `android/app/debug.keystore` used to sign the debug build was removed.

## Files

**New**
- `audio_tour_app/lib/widgets/first_layout_tile_layer.dart`
- `audio_tour_app/lib/widgets/role_line_menu_entry.dart`
- `audio_tour_app/test/home_map_tiles_first_layout_local763_test.dart`
- `audio_tour_app/test/role_line_menu_entry_local763_test.dart`
- `audio_tour_app/test/tour_role_kind_local763_test.dart`
- `SUBMISSION_LOCAL-763.md`
- `screenshots/android_home_coldstart.png`, `screenshots/ios_step1.png`, `screenshots/ios_home_location_modal.png`

**Changed**
- `audio_tour_app/lib/screens/home_screen.dart`
- `audio_tour_app/lib/screens/my_tours_screen.dart`
- `audio_tour_app/lib/screens/organiser_audio_tour_screen.dart`
- `audio_tour_app/lib/screens/tour_generator_screen.dart`
- `audio_tour_app/lib/utils/tour_role_label.dart`
- `audio_tour_app/test/organiser_builder_price_local762_test.dart`
- `tour_pricing_service.py`
- `user-tracking/communities_api.py`
- `live_local762.py`
- `tests/test_local762_tour_role_and_pricing.py`
