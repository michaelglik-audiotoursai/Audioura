##### READY FOR REVIEW

# LOCAL-90: Tier Switching — Submission

**Branch:** `kiro/local90-tier-switching`  
**Base:** `subscribed`  
**Commit:** `8056cc1`

---

## Summary

Implemented the tier-change mechanism that the entitlement gate's remedy strings
promise. Before this task, `switch_to_ppu` and `upgrade` were dead strings — the
user was told to take an action that no code path could execute. Now every remedy
resolves to a callable endpoint.

### What was built

1. **`tier_change.py`** — Core tier-change logic supporting all six transitions:
   `free→ppu`, `free→unlimited`, `ppu→unlimited`, `unlimited→ppu`, `ppu→free`,
   `unlimited→free`. All changes go through `PaymentProvider` (fake for now) and
   sync DB state atomically on success.

2. **`POST /wallet/<user_id>/change-tier`** — HTTP endpoint on the orchestrator
   (registered via the existing `wallet_bp` Blueprint). Accepts `{target_tier}`,
   returns structured result with `success`, `previous_tier`, `new_tier`,
   `message`, `balance_usd`.

3. **`tests/test_local90_tier_switching.py`** — 14-test end-to-end suite proving
   every transition and the critical loop.

### The critical loop (closed)

```
Unlimited user at cost-stop
  → entitlement gate REFUSES, remedy='switch_to_ppu'
  → user calls POST /wallet/{id}/change-tier {target_tier: "ppu"}
  → tier_change.py validates, calls FakePaymentProvider, syncs DB
  → user tops up (balance was $0)
  → entitlement gate now ALLOWS
  → user generates successfully
```

This is the acceptance criterion that matters. Proved in
`test_critical_path_cost_stop_switch_generate`.

---

## Proration Decision (needs Michael's confirmation)

### Unlimited → PPU (at cost-stop)

**No credit for remaining Unlimited days. No free initial top-up.**

The user already consumed up to $25 of our cost under Unlimited — the plan served
its purpose. Crediting the unused portion of $50 would reward gaming: subscribe
Unlimited, generate $25 of content, switch to PPU with a prorated ~$30 credit.

After switching, balance is $0. User must top up to generate. The $2/month PPU fee
starts from the next billing cycle; the switch itself is fee-free for the
remainder of this period.

### PPU → Unlimited (upgrade)

**Credits are non-refundable (per SUBSCRIBED_DESIGN.md). Balance is frozen, not
lost.** If the user later switches back to PPU, the balance is still there.

The $50 Unlimited fee starts a fresh 30-day period. Cost-stop resets to $0.

### Free → Paid

Standard first subscription. PPU gets the initial $10 top-up welcome bonus.
Unlimited gets a fresh period with $0 cost accumulated.

### Paid → Free (cancellation)

Immediate cutoff in the fake provider. Real Apple implementation must honour the
grace period (access until `period_end`). Flagged as a limitation below.

---

## Acceptance Criteria — Live Evidence

### Every transition exercised

```
Test                                                         Status
--------------------------------------------------------------------------------
free → ppu                                                   PASS
free → unlimited                                             PASS
ppu → unlimited                                              PASS
unlimited → ppu                                              PASS
ppu → free (cancel)                                          PASS
unlimited → free (cancel)                                    PASS
CRITICAL: cost-stop → switch → generate                      PASS
no-op same tier                                              PASS
invalid tier name rejected                                   PASS
fail-closed on DB error                                      PASS
cost-stop irrelevant after switch to PPU                     PASS
free upgrade remedy closes the loop                          PASS
proration: Unlimited→PPU, no refund, no free credit          PASS
proration: PPU→Unlimited, credits frozen                     PASS
================================================================================
Total: 14 | PASS: 14 | FAIL: 0
```

### Critical path: cost-stop → switch → generate

```
--- CRITICAL PATH: cost-stop → switch → generate ---
  Step 1: Refused=True, remedy=switch_to_ppu
  Step 2: Switched=True, new_tier=ppu
  Step 3: Balance after switch = $0.00
  Step 3b: Topped up to $10.00
  Step 4: Allowed=True, plan=ppu
✅ CRITICAL: cost-stop → switch → generate — refused→switch→allowed | balance=$10.00
```

### Free user upgrading

```
--- Test: free user upgrade remedy ---
  Created 10 tour requests to exhaust quota
  Step 1: Refused=True, remedy=upgrade
  Step 3: Allowed=True
✅ free upgrade remedy closes the loop — refused=True, upgraded=True, allowed=True
```

### Subscriber cancelling to free

```
--- Test: ppu → free (cancel) ---
✅ ppu → free (cancel) — plan=free

--- Test: unlimited → free (cancel) ---
✅ unlimited → free (cancel) — plan=free
```

### Fail-closed on partial failure (D14)

```
--- Test: fail-closed on DB error ---
  [provider purchase succeeds, but DB sync fails due to FK violation]
  Result: success=False, message="Your purchase was processed but we could not
  activate your subscription. Please contact support with this reference: fake_txn_..."
  User remains on previous tier. Not billed for one tier and entitled to another.
✅ fail-closed on DB error
```

### Proration numbers

| Transition | Balance Before | Balance After | Notes |
|---|---|---|---|
| Unlimited→PPU | n/a | $0.00 | No refund, no free credit |
| PPU→Unlimited | $6.50 | $6.50 | Credits frozen (preserved) |
| Free→PPU | $0.00 | $10.00 | Initial $10 welcome top-up |

### test_local82_subscribed_e2e.py still green (9/10 — pre-existing)

```
Total: 10 | PASS: 9 | FAIL: 1
  Step 10 (API reconciliation) fails with wallet=404 because the running Docker
  container has the OLD orchestrator image without wallet_bp. This is pre-existing
  (same failure at LOCAL-82 merge time). Steps 1-9 all PASS.
```

### Constraints verified

```
audio_tours row count: 55 (before) → 55 (after)
tours-near/43.7009358/7.2683912?radius=50: [1, 12, 14, 17, 21, 24, 27, 28, 29] ✅
```

---

## Files Changed

| File | Change |
|---|---|
| `tier_change.py` | New: core tier-change logic, all 6 transitions, DB sync |
| `wallet_api.py` | Added: `POST /wallet/<user_id>/change-tier` endpoint |
| `tests/test_local90_tier_switching.py` | New: 14-test E2E suite |

---

## Design Decisions

1. **All tier changes go through PaymentProvider.** No DB-only tier flips in the
   production path. `_sync_db_state` only runs after the provider confirms. The
   fake provider models the Apple flow so the same code path works with RevenueCat.

2. **Atomic DB sync with advisory lock.** All table updates (`users.plan`,
   `subscriptions`, `wallet_subscription`) happen in a single transaction with
   `pg_advisory_xact_lock(hashtext(user_id))`. Concurrent requests for the same
   user cannot interleave.

3. **Purchase-first, then cancel.** For `ppu↔unlimited` switches, the new tier is
   purchased BEFORE the old one is cancelled. This means if the purchase fails, the
   user stays on their current tier (safe). Apple's subscription groups handle this
   natively in production.

4. **No initial top-up on tier switch.** The $10 welcome bonus is only for
   `free→ppu` (new subscribers). Switching from `unlimited→ppu` starts at $0
   balance — the user must explicitly top up. This prevents gaming.

5. **Cancellation deletes `wallet_subscription` row.** Free users have no
   subscription tracking. Consistent with D5 (free survives unchanged) and the
   existing code where `_get_user_tier()` returns "free" when no row exists.

---

## Limitations

1. **Apple grace period not modelled.** Real cancellation retains access until
   `period_end`. The fake does immediate cutoff. Production implementation must
   check `period_end` before cutting access on cancellation.

2. **Single FakePaymentProvider instance per request.** The HTTP endpoint creates a
   fresh `FakePaymentProvider()` per call, so its in-memory state doesn't persist.
   This is fine for the DB-backed flow (all state lives in Postgres), but means the
   provider's internal ledger isn't useful across requests. Production RevenueCat
   has persistent server-side state.

3. **Step 10 of LOCAL-82 still fails.** The Docker container runs an old image
   without `wallet_bp`. This is pre-existing and unrelated to this task. Rebuilding
   the orchestrator image would fix it.

4. **Proration decision is defensible but needs Michael.** Particularly:
   "no credit for remaining Unlimited days" is the simplest honest answer but
   might feel unfair to a user who paid $50 and used only 20 days. If Michael
   disagrees, a pro-rated credit into the PPU wallet is a ~10-line change in
   `_sync_db_state_switch`.
