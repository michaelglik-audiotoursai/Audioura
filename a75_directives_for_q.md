# A#75 Directives for Mac Mini Q
## InAppWebView v6 Migration — news_player_screen.dart
**Version target:** v1.2.9+65
**Branch:** Newsletters
**Created:** 2026-06-01

---

## CONTEXT

Assignment A#71 claimed to migrate `news_player_screen.dart` from InAppWebView v5 API to v6,
but the migration was not actually performed in that commit. A#75 completes it.

**IMPORTANT:** The Windows copy of `news_player_screen.dart` already has the v6 API applied.
Your first job is to VERIFY the file is correct, then bump version and build.

---

## STEP 1 — VERIFY migration is already applied

Open `~/Development/Audioura-build/development/audio_tour_app/lib/screens/news_player_screen.dart`

Confirm ALL of the following are TRUE:

✅ `initialSettings: InAppWebViewSettings(` is present (NOT `initialOptions: InAppWebViewGroupOptions(`)
✅ Settings are flat (no nested `crossPlatform:`, `android:`, `ios:` wrappers)
✅ These settings are present inside `InAppWebViewSettings(...)`:
   - `javaScriptEnabled: true`
   - `mediaPlaybackRequiresUserGesture: false`
   - `useShouldOverrideUrlLoading: false`
   - `useOnLoadResource: false`
   - `useHybridComposition: true`
   - `allowContentAccess: true`
   - `allowFileAccess: true`
   - `allowsInlineMediaPlayback: true`
   - `allowsAirPlayForMediaPlayback: true`

**If ALL above are confirmed → proceed to Step 2. No code changes needed.**

**If ANY are missing or wrong → apply the correction:**
Replace any occurrence of:
```dart
initialOptions: InAppWebViewGroupOptions(
  crossPlatform: InAppWebViewOptions(...),
  android: AndroidInAppWebViewOptions(...),
  ios: IOSInAppWebViewOptions(...),
)
```
With the flat v6 form:
```dart
initialSettings: InAppWebViewSettings(
  javaScriptEnabled: true,
  mediaPlaybackRequiresUserGesture: false,
  useShouldOverrideUrlLoading: false,
  useOnLoadResource: false,
  useHybridComposition: true,
  allowContentAccess: true,
  allowFileAccess: true,
  allowsInlineMediaPlayback: true,
  allowsAirPlayForMediaPlayback: true,
),
```

---

## STEP 2 — Bump version

In `~/Development/Audioura-build/development/audio_tour_app/pubspec.yaml`:

Change:
```yaml
version: 1.2.9+64
```
To:
```yaml
version: 1.2.9+65
```

---

## STEP 3 — Flutter analyze

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter analyze
```

Must show: **No issues found!** (warnings about deprecated APIs in third-party packages are OK — only our code matters)

---

## STEP 4 — Build iOS

```bash
flutter build ios --release --no-codesign
```

Must complete without errors.

---

## STEP 5 — Commit and push

```bash
cd ~/Development/Audioura-build
git add development/audio_tour_app/lib/screens/news_player_screen.dart
git add development/audio_tour_app/pubspec.yaml
git commit -m "v1.2.9+65 - A#75: InAppWebView v6 migration in news_player_screen.dart"
git push origin Newsletters
```

---

## STEP 6 — Update remind and assignments files

Update `development/remind_macmini.md`:
- Current build: v1.2.9+65 (A#75 complete)
- Next: A#76 (check assignments file)

Update `D:/Audioura/assignments/mac_mini_assignments.md` (USB):
- Mark A#75 complete with date and commit hash
- Prepend next assignment if available

---

## STOP CONDITIONS

- If `flutter analyze` shows errors in OUR code (not third-party) → STOP, report to Sir Michael
- If iOS build fails → STOP, report full error output
- If push is rejected → STOP, do NOT force push, report to Sir Michael

---

**Expected wall time:** ~15 minutes
**No functional change for users** — identical WebView behaviour, eliminates deprecation footgun
