# Storied v2.2.0 — iOS Integration Contract

Handoff document for the iOS development team. Contains all new service endpoints, request/response contracts, and headers that the iOS app needs to integrate for the Storied release.

---

## Version

- Services: `2.2.0.1` (tag: `storied-v2.2.0-services`)
- iOS app target: `2.2.0+1`
- Branch: `storied`

---

## New Endpoints

### 1. POST /user/persona

Save the user's persona preference after onboarding.

**Request:**
```json
{"user_id": "<device_secret_id>", "persona": "art_lover"}
```

**Valid personas:** `art_lover`, `history_buff`, `family`, `first_time_visitor`

**Headers:** `X-API-Key: <gateway_key>`, `Content-Type: application/json`

**Response:** `200 {"saved": true}` or `400`/`401`

---

### 2. GET /user/persona?user_id=X

Retrieve saved persona (call on app launch to check if onboarding was completed).

**Response:** `200 {"persona": "art_lover"}` or `404 {"persona": null}`

---

### 3. POST /tour/share

Share a completed tour. Call after tour generation completes.

**Request:**
```json
{"location": "...", "tour_type": "...", "total_stops": 10, "tour_text": "..."}
```

**Headers:** `X-API-Key`, `Content-Type: application/json`

**Response:** `200 {"share_id": "abc12345", "share_url": "https://audioura.io/tour/abc12345"}`

---

### 4. GET /tour/{tour_id}

Public endpoint — no API key required. Used when opening a shared deep link.

**Response:** `200 {"tour_text": "...", "location": "...", "tour_type": "...", "total_stops": 10, "share_count": 3}`

**404** if tour_id is unknown.

---

### 5. POST /referral/create

Generate a referral code for the current user.

**Request:** `{"user_id": "<device_secret_id>"}`

**Response:** `200 {"referral_code": "ABC123", "referral_url": "https://audioura.io/join/ABC123"}`

---

### 6. POST /referral/redeem

Redeem a referral code (call when new user enters a code during onboarding).

**Request:** `{"referral_code": "ABC123", "new_user_id": "<new_device_secret_id>"}`

**Response:** `200 {"redeemed": true, "referrer_user_id": "..."}` or `404`

---

## Attestation Headers (iOS — App Attest)

The iOS app must send these headers on every cost-bearing API request:

| Header | Value | Notes |
|--------|-------|-------|
| `X-App-Attestation` | Base64-encoded App Attest assertion | Generated via `DCAppAttestService` |
| `X-App-Platform` | `ios` | Identifies platform for server-side routing |
| `X-App-Key-ID` | The key identifier from `generateKey()` | Used for server-side verification |

**Current mode:** `log_only` — tokens are logged but NEVER block requests. The app should send tokens even if attestation setup fails (send empty string — server handles gracefully).

---

## Tour Generation with Persona

When calling `/generate`, include the `user_id` field:

```json
{"location": "...", "tour_type": "...", "total_stops": 10, "user_id": "<device_secret_id>"}
```

The server will look up the stored persona and use it to personalize the tour narrative.

---

## Deep Links

Share URLs have format: `https://audioura.io/tour/{share_id}`

iOS should register a Universal Link handler for `audioura.io/tour/*`. On open:
1. Extract `share_id` from URL path
2. Call `GET /tour/{share_id}` or `GET /resolve/tour/{share_id}`
3. Display the returned tour text

---

## Rollback Plan

See `storied_rollback_plan.md` for the 3-tier rollback procedure.

---

## Release Notes

See `storied_release_notes.md` for tester-facing feature descriptions.
