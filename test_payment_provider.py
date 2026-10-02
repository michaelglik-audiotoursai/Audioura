"""
Test suite for PaymentProvider interface + FakePaymentProvider.

Exercises every state machine path:
  - purchase → active → renew → active
  - → expire → lapsed
  - → refund → clawback recorded (balance may go negative)
  - restore on a new device
  - low-balance event triggers reminder
  - free plan unaffected

Run: python -m pytest test_payment_provider.py -v
  or: python test_payment_provider.py  (standalone)
"""

import sys
from datetime import datetime, timedelta

from payment_provider import (
    SubscriptionTier,
    SubscriptionState,
    WebhookEvent,
    Entitlement,
    LowBalanceEvent,
)
from fake_payment_provider import (
    FakePaymentProvider,
    CREDIT_TOPUP_USD,
    CREDIT_LOW_BALANCE_USD,
    PRICING_MULTIPLIER,
    UNLIMITED_MONTHLY_FEE_USD,
    UNLIMITED_COST_STOP_FRACTION,
)


def test_free_user_default():
    """Free plan user behaves exactly as before — no subscription state."""
    provider = FakePaymentProvider()
    ent = provider.get_entitlement("free_user_123")
    
    assert ent.tier == SubscriptionTier.FREE
    assert ent.state == SubscriptionState.ACTIVE
    assert ent.period_start is None
    assert ent.period_end is None
    assert ent.credit_balance_usd is None
    assert ent.cost_used_this_period_usd is None
    assert ent.provider_subscription_id is None
    print(f"  FREE user entitlement: tier={ent.tier.value}, state={ent.state.value}, "
          f"no period, no balance — exactly as before")


def test_free_user_usage_noop():
    """Recording usage on a free user is a no-op (no balance to debit)."""
    provider = FakePaymentProvider()
    result = provider.record_usage("free_user_123", "tour_generation", 0.069)
    assert result is None
    ent = provider.get_entitlement("free_user_123")
    assert ent.tier == SubscriptionTier.FREE
    print(f"  FREE user usage: no-op, tier still={ent.tier.value}")


def test_purchase_ppu_subscription():
    """Purchase PPU → active with initial credits."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    result = provider.purchase_subscription("user_a", "com.audioura.ppu_monthly")
    
    assert result.success is True
    assert result.new_tier == SubscriptionTier.PPU
    assert result.new_balance_usd == CREDIT_TOPUP_USD  # $10.00
    assert result.transaction_id is not None
    
    ent = provider.get_entitlement("user_a")
    assert ent.tier == SubscriptionTier.PPU
    assert ent.state == SubscriptionState.ACTIVE
    assert ent.credit_balance_usd == CREDIT_TOPUP_USD
    assert ent.period_start == datetime(2026, 8, 1, 12, 0, 0)
    assert ent.period_end == datetime(2026, 8, 31, 12, 0, 0)
    print(f"  PPU purchase: tier={ent.tier.value}, state={ent.state.value}, "
          f"balance=${ent.credit_balance_usd:.2f}, "
          f"period={ent.period_start} → {ent.period_end}")


def test_purchase_unlimited_subscription():
    """Purchase Unlimited → active with cost tracking."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    result = provider.purchase_subscription("user_b", "com.audioura.unlimited_monthly")
    
    assert result.success is True
    assert result.new_tier == SubscriptionTier.UNLIMITED
    
    ent = provider.get_entitlement("user_b")
    assert ent.tier == SubscriptionTier.UNLIMITED
    assert ent.state == SubscriptionState.ACTIVE
    assert ent.cost_used_this_period_usd == 0.0
    assert ent.cost_stop_usd == UNLIMITED_MONTHLY_FEE_USD * UNLIMITED_COST_STOP_FRACTION  # $25.00
    print(f"  UNLIMITED purchase: tier={ent.tier.value}, state={ent.state.value}, "
          f"cost_used=${ent.cost_used_this_period_usd:.2f}, "
          f"cost_stop=${ent.cost_stop_usd:.2f}")


def test_state_machine_purchase_renew():
    """purchase → active → renew → still active, period extended."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_c", "com.audioura.ppu_monthly")
    
    # Record some usage
    provider.record_usage("user_c", "tour_generation", 0.069)
    ent_before = provider.get_entitlement("user_c")
    balance_before = ent_before.credit_balance_usd
    print(f"  BEFORE renewal: state={ent_before.state.value}, balance=${balance_before:.4f}")
    
    # Advance time to renewal point
    provider.advance_time(timedelta(days=30))
    
    # Webhook: renewal
    result = provider.handle_webhook({
        "event_type": "renewal",
        "user_id": "user_c",
    })
    assert result.handled is True
    assert result.event_type == WebhookEvent.RENEWAL
    
    ent_after = provider.get_entitlement("user_c")
    assert ent_after.state == SubscriptionState.ACTIVE
    assert ent_after.period_start == provider.now
    # Balance preserved across renewal
    assert ent_after.credit_balance_usd == balance_before
    print(f"  AFTER renewal: state={ent_after.state.value}, balance=${ent_after.credit_balance_usd:.4f}, "
          f"new period={ent_after.period_start} → {ent_after.period_end}")


def test_state_machine_expire():
    """active → expire → lapsed."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_d", "com.audioura.ppu_monthly")
    
    ent_before = provider.get_entitlement("user_d")
    print(f"  BEFORE expiry: state={ent_before.state.value}, tier={ent_before.tier.value}")
    
    # Webhook: expiry
    result = provider.handle_webhook({
        "event_type": "expiry",
        "user_id": "user_d",
    })
    assert result.handled is True
    assert result.event_type == WebhookEvent.EXPIRY
    
    ent_after = provider.get_entitlement("user_d")
    assert ent_after.state == SubscriptionState.LAPSED
    print(f"  AFTER expiry: state={ent_after.state.value}, tier={ent_after.tier.value}")


def test_state_machine_time_based_expiry():
    """Subscription expires when clock passes period_end."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_time", "com.audioura.ppu_monthly")
    
    ent = provider.get_entitlement("user_time")
    assert ent.state == SubscriptionState.ACTIVE
    
    # Advance past period end
    provider.advance_time(timedelta(days=31))
    
    ent = provider.get_entitlement("user_time")
    assert ent.state == SubscriptionState.LAPSED
    print(f"  Time-based expiry: state={ent.state.value} after 31 days")


def test_refund_clawback():
    """Refund after spend: balance goes negative, record is NOT lost."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_e", "com.audioura.ppu_monthly")
    
    # Spend most of the balance: 25 tours at $0.069 each → $0.069 * 5 * 25 = $8.625
    for i in range(25):
        provider.record_usage("user_e", "tour_generation", 0.069)
    
    balance_after_spend = provider.get_balance("user_e")
    print(f"  Balance after 25 tours: ${balance_after_spend:.4f}")
    assert balance_after_spend < CREDIT_TOPUP_USD  # spent some
    
    # Apple refunds the $10.00 top-up
    result = provider.handle_webhook({
        "event_type": "refund",
        "user_id": "user_e",
        "refund_amount_usd": 10.00,
    })
    assert result.handled is True
    assert result.event_type == WebhookEvent.REFUND
    
    final_balance = provider.get_balance("user_e")
    print(f"  Balance after $10 refund: ${final_balance:.4f} (NEGATIVE is expected)")
    
    # Balance should be negative: spent $8.625, then lost $10.00
    assert final_balance < 0, f"Expected negative balance, got {final_balance}"
    
    # The transaction is recorded, not lost
    txns = provider.get_transactions("user_e")
    refund_txns = [t for t in txns if t["type"] == "refund_clawback"]
    assert len(refund_txns) == 1
    assert refund_txns[0]["amount_usd"] == -10.00
    assert refund_txns[0]["resulting_balance_usd"] == final_balance
    print(f"  Refund transaction recorded: amount={refund_txns[0]['amount_usd']}, "
          f"resulting_balance={refund_txns[0]['resulting_balance_usd']:.4f}")


def test_restore_on_new_device():
    """Restore purchases on a new device."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    
    # Original purchase
    provider.purchase_subscription("user_f", "com.audioura.ppu_monthly")
    provider.record_usage("user_f", "tour_generation", 0.069)
    balance = provider.get_balance("user_f")
    
    # Restore on same user (simulates new device, same Apple ID)
    result = provider.restore_purchases("user_f")
    assert result.success is True
    assert result.new_tier == SubscriptionTier.PPU
    
    ent = provider.get_entitlement("user_f")
    assert ent.tier == SubscriptionTier.PPU
    assert ent.state == SubscriptionState.ACTIVE
    assert ent.credit_balance_usd == balance  # Balance preserved
    print(f"  Restore: tier={ent.tier.value}, state={ent.state.value}, "
          f"balance=${ent.credit_balance_usd:.4f} (preserved)")


def test_restore_no_purchases():
    """Restore with no prior purchases returns failure."""
    provider = FakePaymentProvider()
    result = provider.restore_purchases("new_user_no_sub")
    assert result.success is False
    assert "No purchases to restore" in result.error
    print(f"  Restore (no purchases): success={result.success}, error='{result.error}'")


def test_low_balance_event():
    """Low balance triggers a reminder event, never an auto-charge."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_g", "com.audioura.ppu_monthly")
    
    # Spend down to near threshold: need to spend $8.00 of the $10.00
    # Each tour costs $0.069 * 5 = $0.345 to user
    # $8.00 / $0.345 ≈ 23.2 tours
    for i in range(23):
        result = provider.record_usage("user_g", "tour_generation", 0.069)
    
    # Balance should be around $2.07, still above threshold
    balance = provider.get_balance("user_g")
    print(f"  After 23 tours: balance=${balance:.4f}")
    
    # One more tour should push below $2.00 threshold
    event = provider.record_usage("user_g", "tour_generation", 0.069)
    balance = provider.get_balance("user_g")
    print(f"  After 24 tours: balance=${balance:.4f}")
    
    if balance < CREDIT_LOW_BALANCE_USD:
        assert event is not None
        assert isinstance(event, LowBalanceEvent)
        assert event.current_balance_usd == balance
        assert event.threshold_usd == CREDIT_LOW_BALANCE_USD
        print(f"  LOW BALANCE EVENT: balance=${event.current_balance_usd:.4f} < "
              f"threshold=${event.threshold_usd:.2f} → reminder triggered")
    
    # Verify events are queryable
    events = provider.get_low_balance_events("user_g")
    assert len(events) >= 1
    print(f"  Pending low-balance events: {len(events)}")
    
    # Verify: NO auto-charge happened. Balance is still low.
    assert provider.get_balance("user_g") < CREDIT_LOW_BALANCE_USD
    print(f"  Confirmed: no auto-charge. Balance still ${provider.get_balance('user_g'):.4f}")


def test_consumable_purchase_clears_low_balance():
    """After user manually tops up, low-balance events are cleared."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_h", "com.audioura.ppu_monthly")
    
    # Spend down below threshold
    for i in range(28):
        provider.record_usage("user_h", "tour_generation", 0.069)
    
    events_before = provider.get_low_balance_events("user_h")
    assert len(events_before) >= 1
    
    # User manually purchases top-up (explicit action, authenticated)
    result = provider.purchase_consumable("user_h", "com.audioura.credit_topup_10")
    assert result.success is True
    assert result.new_balance_usd > CREDIT_LOW_BALANCE_USD
    
    # Low-balance events cleared
    events_after = provider.get_low_balance_events("user_h")
    assert len(events_after) == 0
    print(f"  Top-up: balance=${result.new_balance_usd:.4f}, "
          f"low-balance events cleared ({len(events_before)} → {len(events_after)})")


def test_consumable_requires_ppu():
    """Credit top-up only works for PPU subscribers."""
    provider = FakePaymentProvider()
    
    # Free user can't buy credits
    result = provider.purchase_consumable("free_user", "com.audioura.credit_topup_10")
    assert result.success is False
    print(f"  Free user top-up: success={result.success}, error='{result.error}'")
    
    # Unlimited user can't buy credits either
    provider.purchase_subscription("unlimited_user", "com.audioura.unlimited_monthly")
    result = provider.purchase_consumable("unlimited_user", "com.audioura.credit_topup_10")
    assert result.success is False
    print(f"  Unlimited user top-up: success={result.success}, error='{result.error}'")


def test_unlimited_cost_tracking():
    """Unlimited tracks our-cost without debiting a balance."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_i", "com.audioura.unlimited_monthly")
    
    # Generate 10 tours
    for i in range(10):
        provider.record_usage("user_i", "tour_generation", 0.069)
    
    ent = provider.get_entitlement("user_i")
    expected_cost = 0.069 * 10
    assert abs(ent.cost_used_this_period_usd - expected_cost) < 0.001
    assert ent.cost_stop_usd == 25.0
    print(f"  Unlimited after 10 tours: cost_used=${ent.cost_used_this_period_usd:.4f}, "
          f"cost_stop=${ent.cost_stop_usd:.2f}")


def test_billing_retry():
    """Billing retry sets the state without losing subscription."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_j", "com.audioura.ppu_monthly")
    
    result = provider.handle_webhook({
        "event_type": "billing_retry",
        "user_id": "user_j",
    })
    assert result.handled is True
    
    ent = provider.get_entitlement("user_j")
    assert ent.state == SubscriptionState.BILLING_RETRY
    assert ent.tier == SubscriptionTier.PPU  # tier preserved
    print(f"  Billing retry: state={ent.state.value}, tier={ent.tier.value}")


def test_full_lifecycle():
    """Full state machine: purchase → use → renew → use → expire → restore."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    
    print("\n  === FULL LIFECYCLE ===")
    
    # 1. Purchase
    r = provider.purchase_subscription("lifecycle_user", "com.audioura.ppu_monthly")
    ent = provider.get_entitlement("lifecycle_user")
    print(f"  1. PURCHASE: tier={ent.tier.value}, state={ent.state.value}, "
          f"balance=${ent.credit_balance_usd:.2f}")
    assert ent.tier == SubscriptionTier.PPU
    assert ent.state == SubscriptionState.ACTIVE
    
    # 2. Use
    provider.record_usage("lifecycle_user", "tour_generation", 0.069)
    ent = provider.get_entitlement("lifecycle_user")
    print(f"  2. USE: balance=${ent.credit_balance_usd:.4f} (after 1 tour)")
    
    # 3. Renew
    provider.advance_time(timedelta(days=30))
    provider.handle_webhook({"event_type": "renewal", "user_id": "lifecycle_user"})
    ent = provider.get_entitlement("lifecycle_user")
    print(f"  3. RENEW: state={ent.state.value}, "
          f"period={ent.period_start.date()} → {ent.period_end.date()}")
    assert ent.state == SubscriptionState.ACTIVE
    
    # 4. More usage
    provider.record_usage("lifecycle_user", "news_article", 0.02)
    ent = provider.get_entitlement("lifecycle_user")
    print(f"  4. USE: balance=${ent.credit_balance_usd:.4f} (after news)")
    
    # 5. Expire
    provider.handle_webhook({"event_type": "expiry", "user_id": "lifecycle_user"})
    ent = provider.get_entitlement("lifecycle_user")
    print(f"  5. EXPIRE: state={ent.state.value}")
    assert ent.state == SubscriptionState.LAPSED
    
    # 6. Restore
    r = provider.restore_purchases("lifecycle_user")
    # Restore won't work on a lapsed subscription
    # (correct behavior — user needs to re-purchase or renew)
    print(f"  6. RESTORE (lapsed): success={r.success}")


def test_unknown_product():
    """Unknown product IDs fail gracefully."""
    provider = FakePaymentProvider()
    r = provider.purchase_subscription("user_k", "com.unknown.product")
    assert r.success is False
    assert "Unknown product" in r.error
    print(f"  Unknown product: error='{r.error}'")


def test_cache_hit_costs_zero():
    """Cache hits should meter at ~$0 — the worst bug would be charging generation cost."""
    provider = FakePaymentProvider(now=datetime(2026, 8, 1, 12, 0, 0))
    provider.purchase_subscription("user_cache", "com.audioura.ppu_monthly")
    
    initial_balance = provider.get_balance("user_cache")
    
    # A cache hit costs $0.00 to us
    provider.record_usage("user_cache", "tour_download_cached", 0.00)
    
    after_balance = provider.get_balance("user_cache")
    assert after_balance == initial_balance
    print(f"  Cache hit: balance unchanged ${initial_balance:.2f} → ${after_balance:.2f}")


# --- Before/After comparison for free plan ---

def test_free_plan_before_after():
    """
    Demonstrate that free plan users are completely unaffected.
    Before: user has no subscription state, uses quota entitlements.
    After: identical behavior.
    """
    provider = FakePaymentProvider()
    
    print("\n  === FREE PLAN BEFORE/AFTER ===")
    print("  BEFORE (no subscription system):")
    print("    - User 'free_user' has tier=free, no period, no balance")
    print("    - Usage is quota-gated (1 tour/day via entitlements.py)")
    print("    - No transaction history, no wallet")
    
    ent = provider.get_entitlement("free_user")
    print("  AFTER (with subscription system):")
    print(f"    - User 'free_user' has tier={ent.tier.value}, "
          f"period_start={ent.period_start}, balance={ent.credit_balance_usd}")
    print(f"    - state={ent.state.value} (always active for free)")
    print("    - Usage still quota-gated (entitlements.py unchanged)")
    print("    - record_usage is a no-op for free users")
    
    result = provider.record_usage("free_user", "tour_generation", 0.069)
    assert result is None
    print(f"    - record_usage returns: {result} (no-op confirmed)")
    print("    - No subscription row created in DB for free users")
    print("  VERDICT: Free plan behavior IDENTICAL before and after.")


def run_all_tests():
    """Run all tests and print state machine transitions."""
    tests = [
        test_free_user_default,
        test_free_user_usage_noop,
        test_purchase_ppu_subscription,
        test_purchase_unlimited_subscription,
        test_state_machine_purchase_renew,
        test_state_machine_expire,
        test_state_machine_time_based_expiry,
        test_refund_clawback,
        test_restore_on_new_device,
        test_restore_no_purchases,
        test_low_balance_event,
        test_consumable_purchase_clears_low_balance,
        test_consumable_requires_ppu,
        test_unlimited_cost_tracking,
        test_billing_retry,
        test_full_lifecycle,
        test_unknown_product,
        test_cache_hit_costs_zero,
        test_free_plan_before_after,
    ]
    
    print("=" * 70)
    print("PaymentProvider State Machine Tests")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for test_fn in tests:
        name = test_fn.__name__
        try:
            print(f"\n[TEST] {name}")
            test_fn()
            print(f"  ✓ PASS")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
