#!/usr/bin/env python3
"""
LOCAL-136: Apple grace period tests.

Proves three distinct states:
  1. Active — normal subscription, access granted.
  2. Cancelled-but-not-yet-expired — access continues to period_end.
  3. Expired — access ends.

Plus billing retry grace period (Apple retries ~16 days past period_end).

Tests exercise the entitlement GATE (entitlements.py) — not just provider fields.
Uses injected/parameterised time (never datetime.now() in assertions).
Runs against BOTH providers via the shared suite.

Boundary choice: period_end is EXCLUSIVE — at exactly period_end, access is DENIED.
Rationale: Apple's documented behaviour is "access until the end of the period",
and period_end is the instant the period ends. >= means "the period has ended".

Run:
    python3 tests/test_local136_apple_grace_period.py
"""

import sys
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from payment_provider import (
    SubscriptionTier,
    SubscriptionState,
    WebhookEvent,
)
from fake_payment_provider import (
    FakePaymentProvider,
    BILLING_RETRY_GRACE_DAYS,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: SHARED PROVIDER SUITE — grace period tests on both providers
# ═══════════════════════════════════════════════════════════════════════════════

PASS_COUNT = 0
FAIL_COUNT = 0


def record(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"  ✓ {name}")
    else:
        FAIL_COUNT += 1
        print(f"  ✗ {name}: {detail}")


# ─── Fake provider grace period tests ────────────────────────────────────────

def run_fake_grace_period_tests():
    """Grace period tests against FakePaymentProvider with controlled clock."""
    print("\n" + "=" * 70)
    print("  FAKE PROVIDER — Apple grace period tests")
    print("=" * 70 + "\n")

    # --- Test: cancelled at day 2, access on days 2..29 ---
    def test_cancelled_day2_access_continues():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        # Purchase PPU (period: day 1 to day 31)
        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        ent = provider.get_entitlement(uid)
        assert ent.state == SubscriptionState.ACTIVE
        period_end = ent.period_end

        # Cancel on day 2
        provider.advance_time(timedelta(days=1))
        provider.handle_webhook({"event_type": "cancellation", "user_id": uid})
        ent = provider.get_entitlement(uid)
        assert ent.state == SubscriptionState.CANCELLED, f"Expected CANCELLED, got {ent.state}"
        assert ent.tier == SubscriptionTier.PPU, "Tier should still be PPU"

        # Access on day 15 (mid-period, well before expiry)
        provider.set_time(start + timedelta(days=14))
        ent = provider.get_entitlement(uid)
        assert ent.state == SubscriptionState.CANCELLED
        assert ent.tier == SubscriptionTier.PPU
        record("cancelled_day2_access_day15", True)

        # Access on day 29 (last day before period_end)
        provider.set_time(period_end - timedelta(seconds=1))
        ent = provider.get_entitlement(uid)
        assert ent.state == SubscriptionState.CANCELLED
        assert ent.tier == SubscriptionTier.PPU
        record("cancelled_day2_access_day29", True)

    test_cancelled_day2_access_continues()

    # --- Test: cancelled, denied exactly at period_end ---
    def test_cancelled_denied_at_period_end():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        period_end = provider.get_entitlement(uid).period_end

        # Cancel
        provider.handle_webhook({"event_type": "cancellation", "user_id": uid})

        # At exactly period_end → LAPSED (our boundary: >= means expired)
        provider.set_time(period_end)
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("cancelled_denied_at_period_end", passed,
               f"state={ent.state}, expected LAPSED")

    test_cancelled_denied_at_period_end()

    # --- Test: cancelled, denied after period_end ---
    def test_cancelled_denied_after_period_end():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        period_end = provider.get_entitlement(uid).period_end

        provider.handle_webhook({"event_type": "cancellation", "user_id": uid})

        # 1 day after period_end
        provider.set_time(period_end + timedelta(days=1))
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("cancelled_denied_after_period_end", passed,
               f"state={ent.state}, expected LAPSED")

    test_cancelled_denied_after_period_end()

    # --- Test: billing retry within grace window → access continues ---
    def test_billing_retry_within_grace():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        period_end = provider.get_entitlement(uid).period_end

        # Billing retry on the last day of period
        provider.set_time(period_end - timedelta(days=1))
        provider.handle_webhook({"event_type": "billing_retry", "user_id": uid})
        ent = provider.get_entitlement(uid)
        assert ent.state == SubscriptionState.BILLING_RETRY

        # 5 days past period_end — still in 16-day grace window
        provider.set_time(period_end + timedelta(days=5))
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.BILLING_RETRY
        record("billing_retry_within_grace_5d", passed,
               f"state={ent.state}, expected BILLING_RETRY")

        # 15 days past period_end — still within 16-day window
        provider.set_time(period_end + timedelta(days=15))
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.BILLING_RETRY
        record("billing_retry_within_grace_15d", passed,
               f"state={ent.state}, expected BILLING_RETRY")

    test_billing_retry_within_grace()

    # --- Test: billing retry past grace window → lapsed ---
    def test_billing_retry_past_grace():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        period_end = provider.get_entitlement(uid).period_end

        provider.handle_webhook({"event_type": "billing_retry", "user_id": uid})

        # Exactly at grace end (period_end + 16 days)
        provider.set_time(period_end + timedelta(days=BILLING_RETRY_GRACE_DAYS))
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("billing_retry_at_grace_end_lapsed", passed,
               f"state={ent.state}, expected LAPSED")

    test_billing_retry_past_grace()

    # --- Test: active past period_end → lapsed ---
    def test_active_past_period_end_lapsed():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        period_end = provider.get_entitlement(uid).period_end

        # Don't cancel, don't renew — just let time pass
        provider.set_time(period_end)
        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("active_past_period_end_lapsed", passed,
               f"state={ent.state}, expected LAPSED")

    test_active_past_period_end_lapsed()

    # --- Test: refund after cancellation (wallet allows negative) ---
    def test_refund_after_cancellation():
        start = datetime(2026, 8, 1, 0, 0, 0)
        provider = FakePaymentProvider(now=start)
        uid = f"grace_fake_{uuid.uuid4().hex[:8]}"

        provider.purchase_subscription(uid, "com.audioura.ppu_monthly")
        # Use some credits
        for _ in range(25):
            provider.record_usage(uid, "tour_generation", 0.069)

        # Cancel
        provider.handle_webhook({"event_type": "cancellation", "user_id": uid})
        ent_before = provider.get_entitlement(uid)

        # Refund (clawback drives negative)
        provider.handle_webhook({
            "event_type": "refund", "user_id": uid, "refund_amount_usd": 10.0
        })
        ent_after = provider.get_entitlement(uid)
        # Balance should be negative (was ~$1.375, minus $10 = ~-$8.625)
        passed = ent_after.credit_balance_usd < 0
        record("refund_after_cancel_negative_balance", passed,
               f"balance={ent_after.credit_balance_usd}")

    test_refund_after_cancellation()


# ─── Real provider grace period tests ────────────────────────────────────────

def run_real_grace_period_tests():
    """Grace period tests against RevenueCatPaymentProvider with real DB."""
    from db_connection import check_db_available, get_database_url

    if not check_db_available():
        print("\n  ⚠ SKIPPING real provider grace tests — database unreachable")
        return

    print("\n" + "=" * 70)
    print("  REAL PROVIDER — Apple grace period tests")
    print("=" * 70 + "\n")

    db_url = get_database_url()
    import psycopg2
    from revenuecat_payment_provider import RevenueCatPaymentProvider

    provider = RevenueCatPaymentProvider(db_url=db_url)
    test_users = []

    def make_user():
        uid = f"grace_real_{uuid.uuid4().hex[:8]}"
        test_users.append(uid)
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (secret_id, plan)
                VALUES (%s, 'ppu')
                ON CONFLICT (secret_id) DO NOTHING
            """, (uid,))
        conn.commit()
        conn.close()
        return uid

    def cleanup():
        try:
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                for uid in test_users:
                    cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
                    cur.execute("DELETE FROM users WHERE secret_id = %s", (uid,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"  (cleanup: {e})")

    # --- Test: cancelled before period_end → tier retained ---
    def test_real_cancelled_not_expired():
        uid = make_user()
        now = datetime.now(timezone.utc)
        period_end = now + timedelta(days=25)

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                    credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'ppu', 'cancelled', %s, %s, 10.0, 0)
                ON CONFLICT (user_id) WHERE state IN ('active', 'billing_retry')
                DO UPDATE SET state = 'cancelled', period_end = EXCLUDED.period_end
            """, (uid, now - timedelta(days=5), period_end))
        conn.commit()
        conn.close()

        ent = provider.get_entitlement(uid)
        # Should still show PPU because period_end is in the future
        passed = (ent.tier == SubscriptionTier.PPU and
                  ent.state == SubscriptionState.CANCELLED)
        record("real_cancelled_not_expired_access", passed,
               f"tier={ent.tier}, state={ent.state}")

    test_real_cancelled_not_expired()

    # --- Test: cancelled after period_end → lapsed ---
    def test_real_cancelled_expired():
        uid = make_user()
        now = datetime.now(timezone.utc)
        period_end = now - timedelta(days=1)  # Already expired

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # Use direct insert to avoid ON CONFLICT issues
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                    credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'ppu', 'cancelled', %s, %s, 10.0, 0)
            """, (uid, now - timedelta(days=35), period_end))
        conn.commit()
        conn.close()

        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("real_cancelled_expired_lapsed", passed,
               f"state={ent.state}, expected LAPSED")

    test_real_cancelled_expired()

    # --- Test: billing_retry within grace → tier retained ---
    def test_real_billing_retry_in_grace():
        uid = make_user()
        now = datetime.now(timezone.utc)
        # period_end was 5 days ago, but within 16-day grace
        period_end = now - timedelta(days=5)

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                    credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'ppu', 'billing_retry', %s, %s, 10.0, 0)
            """, (uid, now - timedelta(days=35), period_end))
        conn.commit()
        conn.close()

        ent = provider.get_entitlement(uid)
        # 5 days past period_end, but within 16-day grace → still BILLING_RETRY
        passed = (ent.tier == SubscriptionTier.PPU and
                  ent.state == SubscriptionState.BILLING_RETRY)
        record("real_billing_retry_in_grace", passed,
               f"tier={ent.tier}, state={ent.state}")

    test_real_billing_retry_in_grace()

    # --- Test: billing_retry past grace → lapsed ---
    def test_real_billing_retry_past_grace():
        uid = make_user()
        now = datetime.now(timezone.utc)
        # period_end was 20 days ago (past 16-day grace)
        period_end = now - timedelta(days=20)

        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                    credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'ppu', 'billing_retry', %s, %s, 10.0, 0)
            """, (uid, now - timedelta(days=50), period_end))
        conn.commit()
        conn.close()

        ent = provider.get_entitlement(uid)
        passed = ent.state == SubscriptionState.LAPSED
        record("real_billing_retry_past_grace_lapsed", passed,
               f"state={ent.state}, expected LAPSED")

    test_real_billing_retry_past_grace()

    cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: ENTITLEMENT GATE TESTS — calls check_tour_quota (the actual gate)
# ═══════════════════════════════════════════════════════════════════════════════

def run_entitlement_gate_grace_tests():
    """Prove the gate returns allow/deny for cancelled-not-expired users.
    
    D35: Exercise the control, do not inspect it.
    We call check_tour_quota() — the same function the orchestrator calls.
    """
    from db_connection import check_db_available, get_db_config

    if not check_db_available():
        print("\n  ⚠ SKIPPING gate tests — database unreachable")
        return

    print("\n" + "=" * 70)
    print("  ENTITLEMENT GATE — grace period (calls check_tour_quota)")
    print("=" * 70 + "\n")

    import psycopg2
    cfg = get_db_config()
    os.environ["DB_HOST"] = cfg["host"]
    os.environ["DB_PORT"] = cfg["port"]
    os.environ["DB_NAME"] = cfg["dbname"]
    os.environ["DB_USER"] = cfg["user"]
    os.environ["DB_PASSWORD"] = cfg["password"]

    from entitlements import check_tour_quota

    test_users = []

    def get_conn():
        return psycopg2.connect(**cfg)

    def make_user(plan='ppu'):
        uid = f"gate136_{uuid.uuid4().hex[:8]}"
        test_users.append(uid)
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (secret_id, plan)
                VALUES (%s, %s)
                ON CONFLICT (secret_id) DO UPDATE SET plan = EXCLUDED.plan
            """, (uid, plan))
        conn.commit()
        conn.close()
        return uid

    def set_subscription(uid, tier, state, period_end, balance=10.0):
        conn = get_conn()
        with conn.cursor() as cur:
            now = datetime.now(timezone.utc)
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                    credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, %s, %s, %s, %s, %s, 0)
            """, (uid, tier, state, now - timedelta(days=5), period_end, balance))
            # Ensure wallet has balance for PPU
            if tier == 'ppu' and balance > 0:
                balance_cents = int(balance * 100)
                cur.execute("""
                    INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET balance_cents = %s
                """, (uid, balance_cents, balance_cents))
        conn.commit()
        conn.close()

    def cleanup():
        conn = get_conn()
        with conn.cursor() as cur:
            for uid in test_users:
                cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
                cur.execute("DELETE FROM users WHERE secret_id = %s", (uid,))
        conn.commit()
        conn.close()

    now = datetime.now(timezone.utc)

    # --- GATE TEST: cancelled, period_end in 25 days → ALLOWED ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'cancelled', now + timedelta(days=25))
    result = check_tour_quota(uid, 10)
    passed = result['allowed'] is True
    record("gate_cancelled_not_expired_ALLOWED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- GATE TEST: cancelled, period_end 1 second ago → DENIED ---
    uid2 = make_user('ppu')
    set_subscription(uid2, 'ppu', 'cancelled', now - timedelta(seconds=1))
    result = check_tour_quota(uid2, 10)
    passed = result['allowed'] is False
    record("gate_cancelled_expired_DENIED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- GATE TEST: billing_retry, 5 days past period_end → ALLOWED ---
    uid3 = make_user('ppu')
    set_subscription(uid3, 'ppu', 'billing_retry', now - timedelta(days=5))
    result = check_tour_quota(uid3, 10)
    passed = result['allowed'] is True
    record("gate_billing_retry_in_grace_ALLOWED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- GATE TEST: active, period_end in future → ALLOWED ---
    uid4 = make_user('ppu')
    set_subscription(uid4, 'ppu', 'active', now + timedelta(days=20))
    result = check_tour_quota(uid4, 10)
    passed = result['allowed'] is True
    record("gate_active_ALLOWED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- GATE TEST: lapsed → DENIED ---
    uid5 = make_user('ppu')
    set_subscription(uid5, 'ppu', 'lapsed', now - timedelta(days=5))
    result = check_tour_quota(uid5, 10)
    passed = result['allowed'] is False
    record("gate_lapsed_DENIED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- GATE TEST: unlimited cancelled but not expired → ALLOWED ---
    uid6 = make_user('unlimited')
    set_subscription(uid6, 'unlimited', 'cancelled', now + timedelta(days=20), balance=0)
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
            VALUES (%s, 'unlimited', %s, %s, 500, NOW())
            ON CONFLICT (user_id) DO UPDATE SET monthly_cost_spent_cents = 500
        """, (uid6, now - timedelta(days=5), now + timedelta(days=20)))
    conn.commit()
    conn.close()
    result = check_tour_quota(uid6, 10)
    passed = result['allowed'] is True
    record("gate_unlimited_cancelled_not_expired_ALLOWED", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    cleanup()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 70)
    print("  LOCAL-136: Apple Grace Period — Three States + Billing Retry")
    print("  Boundary: period_end is EXCLUSIVE (>= means expired)")
    print("  Source: Apple Developer 'Billing Grace Period' docs (16 days)")
    print("=" * 70)

    run_fake_grace_period_tests()
    run_real_grace_period_tests()
    run_entitlement_gate_grace_tests()

    print("\n" + "=" * 70)
    total = PASS_COUNT + FAIL_COUNT
    print(f"  RESULTS: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    print("=" * 70 + "\n")

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
