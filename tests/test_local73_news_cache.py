#!/usr/bin/env python3
"""
Test suite for LOCAL-73: News Article Cache
=============================================
Tests:
1. news_cache_layer1 module: key generation, store, get, TTL expiration
2. cost_meter: news_cache_hit in VALID_OPERATION_TYPES, metering at $0.00
3. Orchestrator integration: cache miss → generate → store; cache hit → serve → $0.00
4. Invalidation: expired entries are not served
5. Content-hash correctness: same text = hit, different text = miss
6. Migration SQL validity

Usage:
  # Unit tests (no DB needed):
  python tests/test_local73_news_cache.py

  # Integration tests (needs Postgres on DB_PORT):
  python tests/test_local73_news_cache.py --integration

  DB config from env (same as services):
    DATABASE_URL or DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
"""

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

# Ensure project root is on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

results = []


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


# ─── Unit Tests (no DB) ─────────────────────────────────────────────────────

def test_cache_key_deterministic():
    """Same inputs → same key."""
    from news_cache_layer1 import _cache_key
    k1 = _cache_key("Hello world article text", 3)
    k2 = _cache_key("Hello world article text", 3)
    record("cache_key deterministic", k1 == k2, f"key={k1[:16]}…")


def test_cache_key_whitespace_normalized():
    """Whitespace differences don't matter."""
    from news_cache_layer1 import _cache_key
    k1 = _cache_key("Hello  world\n\narticle   text", 3)
    k2 = _cache_key("Hello world article text", 3)
    record("cache_key whitespace normalized", k1 == k2)


def test_cache_key_different_text():
    """Different text → different key."""
    from news_cache_layer1 import _cache_key
    k1 = _cache_key("Article about cats", 3)
    k2 = _cache_key("Article about dogs", 3)
    record("cache_key different text → different key", k1 != k2)


def test_cache_key_different_points():
    """Same text but different major_points_count → different key."""
    from news_cache_layer1 import _cache_key
    k1 = _cache_key("Same article text", 3)
    k2 = _cache_key("Same article text", 5)
    record("cache_key different points → different key", k1 != k2)


def test_cache_key_is_sha256():
    """Key is 64 hex chars (SHA256)."""
    from news_cache_layer1 import _cache_key
    key = _cache_key("Some article", 2)
    ok = len(key) == 64 and all(c in '0123456789abcdef' for c in key)
    record("cache_key is valid SHA256 hex", ok, f"len={len(key)}")


def test_valid_operation_types_includes_news_cache_hit():
    """news_cache_hit is in VALID_OPERATION_TYPES."""
    from cost_meter import VALID_OPERATION_TYPES
    ok = "news_cache_hit" in VALID_OPERATION_TYPES
    record("news_cache_hit in VALID_OPERATION_TYPES", ok,
           f"types={sorted(VALID_OPERATION_TYPES)}")


def test_valid_operation_types_still_has_news_generate():
    """news_generate remains in VALID_OPERATION_TYPES."""
    from cost_meter import VALID_OPERATION_TYPES
    ok = "news_generate" in VALID_OPERATION_TYPES
    record("news_generate still in VALID_OPERATION_TYPES", ok)


def test_cache_hit_metering_forces_zero_cost():
    """cache_hit=True with news_cache_hit forces cost to 0."""
    from cost_meter import record_operation

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        result = record_operation(
            operation_type="news_cache_hit",
            our_cost_usd=9.99,  # Intentionally wrong — should be forced to 0
            cache_hit=True,
            user_id="test-user",
            job_id="test-job",
        )

        assert result is not None, "Should succeed"
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        cost = float(params[3])
        ok = cost == 0.00
        record("news_cache_hit forces cost to $0.00", ok, f"cost={cost}")


def test_news_generate_records_real_cost():
    """news_generate records the actual cost passed in."""
    from cost_meter import record_operation

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('cost_meter.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn

        result = record_operation(
            operation_type="news_generate",
            our_cost_usd=0.0084,
            cache_hit=False,
            user_id="test-user",
            job_id="test-job",
            breakdown={"tts": 0.0084, "tts_chars": 2100},
        )

        assert result is not None
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        cost = float(params[3])
        cache_hit = params[4]
        ok = cost == 0.0084 and cache_hit is False
        record("news_generate records real cost", ok, f"cost={cost}, cache_hit={cache_hit}")


def test_get_cached_news_miss():
    """get_cached_news returns None when cache is empty."""
    from news_cache_layer1 import get_cached_news

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None
    mock_cursor.fetchone.return_value = None

    with patch('news_cache_layer1.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn
        result = get_cached_news("Some article text", 3, "postgresql://fake")
        ok = result is None
        record("get_cached_news returns None on miss", ok)


def test_get_cached_news_hit():
    """get_cached_news returns (article_id, audio_bytes) on hit."""
    from news_cache_layer1 import get_cached_news

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None
    # First fetchone: UPDATE ... RETURNING article_id
    # Second fetchone: SELECT news_article FROM news_audios
    mock_cursor.fetchone.side_effect = [
        ("cached-article-id-123",),
        (b"FAKE_ZIP_BYTES",),
    ]

    with patch('news_cache_layer1.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn
        result = get_cached_news("Some article text", 3, "postgresql://fake")
        ok = result is not None and result[0] == "cached-article-id-123" and result[1] == b"FAKE_ZIP_BYTES"
        record("get_cached_news returns (article_id, bytes) on hit", ok,
               f"article_id={result[0] if result else None}")


def test_store_news_success():
    """store_news inserts/upserts without error."""
    from news_cache_layer1 import store_news

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
    mock_conn.cursor.return_value.__exit__ = lambda *args: None

    with patch('news_cache_layer1.psycopg2') as mock_pg:
        mock_pg.connect.return_value = mock_conn
        result = store_news(
            article_text="Test article about technology",
            major_points_count=3,
            article_id="art-uuid-123",
            db_url="postgresql://fake",
            request_string="Tech article",
            content_length=29,
        )
        ok = result is True
        record("store_news returns True on success", ok)
        # Verify INSERT was called
        called = mock_cursor.execute.called
        record("store_news executes INSERT", called)


def test_migration_sql_valid():
    """Migration 008 SQL is syntactically reasonable."""
    sql_path = os.path.join(_project_root, "migration", "sql", "008_news_cache.sql")
    ok_exists = os.path.exists(sql_path)
    record("migration 008_news_cache.sql exists", ok_exists)
    if not ok_exists:
        return

    with open(sql_path, 'r') as f:
        sql = f.read()

    checks = [
        ("CREATE TABLE IF NOT EXISTS news_cache" in sql, "CREATE TABLE present"),
        ("cache_key VARCHAR(64) PRIMARY KEY" in sql, "cache_key is PK"),
        ("article_id VARCHAR(255)" in sql, "article_id column"),
        ("created_at TIMESTAMPTZ" in sql, "created_at with timezone"),
        ("hit_count INTEGER" in sql, "hit_count column"),
        ("BEGIN;" in sql, "transaction BEGIN"),
        ("COMMIT;" in sql, "transaction COMMIT"),
    ]
    for check_ok, label in checks:
        record(f"migration SQL: {label}", check_ok)


def test_orchestrator_has_cache_check():
    """news_orchestrator_service.py imports and calls news_cache_layer1."""
    orch_path = os.path.join(_project_root, "news_orchestrator_service.py")
    with open(orch_path, 'r') as f:
        code = f.read()

    checks = [
        ("from news_cache_layer1 import get_cached_news" in code, "imports get_cached_news"),
        ("from news_cache_layer1 import store_news" in code, "imports store_news"),
        ("news_cache_hit" in code, "references news_cache_hit operation type"),
        ("cache_hit=True" in code, "has cache_hit=True path"),
        ("cache_hit=False" in code, "has cache_hit=False path"),
        ("record_operation" in code, "calls record_operation"),
    ]
    for check_ok, label in checks:
        record(f"orchestrator: {label}", check_ok)


def test_orchestrator_cache_hit_before_generation():
    """Cache check occurs BEFORE calling generator/processor services."""
    orch_path = os.path.join(_project_root, "news_orchestrator_service.py")
    with open(orch_path, 'r') as f:
        code = f.read()

    # Find positions — look for the actual HTTP call, not the URL constant definition
    cache_check_pos = code.find("get_cached_news")
    generator_call_pos = code.find("f'{NEWS_GENERATOR_URL}")
    if generator_call_pos == -1:
        # Try alternative pattern
        generator_call_pos = code.find("NEWS_GENERATOR_URL + ")
    if generator_call_pos == -1:
        generator_call_pos = code.find("requests.post(\n            f'{NEWS_GENERATOR_URL}")
    if generator_call_pos == -1:
        # Most reliable: the actual requests.post line that calls the generator
        generator_call_pos = code.find("generator_response = requests.post")
    # The cache check must come before the generator call
    ok = 0 < cache_check_pos < generator_call_pos
    record("cache check is before generator call", ok,
           f"cache@{cache_check_pos} < generator@{generator_call_pos}")


def test_orchestrator_cache_store_after_generation():
    """Cache store occurs AFTER successful generation."""
    orch_path = os.path.join(_project_root, "news_orchestrator_service.py")
    with open(orch_path, 'r') as f:
        code = f.read()

    processor_call_pos = code.find("NEWS_PROCESSOR_URL")
    store_pos = code.find("store_news")
    ok = 0 < processor_call_pos < store_pos
    record("cache store is after processor call", ok,
           f"processor@{processor_call_pos} < store@{store_pos}")


def test_ttl_env_var_configurable():
    """NEWS_CACHE_TTL_HOURS env var is respected."""
    with patch.dict(os.environ, {"NEWS_CACHE_TTL_HOURS": "48"}):
        # Need to reimport to pick up the env var
        import importlib
        import news_cache_layer1
        importlib.reload(news_cache_layer1)
        ok = news_cache_layer1.NEWS_CACHE_TTL_HOURS == 48
        record("NEWS_CACHE_TTL_HOURS env var respected", ok,
               f"got={news_cache_layer1.NEWS_CACHE_TTL_HOURS}")
    # Reset to default
    with patch.dict(os.environ, {"NEWS_CACHE_TTL_HOURS": "24"}):
        importlib.reload(news_cache_layer1)


# ─── Integration Tests (needs Postgres) ─────────────────────────────────────

def _get_db_url():
    """Construct DB URL from env vars (matches service pattern)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5433")
    dbname = os.environ.get("DB_NAME", "audiotours")
    user = os.environ.get("DB_USER", "admin")
    password = os.environ.get("DB_PASSWORD", "password123")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def _db_available():
    try:
        import psycopg2
        conn = psycopg2.connect(_get_db_url())
        conn.close()
        return True
    except Exception:
        return False


def _ensure_test_user(cur):
    """Ensure the ITEST-CACHE user exists (FK constraint)."""
    cur.execute("""
        INSERT INTO users (secret_id, plan) VALUES ('ITEST-CACHE', 'free')
        ON CONFLICT (secret_id) DO NOTHING
    """)


def test_integration_store_and_retrieve():
    """Store a news entry, then retrieve it (real DB)."""
    import psycopg2
    from news_cache_layer1 import store_news, get_cached_news, _cache_key

    db_url = _get_db_url()
    article_text = f"Integration test article {uuid.uuid4()}"
    major_points = 2
    article_id = f"itest-{uuid.uuid4()}"

    # First, ensure the test user exists and create prerequisite rows
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    # Ensure test user exists (FK constraint from article_requests.secret_id → users.secret_id)
    cur.execute("""
        INSERT INTO users (secret_id, plan) VALUES ('ITEST-CACHE', 'free')
        ON CONFLICT (secret_id) DO NOTHING
    """)
    # Ensure article_requests row exists (FK constraint)
    cur.execute("""
        INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at, started_at)
        VALUES (%s, 'ITEST-CACHE', 'test', %s, 'finished', NOW(), NOW())
        ON CONFLICT (article_id) DO NOTHING
    """, (article_id, psycopg2.Binary(article_text.encode('utf-8'))))
    # Insert news_audios row
    cur.execute("""
        INSERT INTO news_audios (article_id, article_name, news_article, number_requested)
        VALUES (%s, 'test', %s, 1)
        ON CONFLICT DO NOTHING
    """, (article_id, psycopg2.Binary(b"FAKE_ZIP_DATA_FOR_ITEST")))
    conn.commit()
    cur.close()
    conn.close()

    # Store in cache
    stored = store_news(article_text, major_points, article_id, db_url, "Test article", len(article_text))
    record("integration: store_news succeeds", stored)

    # Retrieve from cache
    result = get_cached_news(article_text, major_points, db_url)
    ok = result is not None and result[0] == article_id and result[1] == b"FAKE_ZIP_DATA_FOR_ITEST"
    record("integration: get_cached_news returns stored entry", ok,
           f"article_id={result[0] if result else None}")

    # Different text = miss
    result2 = get_cached_news("Completely different article text", major_points, db_url)
    record("integration: different text = cache miss", result2 is None)

    # Cleanup
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    key = _cache_key(article_text, major_points)
    cur.execute("DELETE FROM news_cache WHERE cache_key = %s", (key,))
    cur.execute("DELETE FROM news_audios WHERE article_id = %s", (article_id,))
    cur.execute("DELETE FROM article_requests WHERE article_id = %s", (article_id,))
    conn.commit()
    cur.close()
    conn.close()


def test_integration_ttl_expiration():
    """Expired entries are NOT served (TTL enforcement)."""
    import psycopg2
    from news_cache_layer1 import store_news, get_cached_news, _cache_key, _ensure_table

    db_url = _get_db_url()
    article_text = f"TTL test article {uuid.uuid4()}"
    major_points = 1
    article_id = f"itest-ttl-{uuid.uuid4()}"

    # Create the prerequisite rows
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    _ensure_test_user(cur)
    cur.execute("""
        INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at, started_at)
        VALUES (%s, 'ITEST-CACHE', 'ttl-test', %s, 'finished', NOW(), NOW())
        ON CONFLICT (article_id) DO NOTHING
    """, (article_id, psycopg2.Binary(article_text.encode('utf-8'))))
    cur.execute("""
        INSERT INTO news_audios (article_id, article_name, news_article, number_requested)
        VALUES (%s, 'ttl-test', %s, 1)
        ON CONFLICT DO NOTHING
    """, (article_id, psycopg2.Binary(b"TTL_TEST_ZIP")))
    conn.commit()

    # Store in cache
    store_news(article_text, major_points, article_id, db_url)

    # Manually backdate the cache entry to 25 hours ago (past default 24h TTL)
    key = _cache_key(article_text, major_points)
    cur.execute(
        "UPDATE news_cache SET created_at = NOW() - INTERVAL '25 hours' WHERE cache_key = %s",
        (key,)
    )
    conn.commit()
    cur.close()
    conn.close()

    # Try to retrieve — should be a MISS (expired)
    result = get_cached_news(article_text, major_points, db_url)
    ok = result is None
    record("integration: expired entry = cache miss", ok,
           f"result={result[0] if result else None}")

    # Cleanup
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("DELETE FROM news_cache WHERE cache_key = %s", (key,))
    cur.execute("DELETE FROM news_audios WHERE article_id = %s", (article_id,))
    cur.execute("DELETE FROM article_requests WHERE article_id = %s", (article_id,))
    conn.commit()
    cur.close()
    conn.close()


def test_integration_hit_count_increments():
    """Each cache hit increments hit_count."""
    import psycopg2
    from news_cache_layer1 import store_news, get_cached_news, _cache_key

    db_url = _get_db_url()
    article_text = f"Hit count test {uuid.uuid4()}"
    major_points = 0
    article_id = f"itest-hits-{uuid.uuid4()}"

    # Create prerequisite rows
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    _ensure_test_user(cur)
    cur.execute("""
        INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at, started_at)
        VALUES (%s, 'ITEST-CACHE', 'hits-test', %s, 'finished', NOW(), NOW())
        ON CONFLICT (article_id) DO NOTHING
    """, (article_id, psycopg2.Binary(article_text.encode('utf-8'))))
    cur.execute("""
        INSERT INTO news_audios (article_id, article_name, news_article, number_requested)
        VALUES (%s, 'hits-test', %s, 1)
        ON CONFLICT DO NOTHING
    """, (article_id, psycopg2.Binary(b"HITS_TEST_ZIP")))
    conn.commit()
    cur.close()
    conn.close()

    store_news(article_text, major_points, article_id, db_url)

    # Hit three times
    get_cached_news(article_text, major_points, db_url)
    get_cached_news(article_text, major_points, db_url)
    get_cached_news(article_text, major_points, db_url)

    # Check hit_count
    key = _cache_key(article_text, major_points)
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT hit_count FROM news_cache WHERE cache_key = %s", (key,))
    row = cur.fetchone()
    hit_count = row[0] if row else 0
    ok = hit_count == 3
    record("integration: hit_count increments correctly", ok, f"hit_count={hit_count}")

    # Cleanup
    cur.execute("DELETE FROM news_cache WHERE cache_key = %s", (key,))
    cur.execute("DELETE FROM news_audios WHERE article_id = %s", (article_id,))
    cur.execute("DELETE FROM article_requests WHERE article_id = %s", (article_id,))
    conn.commit()
    cur.close()
    conn.close()


def test_integration_cost_ledger_news_cache_hit():
    """Metering news_cache_hit writes a $0.00 row to cost_ledger."""
    import psycopg2
    from cost_meter import record_operation

    db_url = _get_db_url()
    job_id = f"itest-meter-{uuid.uuid4()}"

    row_id = record_operation(
        operation_type="news_cache_hit",
        our_cost_usd=0.00,
        cache_hit=True,
        user_id="ITEST-CACHE",
        job_id=job_id,
        breakdown={"tts": 0.0, "source": "news_cache"},
    )

    ok_recorded = row_id is not None
    record("integration: news_cache_hit metered", ok_recorded, f"row_id={row_id}")

    if ok_recorded:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute(
            "SELECT operation_type, our_cost_usd, cache_hit FROM cost_ledger WHERE id = %s::uuid",
            (row_id,)
        )
        row = cur.fetchone()
        if row:
            op_type, cost, cache_hit = row
            ok_values = (op_type == "news_cache_hit" and float(cost) == 0.0 and cache_hit is True)
            record("integration: ledger row has correct values", ok_values,
                   f"op={op_type}, cost={cost}, cache_hit={cache_hit}")
        else:
            record("integration: ledger row has correct values", False, "row not found")

        # Cleanup
        cur.execute("DELETE FROM cost_ledger WHERE id = %s::uuid", (row_id,))
        conn.commit()
        cur.close()
        conn.close()


def test_integration_invalidate_expired():
    """invalidate_expired removes old entries."""
    import psycopg2
    from news_cache_layer1 import store_news, invalidate_expired, _cache_key, _ensure_table

    db_url = _get_db_url()
    article_text = f"Invalidation test {uuid.uuid4()}"
    article_id = f"itest-inv-{uuid.uuid4()}"

    # Create prerequisite rows
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    _ensure_test_user(cur)
    cur.execute("""
        INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at, started_at)
        VALUES (%s, 'ITEST-CACHE', 'inv-test', %s, 'finished', NOW(), NOW())
        ON CONFLICT (article_id) DO NOTHING
    """, (article_id, psycopg2.Binary(article_text.encode('utf-8'))))
    cur.execute("""
        INSERT INTO news_audios (article_id, article_name, news_article, number_requested)
        VALUES (%s, 'inv-test', %s, 1)
        ON CONFLICT DO NOTHING
    """, (article_id, psycopg2.Binary(b"INV_TEST_ZIP")))
    conn.commit()

    # Store and backdate
    store_news(article_text, 0, article_id, db_url)
    key = _cache_key(article_text, 0)
    cur.execute(
        "UPDATE news_cache SET created_at = NOW() - INTERVAL '48 hours' WHERE cache_key = %s",
        (key,)
    )
    conn.commit()
    cur.close()
    conn.close()

    # Run invalidation
    removed = invalidate_expired(db_url)
    ok = removed >= 1
    record("integration: invalidate_expired removes old entries", ok, f"removed={removed}")

    # Verify it's gone
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM news_cache WHERE cache_key = %s", (key,))
    still_there = cur.fetchone() is not None
    record("integration: expired entry is deleted", not still_there)

    # Cleanup remaining
    cur.execute("DELETE FROM news_audios WHERE article_id = %s", (article_id,))
    cur.execute("DELETE FROM article_requests WHERE article_id = %s", (article_id,))
    conn.commit()
    cur.close()
    conn.close()


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--integration", action="store_true", help="Run integration tests (needs Postgres)")
    args = ap.parse_args()

    print("=" * 70)
    print("LOCAL-73: News Cache Tests")
    print("=" * 70)

    # Unit tests (always run)
    print("\n--- Unit Tests ---")
    test_cache_key_deterministic()
    test_cache_key_whitespace_normalized()
    test_cache_key_different_text()
    test_cache_key_different_points()
    test_cache_key_is_sha256()
    test_valid_operation_types_includes_news_cache_hit()
    test_valid_operation_types_still_has_news_generate()
    test_cache_hit_metering_forces_zero_cost()
    test_news_generate_records_real_cost()
    test_get_cached_news_miss()
    test_get_cached_news_hit()
    test_store_news_success()
    test_migration_sql_valid()
    test_orchestrator_has_cache_check()
    test_orchestrator_cache_hit_before_generation()
    test_orchestrator_cache_store_after_generation()
    test_ttl_env_var_configurable()

    # Integration tests (if requested and DB available)
    if args.integration:
        print("\n--- Integration Tests ---")
        if _db_available():
            test_integration_store_and_retrieve()
            test_integration_ttl_expiration()
            test_integration_hit_count_increments()
            test_integration_cost_ledger_news_cache_hit()
            test_integration_invalidate_expired()
        else:
            print("  SKIP: Database not available")
            record("integration tests", False, f"DB not reachable at {_get_db_url()}")

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    for name, p, _ in results:
        status = "PASS" if p else "FAIL"
        print(f"  {status}  {name}")
    print(f"\n  {passed}/{total} checks passed")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
