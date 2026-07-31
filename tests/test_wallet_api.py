"""
Test suite for Wallet API endpoints (LOCAL-68).
================================================
Tests the contract that LOCAL-62's Flutter app expects.

Runs against the live orchestrator service (port 5002) with a real PostgreSQL database.
Requires Docker services to be running:
    docker-compose up -d postgres-2 tour-orchestrator
"""

import json
import os
import sys
import time
import uuid
import requests
import psycopg2
from decimal import Decimal
from datetime import datetime, timezone

# Service URL
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:5002")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://admin:password123@localhost:5432/audiotours")


def get_db():
    """Get a database connection for test setup/teardown."""
    return psycopg2.connect(DATABASE_URL)


def setup_test_user(user_id: str, tier: str = "free"):
    """Set up a test user with wallet infrastructure."""
    conn = get_db()
    cur = conn.cursor()

    # Ensure tables exist (wallet_ledger module creates them on first use,
    # but we need wallet_subscription for tier info)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallet_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(128) NOT NULL,
            movement_type VARCHAR(64) NOT NULL,
            amount_cents INTEGER NOT NULL,
            balance_after_cents INTEGER NOT NULL,
            idempotency_key VARCHAR(256) NOT NULL,
            description TEXT,
            reference_id VARCHAR(256),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_idempotency
        ON wallet_ledger (idempotency_key)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user_time
        ON wallet_ledger (user_id, created_at DESC)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallet_balance_cache (
            user_id VARCHAR(128) PRIMARY KEY,
            balance_cents INTEGER NOT NULL DEFAULT 0,
            last_ledger_id UUID,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallet_subscription (
            user_id VARCHAR(128) PRIMARY KEY,
            tier VARCHAR(32) NOT NULL DEFAULT 'free',
            period_start TIMESTAMPTZ,
            period_end TIMESTAMPTZ,
            monthly_cost_spent_cents INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cost_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            operation_type VARCHAR(64) NOT NULL,
            user_id VARCHAR(128),
            our_cost_usd NUMERIC(12, 6) NOT NULL,
            cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
            job_id VARCHAR(128),
            breakdown JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cost_ledger_job
        ON cost_ledger (job_id)
    """)

    # Clean up any existing data for this test user
    cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (user_id,))

    # Set up subscription tier
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        period_end = period_start.replace(year=now.year + 1, month=1)
    else:
        period_end = period_start.replace(month=now.month + 1)

    cur.execute("""
        INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, tier, period_start, period_end, 0))

    conn.commit()
    cur.close()
    conn.close()


def seed_topup(user_id: str, amount_cents: int, key_suffix: str = ""):
    """Seed a top-up transaction."""
    conn = get_db()
    cur = conn.cursor()
    row_id = str(uuid.uuid4())
    idem_key = f"test_topup:{user_id}:{key_suffix or uuid.uuid4().hex[:8]}"

    # Get current balance
    cur.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s",
        (user_id,),
    )
    current = cur.fetchone()[0]
    new_balance = current + amount_cents

    cur.execute("""
        INSERT INTO wallet_ledger (id, user_id, movement_type, amount_cents, balance_after_cents,
                                   idempotency_key, description, created_at)
        VALUES (%s, %s, 'topup', %s, %s, %s, %s, %s)
    """, (row_id, user_id, amount_cents, new_balance, idem_key,
          f"Credit top-up: ${amount_cents/100:.2f}", datetime.now(timezone.utc)))

    # Update cache
    cur.execute("""
        INSERT INTO wallet_balance_cache (user_id, balance_cents, last_ledger_id, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            balance_cents = EXCLUDED.balance_cents,
            last_ledger_id = EXCLUDED.last_ledger_id,
            updated_at = EXCLUDED.updated_at
    """, (user_id, new_balance, row_id, datetime.now(timezone.utc)))

    conn.commit()
    cur.close()
    conn.close()
    return row_id


def seed_charge(user_id: str, amount_cents: int, description: str,
                cache_hit: bool = False, job_id: str = None):
    """Seed a charge transaction with matching cost_ledger entry."""
    conn = get_db()
    cur = conn.cursor()

    if job_id is None:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
    row_id = str(uuid.uuid4())
    idem_key = f"test_charge:{user_id}:{uuid.uuid4().hex[:8]}"

    # Get current balance
    cur.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s",
        (user_id,),
    )
    current = cur.fetchone()[0]
    new_balance = current - amount_cents

    cur.execute("""
        INSERT INTO wallet_ledger (id, user_id, movement_type, amount_cents, balance_after_cents,
                                   idempotency_key, description, reference_id, created_at)
        VALUES (%s, %s, 'charge', %s, %s, %s, %s, %s, %s)
    """, (row_id, user_id, -amount_cents, new_balance, idem_key,
          description, job_id, datetime.now(timezone.utc)))

    # Update cache
    cur.execute("""
        INSERT INTO wallet_balance_cache (user_id, balance_cents, last_ledger_id, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            balance_cents = EXCLUDED.balance_cents,
            last_ledger_id = EXCLUDED.last_ledger_id,
            updated_at = EXCLUDED.updated_at
    """, (user_id, new_balance, row_id, datetime.now(timezone.utc)))

    # Also seed cost_ledger for cache_hit flag lookup
    our_cost = 0.00 if cache_hit else (amount_cents / 100.0 / 5.0)  # reverse the ×5
    op_type = "tour_cache_hit" if cache_hit else "tour_generate"
    cur.execute("""
        INSERT INTO cost_ledger (id, operation_type, user_id, our_cost_usd, cache_hit, job_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (str(uuid.uuid4()), op_type, user_id, our_cost, cache_hit, job_id,
          datetime.now(timezone.utc)))

    conn.commit()
    cur.close()
    conn.close()
    return row_id


def seed_unlimited_cost(user_id: str, spent_cents: int):
    """Seed the unlimited cost-stop counter."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE wallet_subscription
        SET monthly_cost_spent_cents = %s
        WHERE user_id = %s
    """, (spent_cents, user_id))
    conn.commit()
    cur.close()
    conn.close()


# ============================================================
# TESTS
# ============================================================

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def record(self, name, passed, detail=""):
        self.results.append((name, passed, detail))
        if passed:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            print(f"  ✗ {name}: {detail}")


def test_wallet_free_user(results: TestResults):
    """Test GET /wallet for a free user."""
    user_id = f"test_free_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="free")

    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
    results.record("free_user_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("free_user_plan", data["plan"] == "free",
                   f"got plan={data.get('plan')}")
    results.record("free_user_balance_zero", data["balance_usd"] == 0.0,
                   f"got balance={data.get('balance_usd')}")
    results.record("free_user_cost_stop_null", data["cost_stop_progress"] is None,
                   f"got cost_stop={data.get('cost_stop_progress')}")
    results.record("free_user_low_balance_false", data["low_balance"] is False,
                   f"got low_balance={data.get('low_balance')}")
    results.record("free_user_has_period_start", "period_start" in data,
                   f"keys={list(data.keys())}")
    results.record("free_user_has_period_end", "period_end" in data,
                   f"keys={list(data.keys())}")


def test_wallet_ppu_user(results: TestResults):
    """Test GET /wallet for a pay-per-use user with balance."""
    user_id = f"test_ppu_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")
    seed_topup(user_id, 1000)  # $10.00
    seed_charge(user_id, 35, "Tour: French Riviera biking")  # $0.35

    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
    results.record("ppu_user_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("ppu_user_plan", data["plan"] == "ppu",
                   f"got plan={data.get('plan')}")
    results.record("ppu_user_balance", data["balance_usd"] == 9.65,
                   f"got balance={data.get('balance_usd')}")
    results.record("ppu_user_cost_stop_null", data["cost_stop_progress"] is None,
                   f"got cost_stop={data.get('cost_stop_progress')}")
    results.record("ppu_user_low_balance_false", data["low_balance"] is False,
                   f"got low_balance={data.get('low_balance')}")
    results.record("ppu_user_period_spend", data["period_spend_usd"] == 0.35,
                   f"got spend={data.get('period_spend_usd')}")


def test_wallet_ppu_low_balance(results: TestResults):
    """Test low_balance flag triggers when balance < $2.00."""
    user_id = f"test_ppu_low_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")
    seed_topup(user_id, 150)  # $1.50 (below $2 threshold)

    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
    results.record("ppu_low_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("ppu_low_balance_true", data["low_balance"] is True,
                   f"got low_balance={data.get('low_balance')}")
    results.record("ppu_low_balance_value", data["balance_usd"] == 1.50,
                   f"got balance={data.get('balance_usd')}")


def test_wallet_unlimited_user(results: TestResults):
    """Test GET /wallet for an unlimited user with cost-stop progress."""
    user_id = f"test_unlim_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="unlimited")
    seed_unlimited_cost(user_id, 1875)  # $18.75 spent of $25 limit

    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
    results.record("unlimited_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("unlimited_plan", data["plan"] == "unlimited",
                   f"got plan={data.get('plan')}")
    results.record("unlimited_cost_stop_populated",
                   data["cost_stop_progress"] is not None,
                   f"got cost_stop={data.get('cost_stop_progress')}")
    if data["cost_stop_progress"]:
        results.record("unlimited_used_usd",
                       data["cost_stop_progress"]["used_usd"] == 18.75,
                       f"got used={data['cost_stop_progress'].get('used_usd')}")
        results.record("unlimited_limit_usd",
                       data["cost_stop_progress"]["limit_usd"] == 25.0,
                       f"got limit={data['cost_stop_progress'].get('limit_usd')}")


def test_transactions(results: TestResults):
    """Test GET /wallet/<user_id>/transactions — contract compliance."""
    user_id = f"test_txn_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")
    seed_topup(user_id, 1000)
    seed_charge(user_id, 35, "Tour: French Riviera biking", cache_hit=False)
    seed_charge(user_id, 0, "Downloaded — no charge", cache_hit=True)

    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}/transactions?limit=50")
    results.record("txn_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("txn_is_list", isinstance(data, list),
                   f"got type={type(data).__name__}")
    results.record("txn_count", len(data) == 3,
                   f"got count={len(data)}")

    # Check field names match the contract
    if len(data) > 0:
        required_fields = {"id", "created_at", "operation_type", "description", "charged_usd", "cache_hit"}
        actual_fields = set(data[0].keys())
        results.record("txn_field_names", required_fields.issubset(actual_fields),
                       f"missing={required_fields - actual_fields}")

    # Find the cache-hit transaction
    cache_hit_txns = [t for t in data if t.get("cache_hit") is True]
    results.record("txn_cache_hit_exists", len(cache_hit_txns) >= 1,
                   f"found {len(cache_hit_txns)} cache_hit transactions")
    if cache_hit_txns:
        results.record("txn_cache_hit_zero_charge",
                       cache_hit_txns[0]["charged_usd"] == 0.0,
                       f"got charged={cache_hit_txns[0].get('charged_usd')}")


def test_plans_available(results: TestResults):
    """Test GET /plans/available — contract compliance."""
    r = requests.get(f"{ORCHESTRATOR_URL}/plans/available")
    results.record("plans_status_200", r.status_code == 200,
                   f"got {r.status_code}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("plans_is_list", isinstance(data, list),
                   f"got type={type(data).__name__}")
    results.record("plans_count_3", len(data) == 3,
                   f"got count={len(data)}")

    # Check field names
    if len(data) > 0:
        required_fields = {"plan_id", "display_name", "price_usd", "period", "features"}
        actual_fields = set(data[0].keys())
        results.record("plans_field_names", required_fields.issubset(actual_fields),
                       f"missing={required_fields - actual_fields}")

    # Verify plan_ids
    plan_ids = {p["plan_id"] for p in data}
    results.record("plans_has_free", "free" in plan_ids,
                   f"plan_ids={plan_ids}")
    results.record("plans_has_ppu", "ppu" in plan_ids,
                   f"plan_ids={plan_ids}")
    results.record("plans_has_unlimited", "unlimited" in plan_ids,
                   f"plan_ids={plan_ids}")

    # Verify prices come from config, not hardcoded (check they match env/default)
    ppu = next((p for p in data if p["plan_id"] == "ppu"), None)
    if ppu:
        results.record("plans_ppu_price", ppu["price_usd"] == 2.0,
                       f"got price={ppu.get('price_usd')}")
    unlimited = next((p for p in data if p["plan_id"] == "unlimited"), None)
    if unlimited:
        results.record("plans_unlimited_price", unlimited["price_usd"] == 50.0,
                       f"got price={unlimited.get('price_usd')}")


def test_topup_success(results: TestResults):
    """Test POST /wallet/<user_id>/topup — success case."""
    user_id = f"test_topup_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")
    seed_topup(user_id, 500)  # Start with $5.00

    product_id = f"purchase_{uuid.uuid4().hex[:12]}"
    r = requests.post(
        f"{ORCHESTRATOR_URL}/wallet/{user_id}/topup",
        json={"product_id": product_id},
    )
    results.record("topup_status_200", r.status_code == 200,
                   f"got {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        return

    data = r.json()
    results.record("topup_status_field", data["status"] == "success",
                   f"got status={data.get('status')}")
    results.record("topup_new_balance", data["new_balance_usd"] == 15.0,
                   f"got new_balance={data.get('new_balance_usd')}")


def test_topup_idempotent(results: TestResults):
    """Test POST /wallet/<user_id>/topup — same product_id twice credits once."""
    user_id = f"test_idem_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")

    product_id = f"idem_purchase_{uuid.uuid4().hex[:12]}"

    # First call
    r1 = requests.post(
        f"{ORCHESTRATOR_URL}/wallet/{user_id}/topup",
        json={"product_id": product_id},
    )
    results.record("idem_first_200", r1.status_code == 200,
                   f"got {r1.status_code}")

    # Second call — same product_id
    r2 = requests.post(
        f"{ORCHESTRATOR_URL}/wallet/{user_id}/topup",
        json={"product_id": product_id},
    )
    results.record("idem_second_200", r2.status_code == 200,
                   f"got {r2.status_code}")

    if r1.status_code == 200 and r2.status_code == 200:
        d1 = r1.json()
        d2 = r2.json()
        # Both should return the same balance (only credited once)
        results.record("idem_same_balance",
                       d1["new_balance_usd"] == d2["new_balance_usd"],
                       f"first={d1['new_balance_usd']}, second={d2['new_balance_usd']}")
        # Balance should be $10.00 (one top-up of $10 from zero)
        results.record("idem_balance_10",
                       d2["new_balance_usd"] == 10.0,
                       f"got {d2['new_balance_usd']} (expected 10.0)")


def test_topup_missing_product_id(results: TestResults):
    """Test POST /wallet/<user_id>/topup — missing product_id returns 400."""
    user_id = f"test_noprod_{uuid.uuid4().hex[:8]}"
    r = requests.post(
        f"{ORCHESTRATOR_URL}/wallet/{user_id}/topup",
        json={},
    )
    results.record("topup_no_product_400", r.status_code == 400,
                   f"got {r.status_code}")


def test_contract_field_names(results: TestResults):
    """Verify exact field names match the Flutter contract — the critical check."""
    user_id = f"test_contract_{uuid.uuid4().hex[:8]}"
    setup_test_user(user_id, tier="ppu")
    seed_topup(user_id, 745)
    seed_charge(user_id, 35, "Tour: Nice old town")

    # Wallet endpoint
    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
    wallet = r.json()
    wallet_contract = {"plan", "balance_usd", "period_spend_usd", "period_start",
                       "period_end", "cost_stop_progress", "low_balance"}
    results.record("contract_wallet_fields",
                   wallet_contract == set(wallet.keys()),
                   f"extra={set(wallet.keys()) - wallet_contract}, "
                   f"missing={wallet_contract - set(wallet.keys())}")

    # Transactions endpoint
    r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}/transactions")
    txns = r.json()
    if len(txns) > 0:
        txn_contract = {"id", "created_at", "operation_type", "description",
                        "charged_usd", "cache_hit"}
        results.record("contract_txn_fields",
                       txn_contract == set(txns[0].keys()),
                       f"extra={set(txns[0].keys()) - txn_contract}, "
                       f"missing={txn_contract - set(txns[0].keys())}")

    # Plans endpoint
    r = requests.get(f"{ORCHESTRATOR_URL}/plans/available")
    plans = r.json()
    if len(plans) > 0:
        plan_contract = {"plan_id", "display_name", "price_usd", "period", "features"}
        results.record("contract_plan_fields",
                       plan_contract == set(plans[0].keys()),
                       f"extra={set(plans[0].keys()) - plan_contract}, "
                       f"missing={plan_contract - set(plans[0].keys())}")


def test_plan_matches_users_table(results: TestResults):
    """D16 guard: API 'plan' value must equal users.plan in the database.

    This test asserts that the wallet_subscription.tier (which the API returns
    as 'plan') uses the same vocabulary as plans.plan_id — the canonical FK target.
    If this test fails, a vocabulary split has been re-introduced.
    """
    conn = get_db()
    cur = conn.cursor()

    # Ensure plans table has the canonical IDs
    cur.execute("SELECT plan_id FROM plans ORDER BY plan_id")
    db_plan_ids = {row[0] for row in cur.fetchall()}

    # Test for each tier: set up wallet_subscription, call API, compare
    for tier in ("free", "ppu", "unlimited"):
        user_id = f"test_d16_{tier}_{uuid.uuid4().hex[:8]}"
        setup_test_user(user_id, tier=tier)

        r = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}")
        if r.status_code == 200:
            api_plan = r.json()["plan"]
            # The API plan value must be a valid plans.plan_id
            results.record(
                f"d16_{tier}_plan_in_db",
                api_plan in db_plan_ids,
                f"API returned plan='{api_plan}' but valid plan_ids are {db_plan_ids}"
            )
            # The API plan must exactly match what we stored in wallet_subscription.tier
            results.record(
                f"d16_{tier}_plan_matches_tier",
                api_plan == tier,
                f"API returned plan='{api_plan}' but wallet_subscription.tier='{tier}'"
            )

    cur.close()
    conn.close()


# ============================================================
# RUNNER
# ============================================================

def main():
    print("=" * 60)
    print("LOCAL-68: Wallet API — Contract Test Suite")
    print("=" * 60)
    print(f"Target: {ORCHESTRATOR_URL}")
    print(f"Database: {DATABASE_URL}")
    print()

    # Wait for service to be ready
    print("Checking service health...")
    for attempt in range(10):
        try:
            r = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=3)
            if r.status_code == 200:
                print(f"  Service healthy (attempt {attempt + 1})")
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    else:
        print("  ERROR: Service not reachable after 20s")
        sys.exit(1)

    results = TestResults()
    print()

    print("--- GET /wallet/<user_id> ---")
    test_wallet_free_user(results)
    print()
    test_wallet_ppu_user(results)
    print()
    test_wallet_ppu_low_balance(results)
    print()
    test_wallet_unlimited_user(results)
    print()

    print("--- GET /wallet/<user_id>/transactions ---")
    test_transactions(results)
    print()

    print("--- GET /plans/available ---")
    test_plans_available(results)
    print()

    print("--- POST /wallet/<user_id>/topup ---")
    test_topup_success(results)
    print()
    test_topup_idempotent(results)
    print()
    test_topup_missing_product_id(results)
    print()

    print("--- CONTRACT FIELD NAMES ---")
    test_contract_field_names(results)
    print()

    print("--- D16: PLAN VOCABULARY GUARD ---")
    test_plan_matches_users_table(results)
    print()

    # Summary
    print("=" * 60)
    total = results.passed + results.failed
    print(f"Results: {results.passed}/{total} passed, {results.failed} failed")
    if results.failed == 0:
        print("ALL TESTS PASSED ✓")
    else:
        print("FAILURES:")
        for name, passed, detail in results.results:
            if not passed:
                print(f"  ✗ {name}: {detail}")
    print("=" * 60)

    return 0 if results.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
