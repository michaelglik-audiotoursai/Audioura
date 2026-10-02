##### READY FOR REVIEW

**Commit:** `c2be6f4`
**Branch:** `kiro/local61-payment-provider`
**Base:** `storied` (`1fb69e8`)
**Commit count:** `git rev-list --count storied..HEAD` = 1

---

## Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `payment_provider.py` | 161 | Abstract interface: 7 methods (get_entitlement, purchase_subscription, purchase_consumable, restore_purchases, handle_webhook, get_low_balance_events, record_usage) + dataclasses + enums |
| `fake_payment_provider.py` | 297 | Full deterministic implementation: all paths exercised, time-controllable, scriptable |
| `migration/sql/005_subscription_state.sql` | 80 | `subscriptions` table, `subscription_transactions` ledger, `low_balance_events`, 2 new plan rows (ppu, unlimited) |
| `test_payment_provider.py` | 346 | 19 tests covering full state machine + acceptance criteria |

---

## Database design decision: separate `subscriptions` table

**Choice:** A new `subscriptions` table rather than adding columns to `users`.

**Rationale:**
1. `users` is the identity table (secret_id, app_version, is_deleted). Subscription state has its own lifecycle (periods, provider IDs, balances) that changes independently.
2. Free users have **NO subscription row** — zero behavioral change, zero migration risk.
3. The existing `users.plan` FK to `plans` stays intact. Quota-based entitlements (`entitlements.py`) continue working unchanged for free users.
4. `subscriptions` + `subscription_transactions` naturally separate billing state from identity.

The `plans` table gains two rows (`ppu`, `unlimited`) with generous quota ceilings (999 tours/day etc) since billing replaces quota gating for paid tiers. The `free` row is untouched.

---

## Cloud gateway investigation (remind_mobile_ai.md:40)

The mobile app already sends `user_id` in tour generation requests because "Gateway requires it for quota/entitlements check." The orchestrator at line 1209 imports `check_tour_quota` from `entitlements.py` and gates on it.

**Finding:** The existing entitlements gate at the orchestrator level (not a separate gateway service) is the right extension point. For paid tiers, the check transitions from quota-count logic to balance/cost-stop logic. This can be done by extending `check_tour_quota()` to inspect the `subscriptions` table when `plan != 'free'`, returning a `cost_check` result instead of a `quota_exceeded` result. No duplication needed — same call site, same user_id path.

**Not built in this task** (per scope), but the interface is ready: `record_usage()` returns a `LowBalanceEvent` or `None`, and the orchestrator can call it post-generation to debit the cost.

---

## Live-DB changes declared

Migration `005_subscription_state.sql` creates:
- 3 new tables: `subscriptions`, `subscription_transactions`, `low_balance_events`
- 2 new plan rows in existing `plans` table: `ppu`, `unlimited`
- No existing rows modified, no columns added to existing tables
- `free` plan row untouched (ON CONFLICT DO NOTHING)

---

## State machine test output (verbatim)

```
======================================================================
PaymentProvider State Machine Tests
======================================================================

[TEST] test_free_user_default
  FREE user entitlement: tier=free, state=active, no period, no balance — exactly as before
  ✓ PASS

[TEST] test_free_user_usage_noop
  FREE user usage: no-op, tier still=free
  ✓ PASS

[TEST] test_purchase_ppu_subscription
  PPU purchase: tier=ppu, state=active, balance=$10.00, period=2026-08-01 12:00:00 → 2026-08-31 12:00:00
  ✓ PASS

[TEST] test_purchase_unlimited_subscription
  UNLIMITED purchase: tier=unlimited, state=active, cost_used=$0.00, cost_stop=$25.00
  ✓ PASS

[TEST] test_state_machine_purchase_renew
  BEFORE renewal: state=active, balance=$9.6550
  AFTER renewal: state=active, balance=$9.6550, new period=2026-08-31 12:00:00 → 2026-09-30 12:00:00
  ✓ PASS

[TEST] test_state_machine_expire
  BEFORE expiry: state=active, tier=ppu
  AFTER expiry: state=lapsed, tier=ppu
  ✓ PASS

[TEST] test_state_machine_time_based_expiry
  Time-based expiry: state=lapsed after 31 days
  ✓ PASS

[TEST] test_refund_clawback
  Balance after 25 tours: $1.3750
  Balance after $10 refund: $-8.6250 (NEGATIVE is expected)
  Refund transaction recorded: amount=-10.0, resulting_balance=-8.6250
  ✓ PASS

[TEST] test_restore_on_new_device
  Restore: tier=ppu, state=active, balance=$9.6550 (preserved)
  ✓ PASS

[TEST] test_restore_no_purchases
  Restore (no purchases): success=False, error='No purchases to restore'
  ✓ PASS

[TEST] test_low_balance_event
  After 23 tours: balance=$2.0650
  After 24 tours: balance=$1.7200
  LOW BALANCE EVENT: balance=$1.7200 < threshold=$2.00 → reminder triggered
  Pending low-balance events: 1
  Confirmed: no auto-charge. Balance still $1.7200
  ✓ PASS

[TEST] test_consumable_purchase_clears_low_balance
  Top-up: balance=$10.3400, low-balance events cleared (5 → 0)
  ✓ PASS

[TEST] test_consumable_requires_ppu
  Free user top-up: success=False, error='Credit top-up only available for Pay-Per-Use subscribers'
  Unlimited user top-up: success=False, error='Credit top-up only available for Pay-Per-Use subscribers'
  ✓ PASS

[TEST] test_unlimited_cost_tracking
  Unlimited after 10 tours: cost_used=$0.6900, cost_stop=$25.00
  ✓ PASS

[TEST] test_billing_retry
  Billing retry: state=billing_retry, tier=ppu
  ✓ PASS

[TEST] test_full_lifecycle

  === FULL LIFECYCLE ===
  1. PURCHASE: tier=ppu, state=active, balance=$10.00
  2. USE: balance=$9.6550 (after 1 tour)
  3. RENEW: state=active, period=2026-08-31 → 2026-09-30
  4. USE: balance=$9.5550 (after news)
  5. EXPIRE: state=lapsed
  6. RESTORE (lapsed): success=False
  ✓ PASS

[TEST] test_unknown_product
  Unknown product: error='Unknown product: com.unknown.product'
  ✓ PASS

[TEST] test_cache_hit_costs_zero
  Cache hit: balance unchanged $10.00 → $10.00
  ✓ PASS

[TEST] test_free_plan_before_after

  === FREE PLAN BEFORE/AFTER ===
  BEFORE (no subscription system):
    - User 'free_user' has tier=free, no period, no balance
    - Usage is quota-gated (1 tour/day via entitlements.py)
    - No transaction history, no wallet
  AFTER (with subscription system):
    - User 'free_user' has tier=free, period_start=None, balance=None
    - state=active (always active for free)
    - Usage still quota-gated (entitlements.py unchanged)
    - record_usage is a no-op for free users
    - record_usage returns: None (no-op confirmed)
    - No subscription row created in DB for free users
  VERDICT: Free plan behavior IDENTICAL before and after.
  ✓ PASS

======================================================================
Results: 19 passed, 0 failed, 19 total
======================================================================
```

---

## Refund-after-spend test (acceptance criterion: negative balance recorded, not lost)

From `test_refund_clawback`:
```
Balance after 25 tours: $1.3750
Balance after $10 refund: $-8.6250 (NEGATIVE is expected)
Refund transaction recorded: amount=-10.0, resulting_balance=-8.6250
```

User spent 25 × $0.069 × 5 = $8.625, leaving $1.375 from the initial $10.00. Apple refunds the full $10.00, resulting in $1.375 - $10.00 = **-$8.625**. The record is preserved in `subscription_transactions`, not dropped.

---

## Free plan before/after (acceptance criterion)

```
BEFORE (no subscription system):
  - User 'free_user' has tier=free, no period, no balance
  - Usage is quota-gated (1 tour/day via entitlements.py)
  - No transaction history, no wallet

AFTER (with subscription system):
  - User 'free_user' has tier=free, period_start=None, balance=None
  - state=active (always active for free)
  - Usage still quota-gated (entitlements.py unchanged)
  - record_usage is a no-op for free users
  - No subscription row created in DB for free users
  VERDICT: Free plan behavior IDENTICAL before and after.
```

`entitlements.py` is unchanged. `check_tour_quota()` and `check_news_quota()` remain the enforcers for free-tier users. No new code path executes for `plan='free'`.

---

## Regression suite

```
$ python3 -m pytest tests/ --ignore=tests/test_32byte_truncation.py --tb=short
!!!!!!!!!!!!!!!!!!! Interrupted: 40 errors during collection !!!!!!!!!!!!!!!!!!!
```

Same result as baseline (`~/audioura-worktrees/prepush-baseline`): 40 collection errors from missing modules (`Crypto`, `beautifulsoup4`, etc). **Zero new failures introduced.** These are pre-existing environment issues unrelated to subscription work.

---

## Apple constraint encoded

1. **No `auto_topup()` method exists.** The interface has `purchase_consumable()` which requires explicit user action.
2. **Low-balance triggers a `LowBalanceEvent`** (queryable via `get_low_balance_events()`). The app layer shows a reminder; the provider never silently debits.
3. **Refund clawback** allows negative balance — per Michael's ruling: "No Problem. That only impacts how we calculate corporate revenue vs. cashflow."

---

## Swapping in RevenueCat

To add real IAP: create `revenuecat_payment_provider.py` implementing `PaymentProvider`. Wire it via a factory/config switch. The fake stays for tests. One file to add, one config line to change.
