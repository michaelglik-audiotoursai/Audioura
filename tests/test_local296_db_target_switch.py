"""LOCAL-296: pytest suite for AUDIOURA_DB_TARGET resolution logic.

Pure string/logic tests — no database connections. Verifies that
get_database_url() returns the correct database name based on the
AUDIOURA_DB_TARGET env var.
"""
import os
import sys
import importlib
import pytest

# Ensure the tests directory is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _clean_db_module():
    """Remove db_connection from sys.modules before and after each test."""
    sys.modules.pop("db_connection", None)
    yield
    sys.modules.pop("db_connection", None)


def _import_db_connection():
    """Import db_connection fresh (after module cache cleared by fixture)."""
    import db_connection
    db_connection._db_target_logged = False
    db_connection._invalid_target_reported = False
    return db_connection


def test_target_test_resolves_to_audiotours_test(monkeypatch):
    """AUDIOURA_DB_TARGET=test routes to audiotours_test."""
    monkeypatch.setenv("AUDIOURA_DB_TARGET", "test")
    db = _import_db_connection()
    url = db.get_database_url()
    assert url.endswith("/audiotours_test"), f"Expected audiotours_test, got: {url}"


def test_target_production_resolves_to_audiotours(monkeypatch):
    """AUDIOURA_DB_TARGET=production routes to audiotours (even under pytest)."""
    monkeypatch.setenv("AUDIOURA_DB_TARGET", "production")
    db = _import_db_connection()
    url = db.get_database_url()
    assert url.endswith("/audiotours"), f"Expected audiotours, got: {url}"
    assert "/audiotours_test" not in url, f"Got test DB unexpectedly: {url}"


def test_invalid_target_exits_fatally(monkeypatch):
    """AUDIOURA_DB_TARGET=bogus must fail with SystemExit — no silent fallback."""
    monkeypatch.setenv("AUDIOURA_DB_TARGET", "bogus")
    db = _import_db_connection()
    with pytest.raises(SystemExit) as exc_info:
        # LOCAL-325: Resolution is now lazy — trigger it by calling
        # get_database_url() (or get_connection/get_db_config).
        db.get_database_url()
    assert exc_info.value.code == 1


def test_unset_under_pytest_resolves_to_test_db(monkeypatch):
    """With no AUDIOURA_DB_TARGET, pytest detection routes to audiotours_test."""
    monkeypatch.delenv("AUDIOURA_DB_TARGET", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db = _import_db_connection()
    url = db.get_database_url()
    # Under pytest, _is_pytest() returns True → audiotours_test (LOCAL-232)
    assert "audiotours_test" in url, f"Expected audiotours_test under pytest, got: {url}"
