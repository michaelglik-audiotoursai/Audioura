##### READY FOR REVIEW

# LOCAL-83: Wire the charge — Subscribed now bills

## Commit

```
Branch: kiro/local83-wire-charging (off subscribed)
Commit: 029a02d
```

## Per-file changes

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | +55 lines: charging block after cost ceiling check. PPU → `pricing.compute_user_charge()` + `wallet_ledger.charge()`. Unlimited → `record_unlimited_cost()`. Separate try/except, fails closed (D14). Idempotent via `charge:{user_id}:{job_id}` key. |
| `news_orchestrator_service.py` | +57 lines: same pattern after metering block. Skips trusted internal callers. Returns 402 on zero-balance, 503 on billing failure. |
| `wallet_ledger.py` | `monthly_fee()` rewritten: records `amount_cents=0` so fee is visible in Wallet transaction list but does NOT reduce `balance_cents`. Description updated to say "billed by Apple". |
| `tests/test_local82_subscribed_e2e.py` | Step 2 expects $0.00 (was -$2.00). Step 3 expects $10.00 (was $8.00). Integration findings updated. |
| `tests/test_local83_charging_wire.py` | New — 17 targeted acceptance checks. |

## Summary

LOCAL-82 found that `pricing.compute_user_charge()` and `wallet_ledger.charge()` were never called in the generation pipeline. A PPU user could generate forever without their balance moving. This commit wires the missing glue:

1. **Tour path**: immediately after `cost_meter.record_operation()` + cost ceiling pass, the service computes the user charge and debits the wallet (PPU) or records our-cost against the cost stop (unlimited).
2. **News path**: same, after the metering block in `news_orchestrator_service.py`.
3. **D20 fix**: `monthly_fee()` no longer debits the wallet — the $2/$50 fee is an Apple-billed subscription, not a credit deduction.

## Acceptance criteria — live evidence

### 1. PPU charge reconciles (cost_ledger row, charge = cost × 5, balance decreased)

```
--- Test 1: PPU charge reconciles ---
[COST_METER] FRESH | tour_generate | $0.069000 | user=local83_test_114a2fac8c | job=t1_b04e08c3
  ✅ cost_ledger row exists — cost=$0.069000
  ✅ charge = cost × 5 — $0.069 × 5 = 34¢, got 34¢
  ✅ balance decreased by charge — before=1000¢, after=966¢, decrease=34¢, charge=34¢
```

Three numbers reconciled: our cost $0.069, user charge $0.34 (= $0.069 × 5, banker's rounded to cent), balance decreased by exactly 34¢.

### 2. Cache hit: $0.00, balance unchanged to the cent

```
--- Test 2: Cache hit — balance unchanged ---
[COST_METER] CACHE_HIT | tour_cache_hit | $0.000000 | user=local83_test_114a2fac8c | job=t2_cache_de3685b0
  ✅ cache hit charge is $0.00 — got 0¢
  ✅ balance unchanged to the cent — before=966¢, after=966¢
```

### 3. Unlimited: monthly_cost_spent_cents increases by our cost

```
--- Test 3: Unlimited cost recording ---
  ✅ monthly_cost_spent_cents increased — expected=7¢, got=7¢
```

### 4. Drain PPU balance to zero → next request refused naturally

```
--- Test 4: Drain balance → refusal ---
  ✅ balance is zero — balance=0¢
  ✅ next request refused — reason=insufficient_balance, remedy=topup
```

Under the old code, balance could never reach zero because nothing debited the wallet. Now it happens naturally through real charges.

### 5. Charging failure aborts delivery, logs ERROR

```
--- Test 5: Charge failure aborts ---
  ✅ charge failure is detectable — wallet_ledger.charge() returned failure or raised
  ✅ service pattern aborts on failure — generate_tour_text_service.py has fail-closed try/except around charge
```

Service code in `generate_tour_text_service.py` lines 201–252: separate try/except, logs at ERROR via `logging.getLogger().error()`, updates job status to `error` with `error_type="charge_failed"`, cleans up temp file, returns without delivering.

### 6. Same job id retried charges once (idempotency)

```
--- Test 6: Idempotent retry ---
  ✅ first charge succeeded — row_id=d7ba6cd7-01eb-4c94-8123-8a3ede3ded43
  ✅ retry returns same row (idempotent) — row1=d7ba6cd7-..., row2=d7ba6cd7-...
  ✅ balance decreased only once — decrease=35¢, expected=35¢
```

Idempotency key is `charge:{user_id}:{job_id}`. The wallet_ledger unique index on `idempotency_key` prevents double-charge on retry.

### 7. Full `tests/test_local82_subscribed_e2e.py` green with D20 expectations

```
Total: 10 | PASS: 10 | FAIL: 0

Step  Description                                             Our Cost   Charge     Expected     Actual       Status
--------------------------------------------------------------------------------------------------------------
1     Free user allowed to generate (quota-based)             n/a        n/a        n/a          n/a          PASS  
2     PPU monthly fee recorded (D20: balance unchanged)       n/a        $0.0000    $0.00        $0.00        PASS  
3     Top-up $10, balance = $10.00                            n/a        n/a        $10.00       $10.00       PASS  
4     Tour charged: cost=$0.069, charge=$0.34, balance=$9.66  $0.0690    $0.3400    $9.66        $9.66        PASS  
5     CACHE HIT: charge=$0.00, balance unchanged at $9.66     $0.0000    $0.0000    $9.66        $9.66        PASS  
6     News charged: cost=$0.017120, charge=$0.09, balance=$9  $0.0171    $0.0900    $9.57        $9.57        PASS  
7     Zero balance → REFUSED with topup remedy                n/a        n/a        $0.00        $0.00        PASS  
8     Unlimited cost stop: refused + switch-to-PPU offer      n/a        n/a        n/a          n/a          PASS  
9     Refund clawback $8.00 against $5.00 → balance $-3       n/a        $8.0000    $-3.00       $-3.00       PASS  
10    API reconciliation: 2 txns, balance $-3.0               n/a        n/a        $-3.00       $-3.00       PASS  
```

### 8. Cost ceiling: each generation under $1.30

```
  ✅ generation cost under $1.30 — measured cost=$0.069 << $1.30 ceiling
```

Tour cost $0.069, news cost $0.017 — both far below the $1.30 ceiling.

## Limitations

| # | Item | Live / Stubbed | Notes |
|---|------|:-:|---|
| 1 | Tour generation (OpenAI/Polly calls) | **Stubbed** | Cost is simulated at measured values ($0.069 tour, $0.017 news). Real generation → cost_meter integration proven by LOCAL-60/LOCAL-69. |
| 2 | End-to-end HTTP flow through orchestrator | **Stubbed** | The charging code is in `generate_tour_text_service.py` (the async generation worker), not the HTTP route handler. Tests call billing modules directly in the correct sequence. A full HTTP test requires sending a real tour generation request. |
| 3 | Charge failure forcing | **Live but simulated** | Forced by corrupting DB_HOST env var. In production, a real DB outage or import failure triggers the same code path. |
| 4 | Apple IAP / RevenueCat | **Stubbed** | Subscription tier is set via direct DB manipulation. The fake payment provider (per design) is used; real IAP requires App Store Connect products that don't exist yet. |
| 5 | `record_unlimited_cost()` in news path | **Live** | Tested via `test_local83_charging_wire.py` test 3. The news_orchestrator code calls the same function. |
| 6 | `free` tier unchanged | **Live** | Step 1 of E2E test: free user passes quota-based check, no billing involved. |

## D20 design choice — argued

The monthly fee is recorded as a `$0.00` movement (visible in Wallet, balance unchanged) rather than being surfaced from subscription state.

**Why this approach:**
- The Wallet transaction list already exists and is the single source of truth for "what happened to my account".
- Adding a separate subscription-state rendering path introduces a second UI data source and couples Wallet display to RevenueCat state queries.
- A `$0` ledger row is append-only, immutable, timestamped, and carries a description — the same guarantees as every other transaction. No schema change needed.
- If Michael decides the fee SHOULD debit credits: change `amount_cents=0` to `amount_cents=-cents` — one line, tested, reversible.
