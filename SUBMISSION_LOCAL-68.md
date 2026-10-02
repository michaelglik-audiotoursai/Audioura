##### READY FOR REVIEW

# SUBMISSION_LOCAL-68 — Wallet API Endpoints

**Branch:** `kiro/local68-wallet-api`
**Commit:** `da31268` (fix: complete D16 rename in test_wallet_ledger.py)
**Parent:** `8f95d78` (rebase + D16 vocabulary reconciliation)
**Base:** `origin/subscribed` (includes LOCAL-67 entitlement gate)

---

## Summary of changes

### Commit 1 (`09c65fc`): Wallet API endpoints
- `wallet_api.py` — Flask Blueprint implementing the LOCAL-62 contract
- `wallet_ledger.py` — Append-only ledger, idempotent writes, cost-stop
- `pricing.py` — Cost × multiplier with Decimal + banker's rounding
- `Dockerfile.orchestrator` — COPY lines for all modules
- `tests/test_wallet_api.py` — 53-test live contract verification suite
- `SUBMISSION_LOCAL-68.md` — this file

### Commit 2 (`8f95d78`): LEAD bounce fixes
- **Dockerfile.orchestrator conflict** resolved: merged LOCAL-67's
  `cost_ceiling_monitor.py` alongside LOCAL-68's wallet files.
- **D16 vocabulary reconciliation**: `pay_per_use` → `ppu` in
  `wallet_api.py` (4 occurrences), `wallet_ledger.py` (2 occurrences),
  `tests/test_wallet_api.py` (9 occurrences).
- **Guard test** `test_plan_matches_users_table` added: asserts the API's
  `plan` value is a valid `plans.plan_id` for all three tiers.
- **D16 recorded** in `DECISIONS.md`.

### Commit 3 (this): Complete D16 rename in LOCAL-66's test file
- **`tests/test_wallet_ledger.py`**: 2 remaining `"pay_per_use"` → `"ppu"`
  at lines 103 and 171 (monthly_fee call sites).
- **Root cause**: D16 rename in commit 2 touched production code but missed
  LOCAL-66's test file which still passed the old string. `monthly_fee()`
  correctly returns `None` for unknown tiers (fail-closed, D14), causing
  AC1 to fail with `row4 is None`.
- **Cross-suite verification**: all 5 related suites re-run and passing.

---

## Per-file changes

| File | Lines | What |
|------|-------|------|
| `wallet_api.py` | 341 | Blueprint: GET /wallet, GET /transactions, GET /plans, POST /topup |
| `wallet_ledger.py` | 601 | Ledger, balance, cost-stop, low-balance, idempotency |
| `pricing.py` | 157 | Cost → charge computation (from LOCAL-65) |
| `Dockerfile.orchestrator` | 14 | All COPY lines for LOCAL-67 + LOCAL-68 |
| `tests/test_wallet_api.py` | ~530 | 53 live contract tests |
| `DECISIONS.md` | +28 | D16 added |
| `SUBMISSION_LOCAL-68.md` | this | — |

---

## Hosting decision

**Hosted on the tour_orchestrator (port 5002)** because:
1. The Flutter app already routes wallet calls to `Service.orchestrator`
2. The orchestrator is in docker-compose and has DB access
3. No new service created (per task requirement 6)
4. `user-api-2` is an alternative but would require adding psycopg2 and
   wallet dependencies to a service that currently handles only auth

---

## Live evidence

### Test suites — full cross-suite verification

#### tests/test_wallet_api.py: 53/53 passed

```
============================================================
LOCAL-68: Wallet API — Contract Test Suite
============================================================
Results: 53/53 passed, 0 failed
ALL TESTS PASSED ✓
============================================================
```

#### tests/test_wallet_ledger.py: 8/8 passed

```
============================================================
LOCAL-66: Wallet Ledger & Balance — Test Suite
============================================================
AC1 PASS ✓  (Ledger + Derived Balance)
AC2 PASS ✓  (Rebuild Test — 1000 movements)
AC3 PASS ✓  (Clawback Negative Balance)
AC4 PASS ✓  (Idempotency)
AC5 PASS ✓  (Zero-Balance Stop)
AC6 PASS ✓  (Unlimited Cost-Stop)
Cents Conversion PASS ✓
Low Balance Reminder PASS ✓

RESULTS: 8 passed, 0 failed, 8 total
============================================================
```

#### tests/test_local67_entitlement_gate.py: 23/23 passed

```
======================================================================
LOCAL-67: Entitlement Gate Enforcement — Test Suite
======================================================================
RESULTS: 23/23 passed, 0 failed
======================================================================
```

#### test_pricing.py: 30/30 passed

```
test_pricing.py — 30 passed in 0.08s
```

#### tests/test_local60_cost_metering.py: all passed

```
PASS: test_cost_rates
PASS: test_cost_meter_valid_types
PASS: test_cost_meter_rejects_invalid_type
PASS: test_cost_meter_cache_hit_forces_zero
PASS: test_cost_meter_fresh_generation_records_real_cost
PASS: test_last_generation_cost_cache_hit
PASS: test_migration_sql_valid
PASS: test_cost_meter_no_db_returns_none

=== ALL TESTS PASSED ===
```

### `pay_per_use` grep — remaining occurrences

```
$ grep -r "pay_per_use" --include="*.py" .
(zero results)

$ grep -r "pay_per_use" tests/
(zero results)
```

All Python code and all test files: **0 occurrences** of `pay_per_use`.

Remaining in non-Python files (documentation/Flutter only):
- `DECISIONS.md` — D16 explanation text (5 hits, all descriptive)
- `SUBMISSION_LOCAL-68.md` — this file (documenting the change)
- `audio_tour_app/lib/` — Flutter mock (LOCAL-62 domain, flagged for update)
- `audio_tour_app/test/` — Flutter tests (LOCAL-62 domain)
- `migration/sql/006_wallet_ledger.sql` — SQL comment (not a value)

### GET /wallet — Free user

```json
{
    "balance_usd": 0.0,
    "cost_stop_progress": null,
    "low_balance": false,
    "period_end": "2026-08-01T00:00:00+00:00",
    "period_spend_usd": 0.0,
    "period_start": "2026-07-01T00:00:00+00:00",
    "plan": "free"
}
```

### GET /wallet — PPU user ($9.65 balance, $0.35 spent)

```json
{
    "balance_usd": 9.65,
    "cost_stop_progress": null,
    "low_balance": false,
    "period_end": "2026-08-01T00:00:00+00:00",
    "period_spend_usd": 0.35,
    "period_start": "2026-07-01T00:00:00+00:00",
    "plan": "ppu"
}
```

### GET /wallet — Unlimited user ($18.75 of $25.00 cost-stop used)

```json
{
    "balance_usd": 0.0,
    "cost_stop_progress": {
        "limit_usd": 25.0,
        "used_usd": 18.75
    },
    "low_balance": false,
    "period_end": "2026-08-01T00:00:00+00:00",
    "period_spend_usd": 0.0,
    "period_start": "2026-07-01T00:00:00+00:00",
    "plan": "unlimited"
}
```

### GET /wallet/transactions — cache-hit visible

```json
[
    {
        "cache_hit": false,
        "charged_usd": -10.0,
        "created_at": "2026-07-31T19:42:10.457993+00:00",
        "description": "Credit top-up: $10.00",
        "id": "b8ce6c02-5526-44f8-a771-ebf8f2541dee",
        "operation_type": "topup"
    },
    {
        "cache_hit": false,
        "charged_usd": 0.35,
        "created_at": "2026-07-31T19:42:10.457993+00:00",
        "description": "Tour: French Riviera biking",
        "id": "7d334928-f998-4990-a6d2-a351c7802adb",
        "operation_type": "charge"
    },
    {
        "cache_hit": true,
        "charged_usd": 0.0,
        "created_at": "2026-07-31T19:42:10.457993+00:00",
        "description": "Tour: French Riviera biking (cached)",
        "id": "63fe02b7-4750-49d6-9297-23b3f05e9375",
        "operation_type": "charge"
    }
]
```

### GET /plans/available

```json
[
    {"plan_id": "free", "display_name": "Free", "price_usd": 0.0, "period": "forever", "features": ["Browse pre-made tours", "Limited tour downloads"]},
    {"plan_id": "ppu", "display_name": "Pay-Per-Use", "price_usd": 2.0, "period": "month", "features": ["Unlimited tour generation", "Unlimited news articles", "Pay only for what you use", "Credits never expire"]},
    {"plan_id": "unlimited", "display_name": "Unlimited", "price_usd": 50.0, "period": "month", "features": ["Unlimited tour generation", "Unlimited news articles", "No per-use charges", "Priority processing", "All future features included"]}
]
```

### POST /topup — idempotency proven

```
First call:  {"status": "success", "new_balance_usd": 19.65}
Second call: {"status": "success", "new_balance_usd": 19.65}
```

Same `product_id` ("idem_test_receipt_001") called twice → balance credited once.

### D16 vocabulary guard — all assertions pass

```
  ✓ d16_free_plan_in_db
  ✓ d16_free_plan_matches_tier
  ✓ d16_ppu_plan_in_db
  ✓ d16_ppu_plan_matches_tier
  ✓ d16_unlimited_plan_in_db
  ✓ d16_unlimited_plan_matches_tier
```

### Container verification — all modules import

```
entitlements.py imports OK       (LOCAL-67)
cost_ceiling_monitor.py imports OK (LOCAL-67)
wallet_api.py imports OK         (LOCAL-68)
wallet_ledger.py imports OK      (LOCAL-66/68)
pricing.py imports OK            (LOCAL-65/68)
```

---

## Contract compliance checklist

| Requirement | Status |
|-------------|--------|
| Field names match LOCAL-62 mock exactly | ✓ Verified by contract_field_names test |
| `description` human-readable | ✓ "Tour: French Riviera biking" |
| Cache hits: `charged_usd: 0.00`, `cache_hit: true` | ✓ Proven in transactions |
| `cost_stop_progress` null for free/ppu, populated for unlimited | ✓ All three tiers verified |
| Prices from config, not hardcoded | ✓ `os.environ.get()` with defaults |
| `/topup` idempotent | ✓ Same key credits once |
| No new service created | ✓ Hosted on orchestrator (5002) |
| `ppu` canonical (D16) | ✓ Guard test asserts API plan ∈ plans.plan_id |

---

## ⚠️ CONTRACT CHANGE from original mock

The LOCAL-62 Flutter mock used `"pay_per_use"` as the plan identifier.
Per D16 (LEAD decision), the canonical value is now `"ppu"`. The Flutter
`wallet_screen.dart` must be updated to check for `"ppu"` instead of
`"pay_per_use"`. This is a deliberate, documented change — flagged here
per the task instruction to "say so loudly."

---

## DB changes

No schema changes. The `wallet_ledger`, `wallet_balance_cache`, and
`wallet_subscription` tables are created by `_ensure_tables()` on first use
(idempotent CREATE IF NOT EXISTS). Migration
`006_wallet_ledger.sql` is the production path.

The `wallet_subscription.tier` column now stores `'ppu'` (not `'pay_per_use'`),
consistent with `plans.plan_id` and `subscriptions.tier CHECK` constraint.
