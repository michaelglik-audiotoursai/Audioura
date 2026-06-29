# iOS Amazon-Q — Bring the iPhone Build to Parity with Android v2.1.1+1

**For:** iOS Amazon-Q
**From:** Claude
**Date:** 2026-06-03
**Android reference:** commit `a877a50` on `services-migration`, version **2.1.1+1** (Android Amazon-Q)
**Goal:** Produce an iPhone build that is functionally identical to the Android v2.1.1+1 build — same dual-environment (Local WiFi / Cloud) networking, same fixes.

---

## 1. The key fact: this is one Flutter codebase — most of the work is already done

The v2.1.1+1 changes (the `Endpoints` resolver, the About-screen Local/Cloud toggle, the `cloud_use_path_prefixes` flag, the `home_screen` migration, the earlier A#77b refresh and A#78 mic fixes) are **all in shared Dart** (`lib/...`). They are **not** Android-specific. The moment you build the iOS `Runner` target from the **same commit `a877a50`**, the iPhone app gets every one of them automatically.

So "correlating the iPhone build with Android" does **not** mean re-implementing anything. It means: **build the same commit, keep the version number in lockstep, handle the iOS-only build mechanics, and verify the iOS-specific bits below.** Do **not** make parallel Dart edits on the iOS side — that would fork the codebase and is exactly what we want to avoid.

---

## 2. What iOS Amazon-Q needs to do

### 2.1 Build from the same source (required)
- Check out **`services-migration` at commit `a877a50`** (or later, if Android AQ advances it — coordinate so both platforms ship the same commit).
- Confirm `pubspec.yaml` reads `version: 2.1.1+1` (it already does — shared). This drives the iOS `CFBundleShortVersionString` (`$(FLUTTER_BUILD_NAME)` = 2.1.1) and `CFBundleVersion` (`$(FLUTTER_BUILD_NUMBER)` = 1) automatically, so the iPhone build number **matches Android by construction** as long as you build this commit. No manual Info.plist version edits.
- `flutter pub get`, then **`cd ios && pod install`** (the recent changes didn't add plugins, but run it after pulling to be safe), then build/sign the `Runner` target and deploy to the iPhone.

### 2.2 iOS networking — no change required, and here's why (verified)
- The iPhone Info.plist (`ios/Runner/Info.plist`) has **no** `NSAppTransportSecurity` block, yet **local-mode HTTP already works on iPhone** (your existing iPhone logs reach `192.168.0.218`). That's because Flutter's `package:http` uses `dart:io`'s `HttpClient`, which **bypasses iOS App Transport Security** (ATS only governs `NSURLSession`). Cloud mode is HTTPS, so it's ATS-clean anyway, and tour/news playback is from a local `file://` WebView (the downloaded ZIP) — no remote-HTTP WebView load. **So no ATS / Info.plist change is needed for either mode.**
- **Optional hygiene (not a blocker):** add `NSLocalNetworkUsageDescription` to the Info.plist so iOS 14+ local-network access is explicit and the OS prompt (if any) reads cleanly:
  ```xml
  <key>NSLocalNetworkUsageDescription</key>
  <string>Audioura connects to your local Audioura server on the same WiFi network.</string>
  ```
  Skip if you prefer parity-only; local mode already functions without it.

### 2.3 Confirm the permission strings are intact (they are)
The Info.plist already has `NSMicrophoneUsageDescription`, `NSSpeechRecognitionUsageDescription`, and the location strings — which the A#78 voice-search fix and the map features depend on. Nothing to add; just don't remove them.

### 2.4 Run the same parity smoke tests on iPhone
Mirror Android's test list so the two builds are verified identically:
1. **Local mode (default):** Home → tours load from `192.168.0.218:5005` over WiFi.
2. **About:** Local/Cloud toggle present, default Local; switching to Cloud reveals the editable cloud-base-URL field and the "gateway path routing" checkbox (leave it **unchecked**).
3. **Cloud mode, off WiFi (cellular):** paste `https://map-delivery-…run.app`, toggle to Cloud → an existing tour downloads from R2 and plays.
4. **Listen-page Refresh:** no black screen (A#77b).
5. **Voice search mic on Listen page:** no "permission required" snackbar (A#78).
6. **Tour playback / news article / POI map icon:** all open normally.

---

## 3. Shared caveats iOS should be aware of (same as Android — not iOS-specific to fix)

- **Cloud tour *generation* is not ready yet** on either platform. The app updates generation status via raw SQL (`DirectDbUpdate`) to the `:5003` service, which is not deployed to cloud. So test **existing-tour download/play** over cellular (that works); don't expect **new-tour generation** against cloud to complete. Local-WiFi generation is unaffected. (This is a Services + shared-Dart item, not an iOS build task.)
- **`lib/services/direct_db_update.dart` is mislabeled "DEV ONLY"** but is actually in the live tour-status flow. If/when that gets refactored to a REST endpoint, it's shared Dart — iOS inherits the fix automatically. No iOS-specific action.

---

## 4. Process recommendation — keep the two builds correlated going forward

To avoid iOS/Android drift:
- **Single source of truth:** both platforms always build the **same commit** on `services-migration`. When Android AQ bumps the version, iOS builds that same version — don't maintain a separate iOS version line.
- **iOS-only files** that legitimately differ are confined to `ios/` (Info.plist, signing, Podfile). Everything in `lib/` is shared and must not be edited per-platform.
- When Android AQ ships a new version (e.g., the `?? ''` null-guard from the v2.1.1+1 review, or the direct_db_update→REST refactor), iOS re-builds the same commit rather than re-coding.

---

## 5. Summary
| | Action |
|---|---|
| Re-implement Dart changes for iOS | ❌ No — shared codebase, already present |
| Build `Runner` from commit `a877a50`, `pod install`, sign, deploy | ✅ Yes |
| Version in lockstep (2.1.1+1) | ✅ Automatic from shared pubspec |
| ATS / Info.plist networking change | ❌ Not required (Dart bypasses ATS; cloud is HTTPS) |
| Optional `NSLocalNetworkUsageDescription` | ⚪ Nice-to-have, not a blocker |
| Run the 6 parity smoke tests on iPhone | ✅ Yes |
| Cloud generation testing | ⏸ Not ready (shared caveat) — test existing-tour download instead |

**Net:** iOS Amazon-Q's job for parity is a build-and-verify task, not a coding task. Build the same commit, keep the version aligned, confirm the iOS permission strings, optionally add the local-network usage string, and run the same smoke tests. The dual-environment networking and all recent fixes come for free from the shared Dart.
