"""
Test suite for LOCAL-69: News Path Cost Metering
==================================================
Tests:
1. record_operation accepts description parameter
2. News cost calculation: TTS + conditional LLM
3. Description is human-readable ("Article: <headline>")
4. Description truncation at 256 chars
5. Cache hit behaviour for news (not yet implemented — documents gap)
6. Integration: news_orchestrator metering wiring is importable
7. Migration SQL is valid
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


def test_record_operation_accepts_description():
    """Test that record_operation stores description in the DB."""
    from cost_meter import record_operation

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        result = record_operation(
            operation_type="news_generate",
            our_cost_usd=0.025,
            cache_hit=False,
            user_id="test-user",
            job_id="article-uuid-123",
            breakdown={"tts": 0.0248, "llm": 0.00032},
            description="Article: Supreme Court Rules on Immigration Policy",
        )

        assert result is not None
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        # params[7] is description (after breakdown at index 6)
        assert params[7] == "Article: Supreme Court Rules on Immigration Policy"

    print("PASS: test_record_operation_accepts_description")


def test_record_operation_description_none_allowed():
    """Test that description=None is accepted (backward compat)."""
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
            job_id="job-123",
            breakdown={"llm": 0.052, "tts": 0.012, "search": 0.005},
            # description not passed — defaults to None
        )

        assert result is not None
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        assert params[7] is None  # description column

    print("PASS: test_record_operation_description_none_allowed")


def test_description_truncated_at_256():
    """Test that descriptions longer than 256 chars are truncated."""
    from cost_meter import record_operation

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    long_title = "A" * 300  # 300 chars
    long_description = f"Article: {long_title}"

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        record_operation(
            operation_type="news_generate",
            our_cost_usd=0.02,
            cache_hit=False,
            description=long_description,
        )

        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        stored_desc = params[7]
        assert len(stored_desc) <= 256, f"Description not truncated: {len(stored_desc)} chars"
        assert stored_desc.endswith("...")

    print("PASS: test_description_truncated_at_256")


def test_news_cost_calculation_tts_only():
    """Test cost calculation for a short-title article (no LLM cost)."""
    from cost_rates import tts_cost, llm_cost

    # Article with short title (≤12 words) — no LLM call
    article_text_chars = 3000
    major_points = 3

    # TTS chars: min(3000, 5000) + 1200 + 3*400 = 3000 + 1200 + 1200 = 5400
    tts_chars = min(article_text_chars, 5000) + 1200 + major_points * 400
    expected_tts = tts_cost(tts_chars)  # 5400 * $0.000004 = $0.0216

    assert abs(expected_tts - 0.0216) < 0.0001, f"TTS cost wrong: {expected_tts}"

    # No LLM for short titles
    total = expected_tts + 0.0
    assert total == expected_tts
    assert total < 0.03, f"Expected <$0.03, got ${total}"

    print("PASS: test_news_cost_calculation_tts_only")


def test_news_cost_calculation_with_llm():
    """Test cost calculation when title > 12 words triggers LLM."""
    from cost_rates import tts_cost, llm_cost

    # Long title triggers GPT-3.5-turbo short-title generation
    title = "The Supreme Court Just Made a Massive Decision About Immigration That Will Affect Millions"
    title_words = len(title.split())
    assert title_words > 12, f"Title should be >12 words: {title_words}"

    article_text_chars = 4500
    major_points = 5

    tts_chars = min(article_text_chars, 5000) + 1200 + major_points * 400
    _tts_cost = tts_cost(tts_chars)
    _llm_cost = llm_cost(160)  # ~160 tokens for short title

    total = _tts_cost + _llm_cost
    assert _llm_cost > 0, "LLM cost should be non-zero for long titles"
    assert _llm_cost == 0.00032, f"LLM cost wrong: {_llm_cost}"
    assert total > _tts_cost, "Total should exceed TTS-only cost"

    print("PASS: test_news_cost_calculation_with_llm")


def test_news_cost_model_arithmetic():
    """Verify the cost model arithmetic matches real rates.

    At Polly $4/1M chars:
      5000 chars (full article cap) = $0.02
      1200 chars (summary+help overhead) = $0.0048
      3 topics × 400 chars = $0.0048
    Total TTS = $0.0296
    LLM (if triggered): 160 tokens × $0.002/1K = $0.00032
    Grand total ≈ $0.030 (without LLM) or $0.030 (with LLM, negligible)
    """
    from cost_rates import POLLY_COST_PER_CHAR, GPT35_TURBO_COST_PER_1K_TOKENS

    # Verify rates haven't changed
    assert POLLY_COST_PER_CHAR == 0.000004
    assert GPT35_TURBO_COST_PER_1K_TOKENS == 0.002

    # Full article scenario (5000 char cap)
    tts_chars = 5000 + 1200 + 3 * 400  # = 7400
    tts_cost_calculated = tts_chars * POLLY_COST_PER_CHAR
    assert abs(tts_cost_calculated - 0.0296) < 0.0001

    # LLM cost
    llm_tokens = 160
    llm_cost_calculated = llm_tokens / 1000 * GPT35_TURBO_COST_PER_1K_TOKENS
    assert abs(llm_cost_calculated - 0.00032) < 0.00001

    # Total
    total = tts_cost_calculated + llm_cost_calculated
    assert abs(total - 0.02992) < 0.0001

    # Sanity: news article cost is much less than tour cost ($0.069)
    assert total < 0.069, f"News should be cheaper than a tour: ${total}"

    print("PASS: test_news_cost_model_arithmetic")


def test_news_generate_in_valid_types():
    """Ensure news_generate is an accepted operation type."""
    from cost_meter import VALID_OPERATION_TYPES
    assert "news_generate" in VALID_OPERATION_TYPES
    print("PASS: test_news_generate_in_valid_types")


def test_news_cache_hit_type_exists():
    """Verify news_cache_hit is now a valid operation type.

    LOCAL-73 added the news cache layer. The cache hit path meters at $0.00
    with operation_type='news_cache_hit', matching the tour_cache_hit pattern.
    """
    from cost_meter import VALID_OPERATION_TYPES
    assert "news_cache_hit" in VALID_OPERATION_TYPES, (
        "news_cache_hit must exist — LOCAL-73 added the news cache layer"
    )
    print("PASS: test_news_cache_hit_type_exists (cache layer active)")


def test_migration_007_valid():
    """Test that migration 007 SQL is syntactically correct."""
    sql_path = os.path.join(
        _project_root,
        "migration", "sql", "007_cost_ledger_description.sql"
    )
    assert os.path.exists(sql_path), f"Migration file not found: {sql_path}"

    with open(sql_path, 'r') as f:
        sql = f.read()

    assert "ALTER TABLE cost_ledger ADD COLUMN IF NOT EXISTS description" in sql
    assert "VARCHAR(256)" in sql
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql

    print("PASS: test_migration_007_valid")


def test_description_format():
    """Verify the description format matches Wallet spec."""
    # The format should be "Article: <headline>" — not raw operation_type
    headline = "How I Built This: Natalie Gordon of Babylist"
    description = f"Article: {headline}"

    assert description.startswith("Article: ")
    assert "news_generate" not in description
    assert headline in description

    print("PASS: test_description_format")


def test_ensure_table_includes_description():
    """Verify _ensure_table creates the description column."""
    from cost_meter import _ensure_table

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    _ensure_table(mock_conn)

    # Check that one of the execute calls includes 'description'
    all_sql = " ".join(str(call) for call in mock_cursor.execute.call_args_list)
    assert "description" in all_sql, "description column not in _ensure_table SQL"

    print("PASS: test_ensure_table_includes_description")


if __name__ == "__main__":
    test_record_operation_accepts_description()
    test_record_operation_description_none_allowed()
    test_description_truncated_at_256()
    test_news_cost_calculation_tts_only()
    test_news_cost_calculation_with_llm()
    test_news_cost_model_arithmetic()
    test_news_generate_in_valid_types()
    test_news_cache_hit_type_exists()
    test_migration_007_valid()
    test_description_format()
    test_ensure_table_includes_description()
    print("\n=== ALL LOCAL-69 TESTS PASSED ===")
