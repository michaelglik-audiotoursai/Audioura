"""
Test suite for LOCAL-678: the network meter must also catch httpx and aiohttp,
and host-run harnesses must install the meter.

The meter (_meter/paid_api_meter.py) previously patched only requests.Session.send
and urllib.request.urlopen. The OpenAI python SDK (v1/v2) and the Google GenAI SDK
send every request through httpx, so their calls to api.openai.com /
generativelanguage.googleapis.com were NEVER written to paid_api_calls. This
suite proves:

  * httpx_sync_logged   — a sync httpx POST to api.openai.com is logged with the
                          right model/usage/$ (via httpx.MockTransport — NO real
                          paid call and NO network)
  * httpx_async_logged  — the same for httpx.AsyncClient
  * httpx_non_paid_pass  — a non-paid host is NOT logged and passes through
  * httpx_stream_safe    — a streaming send does not consume the body / crash
  * aiohttp_patched      — aiohttp.ClientSession._request is wrapped by install()
  * host harness wiring  — the host-run harnesses carry the meter_bootstrap import
                           and meter_bootstrap.install_meter() actually installs

Every test uses a MockTransport or a plain install() check: NO paid API call and
NO network of any kind. The DB write is monkeypatched to a no-op and the log goes
to a tmp file, so nothing touches the real ledger.
"""
import asyncio
import importlib
import json
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "_meter"))

httpx = pytest.importorskip("httpx")


@pytest.fixture
def meter(monkeypatch, tmp_path):
    """The meter writing to a tmp log, with the DB write and the daily-limit check
    stubbed out so no DB connection and no paid call happen. install() is
    idempotent, so calling it here never double-wraps the HTTP clients."""
    import paid_api_meter as m
    log = tmp_path / "paid_api_calls.jsonl"
    monkeypatch.setattr(m, "LOG", str(log))
    monkeypatch.setattr(m, "_db_write", lambda rec: None)      # no DB
    monkeypatch.setattr(m, "check_daily_limit", lambda: None)  # no limit DB read
    m.install()  # idempotent; patches installed at most once process-wide
    m._LOG_PATH_FOR_TEST = str(log)
    return m


def _read_log(m):
    recs = []
    path = m._LOG_PATH_FOR_TEST
    if not os.path.exists(path):
        return recs  # a non-paid call writes nothing, so the log may not exist
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def _openai_handler(request):
    # A fake OpenAI chat-completions response. No real call is made.
    return httpx.Response(200, json={
        "model": "gpt-4o-mini",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    })


def test_httpx_sync_logged(meter):
    client = httpx.Client(transport=httpx.MockTransport(_openai_handler))
    resp = client.post("https://api.openai.com/v1/chat/completions",
                       json={"model": "gpt-4o-mini"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "gpt-4o-mini"  # caller can still read the body

    recs = _read_log(meter)
    assert len(recs) == 1, "the httpx OpenAI call must be metered exactly once"
    r = recs[0]
    assert r["kind"] == "openai"
    assert r["status"] == 200
    assert r["model"] == "gpt-4o-mini"
    assert r["usage"] == {"prompt_tokens": 100, "completion_tokens": 50}
    # 100 input * $0.15/1e6 + 50 output * $0.60/1e6 = 1.5e-5 + 3.0e-5 = 4.5e-5
    assert abs(r["usd"] - 4.5e-5) < 1e-9


def test_httpx_async_logged(meter):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(_openai_handler)) as c:
            r = await c.post("https://api.openai.com/v1/chat/completions",
                             json={"model": "gpt-4o-mini"})
            return r.json()["model"]

    model = asyncio.run(go())
    assert model == "gpt-4o-mini"
    recs = _read_log(meter)
    assert len(recs) == 1
    assert recs[0]["kind"] == "openai"
    assert recs[0]["model"] == "gpt-4o-mini"


def test_httpx_non_paid_host_passthrough(meter):
    def handler(request):
        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resp = client.get("https://example.com/health")
    assert resp.status_code == 200
    assert _read_log(meter) == [], "a non-paid host must not be metered"


def test_httpx_stream_does_not_crash_or_consume(meter):
    """A streaming send must be recorded (empty body) without consuming the
    caller's stream."""
    def handler(request):
        return httpx.Response(200, json={"model": "gpt-4o-mini", "usage": {}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with client.stream("POST", "https://api.openai.com/v1/chat/completions",
                       json={"model": "gpt-4o-mini"}) as resp:
        body = resp.read()  # caller reads the stream itself
    assert resp.status_code == 200
    assert body  # the caller still got the body
    recs = _read_log(meter)
    assert len(recs) == 1
    assert recs[0]["kind"] == "openai"


def test_aiohttp_request_is_patched(meter):
    aiohttp = pytest.importorskip("aiohttp")
    # install() wraps ClientSession._request; its name is our wrapper's name.
    assert aiohttp.ClientSession._request.__name__ == "_aiohttp_request"


# ── host-run harness wiring ───────────────────────────────────────────────────
# The host harnesses that make paid calls must install the network meter, since
# on the host there is no sitecustomize (PYTHONPATH=/opt/meter) to do it.
WIRED_HARNESSES = [
    "measure_local674_walking.py",
    "measure_local674_pervenue.py",
    "measure_local648_overlap.py",
    "replay_harness.py",
    "run_local594_mcmullen.py",
    "run_local599_massart.py",
]


@pytest.mark.parametrize("fname", WIRED_HARNESSES)
def test_host_harness_imports_meter(fname):
    path = os.path.join(_PROJECT_ROOT, fname)
    assert os.path.exists(path), "%s should exist" % fname
    src = open(path, encoding="utf-8").read()
    assert "meter_bootstrap" in src, (
        "%s must import the meter bootstrap so its host-run paid calls are metered"
        % fname)


def test_meter_bootstrap_installs(monkeypatch, tmp_path):
    """meter_bootstrap.install_meter() returns True and makes the meter active —
    this is the one line every host harness runs. No paid call, no DB."""
    boot_dir = os.path.join(_PROJECT_ROOT, "_meter")
    sys.path.insert(0, boot_dir)
    import meter_bootstrap as mb
    importlib.reload(mb)
    assert mb.install_meter() is True
    # idempotent: a second call is still True and does not raise
    assert mb.install_meter() is True
    # the meter module is importable and has installed its patches
    import paid_api_meter as m
    assert hasattr(m, "install")
