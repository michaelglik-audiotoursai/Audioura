"""
Test suite for LOCAL-575: Kokoro MP3s report only the first chunk's duration.
=============================================================================
Field defect (Michael, tour 388): a stop over 2,000 chars is split into chunks
by polly_tts_service; each Kokoro chunk is encoded to its OWN MP3 (ffmpeg writes
a Xing/Info header per encode) and the chunks were byte-concatenated. The player
trusts the FIRST header, so its timer describes only the first chunk and runs out
early while audio keeps playing. Polly's raw MP3 frames carry no Xing header,
which is why Polly tours never showed this.

What these tests prove:
  * The DEFECT is real: byte-concatenating per-chunk MP3s yields a file whose
    HEADER duration (mutagen) is far shorter than its REAL decoded duration
    (ffprobe) — the header ≈ the first chunk only.
  * The FIX (kokoro_engine.combine_mp3_chunks) decodes every chunk to PCM,
    concatenates, and encodes ONE MP3 whose header duration == real decoded
    duration within 1 %.
  * End to end: a 4,500-char request through polly_tts_service's /synthesize on
    the in-process Kokoro path produces a single MP3 whose header == real within
    1 % (the chunks are no longer byte-concatenated).

RED on subscribed HEAD / GREEN after: combine_mp3_chunks does not exist on the
subscribed base, so the fix tests error there and pass once implemented.

Requires ffmpeg + ffprobe (host has both) and mutagen for the header read. If
any is missing the test is skipped rather than falsely failing.
"""

import os
import shutil
import subprocess
import sys
import wave

import pytest

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")

try:
    from mutagen.mp3 import MP3  # type: ignore
    _HAVE_MUTAGEN = True
except Exception:  # noqa: BLE001
    _HAVE_MUTAGEN = False

try:
    import numpy as np  # noqa: F401
    _HAVE_NUMPY = True
except Exception:  # noqa: BLE001
    _HAVE_NUMPY = False

_requires_tools = pytest.mark.skipif(
    not (_FFMPEG and _FFPROBE and _HAVE_MUTAGEN and _HAVE_NUMPY),
    reason="needs ffmpeg, ffprobe, mutagen and numpy",
)

SAMPLE_RATE = 24000  # neural English (Joanna) — matches kokoro_engine


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_pcm(seconds, freq=220.0, sample_rate=SAMPLE_RATE):
    """A mono s16le sine of ``seconds`` at ``sample_rate`` (bytes)."""
    import numpy as np

    n = int(seconds * sample_rate)
    t = np.arange(n, dtype="float32") / sample_rate
    wave_f = (0.25 * np.sin(2 * np.pi * freq * t)).astype("float32")
    return (np.clip(wave_f, -1, 1) * 32767).astype("<i2").tobytes()


def _pcm_to_mp3_chunk(pcm, sample_rate=SAMPLE_RATE, bitrate="48k"):
    """Encode PCM to an MP3 the way the per-chunk Kokoro encoder does: via a WAV
    container, so ffmpeg writes a Xing/Info header for this chunk. This is what
    produced the multi-header files in the field."""
    import tempfile

    d = tempfile.mkdtemp(prefix="l575_")
    try:
        wav_p = os.path.join(d, "c.wav")
        mp3_p = os.path.join(d, "c.mp3")
        with wave.open(wav_p, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm)
        subprocess.run(
            [_FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-i", wav_p, "-ac", "1", "-ar", str(sample_rate),
             "-b:a", bitrate, "-f", "mp3", mp3_p],
            check=True, capture_output=True,
        )
        with open(mp3_p, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _header_duration(mp3_bytes):
    """Duration the player trusts: mutagen reads the first MPEG/Xing header."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as t:
        t.write(mp3_bytes)
        p = t.name
    try:
        return MP3(p).info.length
    finally:
        os.unlink(p)


def _real_duration(mp3_bytes):
    """Real duration: ffprobe decodes/counts every frame (ignores the header)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as t:
        t.write(mp3_bytes)
        p = t.name
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", p],
            check=True, capture_output=True,
        )
        return float(out.stdout.decode().strip())
    finally:
        os.unlink(p)


def _xing_count(mp3_bytes):
    """Count Xing/Info headers — one per chunk encode. >1 means multi-header."""
    return mp3_bytes.count(b"Xing") + mp3_bytes.count(b"Info")


# ── the defect is real (characterisation; no fix needed to run) ───────────────

@_requires_tools
def test_byte_concat_header_undercounts_duration():
    """Byte-concatenating per-chunk MP3s (today's bug) yields a file whose header
    duration ≈ the first chunk only, far below the real total."""
    durations = [8.0, 7.0, 6.0]
    chunks = [_pcm_to_mp3_chunk(_make_pcm(s)) for s in durations]
    concatenated = b"".join(chunks)

    assert _xing_count(concatenated) >= len(chunks)  # multiple headers present
    header = _header_duration(concatenated)
    real = _real_duration(concatenated)
    first = durations[0]
    # Header tracks the FIRST chunk, not the sum.
    assert abs(header - first) < 1.0, (header, first)
    assert real > sum(durations) * 0.9, (real, sum(durations))
    # And the header grossly under-reports the real duration (the field defect).
    assert header < real * 0.6, (header, real)


# ── the fix: one header, correct total duration ───────────────────────────────

@_requires_tools
def test_combine_mp3_chunks_single_correct_header():
    """combine_mp3_chunks decodes every chunk to PCM, concatenates and encodes a
    single MP3 whose header duration == real decoded duration within 1 %."""
    import kokoro_engine

    durations = [8.0, 7.0, 6.0, 5.0]
    chunks = [_pcm_to_mp3_chunk(_make_pcm(s)) for s in durations]

    combined = kokoro_engine.combine_mp3_chunks(chunks, "Joanna")

    assert _xing_count(combined) <= 1  # at most one Xing header for whole file
    header = _header_duration(combined)
    real = _real_duration(combined)
    assert abs(header - real) <= 0.01 * real, (header, real)
    # And the single header reflects the SUM, not just the first chunk.
    assert header > sum(durations) * 0.9, (header, sum(durations))


@_requires_tools
def test_combine_mixed_kokoro_and_polly_chunks():
    """Mixed fallback: some chunks are 'Polly' (raw frames, no Xing), some are
    'Kokoro' (Xing). Decoding both to PCM and re-encoding still yields one file
    whose header == real within 1 %."""
    import kokoro_engine

    # Kokoro-style chunk (WAV->MP3, has Xing) and a Polly-style chunk (encoded
    # straight from PCM with no Xing header) — both must decode to PCM cleanly.
    kokoro_chunk = _pcm_to_mp3_chunk(_make_pcm(9.0))
    polly_like = subprocess.run(
        [_FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-i", "pipe:0", "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-b:a", "48k", "-f", "mp3", "pipe:1"],
        input=_make_pcm(7.0), check=True, capture_output=True,
    ).stdout

    combined = kokoro_engine.combine_mp3_chunks([kokoro_chunk, polly_like], "Joanna")
    header = _header_duration(combined)
    real = _real_duration(combined)
    assert abs(header - real) <= 0.01 * real, (header, real)
    assert header > 15.0, header  # ~16 s total


@_requires_tools
def test_single_chunk_returned_unchanged():
    """A single chunk is passed through unchanged (no needless re-encode)."""
    import kokoro_engine

    one = _pcm_to_mp3_chunk(_make_pcm(5.0))
    assert kokoro_engine.combine_mp3_chunks([one], "Joanna") == one


# ── end-to-end through the service's in-process Kokoro path ───────────────────

@_requires_tools
def test_synthesize_4500_chars_single_correct_header(monkeypatch):
    """A 4,500-char request on the in-process Kokoro path (KOKORO_URL unset)
    produces ONE MP3 whose header duration == real within 1 % — the chunks are
    recombined at the PCM level, not byte-concatenated."""
    import importlib
    import types
    from unittest.mock import MagicMock

    # Fake boto3 / botocore so the Polly-only container deps are not needed.
    os.environ["TTS_ENGINE"] = "kokoro"
    os.environ["KOKORO_URL"] = ""  # force in-process path (ffmpeg available here)

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

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(sys.modules, "boto3", fake_boto3)
        mp.setitem(sys.modules, "botocore", fake_botocore)
        mp.setitem(sys.modules, "botocore.exceptions", fake_exc)
        if "polly_tts_service" in sys.modules:
            del sys.modules["polly_tts_service"]
        svc = importlib.import_module("polly_tts_service")
        svc.polly_client = fake_polly_client

        # Stub the Kokoro per-chunk encoder to produce a real MP3 proportional to
        # the chunk's character count (so we exercise the real combine without the
        # model). Each returned chunk is a Xing-headed MP3, exactly like the model
        # path. The combine must still yield ONE correct header.
        import kokoro_engine

        def _fake_synth(chunk_text, voice_id):
            seconds = max(0.5, len(chunk_text) / 300.0)  # ~300 chars/sec of audio
            return _pcm_to_mp3_chunk(_make_pcm(seconds))

        mp.setattr(kokoro_engine, "synthesize_to_mp3", _fake_synth)
        mp.setattr(svc, "kokoro_engine", kokoro_engine)

        text = ("The old mill stood by the river for a hundred years. " * 90)[:4500]
        assert len(text) >= 4500 - 60  # ~4,500 chars -> multiple chunks

        client = svc.app.test_client()
        from unittest.mock import patch as _patch
        with _patch("cost_meter.record_operation", side_effect=lambda **kw: "row"):
            resp = client.post(
                "/synthesize", json={"text": text, "voice_id": "Joanna"}
            )

    assert resp.status_code == 200
    mp3 = resp.data
    assert _xing_count(mp3) <= 1, "combined output must have one header"
    header = _header_duration(mp3)
    real = _real_duration(mp3)
    assert abs(header - real) <= 0.01 * real, (header, real)
    fake_polly_client.synthesize_speech.assert_not_called()  # pure Kokoro


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
