#!/usr/bin/env python3
"""
LOCAL-232: Demonstrate the production-write guard firing.

This test proves that conftest.py's ProductionWriteGuardError is raised
when a test attempts to INSERT into audio_tours on the production database.

Run with: python3 -m pytest tests/test_local232_guard_demo.py -v -s
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_guard_blocks_production_insert():
    """INSERT into production audio_tours raises ProductionWriteGuardError."""
    import psycopg2
    from conftest import ProductionWriteGuardError

    # Connect directly to production (bypassing db_connection routing)
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours",  # Explicitly production
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )
    cur = conn.cursor()

    with pytest.raises(ProductionWriteGuardError, match="BLOCKED"):
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test) "
            "VALUES ('SHOULD_NEVER_EXIST', 'guard_test', 1, true)"
        )

    conn.close()


def test_guard_blocks_production_update():
    """UPDATE on production audio_tours raises ProductionWriteGuardError."""
    import psycopg2
    from conftest import ProductionWriteGuardError

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours",
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )
    cur = conn.cursor()

    with pytest.raises(ProductionWriteGuardError, match="BLOCKED"):
        cur.execute(
            "UPDATE audio_tours SET is_test = true WHERE id = -1"
        )

    conn.close()


def test_guard_blocks_production_delete():
    """DELETE from production audio_tours raises ProductionWriteGuardError."""
    import psycopg2
    from conftest import ProductionWriteGuardError

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours",
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )
    cur = conn.cursor()

    with pytest.raises(ProductionWriteGuardError, match="BLOCKED"):
        cur.execute(
            "DELETE FROM audio_tours WHERE id = -1"
        )

    conn.close()


def test_guard_allows_test_db_insert():
    """INSERT into audiotours_test is NOT blocked."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours_test",  # Test database — should pass
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )
    cur = conn.cursor()

    # This should NOT raise
    cur.execute(
        "INSERT INTO audio_tours (tour_name, request_string, number_requested, is_test) "
        "VALUES ('LOCAL-232 Guard Demo', 'guard_demo', 1, true) RETURNING id"
    )
    tour_id = cur.fetchone()[0]
    conn.commit()

    # Clean up
    cur.execute("DELETE FROM audio_tours WHERE id = %s", (tour_id,))
    conn.commit()
    conn.close()


def test_guard_allows_production_select():
    """SELECT from production audio_tours is NOT blocked."""
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname="audiotours",
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )
    cur = conn.cursor()

    # SELECT should pass — guard only blocks writes
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    assert count >= 0  # Just verify it ran
    conn.close()
