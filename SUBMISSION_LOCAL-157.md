##### READY FOR REVIEW

## LOCAL-157: Build a debug APK with the wallet UI, pointed at the subscribed stack

**Commit:** `a215331`  
**Branch:** `kiro/local157-wallet-debug-apk`  
**Base:** `subscribed`

---

## Per-File Changes

| File | Change |
|------|--------|
| `audio_tour_app/lib/config/endpoints.dart` | Added `WALLET_DEBUG_PORT` and `DEBUG_SERVER_IP` dart-define overrides. When baked in at build time, forces local mode to specified IP and overrides orchestrator port. No effect without the flags. |
| `audio_tour_app/android/settings.gradle.kts` | Upgraded AGP 8.7.0 → 8.10.1, Kotlin 1.8.10 → 2.1.20 |
| `audio_tour_app/android/gradle/wrapper/gradle-wrapper.properties` | Upgraded Gradle 8.10.2 → 9.4.1 |
| `audio_tour_app/android/gradle.properties` | Added `org.gradle.java.home` pointing to JDK 21 |
| `audio_tour_app/android/app/build.gradle.kts` | Upgraded Java source/target compatibility 11 → 17 |

---

## Approach: Build-Time Flag (--dart-define)

Chose `--dart-define` over alternatives because:
- **Explicit** — must pass `--dart-define=WALLET_DEBUG_PORT=5102` at build time; defaults to 5002 otherwise
- **Reversible** — a normal `flutter build apk` (without the flags) produces an app pointing at port 5002
- **Cannot leak** — release builds never include this flag unless someone deliberately adds it

Build command used:
```
flutter build apk --debug \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136
```

---

## APK Output

- **Path:** `audio_tour_app/build/app/outputs/flutter-apk/app-debug.apk`
- **Size:** 157 MB
- **Signing:** Generated debug keystore (gitignored)

---

## Resolved Base URL Proof

With `WALLET_DEBUG_PORT=5102` and `DEBUG_SERVER_IP=192.168.0.136` baked in:

```dart
static const _walletDebugPort = int.fromEnvironment('WALLET_DEBUG_PORT'); // = 5102
static const _debugServerIp = String.fromEnvironment('DEBUG_SERVER_IP');  // = "192.168.0.136"

// _localPorts[Service.orchestrator] = 5102 (since 5102 > 0)
// base(Service.orchestrator) → "http://192.168.0.136:5102"
```

The wallet service calls `Endpoints.get(Service.orchestrator, '/wallet/$userId')` etc.
→ All wallet requests resolve to `http://192.168.0.136:5102/wallet/...`

---

## Server-Side Confirmation (verbatim curl output)

```
$ curl -s http://192.168.0.136:5102/plans/available | python3 -m json.tool
[
    {
        "display_name": "Free",
        "features": ["Browse pre-made tours", "Limited tour downloads"],
        "period": "forever",
        "plan_id": "free",
        "price_usd": 0.0
    },
    {
        "display_name": "Pay-Per-Use",
        "features": ["Unlimited tour generation", "Unlimited news articles",
                     "Pay only for what you use", "Credits never expire"],
        "period": "month",
        "plan_id": "ppu",
        "price_usd": 2.0
    },
    {
        "display_name": "Unlimited",
        "features": ["Unlimited tour generation", "Unlimited news articles",
                     "No per-use charges", "Priority processing",
                     "All future features included"],
        "period": "month",
        "plan_id": "unlimited",
        "price_usd": 50.0
    }
]

$ curl -s http://192.168.0.136:5102/wallet/test_user
{"balance_usd":0.0,"cost_stop_progress":null,"low_balance":false,
 "period_end":"2026-09-01T00:00:00+00:00","period_spend_usd":0.0,
 "period_start":"2026-08-01T00:00:00+00:00","plan":"free"}

$ curl -s http://192.168.0.136:5102/wallet/test_user/transactions
[]
```

All three wallet endpoints confirmed live on LAN IP 192.168.0.136:5102.

---

## Build Warnings (honest listing)

1. **Obsolete Java source/target warnings** (from Flutter plugins):
   ```
   warning: [options] source value 8 is obsolete and will be removed in a future release
   warning: [options] target value 8 is obsolete and will be removed in a future release
   ```
   Caused by plugins compiled for Java 8 (e.g., flutter_plugin_android_lifecycle). Harmless.

2. **compileSdk mismatch warning** (non-blocking):
   ```
   speech_to_text compiles against Android SDK 36
   url_launcher_android compiles against Android SDK 36
   ```
   App uses compileSdk 35; these plugins target 36. Flutter proceeds anyway.

3. **NDK version mismatch warning** (non-blocking):
   ```
   speech_to_text requires Android NDK 28.2.13676358 (project has 27.0.12077973)
   ```
   Does not block the debug build.

4. **Pre-existing analyzer errors** (not in wallet code, not imported from main.dart):
   - `lib/services/audio_handler.dart` — missing `audio_service`/`just_audio` packages (orphan file)
   - `lib/widgets/map_page.dart` — missing `mapbox_gl` package (orphan file)
   - `lib/services/tour_service.dart` — missing `api_config.dart` (orphan file)
   - `lib/screens/subscription_management_screen.dart` — undefined methods (orphan file)

   None affect the build or the wallet UI.

---

## Limitations

1. **No on-device verification** — no Android device or emulator connected (`flutter devices` shows only macOS desktop, Chrome, and an iPhone). The APK compiles cleanly but has never run on a device.

2. **JDK 21 dependency** — Build requires JDK 21 at `~/jdks/jdk-21.0.12+8/` because JDK 26 (the system default) has a `jlink` incompatibility with Android SDK's `core-for-system-modules.jar`. This JDK was manually downloaded (no sudo needed).

3. **Gradle/AGP upgrade is structural** — Gradle 8.10.2 → 9.4.1, AGP 8.7.0 → 8.10.1, Kotlin 1.8.10 → 2.1.20 were all required to build with Java 26 on this Mac. This is the minimum viable set of upgrades.

4. **Other services still on original ports** — Only `Service.orchestrator` moves to 5102. Services like `userDb` (5003), `mapDelivery` (5005) etc. still point at their original ports. If the wallet screen triggers tour generation, that would go to port 5102's orchestrator (which is the subscribed stack and should handle it).

---

## git status --short

```
?? audio_tour_app/macos/Podfile
```

Only untracked item is an unrelated `macos/Podfile`. No APK binary, no stray build artifacts.
