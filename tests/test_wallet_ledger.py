"""
Test suite for wallet_ledger (LOCAL-66).
========================================
Covers all acceptance criteria:
    1. Ledger + derived balance — sequence of movements, balance correct at each step
    2. Rebuild test — recomputed from ledger equals cached value after 1000 mixed movements
    3. Clawback-after-spend — balance goes negative, row recorded, nothing lost
    4. Idempotency — same key applied twice credits once
    5. Zero-balance stop fires; clawback-negative does NOT create debt from normal use
    6. Unlimited cost-stop breach produces message and switch offer

Requires: PostgreSQL running (via docker-compose), tables auto-created.
"""

import os
import sys
import uuid
import time
import random
from decimal import Decimal

# Set DB env for local testing
# Docker maps container:5432 → host:5433
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5433")
os.environ.setdefault("DB_NAME", "audiotours")
os.environ.setdefault("DB_USER", "admin")
os.environ.setdefault("DB_PASSWORD", "password123")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wallet_ledger import (
    record_movement,
    get_balance_cents,
    rebuild_balance_from_ledger,
    topup,
    charge,
    refund_clawback,
    monthly_fee,
    check_unlimited_cost_stop,
    record_unlimited_cost,
    check_low_balance,
    get_transaction_history,
    _usd_to_cents,
    _cents_to_usd,
    _get_db_connection,
    _ensure_tables,
    VALID_MOVEMENT_TYPES,
    PRICING_MULTIPLIER,
    CREDIT_LOW_BALANCE_USD,
    UNLIMITED_COST_STOP_USD,
)


def _unique_user():
    """Generate a unique user_id for test isolation."""
    return f"test-local66-{uuid.uuid4().hex[:12]}"


def _unique_key():
    """Generate a unique idempotency key."""
    return f"idem-{uuid.uuid4().hex}"


def _cleanup_user(user_id: str):
    """Remove test data for a user (keeps tests isolated)."""
    conn = _get_db_connection()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()


# ============================================================
# AC1: Ledger + derived balance
# ============================================================

def test_ledger_and_derived_balance():
    """Sequence of top-ups and charges, balance correct at each step."""
    user = _unique_user()

    try:
        # Step 1: Top-up $10.00
        row1, bal1 = topup(user, Decimal("10.00"), _unique_key(), "pay-001")
        assert row1 is not None, "topup should succeed"
        assert bal1 == 1000, f"Expected 1000¢, got {bal1}"

        # Step 2: Charge $0.35 (a tour)
        row2, bal2, stop = charge(user, Decimal("0.35"), _unique_key(), "Tour: Nice walking — $0.35", "job-001")
        assert row2 is not None, "charge should succeed"
        assert bal2 == 965, f"Expected 965¢, got {bal2}"
        assert stop is False

        # Step 3: Charge $0.75 (expensive tour)
        row3, bal3, stop = charge(user, Decimal("0.75"), _unique_key(), "Tour: Riviera biking — $0.75", "job-002")
        assert row3 is not None
        assert bal3 == 890, f"Expected 890¢, got {bal3}"
        assert stop is False

        # Step 4: Monthly fee $2.00
        row4, bal4 = monthly_fee(user, "pay_per_use", _unique_key())
        assert row4 is not None
        assert bal4 == 690, f"Expected 690¢, got {bal4}"

        # Step 5: Another top-up $10.00
        row5, bal5 = topup(user, Decimal("10.00"), _unique_key(), "pay-002")
        assert row5 is not None
        assert bal5 == 1690, f"Expected 1690¢, got {bal5}"

        # Step 6: Charge $1.20
        row6, bal6, stop = charge(user, Decimal("1.20"), _unique_key(), "Tour: Paris museum — $1.20", "job-003")
        assert row6 is not None
        assert bal6 == 1570, f"Expected 1570¢, got {bal6}"
        assert stop is False

        # Verify derived balance matches
        derived = rebuild_balance_from_ledger(user)
        assert derived == bal6, f"Derived {derived} != recorded {bal6}"

        # Print the table
        print("\n=== AC1: Ledger + Derived Balance ===")
        print(f"{'Step':<6} {'Operation':<25} {'Amount':>10} {'Balance':>10}")
        print("-" * 55)
        steps = [
            ("1", "Top-up $10.00", "+$10.00", "$10.00"),
            ("2", "Charge: Nice walking", "-$0.35", "$9.65"),
            ("3", "Charge: Riviera biking", "-$0.75", "$8.90"),
            ("4", "Monthly fee (PPU)", "-$2.00", "$6.90"),
            ("5", "Top-up $10.00", "+$10.00", "$16.90"),
            ("6", "Charge: Paris museum", "-$1.20", "$15.70"),
        ]
        for s in steps:
            print(f"{s[0]:<6} {s[1]:<25} {s[2]:>10} {s[3]:>10}")
        print(f"\nDerived balance from ledger: ${derived / 100:.2f}")
        print(f"Cached balance:             ${get_balance_cents(user) / 100:.2f}")
        print("AC1 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# AC2: Rebuild test (1000 mixed movements)
# ============================================================

def test_rebuild_1000_movements():
    """Balance recomputed from ledger equals cached value after 1000 mixed movements."""
    user = _unique_user()

    try:
        # Seed with a large top-up so charges don't zero-stop
        topup(user, Decimal("500.00"), _unique_key(), "seed")

        operations = []
        for i in range(1000):
            r = random.random()
            if r < 0.3:
                # Top-up between $5 and $20
                amt = Decimal(str(random.randint(500, 2000))) / Decimal(100)
                topup(user, amt, _unique_key(), f"topup-{i}")
                operations.append(("topup", amt))
            elif r < 0.8:
                # Charge between $0.10 and $2.00
                amt = Decimal(str(random.randint(10, 200))) / Decimal(100)
                charge(user, amt, _unique_key(), f"charge-{i}", f"job-{i}")
                operations.append(("charge", amt))
            else:
                # Monthly fee
                monthly_fee(user, "pay_per_use", _unique_key())
                operations.append(("fee", Decimal("2.00")))

        # Get cached balance
        cached = get_balance_cents(user)

        # Rebuild from ledger
        rebuilt = rebuild_balance_from_ledger(user)

        assert rebuilt == cached, f"REBUILD MISMATCH: rebuilt={rebuilt} != cached={cached}"

        print(f"\n=== AC2: Rebuild Test (1000 movements) ===")
        print(f"Operations: 1000 mixed (topups, charges, fees)")
        print(f"Cached balance:  {cached}¢ (${cached / 100:.2f})")
        print(f"Rebuilt balance: {rebuilt}¢ (${rebuilt / 100:.2f})")
        print(f"Match: {rebuilt == cached}")
        print("AC2 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# AC3: Clawback-after-spend — balance goes negative
# ============================================================

def test_clawback_negative_balance():
    """Clawback after spend drives balance negative, row recorded, nothing lost."""
    user = _unique_user()

    try:
        # Top-up $10
        topup(user, Decimal("10.00"), _unique_key(), "pay-x1")
        assert get_balance_cents(user) == 1000

        # Spend $8
        charge(user, Decimal("8.00"), _unique_key(), "Big tour — $8.00", "job-big")
        assert get_balance_cents(user) == 200

        # Apple refund clawback of the original $10 top-up
        row_id, balance = refund_clawback(
            user, Decimal("10.00"), _unique_key(),
            "Apple refund clawback: original top-up reversed",
            "apple-refund-001"
        )

        assert row_id is not None, "Clawback should record successfully"
        assert balance == -800, f"Expected -800¢, got {balance}"

        # Verify the row exists in the ledger
        history = get_transaction_history(user)
        clawback_rows = [h for h in history if h["type"] == "refund_clawback"]
        assert len(clawback_rows) == 1, f"Expected 1 clawback row, got {len(clawback_rows)}"

        # Verify derived balance matches
        rebuilt = rebuild_balance_from_ledger(user)
        assert rebuilt == -800, f"Rebuilt should be -800¢, got {rebuilt}"

        print(f"\n=== AC3: Clawback Negative Balance ===")
        print(f"After top-up $10:       1000¢")
        print(f"After charge $8:         200¢")
        print(f"After clawback $10:     {balance}¢")
        print(f"Row recorded: {row_id}")
        print(f"Rebuilt from ledger:    {rebuilt}¢")
        print(f"Nothing lost: ledger has {len(history)} rows")
        print("AC3 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# AC4: Idempotency — same key twice credits once
# ============================================================

def test_idempotency():
    """Same idempotency key applied twice credits once."""
    user = _unique_user()
    key = f"idem-duplicate-test-{uuid.uuid4().hex[:8]}"

    try:
        # First top-up
        row1, bal1 = topup(user, Decimal("10.00"), key, "pay-dup")
        assert row1 is not None
        assert bal1 == 1000

        # Second top-up with SAME key — should be no-op
        row2, bal2 = topup(user, Decimal("10.00"), key, "pay-dup")
        assert row2 == row1, f"Should return same row: {row2} != {row1}"
        assert bal2 == 1000, f"Balance should still be 1000¢, got {bal2}"

        # Verify only one ledger row exists
        conn = _get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM wallet_ledger WHERE user_id = %s",
                (user,),
            )
            count = cur.fetchone()[0]
        conn.close()
        assert count == 1, f"Expected 1 ledger row, got {count}"

        print(f"\n=== AC4: Idempotency ===")
        print(f"Key: {key}")
        print(f"Attempt 1: row={row1}, balance={bal1}¢")
        print(f"Attempt 2: row={row2}, balance={bal2}¢")
        print(f"Same row returned: {row1 == row2}")
        print(f"Ledger rows: {count}")
        print(f"Balance unchanged: {bal1 == bal2}")
        print("AC4 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# AC5: Zero-balance stop; clawback-negative does NOT create debt
# ============================================================

def test_zero_balance_stop():
    """Zero balance blocks charges; clawback-negative balance blocks normal charges too."""
    user = _unique_user()

    try:
        # Start with $1.00
        topup(user, Decimal("1.00"), _unique_key(), "pay-small")
        assert get_balance_cents(user) == 100

        # Spend all $1.00
        row, bal, stop = charge(user, Decimal("1.00"), _unique_key(), "Spend all", "j1")
        assert bal == 0
        assert stop is False  # This charge succeeded, it didn't trigger stop

        # Now try to charge $0.35 — should be BLOCKED (zero balance)
        row2, bal2, stop2 = charge(user, Decimal("0.35"), _unique_key(), "Should fail", "j2")
        assert row2 is None, "Charge should be blocked"
        assert bal2 == 0
        assert stop2 is True, "Zero-stop should fire"

        # Now simulate a clawback that goes negative
        row3, bal3 = refund_clawback(user, Decimal("5.00"), _unique_key(), "Apple refund")
        assert bal3 == -500

        # Try to charge on negative balance — still blocked (no debt from normal use)
        row4, bal4, stop4 = charge(user, Decimal("0.10"), _unique_key(), "Should also fail", "j3")
        assert row4 is None, "Charge on negative balance should be blocked"
        assert stop4 is True

        print(f"\n=== AC5: Zero-Balance Stop ===")
        print(f"After top-up $1.00:    100¢")
        print(f"After charge $1.00:      0¢ (charge succeeded, spent all)")
        print(f"Charge $0.35 blocked: stop={stop2}, balance=0¢")
        print(f"After clawback $5.00: {bal3}¢ (negative OK)")
        print(f"Charge $0.10 blocked: stop={stop4}, balance={bal4}¢")
        print(f"No debt from normal use: confirmed")
        print("AC5 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# AC6: Unlimited cost-stop breach — message and switch offer
# ============================================================

def test_unlimited_cost_stop():
    """Cost-stop breach produces the message and the switch offer."""
    user = _unique_user()

    try:
        # Set up as unlimited tier
        conn = _get_db_connection()
        _ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wallet_subscription (user_id, tier, monthly_cost_spent_cents, updated_at)
                VALUES (%s, 'unlimited', 0, NOW())
                ON CONFLICT (user_id) DO UPDATE SET tier = 'unlimited', monthly_cost_spent_cents = 0
                """,
                (user,),
            )
        conn.commit()
        conn.close()

        # Record costs incrementally
        # $25.00 cost stop (0.5 × $50)
        # Record $20 in costs — should be fine
        result1 = record_unlimited_cost(user, Decimal("20.00"))
        assert result1["breached"] is False, f"Should not breach at $20: {result1}"

        # Record $4.99 more — still under ($24.99 total)
        result2 = record_unlimited_cost(user, Decimal("4.99"))
        assert result2["breached"] is False, f"Should not breach at $24.99: {result2}"

        # Record $0.02 more — now at $25.01, breached
        result3 = record_unlimited_cost(user, Decimal("0.02"))
        assert result3["breached"] is True, f"Should breach at $25.01: {result3}"
        assert result3["message"] is not None
        assert "switch to Pay-Per-Use" in result3["message"], f"Missing switch offer: {result3['message']}"
        assert "monthly usage limit" in result3["message"], f"Missing limit mention: {result3['message']}"

        print(f"\n=== AC6: Unlimited Cost-Stop ===")
        print(f"Cost stop: ${UNLIMITED_COST_STOP_USD:.2f}")
        print(f"After $20.00 cost:  breached={result1['breached']}")
        print(f"After $24.99 cost:  breached={result2['breached']}")
        print(f"After $25.01 cost:  breached={result3['breached']}")
        print(f"Message: {result3['message']}")
        print("AC6 PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# SUPPLEMENTARY: Cents conversion
# ============================================================

def test_cents_conversion():
    """Verify no float contamination in cent conversion."""
    assert _usd_to_cents(Decimal("10.00")) == 1000
    assert _usd_to_cents(Decimal("0.35")) == 35
    assert _usd_to_cents(Decimal("0.69")) == 69
    assert _usd_to_cents(Decimal("2.00")) == 200
    assert _usd_to_cents(Decimal("50.00")) == 5000
    assert _usd_to_cents(Decimal("0.005")) == 1  # rounds up

    assert _cents_to_usd(1000) == Decimal("10.00")
    assert _cents_to_usd(35) == Decimal("0.35")
    assert _cents_to_usd(-800) == Decimal("-8.00")

    print("\n=== Cents Conversion ===")
    print("All conversions correct, no float contamination.")
    print("PASS ✓")


# ============================================================
# SUPPLEMENTARY: Low balance reminder
# ============================================================

def test_low_balance_reminder():
    """Low balance triggers reminder, above threshold does not."""
    user = _unique_user()

    try:
        # Start with $10 — no reminder
        topup(user, Decimal("10.00"), _unique_key())
        msg = check_low_balance(user)
        assert msg is None, f"Should not trigger at $10: {msg}"

        # Spend down to $1.50 — below $2 threshold
        charge(user, Decimal("8.50"), _unique_key(), "spend down", "j-x")
        msg = check_low_balance(user)
        assert msg is not None, "Should trigger at $1.50"
        assert "Top up" in msg

        print(f"\n=== Low Balance Reminder ===")
        print(f"At $10.00: reminder={msg is None} (correct: no)")
        print(f"At $1.50:  reminder triggered")
        print(f"Message: {msg}")
        print("PASS ✓")

    finally:
        _cleanup_user(user)


# ============================================================
# RUN ALL
# ============================================================

def run_all():
    """Run all acceptance tests."""
    print("=" * 60)
    print("LOCAL-66: Wallet Ledger & Balance — Test Suite")
    print("=" * 60)

    tests = [
        ("AC1: Ledger + derived balance", test_ledger_and_derived_balance),
        ("AC2: Rebuild (1000 movements)", test_rebuild_1000_movements),
        ("AC3: Clawback negative balance", test_clawback_negative_balance),
        ("AC4: Idempotency", test_idempotency),
        ("AC5: Zero-balance stop", test_zero_balance_stop),
        ("AC6: Unlimited cost-stop", test_unlimited_cost_stop),
        ("Supplementary: Cents conversion", test_cents_conversion),
        ("Supplementary: Low balance reminder", test_low_balance_reminder),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"\n  FAIL: {name}: {e}")
        except Exception as e:
            failed += 1
            errors.append((name, f"ERROR: {e}"))
            print(f"\n  ERROR: {name}: {e}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
