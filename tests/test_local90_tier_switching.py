#!/usr/bin/env python3
"""
LOCAL-90: Tier Switching End-to-End Test
=========================================
Proves that every remedy string the entitlement gate returns (`switch_to_ppu`,
`upgrade`, `topup`) can actually be acted upon.

The critical path:
  Unlimited user at cost-stop → refused → switch_to_ppu → SWITCH → generates.

Requirements:
    - PostgreSQL running (docker-compose, host port 5433)
    - Tests run directly against the DB (no HTTP needed for core logic)

Usage:
    python3 tests/test_local90_tier_switching.py
"""

import os
import sys
import uuid
import traceback
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# Ensure project root and tests/ are on the path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests"))

from db_connection import get_connection, get_db_config

# Set env vars so all billing modules use localhost:5433
_cfg = get_db_config()
os.environ["DB_HOST"] = _cfg["host"]
os.environ["DB_PORT"] = _cfg["port"]
os.environ["DB_NAME"] = _cfg["dbname"]
os.environ["DB_USER"] = _cfg["user"]
os.environ["DB_PASSWORD"] = _cfg["password"]

# Now import modules under test
import wallet_ledger
import entitlements
from tier_change import change_tier, VALID_TRANSITIONS
from fake_payment_provider import FakePaymentProvider
from payment_provider import SubscriptionTier

# Unique user ID per run
TEST_USER_PREFIX = f"tier_switch_e2e_{uuid.uuid4().hex[:8]}"
RESULTS = []
ALL_TEST_USERS = []


def log(msg):
    print(f"  {msg}")


def record(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"test": test_name, "status": status, "detail": detail})
    symbol = "✅" if passed else "❌"
    print(f"  {symbol} {test_name}" + (f" — {detail}" if detail else ""))


# ============================================================
# DATABASE HELPERS
# ============================================================

def create_test_user(suffix, plan="free"):
    """Create a test user and return their user_id."""
    user_id = f"{TEST_USER_PREFIX}_{suffix}"
    ALL_TEST_USERS.append(user_id)
    conn = get_connection()
    cur = conn.cursor()

    # Ensure tables
    cur.execute("""CREATE TABLE IF NOT EXISTS plans (
        plan_id VARCHAR(32) PRIMARY KEY, tours_per_day INTEGER NOT NULL DEFAULT 3,
        tour_max_poi INTEGER NOT NULL DEFAULT 10, tour_max_minutes INTEGER DEFAULT 60,
        news_per_period INTEGER DEFAULT 10, news_period VARCHAR(16) DEFAULT 'week',
        news_max_minutes INTEGER DEFAULT 10, downloads_unlimited BOOLEAN DEFAULT FALSE)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        secret_id VARCHAR(128) PRIMARY KEY, plan VARCHAR(32) NOT NULL DEFAULT 'free',
        tours_per_day_override INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY, user_id VARCHAR(128) NOT NULL, tier VARCHAR(32) NOT NULL,
        state VARCHAR(32) NOT NULL DEFAULT 'active',
        period_start TIMESTAMPTZ, period_end TIMESTAMPTZ,
        provider_subscription_id VARCHAR(255),
        credit_balance_usd NUMERIC(10,4) DEFAULT 0,
        cost_used_this_period_usd NUMERIC(10,4) DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS wallet_ledger (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id VARCHAR(128) NOT NULL,
        movement_type VARCHAR(64) NOT NULL, amount_cents INTEGER NOT NULL,
        balance_after_cents INTEGER NOT NULL, idempotency_key VARCHAR(256) NOT NULL,
        description TEXT, reference_id VARCHAR(256), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency ON wallet_ledger (idempotency_key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time ON wallet_ledger (user_id, created_at DESC)")
    cur.execute("""CREATE TABLE IF NOT EXISTS wallet_balance_cache (
        user_id VARCHAR(128) PRIMARY KEY, balance_cents INTEGER NOT NULL DEFAULT 0,
        last_ledger_id UUID, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS wallet_subscription (
        user_id VARCHAR(128) PRIMARY KEY, tier VARCHAR(32) NOT NULL DEFAULT 'free',
        period_start TIMESTAMPTZ, period_end TIMESTAMPTZ,
        monthly_cost_spent_cents INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    cur.execute("""CREATE TABLE IF NOT EXISTS tour_requests (
        id SERIAL PRIMARY KEY, secret_id VARCHAR(128), tour_id VARCHAR(128),
        status VARCHAR(32) DEFAULT 'started', started_at TIMESTAMPTZ DEFAULT NOW(),
        source VARCHAR(32) DEFAULT 'orchestrator')""")

    # Ensure plans
    cur.execute("INSERT INTO plans (plan_id, tours_per_day, tour_max_poi) VALUES ('free', 3, 10) ON CONFLICT DO NOTHING")
    cur.execute("INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, downloads_unlimited) VALUES ('ppu', 999, 50, TRUE) ON CONFLICT DO NOTHING")
    cur.execute("INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, downloads_unlimited) VALUES ('unlimited', 999, 50, TRUE) ON CONFLICT DO NOTHING")

    # Create user
    cur.execute(
        "INSERT INTO users (secret_id, plan) VALUES (%s, %s) ON CONFLICT (secret_id) DO UPDATE SET plan = %s",
        (user_id, plan, plan)
    )
    conn.commit()
    cur.close()
    conn.close()
    return user_id


def setup_subscription(user_id, tier):
    """Set up a user with an active subscription (for testing switches)."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    period_start = now
    period_end = now + timedelta(days=30)

    cur.execute("UPDATE users SET plan = %s WHERE secret_id = %s", (tier, user_id))
    cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (user_id,))
    cur.execute(
        """INSERT INTO subscriptions (user_id, tier, state, period_start, period_end, created_at, updated_at)
           VALUES (%s, %s, 'active', %s, %s, %s, %s)""",
        (user_id, tier, period_start, period_end, now, now)
    )
    cur.execute("""
        INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
        VALUES (%s, %s, %s, %s, 0, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            tier = EXCLUDED.tier, period_start = EXCLUDED.period_start,
            period_end = EXCLUDED.period_end, monthly_cost_spent_cents = 0,
            updated_at = EXCLUDED.updated_at""",
        (user_id, tier, period_start, period_end, now)
    )
    conn.commit()
    cur.close()
    conn.close()


def set_cost_stop_breached(user_id, cost_cents=2600):
    """Set a user's monthly_cost_spent above the $25 stop."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE wallet_subscription SET monthly_cost_spent_cents = %s WHERE user_id = %s",
        (cost_cents, user_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def give_balance(user_id, amount_usd):
    """Top up a user's wallet."""
    idem_key = f"test_topup:{user_id}:{uuid.uuid4().hex[:8]}"
    wallet_ledger.topup(user_id, Decimal(str(amount_usd)), idem_key)


def get_balance(user_id):
    return wallet_ledger.get_balance_cents(user_id) / 100.0


def get_user_tier_from_db(user_id):
    """Read tier from wallet_subscription (canonical)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tier FROM wallet_subscription WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else "free"


def get_user_plan_from_users(user_id):
    """Read plan from users table."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT plan FROM users WHERE secret_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


def cleanup():
    """Remove all test data."""
    conn = get_connection()
    cur = conn.cursor()
    for uid in ALL_TEST_USERS:
        cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (uid,))
        cur.execute("DELETE FROM users WHERE secret_id = %s", (uid,))
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# TESTS
# ============================================================

def test_free_to_ppu():
    """Free → PPU: new subscription with initial $10 credit."""
    log("--- Test: free → ppu ---")
    user_id = create_test_user("free_to_ppu")
    provider = FakePaymentProvider()

    result = change_tier(user_id, "ppu", provider=provider)

    tier_after = get_user_tier_from_db(user_id)
    plan_after = get_user_plan_from_users(user_id)
    balance = get_balance(user_id)

    ok = (
        result["success"] is True
        and result["previous_tier"] == "free"
        and result["new_tier"] == "ppu"
        and tier_after == "ppu"
        and plan_after == "ppu"
        and balance == 10.0  # initial $10 top-up
    )
    record("free → ppu", ok,
           f"tier={tier_after}, plan={plan_after}, balance=${balance:.2f}")
    return ok


def test_free_to_unlimited():
    """Free → Unlimited: new subscription, no balance needed."""
    log("--- Test: free → unlimited ---")
    user_id = create_test_user("free_to_unlim")
    provider = FakePaymentProvider()

    result = change_tier(user_id, "unlimited", provider=provider)

    tier_after = get_user_tier_from_db(user_id)
    plan_after = get_user_plan_from_users(user_id)

    ok = (
        result["success"] is True
        and result["previous_tier"] == "free"
        and result["new_tier"] == "unlimited"
        and tier_after == "unlimited"
        and plan_after == "unlimited"
    )
    record("free → unlimited", ok, f"tier={tier_after}, plan={plan_after}")
    return ok


def test_ppu_to_unlimited():
    """PPU → Unlimited: upgrade. Credits preserved (frozen)."""
    log("--- Test: ppu → unlimited ---")
    user_id = create_test_user("ppu_to_unlim")
    setup_subscription(user_id, "ppu")
    give_balance(user_id, 7.50)  # existing PPU balance
    provider = FakePaymentProvider()

    balance_before = get_balance(user_id)

    result = change_tier(user_id, "unlimited", provider=provider)

    tier_after = get_user_tier_from_db(user_id)
    balance_after = get_balance(user_id)

    # Balance is frozen (preserved) — credits don't disappear
    ok = (
        result["success"] is True
        and result["previous_tier"] == "ppu"
        and result["new_tier"] == "unlimited"
        and tier_after == "unlimited"
        and balance_after == balance_before  # credits preserved
    )
    record("ppu → unlimited", ok,
           f"tier={tier_after}, balance_before=${balance_before:.2f}, after=${balance_after:.2f}")
    return ok


def test_unlimited_to_ppu():
    """Unlimited → PPU: downgrade. No refund. Existing balance available."""
    log("--- Test: unlimited → ppu ---")
    user_id = create_test_user("unlim_to_ppu")
    setup_subscription(user_id, "unlimited")
    provider = FakePaymentProvider()

    result = change_tier(user_id, "ppu", provider=provider)

    tier_after = get_user_tier_from_db(user_id)
    plan_after = get_user_plan_from_users(user_id)

    ok = (
        result["success"] is True
        and result["previous_tier"] == "unlimited"
        and result["new_tier"] == "ppu"
        and tier_after == "ppu"
        and plan_after == "ppu"
    )
    record("unlimited → ppu", ok, f"tier={tier_after}, plan={plan_after}")
    return ok


def test_ppu_to_free():
    """PPU → Free: cancellation."""
    log("--- Test: ppu → free (cancel) ---")
    user_id = create_test_user("ppu_to_free")
    setup_subscription(user_id, "ppu")
    give_balance(user_id, 5.00)
    provider = FakePaymentProvider()

    result = change_tier(user_id, "free", provider=provider)

    plan_after = get_user_plan_from_users(user_id)
    # wallet_subscription row should be gone (free has none)
    tier_after = get_user_tier_from_db(user_id)

    ok = (
        result["success"] is True
        and result["previous_tier"] == "ppu"
        and result["new_tier"] == "free"
        and plan_after == "free"
        and tier_after == "free"
    )
    record("ppu → free (cancel)", ok, f"plan={plan_after}")
    return ok


def test_unlimited_to_free():
    """Unlimited → Free: cancellation."""
    log("--- Test: unlimited → free (cancel) ---")
    user_id = create_test_user("unlim_to_free")
    setup_subscription(user_id, "unlimited")
    provider = FakePaymentProvider()

    result = change_tier(user_id, "free", provider=provider)

    plan_after = get_user_plan_from_users(user_id)

    ok = (
        result["success"] is True
        and result["previous_tier"] == "unlimited"
        and result["new_tier"] == "free"
        and plan_after == "free"
    )
    record("unlimited → free (cancel)", ok, f"plan={plan_after}")
    return ok


def test_critical_path_cost_stop_switch_generate():
    """
    THE CRITICAL TEST: Unlimited user hits cost-stop, switches to PPU, generates.
    
    This closes the loop that the remedy string promises:
    1. User is on Unlimited, cost-stop reached → REFUSED, remedy=switch_to_ppu
    2. User performs the switch → now on PPU
    3. User tops up → has balance
    4. User generates → ALLOWED
    """
    log("--- CRITICAL PATH: cost-stop → switch → generate ---")
    user_id = create_test_user("critical_path")
    provider = FakePaymentProvider()

    # Set up as Unlimited with cost-stop breached
    setup_subscription(user_id, "unlimited")
    set_cost_stop_breached(user_id, 2600)  # $26.00 > $25.00 stop

    # 1. Verify: entitlement gate REFUSES and offers switch_to_ppu
    quota = entitlements.check_tour_quota(user_id, 10)
    refused = not quota["allowed"]
    remedy_is_switch = quota.get("remedy") == "switch_to_ppu"
    log(f"  Step 1: Refused={refused}, remedy={quota.get('remedy')}")

    if not refused or not remedy_is_switch:
        record("CRITICAL: cost-stop → switch → generate", False,
               f"Gate didn't refuse or wrong remedy: {quota}")
        return False

    # 2. Perform the switch to PPU
    switch_result = change_tier(user_id, "ppu", provider=provider)
    switched = switch_result["success"]
    new_tier = switch_result.get("new_tier")
    log(f"  Step 2: Switched={switched}, new_tier={new_tier}")

    if not switched or new_tier != "ppu":
        record("CRITICAL: cost-stop → switch → generate", False,
               f"Switch failed: {switch_result}")
        return False

    # 3. Top up (the switch gives initial $10 credit)
    balance_after_switch = get_balance(user_id)
    log(f"  Step 3: Balance after switch = ${balance_after_switch:.2f}")

    # If balance is $0 (because the initial topup was provider-only), manually top up
    if balance_after_switch <= 0:
        give_balance(user_id, 10.00)
        balance_after_switch = get_balance(user_id)
        log(f"  Step 3b: Topped up to ${balance_after_switch:.2f}")

    # 4. Verify: entitlement gate now ALLOWS
    quota2 = entitlements.check_tour_quota(user_id, 10)
    allowed = quota2["allowed"]
    log(f"  Step 4: Allowed={allowed}, plan={quota2.get('plan')}")

    ok = refused and remedy_is_switch and switched and new_tier == "ppu" and allowed
    record("CRITICAL: cost-stop → switch → generate", ok,
           f"refused→switch→allowed | balance=${balance_after_switch:.2f}")
    return ok


def test_no_op_same_tier():
    """Switching to your current tier is a no-op, not an error."""
    log("--- Test: no-op same tier ---")
    user_id = create_test_user("no_op")
    setup_subscription(user_id, "ppu")
    provider = FakePaymentProvider()

    result = change_tier(user_id, "ppu", provider=provider)

    ok = (
        result["success"] is True
        and result.get("details", {}).get("no_op") is True
    )
    record("no-op same tier", ok, f"msg={result.get('message', '')[:60]}")
    return ok


def test_invalid_transition():
    """Invalid transition rejected cleanly."""
    log("--- Test: invalid transition ---")
    user_id = create_test_user("invalid_trans")
    # User is free; free→free is a no-op, but let's test bad tier name
    provider = FakePaymentProvider()

    result = change_tier(user_id, "platinum", provider=provider)

    ok = result["success"] is False and "Invalid" in result.get("message", "")
    record("invalid tier name rejected", ok, f"msg={result.get('message', '')[:60]}")
    return ok


def test_fail_closed_db_error():
    """If DB sync fails after provider purchase, user is NOT on new tier.
    Simulates the partial failure path.
    """
    log("--- Test: fail-closed on DB error ---")
    user_id = create_test_user("fail_closed")
    provider = FakePaymentProvider()

    # The user is free. We'll test that even if the provider succeeds,
    # a DB failure doesn't leave them entitled.
    # We can't easily simulate a mid-transaction DB crash in a unit test,
    # so instead we verify the design: after a successful switch, the
    # DB state is consistent.
    
    # What we CAN verify: if we remove the user from the users table
    # (simulating a FK violation on the subscription insert), the
    # change_tier should return failure.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE secret_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

    # Try to change tier — should fail because user doesn't exist
    result = change_tier(user_id, "ppu", provider=provider)

    # The user may or may not exist in the provider, but the DB sync
    # should fail and report it
    # Re-create the user for cleanup
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (secret_id, plan) VALUES (%s, 'free') ON CONFLICT DO NOTHING",
        (user_id,),
    )
    conn.commit()
    cur.close()
    conn.close()

    # The failure could come from _get_current_tier or _sync_db_state
    ok = result["success"] is False
    record("fail-closed on DB error", ok,
           f"success={result['success']}, msg={result.get('message', '')[:60]}")
    return ok


def test_unlimited_cost_stop_resets_after_switch():
    """After switching from Unlimited to PPU, the cost-stop is irrelevant.
    The entitlement check should use balance, not cost-stop."""
    log("--- Test: cost-stop irrelevant after switch ---")
    user_id = create_test_user("cost_reset")
    provider = FakePaymentProvider()

    # Start as unlimited at cost stop
    setup_subscription(user_id, "unlimited")
    set_cost_stop_breached(user_id, 3000)  # $30 spent

    # Switch to PPU
    change_tier(user_id, "ppu", provider=provider)

    # Give balance
    give_balance(user_id, 10.00)

    # Check: should be allowed (balance-based, not cost-stop-based)
    quota = entitlements.check_tour_quota(user_id, 10)
    ok = quota["allowed"] is True
    record("cost-stop irrelevant after switch to PPU", ok,
           f"allowed={quota['allowed']}, plan={quota.get('plan')}")
    return ok


def test_free_upgrade_via_remedy():
    """Free user over quota gets remedy=upgrade. Performing upgrade unblocks them."""
    log("--- Test: free user upgrade remedy ---")
    user_id = create_test_user("free_upgrade")
    provider = FakePaymentProvider()

    # Find the actual tours_per_day for free plan
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT tours_per_day FROM plans WHERE plan_id = 'free'")
    tours_per_day = cur.fetchone()[0]
    # Exhaust free quota by creating tour_requests
    for i in range(tours_per_day):
        cur.execute(
            "INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source) VALUES (%s, %s, 'completed', NOW(), 'orchestrator')",
            (user_id, f"tour_{i}"),
        )
    conn.commit()
    cur.close()
    conn.close()
    log(f"  Created {tours_per_day} tour requests to exhaust quota")

    # 1. Entitlement gate refuses with remedy=upgrade
    quota = entitlements.check_tour_quota(user_id, 10)
    refused = not quota["allowed"]
    remedy_is_upgrade = quota.get("remedy") == "upgrade"
    log(f"  Step 1: Refused={refused}, remedy={quota.get('remedy')}")

    # 2. User upgrades to PPU
    result = change_tier(user_id, "ppu", provider=provider)
    switched = result["success"]

    # 3. Now allowed
    quota2 = entitlements.check_tour_quota(user_id, 10)
    allowed = quota2["allowed"]
    log(f"  Step 3: Allowed={allowed}")

    ok = refused and remedy_is_upgrade and switched and allowed
    record("free upgrade remedy closes the loop", ok,
           f"refused={refused}, upgraded={switched}, allowed={allowed}")
    return ok


def test_proration_unlimited_to_ppu():
    """Verify proration: Unlimited→PPU gives no credit for remaining days.
    No initial top-up either — that's a new-subscriber bonus only."""
    log("--- Test: proration Unlimited → PPU ---")
    user_id = create_test_user("proration_u2p")
    provider = FakePaymentProvider()

    setup_subscription(user_id, "unlimited")
    # User has been on Unlimited for 20 days (10 days remaining)
    # No balance expected after switch — user must top up themselves

    result = change_tier(user_id, "ppu", provider=provider)

    # Balance should be $0 — no proration credit, no initial top-up
    # (initial $10 top-up is only for free→ppu new subscribers)
    balance = get_balance(user_id)
    proration_detail = result.get("details", {}).get("proration", "")

    ok = (
        result["success"] is True
        and balance == 0.0  # no free credits on tier switch
        and "No refund" in proration_detail
    )
    record("proration: Unlimited→PPU, no refund, no free credit", ok,
           f"balance=${balance:.2f}, proration='{proration_detail[:50]}'")
    return ok


def test_proration_ppu_to_unlimited():
    """Verify proration: PPU→Unlimited preserves credits (non-refundable)."""
    log("--- Test: proration PPU → Unlimited ---")
    user_id = create_test_user("proration_p2u")
    provider = FakePaymentProvider()

    setup_subscription(user_id, "ppu")
    give_balance(user_id, 6.50)  # remaining PPU credits

    balance_before = get_balance(user_id)
    result = change_tier(user_id, "unlimited", provider=provider)

    balance_after = get_balance(user_id)
    proration_detail = result.get("details", {}).get("proration", "")

    # Credits are frozen, not lost
    ok = (
        result["success"] is True
        and balance_after == balance_before  # credits preserved
        and "non-refundable" in proration_detail
    )
    record("proration: PPU→Unlimited, credits frozen", ok,
           f"before=${balance_before:.2f}, after=${balance_after:.2f}")
    return ok


# ============================================================
# MAIN
# ============================================================

def print_results():
    print("\n" + "=" * 80)
    print(f"{'Test':<60} {'Status':<6}")
    print("-" * 80)
    for r in RESULTS:
        print(f"{r['test'][:59]:<60} {r['status']:<6}")
    print("=" * 80)
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    print(f"\nTotal: {total} | PASS: {passed} | FAIL: {failed}")
    return failed == 0


def main():
    print("=" * 70)
    print("LOCAL-90: Tier Switching End-to-End Test")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)

    # Pre-flight
    print("\n[Pre-flight]")
    try:
        conn = get_connection()
        conn.close()
        log("✅ Database reachable")
    except SystemExit:
        log("❌ Database unreachable — cannot proceed")
        return 7

    # Run tests
    print("\n[Tests]")
    all_passed = True
    try:
        if not test_free_to_ppu():
            all_passed = False
        if not test_free_to_unlimited():
            all_passed = False
        if not test_ppu_to_unlimited():
            all_passed = False
        if not test_unlimited_to_ppu():
            all_passed = False
        if not test_ppu_to_free():
            all_passed = False
        if not test_unlimited_to_free():
            all_passed = False
        if not test_critical_path_cost_stop_switch_generate():
            all_passed = False
        if not test_no_op_same_tier():
            all_passed = False
        if not test_invalid_transition():
            all_passed = False
        if not test_fail_closed_db_error():
            all_passed = False
        if not test_unlimited_cost_stop_resets_after_switch():
            all_passed = False
        if not test_free_upgrade_via_remedy():
            all_passed = False
        if not test_proration_unlimited_to_ppu():
            all_passed = False
        if not test_proration_ppu_to_unlimited():
            all_passed = False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        all_passed = False

    # Results
    all_passed = print_results()

    # Cleanup
    print("\n[Cleanup]")
    cleanup()
    log("Test data removed")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
