#!/usr/bin/env python3
"""
Test suite for LOCAL-768: Kokoro as a private Cloud Run container.
==================================================================
On Cloud Run the Kokoro service (``kokoro_host_service.py``, now containerised)
is PRIVATE (Cloud Run IAM). ``polly_tts_service`` reaches it over ``KOKORO_URL``
and — when ``KOKORO_AUDIENCE`` is set — must attach a Google-signed identity
token (``Authorization: Bearer <id-token>``) fetched from the metadata server
and cached ~50 min. With ``KOKORO_AUDIENCE`` unset the behaviour is exactly
today's (the Mac host, no auth header). Any token error falls back to Polly via
the existing path, logged ``[LOCAL-768]``.

This file holds the RED tests for the new behaviour (they fail on the subscribed
base because the token seam does not exist yet) and the host ``$PORT`` / health
guards for the container:

  1. ``KOKORO_AUDIENCE`` set  -> the /render POST carries ``Authorization:
     Bearer <token>``; the audience passed to the token fetch == KOKORO_AUDIENCE.
  2. ``KOKORO_AUDIENCE`` unset -> NO Authorization header (today's Mac behaviour).
  3. Token fetch raises/returns no token -> fall back to Polly (never ship a
     tour with no audio), metered as the Polly engine.
  4. The token is cached: two requests fetch the token at most once.
  5. ``kokoro_host_service`` binds ``$PORT`` (Cloud Run) with precedence over
     ``KOKORO_PORT``; default 5181 when neither is set.
  6. ``/health`` is 503 ("no_ffmpeg") when ffmpeg is absent even if the model is
     loaded, and 503 ("loading") when the model is not ready — so "healthy"
     really means "can render an MP3".

boto3 / botocore / requests are injected as fakes (they live only in the
container), mirroring tests/test_local573_kokoro_routing.py.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_tts_env():
    """Snapshot and restore the TTS env vars this suite mutates so a value set
    here (notably KOKORO_AUDIENCE) never leaks into other test files, whatever
    the collection order."""
    keys = ("TTS_ENGINE", "KOKORO_URL", "KOKORO_AUDIENCE", "PORT", "KOKORO_PORT")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        # Drop the possibly-imported service module so the next file re-imports
        # it with its own env, not this suite's.
        sys.modules.pop("polly_tts_service", None)
        sys.modules.pop("kokoro_host_service", None)


# ── Service loader (boto3/botocore/requests faked) ───────────────────────────

def _load_service(engine="kokoro", kokoro_url="https://kokoro-subscribed.run.app/render",
                  audience=None, fake_requests=None):
    """Import polly_tts_service with TTS_ENGINE / KOKORO_URL / KOKORO_AUDIENCE set
    and boto3+botocore(+requests) injected. Returns (module, polly_client)."""
    os.environ["TTS_ENGINE"] = engine
    if kokoro_url is None:
        os.environ.pop("KOKORO_URL", None)
    else:
        os.environ["KOKORO_URL"] = kokoro_url
    if audience is None:
        os.environ.pop("KOKORO_AUDIENCE", None)
    else:
        os.environ["KOKORO_AUDIENCE"] = audience

    fake_polly_client = MagicMock()
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *a, **k: fake_polly_client
    fake_botocore = types.ModuleType("botocore")
    fake_exc = types.ModuleType("botocore.exceptions")

    class _ClientError(Exception):
        pass

    class _BotoCoreError(Exception):
        pass

    fake_exc.ClientError = _ClientError
    fake_exc.BotoCoreError = _BotoCoreError
    fake_botocore.exceptions = fake_exc

    patched = {
        "boto3": fake_boto3,
        "botocore": fake_botocore,
        "botocore.exceptions": fake_exc,
    }
    if fake_requests is not None:
        patched["requests"] = fake_requests
    with patch.dict(sys.modules, patched):
        if "polly_tts_service" in sys.modules:
            del sys.modules["polly_tts_service"]
        mod = importlib.import_module("polly_tts_service")
    mod.polly_client = fake_polly_client
    return mod, fake_polly_client


def _fake_requests_module(render_status=200, render_content=b"KOKOROMP3",
                          render_exc=None, metadata_token="id-token-xyz",
                          metadata_status=200, metadata_exc=None):
    """Fake ``requests`` with .post (the /render call, records (url,kwargs) in
    .calls) and .get (the metadata identity call, records audiences in
    .metadata_calls). metadata_token=None -> no token returned."""
    module = types.ModuleType("requests")
    module.calls = []
    module.metadata_calls = []

    def _post(url, **kwargs):
        module.calls.append((url, kwargs))
        if render_exc is not None:
            raise render_exc
        resp = MagicMock()
        resp.status_code = render_status
        resp.content = render_content
        return resp

    def _get(url, **kwargs):
        module.metadata_calls.append((url, kwargs))
        if metadata_exc is not None:
            raise metadata_exc
        resp = MagicMock()
        resp.status_code = metadata_status
        resp.text = metadata_token or ""
        return resp

    module.post = _post
    module.get = _get
    return module


def _polly_response(payload=b"POLLYMP3"):
    stream = MagicMock()
    stream.read.return_value = payload
    return {"AudioStream": stream}


def _english_kokoro_mock():
    fake_k = MagicMock()
    fake_k.should_use_kokoro.return_value = True
    return fake_k


# ── 1. KOKORO_AUDIENCE set -> Bearer token on the /render call ───────────────

def test_audience_set_attaches_bearer_token():
    aud = "https://kokoro-subscribed.run.app"
    freq = _fake_requests_module(metadata_token="id-token-xyz")
    mod, polly = _load_service(
        kokoro_url=aud + "/render", audience=aud, fake_requests=freq)
    mod.kokoro_engine = _english_kokoro_mock()

    with patch("cost_meter.record_operation", side_effect=lambda **kw: "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"KOKOROMP3"
    polly.synthesize_speech.assert_not_called()
    # Exactly one /render POST carrying the bearer token.
    assert len(freq.calls) == 1, freq.calls
    _url, _kw = freq.calls[0]
    headers = _kw.get("headers") or {}
    assert headers.get("Authorization") == "Bearer id-token-xyz", headers
    # The metadata identity call used the audience == KOKORO_AUDIENCE.
    assert len(freq.metadata_calls) >= 1
    md_url, md_kw = freq.metadata_calls[0]
    assert aud in (md_url + str(md_kw.get("params") or "")), (md_url, md_kw)
    assert (md_kw.get("headers") or {}).get("Metadata-Flavor") == "Google"


# ── 2. KOKORO_AUDIENCE unset -> no Authorization header (today's behaviour) ──

def test_audience_unset_no_auth_header():
    freq = _fake_requests_module()
    mod, polly = _load_service(
        kokoro_url="http://host.docker.internal:5181/render",
        audience=None, fake_requests=freq)
    mod.kokoro_engine = _english_kokoro_mock()

    with patch("cost_meter.record_operation", side_effect=lambda **kw: "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"KOKOROMP3"
    assert len(freq.calls) == 1
    _url, _kw = freq.calls[0]
    headers = _kw.get("headers") or {}
    assert "Authorization" not in headers, headers
    # No metadata server contacted when no audience is configured.
    assert len(freq.metadata_calls) == 0, freq.metadata_calls


# ── 3. Token fetch failure -> Polly fallback (never lose audio) ──────────────

def test_token_fetch_failure_falls_back_to_polly():
    aud = "https://kokoro-subscribed.run.app"
    freq = _fake_requests_module(metadata_exc=RuntimeError("metadata unreachable"))
    mod, polly = _load_service(
        kokoro_url=aud + "/render", audience=aud, fake_requests=freq)
    polly.synthesize_speech.return_value = _polly_response(b"POLLYMP3")
    mod.kokoro_engine = _english_kokoro_mock()

    recorded = {}
    with patch("cost_meter.record_operation",
               side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello world", "voice_id": "Joanna"})

    # The tour still gets audio — from Polly — and is metered as Polly.
    assert resp.status_code == 200
    assert resp.data == b"POLLYMP3"
    polly.synthesize_speech.assert_called_once()
    assert recorded["breakdown"]["engine"] == "neural"
    assert recorded["our_cost_usd"] > 0.0


def test_token_empty_falls_back_to_polly():
    # Metadata returns 200 but an empty token -> treat as no token -> Polly.
    aud = "https://kokoro-subscribed.run.app"
    freq = _fake_requests_module(metadata_token=None, metadata_status=200)
    mod, polly = _load_service(
        kokoro_url=aud + "/render", audience=aud, fake_requests=freq)
    polly.synthesize_speech.return_value = _polly_response(b"POLLYMP3")
    mod.kokoro_engine = _english_kokoro_mock()

    with patch("cost_meter.record_operation", side_effect=lambda **kw: "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hi", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"POLLYMP3"
    polly.synthesize_speech.assert_called_once()


# ── 4. Token is cached across requests ───────────────────────────────────────

def test_token_is_cached_across_requests():
    aud = "https://kokoro-subscribed.run.app"
    freq = _fake_requests_module(metadata_token="id-token-xyz")
    mod, polly = _load_service(
        kokoro_url=aud + "/render", audience=aud, fake_requests=freq)
    mod.kokoro_engine = _english_kokoro_mock()

    with patch("cost_meter.record_operation", side_effect=lambda **kw: "row"):
        client = mod.app.test_client()
        r1 = client.post("/synthesize", json={"text": "One", "voice_id": "Joanna"})
        r2 = client.post("/synthesize", json={"text": "Two", "voice_id": "Joanna"})

    assert r1.status_code == 200 and r2.status_code == 200
    assert len(freq.calls) == 2  # two renders
    # Token fetched at most once (cached ~50 min) despite two renders.
    assert len(freq.metadata_calls) <= 1, freq.metadata_calls


# ── 5. kokoro_host_service binds $PORT (Cloud Run) ───────────────────────────

def _reload_host_service():
    if "kokoro_host_service" in sys.modules:
        del sys.modules["kokoro_host_service"]
    # kokoro_engine is imported by the host service at module load; it is a
    # light module (heavy deps imported lazily) so this is safe off-container.
    return importlib.import_module("kokoro_host_service")


def test_host_binds_dollar_port_cloud_run():
    old_port = os.environ.get("PORT")
    old_kport = os.environ.get("KOKORO_PORT")
    try:
        os.environ["PORT"] = "8080"          # Cloud Run injects $PORT
        os.environ.pop("KOKORO_PORT", None)
        host = _reload_host_service()
        assert host.PORT == 8080, host.PORT
    finally:
        if old_port is None:
            os.environ.pop("PORT", None)
        else:
            os.environ["PORT"] = old_port
        if old_kport is not None:
            os.environ["KOKORO_PORT"] = old_kport


def test_host_port_default_and_precedence():
    old_port = os.environ.get("PORT")
    old_kport = os.environ.get("KOKORO_PORT")
    try:
        # Neither set -> default 5181 (host launchd behaviour).
        os.environ.pop("PORT", None)
        os.environ.pop("KOKORO_PORT", None)
        host = _reload_host_service()
        assert host.PORT == 5181, host.PORT

        # $PORT takes precedence over KOKORO_PORT on Cloud Run.
        os.environ["KOKORO_PORT"] = "5181"
        os.environ["PORT"] = "9090"
        host = _reload_host_service()
        assert host.PORT == 9090, host.PORT
    finally:
        if old_port is None:
            os.environ.pop("PORT", None)
        else:
            os.environ["PORT"] = old_port
        if old_kport is None:
            os.environ.pop("KOKORO_PORT", None)
        else:
            os.environ["KOKORO_PORT"] = old_kport


# ── 6. /health means "can render" (ffmpeg + model) ──────────────────────────

def _health_status_for(pipeline_ready, ffmpeg_path):
    """Drive the host /health handler with the given state and return (code, body)."""
    import json as _json

    host = _reload_host_service()
    host._pipeline_ready = pipeline_ready
    host._pipeline_error = None if pipeline_ready else "not loaded"

    captured = {}

    class _FakeHandler(host.KokoroHandler):
        def __init__(self):  # bypass BaseHTTPRequestHandler socket setup
            self.path = "/health"

        def _send_json(self, code, obj):
            captured["code"] = code
            captured["obj"] = obj

    with patch.object(host.shutil, "which", return_value=ffmpeg_path):
        _FakeHandler().do_GET()
    return captured["code"], captured["obj"]


def test_health_fails_without_ffmpeg():
    code, body = _health_status_for(pipeline_ready=True, ffmpeg_path=None)
    assert code == 503, (code, body)
    assert body["status"] == "no_ffmpeg", body


def test_health_fails_without_model():
    code, body = _health_status_for(pipeline_ready=False, ffmpeg_path="/usr/bin/ffmpeg")
    assert code == 503, (code, body)
    assert body["status"] == "loading", body


def test_health_ok_with_ffmpeg_and_model():
    code, body = _health_status_for(pipeline_ready=True, ffmpeg_path="/usr/bin/ffmpeg")
    assert code == 200, (code, body)
    assert body["status"] == "healthy", body


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
