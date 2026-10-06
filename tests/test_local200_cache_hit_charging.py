#!/usr/bin/env python3
"""
LOCAL-200: Cache-hit charging — tours and news charge the same as fresh.

Proves:
  1. tour_cache_hit with fresh_cost_usd charges basis × 5.
  2. news_cache_hit with fresh_cost_usd charges basis × 5.
  3. tour_cache_hit WITHOUT fresh_cost_usd charges $0.00 (no-ledger-row case).
  4. news_cache_hit WITHOUT fresh_cost_usd charges $0.00 (no-ledger-row case).
  5. our_cost_usd is ALWAYS $0.00 on cache hits (accounting truth preserved).
  6. Pre-LOCAL-197 sanity ceiling rejects implausible costs → $0.00 charge.
  7. Translation cache-hit behaviour unchanged by LOCAL-200.
  8. Wallet descriptions are correct for all cache-hit types.
  9. lookup_fresh_cost_for_cache_hit returns None for missing/implausible rows.
 10. projected_costs updated for tour/news cache hits.

Run:
    python3 -m pytest tests/test_local200_cache_hit_charging.py -v
"""

import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing import compute_user_charge, _CACHE_HIT_CHARGE_TYPES, _OPERATION_LABELS
from cost_meter import (
    lookup_fresh_cost_for_cache_hit,
    _FRESH_COST_SANITY_CEILING,
    _CACHE_HIT_TO_FRESH_TYPE,
)
from projected_costs import PROJECTED_COSTS, get_projected_cost_cents


# Ensure clean config state
@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("PRICING_MULTIPLIER", raising=False)
    monkeypatch.delenv("CACHE_HIT_COST_USD", raising=False)


# ===========================================================================
# § 1 — tour_cache_hit charges when fresh_cost_usd is provided
# ===========================================================================

class TestTourCacheHitCharges:
    """Tour cache hits charge the user the same as a fresh tour (LOCAL-200)."""

    def test_tour_cache_hit_with_fresh_cost(self):
        """Typical tour: our_cost=$0.0633 → user charge $0.32."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
        )
        # 0.0633 × 5 = 0.3165 → rounds to 0.32
        assert result["user_charge_usd"] == Decimal("0.32")
        assert result["user_charge_cents"] == 32
        assert result["our_cost_usd"] == Decimal("0.00")
        assert result["cache_hit"] is True

    def test_tour_cache_hit_with_fresh_cost_second_example(self):
        """Second typical tour: our_cost=$0.0573 → user charge $0.29."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0573",
        )
        # 0.0573 × 5 = 0.2865 → rounds to 0.29
        assert result["user_charge_usd"] == Decimal("0.29")
        assert result["user_charge_cents"] == 29

    def test_tour_cache_hit_without_fresh_cost_charges_zero(self):
        """No ledger row found → charge $0.00 (safe fallback)."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0

    def test_tour_cache_hit_fresh_cost_as_float(self):
        """Float input for fresh_cost_usd works correctly."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=0.0633,
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_tour_cache_hit_fresh_cost_as_decimal(self):
        """Decimal input for fresh_cost_usd works correctly."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=Decimal("0.0633"),
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_tour_cache_hit_our_cost_stays_zero(self):
        """Accounting truth: our_cost is $0.00 regardless of charge."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
        )
        assert result["our_cost_usd"] == Decimal("0.00")

    def test_tour_cache_hit_matches_fresh_tour_charge(self):
        """A cached tour and a fresh tour with the same basis produce the same charge."""
        fresh = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        cached = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
        )
        assert fresh["user_charge_usd"] == cached["user_charge_usd"]
        assert fresh["user_charge_cents"] == cached["user_charge_cents"]


# ===========================================================================
# § 2 — news_cache_hit charges when fresh_cost_usd is provided
# ===========================================================================

class TestNewsCacheHitCharges:
    """News cache hits charge the user the same as fresh article (LOCAL-200)."""

    def test_news_cache_hit_with_fresh_cost(self):
        """Typical news article: our_cost=$0.0085 → user charge $0.04."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd="0.0085",
        )
        # 0.0085 × 5 = 0.0425 → banker's: 2 is even → rounds to 0.04
        assert result["user_charge_usd"] == Decimal("0.04")
        assert result["user_charge_cents"] == 4
        assert result["our_cost_usd"] == Decimal("0.00")
        assert result["cache_hit"] is True

    def test_news_cache_hit_without_fresh_cost_charges_zero(self):
        """No ledger row found → charge $0.00 (safe fallback)."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0

    def test_news_cache_hit_our_cost_stays_zero(self):
        """Accounting truth: our_cost is $0.00 regardless of charge."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd="0.0085",
        )
        assert result["our_cost_usd"] == Decimal("0.00")

    def test_news_cache_hit_matches_fresh_news_charge(self):
        """A cached article and a fresh article with the same basis produce the same charge."""
        fresh = compute_user_charge(
            our_cost_usd="0.0085",
            cache_hit=False,
            operation_type="news_generate",
        )
        cached = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd="0.0085",
        )
        assert fresh["user_charge_usd"] == cached["user_charge_usd"]
        assert fresh["user_charge_cents"] == cached["user_charge_cents"]


# ===========================================================================
# § 3 — our_cost_usd ALWAYS $0.00 on cache hits
# ===========================================================================

class TestCacheHitOurCostZero:
    """Verify our_cost_usd field is always $0.00 on ALL cache hits."""

    @pytest.mark.parametrize("op_type,fresh_cost", [
        ("tour_cache_hit", "0.0633"),
        ("tour_cache_hit", None),
        ("news_cache_hit", "0.0085"),
        ("news_cache_hit", None),
        ("translation_cache_hit", "0.3720"),
        ("translation_cache_hit", None),
    ])
    def test_our_cost_always_zero(self, op_type, fresh_cost):
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type=op_type,
            fresh_cost_usd=fresh_cost,
        )
        assert result["our_cost_usd"] == Decimal("0.00"), (
            f"our_cost_usd must be $0.00 for {op_type} (fresh_cost={fresh_cost}), "
            f"got {result['our_cost_usd']}"
        )


# ===========================================================================
# § 4 — Pre-LOCAL-197 sanity ceiling
# ===========================================================================

class TestPreLocal197SanityCeiling:
    """Pre-LOCAL-197 inflated costs are rejected → charge $0.00."""

    def test_tour_cache_hit_implausible_cost_charges_zero(self):
        """A pre-LOCAL-197 tour cost of $0.30 (>$0.25 ceiling) → no fresh_cost passed → $0.00."""
        # The sanity check happens in lookup_fresh_cost_for_cache_hit (DB layer).
        # At the pricing layer, if fresh_cost_usd is None, charge is $0.00.
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=None,  # lookup returned None due to ceiling
        )
        assert result["user_charge_usd"] == Decimal("0.00")

    def test_sanity_ceilings_defined(self):
        """Sanity ceilings exist for all fresh generation types."""
        assert "tour_generate" in _FRESH_COST_SANITY_CEILING
        assert "news_generate" in _FRESH_COST_SANITY_CEILING
        assert "translation_generate" in _FRESH_COST_SANITY_CEILING
        # They must be positive
        for k, v in _FRESH_COST_SANITY_CEILING.items():
            assert v > 0, f"Ceiling for {k} must be positive"

    def test_sanity_ceiling_tour_rejects_inflated(self):
        """$0.30 our cost exceeds the $0.25 ceiling for tours."""
        assert 0.30 > _FRESH_COST_SANITY_CEILING["tour_generate"]

    def test_sanity_ceiling_tour_accepts_normal(self):
        """$0.08 our cost is below the $0.25 ceiling for tours."""
        assert 0.08 < _FRESH_COST_SANITY_CEILING["tour_generate"]


# ===========================================================================
# § 5 — Translation cache-hit unchanged
# ===========================================================================

class TestTranslationCacheHitUnchanged:
    """Translation cache-hit behaviour remains identical after LOCAL-200."""

    def test_translation_cache_hit_with_fresh_cost(self):
        """D45: translation cache hit charges same as fresh."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="translation_cache_hit",
            fresh_cost_usd="0.3720",
        )
        # 0.3720 × 5 = 1.8600 → $1.86
        assert result["user_charge_usd"] == Decimal("1.86")
        assert result["user_charge_cents"] == 186
        assert result["our_cost_usd"] == Decimal("0.00")
        assert result["description"] == "Translation (cached — same charge)"

    def test_translation_cache_hit_without_fresh_cost(self):
        """Translation cache hit without fresh_cost charges $0.00 (safe fallback)."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="translation_cache_hit",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0


# ===========================================================================
# § 6 — Wallet transaction descriptions
# ===========================================================================

class TestWalletDescriptions:
    """Wallet transaction descriptions make the cache-hit charge legible."""

    def test_tour_cache_hit_description(self):
        """Tour cache hit has '(cached — same charge)' label."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
        )
        assert result["description"] == "Tour (cached — same charge)"

    def test_news_cache_hit_description(self):
        """News cache hit has '(cached — same charge)' label."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd="0.0085",
        )
        assert result["description"] == "News article (cached — same charge)"

    def test_translation_cache_hit_description(self):
        """Translation cache hit description unchanged."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="translation_cache_hit",
            fresh_cost_usd="0.3720",
        )
        assert result["description"] == "Translation (cached — same charge)"

    def test_custom_description_overrides_default(self):
        """Callers can override the description."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
            description="Tour: Nice Museum (cached — same charge)",
        )
        assert result["description"] == "Tour: Nice Museum (cached — same charge)"

    def test_tour_cache_hit_no_fresh_cost_description(self):
        """Tour cache hit without fresh_cost still shows label (but charges $0)."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
        )
        assert result["description"] == "Tour (cached — same charge)"


# ===========================================================================
# § 7 — lookup_fresh_cost_for_cache_hit (mocked DB)
# ===========================================================================

class TestLookupFreshCost:
    """Unit tests for cost_meter.lookup_fresh_cost_for_cache_hit with mocked DB."""

    @patch("cost_meter.psycopg2.connect")
    def test_returns_cost_when_row_exists(self, mock_connect):
        """Returns the cost when a valid fresh row is found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (Decimal("0.0633"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = lambda s, *a: None
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("job-123", "tour_cache_hit")
        assert result == pytest.approx(0.0633, abs=1e-6)

    @patch("cost_meter.psycopg2.connect")
    def test_returns_none_when_no_row(self, mock_connect):
        """Returns None when no fresh generation row exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = lambda s, *a: None
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("job-orphan", "tour_cache_hit")
        assert result is None

    @patch("cost_meter.psycopg2.connect")
    def test_returns_none_when_cost_exceeds_ceiling(self, mock_connect):
        """Returns None when cost exceeds sanity ceiling (pre-LOCAL-197)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # $0.30 > $0.25 ceiling for tour_generate
        mock_cursor.fetchone.return_value = (Decimal("0.30"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = lambda s, *a: None
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("job-old", "tour_cache_hit")
        assert result is None

    @patch("cost_meter.psycopg2.connect")
    def test_returns_none_when_cost_is_zero(self, mock_connect):
        """Returns None when the stored cost is $0 (no basis to charge)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (Decimal("0.0"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = lambda s, *a: None
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("job-zero", "tour_cache_hit")
        assert result is None

    @patch("cost_meter.psycopg2.connect")
    def test_news_cache_hit_lookup(self, mock_connect):
        """News cache hit looks up news_generate rows."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (Decimal("0.0085"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = lambda s, *a: None
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("job-news", "news_cache_hit")
        assert result == pytest.approx(0.0085, abs=1e-6)

    def test_unknown_operation_type_returns_none(self):
        """Unknown operation type returns None without DB call."""
        result = lookup_fresh_cost_for_cache_hit("job-x", "unknown_cache_hit")
        assert result is None

    @patch("cost_meter._get_db_url", return_value=None)
    def test_no_db_url_returns_none(self, mock_url):
        """Returns None when no DB URL is available."""
        result = lookup_fresh_cost_for_cache_hit("job-x", "tour_cache_hit")
        assert result is None

    @patch("cost_meter.psycopg2.connect")
    def test_db_error_returns_none(self, mock_connect):
        """Returns None on DB connection error (fail-safe)."""
        mock_connect.side_effect = Exception("connection refused")
        result = lookup_fresh_cost_for_cache_hit("job-x", "tour_cache_hit")
        assert result is None


# ===========================================================================
# § 8 — Projected costs updated
# ===========================================================================

class TestProjectedCostsUpdated:
    """Projected costs for cache hits now match fresh generation."""

    def test_tour_cache_hit_projection_nonzero(self):
        """tour_cache_hit projection is now $0.40 (same as tour_generate)."""
        assert PROJECTED_COSTS["tour_cache_hit"] == Decimal("0.40")
        assert get_projected_cost_cents("tour_cache_hit") == 40

    def test_news_cache_hit_projection_nonzero(self):
        """news_cache_hit projection is now $0.06 (same as news_generate)."""
        assert PROJECTED_COSTS["news_cache_hit"] == Decimal("0.06")
        assert get_projected_cost_cents("news_cache_hit") == 6

    def test_translation_cache_hit_projection_unchanged(self):
        """translation_cache_hit projection unchanged at $2.70."""
        assert PROJECTED_COSTS["translation_cache_hit"] == Decimal("2.70")

    def test_tour_cache_hit_equals_tour_generate_projection(self):
        """Tour cache hit projection equals tour generate projection."""
        assert PROJECTED_COSTS["tour_cache_hit"] == PROJECTED_COSTS["tour_generate"]

    def test_news_cache_hit_equals_news_generate_projection(self):
        """News cache hit projection equals news generate projection."""
        assert PROJECTED_COSTS["news_cache_hit"] == PROJECTED_COSTS["news_generate"]


# ===========================================================================
# § 9 — _CACHE_HIT_CHARGE_TYPES contains all three
# ===========================================================================

class TestCacheHitChargeTypes:
    """The set of chargeable cache-hit types includes all three."""

    def test_contains_translation(self):
        assert "translation_cache_hit" in _CACHE_HIT_CHARGE_TYPES

    def test_contains_tour(self):
        assert "tour_cache_hit" in _CACHE_HIT_CHARGE_TYPES

    def test_contains_news(self):
        assert "news_cache_hit" in _CACHE_HIT_CHARGE_TYPES

    def test_labels_exist_for_all(self):
        """All three have entries in _OPERATION_LABELS."""
        for op_type in _CACHE_HIT_CHARGE_TYPES:
            assert op_type in _OPERATION_LABELS, f"Missing label for {op_type}"
            assert "cached" in _OPERATION_LABELS[op_type].lower()


# ===========================================================================
# § 10 — Existing tests still pass (regression guard)
# ===========================================================================

class TestRegressionGuard:
    """Verify fresh generation charges are unchanged."""

    def test_fresh_tour_unchanged(self):
        result = compute_user_charge(
            our_cost_usd="0.0633",
            cache_hit=False,
            operation_type="tour_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.32")

    def test_fresh_news_unchanged(self):
        result = compute_user_charge(
            our_cost_usd="0.0450",
            cache_hit=False,
            operation_type="news_generate",
        )
        assert result["user_charge_usd"] == Decimal("0.22")

    def test_fresh_translation_unchanged(self):
        result = compute_user_charge(
            our_cost_usd="0.3720",
            cache_hit=False,
            operation_type="translation_generate",
        )
        assert result["user_charge_usd"] == Decimal("1.86")
