##### READY FOR REVIEW

# LOCAL-82: Subscribed End-to-End Integration Test

## Commit

```
Branch: kiro/local82-subscribed-e2e (off subscribed)
Commit: 96c22fc
```

## Per-file changes

| File | Change |
|------|--------|
| `tests/test_local82_subscribed_e2e.py` | New — complete 10-step lifecycle test exercising the full money path against live services |

## Summary

A single script drives one user through the full Subscribed billing lifecycle — free → PPU subscription → tour generation → cache hit → news article → zero-balance refusal → unlimited cost stop → refund clawback → API reconciliation — against running PostgreSQL and orchestrator services. All 10 steps PASS.

## Results table (verbatim from final run)

```
Step  Description                                             Our Cost   Charge     Expected     Actual       Status
--------------------------------------------------------------------------------------------------------------
1     Free user allowed to generate (quota-based)             n/a        n/a        n/a          n/a          PASS  
2     PPU monthly fee debited ($2.00)                         n/a        $2.0000    $-2.00       $-2.00       PASS  
3     Top-up $10, balance = $8.00                             n/a        n/a        $8.00        $8.00        PASS  
4     Tour charged: cost=$0.069, charge=$0.34, balance=$7.66  $0.0690    $0.3400    $7.66        $7.66        PASS  
5     CACHE HIT: charge=$0.00, balance unchanged at $7.66     $0.0000    $0.0000    $7.66        $7.66        PASS  
6     News charged: cost=$0.017120, charge=$0.09, balance=$7  $0.0171    $0.0900    $7.57        $7.57        PASS  
7     Zero balance → REFUSED with topup remedy                n/a        n/a        $0.00        $0.00        PASS  
8     Unlimited cost stop: refused + switch-to-PPU offer      n/a        n/a        n/a          n/a          PASS  
9     Refund clawback $8.00 against $5.00 → balance $-3       n/a        $8.0000    $-3.00       $-3.00       PASS  
10    API reconciliation: 2 txns, balance $-3.0               n/a        n/a        $-3.00       $-3.00       PASS  

Total: 10 | PASS: 10 | FAIL: 0
```

## Key acceptance criteria verification

| Criterion | Evidence |
|-----------|----------|
| Step-by-step table with PASS/FAIL | See above — all rows PASS |
| Balance from ledger reconciles with API at every step | `verify_balance_reconciles()` called at steps 3–7, 9–10 — all match |
| Step 5 shown explicitly (cache hit ≠ charge) | Charge = $0.00, balance unchanged at $7.66 |
| Steps 7 and 8 refuse (not silently allow) | Step 7: `reason=insufficient_balance, remedy=topup`; Step 8: `reason=cost_stop_reached, remedy=switch_to_ppu` |
| Cost ceiling: each generation under $1.30 | Tour: $0.069, News: $0.017 — both ≪ $1.30 |
| Seams reported, not papered over | See Integration Findings below |

## Integration seam finding: CRITICAL

**Wallet charging is NOT wired into the generation pipeline.**

The production flow in `tour_orchestrator_service.py` (line 147 of `generate_tour_text_service.py`) and `news_orchestrator_service.py` (line 215):

1. ✅ `entitlements.check_tour_quota()` gates access (pre-generation)
2. ✅ `cost_meter.record_operation()` records our cost (post-generation)
3. ❌ `pricing.compute_user_charge()` is **never called** post-generation
4. ❌ `wallet_ledger.charge()` is **never called** post-generation

**Impact:** A PPU user passes the entitlement check (has balance > 0), generates a tour, the cost is metered to `cost_ledger`, but no money is ever deducted from their wallet. Their balance never decreases from normal use. The entitlement gate only blocks at `balance == 0`, which can never be reached because nothing debits the wallet.

**Same gap in news:** `news_orchestrator_service.py` (line 215-260) meters cost but never calls `pricing` or `wallet_ledger`.

**Similarly for unlimited tier:** `wallet_ledger.record_unlimited_cost()` is never called post-generation, so `monthly_cost_spent_cents` never increments from actual usage, meaning the $25 cost stop can never naturally trigger.

Each component was verified in isolation (LOCAL-60 through LOCAL-69) and works correctly by itself. The integration glue that chains them together was never built. This test proves the components compose correctly when called in sequence.

## What was tested live vs. stubbed

| Component | Live / Stubbed | Notes |
|-----------|---------------|-------|
| PostgreSQL database | **LIVE** | `development-postgres-2-1` on port 5433 |
| `cost_meter.record_operation()` | **LIVE** | Writes to real `cost_ledger` table |
| `pricing.compute_user_charge()` | **LIVE** | Pure computation, no IO |
| `wallet_ledger.*` (all functions) | **LIVE** | Real wallet writes/reads against DB |
| `entitlements.check_tour_quota()` | **LIVE** | Reads real DB tables (users, plans, subscriptions, wallet) |
| `entitlements.check_news_quota()` | Not directly tested (same code path as tour for paid tiers) |
| `wallet_api` HTTP endpoints (GET /wallet, /transactions) | **LIVE** | Against running orchestrator on port 5002 |
| Tour generation itself (OpenAI calls) | **STUBBED** | Cost metering simulated with measured value ($0.069) |
| News generation itself (Polly/LLM) | **STUBBED** | Cost metering simulated with calculated value ($0.017) |
| Subscription provider (RevenueCat) | **STUBBED** | Tier switch done via direct DB manipulation |

The test does **not** trigger real tour/news generation because that would consume API credits and take 2+ minutes per step. Instead, it simulates what the generation pipeline *would* produce (a cost_ledger entry) and proves the downstream billing chain handles it correctly. This is the correct boundary: the generation → cost_meter integration was already proven by LOCAL-60 and LOCAL-69.

## Limitations

1. **The charging gap cannot be tested end-to-end through HTTP** because the orchestrator never calls `pricing` + `wallet_ledger.charge()`. The test proves the components work by calling them directly in the correct sequence. A follow-up task must wire them into the orchestrator.

2. **No real API spend** — tour/news costs are simulated at measured values, not incurred. The actual `cost_meter` → `cost_ledger` integration with real OpenAI/Polly was proven in LOCAL-60/LOCAL-69.

3. **The `ppu` / `pay_per_use` vocabulary split (D16)** is fully resolved in the code on this branch — `wallet_api.py` returns `plan: "ppu"`, `entitlements.py` dispatches on `"ppu"`, and `plans.plan_id` PK is `"ppu"`. No `pay_per_use` machine identifier was found in production paths.

4. **The entitlement gate for unlimited does not pass `additional_cost_usd`** to `check_unlimited_cost_stop()`. This means it only blocks *after* the $25 limit is exceeded, not *before*. A tour that pushes cost from $24.99 to $25.06 will be allowed. This is arguably correct (block the *next* request, not the one that crossed) but could be tightened.
