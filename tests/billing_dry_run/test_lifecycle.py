"""
Test 1: Full user lifecycle exercising the billing path against audiotours_subscribed.

Steps:
  1. User starts on free plan (balance = 0)
  2. Top up $10 → balance = 1000¢
  3. Charge a tour at ×5 rule → balance falls correctly
  4. Charge until balance goes negative but above −$2.00 floor
  5. Attempt operation that would breach −$2.00 → refused pre-flight
  6. Top up $10 against negative balance → debt carries forward
"""
import os
import sys
import uuid
from decimal import Decimal

# Env must be set before imports
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

from wallet_ledger import (
    get_balance_cents, topup, charge, record_movement,
)
from pricing import compute_user_charge
from projected_costs import would_breach_floor, OVERDRAFT_FLOOR_CENTS


def test_full_lifecycle(test_user_id):
    """Exercise the complete billing lifecycle against audiotours_subscribed."""
    uid = test_user_id

    # ── Step 1: Fresh user, balance = 0 ──────────────────────────────────────
    balance = get_balance_cents(uid)
    assert balance == 0, f"Step 1: Expected 0, got {balance}"
    print(f"  Step 1 PASS: Fresh user balance = {balance}¢")

    # ── Step 2: Top up $10 → 1000¢ ───────────────────────────────────────────
    row_id, new_bal = topup(uid, Decimal("10.00"), f"topup-1-{uid}", "pay-001")
    assert row_id is not None, "Step 2: topup returned None row_id"
    assert new_bal == 1000, f"Step 2: Expected 1000¢, got {new_bal}"
    print(f"  Step 2 PASS: After $10 topup, balance = {new_bal}¢")

    # ── Step 3: Charge a tour at ×5 rule ─────────────────────────────────────
    # Simulate: our_cost = $0.068, user_charge = $0.068 × 5 = $0.34
    pricing_result = compute_user_charge(
        our_cost_usd=Decimal("0.068"),
        cache_hit=False,
        operation_type="tour_generate",
        description="Tour: Test City walking",
    )
    user_charge = pricing_result["user_charge_usd"]
    user_charge_cents = pricing_result["user_charge_cents"]
    assert user_charge == Decimal("0.34"), f"Step 3: Expected $0.34, got {user_charge}"
    assert user_charge_cents == 34, f"Step 3: Expected 34¢, got {user_charge_cents}"

    row_id, new_bal, _ = charge(
        uid, user_charge, f"charge-tour-1-{uid}",
        description="Tour: Test City walking — $0.34",
        job_id="job-test-001",
    )
    assert new_bal == 966, f"Step 3: Expected 966¢, got {new_bal}"
    print(f"  Step 3 PASS: After $0.34 tour charge, balance = {new_bal}¢")

    # ── Step 4: Charge until balance goes negative but above −200¢ ────────────
    # Current: 966¢. Charge 29 more tours at 34¢ each = 986¢ total debits
    # 966 - (29 × 34) = 966 - 986 = -20¢ (above -200¢ floor)
    for i in range(29):
        row_id, new_bal, _ = charge(
            uid, Decimal("0.34"), f"charge-tour-{i+2}-{uid}",
            description=f"Tour: Repeated #{i+2}",
            job_id=f"job-test-{i+2:03d}",
        )
    assert new_bal == -20, f"Step 4: Expected -20¢, got {new_bal}"
    assert new_bal > OVERDRAFT_FLOOR_CENTS, (
        f"Step 4: Balance {new_bal} should be above floor {OVERDRAFT_FLOOR_CENTS}"
    )
    print(f"  Step 4 PASS: After 30 tours, balance = {new_bal}¢ (above −200¢ floor)")

    # ── Step 5: Pre-flight refuses operation that would breach −$2.00 ─────────
    # Balance = -20¢. A tour_generate projected cost = 40¢.
    # -20 - 40 = -60 → NOT below -200, so tour is still allowed!
    # We need to go lower. Let's charge a translation: projected = 270¢.
    # -20 - 270 = -290 < -200 → REFUSED.
    breaches = would_breach_floor(new_bal, "translation_generate")
    assert breaches is True, (
        f"Step 5: Expected breach for translation at {new_bal}¢, got {breaches}"
    )
    print(f"  Step 5 PASS: translation_generate refused at balance={new_bal}¢ "
          f"(would go to {new_bal - 270}¢, below −200¢)")

    # Verify that a tour_generate is still ALLOWED at -20¢
    tour_ok = would_breach_floor(new_bal, "tour_generate")
    assert tour_ok is False, (
        f"Step 5b: tour_generate should be allowed at {new_bal}¢"
    )
    print(f"  Step 5b PASS: tour_generate still allowed at {new_bal}¢")

    # ── Step 6: Top up $10 against −$0.20 balance → $9.80, not $10.00 ────────
    # D41: debt carries forward. -20 + 1000 = 980¢ ($9.80)
    row_id, new_bal = topup(uid, Decimal("10.00"), f"topup-2-{uid}", "pay-002")
    assert new_bal == 980, f"Step 6: Expected 980¢, got {new_bal}"
    print(f"  Step 6 PASS: $10 topup against -20¢ balance → {new_bal}¢ ($9.80)")

    # ── Verify the exact D41 example: −$0.23 + $10 = $9.77 ──────────────────
    # Drive balance to exactly -23¢ from current 980¢
    # Charge (980 + 23) = 1003¢ = $10.03
    row_id, bal, _ = charge(
        uid, Decimal("10.03"), f"charge-big-{uid}",
        description="Drain to -23",
    )
    assert bal == -23, f"Step 6 verify: Expected -23¢, got {bal}"

    row_id, bal = topup(uid, Decimal("10.00"), f"topup-3-{uid}", "pay-003")
    assert bal == 977, f"Step 6 verify: Expected 977¢ ($9.77), got {bal}"
    print(f"  Step 6 verify PASS: D41 exact example: −23¢ + $10.00 = {bal}¢ ($9.77)")

    print("\n  ✓ FULL LIFECYCLE PASSED")
