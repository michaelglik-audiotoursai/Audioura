# SUBMISSION — LOCAL-665: One search button

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-665-one-search` (based on `subscribed` @ `18cdcc89`)
**Version:** `2.4.7+33`

## Why
Michael (2026-10-10): "I sometimes confuse which button to press for the tour
search: flag (the right one) or arrow-glass for location search. Can we merge
them somehow, because the format is very different and by the format we can
understand what the listener is looking for."

The Home AppBar used to carry two buttons:
- `Icons.tour` → `_showTourSearchDialog` (share code + tour-name search)
- `Icons.search` → `_showLocationSearchDialog` (place search, moves the map)

## What changed
One button, one dialog, dispatch by format.

### 1. New pure, UI-free dispatcher — `lib/utils/search_dispatch.dart`
The decision of *what to do* with the typed text lives in a Flutter-free util so
it can be unit-tested directly:
- `SearchKind { shareCode, coordinates, text }`
- `classifySearchInput(raw)` — applies the fixed priority order:
  1. **share code** (reuses the existing `extractShareCode` from
     `share_code.dart`: bare code, full share message, or share link),
  2. **coordinates** (`parseCoordinates`, strict `"lat, lng"` with range checks
     so "Route 66" / a lone number are **not** mistaken for coordinates),
  3. **text** otherwise.
- `TextSearchOutcome { toursAndPlace, toursOnly, placeOnly, nothing }` +
  `resolveTextSearch(tourCount, placeFound)` — the concurrent text-search
  outcome table.

### 2. `lib/screens/home_screen.dart`
- The two AppBar buttons are replaced by **one** `IconButton(Icons.search,
  tooltip: 'Search')` → `_showSearchDialog`.
- `_showSearchDialog`: one `TextField`, hint **"Share code, tour name, or
  place"**, actions **Cancel / Use Current Location / Search** — the same visuals
  as the old shared dialogs (title + single field + buttons), plus the existing
  recent-locations list.
- `_dispatchSearch(query)` runs `classifySearchInput` and acts:
  - **(a) share code** → `_dispatchShareCode`: resolve via the existing
    `_resolveShareCode`, then open the **same** found-tour dialogs the map uses
    (`_presentFoundTours`). If unknown, show
    *"No tour with that code on this server (check Settings → server)"* and
    **STOP** — no fall-through to a place search.
  - **(b) coordinates** → `_useCustomLocation(LatLng(...))` moves the map.
  - **(c) otherwise** → `_dispatchTextSearch`: runs the tour-name search and the
    place lookup **concurrently** (`Future.wait([_searchTours, _geocodeLocation])`),
    then `resolveTextSearch`:
    - tours **and** place → `_presentFoundToursWithPlace`: the shared found-tour
      dialogs **plus** an extra action *"Show &lt;place&gt; on the map"*.
    - tours only → `_presentFoundTours`.
    - place only → `_useCustomLocation` (today's location behaviour).
    - neither → *"Nothing found for '&lt;text&gt;'"*.
- Underlying functions kept intact: `_searchTours`, `_geocodeLocation`,
  `_resolveShareCode`, `_presentFoundTours`, `_useCustomLocation`,
  `_mapController.move`.
- Removed the now-dead `_showTourSearchDialog`, `_showLocationSearchDialog`,
  `_searchAndUseLocation`.

### 3. Version
`pubspec.yaml` bumped `2.4.6+32` → `2.4.7+33`.

### 4. No server change, no paid API calls
The place lookup is the app's existing OpenStreetMap Nominatim geocoder
(`_geocodeLocation`), unchanged.

## Tests — `test/search_dispatch_test.dart` (23 tests, all pass)
Covers each case the ticket named:
- **a code** — bare, full share message, share link, with whitespace.
- **coordinates** — `"42.36, -71.06"`, no-space comma, integer pair, signed.
- **a name** — plain name, multi-word, wildcard; `"Route 66"` / a lone number /
  `"Brooklyn"` stay **text**, not coordinates/code.
- `parseCoordinates` range + shape guards (out-of-range lat/lng, 3 numbers, bare
  number rejected).
- **the concurrent outcome table** (name with tours+place / tours only / place
  only / nothing) via `resolveTextSearch`.

## Verification
- `flutter test test/search_dispatch_test.dart` → **23/23 pass**.
- `flutter analyze lib/utils/search_dispatch.dart test/search_dispatch_test.dart`
  → **No issues found**.
- `flutter analyze lib/screens/home_screen.dart` → **no issues in the changed
  code**; the file's total analyzer issues went **334 → 294** (removing the two
  dead dialog methods cleared ~40 pre-existing lints; the remainder are
  pre-existing and untouched).
- `flutter test` (full suite) → **292 pass**. The only failures (6) are in
  `test/local109_swipe_e2e_test.dart` — live-"real server" / offline-queue E2E
  tests that fail with `SocketException: Connection refused` because no backend
  is running in this environment. They are unrelated to this change (swipe /
  offline queue, not Home search) and fail identically without it.
- `flutter build ios --no-codesign` → **✓ Built build/ios/iphoneos/Runner.app
  (37.3MB)**.
- Did **not** install to the phone (LEAD does).

## Files
- `audio_tour_app/lib/utils/search_dispatch.dart` (new)
- `audio_tour_app/test/search_dispatch_test.dart` (new)
- `audio_tour_app/lib/screens/home_screen.dart`
- `audio_tour_app/pubspec.yaml`
