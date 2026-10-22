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
import pytest

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

    def __setattr__(self, name, value):
        # [LOCAL-734, LEAD] Forward public attributes (autocommit, isolation_level,
        # readonly, …) to the real connection. Without this, `conn.autocommit =
        # True` landed on the wrapper only, the real connection stayed in a
        # transaction, and a test that then hit an app `ALTER TABLE` deadlocked.
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

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

# ─── LOCAL-676: Pin the whole session to the TEST database by default ─────────
#
# Root cause of the round-2 failures: several test modules set
# os.environ['DB_NAME']='audiotours' and/or os.environ['DATABASE_URL']=
# '…/audiotours' UNCONDITIONALLY at module-import time. pytest imports EVERY
# test module during collection, so the last such assignment leaked a
# production DB target into the shared process environment. Other modules that
# resolve their connection lazily (get_connection → get_db_config) or capture a
# URL at import (get_db_config → DATABASE_URL) then connected to production
# 'audiotours', and the LOCAL-232 write guard tripped on their isolated writes.
#
# AUDIOURA_DB_TARGET is the explicit switch db_connection consults FIRST — ahead
# of both DB_NAME and DATABASE_URL (D214, and LOCAL-676 extends the same
# precedence to get_db_config). Setting it here, once, before any test module is
# imported, makes the pytest session resolve to audiotours_test regardless of
# what any module scribbles into DB_NAME/DATABASE_URL during collection.
#
# A module that deliberately needs a read-only production connection still opts
# in with its own `AUDIOURA_DB_TARGET=production` (e.g. via a monkeypatch
# fixture, as test_local320_nondining_regression does) — that per-module value
# overrides this default for its duration and reverts afterward. We only set the
# default when the variable is not already present, so an outer harness that
# chose a target keeps control.
os.environ.setdefault("AUDIOURA_DB_TARGET", "test")

psycopg2.connect = _guarded_connect


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "production_write_guard: LOCAL-232 guard against production writes",
    )
    config.addinivalue_line(
        "markers",
        "service: LOCAL-302 — test drives a running Docker service over HTTP. "
        "Cannot honour AUDIOURA_DB_TARGET because the service has its own "
        "DATABASE_URL. Exclude with: -m 'not service'",
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require services/DB)",
    )
    config.addinivalue_line(
        "markers",
        "network: LOCAL-676 — test makes a real outbound call to a third-party "
        "service (Nominatim/OSM, Wikidata, Wikipedia). Rate-limited and flaky in "
        "CI, so skipped by default. Run with: --run-network (or -m network).",
    )


def pytest_addoption(parser):
    """LOCAL-676: opt-in flag to run the network-only tests."""
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests marked @pytest.mark.network (real Nominatim/Wikidata/"
             "Wikipedia calls). Skipped by default.",
    )


def pytest_collection_modifyitems(config, items):
    """LOCAL-676: skip @pytest.mark.network tests unless opted in.

    Opt in with --run-network, or by selecting them explicitly with -m network
    (so `-m network` still runs them for a targeted network check).
    """
    if config.getoption("--run-network"):
        return
    markexpr = config.getoption("-m", default="")
    if "network" in markexpr:
        return  # user explicitly selected the network tests
    skip_network = pytest.mark.skip(
        reason="network test skipped by default (use --run-network or -m network)"
    )
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)


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
