"""
Test 2: Cache-hit charging (D72/LOCAL-200).

Verifies:
  - A cached tour charges the same as fresh
  - our_cost_usd stays $0.00 for the cache hit
  - A repeat request does not double-charge (idempotency)
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


def test_cache_hit_charging(test_user_id):
    """Cache hit charges same as fresh; our_cost stays $0.00; no double-charge."""
    uid = test_user_id

    # Setup: topup so we have funds
    topup(uid, Decimal("10.00"), f"topup-cache-{uid}", "pay-cache-001")
    assert get_balance_cents(uid) == 1000

    # ── Fresh generation: record cost and charge ──────────────────────────────
    fresh_cost = 0.068
    job_id = f"job-fresh-{uid[:8]}"
    cost_row_id = record_operation(
        operation_type="tour_generate",
        our_cost_usd=fresh_cost,
        cache_hit=False,
        user_id=uid,
        job_id=job_id,
        breakdown={"llm": 0.052, "tts": 0.012, "search": 0.004},
        description="Tour: Cache Test City",
    )
    assert cost_row_id is not None, "Failed to record fresh cost"
    print(f"  Fresh cost recorded: ${fresh_cost} (row {cost_row_id})")

    # Compute fresh charge and apply
    fresh_pricing = compute_user_charge(
        our_cost_usd=Decimal(str(fresh_cost)),
        cache_hit=False,
        operation_type="tour_generate",
        description="Tour: Cache Test City",
    )
    assert fresh_pricing["user_charge_usd"] == Decimal("0.34")
    _, bal_after_fresh, _ = charge(
        uid, fresh_pricing["user_charge_usd"],
        f"charge-fresh-{uid}",
        description="Tour: Cache Test City — $0.34",
        job_id=job_id,
    )
    assert bal_after_fresh == 966, f"Expected 966¢ after fresh charge, got {bal_after_fresh}"
    print(f"  Fresh charge: ${fresh_pricing['user_charge_usd']} → balance={bal_after_fresh}¢")

    # ── Cache hit: look up fresh cost, charge same amount ─────────────────────
    looked_up_cost = lookup_fresh_cost_for_cache_hit(job_id, "tour_cache_hit")
    assert looked_up_cost is not None, "Failed to look up fresh cost for cache hit"
    assert abs(looked_up_cost - fresh_cost) < 0.0001, (
        f"Looked up cost {looked_up_cost} != fresh {fresh_cost}"
    )
    print(f"  Cache hit lookup: found fresh cost=${looked_up_cost}")

    # Record the cache hit in cost_ledger (our_cost = $0.00)
    cache_cost_row = record_operation(
        operation_type="tour_cache_hit",
        our_cost_usd=0.00,
        cache_hit=True,
        user_id=uid,
        job_id=f"job-cache-{uid[:8]}",
        description="Tour: Cache Test City (cached)",
    )
    assert cache_cost_row is not None, "Failed to record cache hit cost"

    # Compute cache-hit charge: should be same as fresh
    cache_pricing = compute_user_charge(
        our_cost_usd=Decimal("0.00"),
        cache_hit=True,
        operation_type="tour_cache_hit",
        description="Tour: Cache Test City (cached — same charge)",
        fresh_cost_usd=Decimal(str(looked_up_cost)),
    )
    assert cache_pricing["our_cost_usd"] == Decimal("0.00"), (
        f"Cache hit our_cost should be $0.00, got {cache_pricing['our_cost_usd']}"
    )
    assert cache_pricing["user_charge_usd"] == Decimal("0.34"), (
        f"Cache hit charge should equal fresh ($0.34), got {cache_pricing['user_charge_usd']}"
    )
    print(f"  Cache hit pricing: our_cost=${cache_pricing['our_cost_usd']}, "
          f"user_charge=${cache_pricing['user_charge_usd']}")

    # Apply cache-hit charge
    _, bal_after_cache, _ = charge(
        uid, cache_pricing["user_charge_usd"],
        f"charge-cache-{uid}",
        description="Tour: Cache Test City (cached — same charge) — $0.34",
        job_id=f"job-cache-{uid[:8]}",
    )
    assert bal_after_cache == 932, f"Expected 932¢ after cache charge, got {bal_after_cache}"
    print(f"  Cache hit charge applied: balance={bal_after_cache}¢")

    # ── Idempotency: repeat request does NOT double-charge ────────────────────
    _, bal_repeat, _ = charge(
        uid, cache_pricing["user_charge_usd"],
        f"charge-cache-{uid}",  # SAME idempotency key!
        description="Tour: Cache Test City (cached — same charge) — $0.34",
        job_id=f"job-cache-{uid[:8]}",
    )
    assert bal_repeat == 932, (
        f"Idempotent repeat should NOT change balance (expected 932, got {bal_repeat})"
    )
    print(f"  Idempotency PASS: repeat charge with same key → balance unchanged ({bal_repeat}¢)")

    print("\n  ✓ CACHE-HIT CHARGING PASSED")
