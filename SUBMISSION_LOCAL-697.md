# SUBMISSION — LOCAL-697

**Branch:** LOCAL-697-search-relocate (from `subscribed` = ac7f1adf)
**Agent:** Mac Mini Kiro
**Build:** 2.4.18+54 (bumped from +53)

## Problem
Michael (Pixel-4, 2026-10-15): searching **'Nice, France'** opened the
**'Select Tours (10 available)'** dialog, and after Cancel the app asked
**'Do you want to relocate to Nice France?'**. This is a regression of the old
pre-LOCAL-665 behaviour.

## Rule (LEAD D662)
When the text search finds a **PLACE**, move the map there **immediately**
(Home view of that area, same as before LOCAL-665) — **no tours dialog, no
confirmation question**. A small snackbar may offer `N tours named "<query>"
— Show` when tour names ALSO matched. The tours dialog appears **only** when NO
place is found but tour names match. Share codes and coordinates are unchanged.

## Behaviour table (now)
| Search result        | Action                                                        |
|----------------------|---------------------------------------------------------------|
| place + tours        | relocate immediately **+** snackbar `N tours named "<q>" — Show` |
| place only           | relocate                                                      |
| tours only           | tours dialog (as today)                                       |
| neither              | `Nothing found for "<q>"`                                     |

## Changes
- **`audio_tour_app/lib/screens/home_screen.dart`**
  - `_dispatchTextSearch`: `toursAndPlace` case now **awaits**
    `_presentFoundToursWithPlace`.
  - `_presentFoundToursWithPlace` rewritten: it **relocates first**
    (`await _useCustomLocation(place, placeName)` → the normal Home view, which
    moves the map via `_mapController.move` and loads nearby tours), then shows a
    small snackbar `N tours named "<query>"` with a single **Show** action that
    opens the usual found-tours dialog. No dialog is shown up front and there is
    no 'relocate?' confirmation. `placeOnly` already relocated (unchanged);
    `toursOnly`/`nothing` unchanged.
- **`audio_tour_app/lib/utils/search_dispatch.dart`**
  - `TextSearchOutcome` doc comments updated to state the D662 intent (a found
    place always wins / relocate; dialog only when place is absent). The pure
    `resolveTextSearch` mapping itself was already correct and is unchanged.
- **`audio_tour_app/test/search_dispatch_test.dart`**
  - Outcome-table group reworded to the D662 intent and extended: place+tours →
    toursAndPlace (relocate+snackbar), place+single-tour → toursAndPlace,
    tours only → toursOnly (dialog), place only → placeOnly (relocate),
    neither → nothing.
- **`audio_tour_app/pubspec.yaml`** — build number 53 → 54.

## Verification
- `flutter test test/search_dispatch_test.dart` → **All tests passed!** (25 tests,
  including the 5 D662 outcome-table cases).
- `flutter analyze` on the three changed files → **no errors**; no new issues in
  the edited regions (remaining output is pre-existing `info`/`warning` lints
  elsewhere in home_screen.dart).
- Not field-tested on a device (unproven). The pure outcome logic is unit-tested;
  the widget relocation path reuses the existing, already-shipping
  `_useCustomLocation` behaviour.

## Base check
`git merge-base --is-ancestor ac7f1adf HEAD` → exit 0 (correct base).
