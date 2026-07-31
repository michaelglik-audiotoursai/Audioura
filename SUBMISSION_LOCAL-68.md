##### READY FOR REVIEW

**Branch:** `kiro/local68-wallet-api`
**Commit:** `7792427`
**Date:** 2026-07-31T15:30 EDT

---

## Commit

```
7792427 LOCAL-68: Wallet API endpoints — contract from LOCAL-62, backed by LOCAL-65/66
```

`git rev-list --count storied..HEAD` = 14 (includes merge of `subscribed` with LOCAL-65/66).

---

## Per-file changes

| File | Change |
|------|--------|
| `wallet_api.py` | **NEW** — Flask Blueprint with 4 endpoints matching the LOCAL-62 contract exactly. Reads from wallet_ledger (LOCAL-66) and pricing (LOCAL-65). Plans from env config. |
| `tour_orchestrator_service.py` | **MODIFIED** — Registers `wallet_bp` Blueprint, adds CORS OPTIONS for wallet routes. 10 lines added. |
| `Dockerfile.orchestrator` | **MODIFIED** — COPY wallet_api.py, wallet_ledger.py, pricing.py, cost_meter.py, cost_rates.py into image. |
| `tests/test_wallet_api.py` | **NEW** — 47-assertion integration test suite against live orchestrator + PostgreSQL. |

---

## Hosting decision

**Wallet endpoints live on the tour orchestrator (port 5002)** because:
1. The Flutter app already routes wallet calls to `Service.orchestrator` (5002) — see `wallet_service.dart:146-175`.
2. The orchestrator is already in docker-compose, talks to PostgreSQL, and has CORS.
3. No new service created (per requirement #6).
4. user-api-2 (5003) was an alternative, but it has its own docker-compose, its own Dockerfile, and the Flutter app doesn't route wallet traffic there.

---

## Evidence: GET /wallet/<user_id> — free user

```
$ curl -s http://localhost:5002/wallet/demo_free | python3 -m json.tool
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

✓ `cost_stop_progress: null` for free (requirement #3).
✓ `low_balance: false` for free.

---

## Evidence: GET /wallet/<user_id> — pay_per_use user

```
$ curl -s http://localhost:5002/wallet/demo_ppu | python3 -m json.tool
{
    "balance_usd": 9.2,
    "cost_stop_progress": null,
    "low_balance": false,
    "period_end": "2026-08-01T00:00:00+00:00",
    "period_spend_usd": 0.8,
    "period_start": "2026-07-01T00:00:00+00:00",
    "plan": "pay_per_use"
}
```

✓ `cost_stop_progress: null` for ppu (requirement #3).
✓ Balance reflects top-up minus charges.

---

## Evidence: GET /wallet/<user_id> — unlimited user

```
$ curl -s http://localhost:5002/wallet/demo_unlimited | python3 -m json.tool
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

✓ `cost_stop_progress` populated with used_usd/limit_usd (requirement #3).
✓ Limit is $25.00 = 0.5 × $50 (from config `UNLIMITED_COST_STOP_FRACTION`).

---

## Evidence: GET /wallet/<user_id>/transactions — cache hit visible

```
$ curl -s "http://localhost:5002/wallet/demo_ppu/transactions?limit=50" | python3 -m json.tool
[
    {
        "cache_hit": false,
        "charged_usd": -10.0,
        "created_at": "2026-07-31T19:20:13.206225+00:00",
        "description": "Credit top-up: $10.00",
        "id": "b6852825-63e5-440d-99fe-f5a1d3473556",
        "operation_type": "topup"
    },
    {
        "cache_hit": false,
        "charged_usd": 0.35,
        "created_at": "2026-07-31T19:20:13.206225+00:00",
        "description": "Tour: French Riviera biking",
        "id": "8cec65e4-0c5d-45e7-983e-1592355e5db1",
        "operation_type": "charge"
    },
    {
        "cache_hit": true,
        "charged_usd": 0.0,
        "created_at": "2026-07-31T19:20:13.206225+00:00",
        "description": "Tour: Paris walking (cached)",
        "id": "88711dc7-3b35-4544-90e3-5f059219ece4",
        "operation_type": "charge"
    },
    {
        "cache_hit": false,
        "charged_usd": 0.45,
        "created_at": "2026-07-31T19:20:13.206225+00:00",
        "description": "Tour: Historic Boston walking",
        "id": "a0cc72b5-b01e-48ab-8a62-fdc3127797fd",
        "operation_type": "charge"
    }
]
```

✓ `cache_hit: true` with `charged_usd: 0.0` visible (requirement #2).
✓ `description` is human-readable: "Tour: French Riviera biking" (requirement #1).
✓ Field names match contract exactly: id, created_at, operation_type, description, charged_usd, cache_hit.

---

## Evidence: GET /plans/available

```
$ curl -s http://localhost:5002/plans/available | python3 -m json.tool
[
    {
        "display_name": "Free",
        "features": ["Browse pre-made tours", "Limited tour downloads"],
        "period": "forever",
        "plan_id": "free",
        "price_usd": 0.0
    },
    {
        "display_name": "Pay-Per-Use",
        "features": ["Unlimited tour generation", "Unlimited news articles",
                     "Pay only for what you use", "Credits never expire"],
        "period": "month",
        "plan_id": "pay_per_use",
        "price_usd": 2.0
    },
    {
        "display_name": "Unlimited",
        "features": ["Unlimited tour generation", "Unlimited news articles",
                     "No per-use charges", "Priority processing",
                     "All future features included"],
        "period": "month",
        "plan_id": "unlimited",
        "price_usd": 50.0
    }
]
```

✓ Prices from config (PPU_MONTHLY_FEE_USD, UNLIMITED_MONTHLY_FEE_USD), not hardcoded (requirement #4).
✓ Field names: plan_id, display_name, price_usd, period, features.

---

## Evidence: POST /wallet/<user_id>/topup — idempotent

```
$ curl -s -X POST http://localhost:5002/wallet/demo_ppu/topup \
    -H "Content-Type: application/json" \
    -d '{"product_id": "receipt_idem_test_001"}'
{"new_balance_usd": 19.2, "status": "success"}

$ curl -s -X POST http://localhost:5002/wallet/demo_ppu/topup \
    -H "Content-Type: application/json" \
    -d '{"product_id": "receipt_idem_test_001"}'
{"new_balance_usd": 19.2, "status": "success"}
```

✓ Same product_id twice → same balance (19.2, not 29.2). Credited once (requirement #5).
✓ Idempotency mechanism: wallet_ledger's UNIQUE index on `idempotency_key` (LOCAL-66).

---

## Evidence: Regression

```
$ curl -s http://localhost:5002/health
{"service": "tour_orchestrator", "status": "healthy"}

$ curl -s http://localhost:5002/jobs
{"jobs": []}

Pricing tests (LOCAL-65):  30/30 passed
Wallet ledger tests (LOCAL-66): 8/8 passed
Wallet API tests (LOCAL-68): 47/47 passed
```

All existing orchestrator endpoints operational. No breaking changes.

---

## DB changes

**None.** All tables used (`wallet_ledger`, `wallet_balance_cache`, `wallet_subscription`, `cost_ledger`) were created by LOCAL-66's migration (006_wallet_ledger.sql) and LOCAL-60's migration (005_cost_ledger.sql). The `_ensure_tables()` pattern in wallet_ledger.py creates them idempotently at runtime if migrations haven't run.
