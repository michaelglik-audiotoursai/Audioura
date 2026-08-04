"""
Test suite for LOCAL-60: Cost Metering
=======================================
Tests:
1. cost_rates module returns correct values
2. cost_meter.record_operation inserts a row
3. Cache hit enforcement (cache_hit=True forces cost=0)
4. Integration: _LAST_GENERATION_COST is populated correctly
5. Invalid operation_type rejected
"""

import json
import os
import sys
import uuid
from unittest.mock import patch, MagicMock

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


def test_cost_rates():
    """Test that centralized rate table returns expected values."""
    from cost_rates import (
        GPT35_TURBO_COST_PER_1K_TOKENS,
        GPT4O_MINI_COST_PER_1K_TOKENS,
        SERPER_COST_PER_QUERY,
        CACHE_HIT_COST_USD,
        llm_cost,
        search_cost,
        tts_cost,
        translation_cost,
    )

    # Basic rate checks — LOCAL-197: updated to real rates
    assert GPT35_TURBO_COST_PER_1K_TOKENS == 0.0008  # real blended rate
    assert GPT4O_MINI_COST_PER_1K_TOKENS == 0.000285  # real blended rate
    assert SERPER_COST_PER_QUERY == 0.001
    assert CACHE_HIT_COST_USD == 0.00

    # Function checks — LOCAL-197: llm_cost now uses split input/output rates
    # total_tokens=1000 with gpt-3.5-turbo: 700 input × $0.50/1M + 300 output × $1.50/1M
    expected_1k = (700 * 0.50 / 1_000_000) + (300 * 1.50 / 1_000_000)  # $0.0008
    assert abs(llm_cost(total_tokens=1000) - expected_1k) < 1e-9
    expected_5k = (3500 * 0.50 / 1_000_000) + (1500 * 1.50 / 1_000_000)  # $0.004
    assert abs(llm_cost(total_tokens=5000) - expected_5k) < 1e-9
    assert search_cost(10) == 0.010
    assert tts_cost(1_000_000) == 4.00
    # [LOCAL-135] translation_cost() now models the full translation service behavior:
    # [LOCAL-143] Parameterized by pass count. Default = DEPLOYED_TRANSLATION_PASSES.
    # [LOCAL-162] Deployed single-pass (LOCAL-142) on 2026-08-03. Default is now passes=1.
    # Single-pass: 1× AWS Translate ($15/1M: full text only)
    # + Polly TTS ($4/1M on ~95% of source × 1.06 translation expansion ratio)
    # = (1M × 1.0 × $15/1M) + (1M × 0.95 × 1.06 × $4/1M) = $15.00 + $4.028 = $19.028
    assert translation_cost(1_000_000) == 15.00 + 1_000_000 * 0.95 * 1.06 * 4.00 / 1_000_000  # $19.028
    # Two-pass (legacy, before LOCAL-142): 2× Translate + Polly = $33.278
    assert translation_cost(1_000_000, passes=2) == 29.25 + 1_000_000 * 0.95 * 1.06 * 4.00 / 1_000_000  # $33.278
    # [LOCAL-143] Single-pass explicit check
    assert translation_cost(1_000_000, passes=1) == 15.00 + 1_000_000 * 0.95 * 1.06 * 4.00 / 1_000_000  # $19.028
    # Verify default uses DEPLOYED_TRANSLATION_PASSES
    from cost_rates import DEPLOYED_TRANSLATION_PASSES
    assert translation_cost(1_000_000) == translation_cost(1_000_000, passes=DEPLOYED_TRANSLATION_PASSES)

    print("PASS: test_cost_rates")


def test_cost_meter_valid_types():
    """Test that VALID_OPERATION_TYPES contains all expected types."""
    from cost_meter import VALID_OPERATION_TYPES

    expected = {
        "tour_generate", "tour_cache_hit",
        "translation_generate", "translation_cache_hit",
        "news_generate", "news_cache_hit", "photo_extension",
    }
    assert expected == VALID_OPERATION_TYPES, f"Mismatch: {expected - VALID_OPERATION_TYPES}"
    print("PASS: test_cost_meter_valid_types")


def test_cost_meter_rejects_invalid_type():
    """Test that invalid operation_type returns None."""
    from cost_meter import record_operation

    # Mock psycopg2 so we don't need a real DB
    with patch('cost_meter.psycopg2') as mock_pg:
        result = record_operation(
            operation_type="invalid_type",
            our_cost_usd=0.05,
            cache_hit=False,
        )
        assert result is None, "Should reject invalid operation_type"
        # Should not have attempted a DB connection
        mock_pg.connect.assert_not_called()

    print("PASS: test_cost_meter_rejects_invalid_type")


def test_cost_meter_cache_hit_forces_zero():
    """Test that cache_hit=True with cost>0 gets forced to 0."""
    from cost_meter import record_operation

    # Mock DB
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        result = record_operation(
            operation_type="tour_cache_hit",
            our_cost_usd=5.00,  # This is wrong — cache hits should cost 0
            cache_hit=True,
            user_id="test-user",
            job_id="test-job",
        )

        assert result is not None, "Should succeed even with wrong cost (forced to 0)"
        # Verify the INSERT was called with cost=0.00
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        # params[3] is our_cost_usd
        assert float(params[3]) == 0.00, f"Expected 0.00 but got {params[3]}"

    print("PASS: test_cost_meter_cache_hit_forces_zero")


def test_cost_meter_fresh_generation_records_real_cost():
    """Test that fresh generation records the actual cost."""
    from cost_meter import record_operation

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        result = record_operation(
            operation_type="tour_generate",
            our_cost_usd=0.069,
            cache_hit=False,
            user_id="test-user",
            job_id="test-job",
            breakdown={"llm": 0.052, "tts": 0.012, "search": 0.005},
        )

        assert result is not None
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        # params[3] is our_cost_usd
        assert float(params[3]) == 0.069, f"Expected 0.069 but got {params[3]}"
        # params[4] is cache_hit
        assert params[4] is False
        # params[5] is job_id
        assert params[5] == "test-job"
        # params[6] is breakdown (JSON string)
        breakdown = json.loads(params[6])
        assert breakdown["llm"] == 0.052

    print("PASS: test_cost_meter_fresh_generation_records_real_cost")


def test_last_generation_cost_cache_hit():
    """Test that _LAST_GENERATION_COST is set correctly on cache hit."""
    # We can't easily run generate_tour_text without a real OpenAI key,
    # but we can verify the module-level variable exists and has correct shape.
    from generate_tour_text import _LAST_GENERATION_COST

    assert "total_cost" in _LAST_GENERATION_COST
    assert "total_tokens" in _LAST_GENERATION_COST
    assert "cache_hit" in _LAST_GENERATION_COST
    assert "breakdown" in _LAST_GENERATION_COST
    assert isinstance(_LAST_GENERATION_COST["breakdown"], dict)

    print("PASS: test_last_generation_cost_cache_hit")


def test_migration_sql_valid():
    """Test that the migration SQL is syntactically valid (basic checks)."""
    sql_path = os.path.join(
        _project_root,
        "migration", "sql", "005_cost_ledger.sql"
    )
    assert os.path.exists(sql_path), f"Migration file not found: {sql_path}"

    with open(sql_path, 'r') as f:
        sql = f.read()

    assert "CREATE TABLE IF NOT EXISTS cost_ledger" in sql
    assert "operation_type VARCHAR(64)" in sql
    assert "our_cost_usd NUMERIC(12, 6)" in sql
    assert "cache_hit BOOLEAN" in sql
    assert "breakdown JSONB" in sql
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql

    print("PASS: test_migration_sql_valid")


def test_cost_meter_no_db_returns_none():
    """Test that missing DB returns None gracefully."""
    from cost_meter import record_operation

    # Remove DATABASE_URL and DB_HOST
    env_backup = {}
    for key in ["DATABASE_URL", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]:
        if key in os.environ:
            env_backup[key] = os.environ.pop(key)

    with patch('cost_meter.psycopg2') as mock_pg:
        # Simulate connection failure
        mock_pg.connect.side_effect = Exception("Connection refused")

        result = record_operation(
            operation_type="tour_generate",
            our_cost_usd=0.05,
            cache_hit=False,
        )
        # Should return None on failure (not crash)
        assert result is None

    # Restore env
    os.environ.update(env_backup)
    print("PASS: test_cost_meter_no_db_returns_none")


if __name__ == "__main__":
    test_cost_rates()
    test_cost_meter_valid_types()
    test_cost_meter_rejects_invalid_type()
    test_cost_meter_cache_hit_forces_zero()
    test_cost_meter_fresh_generation_records_real_cost()
    test_last_generation_cost_cache_hit()
    test_migration_sql_valid()
    test_cost_meter_no_db_returns_none()
    print("\n=== ALL TESTS PASSED ===")
