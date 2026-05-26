# A#73 Directives for Q — App Icon Background (#A93105 brick red)

**Date:** 2026-05-26
**Author:** Claude IO
**Consumer:** Mac Mini Amazon-Q. Q reads this file at `~/Development/Audioura-build/development/a73_directives_for_q.md` after `git pull origin Newsletters` on the Mac Mini. **Sir Michael does not give this file to Q directly** — Q pulls it from GitHub as part of A#73 Step 3.

**Sir Michael's only action on this file:** commit it from Windows together with the regeneration script and push to GitHub. That is A#73 Step 0 in `mac_mini_assignments.md`. After the push, this file is hands-off until the next code-review cycle.

**Scope:** No Dart code changes. Replaces 15 PNG files in `audio_tour_app/ios/Runner/Assets.xcassets/AppIcon.appiconset/` and bumps the build number. All regeneration happens via a Python script (`development/scripts/a73_regenerate_icons.py`) that has been pre-tested in the Claude IO sandbox.

---

## 1. Background

The current app icon (headphones over microphone) has a transparent background; iOS therefore renders it on white, which Sir Michael wants replaced with a brick-red `#A93105` (RGB 169, 49, 5). The icon graphic itself is unchanged — only the background color is added behind it.

The source-of-truth master is `Icon-App-1024x1024@1x.png` in the appiconset. The script reads it (with its existing transparent background), composites it onto a solid `#A93105` canvas, flattens to RGB (App Store requires no alpha channel), then resizes to all 15 size variants required by `Contents.json`.

---

## 2. Fix — single Python script does everything

**File:** `development/scripts/a73_regenerate_icons.py` (committed in Step 0 by Sir Michael; Q just runs it).

### 2.1 Prerequisite — install Pillow

macOS does not ship Pillow. Install it for the user account:

```bash
pip3 install --user Pillow
```

If `pip3` is not on PATH, try `python3 -m pip install --user Pillow`. If both fail, STOP and report — `flutter` requires Python 3 already, so something is wrong with the toolchain.

### 2.2 Run the regenerator

```bash
cd ~/Development/Audioura-build
python3 development/scripts/a73_regenerate_icons.py
```

**Expected output (paths shortened):** 15 lines reading `wrote Icon-App-...png  NxN  ... bytes`, ending with `OK: wrote 15/15 icon files.` Anything else (Python traceback, "ERROR:" line, fewer than 15 files written) → STOP and report.

The script is idempotent — re-running it just re-composites the existing master onto `#A93105` again (no-op for already-tan pixels). Safe to re-run after a failed step.

### 2.3 Bump version

Edit `audio_tour_app/pubspec.yaml` line 4: change `version: 1.2.9+63` → `version: 1.2.9+64`. Nothing else in `pubspec.yaml` changes.

---

## 3. Acceptance

After Step 2 of this section, the following must all hold (verified by spot-checks in the assignment file, Step 6):

- 15 PNGs exist in `audio_tour_app/ios/Runner/Assets.xcassets/AppIcon.appiconset/`, all dated today.
- `Icon-App-1024x1024@1x.png` is 1024×1024 and RGB-only (no alpha).
- `Contents.json` is **unchanged**.
- `audio_tour_app/pubspec.yaml` shows `version: 1.2.9+64`.
- On the iPhone Home Screen after `flutter clean` + rebuild: Audioura icon shows the headphones+microphone graphic on a **brick-red** background — not white, not pale brown, not the generic Flutter logo.

---

## 4. Out of scope

- The icon **graphic** (headphones over microphone) is not redrawn. Only the background changes.
- No code changes in `audio_tour_app/lib/`. If Q is tempted to "also fix" anything in Dart while in the area — don't. That belongs in its own assignment.
- The transparent source 1024 PNG is overwritten in place by the script. If you ever want a different background color, `git checkout <old-commit> -- audio_tour_app/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png` will restore the transparent source from before this commit, then re-run the script with the new color.

---

## 5. Q failure modes to avoid on this assignment

- **Do not** hand-edit any of the PNG files. They are all produced by the script. If a file looks wrong, re-run the script — do not try to "fix" individual variants.
- **Do not** modify `Contents.json`. The filenames the script writes match the entries already in `Contents.json`.
- **Do not** install Pillow with `sudo pip3` or system-wide. Use `--user` so it lands in the user site-packages without touching the macOS-managed Python install.
- **Do not** skip `flutter clean`. Xcode caches the asset catalog; without `flutter clean` the build will reuse the old (white-background) icons and the iPhone will still show the wrong color, making the test look like a failure.
- If the iPhone Home Screen still shows the old icon after a successful build + install: this is the known iOS icon-cache problem. Delete the app from the Home Screen, then re-install — iOS will pick up the new icon. (Same workaround was used in A#70.)
