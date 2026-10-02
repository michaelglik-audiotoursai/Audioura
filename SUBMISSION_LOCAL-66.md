##### READY FOR REVIEW

**Branch:** `kiro/local66-wallet-ledger`
**Commit:** `9958154`
**Date:** 2026-07-31T14:55 EDT

---

## Commit

```
9958154 LOCAL-66: Wallet ledger and balance — append-only user billing, idempotent writes, cost-stop
```

`git rev-list --count storied..HEAD` = 1.

---

## Per-file changes

| File | Change |
|------|--------|
| `wallet_ledger.py` | **NEW** — Core module. Append-only ledger, derived balance with cache, idempotent writes via unique key, zero-balance stop (D3), unlimited cost-stop with switch offer (D4), low-balance reminder, transaction history API. Money as integer cents (never float). |
| `migration/sql/006_wallet_ledger.sql` | **NEW** — DDL for `wallet_ledger`, `wallet_balance_cache`, `wallet_subscription` tables with indexes and comments. |
| `tests/test_wallet_ledger.py` | **NEW** — Full acceptance test suite (8 tests covering all 6 ACs). |

---

## Evidence: AC1 — Ledger + derived balance

```
Step   Operation                     Amount    Balance
-------------------------------------------------------
1      Top-up $10.00                +$10.00     $10.00
2      Charge: Nice walking          -$0.35      $9.65
3      Charge: Riviera biking        -$0.75      $8.90
4      Monthly fee (PPU)             -$2.00      $6.90
5      Top-up $10.00                +$10.00     $16.90
6      Charge: Paris museum          -$1.20     $15.70

Derived balance from ledger: $15.70
Cached balance:             $15.70
AC1 PASS ✓
```

---

## Evidence: AC2 — Rebuild test (1000 mixed movements)

```
Operations: 1000 mixed (topups, charges, fees)
Cached balance:  356788¢ ($3567.88)
Rebuilt balance: 356788¢ ($3567.88)
Match: True
AC2 PASS ✓
```

---

## Evidence: AC3 — Clawback-after-spend (negative balance)

```
After top-up $10:       1000¢
After charge $8:         200¢
After clawback $10:     -800¢
Row recorded: ec09bbc2-7e19-4add-92e2-19b28d3e43c9
Rebuilt from ledger:    -800¢
Nothing lost: ledger has 3 rows
AC3 PASS ✓
```

---

## Evidence: AC4 — Idempotency

```
Key: idem-duplicate-test-3839d0c5
Attempt 1: row=5e017da8-43d0-42a8-819a-0f6d774be6d5, balance=1000¢
Attempt 2: row=5e017da8-43d0-42a8-819a-0f6d774be6d5, balance=1000¢
Same row returned: True
Ledger rows: 1
Balance unchanged: True
AC4 PASS ✓
```

---

## Evidence: AC5 — Zero-balance stop (no debt from ordinary consumption)

```
After top-up $1.00:    100¢
After charge $1.00:      0¢ (charge succeeded, spent all)
Charge $0.35 blocked: stop=True, balance=0¢
After clawback $5.00: -500¢ (negative OK)
Charge $0.10 blocked: stop=True, balance=-500¢
No debt from normal use: confirmed
AC5 PASS ✓
```

---

## Evidence: AC6 — Unlimited cost-stop breach (message + switch offer)

```
Cost stop: $25.00
After $20.00 cost:  breached=False
After $24.99 cost:  breached=False
After $25.01 cost:  breached=True
Message: Your Unlimited plan has reached its monthly usage limit. We've spent $25.01 of the $25.00 monthly allowance on your behalf. You can switch to Pay-Per-Use for the rest of this month to continue generating new content, or wait for your plan to reset at the start of your next billing period.
AC6 PASS ✓
```

---

## Regression suite

```
LOCAL-66 test suite:         8 passed, 0 failed
Shared (test_f4_cache_roundtrip): 4 passed, 4 warnings (unchanged from baseline)
```

Baseline (`~/audioura-worktrees/prepush-baseline`) has 40 collection errors from missing `Crypto`, `requests`, etc. modules — pre-existing. No new failures introduced by LOCAL-66.

---

## DB changes

**Tables created (migration 006):**
- `wallet_ledger` — append-only, unique idempotency key index
- `wallet_balance_cache` — single row per user, rebuildable
- `wallet_subscription` — tier tracking for cost-stop

All created via `_ensure_tables()` during test run. Production should use `migration/sql/006_wallet_ledger.sql`.

---

## Design decisions applied

| Rule | Implementation |
|------|---------------|
| Append-only | No UPDATE/DELETE on wallet_ledger. Corrections are new rows. |
| Integer cents | `amount_cents INTEGER`, never float. Decimal in Python, integer in DB. |
| Derived balance | `SUM(amount_cents)` over all rows. Cache for speed, rebuild for verification. |
| Clawback may go negative | `refund_clawback()` does NOT clamp. Negative balance recorded without error. |
| Zero-balance = hard stop (D3) | `charge()` returns `was_zero_stop_triggered=True` when balance ≤ 0. No debt. |
| Unlimited cost-stop (D4) | Clear message + Pay-Per-Use switch offer. Never fails silently. |
| Idempotency | `UNIQUE INDEX (idempotency_key)`. Duplicate key = return existing row, no double-credit. |
| Consume `charge_usd` directly | `charge()` takes the final user-facing price. ×5 maths is LOCAL-65's scope. |
| Configuration | All thresholds from env vars (PRICING_MULTIPLIER, etc.). Runtime-tunable, no code change. |
| Apple constraint | No auto-charge. `check_low_balance()` returns reminder text for push/banner. |

---

## Limitations

1. **No live service wiring** — `wallet_ledger.py` is called from tests only. Wiring into the orchestrator requires LOCAL-61's `PaymentProvider` to determine tier and gate decisions. The module is ready to be imported.
2. **Subscription period reset** — `monthly_cost_spent_cents` is not auto-reset at period boundaries. That's the renewal handler's responsibility (LOCAL-61).
3. **No IAP integration** — As designed, the `PaymentProvider` fake is in LOCAL-61. This module records movements regardless of payment source.
