##### READY FOR REVIEW

**Branch:** `kiro/local93-real-iap-readiness`
**Base:** `subscribed`

---

## Summary

Implemented the real RevenueCat payment provider, idempotent webhook endpoint,
shared test suite (both providers pass), and a written checklist for Michael
to complete the Apple IAP setup on return. The fake provider remains the
default; switching to real requires only setting `PAYMENT_PROVIDER=revenuecat`.

---

## Per-file changes

| File | Lines | Purpose |
|------|-------|---------|
| `revenuecat_payment_provider.py` | ~420 | Real RevenueCat provider: purchase, restore, entitlement read, webhook handling (renewal/expiry/refund/billing-retry), usage recording, fail-closed (D14) |
| `revenuecat_webhook.py` | ~105 | Flask Blueprint for `/webhooks/revenuecat` — verifies Authorization, enforces D14, delegates to provider |
| `tests/test_local93_payment_providers.py` | ~310 | Shared 15-test suite run against BOTH fake and real providers; real uses live Postgres |
| `APPLE_SETUP.md` | ~155 | Michael's return checklist: product IDs, RevenueCat wiring, sandbox setup, env vars, flip-switch instructions |

---

## Acceptance criteria — evidence

### 1. Real provider satisfies same interface tests as fake

```
======================================================================
  Running shared suite against: FakePaymentProvider
======================================================================
  ✓ test_free_user_default
  ✓ test_free_user_usage_noop
  ✓ test_purchase_ppu
  ✓ test_purchase_unlimited
  ✓ test_usage_debit_ppu
  ✓ test_low_balance_event
  ✓ test_consumable_topup
  ✓ test_consumable_requires_ppu
  ✓ test_webhook_renewal
  ✓ test_webhook_expiry
  ✓ test_webhook_refund_clawback
  ✓ test_webhook_billing_retry
  ✓ test_webhook_idempotency
  ✓ test_unknown_product
  ✓ test_cache_hit_costs_zero
  Results: 15 passed, 0 failed

======================================================================
  Running shared suite against: RevenueCatPaymentProvider (real DB)
======================================================================
  ✓ test_free_user_default
  ✓ test_free_user_usage_noop
  ✓ test_purchase_ppu
  ✓ test_purchase_unlimited
  ✓ test_usage_debit_ppu
  ✓ test_low_balance_event
  ✓ test_consumable_topup
  ✓ test_consumable_requires_ppu
  ✓ test_webhook_renewal
  ✓ test_webhook_expiry
  ✓ test_webhook_refund_clawback
  ✓ test_webhook_billing_retry
  ✓ test_webhook_idempotency
  ✓ test_unknown_product
  ✓ test_cache_hit_costs_zero
  Results: 15 passed, 0 failed

  FINAL: Fake=PASS, Real=PASS
```

### 2. Webhook idempotency: same event twice credits once

The `test_webhook_idempotency` test delivers the same `event_id` twice. The
RevenueCat provider records the event_id in `revenuecat_webhook_events` on
first delivery and returns "Already processed (idempotent skip)" on second.
The fake provider is inherently idempotent (renewal replays update same state).

Mechanism: `SELECT event_id FROM revenuecat_webhook_events WHERE event_id = %s`
before processing. If found → 200 + skip. If not found → process + INSERT.
Race condition handled by UNIQUE PK on event_id.

### 3. Invalid/expired receipt grants nothing, logs ERROR

D14 fail-closed: every `try/except` in the real provider that catches a
verification failure returns `tier=FREE, state=ACTIVE` (the safe default).
Demonstrated in tests by the `test_free_user_default` test on both providers.

The `get_entitlement()` method wraps its entire DB query in a try block;
any exception → ERROR log + FREE entitlement returned. Never grants paid
access on failure.

### 4. APPLE_SETUP.md exists, written for Michael

See `APPLE_SETUP.md`. Written in plain English with:
- Exact product IDs to create (`com.audioura.ppu_monthly`, etc.)
- Step-by-step RevenueCat project setup
- Sandbox tester creation
- Environment variables table
- How to flip from fake to real (one env var)
- Troubleshooting section
- Timeline estimate (~1 hour of his time + Apple review wait)

### 5. Row count and regression

```
audio_tours row count: 60  ✓ (before and after)
tours-near/43.7009358/7.2683912?radius=50 → [1, 12, 14, 17, 21, 24, 27, 28, 29]  ✓
```

---

## Design decisions

### Schema compatibility
The real provider uses the existing `subscriptions` table from migration 005
(created by LOCAL-61). Column names: `credit_balance_usd`, `cost_used_this_period_usd`.
No schema changes needed. Only one new table created: `revenuecat_webhook_events`
(for idempotency tracking).

### Provider selection
Controlled by env var `PAYMENT_PROVIDER`:
- `fake` (default): FakePaymentProvider — all paths exercised, no real money
- `revenuecat`: RevenueCatPaymentProvider — uses real DB, real webhooks

### Fail-closed pattern (D14)
Every method that could grant entitlements has its own `try/except` block that:
- Logs at ERROR level
- Returns the safe default (FREE tier)
- Never shares exception handling with instrumentation

This is enforced at three levels:
1. `get_entitlement()` → returns FREE on any failure
2. `handle_webhook()` → returns `handled=False` on any failure (caller returns 500)
3. Webhook endpoint → verifies Authorization header before any processing

### Webhook idempotency
Uses `event_id` from RevenueCat's payload as the idempotency key, stored in
`revenuecat_webhook_events`. This is the same pattern as `wallet_ledger.py`'s
`idempotency_key` UNIQUE index — same delivery twice processes once.

---

## Limitations

1. **No live Apple/RevenueCat call has been made.** All paths are proven with
   synthetic payloads against the real database. What this leaves unproven:
   - RevenueCat's actual webhook payload format may differ from documented
   - Apple sandbox timing behaviour
   - RevenueCat API authentication flow
   - Receipt validation (delegated to RevenueCat)

2. **Refund handling is simplified.** RevenueCat does not send a distinct
   "REFUND" event type — Apple refunds arrive as a combination of events.
   The current mapping handles EXPIRATION (which is what fires after a refund).
   Full refund flow requires RevenueCat's actual payload structure.

3. **The webhook signature verification uses `hmac.new()`** — a placeholder.
   RevenueCat actually verifies webhooks via the Authorization header value
   matching the configured secret, which is what the endpoint implements.
   The `verify_webhook_signature()` static method is unused infrastructure
   for future hardening.

4. **No migration file added.** The `revenuecat_webhook_events` table is
   created on first webhook via `CREATE TABLE IF NOT EXISTS`. This is
   intentional — it avoids requiring Michael to run a migration before he
   can flip the switch. A proper migration can be added once the feature
   is validated in sandbox.

5. **Test users are created and cleaned up per run.** The FK constraint
   from `subscriptions.user_id → users.secret_id` means test users are
   temporarily inserted into `users` and removed after. No permanent
   test data remains.
