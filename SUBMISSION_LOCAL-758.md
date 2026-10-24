# SUBMISSION — LOCAL-758

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-758-organiser-builder-ux`
**Base:** subscribed @ `9a86e6e8` (`git merge-base --is-ancestor 9a86e6e8 HEAD` → 0)
**code_sha:** `8792a8dda553d5d66f62db241c382a4eff65c13a` (the LOCAL-758 fix commit; this submission note is the follow-up commit on top of it)

Michael, 2026-10-24 ~16:40 (iPhone, community "Salem TV show funs", builder with
the Salem Witch Trials Podcast feed):

> "Next to the stop name there are Up-Arrow and Square-with-a-hat buttons.
> Up-Arrow does not do anything. Square-with-a-hat button changes the name of the
> stop but I have no idea why… I do not see how a stop can be deleted… It has to
> be more intuitive what I can do with the stops."

The "square with a hat" was `Icons.delete_outline` — an icon-only **delete** with
no confirmation and no undo; the next stop slid up, so it looked like the name
changed. The up-arrow was disabled on stop 1 (Michael tried the first row).
Location was two raw number fields; LOCAL-754B's "map pin / Use my location /
address search" and "reorder by drag" were never built.

This ticket reworks **the builder screen only**
(`lib/screens/organiser_audio_tour_screen.dart`). The server, the
`/communities/<id>/build-audio-tour` call and its payload are unchanged.

---

## What shipped

1. **Choosing episodes is a checklist.** After Import, the feed's episodes show
   as a checklist — title + a `date · duration · size` line — with **Select
   none / Select all**. Nothing becomes a stop until it is ticked and **Add
   selected** is tapped; ticked episodes become stops in feed order.
2. **Each stop is a collapsible card.** Collapsed shows the number, the name and
   a location status (`✓ <place>` or "Location needed"). Expanded shows the
   editors.
   - **Drag to reorder** via a `ReorderableListView` drag handle; the dead
     up-arrow is removed.
   - **Remove stop** is a labelled text button (not an icon) with a 5-second
     **Undo** SnackBar that restores the same stop object at the same position.
   - **Stop name** shows "Episode: …" beneath it and a **Use episode title**
     button to restore the original name after an edit.
   - **Location:** **Use my location** (geolocator), **Pick on map** (a
     full-screen `flutter_map`; tap to drop the pin, "Use this pin" to confirm),
     and **Search address** (OpenStreetMap **Nominatim** — the same geocoder
     Home's place search uses). The chosen place shows as a label + a small
     map preview; raw lat/lng live under **Advanced**. Optional text defaults to
     the episode's show notes.
3. Every icon carries a text label or a tooltip; the destructive action reads
   "Remove stop".
4. **Publish validation names the stop:** e.g. `Stop 2 'The Trial of George
   Jacobs' needs a location for a walking tour.`

### Address search — which resolver
Reuses **OpenStreetMap Nominatim** (`nominatim.openstreetmap.org/search`), the
exact service `home_screen.dart`'s place lookup already uses. No new server
endpoint; no map-delivery/area resolver call added.

### Files
- `lib/screens/organiser_audio_tour_screen.dart` — the rebuilt builder + the
  full-screen `_MapPickerScreen`. Adds a test-only tile-provider seam
  (`debugBuilderTileProviderOverride` / `TransparentTileProvider`) so the maps
  render in widget tests without any network; production uses the real
  `NetworkTileProvider` unchanged.
- `lib/services/builder_location_provider.dart` — **new.** An injectable
  `BuilderLocationProvider` (geolocator + Nominatim) with a
  `FakeBuilderLocationProvider` so "Use my location" and address search are
  testable with no device and no network.
- `lib/services/communities_models.dart` — `CommunityEpisode` gains optional
  `date`, `duration`, `sizeBytes`, `description` (parsed defensively; server
  unchanged) and a `metaLine` getter for the checklist.

---

## Red tests (fail on `9a86e6e8`, pass after the fix)

`audio_tour_app/test/organiser_builder_ux_local758_test.dart` — 9 widget tests
driving the **real** `OrganiserAudioTourScreen` with a `MockClient` (feed import)
and a `FakeBuilderLocationProvider`:

1. seeded episodes appear as a **checklist**, nothing is a stop yet
2. importing a feed adds its episodes to the **checklist**, not stops
3. only **ticked** episodes become stops, in feed order
4. **Remove** shows a labelled button and an **Undo** that restores the same
   stop at the same position
5. **Use episode title** restores the stop name after an edit
6. **Use my location** fills the stop from the (fake) provider
7. **address search** fills the stop from the (fake) geocoder
8. publish **validation names the stop** that needs a location
9. **drag reorder** is available (`ReorderableListView` + drag handles)

**Why they are red on the base:** the suite targets the new API that does not
exist at `9a86e6e8` — the `OrganiserAudioTourScreen(locationProvider: …)`
parameter and the `builder_location_provider.dart` library — so it fails to
compile (and therefore fails) against the base screen. Against the fix:

```
$ flutter test test/organiser_builder_ux_local758_test.dart
00:01 +9: All tests passed!
```

---

## Verification

- **`flutter analyze`** on every touched file — no issues:
  `lib/screens/organiser_audio_tour_screen.dart`,
  `lib/services/builder_location_provider.dart`,
  `lib/services/communities_models.dart`,
  `test/organiser_builder_ux_local758_test.dart`,
  `integration_test/local758_builder_screenshot_test.dart`,
  `test_driver/local758_screenshot_driver.dart` → **"No issues found!"**
- **Full suite:** `flutter test` → `+1019 -7`. Baseline (`9a86e6e8`) is
  `+1010 -7`; the +9 are this ticket's new tests. The **7 failures are
  pre-existing and environment-dependent**, unchanged by this work:
  - 6× `test/local109_swipe_e2e_test.dart` — `SocketException` (needs the live
    swipe server on localhost);
  - 1× `test/storied_compat_screens_404_test.dart` — needs a live Storied
    gateway (confirmed still failing with this ticket's `lib/` changes stashed,
    i.e. on the base screen).
  No new failures introduced.

---

## Live test — iOS simulator (screenshots)

Captured on the **iOS Simulator** (iPhone 17) — never a real phone — by driving
the real screen through each state:

```
flutter drive \
  --driver=test_driver/local758_screenshot_driver.dart \
  --target=integration_test/local758_builder_screenshot_test.dart \
  -d <iPhone 17 simulator id>
→ All tests passed.
```

The run uses a seeded community and `FakeBuilderLocationProvider` (deterministic
location), with real OpenStreetMap tiles for the map preview/picker. **No server
was involved; budget $0; no database table was written** (no `DELETE FROM
audio_tours`, no row-count change anywhere). Simulator shut down afterwards.

`audio_tour_app/screenshots_local758/`:

| file | state |
|------|-------|
| `01_checklist.png` | episode checklist — Select none/all, `date · duration · size`, "Add selected" disabled until a tick |
| `02_collapsed_cards.png` | stops after "Add selected" — number, name, "Stop N · Location needed", drag handle |
| `03_expanded_card.png` | one stop open — name + "Episode: …"/"Use episode title", Use my location / Pick on map / Search address, Advanced |
| `04_located_card.png` | after "Use my location" — green ✓ + place label + OSM mini-map preview |
| `05_map_picker.png` | full-screen "Pick on map" — OSM map, dropped pin, "Use this pin" |
| `06_undo_snackbar.png` | "Remove stop" → "Removed …" Undo SnackBar |

---

## Constraints honoured
- Branch created from `subscribed` @ `9a86e6e8`; `git merge-base --is-ancestor
  9a86e6e8 HEAD` → 0. Never branched from `origin/*`.
- Builder screen only; **`home_screen.dart` untouched** (LOCAL-757 owns it).
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
- Committed named files only (no `git add -A`); the simulator-build change to
  `ios/Podfile.lock` was reverted, not committed.
