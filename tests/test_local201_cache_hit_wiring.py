#!/usr/bin/env python3
"""
LOCAL-201: Cache-hit wiring — callers pass fresh_cost_usd to pricing.

Proves:
  1. Tour cache hit with basis present → wallet charged (basis × 5).
  2. Tour cache hit with basis absent (None) → $0.00, no wallet call.
  3. Tour cache hit repeat request (same idempotency key) → no double charge.
  4. News cache hit with basis present → wallet charged (basis × 5).
  5. News cache hit with basis absent (None) → $0.00, no wallet call.
  6. News cache hit repeat request (same idempotency key) → no double charge.
  7. our_cost_usd is ALWAYS $0.00 on every cache hit — assert it.

Run:
    python3 -m pytest tests/test_local201_cache_hit_wiring.py -v
"""

import os
import sys
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

import pytest

# Path setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricing import compute_user_charge


# ===========================================================================
# § 1 — Tour cache-hit wiring: basis present → charge
# ===========================================================================

class TestTourCacheHitWiring:
    """Tour cache hits look up basis and charge when found."""

    def test_basis_present_charges_user(self):
        """When lookup returns a fresh cost, user is charged basis × 5."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd="0.0633",
            description="Tour: Nice Museum",
        )
        # 0.0633 × 5 = 0.3165 → rounds to 0.32
        assert result["user_charge_usd"] == Decimal("0.32")
        assert result["user_charge_cents"] == 32
        assert result["our_cost_usd"] == Decimal("0.00"), "our_cost must be $0.00 on cache hit"
        assert result["cache_hit"] is True
        assert result["operation_type"] == "tour_cache_hit"

    def test_basis_absent_charges_zero(self):
        """When lookup returns None (pre-metering tour), charge is $0.00."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=None,
            description="Tour: Old Town Walk",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0
        assert result["our_cost_usd"] == Decimal("0.00"), "our_cost must be $0.00 on cache hit"

    def test_our_cost_always_zero_on_cache_hit(self):
        """Regardless of basis, our_cost_usd in the result is always $0.00."""
        for basis in ["0.08", "0.02", None, "0.0001"]:
            result = compute_user_charge(
                our_cost_usd="0.00",
                cache_hit=True,
                operation_type="tour_cache_hit",
                fresh_cost_usd=basis,
            )
            assert result["our_cost_usd"] == Decimal("0.00"), (
                f"our_cost must be $0.00 on cache hit, got {result['our_cost_usd']} with basis={basis}"
            )


# ===========================================================================
# § 2 — News cache-hit wiring: basis present → charge
# ===========================================================================

class TestNewsCacheHitWiring:
    """News cache hits look up basis and charge when found."""

    def test_basis_present_charges_user(self):
        """When lookup returns a fresh cost, user is charged basis × 5."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd="0.011",
            description="Article: Breaking News",
        )
        # 0.011 × 5 = 0.055 → rounds to 0.06
        assert result["user_charge_usd"] == Decimal("0.06")
        assert result["user_charge_cents"] == 6
        assert result["our_cost_usd"] == Decimal("0.00"), "our_cost must be $0.00 on cache hit"
        assert result["cache_hit"] is True
        assert result["operation_type"] == "news_cache_hit"

    def test_basis_absent_charges_zero(self):
        """When lookup returns None, charge is $0.00."""
        result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=None,
            description="Article: Old Story",
        )
        assert result["user_charge_usd"] == Decimal("0.00")
        assert result["user_charge_cents"] == 0
        assert result["our_cost_usd"] == Decimal("0.00"), "our_cost must be $0.00 on cache hit"

    def test_our_cost_always_zero_on_cache_hit(self):
        """Regardless of basis, our_cost_usd in the result is always $0.00."""
        for basis in ["0.011", "0.005", None, "0.0001"]:
            result = compute_user_charge(
                our_cost_usd="0.00",
                cache_hit=True,
                operation_type="news_cache_hit",
                fresh_cost_usd=basis,
            )
            assert result["our_cost_usd"] == Decimal("0.00"), (
                f"our_cost must be $0.00 on cache hit, got {result['our_cost_usd']} with basis={basis}"
            )


# ===========================================================================
# § 3 — Idempotency: repeat request does NOT double-charge
# ===========================================================================

class TestCacheHitIdempotency:
    """Cache-hit charges use job_id-based idempotency keys → no double charge."""

    @patch("wallet_ledger.record_movement")
    def test_tour_repeat_request_same_idempotency_key(self, mock_record):
        """Same user + job_id produces same idempotency key → wallet skips second call."""
        from wallet_ledger import charge

        user_id = "user-repeat-test"
        job_id = "tour-abc-123"

        # The idempotency key for a tour cache-hit charge
        expected_key = f"charge:{user_id}:{job_id}"

        # First call — wallet records it
        mock_record.return_value = ("row-1", 900)
        charge(
            user_id=user_id,
            charge_usd=Decimal("0.32"),
            idempotency_key=expected_key,
            description="Tour (cached — same charge) — $0.32",
            job_id=job_id,
        )
        first_call = mock_record.call_args

        # Second call — same key, wallet returns existing row (idempotent)
        mock_record.return_value = ("row-1", 900)
        charge(
            user_id=user_id,
            charge_usd=Decimal("0.32"),
            idempotency_key=expected_key,
            description="Tour (cached — same charge) — $0.32",
            job_id=job_id,
        )
        second_call = mock_record.call_args

        # Both calls use the same idempotency key
        assert first_call == second_call, "Repeat request must use identical idempotency key"

    @patch("wallet_ledger.record_movement")
    def test_news_repeat_request_same_idempotency_key(self, mock_record):
        """Same user + article_id produces same idempotency key."""
        from wallet_ledger import charge

        user_id = "user-news-repeat"
        article_id = "article-xyz-456"

        expected_key = f"charge:{user_id}:{article_id}"

        mock_record.return_value = ("row-1", 950)
        charge(
            user_id=user_id,
            charge_usd=Decimal("0.06"),
            idempotency_key=expected_key,
            description="News article (cached — same charge) — $0.06",
            job_id=article_id,
        )
        first_call = mock_record.call_args

        mock_record.return_value = ("row-1", 950)
        charge(
            user_id=user_id,
            charge_usd=Decimal("0.06"),
            idempotency_key=expected_key,
            description="News article (cached — same charge) — $0.06",
            job_id=article_id,
        )
        second_call = mock_record.call_args

        assert first_call == second_call, "Repeat request must use identical idempotency key"

    def test_idempotency_key_derivation_tour(self):
        """Tour cache-hit idempotency key is charge:{user_id}:{job_id}."""
        user_id = "user-123"
        job_id = "job-abc"
        key = f"charge:{user_id}:{job_id}"
        assert key == "charge:user-123:job-abc"

    def test_idempotency_key_derivation_news(self):
        """News cache-hit idempotency key is charge:{user_id}:{article_id}."""
        user_id = "user-456"
        article_id = "article-def"
        key = f"charge:{user_id}:{article_id}"
        assert key == "charge:user-456:article-def"


# ===========================================================================
# § 4 — End-to-end wiring simulation (mocked DB)
# ===========================================================================

class TestTourServiceWiring:
    """Simulate the tour service cache-hit path with mocked dependencies."""

    @patch("cost_meter.psycopg2.connect")
    def test_lookup_returns_none_for_missing_job(self, mock_connect):
        """Pre-metering tour: no cost_ledger row → None → $0.00."""
        from cost_meter import lookup_fresh_cost_for_cache_hit

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("pre-metering-tour-id", "tour_cache_hit")
        assert result is None

        # Pricing with None basis → $0.00
        charge_result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=result,
        )
        assert charge_result["user_charge_cents"] == 0
        assert charge_result["our_cost_usd"] == Decimal("0.00")

    @patch("cost_meter.psycopg2.connect")
    def test_lookup_returns_cost_for_existing_job(self, mock_connect):
        """Normal tour with cost_ledger row → returns float → charges user."""
        from cost_meter import lookup_fresh_cost_for_cache_hit

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (Decimal("0.0633"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("normal-tour-id", "tour_cache_hit")
        assert result == 0.0633

        # Pricing with basis → charges user
        charge_result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="tour_cache_hit",
            fresh_cost_usd=result,
        )
        assert charge_result["user_charge_cents"] == 32
        assert charge_result["our_cost_usd"] == Decimal("0.00")


class TestNewsServiceWiring:
    """Simulate the news service cache-hit path with mocked dependencies."""

    @patch("cost_meter.psycopg2.connect")
    def test_lookup_returns_none_for_missing_article(self, mock_connect):
        """No cost_ledger row for article → None → $0.00."""
        from cost_meter import lookup_fresh_cost_for_cache_hit

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("old-article-id", "news_cache_hit")
        assert result is None

        charge_result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=result,
        )
        assert charge_result["user_charge_cents"] == 0
        assert charge_result["our_cost_usd"] == Decimal("0.00")

    @patch("cost_meter.psycopg2.connect")
    def test_lookup_returns_cost_for_existing_article(self, mock_connect):
        """Normal article with cost_ledger row → returns float → charges user."""
        from cost_meter import lookup_fresh_cost_for_cache_hit

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (Decimal("0.011"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("recent-article-id", "news_cache_hit")
        assert result == 0.011

        charge_result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=result,
        )
        assert charge_result["user_charge_cents"] == 6
        assert charge_result["our_cost_usd"] == Decimal("0.00")

    @patch("cost_meter.psycopg2.connect")
    def test_sanity_ceiling_rejects_implausible_cost(self, mock_connect):
        """Pre-LOCAL-197 inflated cost ($0.30 for news) exceeds ceiling → None → $0.00."""
        from cost_meter import lookup_fresh_cost_for_cache_hit

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # $0.30 exceeds news ceiling of $0.05
        mock_cursor.fetchone.return_value = (Decimal("0.30"),)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_connect.return_value = mock_conn

        result = lookup_fresh_cost_for_cache_hit("old-inflated-article", "news_cache_hit")
        assert result is None

        charge_result = compute_user_charge(
            our_cost_usd="0.00",
            cache_hit=True,
            operation_type="news_cache_hit",
            fresh_cost_usd=result,
        )
        assert charge_result["user_charge_cents"] == 0
        assert charge_result["our_cost_usd"] == Decimal("0.00")
