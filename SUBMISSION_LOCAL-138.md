##### READY FOR REVIEW

# SUBMISSION_LOCAL-138.md — Billing retry window bounded in the gate

**Task:** LOCAL-138  
**Branch:** `kiro/local138-billing-retry-window-in-gate`  
**Commit:** `369ec6e`  
**Date:** 2026-08-02

---

## Summary

The entitlement gate (`_get_subscription_tier` in `entitlements.py`) previously accepted `billing_retry` state unconditionally. A subscription row stuck in `billing_retry` — due to a RevenueCat outage, dropped webhook, or unresolved Apple billing — would grant access indefinitely. This violated D14 (controls fail closed).

The fix bounds `billing_retry` in the gate's own SQL: `period_end + interval '<grace> days' > NOW()`. The gate is now self-sufficient — it does not depend on a webhook arriving to lapse the row.

**Boundary decision:** `period_end + grace` is EXCLUSIVE (at exactly the boundary, access is DENIED). This matches the cancelled state boundary from LOCAL-136.

**Grace constant:** One source of truth — `BILLING_RETRY_GRACE_DAYS` in `payment_provider.py`, env-configurable via `BILLING_RETRY_GRACE_DAYS` (default 16). Both providers and the gate import it.

---

## Per-file changes

| File | Change |
|------|--------|
| `payment_provider.py` | Added `BILLING_RETRY_GRACE_DAYS = int(os.environ.get("BILLING_RETRY_GRACE_DAYS", "16"))` as the canonical constant (+`import os`) |
| `entitlements.py` | `_get_subscription_tier()` now queries `billing_retry` with `period_end + interval '%s days' > NOW()` using the imported constant; split the old single `IN ('active', 'billing_retry')` query into two: active (unconditional) + billing_retry (bounded) |
| `fake_payment_provider.py` | Removed local `BILLING_RETRY_GRACE_DAYS = 16` definition; imports from `payment_provider` instead |
| `revenuecat_payment_provider.py` | Removed inline `os.environ.get("BILLING_RETRY_GRACE_DAYS", "16")`; imports `BILLING_RETRY_GRACE_DAYS` from `payment_provider` |
| `tests/test_local138_billing_retry_gate.py` | 12 tests: 8 gate assertions + 4 break-probe assertions |

---

## Verbatim evidence

### test_local138_billing_retry_gate.py (12 tests)

```
======================================================================
  LOCAL-138: Billing retry window bounded in the gate
  BILLING_RETRY_GRACE_DAYS = 16
  Boundary: period_end + grace is EXCLUSIVE (>= means expired)
======================================================================

  ✓ billing_retry_5d_past_ALLOW
  ✓ billing_retry_15d_past_ALLOW
  ✓ billing_retry_16d_past_DENY
  ✓ billing_retry_400d_past_DENY_stuck_row
  ✓ active_ALLOW
  ✓ cancelled_before_period_end_ALLOW
  ✓ cancelled_after_period_end_DENY
  ✓ db_error_DENY_fail_closed

======================================================================
  BREAK-PROBE: Neutering billing_retry interval clause
======================================================================

  Replacement count: 1
  ✓ break_probe_clause_found
  ✓ break_probe_400d_flips_DENY_to_ALLOW
  ✓ break_probe_16d_flips_DENY_to_ALLOW

  ✓ Original _get_subscription_tier restored
  ✓ break_probe_restored_400d_DENY

======================================================================
  RESULTS: 12/12 passed, 0 failed
======================================================================
```

### test_local67_entitlement_gate.py (23 tests — unchanged)

```
RESULTS: 23/23 passed, 0 failed
```

### test_local136_apple_grace_period.py (19 tests — unchanged)

```
  RESULTS: 19/19 passed, 0 failed
```

### test_local93_payment_providers.py (fake 18 + real 18 — unchanged)

```
  Results: 18 passed, 0 failed
  Results: 18 passed, 0 failed
  FINAL: Fake=PASS, Real=PASS
```

### Row counts

```
audio_tours: 101
stop_metrics: 1005
```

(audio_tours was 98 at session start; rose to 101 from test_local136/test_local67 runs which insert `tour_requests` rows — audio_tours itself was not modified by LOCAL-138 tests. stop_metrics unchanged.)

### git status

```
(clean — no untracked files after commit)
```

### git diff --stat

```
 entitlements.py                           |  35 +++-
 fake_payment_provider.py                  |   5 +-
 payment_provider.py                       |   9 +
 revenuecat_payment_provider.py            |   4 +-
 tests/test_local138_billing_retry_gate.py | 337 ++++++++++++++++++++++++++++++
 5 files changed, 377 insertions(+), 13 deletions(-)
```

---

## Break-probe detail

1. `inspect.getsource()` confirms the bounded clause exists: `replacement_count: 1`
2. Monkey-patches `_get_subscription_tier` with the old unbounded query (`state IN ('active', 'billing_retry')` — no time check)
3. The 400-day stuck row flips from DENY → ALLOW (proving the clause is what denies it)
4. The exactly-16-day row flips from DENY → ALLOW
5. Original function restored; 400-day case denies again

---

## Limitations

1. **`active` state has no period_end bound in the gate.** An `active` row past period_end is granted access unconditionally. The assumption is that webhooks (renewal or expiry) will always transition `active` → renewed or lapsed. If a webhook is dropped for an `active` row, the same infinite-access issue theoretically exists. However, Apple sends renewal webhooks proactively (before expiry) and the billing_retry case is far more likely to get stuck — `active` rows past period_end are an exceptional transient state. A future task could add `period_end > NOW()` for `active` as well.

2. **The grace window is calendar-day granular.** PostgreSQL's `interval '16 days'` is exact (to the microsecond), so this is actually precise to the second. No limitation here — noting for clarity.

3. **No live Apple/RevenueCat webhook test.** The fix is proven against the gate function with controlled DB state. A dropped webhook in production would be caught by this new clause after grace expires, but that exact scenario cannot be tested without a real RevenueCat environment.
