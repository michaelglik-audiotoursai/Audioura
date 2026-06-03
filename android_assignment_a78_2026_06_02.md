# Android Amazon-Q Assignment — Build v1.2.9+71
## A#78 Parity Build — Listen Page Mic Permission Fix

**Date:** 2026-06-02
**From:** iOS Amazon-Q
**For:** Android Amazon-Q

---

## Context

iOS v1.2.9+71 was just built and smoke-tested on iPhone. Two commits fix the Listen page microphone voice search feature that was broken by a redundant permission check. Android needs a parity build at the same version.

**What changed in these two commits:**

| Commit | Change |
|--------|--------|
| `df6b61b` | Removed redundant `Permission.microphone.request()` block from `_startVoiceSearch()` in `my_tours_screen.dart` |
| `92d0175` | Removed now-dead `permission_handler` import from `my_tours_screen.dart` |

**Why this matters on Android:** The `permission_handler` plugin on Android uses a different permission pathway than `speech_to_text`. The same conflict that caused the iOS bug could exist on Android. This fix cleans both platforms simultaneously since it is a single Flutter file.

**Version target:** `1.2.9+71` **Branch:** `services-migration`

---

## Step 1 — Pull latest

```bash
cd ~/path/to/Audioura-build   # or wherever your clone lives
git pull origin services-migration
```

**Expected:** fast-forward that includes at minimum commits `df6b61b` and `92d0175`.

Verify:
```bash
git log --oneline -5
# Both df6b61b and 92d0175 must be present
```

---

## Step 2 — Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd development/audio_tour_app

# 2a — pubspec at +71
grep "^version:" pubspec.yaml
# Expected: version: 1.2.9+71

# 2b — Permission.microphone.request() block is GONE
grep -n "microphone.request\|Microphone permission required" lib/screens/my_tours_screen.dart
# Expected: zero matches

# 2c — permission_handler import is GONE
grep -n "permission_handler" lib/screens/my_tours_screen.dart
# Expected: zero matches

# 2d — _speechEnabled guard still present
grep -n "_speechEnabled" lib/screens/my_tours_screen.dart
# Expected: at least 2 matches (declaration + guard in _startVoiceSearch)
```

If 2b or 2c shows any match, STOP and report to iOS Q.

---

## Step 3 — Build

```bash
cd development/audio_tour_app
flutter clean && flutter pub get
flutter build apk --release
```

**APK output:** `build/app/outputs/flutter-apk/app-release.apk`

---

## Step 4 — Install and launch

```bash
flutter install
# or
adb install build/app/outputs/flutter-apk/app-release.apk
```

---

## Step 5 — Smoke test ⚠️ STOP HERE, run tests before reporting

**Test 1 — Microphone voice search (primary fix for this build):**
1. Switch app to **Audio mode** → go to **Listen tab**.
2. Tap the **microphone icon** in the AppBar.
3. **Expected:** Listening dialog appears immediately. **No** "Microphone permission required" snackbar.
4. Say something (e.g. "Boston") → dialog closes → article list filters.
5. Check debug log (About → Debug Log): `LISTEN: Voice search ...` line must appear.

**Test 1b — Android permission prompt (Android-specific check):**
- On first mic tap after fresh install, Android may show a system permission dialog for `RECORD_AUDIO`. This is correct — grant it. On subsequent taps, no system dialog should appear and no snackbar should appear.
- If "Microphone permission required" snackbar appears on the SECOND tap (after permission was already granted), that is the same bug that was fixed on iOS — report it to iOS Q immediately.

**Test 2 — Regression:**
1. Listen page Refresh → list reloads, no black screen.
2. Open a tour → audio plays. Open a news article → loads.

---

## Step 6 — Report results

Report to Sir Michael and iOS Q with:
- Build: SUCCESS / FAILED
- Mic dialog opens without snackbar: YES / NO
- Android permission prompt handled correctly on first tap: YES / NO
- Voice search filters articles: YES / NO
- Listen Refresh no black screen: YES / NO
- Android OS version tested on: [version]
- Overall: SUCCESS / PARTIAL / FAILED

---

## Notes for Android Q

- `RECORD_AUDIO` is declared in `AndroidManifest.xml` — no changes needed there.
- `permission_handler` is still a dependency in `pubspec.yaml` (used by other screens) — removing the import from `my_tours_screen.dart` does not affect that.
- Do NOT bump the version number — iOS Q owns version bumps.
- Do NOT commit unless you find Android-specific file changes are required.
