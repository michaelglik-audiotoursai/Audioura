#!/usr/bin/env python3
"""
LOCAL-84 · End-to-end HTTP charging proof
==========================================

PURPOSE: Prove that a real HTTP tour generation request through the orchestrator
actually debits a real wallet. This is the "last inch" that LOCAL-83 explicitly
left unproven.

WHAT THIS DOES:
  1. Creates a PPU test user with a known balance ($5.00)
  2. POSTs a real tour generation request to the orchestrator (port 5002)
  3. Polls to completion (real generation, real API credits consumed)
  4. Asserts against the database:
     - cost_ledger row with real cost, cache_hit=false
     - wallet_ledger charge of exactly cost × 5
     - balance decreased by exactly that amount
     - GET /wallet/<user> reports the same balance
     - transaction description is human-readable
  5. POSTs the same request again — asserts cache hit: $0.00, balance unchanged
  6. Repeats for an unlimited user — monthly_cost_spent_cents rose, no wallet charge

BUDGET: Max 3 generations (ppu fresh, ppu cached, unlimited). Ceiling $1.30/tour.
"""

import os
import sys
import time
import uuid
import json
import requests
from decimal import Decimal, ROUND_HALF_EVEN

# ─── Path setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from db_connection import get_connection, check_db_available

# ─── Configuration ───────────────────────────────────────────────────────────
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:5002")
POLL_INTERVAL = 5  # seconds between status polls
POLL_TIMEOUT = 300  # max seconds to wait for generation (5 minutes)
PRICING_MULTIPLIER = Decimal(os.getenv("PRICING_MULTIPLIER", "5.0"))
COST_CEILING = Decimal("1.30")  # Michael's ceiling per tour

# Test user identifiers (unique per run to avoid collisions)
RUN_ID = uuid.uuid4().hex[:8]
PPU_USER = f"local84-ppu-{RUN_ID}"
UNLIMITED_USER = f"local84-unlimited-{RUN_ID}"

# Tour request parameters — small, cheap, deterministic
# Use a niche location unlikely to be in cache. The cache is keyed on
# (location, tour_type, total_stops), so even if the area was generated
# before with different params, this specific combo should miss.
TOUR_LOCATION = "Larz Anderson Park, Brookline MA"
TOUR_TYPE = "nature"
TOUR_STOPS = 5  # Fewer stops = cheaper + faster
# For cache hit test, we use the SAME params as the first request
# The tour cache is keyed on (location, tour_type, total_stops)

# Unlimited user needs a DIFFERENT location to avoid hitting the cache
# populated by the PPU user's generation
UNLIMITED_TOUR_LOCATION = "Arnold Arboretum, Jamaica Plain, Boston MA"
UNLIMITED_TOUR_TYPE = "nature"
UNLIMITED_TOUR_STOPS = 5

# ─── Results tracking ────────────────────────────────────────────────────────
RESULTS = []
EVIDENCE = []


def check(name, passed, detail=""):
    """Record a test assertion."""
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def evidence(label, data):
    """Record evidence for submission."""
    EVIDENCE.append({"label": label, "data": data})
    print(f"  [EVIDENCE] {label}: {data}")


# ─── Database helpers ────────────────────────────────────────────────────────
def setup_ppu_user(user_id, balance_cents=500):
    """Create a PPU user with known balance. Returns initial balance in cents."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Insert into users table
        cur.execute("""
            INSERT INTO users (secret_id, plan, created_at, updated_at)
            VALUES (%s, 'ppu', NOW(), NOW())
            ON CONFLICT (secret_id) DO UPDATE SET plan = 'ppu', updated_at = NOW()
        """, (user_id,))

        # Insert subscription (active state)
        cur.execute("""
            INSERT INTO subscriptions (user_id, tier, state, period_start, period_end, created_at, updated_at)
            VALUES (%s, 'ppu', 'active', NOW(), NOW() + INTERVAL '30 days', NOW(), NOW())
            ON CONFLICT DO NOTHING
        """, (user_id,))

        # Insert wallet_subscription
        cur.execute("""
            INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
            VALUES (%s, 'ppu', NOW(), NOW() + INTERVAL '30 days', 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET tier = 'ppu', monthly_cost_spent_cents = 0, updated_at = NOW()
        """, (user_id,))

        # Seed wallet with initial topup via wallet_ledger
        cur.execute("""
            INSERT INTO wallet_ledger (user_id, movement_type, amount_cents, balance_after_cents, idempotency_key, description, created_at)
            VALUES (%s, 'topup', %s, %s, %s, 'Initial test balance', NOW())
        """, (user_id, balance_cents, balance_cents, f"setup:{user_id}:{RUN_ID}"))

        # Update balance cache
        cur.execute("""
            INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET balance_cents = %s, updated_at = NOW()
        """, (user_id, balance_cents, balance_cents))

        conn.commit()
        return balance_cents
    finally:
        cur.close()
        conn.close()


def setup_unlimited_user(user_id):
    """Create an unlimited user. Returns initial monthly_cost_spent_cents (0)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (secret_id, plan, created_at, updated_at)
            VALUES (%s, 'unlimited', NOW(), NOW())
            ON CONFLICT (secret_id) DO UPDATE SET plan = 'unlimited', updated_at = NOW()
        """, (user_id,))

        cur.execute("""
            INSERT INTO subscriptions (user_id, tier, state, period_start, period_end, created_at, updated_at)
            VALUES (%s, 'unlimited', 'active', NOW(), NOW() + INTERVAL '30 days', NOW(), NOW())
            ON CONFLICT DO NOTHING
        """, (user_id,))

        cur.execute("""
            INSERT INTO wallet_subscription (user_id, tier, period_start, period_end, monthly_cost_spent_cents, updated_at)
            VALUES (%s, 'unlimited', NOW(), NOW() + INTERVAL '30 days', 0, NOW())
            ON CONFLICT (user_id) DO UPDATE SET tier = 'unlimited', monthly_cost_spent_cents = 0, updated_at = NOW()
        """, (user_id,))

        conn.commit()
        return 0
    finally:
        cur.close()
        conn.close()


def get_balance_cents(user_id):
    """Read balance directly from DB."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT balance_cents FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        # Fallback: sum ledger
        cur.execute("SELECT COALESCE(SUM(amount_cents), 0) FROM wallet_ledger WHERE user_id = %s", (user_id,))
        return cur.fetchone()[0]
    finally:
        cur.close()
        conn.close()


def get_cost_ledger_row(user_id, job_id):
    """Get cost_ledger row for a user's most recent generation.
    
    NOTE: The orchestrator and tour-generator use different job_ids.
    The orchestrator returns its own job_id to the client, but the
    tour-generator records its internal job_id in cost_ledger.
    We look up by user_id + most recent row (within last 5 minutes).
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # First try exact job_id match (orchestrator and generator may share it)
        cur.execute("""
            SELECT id, operation_type, our_cost_usd, cache_hit, job_id, description
            FROM cost_ledger
            WHERE user_id = %s AND job_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, job_id))
        row = cur.fetchone()
        if not row:
            # Fallback: most recent row for this user within last 5 minutes
            cur.execute("""
                SELECT id, operation_type, our_cost_usd, cache_hit, job_id, description
                FROM cost_ledger
                WHERE user_id = %s AND created_at > NOW() - INTERVAL '5 minutes'
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
        if row:
            return {
                "id": str(row[0]), "operation_type": row[1],
                "our_cost_usd": row[2], "cache_hit": row[3],
                "job_id": row[4], "description": row[5]
            }
        return None
    finally:
        cur.close()
        conn.close()


def get_wallet_ledger_charge(user_id, job_id):
    """Get the wallet_ledger charge row for a job.
    
    NOTE: The idempotency key uses the tour-generator's internal job_id,
    not the orchestrator's job_id. We first try exact match, then fall back
    to most recent charge for this user within the last 5 minutes.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # First try exact idempotency key match
        idem_key = f"charge:{user_id}:{job_id}"
        cur.execute("""
            SELECT id, movement_type, amount_cents, balance_after_cents, idempotency_key, description
            FROM wallet_ledger
            WHERE user_id = %s AND idempotency_key = %s
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, idem_key))
        row = cur.fetchone()
        if not row:
            # Fallback: most recent charge for this user within last 5 minutes
            cur.execute("""
                SELECT id, movement_type, amount_cents, balance_after_cents, idempotency_key, description
                FROM wallet_ledger
                WHERE user_id = %s AND movement_type = 'charge' AND created_at > NOW() - INTERVAL '5 minutes'
                ORDER BY created_at DESC LIMIT 1
            """, (user_id,))
            row = cur.fetchone()
        if row:
            return {
                "id": row[0], "movement_type": row[1],
                "amount_cents": row[2], "balance_after_cents": row[3],
                "idempotency_key": row[4], "description": row[5]
            }
        return None
    finally:
        cur.close()
        conn.close()


def get_monthly_cost_spent_cents(user_id):
    """Get monthly_cost_spent_cents for unlimited user."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT monthly_cost_spent_cents FROM wallet_subscription WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0
    finally:
        cur.close()
        conn.close()


def cleanup_test_users():
    """Remove all test data for our test users."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        for user_id in [PPU_USER, UNLIMITED_USER]:
            # Delete in FK-safe order (tour_requests references users)
            cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (user_id,))
            cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM cost_ledger WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE secret_id = %s", (user_id,))
        conn.commit()
        print(f"\n  [CLEANUP] Removed test data for {PPU_USER} and {UNLIMITED_USER}")
    except Exception as e:
        print(f"\n  [CLEANUP WARNING] {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


# ─── HTTP helpers ────────────────────────────────────────────────────────────
def post_generate_tour(user_id, location=TOUR_LOCATION, tour_type=TOUR_TYPE, stops=TOUR_STOPS):
    """POST a tour generation request. Returns (job_id, response_dict) or raises."""
    payload = {
        "location": location,
        "tour_type": tour_type,
        "total_stops": stops,
        "user_id": user_id,
        "language": "en"
    }
    resp = requests.post(
        f"{ORCHESTRATOR_URL}/generate-complete-tour",
        json=payload,
        timeout=30
    )
    data = resp.json()
    evidence(f"POST /generate-complete-tour (user={user_id})",
             f"status={resp.status_code} body={json.dumps(data)}")
    if resp.status_code != 200:
        return None, data, resp.status_code
    return data.get("job_id"), data, resp.status_code


def poll_until_complete(job_id, timeout=POLL_TIMEOUT):
    """Poll /status/<job_id> until completed or failed. Returns final status dict."""
    start = time.time()
    last_status = None
    while time.time() - start < timeout:
        resp = requests.get(f"{ORCHESTRATOR_URL}/status/{job_id}", timeout=15)
        data = resp.json()
        status = data.get("status", "unknown")
        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"    [{elapsed}s] Job {job_id}: {status}")
            last_status = status
        if status in ("completed", "complete"):
            evidence(f"Poll final (job={job_id})", f"status={status} after {int(time.time()-start)}s")
            return data
        if status in ("failed", "error"):
            evidence(f"Poll FAILED (job={job_id})", f"status={status} error={data.get('error')}")
            return data
        time.sleep(POLL_INTERVAL)
    evidence(f"Poll TIMEOUT (job={job_id})", f"Timed out after {timeout}s, last_status={last_status}")
    return {"status": "timeout", "error": f"Timed out after {timeout}s"}


def get_wallet_api(user_id):
    """GET /wallet/<user_id> from the orchestrator API."""
    resp = requests.get(f"{ORCHESTRATOR_URL}/wallet/{user_id}", timeout=10)
    return resp.json()


# ─── TESTS ───────────────────────────────────────────────────────────────────
def test_ppu_fresh_generation():
    """
    Test 1: PPU user — fresh tour generation debits wallet.
    The money shot: does a real HTTP request produce a real wallet charge?
    """
    print("\n" + "=" * 70)
    print("TEST 1: PPU fresh generation — wallet must be debited")
    print("=" * 70)

    # Setup: PPU user with $5.00 balance
    initial_balance = setup_ppu_user(PPU_USER, balance_cents=500)
    evidence("PPU initial balance", f"{initial_balance} cents (${initial_balance/100:.2f})")

    # Verify via wallet API
    wallet_before = get_wallet_api(PPU_USER)
    evidence("GET /wallet before", json.dumps(wallet_before))
    check("wallet API shows initial balance",
          abs(float(wallet_before.get("balance_usd", 0)) - 5.00) < 0.01,
          f"balance_usd={wallet_before.get('balance_usd')}")

    # POST tour generation
    print("\n  Posting tour generation request...")
    job_id, post_resp, status_code = post_generate_tour(PPU_USER)
    check("POST /generate-complete-tour returns 200",
          status_code == 200,
          f"status_code={status_code}, job_id={job_id}")

    if not job_id:
        check("ABORT: no job_id returned", False, f"Response: {post_resp}")
        return None

    # Poll to completion
    print(f"\n  Polling job {job_id} (this will take 1-3 minutes)...")
    final = poll_until_complete(job_id)
    final_status = final.get("status", "unknown")
    check("Tour generation completed",
          final_status in ("completed", "complete"),
          f"final_status={final_status}")

    if final_status not in ("completed", "complete"):
        check("ABORT: generation did not complete", False, f"Final: {json.dumps(final)}")
        return None

    # ─── Database assertions ─────────────────────────────────────────────
    print("\n  Checking database assertions...")

    # 4a. cost_ledger row
    cost_row = get_cost_ledger_row(PPU_USER, job_id)
    check("cost_ledger row exists", cost_row is not None,
          f"row={cost_row}")
    if not cost_row:
        check("ABORT: no cost_ledger row", False)
        return None

    our_cost = Decimal(str(cost_row["our_cost_usd"]))
    check("cost_ledger cache_hit=false", cost_row["cache_hit"] is False,
          f"cache_hit={cost_row['cache_hit']}")
    check("cost_ledger our_cost under ceiling",
          our_cost <= COST_CEILING,
          f"our_cost=${our_cost} (ceiling=${COST_CEILING})")
    evidence("Actual generation cost", f"${our_cost}")

    # 4b. wallet_ledger charge = cost × 5
    expected_charge_usd = (our_cost * PRICING_MULTIPLIER).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    expected_charge_cents = int(expected_charge_usd * 100)

    wallet_charge = get_wallet_ledger_charge(PPU_USER, job_id)
    check("wallet_ledger charge row exists", wallet_charge is not None,
          f"row={wallet_charge}")
    if not wallet_charge:
        # THIS IS THE GAP — if we get here, the HTTP flow does NOT debit the wallet
        evidence("CRITICAL FINDING", "Real HTTP request did NOT produce a wallet charge")
        check("FINDING: HTTP request does not debit wallet", False,
              "The charging wire does not fire during real HTTP tour generation")
        return None

    actual_charge_cents = abs(wallet_charge["amount_cents"])  # charges are negative
    check("wallet_ledger charge = cost × 5",
          actual_charge_cents == expected_charge_cents,
          f"actual={actual_charge_cents}¢ expected={expected_charge_cents}¢ "
          f"(cost=${our_cost} × {PRICING_MULTIPLIER} = ${expected_charge_usd})")

    # 4c. Balance decreased by exactly the charge amount
    balance_after = get_balance_cents(PPU_USER)
    expected_balance = initial_balance - expected_charge_cents
    check("balance decreased by charge amount",
          balance_after == expected_balance,
          f"balance_after={balance_after}¢ expected={expected_balance}¢ "
          f"(started={initial_balance}¢ - charge={expected_charge_cents}¢)")

    # 4d. GET /wallet/<user> reports same balance
    wallet_after = get_wallet_api(PPU_USER)
    wallet_api_balance_cents = int(round(float(wallet_after.get("balance_usd", 0)) * 100))
    check("GET /wallet reports correct balance",
          wallet_api_balance_cents == balance_after,
          f"API={wallet_api_balance_cents}¢ DB={balance_after}¢")
    evidence("GET /wallet after charge", json.dumps(wallet_after))

    # 4e. Description is human-readable
    desc = wallet_charge.get("description", "")
    check("transaction description is human-readable",
          len(desc) > 5 and any(c.isalpha() for c in desc),
          f"description='{desc}'")
    evidence("Charge description", desc)

    return {
        "job_id": job_id,
        "our_cost": our_cost,
        "charge_cents": expected_charge_cents,
        "balance_after": balance_after
    }


def test_ppu_cache_hit():
    """
    Test 2: Same request again — cache hit, $0.00, balance unchanged.
    """
    print("\n" + "=" * 70)
    print("TEST 2: PPU cache hit — balance must not change by a single cent")
    print("=" * 70)

    balance_before = get_balance_cents(PPU_USER)
    evidence("PPU balance before cache-hit request", f"{balance_before}¢")

    # POST the SAME tour request
    print("\n  Posting same request (expecting cache hit)...")
    job_id, post_resp, status_code = post_generate_tour(PPU_USER)
    check("POST returns 200 for cached request",
          status_code == 200,
          f"status_code={status_code}, job_id={job_id}")

    if not job_id:
        check("ABORT: no job_id for cache test", False, f"Response: {post_resp}")
        return

    # Poll to completion (should be fast if cached)
    print(f"  Polling job {job_id} (should be fast if cached)...")
    final = poll_until_complete(job_id)
    final_status = final.get("status", "unknown")
    check("Cached tour generation completed",
          final_status in ("completed", "complete"),
          f"final_status={final_status}")

    if final_status not in ("completed", "complete"):
        check("ABORT: cached generation did not complete", False, f"Final: {json.dumps(final)}")
        return

    # Check cost_ledger: cache_hit should be true
    cost_row = get_cost_ledger_row(PPU_USER, job_id)
    if cost_row:
        check("cost_ledger shows cache_hit=true",
              cost_row["cache_hit"] is True,
              f"cache_hit={cost_row['cache_hit']}, cost=${cost_row['our_cost_usd']}")
        evidence("Cache hit cost_ledger row", json.dumps(cost_row, default=str))
    else:
        # Some implementations skip cost_ledger on cache hit entirely
        evidence("No cost_ledger row for cache hit", "May skip recording on cache")

    # THE KEY ASSERTION: balance unchanged to the cent
    balance_after = get_balance_cents(PPU_USER)
    check("balance UNCHANGED after cache hit",
          balance_after == balance_before,
          f"before={balance_before}¢ after={balance_after}¢ diff={balance_after - balance_before}¢")
    evidence("Cache hit balance proof", f"before={balance_before}¢ after={balance_after}¢ (diff=0)")

    # Wallet API should also show unchanged
    wallet_after = get_wallet_api(PPU_USER)
    wallet_cents = int(round(float(wallet_after.get("balance_usd", 0)) * 100))
    check("GET /wallet unchanged after cache hit",
          wallet_cents == balance_before,
          f"API={wallet_cents}¢ expected={balance_before}¢")


def test_unlimited_generation():
    """
    Test 3: Unlimited user — monthly_cost_spent_cents rises, no wallet charge.
    """
    print("\n" + "=" * 70)
    print("TEST 3: Unlimited user — cost recorded, no wallet charge")
    print("=" * 70)

    # Setup unlimited user
    setup_unlimited_user(UNLIMITED_USER)
    cost_before = get_monthly_cost_spent_cents(UNLIMITED_USER)
    evidence("Unlimited monthly_cost_spent_cents before", f"{cost_before}")

    # POST tour generation
    print("\n  Posting tour generation for unlimited user...")
    job_id, post_resp, status_code = post_generate_tour(
        UNLIMITED_USER,
        location=UNLIMITED_TOUR_LOCATION,
        tour_type=UNLIMITED_TOUR_TYPE,
        stops=UNLIMITED_TOUR_STOPS
    )
    check("POST returns 200 for unlimited user",
          status_code == 200,
          f"status_code={status_code}, job_id={job_id}")

    if not job_id:
        check("ABORT: no job_id for unlimited test", False, f"Response: {post_resp}")
        return

    # Poll to completion
    print(f"  Polling job {job_id} (1-3 minutes)...")
    final = poll_until_complete(job_id)
    final_status = final.get("status", "unknown")
    check("Unlimited tour generation completed",
          final_status in ("completed", "complete"),
          f"final_status={final_status}")

    if final_status not in ("completed", "complete"):
        check("ABORT: unlimited generation did not complete", False, f"Final: {json.dumps(final)}")
        return

    # cost_ledger should have the cost
    cost_row = get_cost_ledger_row(UNLIMITED_USER, job_id)
    check("cost_ledger row exists for unlimited",
          cost_row is not None, f"row={cost_row}")

    if cost_row:
        our_cost = Decimal(str(cost_row["our_cost_usd"]))
        evidence("Unlimited generation cost", f"${our_cost}")
        check("cost under ceiling",
              our_cost <= COST_CEILING,
              f"${our_cost} <= ${COST_CEILING}")
    else:
        our_cost = Decimal("0")

    # monthly_cost_spent_cents should have risen
    cost_after = get_monthly_cost_spent_cents(UNLIMITED_USER)
    check("monthly_cost_spent_cents increased",
          cost_after > cost_before,
          f"before={cost_before} after={cost_after} rise={cost_after - cost_before}")
    evidence("Unlimited cost tracking", f"before={cost_before}¢ after={cost_after}¢")

    # Verify cost rise matches our_cost (converted to cents)
    if our_cost > 0:
        expected_rise = int((our_cost * 100).to_integral_value(rounding=ROUND_HALF_EVEN))
        actual_rise = cost_after - cost_before
        check("cost rise matches our_cost",
              actual_rise == expected_rise,
              f"actual_rise={actual_rise}¢ expected={expected_rise}¢ (${our_cost})")

    # No wallet_ledger charge for unlimited users
    wallet_charge = get_wallet_ledger_charge(UNLIMITED_USER, job_id)
    check("NO wallet_ledger charge for unlimited",
          wallet_charge is None,
          f"charge_row={wallet_charge}")


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("LOCAL-84 · End-to-end HTTP charging proof")
    print(f"Run ID: {RUN_ID}")
    print(f"Orchestrator: {ORCHESTRATOR_URL}")
    print(f"PPU user: {PPU_USER}")
    print(f"Unlimited user: {UNLIMITED_USER}")
    print("=" * 70)

    # Pre-flight checks
    if not check_db_available():
        print("\nERROR: Database not available. Exiting.")
        sys.exit(7)

    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}/health", timeout=5)
        if resp.status_code != 200:
            print(f"\nERROR: Orchestrator not healthy (status={resp.status_code})")
            sys.exit(1)
    except Exception as e:
        print(f"\nERROR: Cannot reach orchestrator at {ORCHESTRATOR_URL}: {e}")
        sys.exit(1)

    print("\n  Pre-flight: DB reachable, orchestrator healthy\n")

    # Clean any stale test data from previous runs
    cleanup_test_users()

    total_api_spend = Decimal("0")

    try:
        # TEST 1: PPU fresh generation
        result1 = test_ppu_fresh_generation()
        if result1:
            total_api_spend += result1["our_cost"]

        # TEST 2: PPU cache hit (only if test 1 succeeded)
        if result1:
            test_ppu_cache_hit()

        # TEST 3: Unlimited user
        test_unlimited_generation()

    finally:
        # Always clean up
        cleanup_test_users()

    # ─── Summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    passed = sum(1 for r in RESULTS if r["passed"])
    failed = sum(1 for r in RESULTS if not r["passed"])
    total = len(RESULTS)

    for r in RESULTS:
        status = "✓" if r["passed"] else "✗"
        print(f"  {status} {r['name']}")

    print(f"\n  {passed}/{total} passed, {failed} failed")
    print(f"\n  Total API spend: ${total_api_spend:.4f} (ceiling: ${COST_CEILING}/tour)")
    evidence("Total API spend", f"${total_api_spend:.4f}")

    print("\n" + "=" * 70)
    print("EVIDENCE")
    print("=" * 70)
    for e in EVIDENCE:
        print(f"  {e['label']}: {e['data']}")

    if failed > 0:
        print(f"\n{'='*70}")
        print(f"FAILED ASSERTIONS ({failed}):")
        print(f"{'='*70}")
        for r in RESULTS:
            if not r["passed"]:
                print(f"  ✗ {r['name']}: {r['detail']}")
        sys.exit(1)
    else:
        print(f"\n  ALL {total} ASSERTIONS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
