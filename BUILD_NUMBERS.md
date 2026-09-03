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
| 22 | — | 2.3.2 | — | **NEXT — claimed in `pubspec.yaml`, not yet built** | — |

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
