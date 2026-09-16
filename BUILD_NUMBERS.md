# Build numbers — the ledger, and the one rule

**A build number is CONSUMED the moment it is uploaded to either store, and can never be
reused on that platform — including when the store REJECTS the upload.**

Both platforms read the same line, so a number spent on one is spent for both by convention:

```
audio_tour_app/pubspec.yaml        version: <version>+<build>
android/app/build.gradle.kts       versionCode = flutter.versionCode
ios/Runner.xcodeproj               CURRENT_PROJECT_VERSION = $(FLUTTER_BUILD_NUMBER)
```

## THE RULE

**Before building for either store, check this file. Use a number HIGHER than every row below,
and add your row when you upload.** `pubspec.yaml` is kept one step ahead of the last consumed
number, so a clean checkout is normally already safe — but **verify, do not assume**: the file is
the record, `pubspec.yaml` is only a convenience.

Michael, 2026-09-03: *"I do not want these two collide with each other. Next build should be on
top of +21 on either system."*

## Ledger

| build | platform | version | commit | outcome | date |
|---|---|---|---|---|---|
| 18 | Android | 2.1.1 | `0bb4e66` | shipped to Play — the live build before this round | 2026-06-25 |
| 19 | iOS | 2.3.1 | `077c979` | **built, never uploaded** — superseded by the 2.3.2 security fix | 2026-09-02 |
| 20 | Android | 2.3.2 | `c0049a8` | **shipped to Play closed testing** | 2026-09-03 |
| 20 | iOS | 2.3.2 | `c0049a8` | **REJECTED by Apple** — `ITMS-90683`, missing `NSPhotoLibraryUsageDescription`. Number consumed anyway. | 2026-09-03 |
| 21 | iOS | 2.3.2 | `cc636d4` | **LIVE on TestFlight**, App Apple ID 6807925770 | 2026-09-03 |
| 22 | iOS | 2.3.2 | `2c85717` | **uploaded to TestFlight** — carries the tour-editing fix (LOCAL-475) and the empty-`tour_type` fix (LOCAL-474/476) | 2026-09-14 |
| 22 | Android | 2.3.2 | `2c85717` | built on Windows with **Flutter 3.29.3** — never shipped; superseded by 23 | 2026-09-14 |
| 23 | iOS | 2.3.2 | `5e53c56` | **uploaded to TestFlight** — removes the client-side cloud-mode block on tour editing | 2026-09-15 |
| 23 | Android | 2.3.2 | `5e53c56` | built on Ubuntu by `GCloud_Storied`; **not uploaded to Play** pending Michael's device test | 2026-09-15 |
| 24 | iOS | 2.3.2 | `92dac9e` | **uploaded to TestFlight** (first upload via the App Store Connect API key, delivery `bde945f9`) — carries **LOCAL-477** (Add Stop no longer pops to Listen) and **LOCAL-478** (original audio loads; stale iOS container paths heal after a TestFlight update) | 2026-09-15 |
| 25 | iOS | 2.3.2 | `1673643` | **uploaded to TestFlight** — build 24 shipped without `--dart-define=GATEWAY_API_KEY`, so `X-API-Key` was empty and every gateway call 401'd ("couldn't connect securely"). 25 is the first iOS build made with `build_ios_release.sh`; key verified present in the compiled binary. Delivery `1dca7f30` | 2026-09-16 |
| 26 | iOS | 2.3.2 | `705bd8f` | **uploaded to TestFlight** (delivery `d2b21824`) — carries **LOCAL-482**: the stop editor's audio player now loads its HTML from the audio's own directory with a relative `src`, matching the Listen/news players, so WKWebView's read grant covers the file. **First build intended for external testers.** | 2026-09-16 |
| 27 | — | — | — | **NEXT** | — |

## Why 20 and 21 differ across platforms

Android shipped 20. Apple rejected 20 during processing and **still consumed the number**, so iOS
had to go to 21 for identical code. That is Apple's accounting, not a difference in the app — the
**version string `2.3.2` is the same on both**, and that is what to tell testers.

## What this is NOT

**There is no automated guard.** `release_tag.sh` tags server deploys (`v<line>t<seq>`); it does not
look at `pubspec.yaml`. Nothing fails a build that reuses a number — Play rejects it at upload with
a clear error, and **Apple silently consumes it**, which is the expensive direction.

If this file is ever wrong, the stores are the truth: Play Console → App bundle explorer, and
App Store Connect → TestFlight → Build Uploads.

## Building and uploading (from 2026-09-16)

```bash
cd ~/Audioura && bash build_ios_release.sh   # REQUIRED — never `flutter build ipa` bare
cd ~/Audioura && bash upload_testflight.sh
```

**Never run `flutter build ipa --release` by hand.** `Endpoints._builtInApiKey` is a
`String.fromEnvironment('GATEWAY_API_KEY')` compile-time constant: with no `--dart-define` it bakes
in as empty, the app sends no `X-API-Key`, and every gateway endpoint returns 401 — which the app
shows the user as "Audioura couldn't connect securely." That is what happened to build 24.
`build_ios_release.sh` reads `build_secrets.env` and refuses to build without the key.

Credentials are an **App Store Connect API key**, not an app-specific password. The private `.p8`
lives at `~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8` (mode 600) and is never passed on a
command line; `~/.appstoreconnect/config.env` holds only the Key ID and Issuer ID, which are
identifiers. Revoke a key at App Store Connect → Users and Access → Integrations.

**Standing warning from Apple, first seen on build 24 (90068):** `MinimumOSVersion` is **13.0**.
**From Spring 2027 Apple rejects any upload below 15.0.** Raising it drops iPhone 6s/7 and the
first-gen SE. Not urgent, but it is a hard deadline, not a suggestion.
