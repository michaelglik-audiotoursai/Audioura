"""
Test 2: Cache-hit charge path via the service layer (LOCAL-201 wiring).

Exercises:
  - A fresh cost_ledger entry → charge → ledger debit
  - A cache-hit request → lookup fresh basis → charge same amount
  - Same cache-hit request repeated → idempotency prevents double-charge

TIGHT assertions:
  - Exact balance deltas (not just "decreased")
  - Exact charge amounts (not just "non-zero")
  - our_cost_usd == 0.00 for cache hits verified numerically
"""
import json
import os
import uuid
import pytest
import psycopg2
from decimal import Decimal


def _get_conn():
    return psycopg2.connect(
        host="localhost", port="5433",
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


class TestCacheHitChargePath:
    """Exercise the cache-hit charge wiring through wallet_api and wallet_ledger."""

    def test_cache_hit_charge_via_library(self, ppu_user_id):
        """
        Directly exercise the charge path that the orchestrator cache-hit block uses:
        1. Record a fresh cost in cost_ledger
        2. Use pricing.compute_user_charge with cache_hit=True + fresh_cost_usd
        3. Call wallet_ledger.charge() with the computed amount
        4. Verify: our_cost=0, user charged same as fresh, balance decreases by exact amount
        5. Repeat with same idempotency key → balance unchanged (no double-charge)

        TIGHT: Asserts exact cents values, not just directions.
        """
        from cost_meter import record_operation
        from pricing import compute_user_charge
        from wallet_ledger import get_balance_cents, charge
        from cost_meter import lookup_fresh_cost_for_cache_hit

        # Step 1: Get initial balance
        initial_balance = get_balance_cents(ppu_user_id)
        print(f"  Initial balance: {initial_balance}¢")
        assert initial_balance > 0, "PPU user should have positive balance from seed"

        # Step 2: Record a fresh generation in cost_ledger
        job_id = f"test-fresh-{uuid.uuid4().hex[:8]}"
        fresh_cost = 0.011  # typical news cost (max observed)
        record_operation(
            operation_type="news_generate",
            our_cost_usd=fresh_cost,
            cache_hit=False,
            user_id=ppu_user_id,
            job_id=job_id,
            breakdown={"llm": 0.007, "tts": 0.004},
            description="Test article fresh gen",
        )
        print(f"  Recorded fresh cost: ${fresh_cost} for job={job_id}")

        # Step 3: Verify the cost_ledger row was written
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT our_cost_usd, cache_hit FROM cost_ledger WHERE job_id = %s",
            (job_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        assert row is not None, f"cost_ledger row missing for job_id={job_id}"
        assert float(row[0]) == pytest.approx(fresh_cost, abs=0.001)
        assert row[1] is False
        print(f"  ✓ cost_ledger row verified: our_cost=${row[0]}, cache_hit={row[1]}")

        # Step 4: Look up the fresh cost (simulating cache-hit lookup)
        basis = lookup_fresh_cost_for_cache_hit(job_id, "news_cache_hit")
        print(f"  Lookup fresh basis: ${basis}")
        assert basis is not None, "lookup_fresh_cost_for_cache_hit returned None"
        assert abs(float(basis) - fresh_cost) < 0.001

        # Step 5: Compute cache-hit charge (same as fresh per D45/LOCAL-200)
        charge_result = compute_user_charge(
            our_cost_usd=0.00,
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=basis,
            description="Test article (cached)",
        )
        print(f"  Cache-hit charge computed: ${charge_result['user_charge_usd']} ({charge_result['user_charge_cents']}¢)")

        # TIGHT: verify exact values
        assert charge_result["our_cost_usd"] == Decimal("0.00"), (
            f"Cache hit our_cost must be $0.00, got {charge_result['our_cost_usd']}"
        )
        # 0.011 * 5 (multiplier) = 0.055 → rounds to 6¢
        expected_charge_cents = 6
        assert charge_result["user_charge_cents"] == expected_charge_cents, (
            f"Expected {expected_charge_cents}¢, got {charge_result['user_charge_cents']}¢"
        )

        # Step 6: Apply the charge to wallet
        idem_key = f"charge:{ppu_user_id}:{job_id}"
        row_id, new_balance, was_stopped = charge(
            user_id=ppu_user_id,
            charge_usd=charge_result["user_charge_usd"],
            idempotency_key=idem_key,
            description=charge_result["description"],
            job_id=job_id,
        )
        print(f"  Charge applied: row={row_id}, balance={new_balance}¢, stopped={was_stopped}")

        # TIGHT: exact balance math
        assert new_balance == initial_balance - expected_charge_cents, (
            f"Expected {initial_balance} - {expected_charge_cents} = {initial_balance - expected_charge_cents}, "
            f"got {new_balance}"
        )
        assert was_stopped is False

        # Step 7: Repeat with same idempotency key → NO double-charge
        row_id2, balance_after_repeat, _ = charge(
            user_id=ppu_user_id,
            charge_usd=charge_result["user_charge_usd"],
            idempotency_key=idem_key,
            description=charge_result["description"],
            job_id=job_id,
        )
        print(f"  Repeat charge: row={row_id2}, balance={balance_after_repeat}¢")
        assert balance_after_repeat == new_balance, (
            f"Double-charge! Expected {new_balance}¢ (unchanged), got {balance_after_repeat}¢"
        )

        print(f"  ✓ CACHE-HIT CHARGE PATH VERIFIED:")
        print(f"    - Fresh cost ${fresh_cost} → user charge {expected_charge_cents}¢")
        print(f"    - Cache hit our_cost=$0.00, user charged same {expected_charge_cents}¢")
        print(f"    - Idempotency prevents double-charge")
        print(f"    - Balance: {initial_balance}¢ → {new_balance}¢ → {balance_after_repeat}¢ (stable)")

    def test_cache_hit_no_basis_charges_zero(self, ppu_user_id):
        """Cache hit with no fresh basis (pre-metering content) → charge $0.00.

        TIGHT: asserts exact $0.00 charge, not just "less than X".
        """
        from pricing import compute_user_charge
        from wallet_ledger import get_balance_cents

        balance_before = get_balance_cents(ppu_user_id)

        # No fresh_cost_usd → charge $0.00
        result = compute_user_charge(
            our_cost_usd=0.00,
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=None,
            description="Pre-metering article",
        )
        print(f"  Cache hit no basis: charge=${result['user_charge_usd']} ({result['user_charge_cents']}¢)")

        # TIGHT: exactly zero
        assert result["user_charge_cents"] == 0
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["our_cost_usd"] == Decimal("0.00")

        # Balance should be unchanged (no charge to apply)
        balance_after = get_balance_cents(ppu_user_id)
        # Note: we didn't actually call charge() here, just compute. Verify no side effect.
        print(f"  Balance before={balance_before}¢, after={balance_after}¢")
        print(f"  ✓ No basis → $0.00 charge (safe fallback)")

    def test_cache_hit_ledger_row_marked(self, ppu_user_id):
        """The cost_ledger row for a cache hit has cache_hit=True and our_cost=0.

        TIGHT: reads the DB directly to verify the row content.
        """
        from cost_meter import record_operation
        from cost_rates import CACHE_HIT_COST_USD

        job_id = f"test-cachehit-row-{uuid.uuid4().hex[:8]}"
        record_operation(
            operation_type="news_cache_hit",
            our_cost_usd=CACHE_HIT_COST_USD,
            cache_hit=True,
            user_id=ppu_user_id,
            job_id=job_id,
            breakdown={"tts": 0.0, "llm": 0.0, "source": "news_cache"},
        )

        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT our_cost_usd, cache_hit, operation_type FROM cost_ledger WHERE job_id = %s",
            (job_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        assert row is not None, f"cost_ledger row not found for {job_id}"
        assert float(row[0]) == 0.0, f"Expected our_cost_usd==0.0, got {row[0]}"
        assert row[1] is True, f"Expected cache_hit==True, got {row[1]}"
        assert row[2] == "news_cache_hit"
        print(f"  ✓ cost_ledger row: our_cost=${row[0]}, cache_hit={row[1]}, type={row[2]}")
