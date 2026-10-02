##### READY FOR REVIEW

# LOCAL-67: Entitlement Gate Enforcement — Submission

**Branch:** `kiro/local67-entitlement-gate`  
**Depends on:** LOCAL-61 (merged), LOCAL-66 (merged)  
**Commit:** (see below)

---

## Summary

Extended `check_tour_quota()` and `check_news_quota()` in `entitlements.py` to
enforce billing-based gates for paid tiers, while preserving the free tier logic
byte-for-byte. The existing orchestrator call site is unchanged — same function,
same parameters, same user_id path.

### What changed

**`entitlements.py`** — rewritten to dispatch by tier:
- **`free`** — identical quota-count logic (tours_per_day, news_per_period). No code path change for any existing user.
- **`ppu`** — queries `wallet_ledger.get_balance_cents()`. Zero → hard stop with topup reminder (D3).
- **`unlimited`** — queries `wallet_ledger.check_unlimited_cost_stop()`. Breach → deny with switch-to-PPU offer (D4).
- **Error path** — dedicated `try/except` per billing check. Fail-closed with `reason: 'entitlement_check_error'` and message distinguishing "out of credit" from "couldn't check credit". Logs at ERROR. Never silently allows.

**Structured result** — every return includes `{allowed, reason, remedy}` plus tier-specific fields. Backward-compatible: free tier still returns `{used, max, remaining, clamped_stops}`.

### What did NOT change

- `tour_orchestrator_service.py` — zero changes. Existing call site reads `quota['allowed']` and `quota['clamped_stops']`, both present in all tiers.
- `news_orchestrator_service.py` — zero changes.
- No new migration (LOCAL-67 uses tables from 005_subscription_state + 006_wallet_ledger).
- No new dependencies.

---

## Verification of LOCAL-61's Finding

LOCAL-61 stated: *"The existing entitlements gate at the orchestrator level is the right extension point... extending `check_tour_quota()` to inspect the subscriptions table when plan != 'free'."*

**Confirmed.** The call site at `tour_orchestrator_service.py:1249`:
```python
from entitlements import check_tour_quota
quota = check_tour_quota(user_id, total_stops)
```
is the single gate for all tiers. The orchestrator already:
1. Rejects empty user_id (401)
2. Catches exceptions from the check (503, fail-closed)
3. Returns the result on denial (429)

No parallel gate needed. The extension is purely inside `check_tour_quota()` dispatch logic.

---

## Acceptance Criteria — Live Evidence

### AC1: Free user behaves exactly as before

```
check_tour_quota result (free, under quota):
  {"allowed": true, "reason": "ok", "remedy": null, "clamped_stops": 10,
   "plan": "free", "used": 0, "max": 10, "remaining": 9}

check_tour_quota result (free, over quota):
  {"allowed": false, "reason": "quota_exceeded", "remedy": "upgrade",
   "error": "quota_exceeded", "limit": "tours_per_day", "plan": "free",
   "used": 10, "max": 10, "reset": "2026-08-01T00:00:00Z", "upgrade": true}
```

All legacy keys present: `used`, `max`, `remaining`, `clamped_stops`, `plan`.
Orchestrator log line `used={quota['used']}, remaining={quota['remaining']}` works unchanged.

### AC2: PPU with balance generates; zero balance stops with reminder

```
PPU with $10 balance:
  {"allowed": true, "reason": "ok", "remedy": null, "plan": "ppu",
   "balance_cents": 1000, "low_balance_reminder": null, "clamped_stops": 10}

PPU with $0 balance:
  {"allowed": false, "reason": "insufficient_balance", "remedy": "topup",
   "plan": "ppu", "balance_usd": "0.00", "balance_cents": 0,
   "message": "Your balance is $0.00. Top up $10.00 to continue generating audio tours and articles."}

PPU with $1.50 (low balance, below $2 threshold):
  {"allowed": true, "reason": "ok", "plan": "ppu", "balance_cents": 150,
   "low_balance_reminder": "Your balance is $1.50. Top up $10.00 to continue using audio tours and articles."}
```

### AC3: Unlimited under stop generates; over stop gets message + switch offer

```
Unlimited under cost stop ($5 of $25):
  {"allowed": true, "reason": "ok", "remedy": null, "plan": "unlimited",
   "current_cost_usd": "5.00", "limit_usd": "25.00", "clamped_stops": 15}

Unlimited over cost stop ($26 of $25):
  {"allowed": false, "reason": "cost_stop_reached", "remedy": "switch_to_ppu",
   "plan": "unlimited", "current_cost_usd": "26.00", "limit_usd": "25.00",
   "message": "Your Unlimited plan has reached its monthly usage limit. We've spent
   $26.00 of the $25.00 monthly allowance... You can switch to Pay-Per-Use for the
   rest of this month to continue generating new content..."}
```

### AC4: Error denies rather than allows, with ERROR log

```
Subscription check error (simulated DB failure):
  [ENTITLEMENTS] ERROR: Could not verify subscription for TEST-PPU-BAL-...: Simulated DB failure — DENYING (fail-closed)
  {"allowed": false, "reason": "entitlement_check_error",
   "message": "We could not verify your subscription status. This is a temporary issue on our end..."}

Billing check error (simulated wallet failure):
  [ENTITLEMENTS] ERROR: Billing check failed for TEST-PPU-BAL-... (tier=ppu): Simulated wallet failure — DENYING (fail-closed, this is NOT a credit issue)
  {"allowed": false, "reason": "entitlement_check_error",
   "message": "We could not verify your account balance. This is a temporary issue on our end..."}
```

Messages clearly distinguish "credit issue" vs "system error".

### AC5: Structured result shape for each case

Every result includes `{allowed: bool, reason: str, remedy: str|null}`:
| Scenario | `allowed` | `reason` | `remedy` |
|---|---|---|---|
| free, OK | true | ok | null |
| free, over quota | false | quota_exceeded | upgrade |
| ppu, has balance | true | ok | null |
| ppu, zero balance | false | insufficient_balance | topup |
| unlimited, under stop | true | ok | null |
| unlimited, over stop | false | cost_stop_reached | switch_to_ppu |
| subscription DB error | false | entitlement_check_error | null |
| billing check error | false | entitlement_check_error | null |
| no active subscription | false | subscription_inactive | resubscribe |

### AC6: Regression suite vs prepush-baseline

```
Baseline (~/audioura-worktrees/prepush-baseline):
  test_tour_quota_integration.py:  3/5 (T2 fails: cloud 401 — pre-existing)
  test_news_quota_integration.py:  3/4 (T2 fails: cloud 401 — pre-existing)

LOCAL-67:
  test_tour_quota_integration.py:  3/5 (identical pattern — same cloud 401)
  test_news_quota_integration.py:  3/4 (identical pattern — same cloud 401)

Additional suites:
  test_local67_entitlement_gate.py:  23/23 PASS
  test_local60_cost_metering.py:     7/7 PASS
  test_wallet_ledger.py:             8/8 PASS
  test_pricing.py:                  30/30 PASS
  test_payment_provider.py:         19/19 PASS
```

Zero regressions introduced.

### AC7: Each test tour under $1.30

No tour generation in this task — the entitlement gate is a pre-generation check. The test suite uses only database queries (subscription lookups, balance reads, cost-stop checks). Zero API spend.

---

## Files Changed

| File | Change |
|---|---|
| `entitlements.py` | Rewritten: tier dispatch, structured results, fail-closed error handling |
| `tests/test_local67_entitlement_gate.py` | New: 23-test comprehensive suite |

## Database Changes

**None.** This task uses existing tables from LOCAL-61 (005_subscription_state.sql) and LOCAL-66 (006_wallet_ledger.sql). No new migration needed.

To run the test suite, migrations 005 and 006 must be applied:
```sql
-- Applied to live database for testing (idempotent):
migration/sql/005_subscription_state.sql
migration/sql/006_wallet_ledger.sql
```
