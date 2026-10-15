# SUBMISSION — LOCAL-699: Working Buy buttons for the $10 Pack and Curator on every platform (TEST PURCHASE on a stub server)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-699-plan-buy-buttons` (from `subscribed`, base `ac7f1adf`)
**Report:** Michael 2026-10-15 (Pixel-4): About → Your plan describes the $10 Pack and
the Curator plan but shows **no button to buy them**.

## Problem
`audio_tour_app/lib/screens/plan_screen.dart` hid the buy buttons on Android behind
`kAndroidBillingEnabled`. That flag went **true** in LOCAL-696, but Michael's Pixel build
predates it — so on his phone the buttons were gated off and the plan was describable but
not buyable. Two further gaps blocked testing a real buy on the Mac Mini stack:

- the plan screen had **no TEST PURCHASE path** for the pack/Curator (only the per-tour
  Buy sheet did, via `IapService.testPurchaseTour`), so against a stub-verification server
  (`IAP_VERIFY_MODE=stub`, where no Apple/Google products exist yet) the only buttons
  called the real store and failed; and
- a missing store product surfaced a vague "not available right now" with no indication it
  was the store that wasn't ready.

## What was built

### 1. `GET /purchases/mode` — the server tells the app how it verifies
`user-tracking/entitlements_api.py` gains a tiny, DB-free route behind the same
`X-API-Key` gate as the other entitlements endpoints:

```
GET /purchases/mode -> {"mode": "stub"|"apple"|"google",
                        "stub": <bool>, "verifies_real": <bool>}
```

A LOCAL/Mac Mini stack running `IAP_VERIFY_MODE=stub` answers `stub=true`; cloud (apple,
the default) answers `stub=false`. This replaces the app's device-side `server_mode`
**guess** with the server's own authoritative answer, so the TEST PURCHASE path is offered
**exactly** when the server will accept a `store='stub'` body — never against a real
apple/google server (which would reject it), never hidden on a stub server (which has no
store products yet).

### 2. App: Buy buttons always visible on BOTH platforms
`plan_screen.dart` `_buyCard()`:
- The `$10 Pack` and `Curator ($25)` buttons are **always rendered** on both iOS and
  Android. Removed the `androidHidden = Platform.isAndroid && !kAndroidBillingEnabled`
  gate and the "coming to Android soon" copy (and the now-unused `dart:io` import). The
  buttons no longer depend on platform or any billing flag.

### 3. App: pack/Curator TEST PURCHASE on both platforms, wired to the server mode
`audio_tour_app/lib/services/iap_service.dart`:
- `purchasesModeIsStub()` — asks `GET /purchases/mode`; falls back to the existing
  device-side `isLocalStubMode()` when the endpoint is unreachable or returns a non-200 /
  malformed body (an older server, or a transient error), so the buy flow still works. Not
  cached — the mode can change as a tester switches between a LOCAL and a cloud server.
- `testPurchasePack(IapProduct)` — the pack/Curator twin of `testPurchaseTour`. Posts
  `{store:'stub', transaction_id:'TEST-699-…', product:<storeId>, user_id}` straight to
  `/purchases/verify`; the stub server grants the level and resets the pack exactly as a
  real purchase would. 200 **or** 409 (`already_verified`) → granted (idempotent).

`plan_screen.dart`:
- `_stubMode` state, resolved from `purchasesModeIsStub()` on load (never blocks the
  buttons from showing). In stub mode `_buy()` runs `testPurchasePack`; otherwise it drives
  the real store via the unchanged `IapService.buy()` (StoreKit on iOS, Play billing on
  Android — LOCAL-696). An amber **TEST PURCHASE — no real charge** banner shows above the
  buttons in stub mode, mirroring the tour Buy sheet.
- A test seam `initialStubMode` (null in production, like the existing
  `initialEntitlements`) lets widget tests render either state with no running user-api.

### 4. App: clear "not available on this store yet" message
- `IapService.buy()`'s product-not-found result now carries
  **"This pack isn't available on this store yet. Please try again later."** instead of the
  generic "not available right now".
- `plan_screen.dart` `_buy()` shows the **specific** `result.message` on an `unavailable`
  result, so a missing store product reads as a clear store-not-ready message rather than a
  silent/vague failure.

On a real-verification server the paths are unchanged: Android uses Play billing and iOS
StoreKit (LOCAL-696), both through `IapService.buy()`.

## Tests
- `tests/test_local699_purchases_mode.py` — **4 tests**: stub → `{stub:true,
  verifies_real:false}`; apple → `{stub:false, verifies_real:true}`; google → likewise;
  auth enforced (401 without / with a wrong key, 200 with the right key). No DB needed.
- `audio_tour_app/test/plan_screen_buy_buttons_test.dart` — **6 tests**: both the $10 Pack
  and Curator buttons are visible on **iOS and Android** (`ThemeData.platform` override) in
  both stub and real-verification mode; the TEST PURCHASE banner shows **only** in stub
  mode and is absent on a real server, with the buttons present in both; the old "coming to
  Android" copy is gone.

### Results (this machine)
- `python3 -m pytest tests/test_local699_purchases_mode.py -q` → **4 passed**.
- `flutter test test/plan_screen_buy_buttons_test.dart test/plan_screen_level_aware_test.dart
  test/plan_screen_free_card_test.dart` → **24 passed** (6 new + 18 existing plan-screen
  tests, no regressions).
- `flutter analyze lib/screens/plan_screen.dart lib/services/iap_service.dart
  test/plan_screen_buy_buttons_test.dart` → **No issues found**.

Live, on-device verification against the Mac Mini stub stack (buttons visible on the Pixel,
a TEST PURCHASE granting the pack) is **unproven** here — it needs Michael's phone and the
LOCAL server. The server endpoint, the app wiring and the widget/server tests are proven as
above.

## Build
- App build number bumped `2.4.18+53` → `2.4.18+54` (`audio_tour_app/pubspec.yaml`).

## Files changed
- `user-tracking/entitlements_api.py` — new `GET /purchases/mode` route.
- `audio_tour_app/lib/services/iap_service.dart` — `purchasesModeIsStub()`,
  `testPurchasePack()`, clearer store-missing message.
- `audio_tour_app/lib/screens/plan_screen.dart` — always-visible buttons, stub TEST
  PURCHASE path + banner, specific unavailable message, `initialStubMode` seam.
- `audio_tour_app/pubspec.yaml` — build number 53 → 54.
- `tests/test_local699_purchases_mode.py` (new), `audio_tour_app/test/plan_screen_buy_buttons_test.dart` (new).

## Scope / safety
- App + user-api `entitlements_api.py` only. No DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE /
  `.continuous_dev` edits.
- iOS/Apple and Android/Play real-purchase paths unchanged; the stub path is additive and
  the mode endpoint is fail-safe (app falls back to its device guess if it's absent).
- No live container checks run; no `-p audioura`, no `audioura-*` rename.
- Commit per step; branch `LOCAL-699-plan-buy-buttons` pushed to `origin`.
