"""
Test suite for LOCAL-723: the daily paid-API limit counts LISTENER spend only.

Background (LEAD, 2026-10-20): DAILY_PAID_LIMIT_USD (LOCAL-673) summed
paid_api_calls by `service`, and test/bench containers run the SAME services as
the listener-facing stack. A night of test spend therefore tripped the
listeners' $8 limit although listeners had spent $0. The copied-env problem made
it worse: the LOCAL-721/722 test containers copied the shared generator's whole
env (HOSTNAME, METER_SERVICE), so their calls were even labelled as the shared
host.

The fix proves the listener role instead of trusting a label, stamps it on every
row, records the REAL hostname, and scopes the limit query to role = 'listener':

  * _meter_role() returns 'listener' ONLY when METER_ROLE=listener AND the env
    token (METER_ROLE_TOKEN) equals the contents of the file at
    METER_ROLE_TOKEN_FILE (bind-mounted only into the shared containers).
  * A copied env (token value present, but NO mounted file) is NOT a listener.
  * Missing/empty token, missing/empty file path, mismatched token, unreadable
    file, or METER_ROLE != listener all yield None (not counted) — fail safe for
    listeners: test spend can never count.
  * _real_hostname() returns socket.gethostname(), never the copyable HOSTNAME
    env.
  * The limit query sums status=200 AND role='listener' for the NY day.

No DB and no network: the role logic is pure, and the query's SQL is asserted by
capturing it through a fake cursor.
"""

import os
import sys
import importlib

import pytest

# _meter is a sibling of the tests/ dir's parent (repo root).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "_meter"))


@pytest.fixture
def meter():
    """A freshly imported meter module with a clean module state per test."""
    import paid_api_meter as m
    importlib.reload(m)
    return m


def _write_token_file(tmp_path, contents):
    p = tmp_path / "role_token"
    p.write_text(contents)
    return str(p)


# --------------------------------------------------------------------------- #
# _meter_role: the proof
# --------------------------------------------------------------------------- #
def test_listener_when_env_and_mounted_token_match(meter, monkeypatch, tmp_path):
    """The real listener stack: METER_ROLE=listener and the env token equals the
    contents of the mounted token file -> role 'listener'."""
    token_file = _write_token_file(tmp_path, "s3cr3t-token\n")
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "s3cr3t-token")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() == "listener"


def test_copied_env_without_mounted_file_is_not_listener(meter, monkeypatch, tmp_path):
    """THE CORE CASE. A test container copies the listener env — including the
    token VALUE and METER_ROLE — but does NOT get the bind-mounted token file.
    The file read fails, so it is NOT a listener and its spend is never counted."""
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "s3cr3t-token")
    # Points at the same mount path the listener uses, but nothing is mounted here.
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", str(tmp_path / "role_token"))
    assert meter._meter_role() is None


def test_copied_env_with_wrong_file_contents_is_not_listener(meter, monkeypatch, tmp_path):
    """Even if some file happens to exist at the path, a token that does not match
    its contents is not a listener (anti-spoof)."""
    token_file = _write_token_file(tmp_path, "the-real-token")
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "a-copied-but-stale-token")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() is None


def test_no_role_env_is_not_listener(meter, monkeypatch, tmp_path):
    token_file = _write_token_file(tmp_path, "s3cr3t-token")
    monkeypatch.delenv("METER_ROLE", raising=False)
    monkeypatch.setenv("METER_ROLE_TOKEN", "s3cr3t-token")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() is None


def test_role_not_listener_value_is_not_listener(meter, monkeypatch, tmp_path):
    token_file = _write_token_file(tmp_path, "s3cr3t-token")
    monkeypatch.setenv("METER_ROLE", "generator")  # some other label
    monkeypatch.setenv("METER_ROLE_TOKEN", "s3cr3t-token")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() is None


def test_missing_token_env_is_not_listener(meter, monkeypatch, tmp_path):
    token_file = _write_token_file(tmp_path, "s3cr3t-token")
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.delenv("METER_ROLE_TOKEN", raising=False)
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() is None


def test_missing_token_file_env_is_not_listener(meter, monkeypatch):
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "s3cr3t-token")
    monkeypatch.delenv("METER_ROLE_TOKEN_FILE", raising=False)
    assert meter._meter_role() is None


def test_empty_file_never_matches_even_empty_token(meter, monkeypatch, tmp_path):
    """An empty token file must not match (empty==empty is rejected), so a blank
    mount can't accidentally qualify anything."""
    token_file = _write_token_file(tmp_path, "   \n")  # whitespace only -> strips to ""
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() is None


def test_role_case_and_whitespace_insensitive_label(meter, monkeypatch, tmp_path):
    token_file = _write_token_file(tmp_path, "tok")
    monkeypatch.setenv("METER_ROLE", "  Listener ")
    monkeypatch.setenv("METER_ROLE_TOKEN", "tok")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)
    assert meter._meter_role() == "listener"


# --------------------------------------------------------------------------- #
# _real_hostname: never trust the copyable HOSTNAME env
# --------------------------------------------------------------------------- #
def test_real_hostname_uses_socket_not_env(meter, monkeypatch):
    monkeypatch.setenv("HOSTNAME", "shared-generator-copied-into-a-test-box")
    monkeypatch.setattr(meter.socket, "gethostname", lambda: "real-test-box")
    assert meter._real_hostname() == "real-test-box"


def test_real_hostname_never_raises(meter, monkeypatch):
    def boom():
        raise OSError("no hostname")
    monkeypatch.setattr(meter.socket, "gethostname", boom)
    assert meter._real_hostname() == ""


# --------------------------------------------------------------------------- #
# _record stamps role into the JSONL row
# --------------------------------------------------------------------------- #
def test_record_row_carries_role(meter, monkeypatch, tmp_path):
    token_file = _write_token_file(tmp_path, "tok")
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "tok")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", token_file)

    log = tmp_path / "paid.jsonl"
    monkeypatch.setattr(meter, "LOG", str(log))
    monkeypatch.setattr(meter, "_db_write", lambda rec: None)  # no DB

    meter._record("https://api.openai.com/v1/chat/completions", 200,
                  b'{"model":"gpt-4o-mini","usage":{"prompt_tokens":10,"completion_tokens":5}}',
                  {"model": "gpt-4o-mini"})
    import json
    row = json.loads(log.read_text().splitlines()[-1])
    assert row["role"] == "listener"


def test_record_row_role_none_for_test_container(meter, monkeypatch, tmp_path):
    # Copied env, no mounted file -> role None on the row.
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", "tok")
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", str(tmp_path / "absent"))

    log = tmp_path / "paid.jsonl"
    monkeypatch.setattr(meter, "LOG", str(log))
    monkeypatch.setattr(meter, "_db_write", lambda rec: None)

    meter._record("https://api.openai.com/v1/chat/completions", 200,
                  b'{"model":"gpt-4o-mini","usage":{"prompt_tokens":10,"completion_tokens":5}}',
                  {"model": "gpt-4o-mini"})
    import json
    row = json.loads(log.read_text().splitlines()[-1])
    assert row["role"] is None


# --------------------------------------------------------------------------- #
# the limit query is scoped to role='listener'
# --------------------------------------------------------------------------- #
class _FakeCursor:
    def __init__(self, sink):
        self._sink = sink

    def execute(self, sql, params=None):
        self._sink["sql"] = sql
        self._sink["params"] = params

    def fetchone(self):
        return (0,)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, sink):
        self._sink = sink

    def cursor(self):
        return _FakeCursor(self._sink)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


def test_query_filters_on_role_listener(meter, monkeypatch):
    """_query_today_total_usd must filter status=200 AND role='listener' for the
    NY day, and must NOT reference the retired service-list scope."""
    sink = {}

    fake_psycopg2 = type(sys)("psycopg2")
    fake_psycopg2.connect = lambda *a, **k: _FakeConn(sink)
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    total = meter._query_today_total_usd("2026-10-20")
    assert total == 0.0

    sql = " ".join(sink["sql"].split())  # normalize whitespace
    assert "status = 200" in sql
    assert "role = 'listener'" in sql
    assert sink["params"] == ("2026-10-20",)
    # The old service-list scope is gone.
    assert "service = ANY" not in sql
    assert "DAILY_PAID_LIMIT_SERVICES" not in sql


def test_query_does_not_read_service_scope_env(meter, monkeypatch):
    """Setting DAILY_PAID_LIMIT_SERVICES must not change the scope anymore (role
    is the only scope)."""
    monkeypatch.setenv("DAILY_PAID_LIMIT_SERVICES", "generate_tour_text_service.py")
    sink = {}
    fake_psycopg2 = type(sys)("psycopg2")
    fake_psycopg2.connect = lambda *a, **k: _FakeConn(sink)
    monkeypatch.setitem(sys.modules, "psycopg2", fake_psycopg2)

    meter._query_today_total_usd("2026-10-20")
    sql = " ".join(sink["sql"].split())
    assert "role = 'listener'" in sql
    assert "service" not in sql
