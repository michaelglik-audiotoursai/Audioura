#!/usr/bin/env python3
"""
Shared database connection helper for all tests.

Resolves the connection from environment variables with correct defaults
for the Mac Mini Docker setup (host port 5433 maps to container port 5432).

Priority:
  1. DATABASE_URL env var (full connection string)
  2. AUDIOURA_DB_TARGET env var ('test' → audiotours_test, 'production' → audiotours)
  3. Individual env vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
  4. Defaults: localhost:5433/audiotours (admin:password123)

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

─── LOCAL-296: AUDIOURA_DB_TARGET switch ─────────────────────────────────────

A single env var to route generation scripts to the test database:
    AUDIOURA_DB_TARGET=test    → forces audiotours_test
    AUDIOURA_DB_TARGET=production → forces audiotours (explicit opt-in)

Any other value is a fatal error (no silent wrong choice).
Production remains the default when the var is unset.
This var is checked BEFORE _is_pytest() — it is the explicit override.

Every connection logs the target database once at first use via
log_db_target(), so it is always visible which table a run touched.
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

# LOCAL-296: Valid values for AUDIOURA_DB_TARGET
_VALID_DB_TARGETS = {"test", "production"}

# LOCAL-296: Track whether we've logged the target database this session
_db_target_logged = False

# LOCAL-296: Ensure invalid-target banner prints only once (pytest catches
# SystemExit, so without this guard the banner reprints on every subsequent
# call to _resolve_db_target within the same process).
_invalid_target_reported = False


def _resolve_db_target():
    """Resolve AUDIOURA_DB_TARGET env var if set.

    Returns the database name if the var is set and valid.
    Returns None if the var is not set (fall through to other logic).
    Raises SystemExit if the var is set to an invalid value — no silent wrong choice.
    """
    global _invalid_target_reported
    target = os.environ.get("AUDIOURA_DB_TARGET")
    if target is None:
        return None
    target = target.strip().lower()
    if target not in _VALID_DB_TARGETS:
        if not _invalid_target_reported:
            _invalid_target_reported = True
            banner = "=" * 70
            print(
                f"\n{banner}\n"
                f"FATAL: AUDIOURA_DB_TARGET has invalid value\n"
                f"{banner}\n"
                f"  Value: {os.environ.get('AUDIOURA_DB_TARGET')!r}\n"
                f"  Valid: 'test' or 'production'\n"
                f"\n"
                f"  An ambiguous database target is exactly how production data gets\n"
                f"  touched by test scripts. Set a valid value or unset the variable.\n"
                f"{banner}",
                file=sys.stderr,
            )
        sys.exit(1)
    if target == "test":
        return _TEST_DBNAME
    return _PRODUCTION_DBNAME


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
    """Return the appropriate default database name for the current context.

    Priority:
      1. AUDIOURA_DB_TARGET env var (explicit switch, fatal on invalid value)
      2. DB_NAME env var (explicit override, always wins)
      3. _is_pytest() detection → audiotours_test
      4. Default → audiotours (production)
    """
    # LOCAL-296: Explicit switch takes priority
    target_override = _resolve_db_target()
    if target_override is not None:
        return target_override

    if _is_pytest():
        return _TEST_DBNAME
    return _PRODUCTION_DBNAME


DEFAULT_DBNAME = _default_dbname()
DEFAULT_DATABASE_URL = (
    f"postgresql://{DEFAULT_USER}:{DEFAULT_PASSWORD}"
    f"@{DEFAULT_HOST}:{DEFAULT_PORT}/{DEFAULT_DBNAME}"
)

EXIT_DB_UNREACHABLE = 7


def log_db_target(context="generation"):
    """Log the target database once per session.

    LOCAL-296: Every generation must log which database it is writing to,
    once, at start. Call this at the top of any generation script.

    Args:
        context: Label for the log line (e.g. 'generation', 'verification').
    """
    global _db_target_logged
    if _db_target_logged:
        return
    _db_target_logged = True
    dbname = _effective_dbname()
    source = _get_db_source()
    print(f"[DB TARGET] {context} → {dbname} ({source})")


def _effective_dbname():
    """Return the database name that get_connection() will actually use.

    This mirrors get_db_config() resolution:
      1. DB_NAME env var (explicit override)
      2. _default_dbname() (AUDIOURA_DB_TARGET → pytest detection → production)
    """
    return os.environ.get("DB_NAME", _default_dbname())


def _get_db_source():
    """Return a human-readable explanation of why this database was chosen."""
    if os.environ.get("DB_NAME"):
        return f"DB_NAME={os.environ['DB_NAME']}"
    if os.environ.get("AUDIOURA_DB_TARGET"):
        return f"AUDIOURA_DB_TARGET={os.environ['AUDIOURA_DB_TARGET']}"
    if _is_pytest():
        return "pytest detected → test database"
    return "default → production"


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
