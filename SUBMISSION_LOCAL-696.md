# SUBMISSION — LOCAL-696: Verify Google Play purchases on the server (Android twin of the Apple JWS verifier)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-696-play-verify` (from `subscribed`, base `756c66a0`)
**ClickUp:** wdvrdayx32 (Play payments profile), wdvrdayx33 (same product ids as Apple)
**Design:** D658 (server enforces pass length), D660 (every paid download is a purchase)

## Problem
`user-tracking/entitlements_api.py` verified Apple purchases (StoreKit 2 JWS, offline,
`apple_jws_verifier.py`) but the Google path returned `verify_mode_not_implemented`.
Michael now has two Android phones and the Play payments profile is being verified; the
11 phase-1 products will exist on Play with the **same product ids as Apple**:
`audioura.pack.l3`, `audioura.round.l4`, `audioura.tour.tier3`,
`audioura.tour.usd{3,5,10,20,50}`, `audioura.pass.usd{5,10,20}` — all **one-time
products** on Play (passes too; the server enforces pass length, D658).

## What was built

### 1. `user-tracking/google_play_verifier.py` (new) — the Android twin of the Apple verifier
A **pure, dependency-light** module mirroring `apple_jws_verifier.py`:
- `GoogleVerificationError(.code)` — a stable machine code per failure (the twin of
  `JwsVerificationError`), so the HTTP layer and tests branch on the exact reason.
- `VerifiedGooglePurchase` dataclass — `order_id`, `product_id`, `purchase_state`,
  `acknowledged`, `consumed`, `raw`.
- `verify_product_purchase(api_client, product_id, purchase_token, expected_product_id, …)`:
  1. Looks the token up with the **Google Play Developer API** (`purchases.products.get`
     for package `com.audioura.audiotours`).
  2. Checks `purchaseState == 0` (Purchased); **Pending (2)** and **Canceled (1)** never
     grant. Checks the response `productId` matches the path **and** the server-expected
     product (a cheaper token can never be replayed to grant an expensive product).
  3. **Acknowledges** the purchase (Google auto-refunds an unacknowledged purchase within
     3 days) and, for consumables, **consumes** it so the same product can be bought
     again (D660). A token Google already shows acknowledged+consumed verifies without a
     second acknowledge/consume (idempotent at the store layer).
  4. Returns the Google **`orderId`** as the authoritative transaction id.
- The module performs **NO network itself**: the caller injects an `api_client`. The real
  client — `GooglePlayApiClient` (service-account auth, `google-auth`) and
  `build_api_client()` — is at the bottom and imports its Google deps **lazily**, so
  stub/apple-only deployments and the whole test suite need no Google libraries.

### 2. Per-store Google mode wired into the HTTP layer
`entitlements_api.py` and `communities_api.py` gain a `google` branch alongside
`stub`/`apple` (independent per `store` field in `/purchases/verify`):
- **Level** (`verify_purchase`), **tour** (`_verify_tour_signed`) and **community pass**
  (`communities_api._verify_pass_signed`) all route `store=='google'` to the Google
  verifier.
- The device sends `{store:'google', purchase_token, product_id, order_id}`; the endpoint
  normalises those onto the shared pipeline (`order_id→transaction_id`,
  `product_id→product`, `purchase_token→signed_transaction`). The authoritative Google
  `orderId` comes back as `google_verified:<orderId>` and is recorded in
  `purchases.transaction_id` (UNIQUE) — so the same order can **never grant twice**
  (idempotency is the same mechanism as Apple; a replay is a `409 already_verified`).
- **No key yet:** when `GOOGLE_PLAY_SA_JSON` is unset, a Google purchase returns
  **503 `{"error":"google_verify_unconfigured"}`** and NEVER grants. **Stub mode is
  unchanged** for local testing; **iOS/Apple is byte-for-byte unchanged.**

### 3. `user-tracking/google_play_voided_poller.py` (new) — refunds
Apple handles refunds at verify time (a JWS `revocationDate` never grants). Google
surfaces refunds/chargebacks out-of-band via `purchases.voidedpurchases.list`. The poller:
- `reconcile_voided_purchases(cur, voided_items)` — **pure**, local-DB only, reverses each
  grant: **tour** → delete the `tour_unlocks` row; **pass** → expire the
  `community_memberships` row **now** (blocks new content; downloaded audio stays on the
  device, D658); **level** → drop `device_entitlement` back to `l1`. Matched by `orderId`
  then by token. **Idempotent** — the ledger row is marked `raw_status='voided:…'` (audit)
  and never deleted; re-running reverses nothing.
- `run_poller()` / `fetch_voided_items()` page the real feed via `GooglePlayApiClient`; a
  missing SA is a clean no-op. Run from a cron/systemd timer (not a request).

### 4. Android app buy flows (`audio_tour_app/lib/services/iap_service.dart`)
- `kAndroidBillingEnabled = true` (was false). The Plan screen now shows the Android buy
  buttons (the existing `androidHidden` flag flips automatically).
- On Android `_verifyAndGrant` POSTs `{store:'google', product_id, order_id,
  purchase_token}` (the Play Billing `purchaseToken` is
  `verificationData.serverVerificationData`; the order id is `purchaseID`). **iOS is
  unchanged** (`{store:'apple', transaction_id, product, signed_transaction}`).
- `completePurchase()` still runs **only after** the server grants (a failed verify
  completes the transaction so the store stops re-delivering it, but does NOT grant).
  Server-side acknowledge+consume is the source of truth for Google.

## Tests (mock the Google API — no network)
- `user-tracking/test_local696_google_verifier.py` — **17 pure tests**: purchased →
  granted + acknowledged + consumed; pending/canceled → refused; wrong product (response,
  path, and expected) → refused; replayed (already ack+consumed) token → idempotent,
  no double ack/consume; 404 → `token_not_found`, 401 → `google_auth_failed`;
  ack/consume failure → refused; missing token / order id → refused; plus the voided
  reconcile core (tour / membership / level reversal, idempotent, unmatched) on an
  in-memory cursor.
- `tests/test_local696_google_play.py` — **5 DB-backed tests** (skip if no DB): google
  tour purchase grants + is idempotent on the orderId; wrong product → 402; **missing SA
  → 503**; a level purchase grants the level; the voided poller removes the unlock
  against the real DB and is idempotent.

Results:
- `pytest tests -k "677 or 686 or 690 or 693 or 695 or 696"` → **93 passed, 18 skipped,
  0 failed**.
- `cd user-tracking && pytest test_local598_apple_jws.py test_local598b_entitlements_auth.py
  test_local696_google_verifier.py` → **39 passed** (Apple verifier unchanged: 17/17).

## FOR LEAD / MICHAEL — Play Console: create the service account (no key is committed)
The server authenticates to the Google Play Developer API as a **service account** whose
JSON key path is env `GOOGLE_PLAY_SA_JSON`. Do NOT commit the key. Steps:

1. **Google Cloud project** (one-time): in the Play Console, go to
   **Setup → API access**. Either create a new Google Cloud project or link the existing
   Audioura one.
2. **Create the service account:** on the **API access** page, **Create new service
   account** → opens Google Cloud Console → **IAM & Admin → Service Accounts → Create**.
   Name it e.g. `audioura-play-verify`. No Google Cloud IAM role is required for the Play
   API itself.
3. **Create a JSON key:** on that service account → **Keys → Add key → JSON** → download.
   This is the file whose path becomes `GOOGLE_PLAY_SA_JSON` in the user-api container.
   Keep it secret; never commit it.
4. **Grant Play access:** back on **Play Console → Setup → API access**, find the new
   service account under **Service accounts** → **Manage Play permissions** → grant, at
   the account or app (`com.audioura.audiotours`) level:
   - **View financial data, orders, and cancellation survey responses** — required for
     `purchases.products.get` and `purchases.voidedpurchases.list`.
   - **Manage orders and subscriptions** — required to **acknowledge** and **consume**
     purchases.
   Save; permissions can take a few minutes to propagate.
5. **Enable the API:** in Google Cloud Console, enable the **Google Play Android Developer
   API** for the project.
6. **Deploy:** place the JSON key in the user-api container and set
   `GOOGLE_PLAY_SA_JSON=/path/to/key.json` and `IAP_VERIFY_MODE=google` (and optionally
   `GOOGLE_PACKAGE_NAME`, default `com.audioura.audiotours`). Until the key is present,
   Google purchases return 503 `google_verify_unconfigured` and nothing is granted.

LEAD: please turn step 1–5 into a ClickUp task for Michael.

## FOR LEAD — files the user-api image must contain (after merge)
The user-api `Dockerfile` does `COPY . .` from `./user-tracking`, so every new module
ships automatically — **no Dockerfile edit is needed**. For completeness, the image must
contain these new/changed files (all under `user-tracking/`):
- `google_play_verifier.py` (new)
- `google_play_voided_poller.py` (new)
- `entitlements_api.py` (changed — google branch + Android field mapping)
- `communities_api.py` (changed — google pass branch)
- `requirements.txt` (changed — adds `google-auth==2.35.0`, `requests==2.32.3`; the Google
  libs are imported lazily, so this only matters once `IAP_VERIFY_MODE=google` runs a real
  verification).

Deploy env for Google: `IAP_VERIFY_MODE=google`, `GOOGLE_PLAY_SA_JSON=/path/to/key.json`
(+ optional `GOOGLE_PACKAGE_NAME`).

## Scope / safety
- Own containers only; no `-p audioura`, no `audioura-*` rename.
- No DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev` edits.
- No committed key material.
- iOS/Apple and stub paths are unchanged; Google is additive and fail-closed (503 with no
  SA, never a silent grant).
