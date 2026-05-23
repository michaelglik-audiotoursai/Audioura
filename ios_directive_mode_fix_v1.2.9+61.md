# iOS Build Directive — Mode-Switch Fix v1.2.9+61

**For:** iOS Amazon-Q
**From:** Mobile App Amazon-Q
**Date:** 2026-05-22
**Branch:** Newsletters
**Version:** v1.2.9+61

---

## What Was Fixed

The Audioura app had a regression where switching from Tours to Audio mode in the
About tab did NOT update the Home and Generate pages — they stayed stuck on Tours
content. This was caused by `IndexedStack` in `main_screen.dart` (introduced in
A#59 review finding NF9) keeping all tab screens permanently mounted, so
`initState()` never re-ran on tab switch and `app_mode` was never re-read from
SharedPreferences.

**Fix:** `main_screen.dart` was replaced with a `_buildBody()` switch version
(identical to v1.2.8+107 known-good, plus the A#59 Listen-tab reload fix).
Full diagnosis is in `development/mode_regression_fix.md`.

---

## What You Need to Do for iPhone

### Step 1 — Verify the dev-tree file is correct

The fixed `main_screen.dart` is at:
```
c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\lib\screens\main_screen.dart
```

It must contain `_buildBody()` and `_listenTabVersion` — NOT `IndexedStack`.
Confirm with:
```
findstr "IndexedStack _buildBody _listenTabVersion" main_screen.dart
```
Expected: `_buildBody` and `_listenTabVersion` found, `IndexedStack` NOT found.

### Step 2 — Check the iOS staging copy

The regression was caused by a staging copy at `D:\Audioura\assets\` diverging
from the dev tree. Check whether an equivalent iOS staging path exists and if so,
copy the fixed `main_screen.dart` there too. If you are building directly from
the dev tree, this step is not needed.

### Step 3 — Build the iOS IPA

Version is now **1.2.9+61**. Build from the dev tree on the Mac build machine:
```bash
cd audio_tour_app
flutter build ipa --release
```
Or via GitHub Actions if that is the iOS build workflow.

### Step 4 — Verify the fix on iPhone

Run through this checklist on the installed IPA:

| Step | Expected result |
|---|---|
| About → switch to Audio → tap Home | Home shows Newsletter/Audio view |
| About → switch to Audio → tap Generate Tour | Generate shows Audio/Newsletter form |
| About → switch to Audio → tap Listen | Listen shows newsletter articles |
| About → switch back to Tours → tap Home | Home shows map/tours view |
| Generate a tour → tap Listen | Tour appears (Listen reload still works) |
| Background tour notification → tap it | Opens Listen tab with new tour |

### Step 5 — What is NOT affected

- ✅ All iOS-specific fixes from v1.2.9+24 through v1.2.9+49 are untouched
- ✅ Location permissions (iOS-specific) unchanged
- ✅ Mic permissions (speech_to_text native, no permission_handler) unchanged
- ✅ Device info (iOS branch in about_screen.dart) unchanged
- ✅ Font fixes unchanged
- ✅ Keyboard dismiss fixes unchanged
- ⚠️ Home map pan/zoom resets on tab switch — this is correct intended behavior,
  same as v1.2.8+107. It was never a reported user complaint on iOS.

---

## Key Architectural Note (DO NOT CHANGE)

The mode-switching mechanism relies entirely on `initState()` re-running every
time a tab is tapped. This only works because `_buildBody()` returns a fresh
widget instance on every build — Flutter disposes the outgoing screen's State
and creates a new one for the incoming screen.

**Never wrap `_buildBody()` in `IndexedStack`** — that was the exact cause of
this regression. If map state preservation is ever requested as a feature, see
the optional `ValueKey`-based `IndexedStack` approach described in
`mode_regression_fix.md`, but do not implement it unless explicitly requested.

---

## Process Note

All mobile changes must be committed to the `Newsletters` git branch after each
accepted cycle — not just applied to a staging copy. The `D:\` staging divergence
is what made this regression invisible to `git log` and took a manual 4-file diff
to find. Going forward: modify dev tree → commit → copy to staging if needed.

---

## Git Status

Android commit for this fix:
- Tag: `1.2.9.61`
- Branch: `Newsletters`
- Commit message: `v1.2.9+61: Fix mode-switch regression — replace IndexedStack with _buildBody() switch`
- Files changed: `main_screen.dart`, `pubspec.yaml`, `main.dart`
