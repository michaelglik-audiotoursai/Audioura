# SUBMISSION — LOCAL-598: Subscription levels, part 3 (the app)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-598-levels-app`
**Base:** `subscribed` @ `04eee1d` (`git merge-base --is-ancestor 04eee1d HEAD` → exit 0)
**App version:** `2.4.3+29` (pubspec kept CRLF)

Part 3 of the subscription-levels work (SUBSCRIPTION_LEVELS.md, D613): the
Flutter app — plan screen, consumable IAP, renew/lapse, 3-day warning, device
ids on metered calls, actionable refusals — plus the server-side offline Apple
verification that gates a purchase grant.

## Commits (7, on top of `subscribed` 04eee1d)

```
cbb51ca D1: send device id (user_id/secret_id) on metered edit calls
f9b36e4 D3+D4: plan screen, consumable IAP (iOS StoreKit 2), hide old wallet UI
77c743a D2: app-open flow — renewal sheet and 3-day warning banner
dedd70a D6: actionable refusals in the UI (generate + edit)
8c18039 D5: offline Apple StoreKit 2 JWS verification (IAP_VERIFY_MODE=apple)
2e522db D8: Dart unit tests — refusal->UI mapping and renewal-sheet logic
937ba33 D7: version 2.4.3+29; iOS build compiles
```

---

## Deliverable 1 — device id on every metered call

**Fix:** `audio_tour_app/lib/services/tour_editing_service.dart`. The edit path
(`TourEditingService.updateMultipleStops` → `/tour/<id>/update-multiple-stops`,
and the single-stop `updateStop` → `/tour/<id>/update-stop`) sent **no** device
id, so LOCAL-595 refused add-stops edits with `401 user_id_required`. Both calls
now attach `user_id` (gateway/auth key) **and** `secret_id` (the metered-count
key LOCAL-595 reads), carrying the single stored `user_id` the generate call
already uses (`_deviceIdFields()` reads `SharedPreferences['user_id']`).

**Audit of metered calls (the two gated ops are `generate` and
`edit_add_stops`):**

| Call | Endpoint | Carried id before? | Now |
|---|---|---|---|
| Generate (foreground) | orchestrator `/generate-complete-tour` | ✅ `user_id` (tour_generator_screen.dart ~L240) | unchanged |
| Generate (background) | orchestrator `/generate-complete-tour` | ✅ `user_id` (~L1624) | unchanged |
| Edit add/modify stops | tour-editing `/tour/<id>/update-multiple-stops` | ❌ **none** | ✅ `user_id` + `secret_id` |
| Edit single stop | tour-editing `/tour/<id>/update-stop` | ❌ none | ✅ `user_id` + `secret_id` |

Free operations (listen, download, read articles, reuse-translation, re-voice
edits that add no stops) are not metered per the design and were left alone.

---

## Deliverable 2 — app open flow

`main_screen.dart` (already a `WidgetsBindingObserver`) calls
`POST /entitlements/app-open` on launch (`initState`) and on every resume
(`didChangeAppLifecycleState`), guarded against overlap.

- **`lib/renewal_logic.dart`** — a PURE, unit-tested `decideRenewalAction(ent,
  lastWarnedAnniversary)`:
  - `renewal_prompt` (at/after anniversary) → show the renew-or-lapse sheet.
  - `warn_renewal` (within 3 days) → show the banner **once per anniversary**,
    keyed on the anniversary string persisted in
    `SharedPreferences['renewal_last_warned_anniversary']`; a new pack warns
    again.
  - `renewal_prompt` beats `warn_renewal`.
- **`lib/widgets/renewal_sheet.dart`** — `showRenewalSheet` ("Your pack's month
  is up — Renew ($10/$25) or continue on the free level"). Renew → `PlanScreen`
  (buy); continue → `POST /entitlements/lapse`; dismiss → unchanged, asked again
  next open. `showRenewalWarningBanner` is the one-time 3-day MaterialBanner. All
  copy says nothing is charged automatically and there are no refunds.
- **`lib/services/entitlements_service.dart`** — `me()` / `appOpen()` / `lapse()`
  against `Service.userDb` with a defensive `Entitlements` model (safe
  `Entitlements.unknown` fallback on any failure, so a network blip never pops a
  sheet or blocks the UI).

---

## Deliverable 3 — plan screen; old wallet UI hidden

- **`lib/screens/plan_screen.dart`** (Settings → **Your plan**): current level
  in plain words, allowances left (from `/entitlements/me`), the anniversary
  date, L3/L4 buy buttons, and the five-level table in plain words.
- **`lib/screens/about_screen.dart`**: the old purple **Wallet** card (which
  opened `WalletScreen` — balance / Pay-Per-Use / Unlimited / top-ups) is
  **replaced** by an indigo **Your plan** card that routes to `PlanScreen`.

**Where the old wallet / PPU / Unlimited UI lives (as requested):**
- `audio_tour_app/lib/screens/wallet_screen.dart` — the tier/balance/top-up
  screen. **Now unreachable from Settings** (its only nav entry was the About
  card we replaced). Left on disk, unreferenced; its `wallet_*` tables stay
  read-only per SUBSCRIPTION_LEVELS.md. `lib/main_wallet_proof.dart` is a
  separate debug entry point, not in the nav.
- `audio_tour_app/lib/screens/subscription_management_screen.dart` is **not**
  tier UI — it manages newsletter/publisher login credentials. It is already
  unreferenced from the nav and was left untouched.

---

## Deliverable 4 — consumable IAP, iOS first

- **`lib/services/iap_service.dart`** — StoreKit 2 (enabled via
  `InAppPurchaseStoreKitPlatform.enableStoreKit2()` on iOS). Products
  `audioura.pack.l3` ($10) and `audioura.round.l4` ($25), both **consumable**
  (`buyConsumable`, never a subscription). On a `purchased`/`restored` event the
  service POSTs `{store:'apple', transaction_id, product, user_id,
  signed_transaction}` — where `signed_transaction` is the StoreKit 2 JWS
  (`verificationData.serverVerificationData`) — to `/purchases/verify`, and
  **grants only on the server's OK** (200, or 409 already-verified treated as
  success), then calls `completePurchase`. A failed verify still completes the
  StoreKit transaction (so it stops redelivering) but does **not** grant.
- **`ios/Audioura.storekit`** — Xcode StoreKit configuration file with both
  Consumable products for local testing (the real products are created later in
  App Store Connect by Michael).
- **Android is out of scope:** `kAndroidBillingEnabled = false`. `buy()` returns
  `unavailable` on Android and `PlanScreen` hides the Android buy buttons with a
  "coming soon" note.
- `pubspec.yaml`: `in_app_purchase ^3.2.0` + `in_app_purchase_storekit ^0.3.19`
  (resolved 3.2.2 / 0.3.22+1), CRLF preserved.

---

## Deliverable 5 — server-side Apple verification (offline)

`IAP_VERIFY_MODE=apple` in `user-tracking/entitlements_api.py` now verifies the
StoreKit 2 JWS **offline** — no API key, no network:

- **`user-tracking/apple_jws_verifier.py`** (pure, `cryptography` only):
  `verify_signed_transaction` decodes the compact JWS, then
  1. reads the `x5c` chain from the JOSE header,
  2. **pins the root** — the chain's final cert must be byte-identical (SHA-256
     fingerprint) to the bundled Apple Root CA G3,
  3. verifies the chain signatures (root → intermediate → leaf),
  4. verifies the ES256 JWS signature with the leaf public key (JWS raw `r||s`
     → DER),
  5. only then trusts the payload and checks `bundleId ==
     com.audioura.audiotours`, `productId`, and `type == Consumable`.
  Every failure raises `JwsVerificationError` with a stable `.code`.
- **`user-tracking/apple_root_ca_g3.pem`** — the real Apple Root CA G3 public
  cert (SHA-256 `63:34:3A:BF…91:79`, matching Apple's published value).
- `verify_purchase` gains the `apple` branch; **stub mode is kept** for tests.
  The JWS `transactionId` is authoritative — it is what gets recorded and
  idempotency-checked, not the client-supplied id. `transactionId` uniqueness is
  still enforced by the `purchases.transaction_id` UNIQUE constraint (the same id
  never grants twice). The endpoint accepts either the store product id
  (`audioura.pack.l3`) or the server key (`l3_pack_10`) and maps between them.
- `requirements.txt` += `cryptography==43.0.1`.

---

## Deliverable 6 — refusals in the UI

`lib/utils/tour_error_resolver.dart` (pure, unit-tested) gained
`refusalActionFor(body)` mapping the subscription error_codes to a button:

| error_code | action / button |
|---|---|
| `plan_limit_daily`, `plan_limit_monthly`, `pack_exhausted`, `level_cannot_generate` | **Buy a pack** → PlanScreen |
| `stops_over_plan`, `by_reference_unavailable` | **Edit request** → back to the form |
| `renewal_due`, `user_id_required` | **Your plan** → PlanScreen |

- **Generate** (`tour_generator_screen.dart`): the initial
  `/generate-complete-tour` non-200 handler and the poll 429 branch now detect a
  structured refusal (429/401 with `error_code`) and show `_showRefusalDialog` —
  the server's **own `message`** plus the matching button. The old hardcoded
  "Daily tour limit reached" snackbar is gone; the user never sees "Unable to
  generate tour" for a plan refusal.
- **Edit** (`tour_editing_service.dart` + `edit_tour_screen.dart`):
  `updateMultipleStops` throws a typed `TourEditRefusal(statusCode, body)` on a
  429/401 refusal; `edit_tour_screen` catches it and shows the same message +
  matching button instead of "Save failed".
- **Join queue:** LOCAL-596's queue endpoints are **not** on this base, so the
  "Join the queue" button is shown **disabled with "coming soon"** (the action
  enum reserves `joinQueue` for a future wiring).

---

## Deliverable 7 — version & build

- `pubspec.yaml`: `2.4.2+28` → **`2.4.3+29`** (CRLF preserved).
- **`flutter analyze`:** 77 errors, **all pre-existing** and in files this task
  never touched — `lib/services/audio_handler.dart` (62),
  `lib/widgets/map_page.dart` (10), `lib/services/tour_service.dart` (3),
  `lib/screens/subscription_management_screen.dart` (2). **Zero new errors** in
  any file added or changed here.
- **`flutter build ios --no-codesign`:** `✓ Built build/ios/iphoneos/Runner.app
  (37.3MB)`, Xcode build done — with the new IAP plugins (pod install linked
  `in_app_purchase_storekit`).
- Not installed on anyone's phone; LEAD installs.

---

## Deliverable 8 — tests (exits pasted)

**Dart** (`cd audio_tour_app && flutter test test/refusal_action_test.dart
test/renewal_logic_test.dart test/tour_error_resolver_test.dart`):

```
00:00 +32: All tests passed!
```

- `test/refusal_action_test.dart` — every subscription error_code →
  action mapping, unknown/absent → none, generation codes are not plan actions,
  labels, and a plan refusal keeps the server message.
- `test/renewal_logic_test.dart` — `decideRenewalAction` sheet/banner rules,
  once-per-anniversary, new-anniversary-warns-again, and defensive
  `Entitlements` parsing.

**Python** (`cd user-tracking && python3 test_local598_apple_jws.py`):

```
PASS test_bundled_apple_root_is_valid
PASS test_happy_path
PASS test_malformed_jws_rejected
PASS test_non_consumable_rejected
PASS test_product_mismatch_rejected
PASS test_tampered_payload_fails_signature
PASS test_wrong_bundle_rejected
PASS test_wrong_root_rejected

8/8 passed
EXIT: 0
```

Self-signed test chain covers the happy path plus every negative case: **wrong
root** (the pin working), **wrong bundle**, **non-consumable**, **product
mismatch**, **tampered payload** (→ `signature_invalid`, i.e. a forged/replayed
transaction cannot pass), and a malformed JWS; plus a check that the bundled
real Apple Root CA G3 parses and is self-signed.

---

## Constraints honoured

- Branched from HEAD (`subscribed` @ `04eee1d`), never from `origin/*`.
- No `audioura-*` containers touched/rebuilt/renamed; no real purchase; no App
  Store Connect change; no GCloud; no DELETE.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
  `SUBSCRIPTION_LEVELS.md`, or `.continuous_dev/STATUS.md`.
- Committed after each deliverable.
