# For Mobile Amazon-Q — Attestation Contract Change (align with gateway)

**Date:** 2026-06-11
**Reviewer:** Claude (independent code reviewer)
**Companion doc (services):** `claude_review_attestation_scaffold_contract_kiro_2026_06_11.md`
**Why:** Kiro deployed the log-only attestation scaffold, but it speaks a **different protocol** than your Phase 1-2 plumbing. Two mismatches must be reconciled **before** you implement Phase 3/4 token generation, or tokens will never validate. This doc is the agreed contract and the changes on your side. **Token generation stays stubbed for now** — this is just re-wiring the plumbing to match the gateway.

---

## What changed and why

Your current code computes its own nonce as `sha256(jsonEncode(requestBody))` and sends the token in `X-App-Attestation`. The gateway instead **issues** a nonce (`GET /attest-nonce`) and currently reads different header names. We're standardizing on the **server-issued nonce** model — it's the classic Play Integrity / App Attest flow and gives true single-use replay protection. This **supersedes** the earlier "hash the request body" guidance (Q1/Q8); the gateway's issued-nonce approach is the stronger pattern and it's already deployed.

## The agreed contract (both sides implement this)

1. App calls **`GET /attest-nonce`** (API-key-gated) → receives a **64-char hex nonce, valid 300s, single-use**.
2. App binds **that** nonce into the platform attestation:
   - Android: pass it as the Play Integrity `requestHash`/nonce.
   - iOS: use it in the App Attest `clientDataHash`.
3. App sends the resulting token in a **single header `X-App-Attestation`**, plus **`X-App-Platform: android|ios`** so the gateway knows how to verify.
4. Gateway verifies the token and that the embedded nonce is one it issued and hasn't expired or been used.

*(Optional v2 hardening, not required now: bind both — `clientDataHash = sha256(server_nonce + request_body)` — for freshness + request-binding.)*

## Your changes

### 1. `app_attestation_service.dart` — fetch the nonce, drop the body-hash
- **Remove** `_generateNonce(requestBody)` (the `sha256(jsonEncode(requestBody))` logic).
- **Add** `_fetchNonce()` → `GET /attest-nonce` with API-key headers, returns the hex nonce string (or null on failure).
- `getToken()` flow becomes: fetch nonce → if null, return null (graceful, never block) → pass nonce into `_getPlayIntegrityToken(nonce)` / `_getAppAttestToken(nonce)` (still stubs returning null for now).
- `getToken()` no longer needs `requestBody` for the nonce. Keep the parameter only if you'll do the optional hybrid later; otherwise drop it to simplify.

```dart
static Future<String?> getToken() async {
  try {
    final nonce = await _fetchNonce();          // GET /attest-nonce
    if (nonce == null) return null;             // graceful — gateway logs absence in log-only mode
    if (Platform.isAndroid) return await _getPlayIntegrityToken(nonce);
    if (Platform.isIOS)     return await _getAppAttestToken(nonce);
  } catch (e) {
    await DebugLogHelper.addDebugLog('ATTEST: token error: $e');
  }
  return null;
}
```

### 2. `endpoints.dart` — header + nonce endpoint
- Keep attaching the token under **`X-App-Attestation`** (unchanged) and **add `X-App-Platform`** (`'android'`/`'ios'`).
- Since `getToken()` no longer needs `requestBody`, you can simplify `apiHeaders` back to not threading it through (and likewise drop the `requestBody:` you added to the generate/translate/status callers — they're no longer needed for the nonce). *Confirm this with the cost of touching those call sites; if simpler to leave the param unused, that's fine.*
- Add the `/attest-nonce` route to your `Service`/URL mapping so `_fetchNonce()` can build the URL (gateway-routed, root path, API-key-gated).

### 3. No change to the stubs
`_getPlayIntegrityToken` / `_getAppAttestToken` stay returning null until Phase 3/4. The point of this commit is that when you *do* implement them, they bind the **fetched** nonce and the gateway already understands the protocol.

## Test criteria (this commit, log-only)

- [ ] In cloud mode, a protected request triggers a `GET /attest-nonce` call (visible in debug logs), token still null → request proceeds (graceful fallback).
- [ ] Header sent is `X-App-Attestation` (when non-null) + `X-App-Platform`; no `X-Integrity-Token`/`X-App-Attest`.
- [ ] Local mode: no nonce fetch, no attestation headers.
- [ ] Nonce fetch failure (e.g. offline) never blocks the request.
- [ ] `flutter analyze` clean; generation + translation still work (since you may be removing the `requestBody:` plumbing).

## Coordinate with Kiro

The header name (`X-App-Attestation` + `X-App-Platform`) and the issued-nonce flow are the **shared contract** — Kiro is updating the gateway to read those exact headers and to keep the nonce store working across Cloud Run instances. Don't implement Phase 3/4 until both sides confirm this contract is live on the gateway in log-only mode.
