# SUBMISSION — LOCAL-729: Reimbursement, administrator only

**Branch:** `LOCAL-729-reimbursement` (from `subscribed`, after LOCAL-728 merged)
**Base:** `subscribed` = `0b398c40` (HEAD at branch creation; `git merge-base
--is-ancestor 0b398c40 HEAD` exits 0 — correct base, not `origin/*`).
**code_sha (base):** `0b398c404d28a9626e049c3cdf36487096590572`
**Design:** ClickUp `wdvrdaz3tb` (approved by Michael 2026-10-21); D691/D690/D692/
D688/D660/D613. **Budget:** $0.00 (Google refund MOCKED only; no model/network
calls).

Reimbursement is **administrator only**. Only Audioura (Michael, through LEAD)
reimburses a tour buyer, a community member or a plan purchaser — never an app
user. Every action reuses the LOCAL-728 `admin_actions` ledger (one audit row
per action) and **no purchase-bearing row is ever deleted** (D690): a money
refund revokes by the existing void/flag path and the receipt row stays.

---

## 1. What was built

### Migration (additive only)
`migration/sql/047_reimbursement.sql`
- Widens `admin_actions.action` CHECK to the SUPERSET: the six LOCAL-728
  moderation verbs **plus** `refund_google`, `apple_refund_support`,
  `grant_tour`, `extend_pass`, `grant_pass`, `add_plan_units`, `extend_plan`
  (drop + re-add; the set only GROWS, so no existing row is invalidated).
- Adds nullable columns to `admin_actions`: `amount_usd`, `transaction_id`,
  `store`, `target_tour_id` (money + purchase link for a reimbursement row).
- Creates `support_ids(support_id PK, user_id UNIQUE, created_at)` — the public
  Support ID alias per device.
- Adds `purchases.refund_supported BOOLEAN NOT NULL DEFAULT FALSE` — the Apple
  "we support it" flag.
- `ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / guarded CHECK:
  **idempotent, no DROP, no DELETE, no retype**.

### Server modules
- `user-tracking/support_id.py` — collision-safe `AU-XXXX` generation
  (unambiguous alphabet, no `O I L 0 1`), `ensure_support_id(cur, user_id)`
  (idempotent, one alias per device), `resolve_to_user_id(cur, token)` (a
  Support ID → device id; a raw device id passes through), `is_support_id`.
- `user-tracking/google_play_refund.py` — `refund_order(cur, order_id,
  api_client, partial_usd)`: a FULL refund calls Google Orders refund with
  `revoke=true` then reverses the grant locally via the existing
  `reconcile_voided_purchases`; a `--partial USD` refunds money WITHOUT
  revoking (buyer keeps access). `RefundNotConfigured` when no service account
  (`GOOGLE_PLAY_SA_JSON`) — a clear refusal that grants/refunds nothing.
- `user-tracking/google_play_verifier.py` — added
  `GooglePlayApiClient.refund_order(package_name, order_id, revoke)` (POST
  `.../orders/{orderId}:refund`). Real path only; tests inject a mock.

### Admin CLI — `moderation.py` (extends LOCAL-728)
Each command writes **exactly one** `admin_actions` row. `<device>` accepts a
device id OR a Support ID (`AU-XXXX`).
```
grant-tour <device|support-id> <tour_id> <language> ["reason"]
extend-pass <community_id> <device|support-id> <days> ["reason"]
grant-pass  <device|support-id> <community_id> <length> ["reason"]
add-plan-units <device|support-id> <n> ["reason"]
extend-plan    <device|support-id> <days> ["reason"]
refund-google  <order_id> [--partial USD] ["reason"]
apple-refund-message <device|support-id|order_id> ["reason"]
support-id <device>
ledger [--device D] [--limit 50]
```

### Admin-key HTTP endpoints — `user-tracking/communities_api.py`
All gated by `_require_admin_key` (distinct `ADMIN_API_KEY`, which the app never
carries; 503 when unset, 401 when wrong/gateway-key):
`POST /communities/admin/support-id`, `/communities/admin/grant-tour`,
`/communities/<id>/admin/extend-pass`, `/communities/<id>/admin/grant-pass`,
`/communities/admin/add-plan-units`, `/communities/admin/extend-plan`,
`/communities/admin/refund-google` (503 `refund_not_configured` without SA),
`/communities/admin/apple-refund-message`, `GET /communities/admin/ledger`.

### App-facing Support ID — `user-tracking/entitlements_api.py`
`GET/POST /support-id` (gateway-keyed): the device's own alias only
(`ensure_support_id`). Never reveals the secret id, cannot read another device.

### Flutter About — Support ID + Copy
- `audio_tour_app/lib/widgets/support_id_row.dart` — `SupportIdRow` (keys
  `support_id_value`, `support_id_copy`), `computeLocalSupportId` (deterministic
  offline alias, same alphabet as the server), `isSupportIdShape`.
- `audio_tour_app/lib/screens/about_screen.dart` — a Support ID row after the
  User ID row, showing the deterministic alias immediately and confirming the
  authoritative one from `GET /support-id` (best-effort), with a Copy button.

---

## 2. Migration — row counts before/after (isolated postgres `-p local729`)

Isolated postgres only: `docker-compose.local729.yml`, project `-p local729`,
host port **55433**, tmpfs (ephemeral). Never `-p audioura`, never touched
`audioura-*` or `development-postgres-2-1`.

Migrations 010..046 applied to a fresh DB (033/034 skipped — they depend on
service self-healing tables `recovery_codes` / `device_consolidation_history`, a
pre-existing ordering gap unrelated to 729), then 047:

```
=== ROW COUNTS BEFORE 047 ===        === ROW COUNTS AFTER 047 ===
admin_actions 0                      admin_actions 0
purchases 0                          purchases 0
tour_unlocks 0                       tour_unlocks 0
community_memberships 0              community_memberships 0
device_entitlement 1                 device_entitlement 1
support_ids <none>                   support_ids 0   (new empty table)
```
Every existing table's row count is **identical** before and after
(`device_entitlement` = 1 is the migration-013 seed row). Purely additive.

**Idempotent:** re-applying 047 is a clean no-op (only
`NOTICE ... already exists, skipping`). The widened CHECK accepts `grant_tour`
and rejects a bogus verb (`new row ... violates check constraint
"chk_admin_actions_action"`).

---

## 3. Example CLI run (isolated DB)

```
$ python3 moderation.py support-id USER-demo729
USER-demo729 → Support ID AU-BSXK

$ python3 moderation.py --actor LEAD grant-tour AU-BSXK 15 en "failed download x3"
Granted tour 15 (en) to USER-demo729 (store=admin_grant). Ledger written.

$ python3 moderation.py apple-refund-message USER-demo729 "ios buyer"
── Send this to the customer ──
Hi — thanks for reaching out. Apple handles refunds for in-app purchases, so
please request one at https://reportaproblem.apple.com using the Apple ID that
made the purchase. We've recorded that Audioura supports this refund, so if
Apple asks us we'll confirm it. Sorry for the trouble!
── (marked 0 Apple purchase(s) refund_supported). Ledger written. ──

$ python3 moderation.py ledger --device AU-BSXK
  #33 apple_refund_support actor=moderation.py user=USER-demo729 ... store=apple ...
  #32 grant_tour actor=LEAD user=USER-demo729 ... store=admin_grant tour=15 ...
```
(`DATABASE_URL` pointed at the isolated `audiotours_test` on 55433; demo rows
cleaned up after.)

---

## 4. Tests

### pytest — `tests/test_local729_reimbursement.py`
Command (both env groups required: `get_connection()` reads
`DB_HOST/DB_PORT/DB_NAME`; the CLI + loaded modules read `DATABASE_URL`):
```
DB_HOST=localhost DB_PORT=55433 DB_NAME=audiotours_test \
DATABASE_URL=postgresql://admin:password123@localhost:55433/audiotours_test \
IAP_VERIFY_MODE=stub python3 -m pytest tests/test_local729_reimbursement.py -v
```
Result: **17 passed in 1.13s**. Coverage:
- **Support ID** unique, idempotent, resolves back to the device, never the
  secret id.
- **grant-tour** writes one unconsumed `tour_unlocks` row (store=`admin_grant`)
  → the download gate (`consumed_at IS NULL`) passes once; consuming it closes
  the gate. One ledger row.
- **extend-pass / grant-pass** change `expires_at` only — the membership row and
  its `transaction_id` (the purchase record) survive (D690). One ledger row each.
- **add-plan-units / extend-plan** touch the allowance state only (fresh_used
  floored at 0; anniversary_at pushed out). One ledger row each (D613).
- **refund-google (MOCKED client, no network)**: full refund calls the API with
  `revoke=true`, revokes the local unlock, and KEEPS the purchase row marked
  `voided:` (D690); partial refund does NOT revoke and keeps access; no service
  account → `RefundNotConfigured` / endpoint 503 `refund_not_configured` with NO
  ledger row.
- **apple-refund-message** marks `purchases.refund_supported` and emits the
  customer text; one ledger row.
- **admin-key refusal**: every reimbursement endpoint returns 401 with no key
  and with the gateway key, and 503 when no admin key is configured; nothing
  reaches the ledger.

**RED test** — `test_red_broken_admin_gate_lets_normal_user_grant_a_tour`:
forces `_require_admin_key` to always pass (the hole) and shows a NORMAL user's
gateway-key call to `grant-tour` succeeds (200) and grants the unlock — so the
green "refused with 401" assertion then FAILS (`pytest.raises(AssertionError)`),
proving the guarantee is not vacuous (a normal user could reimburse themselves).

**Regression:** `tests/test_local728_admin_moderation.py` +
`tests/test_local729_reimbursement.py` together = **28 passed**.

### flutter test — `audio_tour_app/test/local729_support_id_test.dart`
```
cd audio_tour_app && flutter test test/local729_support_id_test.dart
```
Result: **8 passed** (deterministic alias; never uses `O I L 0 1`; shape checks;
`SupportIdRow` renders the alias + Copy button; Copy writes the Support ID to the
clipboard and fires `onCopied`; without `onCopied` it shows a confirmation
snackbar). `flutter analyze` on the two changed Dart files: no errors (only
pre-existing warnings/infos).

---

## 5. Safety

- Isolated postgres only (`-p local729`, host port 55433, tmpfs). Never
  `-p audioura`, never touched `audioura-*` or `development-postgres-2-1`.
- Additive migration only; row counts before/after identical; idempotent.
- No real Google refund — the API client is mocked in tests; the real
  `refund_order` is wired but only runs with a service account present.
- No `DELETE FROM audio_tours`; no phones; no model/network calls. **$0.00.**

## 6. Files
Changed: `moderation.py`, `user-tracking/communities_api.py`,
`user-tracking/entitlements_api.py`, `user-tracking/google_play_verifier.py`,
`audio_tour_app/lib/screens/about_screen.dart`.
New: `migration/sql/047_reimbursement.sql`, `user-tracking/support_id.py`,
`user-tracking/google_play_refund.py`, `tests/test_local729_reimbursement.py`,
`audio_tour_app/lib/widgets/support_id_row.dart`,
`audio_tour_app/test/local729_support_id_test.dart`,
`docker-compose.local729.yml`.
