"""tests/test_local769_boto3_metered.py — LOCAL-769.

GCloud_Storied proved (wdvrdaz5yt, 2026-10-25): tour 446 -> es ran AWS Translate
+ Polly and wrote ZERO paid_api_calls rows. The network meter
(_meter/paid_api_meter.py install()) patches requests / urllib / httpx / aiohttp,
but botocore uses its OWN urllib3 stack — so no Polly or AWS Translate call is
ever recorded, on any service. check_daily_limit() runs before those calls
(LOCAL-673) so the cap can STOP them, but their cost never counts toward it, and
Michael's daily spend report would miss them.

These tests are RED on the base (the botocore meter is not wired yet) and GREEN
after _meter/paid_api_meter.py patches botocore's BaseClient._make_api_call.

What is proven (NO real network, NO real paid call, NO real DB):
  1. polly_synthesize_speech_metered — a stubbed Polly synthesize_speech writes
     exactly ONE kind="polly" row, status 200, usd = billed chars x neural rate,
     with a role field and an Engine+VoiceId model.
  2. translate_text_metered — a stubbed Translate translate_text writes exactly
     ONE kind="aws_translate" row, usd = source chars x translate rate.
  3. meter_db_error_does_not_raise — a _db_write that raises must NOT propagate
     into the caller: the boto3 call still returns its normal result.
  4. no_double_row — a single boto3 call produces exactly one row (not one per
     botocore internal layer / retry wrapper).
  5. role_listener_when_proven — a Polly row carries role="listener" only when
     the container proves it (env label + mounted token file), via _meter_role.
  6. db_write_targets_paid_api_calls — the row the meter persists is INSERTed
     into paid_api_calls (the SAME table check_daily_limit sums), with the polly
     kind and a positive usd, so the daily cap/report see the spend.

The meter is loaded from _meter/ and install()ed; the JSONL log is redirected to
a tmp file and the DB write + daily-limit check are stubbed, exactly like
test_local707_serper_metered.py.
"""
import io
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "_meter"))
sys.path.insert(0, _ROOT)

pytest.importorskip("botocore")
# Clients come from botocore directly: other suites (LOCAL-578) replace
# sys.modules["boto3"] with a MagicMock, which would hand these tests fake clients.
import botocore.session  # noqa: E402
from botocore.stub import Stubber  # noqa: E402


# ── meter fixture: tmp log, DB + daily-limit stubbed ─────────────────────────
@pytest.fixture
def meter(monkeypatch, tmp_path):
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)
    m.install()
    m._LOG_FOR_TEST = str(log)
    return m


def _rows(m):
    p = m._LOG_FOR_TEST
    if not os.path.exists(p):
        return []
    with open(p) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _rows_of_kind(m, kind):
    return [r for r in _rows(m) if r.get("kind") == kind]


def _polly_client():
    return botocore.session.get_session().create_client(
        "polly", region_name="us-east-1",
        aws_access_key_id="x", aws_secret_access_key="y")


def _translate_client():
    return botocore.session.get_session().create_client(
        "translate", region_name="us-east-1",
        aws_access_key_id="x", aws_secret_access_key="y")


# ── 1. Polly synthesize_speech -> one polly row, chars-based usd ─────────────
def test_polly_synthesize_speech_metered(meter):
    import cost_rates
    text = "Hello from Polly, a short neural test line."
    client = _polly_client()
    sb = Stubber(client)
    sb.add_response(
        "synthesize_speech",
        {"AudioStream": io.BytesIO(b"MP3BYTES"),
         "ContentType": "audio/mpeg",
         "RequestCharacters": len(text)},
        {"Text": text, "OutputFormat": "mp3", "VoiceId": "Joanna",
         "Engine": "neural"})
    before = len(_rows_of_kind(meter, "polly"))
    with sb:
        resp = client.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural")
    # Caller's stream must be untouched (the meter must NOT read AudioStream).
    assert resp["AudioStream"].read() == b"MP3BYTES"

    rows = _rows_of_kind(meter, "polly")
    assert len(rows) == before + 1, "exactly one polly row per call"
    row = rows[-1]
    assert row["status"] == 200
    assert "role" in row
    expected = cost_rates.tts_cost(len(text), engine="neural")
    assert abs(row["usd"] - expected) < 1e-12, (row["usd"], expected)
    assert "Joanna" in (row.get("model") or "")


# ── 2. Translate translate_text -> one aws_translate row ─────────────────────
def test_translate_text_metered(meter):
    import cost_rates
    text = "Hello, please translate this short sentence."
    client = _translate_client()
    sb = Stubber(client)
    sb.add_response(
        "translate_text",
        {"TranslatedText": "Hola, por favor traduce esta frase corta.",
         "SourceLanguageCode": "en", "TargetLanguageCode": "es"},
        {"Text": text, "SourceLanguageCode": "en", "TargetLanguageCode": "es"})
    before = len(_rows_of_kind(meter, "aws_translate"))
    with sb:
        resp = client.translate_text(
            Text=text, SourceLanguageCode="en", TargetLanguageCode="es")
    assert resp["TranslatedText"].startswith("Hola")

    rows = _rows_of_kind(meter, "aws_translate")
    assert len(rows) == before + 1, "exactly one aws_translate row per call"
    row = rows[-1]
    assert row["status"] == 200
    assert "role" in row
    expected = len(text) * cost_rates.AWS_TRANSLATE_COST_PER_CHAR
    assert abs(row["usd"] - expected) < 1e-12, (row["usd"], expected)


# ── 3. a meter DB error must not raise into the caller ───────────────────────
def test_meter_db_error_does_not_raise(meter, monkeypatch):
    def _boom(rec):
        raise RuntimeError("DB down")
    monkeypatch.setattr(meter, "_db_write", _boom)
    text = "fail-open check"
    client = _polly_client()
    sb = Stubber(client)
    sb.add_response(
        "synthesize_speech",
        {"AudioStream": io.BytesIO(b"X"), "ContentType": "audio/mpeg",
         "RequestCharacters": len(text)},
        {"Text": text, "OutputFormat": "mp3", "VoiceId": "Joanna",
         "Engine": "neural"})
    with sb:
        # Must NOT raise despite _db_write blowing up.
        resp = client.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural")
    assert resp["ContentType"] == "audio/mpeg"


# ── 4. a single call yields exactly one row ──────────────────────────────────
def test_no_double_row(meter):
    text = "no double counting please"
    client = _translate_client()
    sb = Stubber(client)
    sb.add_response(
        "translate_text",
        {"TranslatedText": "x", "SourceLanguageCode": "en",
         "TargetLanguageCode": "es"},
        {"Text": text, "SourceLanguageCode": "en", "TargetLanguageCode": "es"})
    before = len(_rows_of_kind(meter, "aws_translate"))
    with sb:
        client.translate_text(
            Text=text, SourceLanguageCode="en", TargetLanguageCode="es")
    after = len(_rows_of_kind(meter, "aws_translate"))
    assert after - before == 1, "one boto3 call must write exactly one row"


# ── 5. role is 'listener' only when the container proves it ──────────────────
def test_role_listener_when_proven(meter, monkeypatch, tmp_path):
    token = "secret-listener-token"
    tok_file = tmp_path / "role_token"
    tok_file.write_text(token)
    monkeypatch.setenv("METER_ROLE", "listener")
    monkeypatch.setenv("METER_ROLE_TOKEN", token)
    monkeypatch.setenv("METER_ROLE_TOKEN_FILE", str(tok_file))

    text = "role proof row"
    client = _polly_client()
    sb = Stubber(client)
    sb.add_response(
        "synthesize_speech",
        {"AudioStream": io.BytesIO(b"Y"), "ContentType": "audio/mpeg",
         "RequestCharacters": len(text)},
        {"Text": text, "OutputFormat": "mp3", "VoiceId": "Joanna",
         "Engine": "neural"})
    with sb:
        client.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId="Joanna", Engine="neural")
    row = _rows_of_kind(meter, "polly")[-1]
    assert row["role"] == "listener"


# ── 6. the persisted row lands in paid_api_calls (what the cap sums) ─────────
def test_db_write_targets_paid_api_calls(monkeypatch, tmp_path):
    """_db_write must INSERT the polly/translate row into paid_api_calls — the
    SAME table check_daily_limit sums — with the right kind and a positive usd,
    so the daily cap and Michael's report actually see boto3 spend. We capture
    the SQL + params with a fake psycopg2 (no real DB)."""
    import paid_api_meter as m

    captured = {}

    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return _Cur()
        def close(self): pass

    class _FakePG:
        @staticmethod
        def connect(*a, **k): return _Conn()

    monkeypatch.setitem(sys.modules, "psycopg2", _FakePG)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")

    rec = {"kind": "polly", "status": 200, "service": "t", "caller": "c",
           "url": "https://polly.us-east-1.amazonaws.com", "model": "neural/Joanna",
           "usd": 0.0001, "role": "listener"}
    m._db_write(rec)

    assert "paid_api_calls" in captured.get("sql", "")
    params = captured.get("params")
    assert params is not None
    assert "polly" in params, "kind polly must be written to paid_api_calls"
    assert 0.0001 in params, "usd must be written to paid_api_calls"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# ── 7. a second copy / reload of the meter never stacks a second botocore layer ──
def test_reinstall_never_stacks(meter):
    import importlib, sys
    import botocore.client as bc
    importlib.reload(sys.modules[meter.__name__])
    sys.modules[meter.__name__].install()
    fn = bc.BaseClient._make_api_call
    assert getattr(fn, "_paid_meter_orig", None) is not None
    assert not hasattr(fn._paid_meter_orig, "_paid_meter_orig"), "meter wrapped botocore twice"
