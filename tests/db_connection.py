#!/usr/bin/env python3
"""
Shared database connection helper for all tests.

Resolves the connection from environment variables with correct defaults
for the Mac Mini Docker setup (host port 5433 maps to container port 5432).

Priority:
  1. DATABASE_URL env var (full connection string)
  2. Individual env vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
  3. Defaults: localhost:5433/audiotours (admin:password123)

The default port is 5433 because docker-compose-master.yml maps:
    ports:
      - "5433:5432"

Inside Docker containers, services use postgres-2:5432 (internal network).
Outside Docker (where tests run), the host port is 5433.

─── LOCAL-232: Test database routing ─────────────────────────────────────────

When running under pytest (detected via PYTEST_CURRENT_TEST env var, which
pytest sets automatically for every test), the default database resolves to
`audiotours_test` instead of `audiotours`.

Decision: we detect pytest by the presence of PYTEST_CURRENT_TEST, which
pytest injects unconditionally (since pytest 3.2). This avoids fragile
sys.modules checks and works regardless of how the test file is invoked
(pytest, tox, CI).

To force a specific database (e.g. production for a read-only check):
    DB_NAME=audiotours pytest tests/some_test.py

The explicit env var always wins.
"""
import os
import sys

DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5433"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "password123"

# LOCAL-232: Route to audiotours_test when running under pytest
_PRODUCTION_DBNAME = "audiotours"
_TEST_DBNAME = "audiotours_test"


def _is_pytest():
    """Detect whether we are running in a test context.

    Checks multiple signals (any one is sufficient):
      1. PYTEST_CURRENT_TEST — set by pytest for each running test item.
      2. _AUDIOURA_PYTEST_SESSION — set by conftest.py at import time,
         which fires before any test module is imported.
      3. '_pytest' in sys.modules — pytest framework is loaded.
      4. The __main__ script is in the tests/ directory — covers script-
         based test execution (python3 tests/test_xxx.py).

    This ensures tests route to audiotours_test regardless of invocation
    method (pytest, direct script, subprocess).
    """
    if (
        "PYTEST_CURRENT_TEST" in os.environ
        or "_AUDIOURA_PYTEST_SESSION" in os.environ
        or "_pytest" in sys.modules
    ):
        return True

    # Check if the running script is in the tests/ directory
    main_mod = sys.modules.get("__main__")
    if main_mod:
        main_file = getattr(main_mod, "__file__", None)
        if main_file:
            main_abs = os.path.abspath(main_file)
            tests_dir = os.path.dirname(os.path.abspath(__file__))
            if main_abs.startswith(tests_dir + os.sep):
                return True

    return False


def _default_dbname():
    """Return the appropriate default database name for the current context."""
    if _is_pytest():
        return _TEST_DBNAME
    return _PRODUCTION_DBNAME


DEFAULT_DBNAME = _default_dbname()
DEFAULT_DATABASE_URL = (
    f"postgresql://{DEFAULT_USER}:{DEFAULT_PASSWORD}"
    f"@{DEFAULT_HOST}:{DEFAULT_PORT}/{DEFAULT_DBNAME}"
)

EXIT_DB_UNREACHABLE = 7


def get_database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("DB_HOST", DEFAULT_HOST)
    port = os.environ.get("DB_PORT", DEFAULT_PORT)
    dbname = os.environ.get("DB_NAME", _default_dbname())
    user = os.environ.get("DB_USER", DEFAULT_USER)
    password = os.environ.get("DB_PASSWORD", DEFAULT_PASSWORD)
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def get_db_config():
    return {
        "host": os.environ.get("DB_HOST", DEFAULT_HOST),
        "port": os.environ.get("DB_PORT", DEFAULT_PORT),
        "dbname": os.environ.get("DB_NAME", _default_dbname()),
        "user": os.environ.get("DB_USER", DEFAULT_USER),
        "password": os.environ.get("DB_PASSWORD", DEFAULT_PASSWORD),
    }


def get_connection():
    import psycopg2
    config = get_db_config()
    try:
        conn = psycopg2.connect(**config)
        return conn
    except psycopg2.OperationalError as e:
        print(
            "\n" + "=" * 70 + "\n"
            "DATABASE UNREACHABLE — this is an environment problem, not a test failure\n"
            "=" * 70 + "\n"
            f"  Host: {config['host']}:{config['port']}\n"
            f"  DB:   {config['dbname']}\n"
            f"  User: {config['user']}\n"
            f"\n  Error: {e}\n"
            f"\n  Check: docker-compose-master.yml maps postgres-2 to host port 5433.\n"
            f"         Is the container running? Try: docker ps | grep postgres\n"
            "=" * 70 + "\n",
            file=sys.stderr,
        )
        sys.exit(EXIT_DB_UNREACHABLE)


def check_db_available():
    import psycopg2
    config = get_db_config()
    try:
        conn = psycopg2.connect(**config)
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"  (DB unavailable: {e})")
        return False
