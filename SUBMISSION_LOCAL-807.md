# SUBMISSION — LOCAL-807: Auto-renewing subscriptions (Day / Weekly / Monthly / Annual), Apple first, Google ready

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-807-subscriptions` (from `subscribed`, base `7267c4d8`)
**Design of record:** D733, superseded in product detail by **D734** (Michael, 2026-10-29).

`git merge-base --is-ancestor 7267c4d8 HEAD` → exit 0 (correct base).

## Products (D734 — prices are DATA, in the DB and the store, never hard-coded)
| Plan | Price | Store product id | Term | New tours | Renews |
|------|-------|------------------|------|-----------|--------|
| Day pass | $2.99 | `audioura.sub.day` | 24 h | 3 | No (non-renewing) |
| Weekly | $4.99 | `audioura.sub.weekly` | week | 5 / week | Yes |
| Monthly | $9.99 | `audioura.sub.monthly` | month | 10 / month | Yes |
| Annual | $79.99 | `audioura.sub.annual` | year | 10 / month | Yes |
| 5-tour pack (`l3`, unchanged) | $10 | `audioura.pack.l3` | none | 5 (one-time) | No |

All plans include unlimited catalog downloads and translations. Prices are stored in
`plans.price_usd` (migration 060) and come from the live store on the plans screen —
correct a price with one `UPDATE`, no redeploy, no code change.

## Server (`subscribed`)

### 1. Migration `060_auto_renew_subscriptions.sql` (NOT 059 — see note)
Additive, idempotent (`IF NOT EXISTS` / `ON CONFLICT`), `BEGIN/COMMIT`, no `DELETE`/`DROP`.
- Adds `plans.tours_per_week`, `store_product_id`, `sub_period`, `auto_renews`.
- Seeds the four subscription-level rows (`sub_day`, `sub_week`, `sub_month`, `sub_year`)
  with every number as a column (prices, allowances, store ids).
- `auto_renew_subscriptions` — one row per subscription, keyed by the store's
  **original transaction id / purchase token** (UNIQUE). `status` ∈
  `active|grace|billing_retry|expired|revoked|refunded`; `previous_level` is the level to
  drop back to when the subscription ends (D733 §4).
- `subscription_notifications` — a dedupe ledger (UNIQUE `store + notification_uuid`) so an
  event is applied **at most once** (stores re-deliver on any non-2xx; Pub/Sub is
  at-least-once).

> **Migration number.** The ticket text says "additive migration 059", but `059` is already
> taken by LOCAL-806 (`059_stop_pool_fresh_until.sql`) on this base. I used the next free
> number, **060**. No other change.

> **Why a new table, not migration 005's `subscriptions`.** Migration 005 defines a
> `subscriptions` table for the superseded wallet/PPU model (`tier IN ('ppu','unlimited')`,
> credit balances). Its columns and `CHECK` constraints are unrelated to store-driven
> auto-renewal. A separate, purpose-built `auto_renew_subscriptions` keeps both models
> intact and is fully additive — migration 005 is untouched.

### 2. Apple — App Store Server Notifications v2 + App Store Server API verification
- `apple_jws_verifier.py`: extracted **`verify_and_decode_jws(jws, root_ca_pem)`** — the
  chain-pin (Apple Root CA G3) + leaf/intermediate OID + ES256-signature + decode core,
  with no transaction-specific claim checks. `verify_signed_transaction` now **delegates its
  crypto** to it, so the notification path and the purchase path can never diverge. (The 598
  suite — 17 tests — still passes, proving the refactor is behaviour-preserving.)
- `subscription_notifications.py` (new): `parse_apple_notification(body, root_ca_pem,
  expected_bundle_id)` verifies the `signedPayload` **and** its nested
  `signedTransactionInfo` / `signedRenewalInfo` JWS against the pinned root, checks the
  transaction `bundleId`, and maps the `notificationType`/`subtype` to a lifecycle status:
  SUBSCRIBED, DID_RENEW, DID_FAIL_TO_RENEW (grace / billing-retry), GRACE_PERIOD_EXPIRED,
  EXPIRED, REFUND, REVOKE, DID_CHANGE_RENEWAL_STATUS.
- `POST /iap/apple/notifications` (`entitlements_api.py`): a **store→server webhook** (no
  `X-API-Key` gate — its authenticity is the signed JWS). Applies the event idempotently.
  200 on success/duplicate (Apple stops re-delivering); **401** on a forged payload (content
  fault, so Apple surfaces it); 400 on a malformed body; 500 only on a genuine server error
  so Apple retries.
- `POST /subscriptions/verify`: the app reports its own purchase so the level is granted
  immediately (without waiting for the first notification). Apple path verifies the StoreKit 2
  JWS offline with `required_type='Auto-Renewable Subscription'`, reads
  `originalTransactionId` + `expiresDate`, upserts the subscription and sets the device
  level. `X-API-Key` gated (same as `/purchases/verify`).

### 3. Google — RTDN + `subscriptionsv2.get`, behind a flag
- `google_play_verifier.py`: added `GooglePlayApiClient.get_subscription_v2(package, token)`
  (`purchases.subscriptionsv2.get`).
- `subscription_notifications.py`: `parse_google_rtdn(body, api_client, package)` decodes the
  Pub/Sub `message.data`, maps the Google `notificationType` enum to a lifecycle status, and
  reads the authoritative `expiryTime` / `subscriptionState` from `subscriptionsv2.get`.
- `POST /iap/google/rtdn`: **gated behind `GOOGLE_SUBS_ENABLED`** (default off). Until the
  `audioura-play-verify` service account is granted the subscriptions permission (currently
  403 — D733 §3) it returns **503 `google_subs_disabled`** and never attempts a Play call.
  The code and its tests ship now; live is one env flag away once Michael fixes the
  permission.

### 4. Entitlement mapping (D733 §4)
`apply_event(cur, event, user_id_hint)` is idempotent (dedupe by notification uuid), upserts
the subscription row (keyed on the original transaction id), and drives
`device_entitlement`:
- while **entitling** (active / grace / billing-retry) → the device's level is the
  subscription level (`plans.store_product_id` → `plan_id`; `tours_per_month` /
  `tours_per_week` in the DB), and `anniversary_at` = `period_end` so the plans screen shows
  the renewal date;
- on **expiry / revoke / refund** → the device drops back to `previous_level` (captured when
  the subscription first became active — never another subscription level, falls back to
  `l1`).
The existing allowance code (`subscription_levels` / `_me_payload`) then gates exactly as it
does for any level — **no new quota logic**; the subscription simply selects a level.

## App (Flutter, `in_app_purchase`)

### `lib/services/iap_service.dart`
- `enum IapSubscription { day, weekly, monthly, annual }` with the store ids
  (`audioura.sub.*`, matching the StoreKit file and `plans.store_product_id`) and an
  `autoRenews` getter (false for the Day pass). `kSubscriptionStoreIds` + `isSubscriptionProduct`.
- `buySubscription(sub)` uses `buyNonConsumable` (the correct call for a subscription /
  non-renewing subscription), `restoreSubscriptions()` (triggers the store to redeliver), and
  `manageSubscriptionsUrl()` (the platform Manage-Subscriptions deep link).
- `_verifyAndGrant` routes a subscription purchase to **`/subscriptions/verify`** (not
  `/purchases/verify`); `_handlePurchasedOrRestored` treats a subscription like a pack
  (implicit context → always finished on a verified grant). The consumable pack/tour/pass
  paths are unchanged.

### `lib/screens/plans_screen.dart` (NEW file)
A **one-page reveal** screen (separate from the older `plan_screen.dart`, so its tests are
untouched):
1. The **active plan banner** on top for a subscription level
   ("Weekly · renews 5 Nov 2026 · 3 new tours left"), or a gentle prompt when there is no
   active subscription.
2. Two big choices: **"Pass — time-limited"** and **"Tour pack — no time limit"**.
3. Tapping one reveals ITS options in place: a segmented **Day · Week · Month · Year** with
   the price and "N new tours", or the 5-tour pack; then **one Buy button**.
4. The required **auto-renewal terms** (renews unless cancelled ≥ 24 h before period end;
   Terms + Privacy links) show **only** for the auto-renewing options — never for the Day
   pass or the pack.
5. **Restore purchases** + **Manage subscription** links at the bottom.

Prices come from the live store (`priceOverride` test seam) with a fallback; allowance copy
comes from the plan. Only the store ids are in code.

### StoreKit config — `audio_tour_app/ios/Audioura.storekit`
- New `subscriptionGroups[0]` "Audioura" with the three auto-renewables
  (`audioura.sub.weekly` P1W $4.99, `audioura.sub.monthly` P1M $9.99, `audioura.sub.annual`
  P1Y $79.99).
- `audioura.sub.day` ($2.99) added to `nonRenewingSubscriptions`.
- Lets Apple sandbox run on the **iOS simulator** (Xcode StoreKit testing) — no real money,
  no physical phone. JSON validated.

## Tests
- `user-tracking/test_local807_subscriptions.py` — **22 tests**. Builds the ASSN v2
  `signedPayload` (with nested transaction/renewal JWS) from a throwaway test PKI and the
  injected test root — the exact pattern of `test_local598_apple_jws.py` — so the whole
  Apple path runs with no Apple servers. Covers each `notificationType` → status, forged
  root / wrong bundle rejection, Google RTDN with a mock `subscriptionsv2` client, the pure
  type→status maps, and (via a tiny in-memory FakeCursor) `apply_event` idempotency, the
  active-level grant, and the drop-back to the previous level on EXPIRED.
- `user-tracking/test_local807_subscription_routes.py` — **7 tests**. The Flask routes'
  pre-DB branches: Google gate (503 disabled / 503 unconfigured), malformed Apple body (400),
  `/subscriptions/verify` missing-fields / unsupported-store / google-gated / apple-missing-JWS.
- `audio_tour_app/test/plans_screen_local807_test.dart` — **9 widget tests**. The reveal
  flow (nothing shown until a choice is tapped), the segmented options + price + tours line,
  the auto-renew terms present for Week/Month/Year and absent for the Day pass, the pack
  reveal with no renewal terms, the active banner, and the Buy button driving
  `buySubscription` for the selected option.
- `audio_tour_app/test/iap_subscription_products_local807_test.dart` — **4 unit tests** on
  the product mapping.

### Results (this machine)
- `cd user-tracking && python3 -m pytest -q` → **73 passed** (includes the 29 new 807 tests;
  the 598 Apple-JWS suite still 17/17, proving the verifier refactor is non-breaking).
- `python3 -m pytest tests/test_local734_per_store_verify.py tests/test_local699_purchases_mode.py tests/test_local696_google_play.py tests/test_local136_apple_grace_period.py -q`
  → **24 passed** (no regressions in the IAP tests that import the changed modules).
- `flutter test` on the two new 807 files → **13 passed**.
- `flutter test` on the existing IAP/plan suite (`iap_redelivery`, `plan_screen_*`,
  `local734_per_store_platform`, `plan_pack_carryover`, `plan_left_summary`) → **71 passed**
  (no regressions from the `iap_service.dart` changes).
- `flutter analyze` on the new/changed Flutter files → clean (only the pre-existing
  `enableStoreKit2` deprecation, not introduced here).

## Live (not run here)
Apple sandbox on the iOS **simulator** with the StoreKit configuration file, the server in
its own containers (`-p local807`), paid-API cap $0 — needs the simulator + the LOCAL stack
and is **unproven on this machine**. The server endpoints, the verification, the entitlement
mapping, the app wiring and the StoreKit file are proven by the tests above.

## Legal / store copy needed (NOT edited here — `legal/` is out of scope)
The App Store requires, on the purchase screen and in the app's metadata, for each
**auto-renewing** subscription: title, length, price per period, and that it auto-renews
unless cancelled ≥ 24 h before the period ends, with functional links to the Terms of Use
(EULA) and Privacy Policy. The plans screen shows this text and the two links for the
auto-renewing options. **Action for whoever owns `legal/`:** confirm the Terms/Privacy URLs
(`https://audioura.com/terms`, `/privacy`) are the canonical ones and that the four product
titles/prices are mirrored in App Store Connect and the Play Console listing.

## Scope / safety
- Changed only: the migration, the user-api `entitlements_api.py` + the two verifier modules
  + the new `subscription_notifications.py`, the Flutter `iap_service.dart` + the new
  `plans_screen.dart`, the StoreKit file, and the four new test files. **No** edits to
  DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev` / `legal/` /
  SUBSCRIBED_COMMUNICATION_01 / GCLOUD_STORIED_START_HERE / TRAVEL_PROJECTS.
- Additive migration (no DELETE/DROP); the live DB is never written by this work.
- The consumable pack / tour / community-pass purchase paths are unchanged; the Apple-JWS
  verifier refactor is behaviour-preserving (598 suite green).
- Google is behind `GOOGLE_SUBS_ENABLED` (default off) so no unauthorised Play call is ever
  made before the permission is fixed.

## Files changed
- `migration/sql/060_auto_renew_subscriptions.sql` (new)
- `user-tracking/apple_jws_verifier.py` — `verify_and_decode_jws`; `verify_signed_transaction`
  delegates to it.
- `user-tracking/google_play_verifier.py` — `get_subscription_v2`.
- `user-tracking/subscription_notifications.py` (new) — parsing, mapping, idempotent apply.
- `user-tracking/entitlements_api.py` — `GOOGLE_SUBS_ENABLED`; `/iap/apple/notifications`,
  `/iap/google/rtdn`, `/subscriptions/verify`.
- `audio_tour_app/ios/Audioura.storekit` — subscription group + Day pass.
- `audio_tour_app/lib/services/iap_service.dart` — `IapSubscription`, `buySubscription`,
  restore / manage, subscription verify routing.
- `audio_tour_app/lib/screens/plans_screen.dart` (new) — the one-page reveal screen.
- `user-tracking/test_local807_subscriptions.py` (new),
  `user-tracking/test_local807_subscription_routes.py` (new),
  `audio_tour_app/test/plans_screen_local807_test.dart` (new),
  `audio_tour_app/test/iap_subscription_products_local807_test.dart` (new).


## Live test (LOCAL-807B — run on the Mac Mini, 2026-10-29)

The "Live (not run here)" gap above is now closed. The server ran from **this
branch** in its own containers (`-p local807`) against a **throwaway DB** with
migration 060 applied, and a DEBUG app build ran on the **iOS simulator**
(iPhone 17, iOS 26.4) pointed at that container. No live DB was written; no paid
API was called ($0).

### How it was run
- **Server (own stack, throwaway DB):** `docker-compose.local807-proof.yml`
  (`-p local807`) — a dedicated Postgres on host port 55807 and the
  `user-tracking` user-api (built from this worktree) on 50807 **and** 5003.
  The schema is built at init from `docs/local807/sql/`:
  `00_base_schema.sql` (the minimal `plans` + `device_entitlement` + `purchases`
  + allowance tables the subscription routes read, lifted column-for-column from
  migrations 003/012/015/016/022) then `01_migration_060.sql` (a **verbatim copy
  of `migration/sql/060`**). Migration 060 applied cleanly: the four `sub_*`
  plan rows seeded with the right prices/periods/allowances, and the
  `auto_renew_subscriptions` + `subscription_notifications` tables created.
  The dev stack's user-api was briefly stopped to free host port 5003 for the
  run and **restored afterwards** (verified healthy on 5003).
- **App:** `flutter run -t lib/main_plans_proof.dart -d <iPhone-17-sim>
  --dart-define=DEBUG_SERVER_IP=127.0.0.1`. `main_plans_proof.dart` is a tiny
  proof harness (modelled on the existing `main_wallet_proof.dart`) that sets
  `server_mode=local` and launches `PlansScreen` directly — the new reveal
  screen is not yet wired into the app's menus, so a direct-launch harness is
  the only way to drive it live. On the iOS simulator `127.0.0.1` is the Mac
  host, so the app reached the LOCAL-807 container on `:5003`.
- The app **built and ran** on the simulator (`flutter build ios --simulator
  --debug` → `Built Runner.app`), and the plans screen's active-plan banner
  showed **live data from the LOCAL-807 server** ("Weekly · renews 5 Nov 2026 ·
  N new tours left"), proving the whole app→container→DB path end to end.

### Screenshots — `docs/local807/`
1. `01_plans_first_view.png` — first view, no active subscription: the gentle
   "Choose a plan…" prompt and the two choices (Pass / Tour pack).
2. `02_pass_revealed_month.png` — "Pass" revealed: segmented Day·Week·Month·Year,
   Month = "10 new tours a month · $9.99", the **auto-renewal terms**, and the
   Terms of Use / Privacy Policy links.
3. `03_pass_revealed_weekly.png` — Week selected: "5 new tours a week · $4.99",
   auto-renewal terms + links.
4. `04_tour_pack_revealed.png` — "Tour pack" revealed: the one-time 5-tour pack,
   "$10", "nothing renews automatically" — **no renewal terms**.
5. `05_weekly_subscribe_attempt.png` — Weekly "Subscribe — $4.99" tapped (see the
   StoreKit-sheet note below).
6. `06_restore_purchases.png` — "Restore purchases" tapped → "Restoring your
   purchases…" (the app calls `restorePurchases()` on the store).
7. `07_day_pass_no_renewal.png` — the **Day pass**: "3 new tours · $2.99", "The
   Day pass lasts 24 hours and does NOT renew" — **no auto-renewal terms, no
   Terms/Privacy block** (the exact D734 rule: terms only for the auto-renewing
   options).
8. `08_active_plan_weekly_banner.png` — the active-plan banner: "Weekly · renews
   5 Nov 2026 · N new tours left" — the server grant + weekly allowance + display
   name through the real app.

### Server side — subscription row + allowance decrement (`docs/local807/server_proof.py`)
Run inside the proof container, the hook calls the **real** entitlement-mapping
code — `subscription_notifications.apply_event`, the exact post-verification
core `/subscriptions/verify` runs after it checks the Apple JWS — with a crafted
ACTIVE Weekly event. Verified output:
- `auto_renew_subscriptions` row created: `status=active`, `period_end` = +7 days,
  `previous_level=l1`, keyed on the original transaction id;
- the device driven to `level=sub_week`, `anniversary_at` = `period_end`;
- `/entitlements/me` then reports `tours_this_week_left: 5`;
- inserting **one** delivered `tour_requests` row (`source='orchestrator',
  status='completed'` — the exact rows the allowance gate counts; **no real
  generation, $0**) decrements it to **4**.

### Fixes the live run surfaced (and only these)
1. **The scheme never referenced the StoreKit config.** `ios/Audioura.storekit`
   existed but `Runner.xcscheme` had no `StoreKitConfigurationFileReference`, so
   nothing told the simulator to load it. Added it to the Launch and Test
   actions (`identifier = "Audioura.storekit"`).
2. **A Weekly subscriber saw no "N new tours left".** `entitlements_api._allowances_left`
   handled `tours_per_day`/`tours_per_month` but **not `tours_per_week`** (and
   `_PLAN_COLS`/`_get_plan` did not even select it), so the Weekly plan — whose
   allowance is weekly — produced no "tours left" line on the plans banner, the
   exact copy D734 asks for. Added the `tours_per_week` column to the plan read
   and a weekly branch to `_allowances_left` (counts the same
   orchestrator/completed `tour_requests`, scoped to `date_trunc('week')`,
   emitting `tours_this_week_left`). The Flutter `Allowances` model gained
   `toursThisWeekLeft` and the banner now prefers week → month → day.
3. **The subscription-level rows had no display name.** The migration-060 seeds
   set every number but left `display_name` NULL, so the banner read "sub_week"
   instead of "Weekly". Added idempotent `UPDATE`s to migration 060 (Day pass /
   Weekly / Monthly / Annual).
4. **The bottom links overflowed by 17 px** on a 390-pt-wide iPhone (two
   `TextButton`s in a `Row`). Changed to a `Wrap` so the second link falls to a
   new line instead of clipping.

### One honest limitation (tooling, not a code defect)
`flutter run` / `simctl launch` do **not** apply an Xcode scheme's StoreKit
configuration file — that is only loaded by an Xcode Run/Test session. So under
`flutter run` the simulator's StoreKit returns `notFound` for the products and
the **native purchase sheet cannot appear**; the app handles this gracefully
(the red "This plan isn't available on this store yet" snackbar in
`05_weekly_subscribe_attempt.png`). Separately, StoreKit *configuration-file*
testing signs its transactions with Xcode's local test certificate, which does
not chain to the pinned **Apple Root CA G3**, so `/subscriptions/verify` would
reject a simulator JWS by design (`root_not_apple`) — the real server-side JWS
grant is only exercisable on a real device + App Store sandbox. The simulator
therefore proves the **client/StoreKit half** (the whole reveal flow, prices,
the terms-only-for-auto-renewing rule, the Day-pass copy, restore, and the
graceful not-available handling); the **server half** (grant → subscription row
→ level → allowance decrement) is proven independently by `server_proof.py`
above, and the buy→`/subscriptions/verify` wiring by the 13 green widget/unit
tests and the valid `.storekit`.

### Regression check after the fixes
- `cd user-tracking && python3 -m pytest -q` → **73 passed** (incl. the 598
  Apple-JWS suite — the verifier is untouched by these fixes).
- `flutter test` on the 807 + IAP + plan suites → **88 passed**.
- `flutter analyze` on the changed Dart files → clean (only the pre-existing
  `enableStoreKit2` deprecation).
