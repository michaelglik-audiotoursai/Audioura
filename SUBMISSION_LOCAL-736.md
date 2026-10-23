# SUBMISSION — LOCAL-736

**A finished store purchase is never lost (restart mid-purchase), and an
organiser's status says "Organizer".**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-736-purchase-redelivery`
- **Base:** `subscribed` @ `58782f8f`
- **code_sha:** tip of `LOCAL-736-purchase-redelivery` (see `git rev-parse HEAD` / the pushed branch; parented on base `58782f8f`)

## Why

2026-10-22, Michael's iPhone, Apple sandbox (LEAD's `IAP:` log lines):

```
[20:25:35] IAP: update PurchaseStatus.purchased audioura.pass.usd1 id=2000001255837896 pendingStore=null c=null
           IAP: no server product for audioura.pass.usd1 (no staged tour/community)
```

A pass Apple had already **charged** was redelivered at app start (the app had
been restarted, so the in-memory context was gone), mapped to no server product,
and was **FINISHED** (`completePurchase`) — never sent to the server, never
granted. Real money charged, nothing delivered. The same path existed for TOUR
purchases (`_pendingTourId`). Separately, an organiser's "My status" said "Not a
member".

## What changed

### 1. Staged purchase context survives an app restart — `lib/services/iap_service.dart`

- New `StagedPurchaseContext` (pass → `{community_id, length}`, tour →
  `{tour_id}`, plus `staged_at`), persisted in SharedPreferences keyed by the
  **store product id** (`kStagedContextKey(storeId)`), written **before**
  `buyConsumable` in both `buyCommunityPass` and `buyTour` (and cleared if the
  buy throws).
- On a `purchased`/`restored` update with **no in-memory** context,
  `_resolveContext` reads the persisted context back and `_verifyAndGrant`
  verifies with it — so the body reaches `/purchases/verify` with
  `community_id`+`length` (pass) or `tour_id` (tour) even after a restart.
- The persisted context is **cleared only after the server answers 200/409**
  (verified). A failed verify leaves it intact for the next launch.

### 2. A paid transaction is never discarded — `lib/services/iap_service.dart`

- New pure `shouldFinishPassOrTour({isPack, hadContext, verified})`:
  - pack → always finish (today's behaviour; `serverProductForStoreId != null`),
  - pass/tour with **no context anywhere** → **NOT finished** (left for the
    store to redeliver; `completePurchase` is never called, and it is not even
    verified),
  - pass/tour with context → finished **only when verified**; a failed verify
    (402/5xx or unreachable) is left **unfinished** so the next launch retries.
- Loop guard: `_attemptedTxnThisLaunch` ensures **at most one server attempt per
  transaction id per app start**; a redelivery of the same txn in the same
  session is skipped (left for the next launch).
- StoreKit 2 `appAccountToken` was optional ("only if trivial") — not adopted;
  it was not trivial and is not required.

### 3. Organiser status — `lib/widgets/pass_expiry_display.dart`

- `CommunityMyStatus` already receives `isOwner` (server's `is_owner`). When
  true it now shows **"You are the organizer"** instead of "Not a member".
- The Step-down button lives in `community_page_screen.dart`'s `_ownerControls`
  and is **unchanged** (kept).

## Tests

New `test/iap_redelivery_test.dart` (12 tests, all pass). Store/verify/finish are
injected via seams (`completePurchaseOverride`, `readStagedContextOverride`,
`verifyPostOverride`) — no network, no running server, no real plugin. The test
pins `debugDefaultTargetPlatformOverride = iOS` so the Android billing client's
auto-connect does not leak into the suite.

- **UNIT** — persisted pass context, no in-memory context → the verify body
  carries `community_id` + `length` (+ `user_id`).
- **RED test** — a `purchased` pass update with **no context anywhere** →
  `completePurchase` is **NOT** called (and verify is not called). Re-introducing
  the old "finish it anyway" behaviour fails this test.
- **UNIT** — after a 200, the persisted context for that product is **cleared**.
- A failed verify (500) leaves the transaction **unfinished** and the context
  **intact**.
- Per-launch retry guard: the same txn id is attempted **at most once** per app
  start.
- Pure helpers: `shouldFinishPassOrTour`, `verifyBodyAdditionsFor`,
  `StagedPurchaseContext` JSON round-trip / malformed-reject.

Widget — `test/pass_expiry_display_widget_test.dart` (updated):
- **Organiser** sees **"You are the organizer"** (and not "Not a member"), no
  expiry line, no adds-days note.
- A **non-member (not owner)** still sees **"Not a member"**.

### Results

- `flutter analyze` on the four touched files: **no new issues**. The only
  reported `info` is a pre-existing `enableStoreKit2` deprecation at
  `iap_service.dart:345` (in `initAtStartup`, not touched by this change).
- `flutter test` (full suite): **+831 / -7**. The 7 failures are the known
  baseline — all server-dependent integration tests that need a live backend
  (`local109_swipe_e2e_test.dart` ×6, `storied_compat_screens_404_test.dart`
  ×1). **None are in files this change touched; no new failures.**

## Live test

Not run. The change is covered by deterministic unit/red/widget tests with all
store and server interactions injected; no simulator/emulator run was needed.
**Budget spent: $0.00** (≤ $0.10). No purchase-bearing rows touched; no
`DELETE FROM audio_tours`; Michael's phones untouched.

## Files changed

- `audio_tour_app/lib/services/iap_service.dart`
- `audio_tour_app/lib/widgets/pass_expiry_display.dart`
- `audio_tour_app/test/iap_redelivery_test.dart` (new)
- `audio_tour_app/test/pass_expiry_display_widget_test.dart`
