"""
Test suite for LOCAL-768: Kokoro baked INTO the voice (polly-tts) image.
========================================================================
D667 (LEAD ruling): NO separate Kokoro service on GCloud. Kokoro runs
*in-process* inside polly_tts_service — the r1 mode the code already has:
``TTS_ENGINE=kokoro`` with ``KOKORO_URL=''`` (empty) loads kokoro_engine
in-process, renders English there, and falls back to Polly on any error;
non-English stays Polly. The Mac keeps its host-native Kokoro on :5181; only
the GCloud image changes (Dockerfile.polly-tts-kokoro bakes the model + voices).

These tests pin the behaviour the GCloud image depends on:
  * In-process English render (KOKORO_URL unset) uses the in-process encoder,
    never a host HTTP call, and never Polly; metered engine=kokoro at $0.
  * Non-English (Russian) in-process config still goes to Polly.
  * An in-process Kokoro failure falls back to Polly so a tour never loses audio.
  * /health reports the engine, the kokoro mode (in_process vs host), whether the
    model is loaded, and whether ffmpeg is present — so "healthy" on GCloud means
    "this instance can actually render Kokoro MP3", not just "Polly reachable".

RED before the /health enhancement: the health-report tests assert keys
(``kokoro_mode``, ``model_loaded``, ``ffmpeg_present``) that do not exist on the
subscribed base, so they fail until polly_tts_service.health_check is enhanced;
GREEN after. The routing/render tests document the in-process contract the image
relies on.

boto3 / requests are not installed on the host (they live in the container), so
they are injected as fakes exactly as in test_local573_kokoro_routing.py.
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, patch

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


# ── service loader (mirrors test_local573) ──────────────────────────────────

def _load_service(engine="kokoro", kokoro_url="", fake_requests=None):
    """Import polly_tts_service with TTS_ENGINE / KOKORO_URL set and boto3/
    botocore (and optionally requests) injected as fakes. Pass kokoro_url=""
    (default) to exercise the in-process path LOCAL-768 ships. Returns
    (module, fake_polly_client)."""
    os.environ["TTS_ENGINE"] = engine
    if kokoro_url is None:
        os.environ.pop("KOKORO_URL", None)
    else:
        os.environ["KOKORO_URL"] = kokoro_url

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


def _fake_requests_module():
    """A fake requests whose .post records calls, so we can assert the
    in-process path made NO host HTTP call."""
    module = types.ModuleType("requests")
    module.calls = []

    def _post(url, **kwargs):
        module.calls.append((url, kwargs))
        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"SHOULD_NOT_BE_USED"
        return resp

    module.post = _post
    return module


def _polly_response(payload=b"POLLYMP3"):
    stream = MagicMock()
    stream.read.return_value = payload
    return {"AudioStream": stream}


# ── in-process English render (the GCloud image path) ────────────────────────

def test_inprocess_english_render_no_host_no_polly():
    """TTS_ENGINE=kokoro + empty KOKORO_URL: an English stop renders with the
    in-process encoder, makes NO host HTTP call, and never touches Polly;
    metered engine=kokoro at $0."""
    freq = _fake_requests_module()
    mod, polly = _load_service(engine="kokoro", kokoro_url="", fake_requests=freq)
    fake_k = MagicMock()
    fake_k.should_use_kokoro.return_value = True
    fake_k.synthesize_to_mp3.return_value = b"KOKOROMP3"
    mod.kokoro_engine = fake_k

    recorded = {}
    with patch("cost_meter.record_operation",
               side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize",
                           json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"KOKOROMP3"
    fake_k.synthesize_to_mp3.assert_called_once()   # in-process encoder used
    assert len(freq.calls) == 0                      # NO host HTTP call
    polly.synthesize_speech.assert_not_called()      # NO Polly
    assert recorded["breakdown"]["engine"] == "kokoro"
    assert recorded["our_cost_usd"] == 0.0


def test_inprocess_nonenglish_stays_polly():
    """Russian (Tatyana) in the in-process config still goes to Polly — only
    English voices route to Kokoro."""
    freq = _fake_requests_module()
    mod, polly = _load_service(engine="kokoro", kokoro_url="", fake_requests=freq)
    polly.synthesize_speech.return_value = _polly_response(b"RUPOLLY")
    fake_k = MagicMock()
    fake_k.should_use_kokoro.side_effect = lambda v, engine=None: v in (
        "Joanna", "Matthew", "Amy", "Brian")
    mod.kokoro_engine = fake_k

    recorded = {}
    with patch("cost_meter.record_operation",
               side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize",
                           json={"text": "Privet mir", "voice_id": "Tatyana"})

    assert resp.status_code == 200
    assert resp.data == b"RUPOLLY"
    fake_k.synthesize_to_mp3.assert_not_called()
    assert len(freq.calls) == 0
    polly.synthesize_speech.assert_called_once()
    assert recorded["breakdown"]["engine"] == "standard"
    assert recorded["our_cost_usd"] > 0.0


def test_inprocess_failure_falls_back_to_polly():
    """An in-process Kokoro failure must fall back to Polly so a tour never loses
    audio (metered as the Polly engine, cost > 0)."""
    mod, polly = _load_service(engine="kokoro", kokoro_url="")
    polly.synthesize_speech.return_value = _polly_response(b"POLLYMP3")
    fake_k = MagicMock()
    fake_k.should_use_kokoro.return_value = True
    fake_k.synthesize_to_mp3.side_effect = RuntimeError("model boom")
    mod.kokoro_engine = fake_k

    recorded = {}
    with patch("cost_meter.record_operation",
               side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize",
                           json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"POLLYMP3"
    polly.synthesize_speech.assert_called_once()
    assert recorded["breakdown"]["engine"] == "neural"
    assert recorded["our_cost_usd"] > 0.0


# ── /health reports engine + kokoro mode + model loaded + ffmpeg ─────────────

def test_health_inprocess_reports_engine_mode_model_ffmpeg():
    """With TTS_ENGINE=kokoro + empty KOKORO_URL, /health reports the engine,
    the in-process mode, whether the model is loaded, and whether ffmpeg is
    present — the signal GCloud uses to know an instance can render Kokoro."""
    mod, _ = _load_service(engine="kokoro", kokoro_url="")
    fake_k = MagicMock()
    fake_k.model_loaded.return_value = True
    fake_k.ffmpeg_present.return_value = True
    mod.kokoro_engine = fake_k

    client = mod.app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()

    assert body["tts_engine"] == "kokoro"
    assert body["kokoro_mode"] == "in_process"
    assert body["model_loaded"] is True
    assert body["ffmpeg_present"] is True


def test_health_inprocess_model_not_loaded_reports_false():
    """If the in-process model did not load (or ffmpeg is missing), /health
    reports it rather than claiming healthy — 'can render Kokoro' is explicit."""
    mod, _ = _load_service(engine="kokoro", kokoro_url="")
    fake_k = MagicMock()
    fake_k.model_loaded.return_value = False
    fake_k.ffmpeg_present.return_value = False
    mod.kokoro_engine = fake_k

    client = mod.app.test_client()
    body = client.get("/health").get_json()
    assert body["tts_engine"] == "kokoro"
    assert body["kokoro_mode"] == "in_process"
    assert body["model_loaded"] is False
    assert body["ffmpeg_present"] is False


def test_health_host_mode_reported_when_kokoro_url_set():
    """When KOKORO_URL is set (the Mac host path), /health reports kokoro_mode
    'host' and does not claim an in-process model is loaded."""
    freq = _fake_requests_module()
    mod, _ = _load_service(engine="kokoro",
                           kokoro_url="http://host.docker.internal:5181/render",
                           fake_requests=freq)
    fake_k = MagicMock()
    mod.kokoro_engine = fake_k

    client = mod.app.test_client()
    body = client.get("/health").get_json()
    assert body["tts_engine"] == "kokoro"
    assert body["kokoro_mode"] == "host"
    # In host mode this instance does not load the model itself.
    assert body["model_loaded"] is False


def test_health_polly_default_unchanged_fields_present():
    """Default TTS_ENGINE=polly keeps its original fields and marks kokoro off:
    engine polly, no kokoro mode, model not loaded. The Beta Polly image's health
    semantics are preserved (still reports polly_available)."""
    mod, _ = _load_service(engine="polly", kokoro_url="")
    client = mod.app.test_client()
    body = client.get("/health").get_json()

    assert body["tts_engine"] == "polly"
    assert body["service"] == "polly_tts"
    assert "polly_available" in body
    assert body["kokoro_mode"] is None
    assert body["model_loaded"] is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
