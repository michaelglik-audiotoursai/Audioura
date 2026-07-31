##### READY FOR REVIEW

# SUBMISSION_LOCAL-68 — Wallet API Endpoints

**Branch:** `kiro/local68-wallet-api`
**Commit:** `8f95d78` (fix: rebase + D16 vocabulary reconciliation)
**Parent:** `09c65fc` (original wallet API implementation)
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

### Test suite: 53/53 passed

```
============================================================
LOCAL-68: Wallet API — Contract Test Suite
============================================================
Results: 53/53 passed, 0 failed
ALL TESTS PASSED ✓
============================================================
```

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
