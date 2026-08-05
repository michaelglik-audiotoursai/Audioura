"""
tests/conftest.py — LOCAL-232 production-write guard.

Ensures that no test can INSERT into audio_tours on the PRODUCTION database.
This is the enforcement layer that keeps the convention fixed — even if
db_connection.py routing is bypassed, any INSERT into production audio_tours
from a pytest session will raise immediately.

The guard works by monkeypatching psycopg2.connect to wrap cursors with
statement inspection. If a cursor executes an INSERT INTO audio_tours while
connected to the production database ('audiotours'), it raises
ProductionWriteGuardError.

SELECTs against production are permitted (some tests verify invariants).
Only INSERT/UPDATE/DELETE on audio_tours in the production DB are blocked.
"""
import os
import re
import psycopg2
import psycopg2.extensions

# ─── Guard ──────────────────────────────────────────────────────────────────

PRODUCTION_DBNAME = "audiotours"

# Matches INSERT INTO / UPDATE / DELETE FROM audio_tours (case-insensitive)
_WRITE_PATTERN = re.compile(
    r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+audio_tours\b",
    re.IGNORECASE,
)


class ProductionWriteGuardError(RuntimeError):
    """Raised when a test attempts to write to production audio_tours."""
    pass


class _GuardedCursor:
    """Wraps a psycopg2 cursor to intercept writes to production audio_tours."""

    def __init__(self, real_cursor, dbname):
        self._cursor = real_cursor
        self._dbname = dbname

    def execute(self, query, vars=None):
        if self._dbname == PRODUCTION_DBNAME and query and _WRITE_PATTERN.search(str(query)):
            raise ProductionWriteGuardError(
                f"BLOCKED: Test attempted to write to production '{PRODUCTION_DBNAME}' "
                f"audio_tours table.\n"
                f"  Query: {str(query)[:200]}\n"
                f"  Fix: Ensure tests run against 'audiotours_test'. "
                f"Check DB_NAME env var and db_connection.py routing."
            )
        return self._cursor.execute(query, vars)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args) if hasattr(self._cursor, '__exit__') else None


class _GuardedConnection:
    """Wraps a psycopg2 connection to return guarded cursors."""

    def __init__(self, real_conn):
        self._conn = real_conn
        # Extract dbname from dsn
        info = real_conn.info if hasattr(real_conn, 'info') else None
        if info and hasattr(info, 'dbname'):
            self._dbname = info.dbname
        else:
            # Fallback: parse from dsn string
            dsn = real_conn.dsn if hasattr(real_conn, 'dsn') else ""
            match = re.search(r"dbname=(\S+)", dsn)
            self._dbname = match.group(1) if match else ""

    def cursor(self, *args, **kwargs):
        real_cursor = self._conn.cursor(*args, **kwargs)
        if self._dbname == PRODUCTION_DBNAME:
            return _GuardedCursor(real_cursor, self._dbname)
        return real_cursor

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self._conn.__exit__(*args)


# Store the original connect function
_original_connect = psycopg2.connect


def _guarded_connect(*args, **kwargs):
    """Wraps psycopg2.connect to add production-write guard."""
    conn = _original_connect(*args, **kwargs)
    return _GuardedConnection(conn)


# ─── Activate the guard at import time (pytest loads conftest.py first) ─────

# Signal to db_connection.py that we are in a pytest session.
# This fires BEFORE any test module is imported, so db_connection.py
# will resolve to audiotours_test even for script-style tests that
# execute at module-import time.
os.environ["_AUDIOURA_PYTEST_SESSION"] = "1"

psycopg2.connect = _guarded_connect


def pytest_configure(config):
    """Register the production-write guard marker for informational purposes."""
    config.addinivalue_line(
        "markers",
        "production_write_guard: LOCAL-232 guard against production writes",
    )


def pytest_sessionstart(session):
    """Clean the test database at the start of each pytest session.

    This ensures tests are re-runnable against audiotours_test without
    unique constraint violations from previous runs. Only cleans the
    test database — never production.
    """
    import psycopg2 as _pg2
    try:
        conn = _original_connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5433"),
            dbname="audiotours_test",
            user=os.environ.get("DB_USER", "admin"),
            password=os.environ.get("DB_PASSWORD", "password123"),
        )
        cur = conn.cursor()
        cur.execute("TRUNCATE audio_tours CASCADE")
        cur.execute("TRUNCATE stop_metrics CASCADE")
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass  # If test DB doesn't exist yet, migration hasn't run


def pytest_unconfigure(config):
    """Restore original psycopg2.connect on session end."""
    psycopg2.connect = _original_connect
    os.environ.pop("_AUDIOURA_PYTEST_SESSION", None)
