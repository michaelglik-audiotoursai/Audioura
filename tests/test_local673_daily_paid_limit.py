"""
Test suite for LOCAL-673: a daily paid-API spend STOP.

The meter (_meter/paid_api_meter.py) refuses a paid request once today's
(America/New_York) billed (status 200) spend in paid_api_calls reaches
DAILY_PAID_LIMIT_USD, pushes an alert once per day, and fails OPEN on any meter
error. These tests exercise the enforcement contract WITHOUT a database and
WITHOUT a network call:

  * off              — limit unset / <= 0 / unparseable -> allow
  * under            — total < limit -> allow (the paid request would be sent)
  * over             — total >= limit -> raise DailyPaidLimitExceeded, no call
  * network refused  — requests.Session.send patch raises BEFORE the real send
  * cache expiry     — the DB total is read at most once per 60 s TTL
  * day boundary     — the cache re-queries when the NY day rolls over
  * fail-open        — a DB error -> allow (never block on a meter bug)
  * alert once/day   — the ALERTS.md line is written at most once per NY day,
                       in the exact '*** DAILY PAID LIMIT $X reached at HH:MM ***'
                       format

The DB is represented by monkeypatching _query_today_total_usd, so these tests
make no DB connection and no paid API call of any kind.
"""

import os
import sys
import importlib
from datetime import datetime

import pytest

try:
    from zoneinfo import ZoneInfo
    _NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    _NY = None

# _meter is a sibling of the tests/ dir's parent (repo root).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "_meter"))


@pytest.fixture
def meter(monkeypatch, tmp_path):
    """A freshly imported meter module with isolated cache, alert file, and env.

    The DB query is left unpatched here; each test installs its own
    _query_today_total_usd. The limit is set to $8 (LEAD's value) unless a test
    changes it. The alert path points at a temp file so nothing touches the real
    ALERTS.md.
    """
    import paid_api_meter as m
    importlib.reload(m)  # guarantee a clean module-global state per test

    monkeypatch.setenv("DAILY_PAID_LIMIT_USD", "8")
    m.ALERTS_PATH = str(tmp_path / "ALERTS.md")
    # Reset the module globals the reload may have carried if already imported.
    m._limit_cache.update(expiry=0.0, total=0.0, day=None)
    m._alerted_day = None
    return m


def _set_total(m, value):
    """Make the (cached) DB query return a fixed billed total and clear the cache
    so the next check re-reads it."""
    m._query_today_total_usd = lambda day_str, _v=value: float(_v)
    m._limit_cache.update(expiry=0.0, total=0.0, day=None)


# --------------------------------------------------------------------------- #
# off
# --------------------------------------------------------------------------- #
def test_limit_off_when_unset(meter, monkeypatch):
    monkeypatch.delenv("DAILY_PAID_LIMIT_USD", raising=False)
    assert meter._limit_usd() is None
    # A DB error would raise if consulted; it must not be, since the limit is off.
    meter._query_today_total_usd = lambda d: (_ for _ in ()).throw(AssertionError("DB consulted while limit off"))
    assert meter.check_daily_limit() is None


@pytest.mark.parametrize("raw", ["0", "-5", "", "notanumber"])
def test_limit_off_for_nonpositive_or_bad_values(meter, monkeypatch, raw):
    monkeypatch.setenv("DAILY_PAID_LIMIT_USD", raw)
    assert meter._limit_usd() is None
    assert meter.check_daily_limit() is None


# --------------------------------------------------------------------------- #
# under -> allow
# --------------------------------------------------------------------------- #
def test_under_limit_allows(meter):
    _set_total(meter, 2.0)
    assert meter.check_daily_limit() is None  # would send the paid request
    # No alert written when under the limit.
    assert not os.path.exists(meter.ALERTS_PATH)


# --------------------------------------------------------------------------- #
# over -> raise, no call
# --------------------------------------------------------------------------- #
def test_at_or_over_limit_raises(meter):
    _set_total(meter, 8.0)  # exactly at the limit counts as reached (>=)
    with pytest.raises(meter.DailyPaidLimitExceeded):
        meter.check_daily_limit()


def test_over_limit_raises_and_message_is_clear(meter):
    _set_total(meter, 12.3456)
    with pytest.raises(meter.DailyPaidLimitExceeded) as ei:
        meter.check_daily_limit()
    msg = str(ei.value)
    assert "DAILY_PAID_LIMIT_USD" in msg
    assert "12.3456" in msg  # today's total
    assert "America/New_York" in msg


# --------------------------------------------------------------------------- #
# network refused BEFORE the real send
# --------------------------------------------------------------------------- #
def test_requests_patch_refuses_before_network(meter):
    """install() wraps requests.Session.send so an over-limit OpenAI call raises
    before the underlying send runs — proving no paid request leaves the box."""
    import requests

    _set_total(meter, 99.0)

    sent = {"n": 0}
    real_send = requests.Session.send

    def tripwire(self, request, **kw):
        sent["n"] += 1
        raise AssertionError("the real network send was reached")

    try:
        requests.Session.send = tripwire
        meter.install()  # re-wraps the (tripwire) send with the limit check in front
        req = requests.Request(
            "POST", "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o-mini"},
        ).prepare()
        with pytest.raises(meter.DailyPaidLimitExceeded):
            requests.Session().send(req)
        assert sent["n"] == 0  # the real send was never reached
    finally:
        requests.Session.send = real_send


def test_requests_patch_allows_nonpaid_host(meter):
    """A non-paid host is never limit-checked, even over the limit."""
    import requests

    _set_total(meter, 99.0)
    reached = {"n": 0}
    real_send = requests.Session.send

    def fake_send(self, request, **kw):
        reached["n"] += 1

        class _R:
            status_code = 200
            content = b"{}"

        return _R()

    try:
        requests.Session.send = fake_send
        meter.install()
        req = requests.Request("GET", "https://example.com/health").prepare()
        requests.Session().send(req)  # must NOT raise
        assert reached["n"] == 1
    finally:
        requests.Session.send = real_send


# --------------------------------------------------------------------------- #
# cache expiry (60 s TTL)
# --------------------------------------------------------------------------- #
def test_cache_reads_db_once_within_ttl(meter, monkeypatch):
    calls = {"n": 0}

    def counting_query(day_str):
        calls["n"] += 1
        return 2.0

    meter._query_today_total_usd = counting_query
    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)

    # Freeze time so the TTL cannot expire between calls.
    monkeypatch.setattr(meter.time, "time", lambda: 1000.0)
    for _ in range(5):
        assert meter.check_daily_limit() is None
    assert calls["n"] == 1  # only the first call hit the DB


def test_cache_requeries_after_ttl(meter, monkeypatch):
    calls = {"n": 0}

    def counting_query(day_str):
        calls["n"] += 1
        return 2.0

    meter._query_today_total_usd = counting_query
    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)

    now = {"t": 1000.0}
    monkeypatch.setattr(meter.time, "time", lambda: now["t"])
    assert meter.check_daily_limit() is None
    assert calls["n"] == 1
    # Advance beyond the 60 s TTL -> the next check must re-query.
    now["t"] = 1000.0 + meter._LIMIT_CACHE_TTL + 1
    assert meter.check_daily_limit() is None
    assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# day boundary
# --------------------------------------------------------------------------- #
def test_cache_requeries_at_ny_day_boundary(meter, monkeypatch):
    """Even inside the 60 s TTL, the first check on a new NY day re-queries,
    because the cache is keyed on the NY calendar day."""
    seen_days = []

    def recording_query(day_str):
        seen_days.append(day_str)
        return 1.0

    meter._query_today_total_usd = recording_query
    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)

    # Freeze wall-clock so the TTL alone would keep the cache warm.
    monkeypatch.setattr(meter.time, "time", lambda: 5000.0)

    day1 = datetime(2026, 10, 10, 23, 59)
    day2 = datetime(2026, 10, 11, 0, 1)
    ny = {"dt": day1}
    monkeypatch.setattr(meter, "_ny_now", lambda: ny["dt"])

    assert meter.check_daily_limit() is None
    assert meter.check_daily_limit() is None  # same day, served from cache
    assert seen_days == ["2026-10-10"]

    ny["dt"] = day2  # NY day rolled over
    assert meter.check_daily_limit() is None
    assert seen_days == ["2026-10-10", "2026-10-11"]  # re-queried for the new day


# --------------------------------------------------------------------------- #
# fail-open
# --------------------------------------------------------------------------- #
def test_fail_open_on_db_error(meter):
    def boom(day_str):
        raise RuntimeError("DB down")

    meter._query_today_total_usd = boom
    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)
    # A meter/DB error must never block: check returns None (allow).
    assert meter.check_daily_limit() is None


# --------------------------------------------------------------------------- #
# alert once per day, exact format
# --------------------------------------------------------------------------- #
def test_alert_written_once_per_day_with_exact_format(meter, monkeypatch):
    _set_total(meter, 10.0)
    fixed = datetime(2026, 10, 10, 14, 5)
    monkeypatch.setattr(meter, "_ny_now", lambda: fixed)

    for _ in range(3):
        meter._limit_cache.update(expiry=0.0, total=0.0, day=None)
        with pytest.raises(meter.DailyPaidLimitExceeded):
            meter.check_daily_limit()

    lines = [ln for ln in open(meter.ALERTS_PATH).read().splitlines() if ln.strip()]
    assert len(lines) == 1  # once per day only
    assert lines[0] == "*** DAILY PAID LIMIT $8 reached at 14:05 ***"


def test_alert_rewrites_on_new_day(meter, monkeypatch):
    _set_total(meter, 10.0)
    day = {"dt": datetime(2026, 10, 10, 14, 5)}
    monkeypatch.setattr(meter, "_ny_now", lambda: day["dt"])

    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)
    with pytest.raises(meter.DailyPaidLimitExceeded):
        meter.check_daily_limit()

    day["dt"] = datetime(2026, 10, 11, 9, 30)
    meter._limit_cache.update(expiry=0.0, total=0.0, day=None)
    with pytest.raises(meter.DailyPaidLimitExceeded):
        meter.check_daily_limit()

    lines = [ln for ln in open(meter.ALERTS_PATH).read().splitlines() if ln.strip()]
    assert lines == [
        "*** DAILY PAID LIMIT $8 reached at 14:05 ***",
        "*** DAILY PAID LIMIT $8 reached at 09:30 ***",
    ]


# --------------------------------------------------------------------------- #
# Service wiring: the boto3 paid paths (AWS Translate, Polly) are NOT covered by
# the network meter patch, so they must call check_daily_limit() explicitly and
# refuse WITHOUT invoking the AWS client.
# --------------------------------------------------------------------------- #
import types


def _load_translation_service(monkeypatch):
    """Import translation_service with heavy deps stubbed, returning (module, meter)."""
    monkeypatch.syspath_prepend(os.path.join(_PROJECT_ROOT, "translation-service"))
    monkeypatch.syspath_prepend(os.path.join(_PROJECT_ROOT, "_meter"))

    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *a, **k: types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "boto3", boto3_stub)

    psycopg2_stub = types.ModuleType("psycopg2")
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2_stub)

    bs4_stub = types.ModuleType("bs4")
    bs4_stub.BeautifulSoup = object
    bs4_stub.NavigableString = object
    monkeypatch.setitem(sys.modules, "bs4", bs4_stub)

    import paid_api_meter as m
    importlib.reload(m)
    import translation_service as ts
    importlib.reload(ts)
    return ts, m


def test_translation_aws_path_refuses_without_calling_api(monkeypatch, tmp_path):
    ts, m = _load_translation_service(monkeypatch)
    monkeypatch.setenv("DAILY_PAID_LIMIT_USD", "8")
    m.ALERTS_PATH = str(tmp_path / "ALERTS.md")
    m._query_today_total_usd = lambda d: 99.0
    m._limit_cache.update(expiry=0.0, total=0.0, day=None)
    m._alerted_day = None

    svc = ts.TranslationService.__new__(ts.TranslationService)
    svc._AWS_MAX_CHARS = 9000

    def tripwire(**kw):
        raise AssertionError("AWS Translate was called despite the daily limit")

    svc.translate_client = types.SimpleNamespace(translate_text=tripwire)

    with pytest.raises(ts.DailyPaidLimitExceeded):
        svc._translate_text_aws("A genuine sentence that would be translated.", "es")


def test_translation_polly_path_refuses_without_calling_api(monkeypatch, tmp_path):
    ts, m = _load_translation_service(monkeypatch)
    monkeypatch.setenv("DAILY_PAID_LIMIT_USD", "8")
    m.ALERTS_PATH = str(tmp_path / "ALERTS.md")
    m._query_today_total_usd = lambda d: 99.0
    m._limit_cache.update(expiry=0.0, total=0.0, day=None)
    m._alerted_day = None

    svc = ts.TranslationService.__new__(ts.TranslationService)

    def tripwire(**kw):
        raise AssertionError("Polly was called despite the daily limit")

    svc.polly_client = types.SimpleNamespace(synthesize_speech=tripwire)

    # generate_audio runs the check BEFORE its try-block, so the hard STOP
    # propagates rather than being swallowed into a silent None (a half tour).
    with pytest.raises(ts.DailyPaidLimitExceeded):
        svc.generate_audio("Some stop narration text.", "ru")


def test_translation_under_limit_allows_api_call(monkeypatch, tmp_path):
    ts, m = _load_translation_service(monkeypatch)
    monkeypatch.setenv("DAILY_PAID_LIMIT_USD", "8")
    m.ALERTS_PATH = str(tmp_path / "ALERTS.md")
    m._query_today_total_usd = lambda d: 1.0  # well under
    m._limit_cache.update(expiry=0.0, total=0.0, day=None)

    svc = ts.TranslationService.__new__(ts.TranslationService)
    svc._AWS_MAX_CHARS = 9000

    called = {"n": 0}

    def ok(**kw):
        called["n"] += 1
        return {"TranslatedText": "Una frase."}

    svc.translate_client = types.SimpleNamespace(translate_text=ok)
    out = svc._translate_text_aws("A sentence.", "es")
    assert out == "Una frase."
    assert called["n"] == 1  # under the limit -> the paid call is made


def test_polly_tts_service_wires_the_check(monkeypatch):
    """polly_tts_service imports check_daily_limit and calls it on the paid path
    right before Polly synthesize (the closure is not importable, so assert the
    wiring at the source level)."""
    monkeypatch.syspath_prepend(os.path.join(_PROJECT_ROOT, "_meter"))
    path = os.path.join(_PROJECT_ROOT, "polly_tts_service.py")
    src = open(path).read()
    assert "from paid_api_meter import check_daily_limit as _check_daily_limit" in src
    # The check must appear before the synthesize_speech call in the source.
    i_check = src.index("_check_daily_limit()")
    i_polly = src.index("polly_client.synthesize_speech")
    assert i_check < i_polly
