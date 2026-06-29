# For Mobile Kiro — v1 Security Gate: App Attestation (Play Integrity + App Attest)

**Date:** 2026-06-11
**Scope:** Flutter/Dart app code + platform-specific native setup
**Branch:** `services-migration`
**Current state:** No attestation implementation exists. Zero references to Play Integrity, App Attest, or attestation tokens in the codebase.

---

## Goal

Prevent unauthorized clients (scripts, modified APKs, emulators) from calling cost-bearing API endpoints. Before every generation or translation request, the app must:

1. Generate a platform-specific attestation token (Play Integrity on Android, App Attest on iOS)
2. Attach the token as an HTTP header on the request
3. The gateway (api.audioura.com) validates the token server-side before forwarding to the backend

This is a **security gate** — not user-facing. The user sees no difference. Invalid tokens get a `403 Forbidden` response.

---

## Architecture

```
┌─────────────────────┐         ┌─────────────────────┐
│   Audioura App      │         │   API Gateway        │
│                     │         │  (api.audioura.com)  │
│  1. Generate token  │────────▶│  2. Validate token   │
│  3. Attach header   │         │  4. Forward if valid  │
│     X-Attestation   │         │  5. Reject if invalid │
└─────────────────────┘         └─────────────────────┘
```

**Header:** `X-App-Attestation: <base64-encoded-token>`

**Protected endpoints** (cost-bearing):
- `POST /generate-complete-tour` (orchestrator)
- `POST /translate-with-audio` (translation)
- `POST /generate-complete-tour-background` (orchestrator)

**Unprotected endpoints** (read-only, low cost):
- `GET /status/*`
- `GET /download-tour/*`
- `GET /tours-near/*`
- `GET /health`

---

## Implementation Plan

### Phase 1 — Platform Attestation Service (new file)

**New file:** `lib/services/app_attestation_service.dart`

```dart
import 'dart:io' show Platform;

class AppAttestationService {
  /// Returns a platform-appropriate attestation token.
  /// Android: Play Integrity API token
  /// iOS: App Attest assertion
  /// Returns null if attestation is unavailable (dev mode, emulator).
  static Future<String?> getToken() async {
    if (Platform.isAndroid) {
      return await _getPlayIntegrityToken();
    } else if (Platform.isIOS) {
      return await _getAppAttestToken();
    }
    return null;
  }

  static Future<String?> _getPlayIntegrityToken() async {
    // Use play_integrity Flutter plugin
    // 1. Call IntegrityTokenRequest with cloud project number
    // 2. Return the token string
  }

  static Future<String?> _getAppAttestToken() async {
    // Use platform channel to DCAppAttestService
    // 1. Generate key (one-time, stored in keychain)
    // 2. Attest key with Apple (one-time)
    // 3. Generate assertion for this request
    // 4. Return base64-encoded assertion
  }
}
```

### Phase 2 — Integrate into Endpoints.apiHeaders()

**File:** `lib/config/endpoints.dart`

Add attestation token to headers for protected services:

```dart
static Future<Map<String, String>> apiHeaders(Service s) async {
  final prefs = await SharedPreferences.getInstance();
  final headers = {'Content-Type': 'application/json'};
  final mode = prefs.getString('server_mode') ?? 'local';
  if (mode == 'cloud') {
    final key = (prefs.getString('gateway_api_key') ?? '').trim();
    if (key.isNotEmpty) headers['X-API-Key'] = key;
    
    // Attestation for cost-bearing endpoints only
    if (_isProtectedService(s)) {
      final token = await AppAttestationService.getToken();
      if (token != null) headers['X-App-Attestation'] = token;
    }
  }
  return headers;
}

static bool _isProtectedService(Service s) {
  return s == Service.orchestrator || s == Service.translation;
}
```

### Phase 3 — Android: Play Integrity Setup

**Plugin:** `play_integrity` (or Google's official `google_play_integrity` package)

**Files to modify/create:**
| File | Change |
|------|--------|
| `pubspec.yaml` | Add `play_integrity: ^latest` dependency |
| `android/app/build.gradle.kts` | Add Play Integrity dependency if plugin requires it |
| `lib/services/app_attestation_service.dart` | Implement `_getPlayIntegrityToken()` |

**Setup required (Google Cloud Console):**
1. Link app to Google Play Console (requires package `com.audioura.app`)
2. Enable Play Integrity API in Google Cloud project
3. Get cloud project number for token requests
4. Store project number in app config (NOT a secret — safe to embed)

**Token flow (Android):**
1. App calls `IntegrityManager.requestIntegrityToken(nonce)` 
2. Nonce = SHA-256 of request body (ties token to specific request)
3. Returns encrypted token → send as header
4. Gateway decrypts and validates with Google's servers

### Phase 4 — iOS: App Attest Setup

**Approach:** Platform channel (MethodChannel) to native Swift code using `DCAppAttestService`

**Files to modify/create:**
| File | Change |
|------|--------|
| `ios/Runner/AppDelegate.swift` | Register App Attest method channel |
| `ios/Runner/AppAttestHandler.swift` | New file — native App Attest logic |
| `lib/services/app_attestation_service.dart` | Implement `_getAppAttestToken()` via MethodChannel |

**Token flow (iOS):**
1. First launch: `DCAppAttestService.generateKey()` → store keyId in Keychain
2. First launch: `attestKey(keyId, clientDataHash)` → send attestation to server for registration
3. Each request: `generateAssertion(keyId, clientDataHash)` → returns assertion bytes
4. Base64-encode assertion → send as `X-App-Attestation` header
5. Gateway validates assertion with Apple's servers

### Phase 5 — Graceful Fallback

**Critical:** Attestation must NEVER block functionality in development/testing:

```dart
static Future<String?> getToken() async {
  try {
    if (Platform.isAndroid) return await _getPlayIntegrityToken();
    if (Platform.isIOS) return await _getAppAttestToken();
  } catch (e) {
    DebugLogHelper.addDebugLog('ATTEST: Failed to get token: $e');
    // Don't throw — let request proceed without token
    // Gateway decides whether to enforce or allow
  }
  return null;
}
```

**Gateway behavior:**
- Token present + valid → allow (200)
- Token present + invalid → reject (403)
- Token absent + enforcement OFF (dev/testing) → allow (200)
- Token absent + enforcement ON (production) → reject (403)

---

## Files Summary

| File | Action | Priority |
|------|--------|----------|
| `lib/services/app_attestation_service.dart` | **CREATE** — attestation service | P0 |
| `lib/config/endpoints.dart` | **MODIFY** — add attestation header | P0 |
| `pubspec.yaml` | **MODIFY** — add play_integrity dependency | P0 |
| `ios/Runner/AppAttestHandler.swift` | **CREATE** — native iOS attestation | P1 |
| `ios/Runner/AppDelegate.swift` | **MODIFY** — register method channel | P1 |
| `android/app/build.gradle.kts` | **MODIFY** — if plugin needs gradle config | P1 |

---

## Dependencies

### App-side
- Flutter plugin for Play Integrity (evaluate: `play_integrity`, `google_play_integrity`, or raw MethodChannel)
- iOS native code for `DCAppAttestService` (no Flutter plugin exists — must use MethodChannel)

### Server-side (gateway team)
- Gateway must read `X-App-Attestation` header
- Gateway must validate Android tokens with Google Play Integrity API (decrypt + verify)
- Gateway must validate iOS assertions with Apple's attestation endpoint
- Gateway must have enforcement toggle (OFF during dev, ON for production)
- Gateway must return `403` with `{"error": "attestation_failed"}` on invalid tokens

### External accounts
- Google Play Console: app must be registered (even for internal testing track)
- Apple Developer: App Attest requires a valid provisioning profile (already have Team ID `4HGRU6TKGQ`)
- Google Cloud: Play Integrity API must be enabled, project number obtained

---

## Test Criteria

### Development (enforcement OFF)
- [ ] App generates token on Android (debug log: `ATTEST: Token generated (X bytes)`)
- [ ] App generates assertion on iOS (debug log: `ATTEST: Assertion generated (X bytes)`)
- [ ] Token attached to `X-App-Attestation` header on generation requests
- [ ] Requests succeed even if token generation fails (graceful fallback)
- [ ] Local mode: no attestation attempted (header not sent)

### Production (enforcement ON)
- [ ] Valid app on real device → generation works
- [ ] Modified APK (tampered signature) → gateway returns 403
- [ ] Emulator without Play Integrity support → gateway returns 403 (or allows if fallback configured)
- [ ] Request replay (same token reused) → gateway returns 403 (nonce prevents replay)

---

## Nonce Strategy

Tie each attestation token to the specific request to prevent replay:

```dart
import 'dart:convert';
import 'package:crypto/crypto.dart';

String _generateNonce(Map<String, dynamic> requestBody) {
  final bodyString = jsonEncode(requestBody);
  final bytes = utf8.encode(bodyString);
  return sha256.convert(bytes).toString();
}
```

This ensures a token generated for one tour request can't be replayed for a different request.

---

## Timeline Recommendation

1. **Phase 1-2** (app service + header integration): 1 session — no platform-specific code yet, just the abstraction
2. **Phase 3** (Android Play Integrity): 1 session — plugin integration + testing on real device
3. **Phase 4** (iOS App Attest): 1 session — native Swift code + method channel
4. **Phase 5** (gateway enforcement): Services team — independent of app work

Phases 1-2 can ship immediately (token will be `null` until Phase 3/4, and gateway enforcement is OFF). This lets the gateway team build their validation logic in parallel.

---

## Version Impact

This will require a version bump (new dependency, new native code). Suggest bundling with the next feature version after v2.1.1+7 poll hardening is validated.
