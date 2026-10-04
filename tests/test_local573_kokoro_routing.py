"""
Test suite for LOCAL-573: Kokoro TTS engine switch
===================================================
Covers:
  * Routing predicates (English -> Kokoro, Russian/other -> Polly, switch off -> Polly)
  * Voice gender mapping (female -> af_heart, male -> am_michael)
  * Sample-rate mapping (neural English 24000, standard English 22050)
  * Service /synthesize behaviour with TTS_ENGINE=kokoro:
      - English voice renders via Kokoro, metered engine=kokoro at $0
      - Kokoro exception falls back to Polly (metered engine=polly at Polly cost)
      - Russian voice never touches Kokoro (metered Polly)
  * Default TTS_ENGINE=polly path is unchanged (Kokoro never called)
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)


# ── Pure routing logic (no boto3 / no kokoro model needed) ───────────────────

def test_routing_english_to_kokoro():
    import kokoro_engine as k
    for v in ("Joanna", "Matthew", "Amy", "Brian", "Ruth", "Ivy", "Emma"):
        assert k.should_use_kokoro(v, engine="kokoro") is True, v


def test_routing_nonenglish_stays_polly():
    import kokoro_engine as k
    for v in ("Tatyana", "Lucia", "Celine", "Marlene", "Zhiyu", "Seoyeon"):
        assert k.should_use_kokoro(v, engine="kokoro") is False, v


def test_routing_switch_off_stays_polly():
    import kokoro_engine as k
    assert k.should_use_kokoro("Joanna", engine="polly") is False


def test_voice_gender_mapping():
    import kokoro_engine as k
    assert k.kokoro_voice_for("Joanna") == "af_heart"
    assert k.kokoro_voice_for("Amy") == "af_heart"
    assert k.kokoro_voice_for("Matthew") == "am_michael"
    assert k.kokoro_voice_for("Brian") == "am_michael"


def test_sample_rate_mapping():
    import kokoro_engine as k
    # neural English voices -> 24000 (Polly neural MP3 default)
    assert k.target_sample_rate_for("Joanna") == 24000
    assert k.target_sample_rate_for("Matthew") == 24000
    # standard English voices -> 22050 (Polly standard MP3 default)
    assert k.target_sample_rate_for("Ivy") == 22050
    assert k.target_sample_rate_for("Ruth") == 22050


def test_env_var_drives_routing():
    import kokoro_engine as k
    old = os.environ.get("TTS_ENGINE")
    try:
        os.environ["TTS_ENGINE"] = "kokoro"
        assert k.should_use_kokoro("Joanna") is True
        os.environ["TTS_ENGINE"] = "polly"
        assert k.should_use_kokoro("Joanna") is False
    finally:
        if old is None:
            os.environ.pop("TTS_ENGINE", None)
        else:
            os.environ["TTS_ENGINE"] = old


# ── Service /synthesize behaviour (boto3 Polly + kokoro both mocked) ─────────

def _load_service_with_engine(engine):
    """Import polly_tts_service with TTS_ENGINE set, boto3 stubbed, kokoro patched.

    boto3 is not installed on the host (it lives in the container), so we inject a
    fake boto3 module whose client() returns a MagicMock. Returns (module, client).
    """
    import types

    os.environ["TTS_ENGINE"] = engine
    fake_polly_client = MagicMock()
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *a, **k: fake_polly_client
    # botocore.exceptions is imported by the service for ClientError/BotoCoreError.
    fake_botocore = types.ModuleType("botocore")
    fake_exc = types.ModuleType("botocore.exceptions")

    class _ClientError(Exception):
        pass

    class _BotoCoreError(Exception):
        pass

    fake_exc.ClientError = _ClientError
    fake_exc.BotoCoreError = _BotoCoreError
    fake_botocore.exceptions = fake_exc

    patched_modules = {
        "boto3": fake_boto3,
        "botocore": fake_botocore,
        "botocore.exceptions": fake_exc,
    }
    with patch.dict(sys.modules, patched_modules):
        if "polly_tts_service" in sys.modules:
            del sys.modules["polly_tts_service"]
        mod = importlib.import_module("polly_tts_service")
    mod.polly_client = fake_polly_client
    return mod, fake_polly_client


def _polly_response(payload=b"POLLYMP3"):
    stream = MagicMock()
    stream.read.return_value = payload
    return {"AudioStream": stream}


def test_english_renders_kokoro_and_meters_zero():
    mod, polly = _load_service_with_engine("kokoro")
    fake_k = MagicMock()
    fake_k.should_use_kokoro.return_value = True
    fake_k.synthesize_to_mp3.return_value = b"KOKOROMP3"
    mod.kokoro_engine = fake_k

    recorded = {}

    def _fake_record(**kwargs):
        recorded.update(kwargs)
        return "row-1"

    with patch("cost_meter.record_operation", side_effect=_fake_record):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"KOKOROMP3"
    polly.synthesize_speech.assert_not_called()
    assert recorded["breakdown"]["engine"] == "kokoro"
    assert recorded["our_cost_usd"] == 0.0


def test_kokoro_exception_falls_back_to_polly():
    mod, polly = _load_service_with_engine("kokoro")
    polly.synthesize_speech.return_value = _polly_response(b"POLLYMP3")
    fake_k = MagicMock()
    fake_k.should_use_kokoro.return_value = True
    fake_k.synthesize_to_mp3.side_effect = RuntimeError("boom")
    mod.kokoro_engine = fake_k

    recorded = {}
    with patch("cost_meter.record_operation", side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello world", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"POLLYMP3"
    polly.synthesize_speech.assert_called_once()
    # Fell back entirely to Polly -> metered as the Polly engine (neural for Joanna), cost > 0
    assert recorded["breakdown"]["engine"] == "neural"
    assert recorded["our_cost_usd"] > 0.0


def test_russian_never_uses_kokoro():
    mod, polly = _load_service_with_engine("kokoro")
    polly.synthesize_speech.return_value = _polly_response(b"RUPOLLY")
    fake_k = MagicMock()
    # Real routing: Tatyana is not English, so should_use_kokoro is False.
    fake_k.should_use_kokoro.side_effect = lambda v, engine=None: v in (
        "Joanna", "Matthew", "Amy", "Brian",
    )
    mod.kokoro_engine = fake_k

    recorded = {}
    with patch("cost_meter.record_operation", side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Privet mir", "voice_id": "Tatyana"})

    assert resp.status_code == 200
    assert resp.data == b"RUPOLLY"
    fake_k.synthesize_to_mp3.assert_not_called()
    polly.synthesize_speech.assert_called_once()
    assert recorded["breakdown"]["engine"] == "standard"  # Tatyana = Polly standard
    assert recorded["our_cost_usd"] > 0.0


def test_default_polly_engine_never_calls_kokoro():
    mod, polly = _load_service_with_engine("polly")
    polly.synthesize_speech.return_value = _polly_response(b"POLLYDEFAULT")
    fake_k = MagicMock()
    mod.kokoro_engine = fake_k  # present but must never be used when engine=polly

    recorded = {}
    with patch("cost_meter.record_operation", side_effect=lambda **kw: recorded.update(kw) or "row"):
        client = mod.app.test_client()
        resp = client.post("/synthesize", json={"text": "Hello", "voice_id": "Joanna"})

    assert resp.status_code == 200
    assert resp.data == b"POLLYDEFAULT"
    fake_k.synthesize_to_mp3.assert_not_called()
    fake_k.should_use_kokoro.assert_not_called()
    polly.synthesize_speech.assert_called_once()
    assert recorded["breakdown"]["engine"] == "neural"
    assert recorded["our_cost_usd"] > 0.0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
