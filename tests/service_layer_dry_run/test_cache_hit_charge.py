"""
Test 2: Cache-hit charge path via the service layer (LOCAL-201 wiring).

Exercises:
  - A fresh cost_ledger entry → charge → ledger debit
  - A cache-hit request → lookup fresh basis → charge same amount
  - Same cache-hit request repeated → idempotency prevents double-charge

Uses the news_orchestrator_service's generate-news endpoint with a
pre-cached article to trigger the cache-hit path.
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
        4. Verify: our_cost=0, user charged same as fresh, balance decreases
        5. Repeat with same idempotency key → balance unchanged
        """
        from cost_meter import record_operation
        from pricing import compute_user_charge
        from wallet_ledger import get_balance_cents, charge
        from cost_meter import lookup_fresh_cost_for_cache_hit

        # Step 1: Get initial balance
        initial_balance = get_balance_cents(ppu_user_id)
        print(f"  Initial balance: {initial_balance}¢")

        # Step 2: Record a fresh generation in cost_ledger
        # News ceiling is $0.05 (3× max observed $0.011). Use $0.011.
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

        # Step 3: Look up the fresh cost (simulating cache-hit lookup)
        basis = lookup_fresh_cost_for_cache_hit(job_id, "news_cache_hit")
        print(f"  Lookup fresh basis: ${basis}")
        assert basis is not None
        assert abs(float(basis) - fresh_cost) < 0.001

        # Step 4: Compute cache-hit charge (same as fresh per D45/LOCAL-200)
        charge_result = compute_user_charge(
            our_cost_usd=0.00,
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=basis,
            description="Test article (cached)",
        )
        print(f"  Cache-hit charge computed: ${charge_result['user_charge_usd']} ({charge_result['user_charge_cents']}¢)")
        assert charge_result["our_cost_usd"] == Decimal("0.00")
        assert charge_result["user_charge_cents"] > 0  # Should be 0.011 * 5 = $0.055 → 6¢
        expected_charge_cents = 6  # 0.011 * 5 = 0.055 → rounds to 0.06 (banker's) = 6¢
        assert charge_result["user_charge_cents"] == expected_charge_cents

        # Step 5: Apply the charge to wallet
        idem_key = f"charge:{ppu_user_id}:{job_id}"
        row_id, new_balance, was_stopped = charge(
            user_id=ppu_user_id,
            charge_usd=charge_result["user_charge_usd"],
            idempotency_key=idem_key,
            description=charge_result["description"],
            job_id=job_id,
        )
        print(f"  Charge applied: row={row_id}, balance={new_balance}¢, stopped={was_stopped}")
        assert new_balance == initial_balance - expected_charge_cents
        assert was_stopped is False

        # Step 6: Repeat with same idempotency key → NO double-charge
        row_id2, balance_after_repeat, _ = charge(
            user_id=ppu_user_id,
            charge_usd=charge_result["user_charge_usd"],
            idempotency_key=idem_key,
            description=charge_result["description"],
            job_id=job_id,
        )
        print(f"  Repeat charge: row={row_id2}, balance={balance_after_repeat}¢")
        assert balance_after_repeat == new_balance, (
            f"Double-charge! Expected {new_balance}¢, got {balance_after_repeat}¢"
        )
        print(f"  ✓ CACHE-HIT CHARGE PATH VERIFIED:")
        print(f"    - Fresh cost ${fresh_cost} → user charge ${charge_result['user_charge_usd']}")
        print(f"    - Cache hit our_cost=$0.00, user charged same ${charge_result['user_charge_usd']}")
        print(f"    - Idempotency prevents double-charge")
        print(f"    - Balance: {initial_balance}¢ → {new_balance}¢ (no change on repeat)")

    def test_cache_hit_no_basis_charges_zero(self, ppu_user_id):
        """Cache hit with no fresh basis (pre-metering content) → charge $0.00."""
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
        assert result["user_charge_cents"] == 0
        assert result["user_charge_usd"] == Decimal("0.00")
        print(f"  ✓ No basis → $0.00 charge (safe fallback)")
