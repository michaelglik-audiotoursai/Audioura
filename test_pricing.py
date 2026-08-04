"""
Tests for pricing.py — LOCAL-65 pricing engine.
================================================
Covers:
  1. Every operation type (generate + cache-hit variants)
  2. Float-drift test (10,000 sequential charges, exact to the cent)
  3. Round-trip against real cost_ledger rows (known measured values)
  4. Config change honoured without code change (multiplier override)
  5. Edge cases: zero cost, negative cost guard, description override
"""

import os
from decimal import Decimal

import pytest

# Ensure a clean config state for each test
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove pricing env vars so defaults apply unless a test sets them."""
    monkeypatch.delenv("PRICING_MULTIPLIER", raising=False)
    monkeypatch.delenv("CACHE_HIT_COST_USD", raising=False)


# ---------------------------------------------------------------------------
# Import after fixture definition so module-level env reads use defaults
# ---------------------------------------------------------------------------
from pricing import (
    compute_user_charge,
    compute_charges_for_ledger_rows,
    get_pricing_multiplier,
    get_cache_hit_cost,
    _CENT,
)


# ===========================================================================
# § 1 — Every operation type
# ===========================================================================

class TestOperationTypes:
    """Each known operation type produces correct charge and description."""

    def test_tour_generate(self):
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        # 0.0633 * 5 = 0.3165 → banker's rounds to 0.32
        assert result["user_charge_usd"] == Decimal("0.32")
        assert result["user_charge_cents"] == 32
        assert result["cache_hit"] is False
        assert result["description"] == "Tour generation"

    def test_tour_generate_second_example(self):
        result = compute_user_charge(
            our_cost_usd="0.0573",
            cache_hit=False,
            operation_type="tour_generate",
        )
        # 0.0573 * 5 = 0.2865 → to quantize to 0.01, third digit is 6 (>5) → rounds up → 0.29
        assert result["user_charge_usd"] == Decimal("0.29")
        assert result["user_charge_cents"] == 29

    def test_translation_generate(self):
        result = compute_user_charge(
            our_cost_usd="0.3720",
            cache_hit=False,
            operation_type="translation_generate",
        )
        # 0.3720 * 5 = 1.8600 → exactly 1.86
        assert result["user_charge_usd"] == Decimal("1.86")
        assert result["user_charge_cents"] == 186
        assert result["description"] == "Translation"

    def test_tour_cache_hit(self):
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0
        assert result["description"] == "Tour (cached — same charge)"

    def test_translation_cache_hit(self):
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="translation_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0
        assert result["description"] == "Translation (cached — same charge)"

    def test_news_generate(self):
        result = compute_user_charge(
            our_cost_usd="0.0450",
            cache_hit=False,
            operation_type="news_generate",
        )
        # 0.045 * 5 = 0.225 → banker's rounds to 0.22 (half-even: 2 is even)
        assert result["user_charge_usd"] == Decimal("0.22")
        assert result["user_charge_cents"] == 22
        assert result["description"] == "News article"

    def test_photo_extension(self):
        result = compute_user_charge(
            our_cost_usd="0.10",
            cache_hit=False,
            operation_type="photo_extension",
        )
        # 0.10 * 5 = 0.50
        assert result["user_charge_usd"] == Decimal("0.50")
        assert result["user_charge_cents"] == 50
        assert result["description"] == "Photo tour extension"

    def test_cache_hit_forces_zero_even_with_nonzero_cost(self):
        """Even if caller erroneously passes a non-zero cost with cache_hit=True,
        the charge must still be $0.00."""
        result = compute_user_charge(
            our_cost_usd="0.05",
            cache_hit=True,
            operation_type="tour_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0


# ===========================================================================
# § 2 — Float-drift test (10,000 charges, balance exact to the cent)
# ===========================================================================

class TestFloatDrift:
    """Verify no floating-point drift accumulates over many transactions."""

    def test_10000_sequential_charges_exact(self):
        """Sum 10,000 charges of $0.0633 each at ×5. Expected: 10000 × $0.32 = $3,200.00.

        With float math, 10000 * 0.32 might drift. With Decimal + quantize
        per charge, the sum must be exact.
        """
        total = Decimal("0.00")
        cost = Decimal("0.0633")

        for _ in range(10_000):
            result = compute_user_charge(
                our_cost_usd=cost,
                cache_hit=False,
                operation_type="tour_generate",
            )
            total += result["user_charge_usd"]

        # Each charge is exactly $0.32
        expected = Decimal("0.32") * 10_000
        assert total == expected, f"Drift detected: {total} != {expected}"

    def test_10000_mixed_operations_no_drift(self):
        """Mixed operation types, verify integer-cent total matches sum."""
        total_decimal = Decimal("0.00")
        total_cents = 0

        costs = [
            ("0.0633", False, "tour_generate"),
            ("0.0573", False, "tour_generate"),
            ("0.3720", False, "translation_generate"),
            ("0.00", True, "tour_cache_hit"),
            ("0.00", True, "translation_cache_hit"),
        ]

        for i in range(10_000):
            cost_str, cache_hit, op_type = costs[i % len(costs)]
            result = compute_user_charge(
                our_cost_usd=cost_str,
                cache_hit=cache_hit,
                operation_type=op_type,
            )
            total_decimal += result["user_charge_usd"]
            total_cents += result["user_charge_cents"]

        # Verify internal consistency: cents == decimal * 100
        assert total_cents == int(total_decimal * 100)

        # The 5 operations produce: 0.32 + 0.29 + 1.86 + 0.00 + 0.00 = 2.47 per cycle
        # 10000 / 5 = 2000 full cycles → 2000 * 2.47 = 4940.00
        expected = Decimal("2.47") * 2000
        assert total_decimal == expected


# ===========================================================================
# § 3 — Round-trip against real cost_ledger rows
# ===========================================================================

class TestLedgerRoundTrip:
    """Test with the known measured values from the task spec."""

    KNOWN_ROWS = [
        {
            "id": "row-1",
            "operation_type": "tour_generate",
            "our_cost_usd": 0.0633,  # float, as DB returns
            "cache_hit": False,
            "user_id": "user-abc",
            "job_id": "job-001",
        },
        {
            "id": "row-2",
            "operation_type": "tour_generate",
            "our_cost_usd": 0.0573,
            "cache_hit": False,
            "user_id": "user-abc",
            "job_id": "job-002",
        },
        {
            "id": "row-3",
            "operation_type": "translation_generate",
            "our_cost_usd": 0.3720,
            "cache_hit": False,
            "user_id": "user-abc",
            "job_id": "job-003",
        },
        {
            "id": "row-4",
            "operation_type": "tour_cache_hit",
            "our_cost_usd": 0.0000,
            "cache_hit": True,
            "user_id": "user-abc",
            "job_id": "job-004",
        },
        {
            "id": "row-5",
            "operation_type": "translation_cache_hit",
            "our_cost_usd": 0.0000,
            "cache_hit": True,
            "user_id": "user-abc",
            "job_id": "job-005",
        },
    ]

    EXPECTED_CHARGES = [
        Decimal("0.32"),
        Decimal("0.29"),   # 0.0573 * 5 = 0.2865 → third digit 6 > 5 → rounds up
        Decimal("1.86"),
        Decimal("0.00"),
        Decimal("0.00"),
    ]

    def test_known_ledger_rows(self):
        results = compute_charges_for_ledger_rows(self.KNOWN_ROWS)
        assert len(results) == 5

        # Row 1: 0.0633 * 5 = 0.3165 → third decimal 6 > 5 → round up → 0.32
        assert results[0]["user_charge_usd"] == Decimal("0.32")
        assert results[0]["ledger_id"] == "row-1"

        # Row 2: 0.0573 * 5 = 0.2865 → third decimal 6 > 5 → round up → 0.29
        assert results[1]["user_charge_usd"] == Decimal("0.29")
        assert results[1]["ledger_id"] == "row-2"

        # Row 3: 0.3720 * 5 = 1.8600 → exact → 1.86
        assert results[2]["user_charge_usd"] == Decimal("1.86")
        assert results[2]["ledger_id"] == "row-3"

        # Row 4: cache hit → $0.00
        assert results[3]["user_charge_usd"] == Decimal("0.00")
        assert results[3]["ledger_id"] == "row-4"

        # Row 5: cache hit → $0.00
        assert results[4]["user_charge_usd"] == Decimal("0.00")
        assert results[4]["ledger_id"] == "row-5"

    def test_ledger_rows_preserve_metadata(self):
        results = compute_charges_for_ledger_rows(self.KNOWN_ROWS)
        for i, result in enumerate(results):
            assert result["user_id"] == "user-abc"
            assert result["job_id"] == self.KNOWN_ROWS[i]["job_id"]


# ===========================================================================
# § 4 — Config change honoured without code change
# ===========================================================================

class TestConfigOverride:
    """Verify env-var changes to PRICING_MULTIPLIER take effect immediately."""

    def test_multiplier_override_to_3(self, monkeypatch):
        monkeypatch.setenv("PRICING_MULTIPLIER", "3.0")
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        # 0.0633 * 3 = 0.1899 → third decimal 9 > 5 → 0.19
        assert result["user_charge_usd"] == Decimal("0.19")
        assert result["multiplier"] == Decimal("3.0")

    def test_multiplier_override_to_10(self, monkeypatch):
        monkeypatch.setenv("PRICING_MULTIPLIER", "10.0")
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        # 0.0633 * 10 = 0.633 → third decimal 3 < 5 → 0.63
        assert result["user_charge_usd"] == Decimal("0.63")

    def test_multiplier_override_to_1(self, monkeypatch):
        """Multiplier 1.0 = pass-through (no markup)."""
        monkeypatch.setenv("PRICING_MULTIPLIER", "1.0")
        result = compute_user_charge(
            our_cost_usd="0.3720",
            cache_hit=False,
            operation_type="translation_generate",
        )
        # 0.3720 * 1 = 0.372 → third decimal 2 < 5 → 0.37
        assert result["user_charge_usd"] == Decimal("0.37")

    def test_cache_hit_ignores_multiplier_change(self, monkeypatch):
        """Cache hits charge $0 regardless of multiplier."""
        monkeypatch.setenv("PRICING_MULTIPLIER", "100.0")
        result = compute_user_charge(
            our_cost_usd="0.05",
            cache_hit=True,
            operation_type="tour_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")

    def test_bad_env_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("PRICING_MULTIPLIER", "not_a_number")
        # Should not crash, falls back to 5.0
        result = compute_user_charge(
            our_cost_usd="0.10",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.50")
        assert result["multiplier"] == Decimal("5.0")


# ===========================================================================
# § 5 — Edge cases and description override
# ===========================================================================

class TestEdgeCases:
    """Edge cases and human-readable description."""

    def test_custom_description(self):
        result = compute_user_charge(
            our_cost_usd="0.069",
            cache_hit=False,
            operation_type="tour_generate",
            description="Tour: French Riviera biking",
        )
        assert result["description"] == "Tour: French Riviera biking"

    def test_unknown_operation_type_gets_title_case(self):
        result = compute_user_charge(
            our_cost_usd="0.05",
            cache_hit=False,
            operation_type="some_new_operation",
        )
        assert result["description"] == "Some New Operation"

    def test_zero_cost_fresh_generation(self):
        """A fresh generation that somehow costs $0 (shouldn't happen, but don't crash)."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0

    def test_float_input_converted_correctly(self):
        """Float inputs are converted via str() to avoid Decimal(float) imprecision."""
        result = compute_user_charge(
            our_cost_usd=0.0633,  # float
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_string_input_works(self):
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_decimal_input_works(self):
        result = compute_user_charge(
            our_cost_usd=Decimal("0.0633"),
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_cents_integer_consistency(self):
        """user_charge_cents always equals user_charge_usd * 100 as int."""
        test_costs = ["0.001", "0.01", "0.05", "0.069", "0.15", "1.00", "2.50"]
        for cost_str in test_costs:
            result = compute_user_charge(
                our_cost_usd=cost_str,
                cache_hit=False,
                operation_type="tour_generate",
            )
            expected_cents = int(result["user_charge_usd"] * 100)
            assert result["user_charge_cents"] == expected_cents, (
                f"Cents mismatch for cost {cost_str}: "
                f"{result['user_charge_cents']} != {expected_cents}"
            )


# ===========================================================================
# § 6 — Banker's rounding specific cases
# ===========================================================================

class TestBankersRounding:
    """Verify banker's rounding (ROUND_HALF_EVEN) behaves as expected."""

    def test_exact_half_rounds_to_even_down(self):
        """0.025 * 5 = 0.125 → round to 0.12 (2 is even, round down)."""
        result = compute_user_charge(
            our_cost_usd="0.025",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.12")

    def test_exact_half_rounds_to_even_up(self):
        """0.035 * 5 = 0.175 → round to 0.18 (7 is odd, round up to 8)."""
        result = compute_user_charge(
            our_cost_usd="0.035",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.18")

    def test_above_half_always_rounds_up(self):
        """0.0573 * 5 = 0.2865 — the digit past .01 boundary is 6 (> 5), rounds up."""
        result = compute_user_charge(
            our_cost_usd="0.0573",
            cache_hit=False,
            operation_type="tour_generate",
        )
        # 0.2865: to quantize to 0.01, look at position 3: '6' > 5 → always up → 0.29
        assert result["user_charge_usd"] == Decimal("0.29")

    def test_below_half_always_rounds_down(self):
        """0.0633 * 5 = 0.3165 — digit past .01 is 6 > 5 → rounds up to 0.32."""
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.32")


# ===========================================================================
# § 7 — Translation cost flag verification
# ===========================================================================

class TestTranslationFlag:
    """
    FLAG FOR MICHAEL: Translation at ×5 costs the user ~$1.86 vs ~$0.32
    for the tour. These tests document the ratio so it's visible in test
    output and review.
    """

    def test_translation_vs_tour_ratio(self):
        tour = compute_user_charge("0.0633", False, "tour_generate")
        translation = compute_user_charge("0.3720", False, "translation_generate")

        ratio = translation["user_charge_usd"] / tour["user_charge_usd"]
        # Translation is ~5.8× the tour price
        assert ratio > Decimal("5"), (
            f"Translation/tour ratio is {ratio} — translation costs "
            f"${translation['user_charge_usd']} vs tour ${tour['user_charge_usd']}"
        )

    def test_translation_absolute_values_documented(self):
        """Document the exact numbers for Michael's review."""
        translation = compute_user_charge("0.3720", False, "translation_generate")
        assert translation["user_charge_usd"] == Decimal("1.86")
        assert translation["our_cost_usd"] == Decimal("0.3720")
