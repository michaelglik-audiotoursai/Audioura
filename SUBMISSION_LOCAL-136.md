##### READY FOR REVIEW

## LOCAL-136: Model Apple's grace period

**Branch:** `kiro/local136-apple-grace-period`  
**Base:** `subscribed`

---

## Summary

Models three distinct subscription states in the entitlement gate:

1. **Active** — normal subscription, access granted.
2. **Cancelled-but-not-yet-expired** — user cancelled auto-renew but has paid through `period_end`. Access continues until `period_end` (inclusive boundary: `>=` means expired).
3. **Expired/Lapsed** — `period_end` has passed, access denied.

Additionally models **billing retry grace period**: when Apple fails to charge a renewal, access continues for 16 days past `period_end` while Apple retries payment.

**Boundary decision:** `period_end` is exclusive — at exactly `period_end`, access is DENIED. Rationale: "access until the end of the period" means the instant the period ends is when access stops.

**Grace period source:** Apple Developer documentation "Billing Grace Period" — Apple retries billing for up to 16 days. Made configurable via `BILLING_RETRY_GRACE_DAYS` env var (fake provider constructor param, real provider env var). Default: 16.

---

## Files Changed

| File | Change |
|------|--------|
| `entitlements.py` | `_get_subscription_tier()` now grants access for `cancelled` state when `period_end > NOW()` |
| `fake_payment_provider.py` | `get_entitlement()` handles cancelled→lapsed at period_end, billing_retry grace window; added `BILLING_RETRY_GRACE_DAYS` constant and constructor param |
| `revenuecat_payment_provider.py` | `get_entitlement()` handles cancelled→lapsed at period_end, billing_retry grace window (configurable via env var) |
| `tests/test_local93_payment_providers.py` | +3 shared tests (cancelled-not-expired, cancelled-expired, billing-retry-retains-access) — runs on both providers |
| `tests/test_local136_apple_grace_period.py` | 19-test suite: fake provider boundary tests, real provider DB tests, entitlement gate tests |

---

## Evidence

### Before counts (existing suites unchanged)

```
Entitlement gate (test_local67): 23/23 passed
Shared provider (test_local93):  15/15 passed (fake), 15/15 passed (real)
```

### After counts

```
Entitlement gate (test_local67): 23/23 passed
Shared provider (test_local93):  18/18 passed (fake), 18/18 passed (real)
Grace period (test_local136):    19/19 passed
```

### Gate test results (D35: exercise the control)

```
gate_cancelled_not_expired_ALLOWED         ✓  (allowed=True)
gate_cancelled_expired_DENIED              ✓  (allowed=False, reason=subscription_inactive)
gate_billing_retry_in_grace_ALLOWED        ✓  (allowed=True)
gate_active_ALLOWED                        ✓  (allowed=True)
gate_lapsed_DENIED                         ✓  (allowed=False, reason=subscription_inactive)
gate_unlimited_cancelled_not_expired_ALLOWED ✓ (allowed=True)
```

### Break-probe (D36)

```
Neutered: sed 's/AND state = .cancelled. AND period_end > NOW()/AND state = .cancelled. AND FALSE/'
Result: 2 tests went RED:
  ✗ gate_cancelled_not_expired_ALLOWED: allowed=False, reason=subscription_inactive
  ✗ gate_unlimited_cancelled_not_expired_ALLOWED: allowed=False, reason=subscription_inactive
Restored: all 19 GREEN
Replacement count: 1 line in entitlements.py
```

### Boundary conditions covered

| Condition | Result | Test |
|-----------|--------|------|
| Cancel day 2 of 30, check day 15 | ALLOWED | cancelled_day2_access_day15 |
| Cancel day 2 of 30, check day 29 | ALLOWED | cancelled_day2_access_day29 |
| Exactly at period_end | DENIED (LAPSED) | cancelled_denied_at_period_end |
| 1 day after period_end | DENIED (LAPSED) | cancelled_denied_after_period_end |
| Billing retry 5 days past period_end | ALLOWED (in 16-day grace) | billing_retry_within_grace_5d |
| Billing retry 15 days past period_end | ALLOWED (in 16-day grace) | billing_retry_within_grace_15d |
| Billing retry at grace end (16 days) | DENIED (LAPSED) | billing_retry_at_grace_end_lapsed |
| Refund after cancellation | Balance goes negative | refund_after_cancel_negative_balance |

### Clock handling

All assertions use injected time:
- Fake provider: `FakePaymentProvider(now=...)` + `set_time()` / `advance_time()`
- Real provider: `period_end` set relative to `datetime.now(timezone.utc)` at test setup
- No `datetime.now()` in assertion paths

---

## Limitations

1. **RevenueCat webhook format assumed.** The `CANCELLATION` event type mapping is based on documented RevenueCat behaviour. Real webhook payloads may differ.
2. **No live Apple verification.** All tests use synthetic data. Real Apple grace period behaviour depends on App Store Connect configuration (Billing Grace Period must be enabled in ASC).
3. **Billing retry grace window is applied in `get_entitlement()` only.** The entitlement gate (`entitlements.py`) queries the DB directly; it checks `state IN ('active', 'billing_retry')` plus the new `cancelled AND period_end > NOW()` clause. The billing retry grace window (16-day extension past period_end) is evaluated by the provider's `get_entitlement()` when transitioning state — but the gate's own query doesn't encode the 16-day window. This means the gate trusts the state column: if the provider hasn't yet transitioned billing_retry→lapsed, the gate allows access.
4. **Docker not tested.** Per constraint, no container builds were attempted.
