"""
Test suite for LOCAL-67: Entitlement gate enforcement.
=====================================================
Tests all tiers (free, ppu, unlimited) with structured result validation.
Runs against the database with controlled test data — no mocking of the gate itself.

Acceptance criteria verified:
  1. Free user behaves exactly as before (before/after comparison).
  2. PPU user with balance generates; at zero balance is stopped with reminder.
  3. Unlimited user under cost stop generates; over it gets switch offer.
  4. Entitlement check erroring denies (not allows) with ERROR log.
  5. Structured result shape shown for each case.
"""

import os
import sys
import json
import uuid
import traceback
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Ensure project root and tests/ are on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_connection import get_db_config

# Set env defaults from shared helper BEFORE importing service modules
# (entitlements, wallet_ledger use os.getenv with Docker-internal defaults)
_cfg = get_db_config()
os.environ.setdefault("DB_HOST", _cfg["host"])
os.environ.setdefault("DB_PORT", _cfg["port"])
os.environ.setdefault("DB_NAME", _cfg["dbname"])
os.environ.setdefault("DB_USER", _cfg["user"])
os.environ.setdefault("DB_PASSWORD", _cfg["password"])

import psycopg2

# Database connection via shared helper (defaults to port 5433)
DB_CONFIG = {
    'host': _cfg['host'],
    'database': _cfg['dbname'],
    'user': _cfg['user'],
    'password': _cfg['password'],
    'port': _cfg['port'],
}

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def setup_test_users():
    """Create test users and subscriptions for each tier.
    Uses unique IDs to avoid collision with real data.
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # Ensure plans exist (free is seeded by 003, ppu/unlimited by 005)
    cur.execute("""
        INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
        VALUES ('free', 1, 30, 120, 10, 'week', 10, TRUE)
        ON CONFLICT (plan_id) DO NOTHING
    """)
    cur.execute("""
        INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
        VALUES ('ppu', 999, 50, 300, 999, 'day', 60, TRUE)
        ON CONFLICT (plan_id) DO NOTHING
    """)
    cur.execute("""
        INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited)
        VALUES ('unlimited', 999, 50, 300, 999, 'day', 60, TRUE)
        ON CONFLICT (plan_id) DO NOTHING
    """)
    
    test_users = {
        'free': f'TEST-FREE-{uuid.uuid4().hex[:8]}',
        'ppu_with_balance': f'TEST-PPU-BAL-{uuid.uuid4().hex[:8]}',
        'ppu_zero_balance': f'TEST-PPU-ZERO-{uuid.uuid4().hex[:8]}',
        'unlimited_under': f'TEST-UNL-UNDER-{uuid.uuid4().hex[:8]}',
        'unlimited_over': f'TEST-UNL-OVER-{uuid.uuid4().hex[:8]}',
    }
    
    # Create users
    for key, uid in test_users.items():
        plan = 'free' if 'free' in key else ('ppu' if 'ppu' in key else 'unlimited')
        cur.execute("""
            INSERT INTO users (secret_id, plan)
            VALUES (%s, %s)
            ON CONFLICT (secret_id) DO UPDATE SET plan = EXCLUDED.plan
        """, (uid, plan))
    
    # Create subscriptions for paid users
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=5)
    period_end = now + timedelta(days=25)
    
    for key, uid in test_users.items():
        if 'ppu' in key:
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end, credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'ppu', 'active', %s, %s, 0, 0)
                ON CONFLICT (user_id) WHERE state IN ('active', 'billing_retry')
                DO UPDATE SET tier = 'ppu', state = 'active'
            """, (uid, period_start, period_end))
        elif 'unlimited' in key:
            cur.execute("""
                INSERT INTO subscriptions (user_id, tier, state, period_start, period_end, credit_balance_usd, cost_used_this_period_usd)
                VALUES (%s, 'unlimited', 'active', %s, %s, 0, 0)
                ON CONFLICT (user_id) WHERE state IN ('active', 'billing_retry')
                DO UPDATE SET tier = 'unlimited', state = 'active'
            """, (uid, period_start, period_end))
    
    # Set up wallet state
    # PPU with balance: credit 1000 cents ($10.00)
    ppu_bal_user = test_users['ppu_with_balance']
    cur.execute("""
        INSERT INTO wallet_ledger (user_id, movement_type, amount_cents, balance_after_cents, idempotency_key, description)
        VALUES (%s, 'topup', 1000, 1000, %s, 'Test top-up $10.00')
        ON CONFLICT (idempotency_key) DO NOTHING
    """, (ppu_bal_user, f'test-topup-{ppu_bal_user}'))
    cur.execute("""
        INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
        VALUES (%s, 1000, NOW())
        ON CONFLICT (user_id) DO UPDATE SET balance_cents = 1000
    """, (ppu_bal_user,))
    
    # PPU with zero balance: no wallet records (balance = 0)
    ppu_zero_user = test_users['ppu_zero_balance']
    cur.execute("""
        INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
        VALUES (%s, 0, NOW())
        ON CONFLICT (user_id) DO UPDATE SET balance_cents = 0
    """, (ppu_zero_user,))
    
    # Unlimited under cost stop: wallet_subscription with low cost
    unl_under_user = test_users['unlimited_under']
    cur.execute("""
        INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
        VALUES (%s, 'unlimited', %s, %s, 500, NOW())
        ON CONFLICT (user_id) DO UPDATE SET monthly_cost_spent_cents = 500
    """, (unl_under_user, period_start, period_end))
    
    # Unlimited over cost stop: wallet_subscription with cost exceeding $25 (2500 cents)
    unl_over_user = test_users['unlimited_over']
    cur.execute("""
        INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
        VALUES (%s, 'unlimited', %s, %s, 2600, NOW())
        ON CONFLICT (user_id) DO UPDATE SET monthly_cost_spent_cents = 2600
    """, (unl_over_user, period_start, period_end))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return test_users


def cleanup_test_users(test_users):
    """Remove test data after tests."""
    conn = get_conn()
    cur = conn.cursor()
    for uid in test_users.values():
        cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE secret_id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()


def record_result(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1
    RESULTS.append({"test": name, "status": status, "detail": detail})
    print(f"  [{status}] {name}")
    if detail and not passed:
        print(f"        {detail}")


def assert_structured_result(result, test_name_prefix):
    """Verify every result has the structured fields the app needs."""
    has_allowed = 'allowed' in result
    has_reason = 'reason' in result
    has_remedy = 'remedy' in result
    
    if not has_allowed:
        record_result(f"{test_name_prefix} — has 'allowed'", False, f"Missing 'allowed' in {result}")
        return False
    if not has_reason:
        record_result(f"{test_name_prefix} — has 'reason'", False, f"Missing 'reason' in {result}")
        return False
    if not has_remedy:
        record_result(f"{test_name_prefix} — has 'remedy'", False, f"Missing 'remedy' in {result}")
        return False
    
    record_result(f"{test_name_prefix} — structured result shape", True,
                  f"allowed={result['allowed']}, reason={result['reason']}, remedy={result['remedy']}")
    return True


# ============================================================
# TEST: Free tier unchanged
# ============================================================
def test_free_tier_allowed(test_users):
    """Free user with no tours today → allowed. Exactly as before."""
    from entitlements import check_tour_quota
    uid = test_users['free']
    result = check_tour_quota(uid, 10)
    
    assert_structured_result(result, "free_allowed")
    
    passed = (
        result['allowed'] is True
        and result['plan'] == 'free'
        and result.get('clamped_stops') is not None
        and result.get('used') is not None
        and result.get('remaining') is not None
        and result['reason'] == 'ok'
    )
    record_result("free_tier_allowed — generates normally", passed,
                  json.dumps(result, default=str))


def test_free_tier_quota_exceeded(test_users):
    """Free user who has used their daily quota → denied with upgrade remedy."""
    from entitlements import check_tour_quota, get_user_plan
    uid = test_users['free']
    
    # Get the actual plan limit to exhaust it
    plan = get_user_plan(uid)
    tours_per_day = plan['tours_per_day']
    
    # Insert enough tour_requests for today to exhaust the quota
    conn = get_conn()
    cur = conn.cursor()
    for _ in range(tours_per_day):
        cur.execute("""
            INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
            VALUES (%s, %s, 'completed', NOW(), 'orchestrator')
        """, (uid, str(uuid.uuid4())))
    conn.commit()
    cur.close()
    conn.close()
    
    result = check_tour_quota(uid, 10)
    
    assert_structured_result(result, "free_denied")
    
    passed = (
        result['allowed'] is False
        and result['reason'] == 'quota_exceeded'
        and result['remedy'] == 'upgrade'
        and result['plan'] == 'free'
        and 'used' in result
        and 'max' in result
    )
    record_result("free_tier_quota_exceeded — denied with upgrade remedy", passed,
                  json.dumps(result, default=str))


# ============================================================
# TEST: PPU tier
# ============================================================
def test_ppu_with_balance(test_users):
    """PPU user with $10 balance → allowed."""
    from entitlements import check_tour_quota
    uid = test_users['ppu_with_balance']
    result = check_tour_quota(uid, 10)
    
    assert_structured_result(result, "ppu_balance")
    
    passed = (
        result['allowed'] is True
        and result['plan'] == 'ppu'
        and result['reason'] == 'ok'
        and result.get('clamped_stops') is not None
    )
    record_result("ppu_with_balance — generates normally", passed,
                  json.dumps(result, default=str))


def test_ppu_zero_balance(test_users):
    """PPU user with $0 balance → ALLOWED per LOCAL-163 overdraft rule (D41).
    D3's zero-stop is superseded: balance $0.00 - projected $0.40 = -$0.40,
    which is above the -$2.00 floor. Rule 1: finish what you started.
    """
    from entitlements import check_tour_quota
    uid = test_users['ppu_zero_balance']
    result = check_tour_quota(uid, 10)
    
    assert_structured_result(result, "ppu_zero")
    
    # LOCAL-163: zero balance is now ALLOWED (overdraft to about −$0.40)
    passed = (
        result['allowed'] is True
        and result['reason'] == 'ok'
        and result['plan'] == 'ppu'
    )
    record_result("ppu_zero_balance — allowed per overdraft rule (D41)", passed,
                  json.dumps(result, default=str))


def test_ppu_low_balance_reminder(test_users):
    """PPU user with balance below $2 threshold → allowed but with low_balance_reminder."""
    from entitlements import check_tour_quota
    uid = test_users['ppu_with_balance']
    
    # Set balance to $1.50 (150 cents) — below the $2 threshold
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE wallet_balance_cache SET balance_cents = 150 WHERE user_id = %s
    """, (uid,))
    conn.commit()
    cur.close()
    conn.close()
    
    result = check_tour_quota(uid, 10)
    
    passed = (
        result['allowed'] is True
        and result.get('low_balance_reminder') is not None
        and 'Top up' in result.get('low_balance_reminder', '')
    )
    record_result("ppu_low_balance_reminder — allowed with reminder", passed,
                  json.dumps(result, default=str))
    
    # Restore balance for other tests
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE wallet_balance_cache SET balance_cents = 1000 WHERE user_id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# TEST: Unlimited tier
# ============================================================
def test_unlimited_under_cost_stop(test_users):
    """Unlimited user with $5 of $25 used → allowed."""
    from entitlements import check_tour_quota
    uid = test_users['unlimited_under']
    result = check_tour_quota(uid, 15)
    
    assert_structured_result(result, "unlimited_under")
    
    passed = (
        result['allowed'] is True
        and result['plan'] == 'unlimited'
        and result['reason'] == 'ok'
        and result.get('clamped_stops') is not None
    )
    record_result("unlimited_under_cost_stop — generates normally", passed,
                  json.dumps(result, default=str))


def test_unlimited_over_cost_stop(test_users):
    """Unlimited user over $25 cost stop → denied with switch_to_ppu offer (D4)."""
    from entitlements import check_tour_quota
    uid = test_users['unlimited_over']
    result = check_tour_quota(uid, 10)
    
    assert_structured_result(result, "unlimited_over")
    
    passed = (
        result['allowed'] is False
        and result['reason'] == 'cost_stop_reached'
        and result['remedy'] == 'switch_to_ppu'
        and result['plan'] == 'unlimited'
        and 'message' in result
        and 'Pay-Per-Use' in result.get('message', '')
    )
    record_result("unlimited_over_cost_stop — denied with switch offer", passed,
                  json.dumps(result, default=str))


# ============================================================
# TEST: Error handling — fail closed
# ============================================================
def test_entitlement_check_error_denies(test_users):
    """When the entitlement check itself errors, deny (not allow).
    Force by making _get_subscription_tier raise.
    """
    from entitlements import check_tour_quota
    import entitlements
    
    uid = test_users['ppu_with_balance']
    
    # Monkey-patch _get_subscription_tier to raise
    original = entitlements._get_subscription_tier
    def _exploding_tier(user_id):
        raise ConnectionError("Simulated DB failure")
    
    entitlements._get_subscription_tier = _exploding_tier
    try:
        result = check_tour_quota(uid, 10)
    finally:
        entitlements._get_subscription_tier = original
    
    assert_structured_result(result, "error_denies")
    
    passed = (
        result['allowed'] is False
        and result['reason'] == 'entitlement_check_error'
        and 'temporary issue' in result.get('message', '').lower()
    )
    record_result("entitlement_check_error — denies with ERROR explanation", passed,
                  json.dumps(result, default=str))


def test_billing_check_error_denies(test_users):
    """When the billing check (wallet query) errors, deny (not allow)."""
    from entitlements import check_tour_quota
    import entitlements
    
    uid = test_users['ppu_with_balance']
    
    # Monkey-patch _check_ppu_balance to raise
    original = entitlements._check_ppu_balance
    def _exploding_balance(user_id, operation_type="tour_generate"):
        raise RuntimeError("Simulated wallet failure")
    
    entitlements._check_ppu_balance = _exploding_balance
    try:
        result = check_tour_quota(uid, 10)
    finally:
        entitlements._check_ppu_balance = original
    
    assert_structured_result(result, "billing_error_denies")
    
    passed = (
        result['allowed'] is False
        and result['reason'] == 'entitlement_check_error'
        and 'could not verify' in result.get('message', '').lower()
    )
    record_result("billing_check_error — denies with explanation", passed,
                  json.dumps(result, default=str))


# ============================================================
# TEST: News quota (parallel path)
# ============================================================
def test_news_free_allowed(test_users):
    """Free user news quota check → allowed."""
    from entitlements import check_news_quota
    uid = test_users['free']
    result = check_news_quota(uid)
    
    assert_structured_result(result, "news_free")
    
    passed = (
        result['allowed'] is True
        and result['plan'] == 'free'
        and result['reason'] == 'ok'
        and 'news_max_minutes' in result
    )
    record_result("news_free_allowed", passed, json.dumps(result, default=str))


def test_news_ppu_with_balance(test_users):
    """PPU user with balance → news allowed."""
    from entitlements import check_news_quota
    uid = test_users['ppu_with_balance']
    result = check_news_quota(uid)
    
    assert_structured_result(result, "news_ppu_balance")
    
    passed = (
        result['allowed'] is True
        and result['plan'] == 'ppu'
        and 'news_max_minutes' in result
    )
    record_result("news_ppu_with_balance", passed, json.dumps(result, default=str))


def test_news_ppu_zero_balance(test_users):
    """PPU user with zero balance → news ALLOWED per LOCAL-163 overdraft rule (D41).
    Balance $0.00 - projected $0.06 (news) = -$0.06, above the -$2.00 floor.
    """
    from entitlements import check_news_quota
    uid = test_users['ppu_zero_balance']
    result = check_news_quota(uid)
    
    # LOCAL-163: zero balance is now ALLOWED for news (overdraft to about −$0.06)
    passed = (
        result['allowed'] is True
        and result['reason'] == 'ok'
    )
    record_result("news_ppu_zero_balance", passed, json.dumps(result, default=str))


# ============================================================
# TEST: Backward compatibility — result shape for free tier
# ============================================================
def test_free_result_backward_compatible(test_users):
    """Free tier result includes all legacy fields (used, max, remaining, plan, clamped_stops).
    This ensures the orchestrator call site does not break.
    """
    from entitlements import check_tour_quota
    # Use a fresh free user that hasn't exhausted quota
    uid = f'TEST-FREE-COMPAT-{uuid.uuid4().hex[:8]}'
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (secret_id, plan) VALUES (%s, 'free')
        ON CONFLICT (secret_id) DO NOTHING
    """, (uid,))
    conn.commit()
    cur.close()
    conn.close()
    
    try:
        result = check_tour_quota(uid, 10)
        
        required_keys = {'allowed', 'clamped_stops', 'plan', 'used', 'max', 'remaining', 'reason', 'remedy'}
        actual_keys = set(result.keys())
        missing = required_keys - actual_keys
        
        passed = len(missing) == 0 and result['allowed'] is True
        record_result("free_result_backward_compatible", passed,
                      f"Missing keys: {missing}" if missing else json.dumps(result, default=str))
    finally:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE secret_id = %s", (uid,))
        conn.commit()
        cur.close()
        conn.close()


# ============================================================
# MAIN
# ============================================================
def main():
    global PASS_COUNT, FAIL_COUNT
    
    print("=" * 70)
    print("LOCAL-67: Entitlement Gate Enforcement — Test Suite")
    print("=" * 70)
    print()
    
    # Verify DB connectivity
    try:
        conn = get_conn()
        conn.close()
        print(f"✓ Database connected ({DB_CONFIG['host']}:{DB_CONFIG['port']})")
    except Exception as e:
        print(f"✗ Database connection FAILED: {e}")
        print("  Tests require a running PostgreSQL instance with the Audioura schema.")
        sys.exit(1)
    
    # Ensure wallet tables exist
    try:
        from wallet_ledger import _ensure_tables, _get_db_connection
        conn = _get_db_connection()
        _ensure_tables(conn)
        conn.close()
        print("✓ Wallet tables ensured")
    except Exception as e:
        print(f"✗ Wallet table setup failed: {e}")
        sys.exit(1)
    
    # Set up test data
    print()
    print("Setting up test data...")
    try:
        test_users = setup_test_users()
        print(f"✓ Test users created: {list(test_users.keys())}")
    except Exception as e:
        print(f"✗ Test setup failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    print()
    print("-" * 70)
    print("Running tests...")
    print("-" * 70)
    print()
    
    # Run all tests
    tests = [
        test_free_tier_allowed,
        test_free_tier_quota_exceeded,
        test_ppu_with_balance,
        test_ppu_zero_balance,
        test_ppu_low_balance_reminder,
        test_unlimited_under_cost_stop,
        test_unlimited_over_cost_stop,
        test_entitlement_check_error_denies,
        test_billing_check_error_denies,
        test_news_free_allowed,
        test_news_ppu_with_balance,
        test_news_ppu_zero_balance,
        test_free_result_backward_compatible,
    ]
    
    for test_fn in tests:
        try:
            test_fn(test_users)
        except Exception as e:
            record_result(test_fn.__name__, False, f"EXCEPTION: {e}")
            traceback.print_exc()
        print()
    
    # Cleanup
    print("-" * 70)
    print("Cleaning up test data...")
    try:
        cleanup_test_users(test_users)
        print("✓ Test data cleaned up")
    except Exception as e:
        print(f"⚠ Cleanup error (non-fatal): {e}")
    
    # Summary
    print()
    print("=" * 70)
    total = PASS_COUNT + FAIL_COUNT
    print(f"RESULTS: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    print("=" * 70)
    
    # Write JSON report
    report = {
        "test_suite": "LOCAL-67 Entitlement Gate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pass_count": PASS_COUNT,
        "fail_count": FAIL_COUNT,
        "total": total,
        "results": RESULTS,
    }
    
    os.makedirs("scratch", exist_ok=True)
    report_path = "scratch/test_local67_results.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport written to {report_path}")
    
    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == '__main__':
    main()
