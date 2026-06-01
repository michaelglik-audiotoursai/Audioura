# Mac Mini Assignment Instructions
## iOS Development Task Execution

---

# T: 05/2026 - A#53 — Build v1.2.9+52 (A#51 Map AppBar + A#52 Per-Stop Map Focus)

**Goal:** Build v1.2.9+52. Includes A#51 (map icon moved to Tour Player AppBar) and A#52 (per-stop map focus — map opens centered on the currently playing stop). Both fully approved. A#51 was staged but never built. A#52 passed two Claude.AI review rounds (NF1 + NF2 fixed). This is the first build of both.

**Scripts:** `copy_ios_fixes.sh` (20 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#50 (v1.2.9+50):**
- ✅ **tour_player_screen.dart** — A#51: map icon (`Icons.map`) moved from Listen Page tour cards to Tour Player AppBar. `_hasMap` bool + `_checkForMap()` in `initState` — reads `audio_1.txt` for `Coordinates:` regex. Map button only shown when `_hasMap == true`. A#52: `_currentStop` field (default 1). `_getCurrentStop()` — two-pass JS: pass 1 finds `!paused` audio (currently playing), pass 2 finds max `currentTime` (most recently active), default 1. Map button is async: calls `_getCurrentStop()`, `setState(_currentStop)`, guards `if (!mounted)`, pushes `TourMapScreen(focusStopIndex: stop)`.
- ✅ **my_tours_screen.dart** — A#51: map detection code fully removed (map icon now lives in Tour Player AppBar, not Listen Page). `_tourHasMap` state map removed. `_detectMapTours()` removed.
- ✅ **tour_map_screen.dart** — A#52: `focusStopIndex` (int?) parameter added. `_focusPoi()` — returns POI by exact index match, fallback nearest-by-GPS. `_fitBounds({bool forceFitAll = false})` — when `!forceFitAll && focusStopIndex != null` fits `[user, focusPoi]`; otherwise fits all POIs + user. AppBar "Fit all stops" calls `_fitBounds(forceFitAll: true)`. AppBar title shows `"Tour Title — Stop N"` when focused.
- ✅ **pubspec.yaml** — version bumped to 1.2.9+52

**NF1 fix (two-pass JS heuristic):** Single-pass `!paused || currentTime > 0` was wrong after sequential playback — hits stop 1 even when stop 3 is active. Two-pass (prefer `!paused`, fallback max `currentTime`) is correct.

**NF2 fix (Fit all stops):** `forceFitAll=true` on AppBar button always shows all POIs regardless of `focusStopIndex`. Default `forceFitAll=false` honors focused stop on initial map open.

**Post-approval backlog (not blocking this build):**
- NF6: `if (forceFitAll) _fittedWithLocation = true;` at top of `_fitBounds` — prevents GPS first-fix from overriding user's explicit "fit all"
- NF7: `poi.index == next?.index` safer than `poi == next` identity comparison
- NF5: `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)` (Flutter 3.27+ deprecation)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (20 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 20 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: A#51 Map Icon in Tour Player AppBar

1. Go to Listen Page
2. **Expected**: Walking tours do NOT show a green map icon in the card trailing row (A#51 removed it from here)
3. Tap a walking tour → Tour Player opens
4. **Expected**: Map icon (🗺) appears in the Tour Player AppBar (top right)
5. Museum tours (no coordinates) → Tour Player AppBar should NOT show map icon
6. Tap the map icon → full-screen map opens

## Step 5 — Test: A#52 Per-Stop Map Focus

**Test 1: No audio started**
1. Open a walking tour in Tour Player (do not press play)
2. Tap map icon
3. **Expected**: Map opens, Stop 1 marker is orange, all POIs visible

**Test 2: Play through stops**
1. Play stop 1 → let it finish → stop 2 starts → let it finish → stop 3 starts
2. While stop 3 is playing, tap map icon
3. **Expected**: Map opens with Stop 3 orange, map fits user location + Stop 3
4. AppBar title shows `"[Tour Name] — Stop 3"`

**Test 3: Pause mid-stop**
1. Play to stop 3, pause it
2. Tap map icon
3. **Expected**: Stop 3 orange (highest `currentTime` wins)

**Test 4: Fit all stops button**
1. Open focused map (Stop 3 orange)
2. Tap "Fit all stops" in AppBar
3. **Expected**: All numbered markers visible, map zooms out to show all POIs

**Test 5: Center on me**
1. Tap "Center on my location"
2. **Expected**: Map jumps to GPS dot at zoom 15

**Test 6: Museum tour (if available)**
1. Open a museum tour (only 1 POI with coordinates)
2. Tap map icon
3. **Expected**: 1 POI shown, Stop 1 orange, no crash

## Step 6 — Copy Results and Return

```
echo "Assignment 53 Results:" > ~/Desktop/a53_results.txt
echo "Date: $(date)" >> ~/Desktop/a53_results.txt
echo "Version: 1.2.9+52" >> ~/Desktop/a53_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a53_results.txt
echo "A51: Map icon in Tour Player AppBar (not Listen Page): [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A51: Map icon absent on museum tours: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A52: No audio - Stop 1 orange, all POIs visible: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A52: Playing stop 3 - Stop 3 orange on map open: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A52: Paused stop 3 - Stop 3 orange (max currentTime): [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A52: Fit all stops shows all markers: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "A52: AppBar title shows Stop N: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "GPS blue dot visible: [YES/NO]" >> ~/Desktop/a53_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a53_results.txt

cp ~/Desktop/a53_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 53 complete. v1.2.9+52. Build: [SUCCESS/FAILED]. A51 map icon in AppBar: [YES/NO]. A51 absent on museum: [YES/NO]. A52 Stop 1 default: [YES/NO]. A52 Stop 3 focused: [YES/NO]. A52 Fit all stops: [YES/NO]. AppBar title Stop N: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#50 — Walking Tour Map Feature (v1.2.9+50)

**Goal:** Build v1.2.9+50. New `tour_map_screen.dart` — full-screen flutter_map with numbered POI markers, GPS blue dot, dotted arrow to nearest POI, tap-marker bottom sheet (name/type/address). Green map icon on Listen page tour cards, shown only for tours with parseable `Coordinates:` in `audio_1.txt`. Claude IO APPROVED. Q3 fix applied: `_fittedWithLocation` flag — map re-fits once on first GPS fix to include user location.

**Scripts:** `copy_ios_fixes.sh` (20 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#49c (v1.2.9+49):**
- ✅ **tour_map_screen.dart** (NEW) — `TourMapScreen`: reads `audio_N.txt` files, parses `Coordinates:`, `Type/Specialty:`, `Address:`, POI name (line 1). Shows numbered markers on `flutter_map` (OpenStreetMap tiles). GPS blue dot via `geolocator`. Dotted polyline to nearest POI (orange marker). Tap marker → bottom sheet with name/type/address. AppBar: "Center on my location" + "Fit all stops" buttons. **Q3 fix**: `_fittedWithLocation = false` field — stream listener calls `_fitBounds()` once on first GPS fix, never again.
- ✅ **my_tours_screen.dart** — Added `_tourHasMap` state map. `_detectMapTours()` called after `_loadTours()` — reads `audio_1.txt` per tour, checks for `Coordinates:` regex. Green map icon (`Icons.map`) in tour card trailing row, shown only when `_tourHasMap[index] == true`.
- ✅ **pubspec.yaml** — version bumped to 1.2.9+50
- ✅ **copy_ios_fixes.sh** — now copies **20 files** (added `tour_map_screen.dart`)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (20 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 20 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: Map Icon on Listen Page

1. Go to Listen Page
2. **Expected**: Walking tours show a green map icon (🗺) in the trailing row
3. Museum tours (no coordinates) should NOT show the map icon
4. Tap the map icon on a walking tour
5. **Expected**: Full-screen map opens with numbered blue markers at POI locations
6. Map initially fits POI markers only → once GPS acquired, re-fits to include user location (once only)
7. Tap any marker → bottom sheet shows POI name, type, address
8. Confirm GPS blue dot appears (requires location permission)
9. Confirm dotted line points to nearest marker (orange)
10. Tap "Fit all stops" → all markers visible
11. Tap "Center on my location" → map centers on GPS dot
12. **⚠️ CRITICAL**: If you have a translated walking tour (Russian etc.) — confirm green map icon appears on it too (verifies `Coordinates:` keyword not translated)

## Step 5 — Copy Results and Return

```
echo "Assignment 50 Results:" > ~/Desktop/a50_results.txt
echo "Date: $(date)" >> ~/Desktop/a50_results.txt
echo "Version: 1.2.9+50" >> ~/Desktop/a50_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a50_results.txt
echo "Map icon visible on walking tours: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Map icon absent on museum tours: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Map opens with numbered markers: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Tap marker shows bottom sheet: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "GPS blue dot visible: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Dotted arrow to nearest POI: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Map re-fits on first GPS fix: [YES/NO]" >> ~/Desktop/a50_results.txt
echo "Translated tour map icon visible (if tested): [YES/NO/NOT_TESTED]" >> ~/Desktop/a50_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a50_results.txt

cp ~/Desktop/a50_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 50 complete. v1.2.9+50. Build: [SUCCESS/FAILED]. Map icon on walking tours: [YES/NO]. Map opens with markers: [YES/NO]. Bottom sheet on tap: [YES/NO]. GPS dot: [YES/NO]. Arrow to nearest: [YES/NO]. Map re-fits on GPS: [YES/NO]. Translated tour map icon: [YES/NO/NOT_TESTED]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#49c — Spinner During Translation Wait + Q1 Polish (v1.2.9+49)

**Goal:** Build v1.2.9+49. A#49b (v1.2.9+47) was APPROVED by Claude IO. Q2 (no spinner during 21s translation wait) recommended fix applied. Q1 optional polish applied in same patch. Bug fix: Q1+Q2 patch accidentally hit `_generateTour` catch block (same setState pattern, `wantsEnglish` out of scope there) — restored to unconditional reset.

**Scripts:** `copy_ios_fixes.sh` (19 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#49b (v1.2.9+47):**
- ✅ **Q1** — `_autoDownloadAndPlay` Step 7 setState: `_isGenerating = !wantsEnglish` (keeps spinner running if translation still pending). `_progress = ''` gated on `wantsEnglish` (avoids theoretical flicker)
- ✅ **Q2 success** — `_pollAndAutoDownload` success branch (line 288): `setState(() { _isGenerating = false; _progress = ''; })` — spinner stops when Russian player opens
- ✅ **Q2 failure** — `_pollAndAutoDownload` failure branch (line 302): `setState(() { _isGenerating = false; _progress = ''; })` — spinner stops when translation fails
- ✅ **Bug fix** — `_generateTour` catch block (line 243) was incorrectly patched with `_isGenerating = !wantsEnglish` — `wantsEnglish` is not in scope there. Restored to `_isGenerating = false; _progress = '';`
- ✅ `pubspec.yaml` — version bumped to 1.2.9+49

**Result matrix:**
- Russian only + translation success → spinner runs continuously → Russian player opens → spinner stops ✔
- Russian only + translation fail → spinner runs → orange snackbar → spinner stops, progress cleared ✔
- English only → spinner stops at extraction complete, English player opens immediately ✔
- English + Russian → spinner stops at extraction complete, English player opens, Russian added to Listen Page ✔

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (19 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 19 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: Generate Tour in Russian Only

1. Go to Tour Generator tab
2. Type: `Walking tour in Nice, France`
3. Deselect English, select Russian only → **Generate Now**
4. Wait for generation (~2 min)
5. **Expected**: Spinner runs continuously (NOT stopped) + "Preparing translation..." label
6. Wait ~21s more for translation
7. **Expected**: Russian player opens automatically + spinner stops
8. **Expected**: Green snackbar "RU version added to My Tours"
9. Go to Listen Page → **1 tour only (Russian)**
10. Check log:
    - `TOUR: Suppressing English auto-play — waiting for translation`
    - `TOUR: Removed English fallback (tour_id <N>) — 1 entry pruned`

**Test: Russian only, translation FAILS (block port 5030 or use wrong IP):**
1. Expected: spinner runs → orange snackbar → spinner stops, progress cleared, no player
2. Listen Page shows 1 English fallback tour

**Regression Test — English only:**
1. Select English only → Generate Now
2. **Expected**: Spinner stops at extraction complete, English player opens + "Tour ready!" snackbar

## Step 5 — Copy Results and Return

```
echo "Assignment 49c Results:" > ~/Desktop/a49c_results.txt
echo "Date: $(date)" >> ~/Desktop/a49c_results.txt
echo "Version: 1.2.9+49" >> ~/Desktop/a49c_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a49c_results.txt
echo "Russian-only: Spinner runs during translation wait: [YES/NO]" >> ~/Desktop/a49c_results.txt
echo "Russian-only: Russian player opened after translation: [YES/NO]" >> ~/Desktop/a49c_results.txt
echo "Russian-only: Spinner stops when player opens: [YES/NO]" >> ~/Desktop/a49c_results.txt
echo "Russian-only: Listen Page shows 1 tour (Russian only): [YES/NO]" >> ~/Desktop/a49c_results.txt
echo "English-only: Spinner stops at extraction, player opens: [YES/NO]" >> ~/Desktop/a49c_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a49c_results.txt

cp ~/Desktop/a49c_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 49c complete. v1.2.9+49. Build: [SUCCESS/FAILED]. Spinner runs during translation: [YES/NO]. Russian player opened: [YES/NO]. Spinner stops on completion: [YES/NO]. Listen Page 1 tour: [YES/NO]. English-only unchanged: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#49 — Navigate to Translated Player + Fix UX Snackbar/Progress (v1.2.9+47)

**Goal:** Build v1.2.9+47. A#49 (v1.2.9+46) was reviewed by Claude IO — APPROVED with two required pre-build fixes (C1, C2). Applied as A#49b.

**Scripts:** `copy_ios_fixes.sh` (19 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#48 (v1.2.9+45):**
- ✅ **tour_generator_screen.dart** — `_autoDownloadAndPlay`: gains `wantsEnglish` param. When false, skips `Navigator.push`, shows "Preparing translation..." instead
- ✅ **tour_generator_screen.dart** — `_pollAndAutoDownload`: computes `wantsEnglish` before `_autoDownloadAndPlay`, passes it in. After translation succeeds, navigates to Russian player via `translatedPath`
- ✅ **tour_generator_screen.dart** — `_processAdditionalLanguages`: return type `int` → `String?` (path of first saved translated tour)
- ✅ **C1** — `_showSuccess('Tour ready! Opening now...')` gated on `wantsEnglish` (was firing for Russian-only users before player opened)
- ✅ **C2** — `_progress = 'Preparing translation...'` now cleared when translation fails (`else if (!wantsEnglish && translatedPath == null)`)
- ✅ `pubspec.yaml` — version bumped to 1.2.9+47

**Result matrix:**
- Russian only + translation success → "Preparing translation..." → Russian player opens ✔
- Russian only + translation fail → English fallback kept, progress cleared, snackbar only ✔
- English only → English player opens immediately, "Tour ready!" snackbar shown ✔
- English + Russian → English player opens immediately, Russian added to Listen Page ✔

**Goal:** Build v1.2.9+45. When user generates a tour with only Russian selected, the English tour was being saved to the Listen page. Original fix (A#48 +44) skipped the English save unconditionally — Claude IO identified a regression: if translation fails, user ends up with zero tours. Fixed with save-then-remove: English always saved first as fallback, then pruned only if translation succeeded.

**Scripts:** `copy_ios_fixes.sh` (19 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#47 (v1.2.9+43):**
- ✅ **tour_generator_screen.dart** — `_autoDownloadAndPlay` Step 6: English always saved unconditionally as fallback
- ✅ **tour_generator_screen.dart** — `_processAdditionalLanguages` return type changed `void` → `int` (returns `saved.length`). All early returns now return `0`.
- ✅ **tour_generator_screen.dart** — `_pollAndAutoDownload`: after `_processAdditionalLanguages`, if `!wantsEnglish && translationsSucceeded > 0` calls `_removeTourFromSavedTours(finalTourId)` to prune English entry
- ✅ **tour_generator_screen.dart** — new `_removeTourFromSavedTours(int tourId)` helper: removes entry from `saved_tours` by matching `tour_id` field
- ✅ `pubspec.yaml` — version bumped to 1.2.9+45

**Result matrix:**
- Russian only + translation success → Russian only in Listen Page ✔
- Russian only + translation fail → English fallback in Listen Page (user has something) ✔
- English + Russian + success → English + Russian in Listen Page ✔
- English + Russian + fail → English only in Listen Page ✔

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (19 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 19 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: Generate Tour in Russian Only

1. Go to Tour Generator tab
2. Type: `Walking tour in Nice, France`
3. In language selector: **deselect English, select Russian only**
4. Tap **Generate Now**
5. Wait for generation + download (~2 min)
6. Tour player opens automatically (English audio plays)
7. **Expected**: Green snackbar "RU version added to My Tours"
8. Go to Listen Page
9. **Expected**: **1 tour only — Russian only (NO English)**
10. Check debug log for:
    - `TOUR: Removed English fallback (tour_id <N>) — 1 entry pruned`
    - `TOUR: Saved translated tour (ru) ID: <number>`

**Also test: English + Russian selected**
1. Keep English, add Russian → Generate Now
2. **Expected**: 2 tours in Listen Page (English + Russian)
3. Check debug log: NO `Removed English fallback` line

## Step 5 — Copy Results and Return

```
echo "Assignment 48 Results:" > ~/Desktop/a48_results.txt
echo "Date: $(date)" >> ~/Desktop/a48_results.txt
echo "Version: 1.2.9+45" >> ~/Desktop/a48_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a48_results.txt
echo "Russian-only: Listen Page shows 1 tour (Russian only): [YES/NO]" >> ~/Desktop/a48_results.txt
echo "Russian-only: English pruned log line present: [YES/NO]" >> ~/Desktop/a48_results.txt
echo "English+Russian: Listen Page shows 2 tours: [YES/NO]" >> ~/Desktop/a48_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a48_results.txt

cp ~/Desktop/a48_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 48 complete. v1.2.9+45. Build: [SUCCESS/FAILED]. Russian-only shows 1 tour: [YES/NO]. English pruned logged: [YES/NO]. English+Russian shows 2 tours: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#47 final — Fix Tour Generation Language + Follow-ups (v1.2.9+43)

**Goal:** Build v1.2.9+43. Includes all A#47 fixes plus three Claude IO in-cycle follow-ups.

**Scripts:** `copy_ios_fixes.sh` (19 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#46 (v1.2.9+41):**
- ✅ **tour_generator_screen.dart** — `_processAdditionalLanguages` stub replaced with real implementation: calls `TranslationService.translateTour()` (port 5030), downloads each translated ZIP from port 5005, saves via new `_saveTourToMyToursTranslated` helper. `_autoDownloadAndPlay` return type changed from `Future<void>` to `Future<int?>`. Dead `tourData['language']` assignments removed.
- ✅ **NF4** — `Config.defaultServerIp` replaces hardcoded `'192.168.0.218'` in `_processAdditionalLanguages` (line 398)
- ✅ **Q2** — Snackbar at end of `_processAdditionalLanguages`: green on full success, orange on partial failure, red on full failure. `mounted` guarded.
- ✅ **NF2** — `_saveTourInfo` now writes `'tour_id': jobId` (was `'id'`) + `'editable': false, 'is_translation': false` for schema parity with home_screen.dart
- ✅ `pubspec.yaml` — version bumped to 1.2.9+43

**Note:** English tour is always generated first (backend requirement). If user selects only Russian, they get both English + Russian in Listen Page, plus a green snackbar "RU version added to My Tours."

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (19 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 19 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: Generate Tour in Russian Only

1. Go to Tour Generator tab
2. Type: `Walking tour in Nice, France`
3. In language selector: **deselect English, select Russian only**
4. Tap **Generate Now**
5. Wait for generation + download (~2 min)
6. **Expected**: Green snackbar "RU version added to My Tours"
7. Go to Listen Page
8. **Expected**: 2 tours — English (generated) + Russian (translated)
9. Check debug log for:
   - `TOUR: Requesting translations for: ru`
   - `Translation: HTTP 200 received`
   - `TOUR: Saved translated tour (ru) ID: <number>`

## Step 5 — Copy Results and Return

```
echo "Assignment 47 Results:" > ~/Desktop/a47_results.txt
echo "Date: $(date)" >> ~/Desktop/a47_results.txt
echo "Version: 1.2.9+43" >> ~/Desktop/a47_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a47_results.txt
echo "Snackbar shown after translation: [YES/NO]" >> ~/Desktop/a47_results.txt
echo "Russian tour appears in Listen Page: [YES/NO]" >> ~/Desktop/a47_results.txt
echo "Translation HTTP 200 logged: [YES/NO]" >> ~/Desktop/a47_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a47_results.txt

cp ~/Desktop/a47_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 47 complete. v1.2.9+43. Build: [SUCCESS/FAILED]. Snackbar shown: [YES/NO]. Russian tour in Listen Page: [YES/NO]. Translation HTTP 200: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#47 — Fix Tour Generation Language Selection (v1.2.9+42)

**Goal:** Build v1.2.9+42. When user generates a new tour with only Russian selected (English deselected), the tour was always generated in English. Root cause: backend `generate-complete-tour` ignores the `language` parameter — it always generates English. The app was sending `language: ru` but never calling the translation service after generation. Fixed by replacing the `_processAdditionalLanguages` stub with real translation logic.

**Scripts:** `copy_ios_fixes.sh` (19 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#46 (v1.2.9+41):**
- ✅ **tour_generator_screen.dart** — `_processAdditionalLanguages` stub replaced with real implementation: calls `TranslationService.translateTour()` (port 5030), downloads each translated ZIP from port 5005, saves via new `_saveTourToMyToursTranslated` helper. `_autoDownloadAndPlay` return type changed from `Future<void>` to `Future<int?>` to pass `finalTourId` back to the caller. Dead `tourData['language']` assignments removed from both `_generateTour` and `_generateTourBackground` (backend ignores this param).
- ✅ `pubspec.yaml` — version bumped to 1.2.9+42

**Note:** English tour is always generated first (backend requirement). If user selects only Russian, they get both English + Russian in Listen Page. This is consistent with home_screen.dart behavior.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (19 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 19 files`, then `✅ flutter analyze passed (0 errors in project files)`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test: Generate Tour in Russian Only

1. Go to Tour Generator tab
2. Type: `Walking tour in Nice, France`
3. In language selector: **deselect English, select Russian only**
4. Tap **Generate Now**
5. Wait for generation + download (~2 min)
6. Go to Listen Page
7. **Expected**: 2 tours — English (generated) + Russian (translated)
8. Check debug log for:
   - `TOUR: Requesting translations for: ru`
   - `Translation: HTTP 200 received`
   - `TOUR: Saved translated tour (ru) ID: <number>`

## Step 5 — Copy Results and Return

```
echo "Assignment 47 Results:" > ~/Desktop/a47_results.txt
echo "Date: $(date)" >> ~/Desktop/a47_results.txt
echo "Version: 1.2.9+42" >> ~/Desktop/a47_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a47_results.txt
echo "Russian tour appears in Listen Page: [YES/NO]" >> ~/Desktop/a47_results.txt
echo "Translation HTTP 200 logged: [YES/NO]" >> ~/Desktop/a47_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a47_results.txt

cp ~/Desktop/a47_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 47 complete. v1.2.9+42. Build: [SUCCESS/FAILED]. Russian tour in Listen Page: [YES/NO]. Translation HTTP 200: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#46 — Inline edit_tour_screen Part Files + Remove foundation.dart (v1.2.9+41)

**Goal:** Build v1.2.9+41. Claude IO A#45 review (NF1) found that `edit_tour_screen_part2/3/4.dart` are top-level library scope — instance members of `_EditTourScreenState` are unreachable and `build()` in part4 does not satisfy `State.build`. All three part files have been deleted and their content inlined into a single `edit_tour_screen.dart`. Also removes unused `foundation.dart` import from `tour_player_screen.dart`.

**Scripts:** `copy_ios_fixes.sh` (now 19 files + flutter analyze guard) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#45 (v1.2.9+40):**
- ✅ **edit_tour_screen.dart** — Single-file. All methods from part2 (`_saveAllChanges`, `_handleNewTourDownload`, `_handleTraditionalSave`, `_extractTourId`, `_resetAllModifiedFlags`) and part3 (`_updateLocalTourId`, `_showSuccessMessage`, `_navigateToListenPage`, `_updateUIIndicators`, `_prepareStopsForBackend`, `_addNewStop`, `_reorderStops`) and part4 (`build()`) inlined into `_EditTourScreenState`. `part` directives removed.
- ✅ **edit_tour_screen_part2/3/4.dart** — Deleted from dev tree and assets.
- ✅ **tour_player_screen.dart** — Removed unused `import 'package:flutter/foundation.dart'`.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+41
- ✅ `copy_ios_fixes.sh` — now copies **19 files** (removed 3 part files). Added `flutter analyze` guard at top — script aborts if analyze reports errors.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)
- [ ] **VERIFICATION ASK (before deleting app):** First launch WITHOUT deleting app. Navigate to Listen Page. Check log for `LISTEN: Skipping tour with invalid field types`.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (19 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 19 files`, then `flutter analyze` runs and passes with `✅ flutter analyze passed (0 errors in project files)`

**Note:** The script first deletes stale `edit_tour_screen_part2/3/4.dart` from the Mac Mini if they exist, then copies 19 files, then runs `flutter analyze` (excluding pre-existing broken `audio_handler.dart` and `map_page.dart`). If analyze finds errors in our files it aborts with a list.

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Verification Ask (WITHOUT deleting app)

1. Launch app → navigate to Listen Page
2. Check log for `LISTEN: Skipping tour with invalid field types`
3. Record how many entries skipped and what keys they had

## Step 5 — Clean Test (delete app, reinstall)

1. Delete app from iPhone
2. Reinstall: `./build_install_launch.sh`
3. Download Kyoto — Original only, add Russian + French
4. Expected snackbar: `Tour downloaded with 2 translations (ru, fr)`
5. Listen Page: 3 tours with real stop counts
6. Directory names: `{name}_ru_{id}/` format

## Step 6 — Copy Results and Return

```
echo "Assignment 46 Results:" > ~/Desktop/a46_results.txt
echo "Date: $(date)" >> ~/Desktop/a46_results.txt
echo "Version: 1.2.9+41" >> ~/Desktop/a46_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a46_results.txt
echo "flutter analyze: [PASSED/FAILED]" >> ~/Desktop/a46_results.txt
echo "Verification ask - skipped entries: [N, keys]" >> ~/Desktop/a46_results.txt
echo "Snackbar shows translation count: [YES/NO]" >> ~/Desktop/a46_results.txt
echo "Listen Page shows 3 tours: [YES/NO]" >> ~/Desktop/a46_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a46_results.txt

cp ~/Desktop/a46_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 46 complete. v1.2.9+41. Build: [SUCCESS/FAILED]. flutter analyze: [PASSED/FAILED]. Verification ask: [N skipped, keys]. Snackbar translation count: [YES/NO]. Listen Page 3 tours: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#45 — Build Fix: Stage Sync + dart:async + part4 + tour_player (v1.2.9+40)

**Goal:** Build v1.2.9+40. The A#44 build failed with multiple compile errors. Root causes identified and fixed.

**Scripts:** `copy_ios_fixes.sh` (now 22 files) then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#44 (v1.2.9+39):**
- ✅ **home_screen.dart** — Re-staged. A#44 patches were applied to dev copy but staging step failed silently last session. Staged copy was still pre-A#44 (had the `editTourId` compile errors).
- ✅ **edit_tour_screen.dart** — Added `import 'dart:async'` (needed for `unawaited()`). Fixed `EditStopScreen(stop: stop)` → `EditStopScreen(tourData: widget.tourData, stopData: stop)` (constructor requires both params).
- ✅ **edit_tour_screen_part4.dart** — Added to copy script and staged. File existed in dev but was never included in `copy_ios_fixes.sh`. Build error: `part 'edit_tour_screen_part4.dart'` declared but file missing on Mac Mini.
- ✅ **edit_stop_screen.dart** — Added `import 'dart:async'` (needed for `unawaited()`).
- ✅ **html_audio_recorder_service.dart** — Added `import 'dart:async'` (needed for `unawaited()`).
- ✅ **tour_player_screen.dart** — Removed `import '../services/web_file_service.dart'` (file doesn't exist on iOS). Replaced `WebFileService.getTourFilePath()` call with direct mobile file URL (the `kIsWeb` branch was dead code on iOS anyway).
- ✅ `pubspec.yaml` — version bumped to 1.2.9+40
- ✅ `copy_ios_fixes.sh` — now copies **22 files** (added `edit_tour_screen_part4.dart`)

**Note:** `edit_tour_screen_part2.dart` and `edit_tour_screen_part3.dart` are `part of` files — they inherit imports from `edit_tour_screen.dart`. Adding `dart:async` to the main file covers them.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)
- [ ] **VERIFICATION ASK (before deleting app):** First launch WITHOUT deleting app. Navigate to Listen Page. Check log for `LISTEN: Skipping tour with invalid field types`.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (22 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 22 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Verification Ask (WITHOUT deleting app)

1. Launch app → navigate to Listen Page
2. Check log for `LISTEN: Skipping tour with invalid field types: [tour_name, directory, downloaded_at]`
3. Record how many entries skipped and what keys they had

## Step 5 — Clean Test (delete app, reinstall)

1. Delete app from iPhone
2. Reinstall: `./build_install_launch.sh`
3. Download Kyoto — Original only, add Russian + French
4. Expected snackbar: `Tour downloaded with 2 translations (ru, fr)`
5. Listen Page: 3 tours with real stop counts
6. Directory names: `{name}_ru_{id}/` format

## Step 6 — Copy Results and Return

```
echo "Assignment 45 Results:" > ~/Desktop/a45_results.txt
echo "Date: $(date)" >> ~/Desktop/a45_results.txt
echo "Version: 1.2.9+40" >> ~/Desktop/a45_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a45_results.txt
echo "Verification ask - skipped entries: [N, keys]" >> ~/Desktop/a45_results.txt
echo "Snackbar shows translation count: [YES/NO]" >> ~/Desktop/a45_results.txt
echo "Listen Page shows 3 tours: [YES/NO]" >> ~/Desktop/a45_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a45_results.txt

cp ~/Desktop/a45_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 45 complete. v1.2.9+40. Build: [SUCCESS/FAILED]. Verification ask: [N skipped, keys]. Snackbar translation count: [YES/NO]. Listen Page 3 tours: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#44 — Fix Compile Errors from A#43 Item 6 (v1.2.9+39)

**Goal:** Build v1.2.9+39. Claude IO review of A#43 found two compile errors and two logic bugs in the `parent_tour_id` threading (Item 6). All other A#43 items were approved. This build fixes only the Item 6 issues.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~20 minutes

**What changed since A#43 (v1.2.9+38):**
- ✅ **Showstopper 1** — `editTourId` was referenced in `_downloadSingleTour` but is a local variable in `_saveTourToMyTours`. Compile error: `Undefined name 'editTourId'`. Fixed by adding `_resolveParentEditTourId(tourId, prefs)` helper and calling it instead.
- ✅ **Showstopper 2** — Dead `if (isTranslation)` block in `_saveTourToMyTours` referenced `editTourId` 8 lines before its declaration. Compile error: `Local variable 'editTourId' can't be referenced before it is declared`. Fixed by replacing the dead block with `assert(!isTranslation, ...)`.
- ✅ **Bug B1** — `_downloadSingleTourSilent` scanned `saved_tours` comparing `m['tour_id'] == tourId.toString()` but `tour_id` stores the edit UUID (e.g. `305cf634`), not the download ID (e.g. `167`). Match never fired. Fixed by using `_resolveParentEditTourId` instead.
- ✅ **Bug B2** — Same scan looked for `m['edit_tour_id']` which is not a field in the schema. Fixed by same `_resolveParentEditTourId` approach.
- ✅ **Q2** — `parent_tour_id` now stores `null` instead of empty string when resolution fails: `parentEditTourId.isEmpty ? null : parentEditTourId`.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+39

**New helper added:**
```dart
Future<String> _resolveParentEditTourId(int downloadTourId, SharedPreferences prefs) async
```
Calls the resolution endpoint (port 5025) and returns `edit_tour_id`. Both `_downloadSingleTour` and `_downloadSingleTourSilent` call it before `_downloadTranslatedVersions`.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)
- [ ] **VERIFICATION ASK (before deleting app):** First launch WITHOUT deleting app. Navigate to Listen Page. Check log for `LISTEN: Skipping tour with invalid field types` lines.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (21 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 21 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Verification Ask (WITHOUT deleting app)

1. Launch app → navigate to Listen Page
2. Check log for `LISTEN: Skipping tour with invalid field types: [tour_name, directory, downloaded_at]`
3. Record how many entries skipped and what keys they had

## Step 5 — Clean Test (delete app, reinstall)

1. Delete app from iPhone
2. Reinstall: `./build_install_launch.sh`
3. Download Kyoto — Original only, add Russian + French
4. Expected snackbar: `Tour downloaded with 2 translations (ru, fr)`
5. Listen Page: 3 tours with real stop counts
6. Directory names: `{name}_ru_{id}/` format

## Step 6 — Copy Results and Return

```
echo "Assignment 44 Results:" > ~/Desktop/a44_results.txt
echo "Date: $(date)" >> ~/Desktop/a44_results.txt
echo "Version: 1.2.9+39" >> ~/Desktop/a44_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a44_results.txt
echo "Verification ask - skipped entries: [N, keys]" >> ~/Desktop/a44_results.txt
echo "Snackbar shows translation count: [YES/NO]" >> ~/Desktop/a44_results.txt
echo "Listen Page shows 3 tours: [YES/NO]" >> ~/Desktop/a44_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a44_results.txt

cp ~/Desktop/a44_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 44 complete. v1.2.9+39. Build: [SUCCESS/FAILED]. Verification ask: [N skipped, keys]. Snackbar translation count: [YES/NO]. Listen Page 3 tours: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/2026 - A#43 — M8 Extraction + Translation UX + Hygiene Sweep (v1.2.9+38)

**Goal:** Build v1.2.9+38. Implements all 12 items from Claude IO's `instructions_for_a43.md`. Core change is M8 architectural refactor — translation loop extracted into shared `_downloadTranslatedVersions()` method. Also fixes snackbar counts, prunes zombie SharedPreferences entries, sweeps 14 non-awaited DebugLogHelper calls, adds Config class, and more.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~20-25 minutes

**What changed since A#42 (v1.2.9+37):**
- ✅ **Item 1 (M8)** — `_downloadTranslatedVersions(tourId, languages, serverIp, parentEditTourId)` extracted. Translation loop now exists exactly once. Both `_downloadSingleTour` and `_downloadSingleTourSilent` call it.
- ✅ **Item 2 (Q4)** — `_downloadMultipleTours` aggregates per-tour translation failures into `Map<String, List<String>> failuresByTour`. Snackbar shows failure summary.
- ✅ **Item 3** — Snackbar count now reflects translations: "Tour downloaded with 2 translations (ru, fr)" instead of always "Tour downloaded successfully!"
- ✅ **Item 4** — `_loadTours()` prunes zombie `saved_tours` entries on first load. Corrupt entries removed from SharedPreferences so they don't accumulate.
- ✅ **Item 5** — Field validation in `_loadTours()` tightened from null-check to type-check (`is! String`). Entries with non-String fields are skipped.
- ✅ **Item 6 (N2/M6)** — `parentEditTourId` threaded through to `_saveTourToMyToursTranslated`. `parent_tour_id` field now populated instead of always null.
- ✅ **Item 7 (M1)** — All 14 non-awaited `DebugLogHelper.addDebugLog` calls fixed across 7 files. Sync callbacks use `unawaited()` with comment.
- ✅ **Item 8 (M4)** — New `lib/config.dart` with `Config.defaultServerIp = '192.168.0.218'`. All 12 hardcoded `'192.168.0.217'` defaults replaced.
- ✅ **Item 9 (M5)** — Translation response body truncated to 500 chars in log.
- ✅ **Item 10** — `_countTourStops` logs when falling back to default 10.
- ✅ **Item 11** — Moot: translation loop removed from both functions by M8.
- ✅ **Item 12 (M7)** — Translated tour directory now named `{safeName}_{lang}_{id}/` instead of `translated_tour_{id}/`.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+38

**Files modified:** `home_screen.dart`, `my_tours_screen.dart`, `translation_service.dart`, `edit_tour_screen.dart`, `edit_tour_screen_part2.dart`, `edit_tour_screen_part3.dart`, `edit_stop_screen.dart`, `html_audio_recorder_service.dart`, `tour_player_screen.dart`
**Files added:** `lib/config.dart`

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)
- [ ] **VERIFICATION ASK (before deleting app):** First launch WITHOUT deleting app. Navigate to Listen Page. Check log for `LISTEN: Skipping tour with invalid field types` lines — confirms A#42 diagnosis. Then delete app and do clean test.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (21 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 21 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Verification Ask (run WITHOUT deleting app first)

1. Launch app → navigate to Listen Page
2. Check debug log for `LISTEN: Skipping tour with invalid field types: [tour_name, directory, downloaded_at]`
3. Record: how many entries skipped and what keys they had
4. This confirms the A#42 white-screen diagnosis

## Step 5 — Clean Test (delete app, reinstall)

1. Delete app from iPhone
2. Reinstall: `./build_install_launch.sh`
3. Download Kyoto — select **Original only** (NOT Custom/translated)
4. Add Russian + French languages
5. Tap Download Tour

**Expected snackbar:** `Tour downloaded with 2 translations (ru, fr)`

6. Navigate to Listen Page
7. **Expected:** 3 tours (English + Russian + French) with real stop counts
8. Check log: `LISTEN: Loaded 3 valid tours (0 skipped)`
9. Check directory names: should be `{name}_ru_{id}/` and `{name}_fr_{id}/` not `translated_tour_{id}/`

## Step 6 — Batch Test

1. Use tour search to select 2 tours
2. Add Russian language
3. Download Selected
4. **Expected snackbar:** `2 tours downloaded with 2 translations`
5. If any translation fails: `2 tours downloaded. Some translations failed: {tour}: ru`

## Step 7 — Copy Results and Return

```
echo "Assignment 43 Results:" > ~/Desktop/a43_results.txt
echo "Date: $(date)" >> ~/Desktop/a43_results.txt
echo "Version: 1.2.9+38" >> ~/Desktop/a43_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a43_results.txt
echo "Verification ask - skipped entries: [N entries, keys: tour_name/directory/downloaded_at]" >> ~/Desktop/a43_results.txt
echo "Snackbar shows translation count: [YES/NO]" >> ~/Desktop/a43_results.txt
echo "Listen Page shows 3 tours: [YES/NO]" >> ~/Desktop/a43_results.txt
echo "Directory names use new format: [YES/NO]" >> ~/Desktop/a43_results.txt
echo "Batch download snackbar correct: [YES/NO]" >> ~/Desktop/a43_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a43_results.txt

cp ~/Desktop/a43_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 8 — Report Results

> "Assignment 43 complete. v1.2.9+38. Build: [SUCCESS/FAILED]. Verification ask: [N skipped, keys]. Snackbar shows translation count: [YES/NO]. Listen Page 3 tours: [YES/NO]. Directory names correct: [YES/NO]. Batch snackbar: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#42 — Fix White Screen on Listen Page (v1.2.9+37)

**Goal:** Build v1.2.9+37. After A#41 test, the Listen Page showed a white screen instead of tours. Root cause: `_loadTours()` in `my_tours_screen.dart` called `jsonDecode` on all saved tour entries inside a single `setState` — one entry with missing/null fields (old schema from pre-A#40 builds, or the failed second download of tour 170) caused the entire `setState` to throw, leaving `_tours` empty and the screen blank.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#41:**
- ✅ `my_tours_screen.dart` — `_loadTours()` rewritten to parse entries one-by-one with try/catch. Entries missing `title`, `path`, or `created` are skipped with a debug log line. One bad entry no longer blanks the whole screen.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+37

**Root cause from log_iPhone_05132026_1212.txt:**
The log showed 4 successful saves (English + ru + fr + zh). But the `saved_tours` SharedPreferences list also contained entries from previous test runs (A#36–A#40) that used the old broken schema (`tour_name`, `directory`, `downloaded_at` instead of `title`, `path`, `created`). When `_loadTours` tried to render those old entries, `tour['title']` was null → `Text(null)` → assertion crash inside `setState` → `_tours` never set → white screen.

**Also noted from log:** When you selected "Original + Russian Custom" in the multi-select dialog, the app tried to download the Russian Custom tour (ID 170) as a regular tour via `_downloadSingleTourSilent` → resolution endpoint → 404. This is why the snackbar said "1 tours downloaded" — only the English original counted. The 3 translated tours (ru/fr/zh) were saved correctly via the translation path. This is a separate UX issue (Custom/translated tours should not be selectable for direct download) — deferred.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] **IMPORTANT**: Delete the app from iPhone before installing to clear old corrupt SharedPreferences entries

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

**Note:** `copy_ios_fixes.sh` must include `my_tours_screen.dart`. Check the script includes it — if not, copy manually:
```
cp "/Volumes/USB DISK/Audioura/assets/my_tours_screen.dart" \
   ~/Development/AudioTours/development/audio_tour_app/lib/screens/my_tours_screen.dart
```

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test

1. Open app → Home tab → search **Kyoto, Japan**
2. Tap the Kyoto tour marker → select **Original only** (do NOT select Custom/translated tours)
3. Select languages: **Russian + French**
4. Tap **Download Tour**
5. Wait for translation to complete (~22 seconds)
6. Go to **Listen Page**
7. **Expected**: Tours list visible (NOT white screen)
8. **Expected**: 3 entries — English, Russian (Cyrillic name), French
9. **Expected**: Stop count shows real number (not "0 stops")

**Check debug log for:**
- `LISTEN: Loading X tours from storage`
- `LISTEN: Loaded X valid tours (Y skipped)` — Y should be 0 on fresh install
- `HOME: Saved translated tour 170 as: пешеходная...`

## Step 5 — Copy Results and Return

```
echo "Assignment 42 Results:" > ~/Desktop/a42_results.txt
echo "Date: $(date)" >> ~/Desktop/a42_results.txt
echo "Version: 1.2.9+37" >> ~/Desktop/a42_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a42_results.txt
echo "Listen Page shows tours (not white): [YES/NO]" >> ~/Desktop/a42_results.txt
echo "Russian tour visible: [YES/NO]" >> ~/Desktop/a42_results.txt
echo "French tour visible: [YES/NO]" >> ~/Desktop/a42_results.txt
echo "Stop count correct: [YES/NO]" >> ~/Desktop/a42_results.txt
echo "Tapped translated tour - what happened: [PLAYS/CRASH/BLANK]" >> ~/Desktop/a42_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a42_results.txt

cp ~/Desktop/a42_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 42 complete. v1.2.9+37. Build: [SUCCESS/FAILED]. Listen Page shows tours: [YES/NO]. Russian visible: [YES/NO]. French visible: [YES/NO]. Stop count correct: [YES/NO]. Tapped translated tour: [PLAYS/CRASH/BLANK]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#41 — H3 Ordering Fix + Q1/Q2/Q3/N1 Corrections (v1.2.9+36)

**Goal:** Build v1.2.9+36. Claude IO's second-pass review of A#40 found one ordering bug in a fix that landed, answered 3 open questions requiring code changes, and identified 2 new findings. All 5 are fixed in this build.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#40 (all in `home_screen.dart`):**
- ✅ **H3 ordering bug** — In `_downloadSingleTour()` catch block, `if (!mounted) return` was after `Navigator.canPop(context)`. `canPop` reads the widget tree and can throw on a deactivated widget. Swapped: `!mounted` check now comes first (line 1310).
- ✅ **Q1 — stops count** — `_saveTourToMyToursTranslated()` now calls `_countTourStops(zipBytes)` instead of hardcoding `'0'`. My Tours card now shows real stop count for translated tours (line 1554).
- ✅ **Q2 — _downloadMultipleTours guards** — Added `if (!mounted) return` + `if (Navigator.canPop(context)) Navigator.pop(context)` before the post-loop `Navigator.pop` (line 947). Added second `if (!mounted) return` before `ScaffoldMessenger` (line 963). Bare `Navigator.pop` replaced with guarded version.
- ✅ **N1 — two silent snackbar holes** — In `_downloadSingleTour()`: (a) when `_extractTranslatedIds()` returns null, all languages now added to `translationFailures`; (b) when server omits a language from response, that language now added to `translationFailures` with `continue`. Same null-ID hole closed in `_downloadSingleTourSilent()` (log only, no snackbar there).
- ✅ **Q3 — silent path outer try/catch** — Entire translation block in `_downloadSingleTourSilent()` wrapped in try/catch. Any exception after English is saved (malformed response, SharedPreferences quirk, etc.) is now caught and logged without rethrowing. English success is never retroactively un-succeeded.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+36

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Translation

1. Open app → Home tab → search **Kyoto, Japan**
2. Tap the Kyoto tour marker → download dialog
3. Add **Russian** AND **French** in language selector (keep English)
4. Tap **Download Tour**
5. Wait for translation dialog to close (~22 seconds)
6. **Expected**: Three entries in My Tours:
   - Kyoto tour (English) — normal entry with real stop count
   - Kyoto tour (Russian) — real stop count (NOT "0 stops")
   - Kyoto tour (French) — real stop count (NOT "0 stops")
7. **Expected**: NO black screen at any point
8. **Expected**: Green snackbar "Tour downloaded successfully!"
9. Tap each translated tour → should open without crash

**Check debug log for:**
- `HOME: Skipping resolution for translated tour ID: 170`
- `HOME: Saved translated tour 170 as: <name>`
- `HOME: Skipping resolution for translated tour ID: 171`
- `HOME: Saved translated tour 171 as: <name>`

## Step 5 — Copy Results and Return

```
echo "Assignment 41 Results:" > ~/Desktop/a41_results.txt
echo "Date: $(date)" >> ~/Desktop/a41_results.txt
echo "Version: 1.2.9+36" >> ~/Desktop/a41_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a41_results.txt
echo "No black screen: [YES/NO]" >> ~/Desktop/a41_results.txt
echo "Russian tour in My Tours: [YES/NO]" >> ~/Desktop/a41_results.txt
echo "French tour in My Tours: [YES/NO]" >> ~/Desktop/a41_results.txt
echo "Stop count correct (not 0): [YES/NO]" >> ~/Desktop/a41_results.txt
echo "My Tours screen no crash: [YES/NO]" >> ~/Desktop/a41_results.txt
echo "Translated tour opens in player: [YES/NO]" >> ~/Desktop/a41_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a41_results.txt

cp ~/Desktop/a41_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 41 complete. v1.2.9+36. Build: [SUCCESS/FAILED]. No black screen: [YES/NO]. Russian in My Tours: [YES/NO]. French in My Tours: [YES/NO]. Stop count correct: [YES/NO]. My Tours no crash: [YES/NO]. Tour player opens: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#40 — Fix Schema Mismatch + Silent Path + Navigator Guards + Partial Failure Snackbar (v1.2.9+35)

**Goal:** Build v1.2.9+35. Claude IO code review identified 6 issues that would cause crashes or incorrect behavior. This build fixes all critical and high-priority items.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#39 (all in `home_screen.dart`):**
- ✅ **C1 — Schema fix**: `_saveTourToMyToursTranslated()` now writes `title`, `path`, `created`, `stops`, `original_request`, `tour_id`, `editable`, `is_translation`, `parent_tour_id` — matching the schema `my_tours_screen.dart` reads. Previously used `tour_name`, `directory`, `downloaded_at` which caused `Text(tour['title'])` → null assertion crash on My Tours screen.
- ✅ **C2 — Silent path try/catch**: `_downloadSingleTourSilent()` translation loop now has per-language try/catch (same as `_downloadSingleTour`). Previously a translation failure in the silent path threw an exception that `_downloadMultipleTours` caught, causing `successCount` to not increment → "No new tours downloaded" even when all English tours saved.
- ✅ **H1 — All Navigator.pop guarded**: All 3 bare `Navigator.pop(context)` in `_downloadSingleTour` replaced with `if (Navigator.canPop(context)) Navigator.pop(context)`. Prevents double-pop crash on any code path.
- ✅ **H2 — Partial failure snackbar**: `translationFailures` list tracks per-language failures. If any language failed: orange snackbar "English downloaded; ru translation failed." instead of always-green "Tour downloaded successfully!".
- ✅ **H3 — mounted checks**: `if (!mounted) return` added after English download save and after translation await — prevents "deactivated widget" exceptions if user navigates away during the 22-second translation wait.
- ✅ **M2 — rethrow**: `throw e` → `rethrow` in `_saveTourToMyTours` catch block. Preserves original stack trace.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+35

**Root cause (Claude IO review):**
C1: `_saveTourToMyToursTranslated` used different field names than the rest of the app. My Tours screen reads `tour['title']` — translated tours stored `tour_name` → null → assertion failure on first render.
C2: The architectural duplication (two parallel download paths) meant the A#39 per-language try/catch was only applied to `_downloadSingleTour`, not `_downloadSingleTourSilent`. Batch downloads still failed silently.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Translation (Single Tour)

1. Open app → Home tab → search **Kyoto, Japan**
2. Tap the Kyoto tour marker → download dialog
3. Add **Russian** AND **French** in language selector (keep English)
4. Tap **Download Tour**
5. Wait for translation dialog to close (~22 seconds)
6. **Expected**: Three entries in My Tours:
   - Kyoto tour (English) — normal entry
   - Kyoto tour (Russian) — `translated_tour_170/`
   - Kyoto tour (French) — `translated_tour_171/`
7. **Expected**: NO black screen at any point
8. **Expected**: Green snackbar "Tour downloaded successfully!" (all languages worked)
9. Tap each translated tour in Listen tab → should open without crash

**Check debug log for:**
- `HOME: Skipping resolution for translated tour ID: 170`
- `HOME: Saved translated tour 170 as: <name>`
- `HOME: Skipping resolution for translated tour ID: 171`
- `HOME: Saved translated tour 171 as: <name>`

## Step 5 — Test My Tours Screen (Critical C1 Verification)

1. After downloading Kyoto with Russian + French, go to Listen tab
2. **Expected**: All 3 tours display with titles (NOT blank/crash)
3. Tap each translated tour
4. **Expected**: Tour player opens (NOT crash)

## Step 6 — Copy Results and Return

```
echo "Assignment 40 Results:" > ~/Desktop/a40_results.txt
echo "Date: $(date)" >> ~/Desktop/a40_results.txt
echo "Version: 1.2.9+35" >> ~/Desktop/a40_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a40_results.txt
echo "No black screen: [YES/NO]" >> ~/Desktop/a40_results.txt
echo "Russian tour in My Tours: [YES/NO]" >> ~/Desktop/a40_results.txt
echo "French tour in My Tours: [YES/NO]" >> ~/Desktop/a40_results.txt
echo "My Tours screen no crash: [YES/NO]" >> ~/Desktop/a40_results.txt
echo "Translated tour opens in player: [YES/NO]" >> ~/Desktop/a40_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a40_results.txt

cp ~/Desktop/a40_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 40 complete. v1.2.9+35. Build: [SUCCESS/FAILED]. No black screen: [YES/NO]. Russian in My Tours: [YES/NO]. French in My Tours: [YES/NO]. My Tours no crash: [YES/NO]. Tour player opens: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#39 — Fix Translated Tour Save (404 Resolution) + Black Screen Escape (v1.2.9+34)

**Goal:** Build v1.2.9+34. Translated tours (Russian/French) were failing with `404 EDIT_ID_NOT_FOUND` because `_saveTourToMyTours` tried to resolve an `edit_tour_id` for translated tours — they don't have one. This caused an unhandled exception that left the translation dialog open with no escape (black screen). This build fixes both.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#38:**
- ✅ `home_screen.dart` — `_saveTourToMyTours` now accepts `isTranslation: true` parameter. When set, skips the `/tour/$id/resolve` call entirely and delegates to new `_saveTourToMyToursTranslated()` helper which saves directly using `tourId` as directory key.
- ✅ `home_screen.dart` — `_saveTourToMyToursTranslated()` helper: extracts tour name from ZIP manifest, saves files to `translated_tour_<id>/` directory, adds entry to `saved_tours` SharedPreferences with `is_translation: true` flag.
- ✅ `home_screen.dart` — Translation download loop in `_downloadSingleTour` wrapped in per-language `try/catch` — one language failing no longer crashes the whole flow.
- ✅ `home_screen.dart` — `Navigator.pop` replaced with `Navigator.canPop` guard — dialog always dismissed even if exception occurs.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+34

**Root cause (from log_iPhone_05122026_1203.txt):**
```
[11:59:51] Translation: HTTP 200 received
[11:59:51] Translation: Success - {"translations": {"fr": {"id": 171}, "ru": {"id": 170}}}
[11:59:51] HOME: Resolving tour ID for download ID: 170
[11:59:51] HOME: Tour resolution response: 404
[11:59:51] HOME: Tour resolution error: EDIT_ID_NOT_FOUND
[11:59:51] HOME: Error saving tour to My Tours: Exception: Tour could not be downloaded.
```
Translated tour IDs (170, 171) don't exist in the resolution service — they're translations, not originals. The 404 threw an exception, the translation dialog was never dismissed (`barrierDismissible: false`), leaving a black screen with no escape.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Translation

1. Open app → Home tab → search **Kyoto, Japan**
2. Tap the Kyoto tour marker → download dialog
3. Add **Russian** AND **French** in language selector (keep English)
4. Tap **Download Tour**
5. Wait for translation dialog to close (~22 seconds based on log)
6. **Expected**: Three entries in My Tours:
   - Kyoto tour (English)
   - Kyoto tour (Russian) — `translated_tour_170/`
   - Kyoto tour (French) — `translated_tour_171/`
7. **Expected**: NO black screen at any point
8. Open each translated tour in Listen tab → audio should be in respective language

**Check debug log for:**
- `HOME: Skipping resolution for translated tour ID: 170`
- `HOME: Saved translated tour 170 as: <name>`
- `HOME: Skipping resolution for translated tour ID: 171`
- `HOME: Saved translated tour 171 as: <name>`

## Step 5 — Copy Results and Return

```
echo "Assignment 39 Results:" > ~/Desktop/a39_results.txt
echo "Date: $(date)" >> ~/Desktop/a39_results.txt
echo "Version: 1.2.9+34" >> ~/Desktop/a39_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a39_results.txt
echo "No black screen: [YES/NO]" >> ~/Desktop/a39_results.txt
echo "Russian tour in My Tours: [YES/NO]" >> ~/Desktop/a39_results.txt
echo "French tour in My Tours: [YES/NO]" >> ~/Desktop/a39_results.txt
echo "Russian audio plays: [YES/NO/NOT_TESTED]" >> ~/Desktop/a39_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a39_results.txt

cp ~/Desktop/a39_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 39 complete. v1.2.9+34. Build: [SUCCESS/FAILED]. No black screen: [YES/NO]. Russian tour in My Tours: [YES/NO]. French tour in My Tours: [YES/NO]. Russian audio: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#38 — Fix Translation Response Parsing: Handle Actual Server Shape (v1.2.9+33)

**Goal:** Build v1.2.9+33. The translation API returns `translations.ru.id` but the app was parsing `translated_tour_ids.ru`. Russian tour ID was extracted as `null` every time — download never happened. This build fixes the parsing to handle both response shapes.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#37:**
- ✅ `home_screen.dart` — new `_extractTranslatedIds()` helper handles both response shapes:
  - Shape A (spec): `{"translated_tour_ids": {"ru": 168}}`
  - Shape B (actual server): `{"translations": {"ru": {"id": 168, "status": "translated"}}}`
  - Both `_downloadSingleTour()` and `_downloadSingleTourSilent()` now use this helper
- ✅ `pubspec.yaml` — version bumped to 1.2.9+33

**Root cause (confirmed from log_iPhone_05122026_1056.txt):**
```
[10:53:02] Translation: HTTP 200 received
[10:53:02] Translation: Success - {"status": "completed", "translations": {"ru": {"id": 168, "status": "translated"}}}
```
Server returned `translations.ru.id = 168`. App parsed `translated_tour_ids` → got `null` → skipped download entirely. Russian tour never saved.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service on port 5030)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Translation

1. Open app → Home tab → search **Shanghai, China**
2. Tap the Shanghai tour marker → download dialog
3. Add **Russian** in language selector (keep English)
4. Tap **Download Tour**
5. Wait for "Requesting translation..." dialog to close (~16 seconds based on log)
6. **Expected**: Two entries in My Tours:
   - `walking tour in Shanghai, China - walking Tour` (English)
   - `walking tour in Shanghai, China - walking Tour` (Russian) — separate entry
7. Open Russian tour in Listen tab → audio should be in Russian

**Check debug log for:**
- `Translation: HTTP 200 received`
- `Translation: Success - {"status": "completed", "translations": ...}`
- `HOME: Saved translated tour (ru) ID: 168`

## Step 5 — Copy Results and Return

```
echo "Assignment 38 Results:" > ~/Desktop/a38_results.txt
echo "Date: $(date)" >> ~/Desktop/a38_results.txt
echo "Version: 1.2.9+33" >> ~/Desktop/a38_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a38_results.txt
echo "Translation HTTP 200 received: [YES/NO]" >> ~/Desktop/a38_results.txt
echo "HOME: Saved translated tour (ru) logged: [YES/NO]" >> ~/Desktop/a38_results.txt
echo "Russian tour appears in My Tours: [YES/NO]" >> ~/Desktop/a38_results.txt
echo "Russian audio plays: [YES/NO/NOT_TESTED]" >> ~/Desktop/a38_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a38_results.txt

cp ~/Desktop/a38_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 38 complete. v1.2.9+33. Build: [SUCCESS/FAILED]. HTTP 200: [YES/NO]. Saved translated tour logged: [YES/NO]. Russian tour in My Tours: [YES/NO]. Russian audio: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/13/2026 - A#37 — Fix Silent Translation Failure: await DebugLogHelper + Add HTTP Status Log (v1.2.9+32)

**Goal:** Build v1.2.9+32 with fixed logging in `translation_service.dart`. Services Amazon-Q confirmed the translation request never reached the server on May 12 — the mobile app fires the request but exception details are silently dropped because `DebugLogHelper.addDebugLog()` was not awaited. This build adds `await` to all log calls and adds a new `Translation: HTTP <status> received` log line so we can see exactly where the failure occurs.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#36:**
- ✅ `translation_service.dart` — all 3 `DebugLogHelper.addDebugLog()` calls now properly `await`ed. Added `Translation: HTTP <statusCode> received` log line after the HTTP call returns. Previously: fire-and-forget logs meant any exception (port unreachable, timeout, bad response) was silently swallowed with no trace in the debug log viewer.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+32

**Root cause (confirmed by Services Amazon-Q):**
- iPhone fired `Requesting tour translation for languages: ru` at 13:49:39 and 13:50:41 on May 12
- Translation service logs show NO corresponding entries for May 12 — request never reached the server
- `home_screen.dart` logic is correct (properly awaits `TranslationService.translateTour()` and handles response)
- The gap: `translation_service.dart` had fire-and-forget `DebugLogHelper` calls — if `http.post` threw an exception (e.g. connection refused on port 5030), the exception was caught but the log write was dropped before the UI could capture it
- Services confirmed tour 8 WAS translated on May 11 → ID 161. The iPhone just never got that ID back.

**What the fixed logs will show (one of these):**
- `Translation: POST http://192.168.0.218:5030/translate-with-audio tourId=8 languages=ru` → `Translation: HTTP 200 received` → `Translation: Success - {"status":"completed","translated_tour_ids":{"ru":161}}` → `HOME: Saved translated tour (ru) ID: 161` ✅
- `Translation: POST ...` → `Translation: Exception - SocketException: Connection refused` (port 5030 down) ❌
- `Translation: POST ...` → `Translation: Exception - TimeoutException` (service too slow) ❌

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running — verify translation-service container: `docker ps | grep translation` on Windows laptop
- [ ] **IMPORTANT**: Wait at least 3 minutes after tapping Download before checking debug log — Polly audio generation takes 1-2 min

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Translation with Debug Log

1. Open app → Home tab (map view)
2. Tap any tour marker → download dialog opens
3. In language selector, add **Russian** (keep English checked too)
4. Tap **Download Tour**
5. **Wait 3+ minutes** (Polly audio generation is slow)
6. Open Debug Log viewer (About tab → Debug Log)
7. Look for these log lines in order:
   - `HOME: Requesting tour translation for languages: ru`
   - `Translation: POST http://192.168.0.218:5030/translate-with-audio tourId=X languages=ru`
   - `Translation: HTTP 200 received` ← NEW — confirms request reached server
   - `Translation: Success - {"status":"completed",...}`
   - `HOME: Saved translated tour (ru) ID: <number>`
8. **Expected**: Two entries in My Tours (English + Russian)

**If log shows `Translation: Exception - SocketException`:**
- Port 5030 is unreachable — translation-service container not running
- On Windows: `docker ps | grep translation` and `docker start <container_name>`

**If log shows `Translation: Exception - TimeoutException`:**
- Service is running but taking >5 minutes — check service logs on Windows

## Step 5 — Copy Results and Return

```
echo "Assignment 37 Results:" > ~/Desktop/a37_results.txt
echo "Date: $(date)" >> ~/Desktop/a37_results.txt
echo "Version: 1.2.9+32" >> ~/Desktop/a37_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a37_results.txt
echo "Translation: POST log line appears: [YES/NO]" >> ~/Desktop/a37_results.txt
echo "Translation: HTTP 200 received: [YES/NO]" >> ~/Desktop/a37_results.txt
echo "Translation: Success log appears: [YES/NO]" >> ~/Desktop/a37_results.txt
echo "Russian tour in My Tours: [YES/NO]" >> ~/Desktop/a37_results.txt
echo "Exception seen (if any): [NONE / SocketException / TimeoutException / OTHER]" >> ~/Desktop/a37_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a37_results.txt

cp ~/Desktop/a37_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 37 complete. v1.2.9+32. Build: [SUCCESS/FAILED]. Translation POST logged: [YES/NO]. HTTP 200 received: [YES/NO]. Russian tour in My Tours: [YES/NO]. Exception: [NONE/type]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/08/2026 - A#36 — Tour Translation Feature: Wire Up Real API Calls (v1.2.9+31)

**Goal:** Build v1.2.9+31 with working tour translation. When user downloads a tour with Russian selected, the app now calls the real translation service and downloads the translated tour as a separate My Tours entry.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#35:**
- ✅ `translation_service.dart` — completely rewritten. Was using `localhost:5030` (wrong — phone can't reach Windows server that way) and `/translate-with-audio` endpoint (didn't exist). Now uses `serverIp` from SharedPreferences, correct endpoint `/translate-with-audio`, integer `tourId`, and parses `translated_tour_ids` from response.
- ✅ `home_screen.dart` — both `_downloadSingleTour()` and `_downloadSingleTourSilent()` now call `TranslationService.translateTour()` for real. After translation completes, downloads the translated tour ZIP from port 5005 and saves it as a separate My Tours entry (e.g. "McMullen Museum of Art (Russian)"). Old orange stub snackbar removed.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+31

**API flow (confirmed with Services Amazon-Q via ISSUE-058):**
1. `POST 192.168.0.218:5030/translate-with-audio` with `{content_id: <int>, content_type: "tour", languages: ["ru"]}`
2. Response: `{status: "completed", translated_tour_ids: {"ru": <new_int_id>}}`
3. `GET 192.168.0.218:5005/download-tour/<new_int_id>` → save as separate My Tours entry

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Services backend running (translation-service container on port 5030 must be up)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Tour Translation

1. Open app → Home tab (map view)
2. Tap any tour marker → download dialog opens
3. In language selector, add **Russian** (keep English checked too)
4. Tap **Download Tour**
5. Watch for two progress dialogs: "Downloading tour..." then "Requesting translation to ru..."
6. **Expected**: Two entries appear in My Tours:
   - "[Tour Name]" (English)
   - "[Tour Name]" (Russian) — separate entry
7. Open the Russian tour in Listen tab → audio should be in Russian (Polly Tatyana voice)

**If translation times out (Polly audio generation can take 1-2 min):**
- The English tour should still save successfully
- Check debug log for: `HOME: Saved translated tour (ru) ID: <number>`
- If log shows `Translation failed` — check Services container: `docker ps | grep translation`

## Step 5 — Copy Results and Return

```
echo "Assignment 36 Results:" > ~/Desktop/a36_results.txt
echo "Date: $(date)" >> ~/Desktop/a36_results.txt
echo "Version: 1.2.9+31" >> ~/Desktop/a36_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a36_results.txt
echo "English tour downloads: [YES/NO]" >> ~/Desktop/a36_results.txt
echo "Translation API called (no stub snackbar): [YES/NO]" >> ~/Desktop/a36_results.txt
echo "Russian tour appears in My Tours: [YES/NO]" >> ~/Desktop/a36_results.txt
echo "Russian audio plays (not English): [YES/NO/NOT_TESTED]" >> ~/Desktop/a36_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a36_results.txt

cp ~/Desktop/a36_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 36 complete. v1.2.9+31. Build: [SUCCESS/FAILED]. English tour downloads: [YES/NO]. Translation API called: [YES/NO]. Russian tour in My Tours: [YES/NO]. Russian audio plays: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/08/2026 - A#35 — Mic Permission: Drop permission_handler, Use speech_to_text Natively (v1.2.9+30)

**Goal:** Fix mic permanently showing "Microphone Access Required" even when permission is granted in iOS Settings. Build v1.2.9+30, install on iPhone 16.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#34:**
- ✅ `voice_control_service.dart` — `startVoiceListening()` no longer uses `permission_handler` for the mic check. Instead calls `_speechToText.initialize()` fresh on every mic button press. `speech_to_text` talks to iOS natively and always reflects the current Settings state. If it returns `true` → voice starts. If `false` → "Open Settings" dialog.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+30

**Root cause (confirmed from A#34 log):**
`permission_handler` caches `permanentlyDenied` internally and never re-reads from iOS, even after the user enables the mic in Settings. Every call to `Permission.microphone.status` kept returning `permanentlyDenied` regardless of actual iOS Settings state. This is a known `permission_handler` iOS limitation.

**Why the new approach works:**
`speech_to_text.initialize()` calls iOS `SFSpeechRecognizer.requestAuthorization()` and `AVAudioSession` directly — it always reflects the live iOS permission state. No caching.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] **Delete Audioura from iPhone before installing** (hold icon → Remove App)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Mic Permission Flow

1. App opens → system mic dialog appears (first launch)
2. Tap **Allow**
3. Open a tour → tour player screen
4. Tap mic button
5. **Expected**: Voice recognition starts immediately — NO "Microphone Access Required" dialog

**If you tapped Deny at step 2:**
1. Tap mic button → "Microphone Access Required" dialog appears
2. Tap "Open Settings" → enable mic → return to app
3. Tap mic button again
4. **Expected**: Voice recognition starts — NO dialog this time

## Step 5 — Copy Results and Return

```
echo "Assignment 35 Results:" > ~/Desktop/a35_results.txt
echo "Date: $(date)" >> ~/Desktop/a35_results.txt
echo "Version: 1.2.9+30" >> ~/Desktop/a35_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a35_results.txt
echo "Voice starts after Allow (no dialog): [YES/NO]" >> ~/Desktop/a35_results.txt
echo "Voice starts after enabling in Settings: [YES/NO/NOT_TESTED]" >> ~/Desktop/a35_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a35_results.txt

cp ~/Desktop/a35_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 35 complete. v1.2.9+30. Build: [SUCCESS/FAILED]. Voice starts after Allow: [YES/NO]. Voice starts after Settings enable: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/08/2026 - A#34 — Mic Permission Status Fix (v1.2.9+29)

**Goal:** Fix mic permission check so that after user grants permission in iOS Settings, voice recognition actually starts instead of showing "Microphone Access Required" dialog again.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh`

**Time:** ~15-20 minutes

**What changed since A#33:**
- ✅ `voice_control_service.dart` — `startVoiceListening()` rewritten. Now: (1) reads current status, (2) if `denied` (not `permanentlyDenied`) calls `request()` once, (3) if still not granted after request → shows "Open Settings" dialog. Previously it was treating `denied` and `permanentlyDenied` identically, causing the dialog to appear even when permission was actually granted in Settings.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+29

**Root cause from A#33 log:**
```
First-launch mic permission request result: PermissionStatus.permanentlyDenied
Microphone permission status: PermissionStatus.denied
```
The old `permanentlyDenied` state from a previous install was cached by iOS. After reinstall, status showed as `denied` but any `request()` call returned `permanentlyDenied` silently. The fix: only show "Open Settings" after a `request()` attempt fails — never skip the request attempt.

**⚠️ IMPORTANT for A#34 test**: Delete app from iPhone before installing to get a clean permission state.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked
- [ ] Delete Audioura from iPhone before installing (hold icon → Remove App)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

## Step 4 — Test Mic Permission Flow

**Fresh install — permission never granted:**
1. App opens → system dialog "Audioura Would Like to Access the Microphone" appears
2. Tap **Allow**
3. Open a tour → tour player screen
4. Tap mic button (or triple-click volume)
5. **Expected**: Voice recognition starts immediately — NO "Microphone Access Required" dialog

**If you tap Deny in step 2:**
1. Tap mic button
2. **Expected**: "Microphone Access Required" dialog with "Open Settings" button
3. Tap "Open Settings" → enable mic in Settings → return to app
4. Tap mic button again
5. **Expected**: Voice recognition starts — dialog does NOT appear again

## Step 5 — Copy Results and Return

```
echo "Assignment 34 Results:" > ~/Desktop/a34_results.txt
echo "Date: $(date)" >> ~/Desktop/a34_results.txt
echo "Version: 1.2.9+29" >> ~/Desktop/a34_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a34_results.txt
echo "First-launch mic dialog shown: [YES/NO]" >> ~/Desktop/a34_results.txt
echo "Voice starts after Allow (no dialog): [YES/NO]" >> ~/Desktop/a34_results.txt
echo "Open Settings dialog on Deny: [YES/NO/NOT_TESTED]" >> ~/Desktop/a34_results.txt
echo "Voice starts after enabling in Settings: [YES/NO/NOT_TESTED]" >> ~/Desktop/a34_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a34_results.txt

cp ~/Desktop/a34_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

> "Assignment 34 complete. v1.2.9+29. Build: [SUCCESS/FAILED]. First-launch dialog: [YES/NO]. Voice starts after Allow: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/08/2026 - A#33 — Mic First-Launch Permission + Build Script Rename (v1.2.9+28)

**Goal:** Deploy mic permission first-launch fix. Build v1.2.9+28, install on iPhone 16, test that system mic dialog appears on first launch.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch.sh` ← NEW generic name

**Time:** ~15-20 minutes

**What changed since A#32:**
- ✅ `voice_control_service.dart` — `initialize()` no longer calls `Permission.microphone.request()`. New `requestMicPermissionOnFirstLaunch()` method: uses `SharedPreferences` flag `mic_permission_asked` to show the system dialog exactly once on first install.
- ✅ `voice_methods.dart` — `initializeVoiceControl()` now calls `requestMicPermissionOnFirstLaunch()` before `initialize()`. On subsequent launches, `startVoiceListening()` handles denied/permanentlyDenied as before.
- ✅ `pubspec.yaml` — version bumped to 1.2.9+28
- ✅ `build_install_launch.sh` — NEW generic build script (replaces `build_install_launch_a28.sh`). Old script kept as history — do not reuse.
- ✅ `copy_ios_fixes.sh` — updated to reference `build_install_launch.sh`

**Why the fix works:**
- Before: `initialize()` called `request()` at startup → iOS silently returned `permanentlyDenied` without showing a dialog (iOS only shows the dialog once; if already denied, it ignores the request)
- After: First launch → `requestMicPermissionOnFirstLaunch()` fires → system dialog shown → user taps Allow/Deny → flag set → never asked again at startup. Triple-click still triggers `startVoiceListening()` which handles `permanentlyDenied` with the "Open Settings" dialog.

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] `build_install_launch.sh` is on USB at `/Audioura/scripts/build_install_launch.sh`
- [ ] iPhone 16 connected and unlocked
- [ ] **IMPORTANT**: To test first-launch behavior, delete the app from iPhone before installing (hold icon → Remove App). This clears the `SharedPreferences` flag.

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch.sh
./build_install_launch.sh
```

**Note:** This is the renamed generic script. Same proven logic as `build_install_launch_a28.sh`.

## Step 4 — Test First-Launch Mic Permission

1. App opens (fresh install — app was deleted before)
2. **Expected immediately**: iOS system dialog "Audioura Would Like to Access the Microphone" appears
3. Tap **OK** / **Allow**
4. App continues loading normally

**If dialog did NOT appear:**
- Check if app was truly deleted before install (SharedPreferences flag may have persisted)
- Go to Settings > Audioura > Microphone — if toggle is already ON, permission was granted previously

## Step 5 — Test Triple-Click Still Works

1. Open a tour → tour player screen
2. Triple-click volume button (3 rapid presses within 500ms)
3. **Expected**: Voice listening starts (listening indicator shown)

## Step 6 — Test permanentlyDenied Dialog (optional)

Only if mic was denied in Step 4:
1. Triple-click volume button
2. **Expected**: "Microphone Access Required" dialog with "Open Settings" button
3. Tap "Open Settings" → iOS Settings > Audioura > Microphone

## Step 7 — Copy Results and Return

```
echo "Assignment 33 Results:" > ~/Desktop/a33_results.txt
echo "Date: $(date)" >> ~/Desktop/a33_results.txt
echo "Version: 1.2.9+28" >> ~/Desktop/a33_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a33_results.txt
echo "First-launch mic dialog shown: [YES/NO]" >> ~/Desktop/a33_results.txt
echo "Triple-click voice works: [YES/NO/NOT_TESTED]" >> ~/Desktop/a33_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a33_results.txt

cp ~/Desktop/a33_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 8 — Report Results

> "Assignment 33 complete. v1.2.9+28. Build: [SUCCESS/FAILED]. First-launch mic dialog: [YES/NO]. Triple-click works: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/06/2026 - A#32 — Mic Permission Fix + Download Spinner Fix (v1.2.9+27)

**Goal:** Deploy microphone permission fix and download spinner fix. Build v1.2.9+27, install on iPhone 16, test both fixes.

**Scripts:** `copy_ios_fixes.sh` then `build_install_launch_a28.sh`

**Time:** ~15-20 minutes

**What changed since A#31:**
- ✅ `voice_control_service.dart` — mic `permanentlyDenied` no longer silently fails; triggers actionable message
- ✅ `voice_methods.dart` — new `mic_permission_denied` action shows dialog with "Open Settings" button → takes user directly to iOS Settings > Audioura > Microphone
- ✅ `home_screen.dart` — download spinner fix: `_downloadMultipleTours` now calls `_downloadSingleTourSilent` (no internal dialog) so dialogs don't double-pop and leave a stuck spinner
- ✅ `pubspec.yaml` — version bumped to 1.2.9+27
- ✅ `copy_ios_fixes.sh` — updated to copy 13 files (added `voice_methods.dart`, `voice_control_service.dart`)

## Prerequisites

- [ ] USB contains updated files in `/Audioura/assets/`
- [ ] iPhone 16 connected and unlocked

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy Files (13 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes.sh
./copy_ios_fixes.sh
```

**Expected:** `✅ Successfully copied: 13 files`

## Step 3 — Build, Install, Launch

```
chmod +x build_install_launch_a28.sh
./build_install_launch_a28.sh
```

## Step 4 — Test Mic Permission Fix

**If microphone was previously denied (likely):**
1. Open app → tap Listen tab → tap any tour → tour player opens
2. Triple-click volume button (3 rapid presses)
3. **Expected**: Dialog appears: "Microphone Access Required" with "Open Settings" button
4. Tap "Open Settings" → iOS Settings opens at Audioura page
5. Enable Microphone toggle
6. Return to app → triple-click volume button again
7. **Expected**: Voice recognition starts (listening indicator)

**If microphone was never asked:**
1. Same steps — system permission dialog should appear on first triple-click
2. Tap Allow → voice recognition starts immediately

## Step 5 — Test Download Spinner Fix

1. Go to Home tab (map view)
2. Tap a cluster marker (purple with green badge = multiple tours)
3. Select 1-2 tours and tap Download Selected
4. **Expected**: Single spinner dialog appears, completes, disappears cleanly
5. Green snackbar "X tours downloaded" appears
6. **Expected**: NO stuck spinner after snackbar
7. Navigate away and back — no orphaned dialogs

**Also test single tour download:**
1. Tap a single blue marker → Download Tour
2. **Expected**: Spinner appears, completes, disappears, green snackbar shown

## Step 6 — Copy Results and Return

```
echo "Assignment 32 Results:" > ~/Desktop/a32_results.txt
echo "Date: $(date)" >> ~/Desktop/a32_results.txt
echo "Version: 1.2.9+27" >> ~/Desktop/a32_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a32_results.txt
echo "Mic permission dialog shown: [YES/NO]" >> ~/Desktop/a32_results.txt
echo "Open Settings button works: [YES/NO]" >> ~/Desktop/a32_results.txt
echo "Voice recognition after enabling: [YES/NO/NOT_TESTED]" >> ~/Desktop/a32_results.txt
echo "Download spinner clears: [YES/NO]" >> ~/Desktop/a32_results.txt
echo "Multi-tour download works: [YES/NO]" >> ~/Desktop/a32_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a32_results.txt

cp ~/Desktop/a32_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report Results

> "Assignment 32 complete. v1.2.9+27. Build: [SUCCESS/FAILED]. Mic dialog: [YES/NO]. Open Settings: [YES/NO]. Download spinner clears: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/01/2026 - A#31 — Deploy v1.2.9+26 (Keyboard Fix) + Build + Test

**Goal:** Copy all iOS files including the keyboard dismissal fix to Mac Mini, build v1.2.9+26, install on iPhone 16, and verify the keyboard dismissal works on Tour Generator screen.

**Scripts to run:** `copy_ios_fixes_v1_2_9_24.sh` then `build_install_launch_a28.sh`

**Scope:** FILE COPY + BUILD + INSTALL + KEYBOARD TEST

**Time:** ~15-20 minutes

**What changed since A#30:**
- ✅ `tour_generator_screen.dart` - iOS keyboard dismissal fix (v1.2.9+26)
  - `GestureDetector` wraps entire body — tap anywhere outside TextField dismisses keyboard
  - `keyboard_hide` IconButton as `suffixIcon` in both TextFields — visible dismiss button
  - `textInputAction: TextInputAction.done` on both TextFields — keyboard Return key says "Done"
- ✅ Version: 1.2.9+26
- ✅ Copy script updated to include `tour_generator_screen.dart` (now copies 11 files)

## Prerequisites

- [ ] USB stick contains updated files in `/Audioura/assets/lib/screens/tour_generator_screen.dart`
- [ ] `D:\Audioura\scripts\copy_ios_fixes_v1_2_9_24.sh` updated (now copies 11 files)
- [ ] iPhone 16 (UDID `F9D6F807-D301-59EE-B574-5747D617D82C`) connected and unlocked

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy All Files (11 files)

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes_v1_2_9_24.sh
./copy_ios_fixes_v1_2_9_24.sh
```

**Expected Output:**
```
✅ Successfully copied: 11 files
❌ Failed to copy: 0 files
🎉 ALL FILES COPIED SUCCESSFULLY
```

**If `tour_generator_screen.dart` fails:** Check that `D:\Audioura\assets\lib\screens\tour_generator_screen.dart` was copied to USB before ejecting.

## Step 3 — Build, Install, and Launch v1.2.9+26

```
chmod +x build_install_launch_a28.sh
./build_install_launch_a28.sh
```

**Expected Results:**
- **Build**: SUCCESS (exit code 0)
- **Install**: SUCCESS (exit code 0)
- **Launch**: SUCCESS
- **Verdict**: SUCCESS or AMBIGUOUS (app running)

## Step 4 — Test Keyboard Dismissal on iPhone 16

### **Test 1: Tap Outside Dismisses Keyboard**
1. Open app → tap **Tour Generator** tab (bottom nav)
2. Tap the text input field — keyboard appears
3. Tap anywhere on the screen OUTSIDE the text field
4. **Expected**: Keyboard dismisses immediately
5. **Expected**: You can now tap other bottom nav tabs without keyboard blocking

### **Test 2: keyboard_hide Button Dismisses Keyboard**
1. Tap the text input field — keyboard appears
2. Look for the keyboard icon (⌨️) inside the right side of the text field
3. Tap the keyboard icon
4. **Expected**: Keyboard dismisses immediately

### **Test 3: Done Key Dismisses Keyboard**
1. Tap the text input field — keyboard appears
2. Look at the keyboard — bottom-right key should say **"Done"** (not "Return")
3. Tap **Done**
4. **Expected**: Keyboard dismisses immediately

### **Test 4: Navigation Not Blocked**
1. Tap the text input field — keyboard appears
2. WITHOUT dismissing keyboard, tap a different bottom nav tab (e.g. Home)
3. **Expected**: App navigates away (keyboard auto-dismisses on navigation)
4. Navigate back to Tour Generator
5. **Expected**: No stuck keyboard

### **Test 5: Newsletter URL Field (if visible)**
1. Switch to Newsletter/Audio mode if available
2. Tap the Newsletter URL text field
3. Repeat Tests 1-3 for this field
4. **Expected**: Same keyboard dismissal behavior

## Step 5 — Copy Results and Return

```
echo "Assignment 31 Keyboard Fix Test Results:" > ~/Desktop/a31_results.txt
echo "Date: $(date)" >> ~/Desktop/a31_results.txt
echo "Version: 1.2.9+26" >> ~/Desktop/a31_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a31_results.txt
echo "Tap outside dismisses keyboard: [YES/NO]" >> ~/Desktop/a31_results.txt
echo "keyboard_hide button works: [YES/NO]" >> ~/Desktop/a31_results.txt
echo "Done key works: [YES/NO]" >> ~/Desktop/a31_results.txt
echo "Navigation not blocked: [YES/NO]" >> ~/Desktop/a31_results.txt
echo "Newsletter URL field keyboard: [YES/NO/NOT_TESTED]" >> ~/Desktop/a31_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a31_results.txt

cp ~/Desktop/a31_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

Switch back to Windows and report:

> "Assignment 31 complete. v1.2.9+26 deployed. Build: [SUCCESS/FAILED]. Tap outside: [YES/NO]. keyboard_hide button: [YES/NO]. Done key: [YES/NO]. Navigation unblocked: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 05/01/2026 - A#30 — Restore Full Feature Parity + Build v1.2.9+25 + Test

**Goal:** Copy all restored iOS-compatible files (full home_screen.dart + all services/widgets) to Mac Mini, build v1.2.9+25, install on iPhone 16, and verify all features work including tour clustering, location search, newsletter system, and subscription features.

**Script to run:** `copy_ios_fixes_v1_2_9_24.sh` followed by `build_install_launch_a28.sh`

**Scope:** **FILE COPY + BUILD + INSTALL + FEATURE TESTING** - Full feature parity deployment.

**Time:** ~15-20 minutes (file copy + build + install + testing).

**What changed since A#29:**
- ✅ `home_screen.dart` - FULL version restored (tour clustering, location search, tour search, newsletter system, treat view, language selector)
- ✅ `device_service.dart` - Fixed for iOS (`Platform.isIOS` + `iosInfo.identifierForVendor` instead of Android-only `androidInfo`)
- ✅ `subscription_service.dart` - Restored (encryption key management, Diffie-Hellman key exchange)
- ✅ `subscription_encryption_service.dart` - Restored (AES-128-CBC encryption)
- ✅ `translation_service.dart` - Restored
- ✅ `language_selector.dart` - Restored (multi-language chip selector)
- ✅ `subscription_credential_dialog.dart` - Restored (paywall credential dialog)
- ✅ `pubspec.yaml` - Fonts section removed (was causing build failure)
- ✅ Version: 1.2.9+25

**Root cause of A#29 build failure:** `pubspec.yaml` declared `fonts/Roboto-Regular.ttf` and `fonts/Roboto-Bold.ttf` which don't exist. Fixed by removing the fonts section (Flutter Material Design includes Roboto natively).

## Prerequisites

- [ ] USB stick contains updated files in `/Audioura/assets/`
- [ ] `D:\Audioura\scripts\copy_ios_fixes_v1_2_9_24.sh` updated (now copies 10 files)
- [ ] `D:\Audioura\scripts\build_install_launch_a28.sh` exists (proven working)
- [ ] iPhone 16 (UDID `F9D6F807-D301-59EE-B574-5747D617D82C`) connected and unlocked

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy All Restored Files

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes_v1_2_9_24.sh
./copy_ios_fixes_v1_2_9_24.sh
```

**Expected Output:**
```
✅ Successfully copied: 10 files
❌ Failed to copy: 0 files
🎉 ALL FILES COPIED SUCCESSFULLY
```

**Files being copied:**
- `lib/screens/about_screen.dart`
- `lib/screens/home_screen.dart` (FULL version)
- `lib/services/device_service.dart` (iOS-compatible)
- `lib/services/subscription_service.dart`
- `lib/services/subscription_encryption_service.dart`
- `lib/services/translation_service.dart`
- `lib/widgets/language_selector.dart`
- `lib/widgets/subscription_credential_dialog.dart`
- `pubspec.yaml` (fonts section removed)
- `ios/Runner/Info.plist`

## Step 3 — Build, Install, and Launch v1.2.9+25

```
chmod +x build_install_launch_a28.sh
./build_install_launch_a28.sh
```

**Expected Results:**
- **Build**: SUCCESS (exit code 0) - no missing asset errors
- **Install**: SUCCESS (exit code 0) on iPhone 16
- **Launch**: SUCCESS - app visible and running
- **Verdict**: SUCCESS

**If build fails with asset error:** Check that `pubspec.yaml` fonts section was removed correctly.
**If build fails with missing import:** Check that all 10 files were copied successfully in Step 2.

## Step 4 — Test Restored Features on iPhone 16

### **Test 1: Basic Launch + Location**
1. App opens without crash
2. Location permission dialog appears
3. Map loads with tour markers
4. Tour markers show clustering (purple marker with green dot badge when multiple tours nearby)

### **Test 2: Location Search**
1. Tap search icon in app bar
2. Type a city name (e.g. "Paris, France")
3. Map should move to that location
4. Tours for that area should load
5. Orange search marker should appear

### **Test 3: Tour Search**
1. Tap tour search icon in app bar
2. Type a search term (e.g. "Boston")
3. Results should appear with checkboxes
4. Language selector should show (English, Spanish, French, etc.)
5. Select tours and tap Download

### **Test 4: Newsletter Mode (Audio)**
1. Switch app mode to Audio
2. Newsletter list should load from server
3. Tap a newsletter to see article list
4. Language selector should appear in article dialog

### **Test 5: About Screen**
1. Device info displays correctly (iOS device name, OS version)
2. Settings persist after switching tabs

## Step 5 — Copy Results and Return

```
echo "Assignment 30 Feature Parity Test Results:" > ~/Desktop/a30_results.txt
echo "Date: $(date)" >> ~/Desktop/a30_results.txt
echo "Version: 1.2.9+25" >> ~/Desktop/a30_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a30_results.txt
echo "Tour clustering: [WORKING/ERROR]" >> ~/Desktop/a30_results.txt
echo "Location search: [WORKING/ERROR]" >> ~/Desktop/a30_results.txt
echo "Tour search: [WORKING/ERROR]" >> ~/Desktop/a30_results.txt
echo "Newsletter mode: [WORKING/ERROR]" >> ~/Desktop/a30_results.txt
echo "Language selector: [WORKING/ERROR]" >> ~/Desktop/a30_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a30_results.txt

cp ~/Desktop/a30_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

Switch back to Windows and report:

> "Assignment 30 complete. v1.2.9+25 deployed. Build: [SUCCESS/FAILED]. Tour clustering: [WORKING/ERROR]. Location search: [WORKING/ERROR]. Tour search: [WORKING/ERROR]. Newsletter mode: [WORKING/ERROR]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 04/30/2026 12:15 - A#29 — Copy iOS Fixes v1.2.9+24 + Build + Install + Test

**Goal:** Copy iOS fixes (device info, settings persistence, location permissions) to Mac Mini, build v1.2.9+24, install on iPhone 16, and test all runtime functionality.

**Script to run:** `copy_ios_fixes_v1_2_9_24.sh` followed by `build_install_launch_a28.sh`

**Scope:** **FILE COPY + BUILD + INSTALL + RUNTIME TESTING** - Complete iOS fixes deployment and validation.

**Time:** ~10-15 minutes (file copy + build + install + testing).

**iOS Fixes Included:**
- ✅ iOS device info support (about_screen.dart)
- ✅ Settings persistence fix (about_screen.dart) 
- ✅ Location permission fix (home_screen.dart)
- ✅ Version updated to 1.2.9+24 (pubspec.yaml)
- ✅ Location permission descriptions (Info.plist)

## Prerequisites

- [ ] `D:\Audioura\scripts\copy_ios_fixes_v1_2_9_24.sh` exists
- [ ] `D:\Audioura\scripts\build_install_launch_a28.sh` exists
- [ ] USB stick contains updated source files in `/AudioTours/development/audio_tour_app/`
- [ ] iPhone 16 (UDID `F9D6F807-D301-59EE-B574-5747D617D82C`) connected and unlocked
- [ ] Assignment 27 completed successfully (baseConfigurationReference fix in place)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Copy iOS Fixes v1.2.9+24

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x copy_ios_fixes_v1_2_9_24.sh
./copy_ios_fixes_v1_2_9_24.sh
```

**Expected Output:**
```
✅ Successfully copied: 4 files
❌ Failed to copy: 0 files
🎉 ALL FILES COPIED SUCCESSFULLY

iOS Fixes v1.2.9+24 applied:
- ✅ iOS device info support (about_screen.dart)
- ✅ Settings persistence fix (about_screen.dart)
- ✅ Location permission fix (home_screen.dart)
- ✅ Version updated to 1.2.9+24 (pubspec.yaml)
- ✅ Location permission descriptions (Info.plist)

Ready for Assignment 28 Path A execution
```

**If copy fails:** Check USB drive mounting and file paths, retry script.

## Step 3 — Build, Install, and Launch v1.2.9+24

```
chmod +x build_install_launch_a28.sh
./build_install_launch_a28.sh
```

**Expected Results:**
- **Build**: SUCCESS (exit code 0) with iOS device info and location fixes
- **Install**: SUCCESS (exit code 0) on iPhone 16
- **Launch**: SUCCESS - app visible and running
- **Verdict**: SUCCESS (no crashes, process running at +15s)

## Step 4 — Test iOS Fixes on iPhone 16

### **Test 1: About Screen Device Info**
1. **Open Audioura** on iPhone 16
2. **Navigate to About tab**
3. **Verify all fields display correctly:**
   - Version: 1.2.9
   - Build: 24
   - User ID: USER-xxxxxxxx
   - Device: iPhone iPhone16,1 (or similar)
   - OS: iOS 18.3.1 (or current version)
4. **Expected**: No "Error loading" messages

### **Test 2: Settings Persistence**
1. **In About tab, change Server IP** to test value (e.g., 192.168.0.999)
2. **Tap Save** - should show green success message
3. **Switch to Home tab** then back to About tab
4. **Verify Server IP field** shows the test value (not default)
5. **Change back to correct IP** (192.168.0.218) and save
6. **Expected**: Settings persist between screen switches

### **Test 3: Location Permission**
1. **Navigate to Home tab** (Tours mode)
2. **App should request location permission** with dialog:
   - "Audioura needs location access to find nearby tours..."
3. **Tap Allow** when prompted
4. **Verify location services work:**
   - Map should center on current location
   - Red user location marker should appear
   - Tours should load for current area
5. **Expected**: Location permission granted and GPS features working

### **Test 4: Core App Functionality**
1. **Test network connectivity** - tours should load from 192.168.0.218:5005
2. **Test map interaction** - zoom, pan, marker taps
3. **Test mode switching** - Tours ↔ Audio modes
4. **Test basic navigation** - all tabs accessible
5. **Expected**: All core features working normally

## Step 5 — Copy Results and Return

```
echo "Assignment 29 iOS Fixes Test Results:" > ~/Desktop/a29_ios_fixes_test.txt
echo "Date: $(date)" >> ~/Desktop/a29_ios_fixes_test.txt
echo "Version: 1.2.9+24" >> ~/Desktop/a29_ios_fixes_test.txt
echo "About Screen Device Info: [WORKING/ERROR - describe]" >> ~/Desktop/a29_ios_fixes_test.txt
echo "Settings Persistence: [WORKING/ERROR - describe]" >> ~/Desktop/a29_ios_fixes_test.txt
echo "Location Permission: [GRANTED/DENIED - describe]" >> ~/Desktop/a29_ios_fixes_test.txt
echo "Core Functionality: [WORKING/ISSUES - describe]" >> ~/Desktop/a29_ios_fixes_test.txt
echo "Overall Status: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a29_ios_fixes_test.txt

cp ~/Desktop/a29_ios_fixes_test.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report Results

Switch back to Windows and report:

> "Assignment 29 complete. iOS Fixes v1.2.9+24 deployed. About screen: [WORKING/ERROR]. Settings persistence: [WORKING/ERROR]. Location permission: [GRANTED/DENIED]. Core functionality: [WORKING/ISSUES]. Overall: [SUCCESS/PARTIAL/FAILED]."

---

# T: 04/29/2026 17:02 - A#28 — Build, Install, Launch (CORRECTED FINAL STEP)

**Goal:** With Branch B confirmed fixed in A27 (build exit 0, `FLUTTER_BUILD_DIR=build`, Runner.app produced), now produce a properly *signed* Runner.app via Xcode's automatic-signing pipeline, install on iPhone 16, launch, and capture evidence about whether the app stays running or crashes with the historical CwlCatchException dyld error.

**Script to run:** `build_install_launch_a28.sh`

**Scope:** **BUILD-WITH-CODESIGN + INSTALL + LAUNCH + EVIDENCE.** Single composite operation that the iOS toolchain has been doing reliably for years — we delegate signing/profile/entitlements to `flutter build ios --release` (the exact path that worked for A18's drag-and-drop install) instead of trying to imitate it manually.

**Time:** ~7–12 minutes (build with sign + install + 25s monitoring + crash scrape).

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-04-29. Drafted directly per Sir Michael's preference — no Amazon-Q intermediary — and self-reviewed before USB transfer (lesson V2).

## ⚠️ Supersedes — please use this, not the inline A28

`D:\Audioura\assignments\mac_mini_assignments.md` (lines 701–850) and `D:\Audioura\scripts\sign_install_a28.sh` are an **earlier Amazon-Q draft of A28** that this assignment **REPLACES**. The earlier draft has four critical issues — discussed in the project log under "Why this approach (vs Amazon-Q's A28)" below. **Do not run `sign_install_a28.sh`.** Run `build_install_launch_a28.sh` only.

Sir Michael deletes Mac/USB files himself per Rule 4; both files have been intentionally left in place as history.

## Background

A27 hit Case A: build exit 0, `FLUTTER_BUILD_DIR_PRESENT_A27=YES` (value `build`), `RELEASE_SENTINEL_PROPAGATED_A27=YES`. The Branch B fix is fully validated. `Runner.app` was produced at `~/Development/AudioTours/development/audio_tour_app/build/ios/iphoneos/Runner.app` with `Frameworks/CwlCatchException.framework` correctly embedded. RunnerTests `baseConfigurationReference` was correctly untouched.

But A27 used `flutter build ios --release --no-codesign`, which means the resulting `Runner.app`:

- has **no** `embedded.mobileprovision`
- has **no** compiled `Runner.app.xcent` (the runtime entitlements blob with `application-identifier`, `team-identifier`, `get-task-allow=true`, `keychain-access-groups`)
- is **not signed** by any team identity

That's exactly right for verifying the build pipeline is healthy, but wrong for installing on a real device. iOS install requires three things together (the project log captures this as the "iOS Installation 3-step sequence"):

1. **Code signature** — every framework + the main binary signed by an Apple Development identity for team `4HGRU6TKGQ`.
2. **Provisioning profile** embedded as `Runner.app/embedded.mobileprovision`, listing the device UDID.
3. **Entitlements** compiled into a `.xcent` blob with `application-identifier = 4HGRU6TKGQ.com.glikfamily.audioura`.

A28 produces all three by re-running the build *without* `--no-codesign`. Xcode's automatic-signing pipeline handles all three steps in one shot — the exact pipeline that worked for A18's drag-and-drop install — so we don't have to reimplement provisioning-profile lookup and entitlement-blob generation manually in bash.

## Why this approach (vs Amazon-Q's A28)

Amazon-Q's `sign_install_a28.sh` tried to take the existing `--no-codesign` Runner.app and *re-sign* it manually. That approach has four bugs that would have blocked install:

1. It never embeds `Runner.app/embedded.mobileprovision`. `xcrun devicectl device install app` fails with `0xe8008015`.
2. `--entitlements $PROJECT_DIR/ios/Runner/Runner.entitlements` points at the human-authored input file, not the compiled `.xcent` blob with `application-identifier`. Install fails with under-specified entitlements.
3. If install fails, the script continues to `process launch` an app that isn't on the device. Same V1 anti-pattern that A26 had ("verification must HALT, not just print").
4. The "launch test" is `xcrun devicectl device process launch` — exit 0 means the launch *command* dispatched, not that the app stayed running. The CwlCatchException crash happens ~0.5s after launch (dyld load time). Amazon-Q's script captures zero evidence of this — it relies entirely on Sir Michael eyeballing the iPhone screen.

A28 (Path A) avoids all four:

1. Build with codesign → Xcode embeds the profile.
2. Build with codesign → Xcode generates the proper `.xcent`.
3. HALTs (exit 1) on every failure: build, codesign verify, install, with no fall-through.
4. Captures process list at +5s and +15s post-launch and scrapes `~/Library/Logs/CrashReporter/MobileDevice/` for any *new* crash report appearing after launch (with a baseline taken pre-launch). The dyld error string `Library not loaded ... CwlCatchException` is grep'd in both the launch log and any new crash file.

## Environmental prerequisites (NEW for A28)

These are the only things the script can't fully validate up front. Confirm before running:

- [ ] **Xcode automatic signing is set up** — at some point (likely before A18) Xcode UI was opened with the Audioura project, signed in to the Apple ID for team `4HGRU6TKGQ`, and let auto-resolve a Development profile. A18's successful drag-and-drop install confirms this was true ~3 days ago. If an Apple ID password expiry, certificate expiry, or new device addition has happened since, automatic signing may need a one-time refresh in Xcode UI.
- [ ] **Developer Mode is ON** on iPhone 16. Settings → Privacy & Security → Developer Mode. iOS 16+ requires this for any devicectl-launched app. If off, install may succeed but launch fails.
- [ ] **iPhone 16 is trust-paired with this Mac** — the "Trust This Computer" dialog has been accepted for this Mac at some point, and the iPhone is unlocked when running the script.
- [ ] **An Apple Development codesigning identity for team `4HGRU6TKGQ` is in the Mac's keychain.** The script runs `security find-identity -v -p codesigning` in pre-flight and prints the result; if no `Apple Development` line for the team appears, the build is likely to fail with "No matching profiles".

The script tolerates the device-connectivity probe failing (warns + continues, since `devicectl list devices` can flake without affecting later commands), but a missing signing identity will surface as a build failure with a clear `flutter build` error message — not silent.

# 🔧 DEBUGGING SECTION - iPhone Detection Issues

## When iPhone Detection Fails
**Symptoms**: `Error Domain=com.apple.dt.CoreDeviceError Code=1002 "No provider was found."`
**Or**: `FATAL: iPhone 16 not connected` (even when visible in Finder)

### **Recovery Steps** (Try in order):

#### **Step 1: Restart Mac Mini** (Safest approach)
```bash
sudo shutdown -r now
```
This cleanly restarts all system services including CoreDevice.

#### **Step 2: Manual Service Recovery** (If restart not preferred)
```bash
# Check available CoreDevice services:
sudo launchctl list | grep -i device

# Try to load CoreDevice services:
sudo launchctl load /System/Library/LaunchDaemons/com.apple.CoreDevice*

# Restart related services:
sudo launchctl kickstart -k system/com.apple.usbd
sudo launchctl kickstart -k system/com.apple.mobile.lockdown
```

#### **Step 3: Check if iPhone is Actually Detected**
```bash
# Check USB devices (should show iPhone):
system_profiler SPUSBDataType | grep -i iphone

# Check if Xcode can see devices:
xcrun devicectl list devices

# Alternative device detection:
xcrun simctl list devices | grep -i iphone
```

#### **Step 4: Physical Reconnection**
1. **Unplug iPhone from Mac Mini**
2. **Wait 10 seconds**
3. **Plug iPhone back in**
4. **Unlock iPhone and check for trust dialog**
5. **Tap "Trust" if dialog appears**

#### **Step 5: iPhone Developer Mode Verification**
**On iPhone 16:**
1. **Settings → Privacy & Security → Developer Mode**
2. **Toggle OFF then ON** (even if already enabled)
3. **Restart iPhone** after toggling
4. **Reconnect to Mac Mini**

### **Common Root Causes**:
- **Trust relationship** between iPhone and Mac Mini broken
- **iPhone Developer Mode** not properly enabled
- **CoreDevice services** crashed or misconfigured
- **USB connection** intermittent

**Note**: If you killed CoreDevice processes with `pkill`, restart Mac Mini for clean recovery.

## ⚠️ TROUBLESHOOTING: iPhone Not Found Error

**If you encounter**: `Error Domain=com.apple.dt.CoreDeviceError Code=1002 "No provider was found."`
**Or**: `FATAL: iPhone 16 (UDID: F9D6F807-D301-59EE-B574-5747D617D82C) not connected`

**Even when iPhone appears in Finder**, try these solutions in order:

### **Solution 1: Trust/Pairing Issue**
1. **Unlock iPhone 16** and keep it unlocked during script execution
2. **Reconnect USB cable** (unplug and replug into Mac Mini)
3. **Check for "Trust This Computer" dialog** on iPhone screen - tap "Trust"
4. **Enter iPhone passcode** when prompted
5. **Wait 10 seconds** then retry the script

### **Solution 2: Restart Core Device Services**
```bash
# On Mac Mini terminal:
sudo pkill -f CoreDevice
sudo launchctl kickstart -k system/com.apple.CoreDevice.CoreDeviceService
# Wait 15 seconds then retry script
```

### **Solution 3: Check Xcode Command Line Tools**
```bash
# Verify and reset Xcode command line tools:
xcode-select --print-path
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
# Retry script after this command
```

### **Solution 4: Alternative Device Detection Test**
```bash
# Test if iPhone is detected by system:
system_profiler SPUSBDataType | grep -A 10 iPhone
instruments -s devices | grep iPhone
# If iPhone appears in either output, trust/pairing is the issue
```

### **Solution 5: Developer Mode Verification**
**On iPhone 16:**
1. **Settings → Privacy & Security → Developer Mode**
2. **Toggle OFF then ON** (even if already enabled)
3. **Restart iPhone** after toggling
4. **Reconnect to Mac Mini** and retry script

**Note**: The `CoreDeviceError Code=1002` typically indicates trust/pairing issues, not physical connection problems. Solutions 1-3 resolve 90% of cases.

## Standard prerequisites

- [ ] `D:\Audioura\scripts\build_install_launch_a28.sh` exists (Windows side, copied to USB)
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `F9D6F807-D301-59EE-B574-5747D617D82C`) plugged in and unlocked
- [ ] A27 completed successfully — `project.pbxproj` shows Runner Debug + Release wired to `Flutter/{Debug,Release}.xcconfig`. The script verifies this in Step 0; HALTs if A27 has been reverted.
- [ ] No background `xcodebuild` or Xcode UI build in progress

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x build_install_launch_a28.sh
```

## Step 3 — Run the script

```
./build_install_launch_a28.sh
```

**Do NOT wrap with `script ~/Desktop/...`.** The script handles its own output capture via `exec > >(tee ~/Desktop/full_a28_session.txt) 2>&1` (B1).

**What the script does (in order):**

1. **STEP 0 — Pre-flight checks.** Validates project dir + pbxproj exist. Confirms A27's `baseConfigurationReference` fix is still in place for both Debug and Release (HALTs if reverted). Lists codesigning identities (warn-only). Lists devicectl devices (warn-only). Snapshots existing crash report files in `~/Library/Logs/CrashReporter/MobileDevice/` so we can detect any NEW crashes from this run.
2. **STEP 1 — `flutter build ios --release` (WITH codesign).** No `--no-codesign` flag this time. Xcode's automatic-signing pipeline embeds the provisioning profile, generates the `.xcent`, and signs every framework + the main bundle. Build exit captured via `${PIPESTATUS[0]}`. HALTs on non-zero exit and prints common-cause hints (no matching profile, bundle ID mismatch, signing required, etc.).
3. **STEP 2 — Verify the signed Runner.app.** Confirms `embedded.mobileprovision` is present (HALTs if missing — that would mean the build was somehow still `--no-codesign`). Dumps `embedded.mobileprovision` metadata (TeamIdentifier, AppIDName, ExpirationDate, Name), main-bundle codesign info, codesign verify, framework codesign info, compiled entitlements. HALTs if `codesign --verify --verbose=2` fails.
4. **STEP 3 — `xcrun devicectl device install app`.** Streams output to a tee'd log; captures exit via `${PIPESTATUS[0]}`. HALTs on non-zero exit and prints common-cause hints (`0xe8008015`, `0xe800801c`, Developer Mode disabled, device locked, trust not established).
5. **STEP 4 — Launch + monitor.** Captures pre-launch process list (both `process list` and `info processes` devicectl variants for syntax tolerance across Xcode versions). Launches the app via `xcrun devicectl device process launch`. Waits 5 seconds, captures process list, greps for `audioura` / bundle ID — counts as `RUNNING_5S`. Waits 10 more seconds (total 15s), captures again, greps — counts as `RUNNING_15S`. The 15s window is generous: the historical CwlCatchException crash happens within ~0.5s of launch, so absence at +15s strongly indicates the crash recurred.
6. **STEP 5 — Crash report scrape.** Waits 10 more seconds for any device-side crash report to sync to the Mac. Diffs the post-launch `~/Library/Logs/CrashReporter/MobileDevice/` listing against the pre-launch baseline; captures the names of any NEW files; prints the first 80 lines of each. Grep's both the launch log and any new crash file for the literal string `Library not loaded ... CwlCatchException`.
7. **STEP 6 — Final verdict.** Combines the +15s process-presence count with the new-crash-file count into one of four buckets (table below); writes `~/Desktop/a28_final_verdict.txt`.
8. **STEP 7 — Copy results to USB + local backup** (B2 + M5 — real double quotes around USB path, visible per-file errors, parallel local backup).

**Run time:** ~7–12 minutes total (build is the long part; monitoring is exactly 25s post-launch).

## Step 4 — Headline result to watch for

The script prints a final on-screen verdict block. The verdict is one of four values, derived from two counts:

| Process at +15s | New crash files | Verdict | Reading |
|---|---|---|---|
| ≥ 1 | 0 | **SUCCESS** | App launched, still running, no new crash. iOS barrier eliminated. |
| 0   | ≥ 1 | **CRASHED** | App not running AND a fresh crash report exists. Look at the printed crash file head — if it says `Library not loaded ... CwlCatchException`, the framework is present in the bundle but rpath-unresolvable for the main binary (would need a separate rpath / Embed-and-Sign-mode investigation). |
| 0   | 0 | **AMBIGUOUS** | Most likely the devicectl process-list output didn't include `audioura` / bundle ID in a form our grep matched (exec name might be `Runner`). Check the iPhone screen — if Audioura is visibly running, the verdict is effectively SUCCESS. |
| ≥ 1 | ≥ 1 | **MIXED** | Process is in list AND a crash file appeared. Most likely an OLD crash file synced just now. Cross-reference the crash file's timestamp + bundle ID with the launch epoch. |

Always glance at the iPhone screen as a sanity backstop, especially for AMBIGUOUS / MIXED.

## Step 5 — No cleanup verification this time

Unlike A25/A27, **A28 makes no temporary modifications** that need reverting. There's no cleanup trap, no sentinels, no printenv hook. The build's signed `Runner.app` and the installed app on the iPhone are intentional, durable outputs. If the install succeeds and the app crashes, the failed install is recoverable: hold-press the Audioura icon on the iPhone home screen and tap "Remove App", or run `xcrun devicectl device uninstall app --device 00008140-000558A902BA801C com.glikfamily.audioura`.

## Step 6 — Eject USB and return

```
diskutil eject "/Volumes/USB DISK"
```

## Step 7 — Report to Claude

Switch back to Windows. Open a new Cowork session with this name:

> "Audioura Build and Start #5"

…and report the verdict + the four counts:

> "Assignment 28 complete. VERDICT: [SUCCESS / CRASHED / AMBIGUOUS / MIXED]. Build exit: [N]. Install exit: [N]. Process matches at +5s/+15s: [N]/[N]. New crash files: [N]. iPhone screen: [Audioura visible and responsive / black / springboard / crashed]."

Plus any notable observations from the terminal output, especially any line of the form `Library not loaded ... CwlCatchException` or any unfamiliar dyld error.

## Result files (all timestamped) on USB

```
full_a28_session_<ts>.txt              (full terminal recording -- the master log)
a28_final_verdict_<ts>.txt             (THE HEADLINE: build/install/launch exit + 2 counts + verdict)
a28_signed_app_verification_<ts>.txt   (embedded.mobileprovision metadata + codesign output + entitlements)
flutter_build_a28_<ts>.log             (flutter build with codesign output)
a28_install_<ts>.log                   (devicectl install output)
a28_launch_<ts>.log                    (devicectl process launch output)
a28_proclist_before_<ts>.txt           (pre-launch device process list)
a28_proclist_5s_<ts>.txt               (process list +5s after launch)
a28_proclist_15s_<ts>.txt              (process list +15s after launch)
a28_new_crashes_list_<ts>.txt          (paths of any NEW crash report files since launch baseline)
a28_crash_<ts>_<basename>              (any new crash report file copied verbatim, if present)
```

Local backup copies in `~/Desktop/a28_results/`.

## Rollback / cleanup

If the build/install/launch fails, the install state on the iPhone is the only thing that needs cleanup. You can either:

- **Leave it.** A failed install just leaves no Audioura icon on the iPhone — nothing to undo.
- **Remove a partially-installed app.** Hold-press the Audioura icon on the iPhone home screen → "Remove App". Or:
  ```
  xcrun devicectl device uninstall app --device 00008140-000558A902BA801C com.glikfamily.audioura
  ```

`project.pbxproj` is NOT touched by A28 — A27's edit remains in place regardless of A28's outcome. The pre-A27 backup at `project.pbxproj.backup_a27_20260429_160121` on the Mac Mini is also untouched.

If the build fails because Xcode automatic signing has expired/desynced, the recovery is: open the project in Xcode UI (`open ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcworkspace`), let the Signing & Capabilities tab auto-fix, then re-run this script.

## Safety notes

- **No file modifications.** Unlike A25 and A27, A28 modifies no source files, no Flutter SDK files, no xcconfigs. The only things changing are (a) the build artifact (`build/ios/iphoneos/Runner.app` is regenerated with codesign instead of `--no-codesign`), and (b) the iPhone's installed-apps list.
- **HALT-on-failure throughout.** Every step that can fail (build, codesign-verify, install) is followed immediately by an `if [ "$EXIT" -ne 0 ]; then ... exit 1; fi` block that copies results to USB before exiting. (V1 lesson — verification must halt, not just print.)
- **Signing is delegated to Xcode.** A28 makes zero direct `codesign --sign` calls. This is intentional: getting framework-by-framework codesign right (especially for nested signed content, dylib siblings, entitlements blob synthesis) is exactly the failure mode that broke Amazon-Q's draft. Letting `flutter build` invoke `xcodebuild` lets Apple's pipeline do its job.
- **Best-effort process-list parsing.** The script captures both `xcrun devicectl device process list` AND `xcrun devicectl device info processes` outputs; greps both. If the output format changes in a future Xcode update such that our grep misses, the verdict is AMBIGUOUS — recoverable by checking the iPhone screen.

## Bash bug-fixes from A24/A25/A26 review baked in upfront

- **B1:** `exec > >(tee ...) 2>&1` for output capture (no `script` from inside script body)
- **B2:** USB `cp` uses real double quotes around the path (it contains a space), visible per-file errors
- **B3:** single-quoted grep patterns for literal text
- **B4:** N/A (no line insertion in this script)
- **B5:** `"$HOME/..."` not `"~/..."` inside double quotes
- **B6:** `${PIPESTATUS[0]}` for flutter build / install / launch exit codes after the `tee` pipe
- **B7:** N/A (no sed-with-shell-variable in this script)
- **V1:** verification HALTS (`exit 1`) on every failure, with USB+local backup copy before exiting
- **V2:** Claude reviewed this script before USB transfer
- **M1:** system-date drift check
- **M3:** `cd` only for the flutter build (the one acceptable absolute-path exception)
- **M5:** local backup directory fallback

## Next step (preview, not part of A28)

**If A28 lands SUCCESS:** the iOS development barrier is fully eliminated. The next milestone is feature parity verification — testing core Audioura functionality on iPhone (tour loading, GPS triggering, audio playbook, voice activation, network connectivity to the local backend at `192.168.0.136:5002/5004`). That's a manual checklist + maybe an A29 to capture the first sample tour run.

**If A28 lands CRASHED with `Library not loaded ... CwlCatchException`:** this would mean the framework is *embedded* in `Frameworks/` (A27 evidence confirmed it is) but is not *rpath-resolvable* by the main `Runner` binary at load time. That's a different bug from Branch B — likely a `LD_RUNPATH_SEARCH_PATHS` or "Embed & Sign" vs "Embed Without Signing" issue in the Runner target's framework search paths or General > Frameworks list. A29 would diagnose with `otool -L Runner.app/Runner` and the embedded-frameworks build phase inspection.

**If A28 lands CRASHED with a different error:** capture the crash file head and we'll diagnose case-by-case.

**If A28 lands AMBIGUOUS:** if the iPhone screen shows Audioura running, treat as SUCCESS. If it doesn't, A29 would narrow the gap — likely by adding `idevicesyslog` capture (if the Mac has libimobiledevice installed) for richer console capture during launch.

**Status**: ✅ COMPLETED - Assignment 28 SUCCESS - App running on iPhone 16

---

# T: 04/29/2026 15:47 - A#27 — Fix project.pbxproj baseConfigurationReference (Branch B, Python-based)

**Goal:** Re-attempt the Branch B fix that A26 failed to apply, this time using Python (not sed) anchored on the specific Runner config UUIDs. After the edit, run `flutter build ios --release --no-codesign` and capture both build outcome and a fresh printenv from inside the Run Script Phase to prove (or disprove) that `FLUTTER_BUILD_DIR` now reaches the build env.

**Script to run:** `fix_baseconfig_a27.sh`

**Scope:** **TARGETED FIX + EVIDENCE.** Sign + install on the iPhone is **NOT** part of A27 — that will be Assignment 28 if the build succeeds. This honors the "one change per assignment" rule and lets us see clean causality between the pbxproj edit and the build outcome.

**Time:** ~5–10 minutes (edit + build + diagnostics).

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-04-29. Drafted directly per Sir Michael's request — no Amazon-Q intermediary — and self-reviewed before USB transfer (lesson V2).

## Background

Assignment 25 confirmed Branch B with sentinels: `RELEASE_SENTINEL_PROPAGATED=NO`, `DEBUG_SENTINEL_PROPAGATED=NO`. The Runner target's Debug + Release `baseConfigurationReference` in `project.pbxproj` point at `Pods-Runner.{debug,release}.xcconfig` instead of `Flutter/{Debug,Release}.xcconfig`, so `Flutter/*.xcconfig` is bypassed and `Generated.xcconfig` (which is `#include`d only from `Flutter/*.xcconfig`) never reaches the build env. That's why `FLUTTER_BUILD_DIR` is null at `xcode_backend.dart:345`.

Assignment 26 attempted the fix with sed and **silently failed**. Two bugs:

1. `DEBUG_FLUTTER_REF=$(grep -o '... Debug\.xcconfig \*/' file | cut -d' ' -f1)` returned a multiline shell variable (the same hex24 ID appears in PBXFileReference, PBXBuildFile, AND baseConfigurationReference sections — `grep -o` matched all three lines, `cut` extracted the same ID per line). When that multiline variable was substituted into a sed pattern, sed errored out with `unescaped newline inside substitute pattern`.
2. The sed regex itself was wrong even with a clean variable: it ended in `\*\;` which matches `*;`, but the actual text ends with `*/;` (close-of-comment + semicolon). The missing `\/` would have matched zero occurrences regardless.

Both errors went to stderr but the script kept printing OK markers. `project.pbxproj` was not modified. Backup is intact (`project.pbxproj.backup_a26_20260429_142729`).

A27 fixes both classes of bug at once by switching the edit to Python, which (a) handles regex escaping cleanly, (b) returns a substitution count via `re.subn(...)` so we can `assert n == 1`, and (c) anchors the substitution on the **specific Runner config UUIDs** (`97C147061CF9000F007C117D` Debug, `97C147071CF9000F007C117D` Release), which guarantees RunnerTests is untouched.

## Prerequisites

- [ ] `D:\Audioura\scripts\fix_baseconfig_a27.sh` exists (Windows side, copied to USB)
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged in (not strictly required for A27, but standard)
- [ ] No background `xcodebuild` or Xcode UI build in progress
- [ ] A26's pbxproj backup `project.pbxproj.backup_a26_20260429_142729` still present at `~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/` (defense-in-depth — A27 creates its own backup independently)

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x fix_baseconfig_a27.sh
```

## Step 3 — Run the fix script

```
./fix_baseconfig_a27.sh
```

**Do NOT wrap with `script ~/Desktop/...`.** The script handles its own output capture via `exec > >(tee ~/Desktop/full_a27_session.txt) 2>&1` (B1 lesson — bare `script` from inside a script body froze the v1→v2 saga).

**What the script does (in order):**

1. **Pre-flight:** validates all four required files exist; confirms both Runner config UUIDs are present in `project.pbxproj`. HALTs if anything is missing.
2. **Backup:** creates `project.pbxproj.backup_a27_<timestamp>` and stashes a copy in the local backup dir + USB.
3. **Capture BEFORE:** dumps every `baseConfigurationReference` line + the Runner Debug/Release config blocks (truncated by first `};`).
4. **Python edit:** locates the live PBXFileReference IDs for `Debug.xcconfig` / `Release.xcconfig` (anchored on `path = Debug.xcconfig;` / `path = Release.xcconfig;` to disambiguate from Pods-Runner.* file refs); rewrites `baseConfigurationReference` inside the two specific Runner config UUID blocks via `re.subn(...)` with `assert n == 1` per substitution. **HALTs and restores from backup** if either substitution misses or matches more than once.
5. **Capture AFTER + verify (HALT-on-fail):** dumps post-edit state; counts (a) `baseConfigurationReference.*\* Debug.xcconfig */` inside the Runner Debug block (must be 1); (b) the same for Release (must be 1); (c) `baseConfigurationReference.*Pods-Runner.debug.xcconfig` in the Runner Debug block (must be 0); (d) the same for Release. Any deviation HALTs and restores from backup. (V1 lesson — verification must `exit 1`, not just print.)
6. **Sentinels + printenv hook:** appends `XCCONFIG_SENTINEL_RELEASE_A27 = release_xcconfig_loaded_a27` to `Release.xcconfig`, the symmetric line to `Debug.xcconfig`, and `printenv | sort > /tmp/flutter_build_phase_env_a27.log` at the top of `xcode_backend.sh` (B4 awk insertion). All idempotent.
7. **Snapshot Podfile.lock** to `~/Desktop/a27_podfile_lock.txt` (standard since A19).
8. **Build:** `flutter build ios --release --no-codesign` with `tee` → `/tmp/flutter_build_27.log`; reads exit code via `${PIPESTATUS[0]}` (B6).
9. **Sentinel detection + env capture:** greps the printenv log for both A27 sentinels AND for `^FLUTTER_BUILD_DIR=`. Writes a headline result file (`a27_sentinel_results`) covering all five interpretation cases (A through E).
10. **Build artifacts info:** captures presence/absence of `Runner.app` and `Frameworks/CwlCatchException.framework`.
11. **Copy to USB + local backup:** all result files timestamped (B2 — real double quotes around USB path with space, visible per-file errors).
12. **Cleanup trap fires on EXIT:** reverts sentinels + printenv hook (NOT pbxproj); writes per-file PASS/FAIL.

**Run time:** ~5–10 minutes.

## Step 4 — Headline results to watch for

The script's final on-screen block reports four numbers:

```
Build exit code:                       <0 or non-zero>
RELEASE_SENTINEL_PROPAGATED_A27:       YES | NO
DEBUG_SENTINEL_PROPAGATED_A27:         YES | NO
FLUTTER_BUILD_DIR_PRESENT_A27:         YES | NO
```

The interpretation table is in `~/Desktop/a27_sentinel_results.txt` and on USB at `a27_sentinel_results_<ts>.txt`. Summary:

| Build exit | Sentinels | FLUTTER_BUILD_DIR | Reading |
|---|---|---|---|
| 0 | YES | YES | A — Branch B fix succeeded. Proceed to A28 (sign + install). |
| 0 | NO  | NO  | B — Build succeeded for an unexpected reason. Inspect the env. |
| ≠0 | YES | YES | C — xcconfig wiring fixed; different build error remains. New theory needed. |
| ≠0 | YES | NO  | D — Sentinels propagate but Generated.xcconfig still not loading. Inspect the `#include` chain. |
| ≠0 | NO  | NO  | E — pbxproj edit didn't take effect at build time. Inspect `a27_after_fix.txt`. |

## Step 5 — Verify cleanup, then return

The script's final visible output is the cleanup verification (written by the trap). Confirm three PASS lines:

```
xcode_backend.sh:    PASS -- printenv line removed
Release.xcconfig:    PASS -- sentinel removed
Debug.xcconfig:      PASS -- sentinel removed
```

The note below those three lines reminds that `project.pbxproj` is intentionally NOT reverted (it holds the actual fix) and points at the timestamped backup.

If any FAIL appears, do NOT continue any other build work — re-run the script (it is idempotent for sentinels + printenv hook), or contact Claude before any further build attempts. A FAIL means the sentinel/printenv line is still in place and would contaminate any subsequent build.

Then eject the USB:
```
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report to Claude

Switch back to Windows and report the headline:

> "Assignment 27 complete. Build exit code: [N]. RELEASE/DEBUG sentinel: [YES/NO/YES/NO]. FLUTTER_BUILD_DIR_PRESENT: [YES/NO]. Cleanup [PASS/FAIL per file]."

Plus any notable observations from the terminal output, especially the Python script's printed lines (it reports the file-ref IDs it discovered, the substitution counts, and any WARN if the discovered IDs differ from the A25-recorded values).

## Result files (all timestamped) on USB

```
full_a27_session_<ts>.txt              (full terminal recording -- the master log)
a27_sentinel_results_<ts>.txt          (THE HEADLINE: build exit + 3 propagation flags + interpretation)
flutter_build_phase_env_a27_<ts>.log   (printenv from inside xcode_backend.sh)
flutter_build_27_<ts>.log              (flutter build output)
a27_before_fix_<ts>.txt                (baseConfigurationReference + Runner config blocks BEFORE)
a27_after_fix_<ts>.txt                 (same, AFTER the Python edit)
a27_xcconfig_dumps_<ts>.txt            (Release + Debug post-A27-sentinel-insertion)
a27_podfile_lock_<ts>.txt              (Podfile.lock snapshot)
a27_build_artifacts_<ts>.txt           (Runner.app + Frameworks/CwlCatchException presence)
a27_cleanup_verification_<ts>.txt      (per-file PASS/FAIL from the cleanup trap)
project_pbxproj_backup_a27_<ts>.txt    (pre-A27 backup of project.pbxproj)
```

Local backup copies in `~/Desktop/a27_results/`.

Mac Mini also has the live backup at `~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj.backup_a27_<ts>`.

## Rollback instructions

If the build fails AND the post-fix verification PASSED (i.e. the edit applied correctly but the build still breaks), the pbxproj edit is in place — do not touch it. Bring back the result files for analysis; A28 will be designed from the evidence.

If you want to manually revert the pbxproj edit:

```
cp ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj.backup_a27_<timestamp> \
   ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj
```

Sir Michael deletes the backup himself per the project's Rule 4 (no deletes from `D:\` or the Mac Mini Flutter project by Claude / Amazon-Q).

## Safety notes

- **Two-phase modification.** The pbxproj edit is the durable change. Sentinels + printenv hook are temporary and reverted by the cleanup trap.
- **HALT-on-failure throughout.** Both the Python edit and the post-edit shell verification `exit 1` on any anomaly, restoring from backup before returning. (V1 lesson from A26: verification must halt, not just print.)
- **Anchored on specific UUIDs.** The Python regex requires the exact Runner config UUID at the start of the matched block, so RunnerTests blocks (different UUIDs) are mathematically untouched. `re.subn(...)` returns a count we `assert == 1` on, so any drift produces a FATAL — not a silent OK.
- **Idempotent for sentinels + printenv.** Running the script a second time skips lines that are already present rather than duplicating. The pbxproj edit is also effectively idempotent — the regex won't match twice because the second run finds the new (Flutter) ref instead of the old (Pods) ref.
- **No `flutter clean` or `flutter pub get`.** Either would regenerate `Generated.xcconfig` (fine) but also potentially run `pod install` side effects. We avoid them.
- **No Podfile / `pod install` changes.** This assignment is purely a `project.pbxproj` edit + diagnostics.
- **No source code edits.** Only the four files listed above are modified; only `project.pbxproj` is left modified at end.

## Bash bug-fixes from A24/A25/A26 review baked in upfront

- **B1:** `exec > >(tee ...) 2>&1` for output capture (no `script` from inside script body)
- **B2:** USB `cp` uses real double quotes around the path (it contains a space), visible per-file errors
- **B3:** single-quoted grep patterns
- **B4:** awk for line insertion (BSD sed lacks inline `2i\<text>` on macOS)
- **B5:** `"$HOME/..."` not `"~/..."` inside double quotes
- **B6:** `${PIPESTATUS[0]}` for flutter build's exit code after the `tee` pipe
- **B7 (NEW from A26):** no multiline shell variable into sed — use Python with `re.search` (first match only) and `re.subn(...)` with `assert n == 1`
- **V1 (NEW from A26):** verification HALTS (`exit 1`) on failure, not just prints — followed by `cp backup pbxproj` to restore
- **V2 (NEW from A26):** Claude reviewed this script before USB transfer — A26 was Amazon-Q-drafted and unreviewed; both bugs would have been caught in a 60-second review. A27 is drafted directly by Claude to keep this discipline.
- **M1:** system-date drift check (Amazon-Q tagged A20 as 01/31/2025 while we were in April 2026)
- **M3:** `cd` only for the flutter build (the one acceptable absolute-path exception)
- **M5:** local backup directory fallback in case USB copy fails

## Next step (preview, not part of A27)

**If A27 lands case A (build=0, sentinels=YES, FLUTTER_BUILD_DIR=YES):** Claude drafts Assignment 28 — sign + install on iPhone 16 (UDID `00008140-000558A902BA801C`) using signing identity `594584F3D3BC571D94A822A2158871CA13898701`. The acceptance test is: app launches without `Library not loaded: @rpath/CwlCatchException.framework/CwlCatchException`.

**If A27 lands case C/D/E:** Claude reads the evidence files and designs the next targeted diagnostic. Cases C and D both indicate the pbxproj fix took effect at the file level but something else is still wrong; case E indicates the file-level edit did not propagate to the build env (would require deeper investigation — possibly Xcode caching or a derived-data flush).

**Status**: ✅ COMPLETED - Assignment 27 SUCCESS - Case A achieved (build exit 0, FLUTTER_BUILD_DIR present)

---

# T: 04/29/2026 14:27 - A#26 — Fix project.pbxproj baseConfigurationReference (Branch B)

**Goal:** Restore Flutter configuration chain by fixing `baseConfigurationReference` entries in `project.pbxproj` to point to Flutter xcconfig files instead of Pods xcconfig files.

**Script to run:** `fix_baseconfig_a26.sh`

**Scope:** **TARGETED FIX** based on Assignment 25 Branch B results (`RELEASE_SENTINEL_PROPAGATED=NO`).

**Time:** ~5–10 minutes (fix + build test).

**Status**: ❌ COMPLETED - Assignment 26 FAILED (sed syntax errors + persistent build failure)

---

# T: 04/29/2026 - A#25 — Sentinel Test for xcconfig Base-Configuration Loading

**Goal:** Determine whether `Flutter/Release.xcconfig` and `Flutter/Debug.xcconfig` are loaded as the active base configuration of their respective build configurations, by inserting unique sentinel keys and checking whether they propagate to the Run Script Phase environment.

**Script to run:** `sentinel_test_a25.sh`

**Scope:** **DIAGNOSIS ONLY — NO FIXES.** Assignment 26 will be the targeted one-change fix designed by Claude after these results land.

**Time:** ~5–10 minutes (build + diagnostics).

**Status:** ✅ COMPLETED - Branch B confirmed (RELEASE_SENTINEL_PROPAGATED=NO)

---

# T: 04/29/2026 - A#24 v3 — Diagnose xcconfig Propagation to Run Script Phase

**Goal:** Capture evidence to determine why `FLUTTER_BUILD_DIR` (present in Generated.xcconfig) isn't reaching the shell environment of `xcode_backend.sh`. **DIAGNOSIS ONLY - NO FIXES YET.**

**Script to run:** `diagnose_xcconfig_propagation_a24_v3.sh`

**Version 3:** Fixed B5 (tilde-in-quotes for Pods paths) and B6 (PIPESTATUS for flutter build exit code) per Claude review

**Time:** ~5-10 minutes (build + diagnostics)

**Status:** ✅ COMPLETED - Environment capture successful, FLUTTER_BUILD_DIR missing confirmed

---

# T: 04/29/2026 - A#23 — Read xcconfig Files (Quick Diagnostic)

**Goal:** Read the current contents of Flutter xcconfig files to confirm exactly what environment variables need to be added to fix the `FLUTTER_BUILD_DIR` null-check error.

**Script to run:** `xcconfig_diagnostic.sh`

**Time:** ~30 seconds (just reading files)

**Status:** ✅ COMPLETED - xcconfig files analyzed, FLUTTER_BUILD_DIR present in Generated.xcconfig

---

# T: 04/29/2026 - A#22 — xcodebuild Attempt + xcode_backend.dart Diagnostic

**Goal:** Capture diagnostic data about the failing `xcode_backend.dart:345` null-check, and try invoking `xcodebuild` directly to see whether that path can succeed where `flutter build ios` fails.

**Script to run:** `xcodebuild_diagnose_and_attempt.sh`

**Status:** ✅ COMPLETED - xcodebuild failed with same null-check error, diagnostics captured

---

# T: 04/29/2026 - A#21: Revert Podfile and Diagnose Framework Embedding

(Archived - see D:\Audioura\archive\assignment_21_walkthrough.md)

**Status:** ✅ COMPLETED - Controlled crash reproduction successful, diagnostic evidence gathered

---

# T: 04/29/2026 - A#20: Remove CwlCatchException Source Plugin

(Archived - see D:\Audioura\archive\)

**Status:** ✅ COMPLETED - Plugin removal successful, build issues identified

---

# T: 04/25/2026 21:45 - A#19: ELIMINATE CWLCATCHEXCEPTION COMPLETELY

**Goal:** Remove ALL dev_dependencies from pubspec.yaml and rebuild completely clean

**Script to run:** `clean_build_no_cwl.sh`

**Strategy:** Remove ALL dev_dependencies from pubspec.yaml and rebuild completely clean

**Expected:** Working Audioura app with NO CwlCatchException dependency

**Status:** ✅ COMPLETED - CwlCatchException eliminated, manual installation successful, crash persists in release build

---

# T: 04/25/2026 - A#18: Manual Installation Success Analysis

**Analysis:** Manual Xcode installation successful (drag-and-drop works)
- ✅ Release app bundle created and signed (21MB)
- ✅ App appears on iPhone home screen with correct icon
- ❌ CwlCatchException crash STILL occurs in release build
- ❌ Dependency now in MAIN Runner executable (not debug dylib)

**Root Cause Identified:** Library not loaded: @rpath/CwlCatchException.framework/CwlCatchException

**Status:** ✅ COMPLETED - Installation method proven, runtime issue identified

---

**Last Updated:** 2026-05-15 - A#53 added (build v1.2.9+52 — A#51 map AppBar + A#52 per-stop focus)
**Format:** Single # headings, T: instead of Time:, A#nn instead of Assignment nn
**Organization:** Current assignment at top for easy navigation
**Status:** Ready for A#53 execution