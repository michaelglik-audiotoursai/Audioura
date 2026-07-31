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
"""
import os
import sys

# ─── Defaults matching docker-compose-master.yml host-side mapping ───────────
DEFAULT_HOST = "localhost"
DEFAULT_PORT = "5433"
DEFAULT_DBNAME = "audiotours"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "password123"
DEFAULT_DATABASE_URL = (
    f"postgresql://{DEFAULT_USER}:{DEFAULT_PASSWORD}"
    f"@{DEFAULT_HOST}:{DEFAULT_PORT}/{DEFAULT_DBNAME}"
)

# ─── Exit code for environment/infra failures (distinct from test failures) ──
EXIT_DB_UNREACHABLE = 7


def get_database_url():
    """Return a full DATABASE_URL, resolved from env or defaults."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("DB_HOST", DEFAULT_HOST)
    port = os.environ.get("DB_PORT", DEFAULT_PORT)
    dbname = os.environ.get("DB_NAME", DEFAULT_DBNAME)
    user = os.environ.get("DB_USER", DEFAULT_USER)
    password = os.environ.get("DB_PASSWORD", DEFAULT_PASSWORD)
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def get_db_config():
    """Return a dict suitable for psycopg2.connect(**config)."""
    return {
        "host": os.environ.get("DB_HOST", DEFAULT_HOST),
        "port": os.environ.get("DB_PORT", DEFAULT_PORT),
        "dbname": os.environ.get("DB_NAME", DEFAULT_DBNAME),
        "user": os.environ.get("DB_USER", DEFAULT_USER),
        "password": os.environ.get("DB_PASSWORD", DEFAULT_PASSWORD),
    }


def get_connection():
    """
    Open and return a psycopg2 connection using resolved config.

    On failure: prints a clear diagnostic message and calls sys.exit(EXIT_DB_UNREACHABLE).
    This ensures infra problems are never confused with test assertion failures.
    """
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
    """
    Return True if the DB is reachable, False otherwise.
    Does NOT exit — use this for tests that want to skip gracefully.
    """
    import psycopg2

    config = get_db_config()
    try:
        conn = psycopg2.connect(**config)
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        print(f"  (DB unavailable: {e})")
        return False
