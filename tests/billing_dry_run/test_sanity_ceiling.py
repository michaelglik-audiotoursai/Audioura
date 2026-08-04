"""
Test 3: Pre-LOCAL-197 ledger row sanity ceiling.

A cost recorded at the old inflated rate is rejected by the sanity ceiling
and charges $0.00 rather than overcharging.
"""
import os
import sys
import uuid
from decimal import Decimal

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "audiotours_subscribed")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "password123")
os.environ.setdefault("DATABASE_URL",
    "postgresql://admin:password123@localhost:5433/audiotours_subscribed")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from wallet_ledger import get_balance_cents, topup, charge
from pricing import compute_user_charge
from cost_meter import record_operation, lookup_fresh_cost_for_cache_hit


def test_sanity_ceiling_rejects_inflated_cost(test_user_id):
    """Pre-LOCAL-197 inflated rate is caught by sanity ceiling → $0.00 charge."""
    uid = test_user_id

    # Setup
    topup(uid, Decimal("10.00"), f"topup-sanity-{uid}", "pay-sanity-001")
    assert get_balance_cents(uid) == 1000

    # ── Record a pre-LOCAL-197 row with inflated cost ─────────────────────────
    # Old rate was ~$0.002/1K tokens → a 5000-token tour cost ~$0.010
    # But at the old inflated model, it was recorded as $0.35 (2.5× too high)
    # The sanity ceiling for tour_generate is $0.25
    inflated_cost = 0.35  # Above $0.25 ceiling
    inflated_job_id = f"job-inflated-{uid[:8]}"
    record_operation(
        operation_type="tour_generate",
        our_cost_usd=inflated_cost,
        cache_hit=False,
        user_id=uid,
        job_id=inflated_job_id,
        description="Tour: Old Inflated Rate Tour",
    )

    # ── Try to look up this cost for a cache hit ──────────────────────────────
    looked_up = lookup_fresh_cost_for_cache_hit(inflated_job_id, "tour_cache_hit")
    assert looked_up is None, (
        f"Sanity ceiling should have rejected ${inflated_cost} → None, got ${looked_up}"
    )
    print(f"  Sanity ceiling PASS: ${inflated_cost} exceeds $0.25 ceiling → returned None")

    # ── Without a valid basis, cache-hit charges $0.00 ────────────────────────
    cache_pricing = compute_user_charge(
        our_cost_usd=Decimal("0.00"),
        cache_hit=True,
        operation_type="tour_cache_hit",
        description="Tour: Old Inflated Rate Tour (cached)",
        fresh_cost_usd=None,  # No valid basis found
    )
    assert cache_pricing["user_charge_usd"] == Decimal("0.00"), (
        f"Without valid basis, cache hit should charge $0.00, got {cache_pricing['user_charge_usd']}"
    )
    print(f"  No basis → charge $0.00 PASS")

    # Verify balance unchanged
    bal = get_balance_cents(uid)
    assert bal == 1000, f"Balance should still be 1000¢, got {bal}"
    print(f"  Balance unchanged: {bal}¢")

    # ── Verify that a VALID cost passes the ceiling ───────────────────────────
    valid_cost = 0.068  # Well under $0.25
    valid_job_id = f"job-valid-{uid[:8]}"
    record_operation(
        operation_type="tour_generate",
        our_cost_usd=valid_cost,
        cache_hit=False,
        user_id=uid,
        job_id=valid_job_id,
        description="Tour: Valid Cost Tour",
    )
    valid_lookup = lookup_fresh_cost_for_cache_hit(valid_job_id, "tour_cache_hit")
    assert valid_lookup is not None and abs(valid_lookup - valid_cost) < 0.001, (
        f"Valid cost should pass ceiling, got {valid_lookup}"
    )
    print(f"  Valid cost ${valid_cost} passes ceiling PASS (returned ${valid_lookup})")

    print("\n  ✓ SANITY CEILING PASSED")
