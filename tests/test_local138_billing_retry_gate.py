#!/usr/bin/env python3
"""
LOCAL-138: Billing retry window bounded in the gate itself.

Proves the gate denies access for billing_retry rows stuck past the grace
window (period_end + 16 days), even when no webhook has arrived to transition
the state. The gate is self-sufficient — it must not depend on provider
webhooks for safety.

Boundary: period_end is EXCLUSIVE (consistent with cancelled state per LOCAL-136).
At exactly period_end + BILLING_RETRY_GRACE_DAYS, access is DENIED.

D35: Exercise the control, do not inspect it. All assertions call
check_tour_quota() — the same function the orchestrator calls.

Run:
    python3 tests/test_local138_billing_retry_gate.py
"""

import sys
import os
import uuid
import psycopg2
from datetime import datetime, timedelta, timezone

# Ensure project root and tests/ on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

from db_connection import check_db_available, get_db_config

if not check_db_available():
    print("DATABASE UNREACHABLE — cannot run tests")
    sys.exit(7)

# Set env for entitlements module BEFORE import
_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

from entitlements import check_tour_quota
from payment_provider import BILLING_RETRY_GRACE_DAYS

# ═══════════════════════════════════════════════════════════════════════════════
# TEST INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════════════════════

PASS_COUNT = 0
FAIL_COUNT = 0
DB_CONFIG = {
    'host': _cfg['host'],
    'database': _cfg['dbname'],
    'user': _cfg['user'],
    'password': _cfg['password'],
    'port': _cfg['port'],
}
test_users = []


def record(name, passed, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if passed:
        PASS_COUNT += 1
        print(f"  ✓ {name}")
    else:
        FAIL_COUNT += 1
        print(f"  ✗ {name}: {detail}")


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def make_user(plan='ppu'):
    """Create a test user with a unique UUID-based ID."""
    uid = f"gate138_{uuid.uuid4().hex[:8]}"
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
    """Insert a subscription row with controlled period_end for testing."""
    conn = get_conn()
    with conn.cursor() as cur:
        now = datetime.now(timezone.utc)
        cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
        cur.execute("""
            INSERT INTO subscriptions (user_id, tier, state, period_start, period_end,
                credit_balance_usd, cost_used_this_period_usd)
            VALUES (%s, %s, %s, %s, %s, %s, 0)
        """, (uid, tier, state, now - timedelta(days=60), period_end, balance))
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
    """Remove all test data by user_id. Never a bare DELETE FROM."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: BILLING RETRY GATE BOUNDARY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

def run_billing_retry_gate_tests():
    """Prove the gate bounds billing_retry by period_end + grace."""
    print("\n" + "=" * 70)
    print("  LOCAL-138: Billing retry window bounded in the gate")
    print(f"  BILLING_RETRY_GRACE_DAYS = {BILLING_RETRY_GRACE_DAYS}")
    print("  Boundary: period_end + grace is EXCLUSIVE (>= means expired)")
    print("=" * 70 + "\n")

    now = datetime.now(timezone.utc)

    # --- billing_retry, 5 days past period_end → ALLOW ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'billing_retry', now - timedelta(days=5))
    result = check_tour_quota(uid, 10)
    record("billing_retry_5d_past_ALLOW", result['allowed'] is True,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- billing_retry, 15 days past period_end → ALLOW ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'billing_retry', now - timedelta(days=15))
    result = check_tour_quota(uid, 10)
    record("billing_retry_15d_past_ALLOW", result['allowed'] is True,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- billing_retry, exactly 16 days past period_end → DENY ---
    # Boundary: at exactly grace end, access is DENIED (exclusive)
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'billing_retry', now - timedelta(days=BILLING_RETRY_GRACE_DAYS))
    result = check_tour_quota(uid, 10)
    record("billing_retry_16d_past_DENY", result['allowed'] is False,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- billing_retry, 400 days past period_end (the stuck row) → DENY ---
    # THIS IS THE BUG: without the fix, this row grants access forever
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'billing_retry', now - timedelta(days=400))
    result = check_tour_quota(uid, 10)
    record("billing_retry_400d_past_DENY_stuck_row", result['allowed'] is False,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- active → ALLOW (unchanged) ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'active', now + timedelta(days=20))
    result = check_tour_quota(uid, 10)
    record("active_ALLOW", result['allowed'] is True,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- cancelled before period_end → ALLOW (unchanged) ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'cancelled', now + timedelta(days=10))
    result = check_tour_quota(uid, 10)
    record("cancelled_before_period_end_ALLOW", result['allowed'] is True,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- cancelled after period_end → DENY (unchanged) ---
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'cancelled', now - timedelta(days=1))
    result = check_tour_quota(uid, 10)
    record("cancelled_after_period_end_DENY", result['allowed'] is False,
           f"allowed={result['allowed']}, reason={result.get('reason')}")

    # --- DB error → DENY (fail-closed, unchanged) ---
    import entitlements
    original_fn = entitlements._get_subscription_tier

    def _exploding_tier(user_id):
        raise ConnectionError("Simulated DB connection failure")

    uid_db_err = make_user('ppu')
    # Set an active subscription so the plan check routes to paid path
    set_subscription(uid_db_err, 'ppu', 'active', now + timedelta(days=20))
    entitlements._get_subscription_tier = _exploding_tier
    try:
        result = check_tour_quota(uid_db_err, 10)
    finally:
        entitlements._get_subscription_tier = original_fn
    passed = result['allowed'] is False
    record("db_error_DENY_fail_closed", passed,
           f"allowed={result['allowed']}, reason={result.get('reason')}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: BREAK-PROBE — neuter the interval clause, show 400-day flips
# ═══════════════════════════════════════════════════════════════════════════════

def run_break_probe():
    """Neuter the billing_retry interval clause, show the stuck row flips DENY → ALLOW."""
    print("\n" + "=" * 70)
    print("  BREAK-PROBE: Neutering billing_retry interval clause")
    print("=" * 70 + "\n")

    import entitlements
    import inspect

    # Read the source to confirm the bounded clause exists
    source = inspect.getsource(entitlements._get_subscription_tier)
    bounded_clause = "AND period_end + interval '%s days' > NOW()"
    replacement_count = source.count(bounded_clause)
    print(f"  Replacement count: {replacement_count}")

    if replacement_count == 0:
        record("break_probe_clause_found", False, "bounded clause not found in source")
        return

    record("break_probe_clause_found", True)

    # Build a neutered version of _get_subscription_tier that uses the OLD
    # unbounded query (billing_retry accepted unconditionally)
    _get_conn = entitlements._get_conn

    def _neutered_get_subscription_tier(user_id):
        """Break-probe: billing_retry has NO time bound (old behaviour)."""
        try:
            conn = _get_conn()
        except Exception as e:
            raise

        try:
            cur = conn.cursor()
            # NEUTERED: billing_retry accepted unconditionally (the old bug)
            cur.execute("""
                SELECT tier FROM subscriptions
                WHERE user_id = %s AND state IN ('active', 'billing_retry')
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            if row:
                cur.close()
                conn.close()
                return row[0]

            cur.execute("""
                SELECT tier FROM subscriptions
                WHERE user_id = %s AND state = 'cancelled' AND period_end > NOW()
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return row[0] if row else None
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            raise

    # Monkey-patch with neutered version
    original_fn = entitlements._get_subscription_tier
    entitlements._get_subscription_tier = _neutered_get_subscription_tier

    now = datetime.now(timezone.utc)

    # The 400-day stuck row should now flip from DENY → ALLOW
    uid = make_user('ppu')
    set_subscription(uid, 'ppu', 'billing_retry', now - timedelta(days=400))
    result = check_tour_quota(uid, 10)
    flipped = result['allowed'] is True
    record("break_probe_400d_flips_DENY_to_ALLOW", flipped,
           f"allowed={result['allowed']} (expected True when neutered)")

    # The 16-day case should also flip from DENY → ALLOW
    uid2 = make_user('ppu')
    set_subscription(uid2, 'ppu', 'billing_retry', now - timedelta(days=BILLING_RETRY_GRACE_DAYS))
    result = check_tour_quota(uid2, 10)
    flipped = result['allowed'] is True
    record("break_probe_16d_flips_DENY_to_ALLOW", flipped,
           f"allowed={result['allowed']} (expected True when neutered)")

    # Restore
    entitlements._get_subscription_tier = original_fn
    print("\n  ✓ Original _get_subscription_tier restored")

    # Verify restoration: 400-day case should DENY again
    uid3 = make_user('ppu')
    set_subscription(uid3, 'ppu', 'billing_retry', now - timedelta(days=400))
    result = check_tour_quota(uid3, 10)
    record("break_probe_restored_400d_DENY", result['allowed'] is False,
           f"allowed={result['allowed']} (expected False after restore)")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        run_billing_retry_gate_tests()
        run_break_probe()
    finally:
        cleanup()

    print("\n" + "=" * 70)
    total = PASS_COUNT + FAIL_COUNT
    print(f"  RESULTS: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")
    print("=" * 70 + "\n")

    sys.exit(0 if FAIL_COUNT == 0 else 1)


if __name__ == "__main__":
    main()
