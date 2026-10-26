"""[wdvrdaz5yt] cost_meter builds a libpq URL that works with a Cloud SQL socket
directory in DB_HOST, and both copies of cost_meter.py stay identical."""
import filecmp
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location("cm", os.path.join(ROOT, "cost_meter.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_socket_host_goes_in_query(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "/cloudsql/p:us-central1:db")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_USER", "u")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/w")
    monkeypatch.setenv("DB_NAME", "audiotours")
    url = _load()._get_db_url()
    assert url.startswith("postgresql://u:p%40ss%2Fw@/audiotours?host=")
    import pytest
    ext = pytest.importorskip("psycopg2.extensions")
    dsn = ext.parse_dsn(url)
    assert dsn["host"] == "/cloudsql/p:us-central1:db"
    assert dsn["password"] == "p@ss/w" and dsn["dbname"] == "audiotours" and dsn["port"] == "5432"


def test_tcp_host_unchanged(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "postgres-2")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_USER", "admin")
    monkeypatch.setenv("DB_PASSWORD", "password123")
    monkeypatch.setenv("DB_NAME", "audiotours")
    assert _load()._get_db_url() == "postgresql://admin:password123@postgres-2:5432/audiotours"


def test_copies_identical():
    assert filecmp.cmp(os.path.join(ROOT, "cost_meter.py"),
                       os.path.join(ROOT, "translation-service", "cost_meter.py"), shallow=False)
