# Transition Brief — Mac Mini Kiro CLI (🍎)

**Date:** 2026-05-28. Supersedes any prior version (lost during A#74 cleanup).
**Audience:** 🍎 MAC MINI KIRO CLI (launched via `kiro-cli chat --trust-all-tools`).
**Status of your `remind_macmini.md`:** untouched. You own it.

You executed A#75 successfully — iPhone is on v1.2.9+65. **You are now idle until either:** (a) Services Q delivers a PreProd HTTPS URL and iOS Q gives you a new build assignment with `--dart-define=AUDIOURA_ENV=preprod`, or (b) the App Store submission phases (TestFlight, production) begin.

Your role doesn't change — you execute iOS build assignments. The new patterns you'll see are described below.

---

## New build pattern 1 — environment-keyed builds (post-Services Q's M04)

Once iOS Q delivers `lib/config/api_config.dart`, all future iOS builds will pass an env flag:

```bash
# Current LAN dev backend (still works for laptop testing)
flutter build ipa --release --dart-define=AUDIOURA_ENV=dev

# GCP Cloud Run PreProd
flutter build ipa --release --dart-define=AUDIOURA_ENV=preprod

# Production (api.audioura.io) — App Store submissions use this
flutter build ipa --release --dart-define=AUDIOURA_ENV=prod
```

Claude IO will update `build_install_launch.sh` (on the USB at `/Volumes/USB DISK/Audioura/scripts/`) to accept an `--env` argument. Until that update lands, your existing build pattern still works (defaults to `dev`).

**You do not create or edit per-env config files.** All env handling flows through Dart's `--dart-define`. Your job is to pass it correctly.

When asked to verify a backend cutover, build the matching env variant and run the iPhone smoke test against it. The debug log on app launch will log which base URL was resolved — confirm it matches the expected env.

---

## New build pattern 2 — TestFlight archive + upload (Phase 3 / A33)

Spec: `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md` Phase 3.

```bash
cd ~/Development/Audioura-build/audio_tour_app
flutter clean
flutter pub get
# TestFlight is for App-Store-bound builds, so use prod env
flutter build ipa --release --dart-define=AUDIOURA_ENV=prod

# Upload via app-specific password stored in keychain
xcrun altool --upload-app \
  --type ios \
  --file build/ios/ipa/audio_tour_app.ipa \
  --username audiotoursai@gmail.com \
  --password "@keychain:AC_PASSWORD"
```

Pitfalls:
- **Build number (`+NN` in pubspec) must increment for every TestFlight upload.** Apple rejects duplicates.
- **Apple processing takes 5–30 minutes after upload.** Don't refresh App Store Connect aggressively — wait for the email.
- **App-specific password is generated at `appleid.apple.com`** and stored in Mac Mini keychain. Sir Michael does this setup once; you reference it via `@keychain:AC_PASSWORD`.

Fallback if `xcrun altool` fails: `open ios/Runner.xcworkspace` → Product → Archive → distribute via Xcode UI. Slower but reliable.

---

## New build pattern 3 — production App Store submission (Phase 6 / A36)

Identical to TestFlight pattern (Pattern 2). The difference is on Sir Michael's side: in App Store Connect, he clicks "Submit for Review" instead of "Internal Testing." Same build artifact.

After every rejection cycle: increment build number, fix the cited issue, rebuild, re-upload. Plan for at least one rejection cycle (1-2 weeks each).

---

## What stays the same

- **Bundle ID:** `com.glikfamily.audioura`. Do not change.
- **Team ID:** `4HGRU6TKGQ`. Do not change.
- **Signing identity:** `594584F3D3BC571D94A822A2158871CA13898701`. In keychain, proven working.
- **Apple Developer Program:** active, paid, member of team `4HGRU6TKGQ`.
- **`flutter clean` is mandatory** before any release build. Xcode caches the asset catalog.
- **STOP conditions still apply.** Anything that says STOP, you stop and report.

---

## What's NOT your scope

- App icon generation (A#73 did it, regenerator script at `development/scripts/a73_regenerate_icons.py`).
- Info.plist edits — iOS Q designs them; you just rebuild.
- Play Console anything — Mobile Q.
- Backend / GCP / services migration — Services Q.

---

## Where this doc lives

`~/Development/Audioura-build/development/transition_for_MacMini_Kiro.md` after the next `git pull`. Git-tracked on Newsletters.
