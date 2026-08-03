##### READY FOR REVIEW

# LOCAL-157: Build a debug APK with the wallet UI, pointed at the subscribed stack

**Branch:** `kiro/local157-wallet-debug-apk`  
**Commit:** `d1c05f1`  
**Commits ahead of subscribed:** 3  

---

## Summary

Debug APK built with original toolchain versions (no bumps). JDK selection
moved to `~/.gradle/gradle.properties` (machine-local, never committed).
The `--dart-define` approach from round 1 is preserved unchanged.

---

## Defect 1 — Fixed: Machine-specific absolute path removed

`audio_tour_app/android/gradle.properties` no longer contains:
```
org.gradle.java.home=/Users/micha/jdks/jdk-21.0.12+8/Contents/Home
```

This setting now lives in `~/.gradle/gradle.properties` (per-user, never
committed):
```
# Machine-local JDK for Gradle (JDK 26 jlink incompatible with Android SDK modules)
org.gradle.java.home=/Users/micha/jdks/jdk-21.0.12+8/Contents/Home
# Extra heap for JetifyTransform on this machine
org.gradle.jvmargs=-Xmx4G
```

**Proof — no absolute paths in tracked files:**
```
$ git grep "/Users/micha" -- audio_tour_app/
(no output)
```

## Defect 2 — Fixed: All toolchain bumps reverted

| Component | Round 1 | Reverted to |
|---|---|---|
| Java target | 17 | **11** |
| Gradle | 9.4.1 | **8.10.2** |
| AGP | 8.10.1 | **8.7.0** |
| Kotlin | 2.1.20 | **1.8.10** |

**Why it works:** The only issue was JDK 26's `jlink` incompatibility with
Android SDK modules. Setting `org.gradle.java.home` to JDK 21 in the
user-local file completely resolves this — no shared toolchain changes needed.

**Build succeeds on original versions:**
```
$ flutter build apk --debug \
    --dart-define=WALLET_DEBUG_PORT=5102 \
    --dart-define=DEBUG_SERVER_IP=192.168.0.136
...
✓ Built build/app/outputs/flutter-apk/app-debug.apk
```

---

## APK Output

- **Path:** `audio_tour_app/build/app/outputs/flutter-apk/app-debug.apk`
- **Size:** 157 MB
- **Not committed** (gitignored via `build/` in `.gitignore`)

---

## Resolved Base URL — contains 5102

The `--dart-define` mechanism in `endpoints.dart`:
```dart
static const _walletDebugPort = int.fromEnvironment('WALLET_DEBUG_PORT');
// → 5102

Service.orchestrator: _walletDebugPort > 0 ? _walletDebugPort : 5002,
// → 5102

static const _debugServerIp = String.fromEnvironment('DEBUG_SERVER_IP');
// → "192.168.0.136"

if (_debugServerIp.isNotEmpty) {
  return 'http://$_debugServerIp:${_localPorts[s]}';
}
// → "http://192.168.0.136:5102"
```

All wallet service calls (`/wallet/<id>`, `/wallet/<id>/transactions`,
`/plans/available`, `/wallet/<id>/topup`) route through `Service.orchestrator`,
so they resolve to `http://192.168.0.136:5102/...`.

---

## Server-side confirmation — endpoints answer on LAN IP

```
$ curl -s http://192.168.0.136:5102/plans/available
[{"display_name":"Free","features":["Browse pre-made tours","Limited tour downloads"],
"period":"forever","plan_id":"free","price_usd":0.0},
{"display_name":"Pay-Per-Use","features":["Unlimited tour generation",
"Unlimited news articles","Pay only for what you use","Credits never expire"],
"period":"month","plan_id":"ppu","price_usd":2.0},
{"display_name":"Unlimited","features":["Unlimited tour generation",
"Unlimited news articles","No per-use charges","Priority processing",
"All future features included"],"period":"month","plan_id":"unlimited","price_usd":50.0}]

$ curl -s http://192.168.0.136:5102/wallet/test_user
{"balance_usd":0.0,"cost_stop_progress":null,"low_balance":false,
"period_end":"2026-09-01T00:00:00+00:00","period_spend_usd":0.0,
"period_start":"2026-08-01T00:00:00+00:00","plan":"free"}

$ curl -s http://192.168.0.136:5102/wallet/test_user/transactions
[]
```

All three wallet endpoints return valid JSON on the LAN IP.

---

## Build warnings (all pre-existing, non-blocking)

1. **NDK version mismatch** (info only): Gradle suggests ndkVersion 28.2.13676358;
   project uses 27.0.12077973. Build succeeds — backward compatible.

2. **"source value 8 is obsolete"** (×8 occurrences): Third-party plugin code
   targets Java 8. Non-fatal warnings from JDK 21 compiler.

3. **flutter analyze: 79 errors** — all pre-existing in dead/orphaned files:
   - `audio_handler.dart`: references `audio_service`/`just_audio` (not in pubspec)
   - `map_page.dart`: references `mapbox_gl` (not in pubspec)
   - `tour_service.dart`: references non-existent `api_config.dart`
   - `subscription_management_screen.dart`: calls undefined methods on `SubscriptionService`
   - `widget_test.dart`: references non-existent `package:audio_tour_app/main.dart`

   None of these files are imported by the live app tree — the build succeeds
   because they're unreachable dead code.

4. **1311 info-level lint warnings** (mostly `avoid_print` in test files,
   `prefer_const_declarations`). Standard for a project this size.

---

## Device install status

No Android device or emulator connected to this Mac. `flutter devices` shows:
- macOS (desktop)
- Chrome (web)
- iPhone (wireless, iOS — cannot run Android APK)

The APK is ready for sideloading via ADB or file transfer.

---

## Per-file changes (from subscribed)

| File | Change |
|---|---|
| `audio_tour_app/lib/config/endpoints.dart` | +15 lines: `WALLET_DEBUG_PORT` and `DEBUG_SERVER_IP` dart-define constants with conditional port override |
| `SUBMISSION_LOCAL-157.md` | This file |

**Android build files:** net zero change from `subscribed` (round 1 bumps
reverted in commit `d1c05f1`).

---

## Limitations

1. **Not tested on a device.** No Android device/emulator available on this Mac.
   The APK compiles and packages, but no runtime behavior confirmed.
2. **Pre-existing analyzer errors** in 5 dead files — not introduced by this task.
3. **`~/.gradle/gradle.properties` is machine-local.** Any new machine building
   this project with JDK 26 will need the same `org.gradle.java.home` pointing
   at a JDK 17–21. This is standard Gradle practice and documented in the file.
4. **Disk space was tight** (148MB free before cleanup). Freed 2GB by removing
   Xcode DerivedData and a stale JDK tarball from `/tmp`.

---

## git status --short (final)

```
(empty — clean working tree)
```
