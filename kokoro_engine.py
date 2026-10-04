#!/usr/bin/env python3
"""
[LOCAL-573] Kokoro-82M local TTS engine for English tours.
============================================================
This module is the Kokoro side of the ``TTS_ENGINE`` switch. The polly-tts
service imports it only when ``TTS_ENGINE=kokoro``; with the default
``TTS_ENGINE=polly`` nothing here runs and the service is byte-for-byte today's.

Design points:
  * **Routing only on English voices.** Russian (Tatyana) and every other
    language keep going to Polly. ``should_use_kokoro(voice_id)`` is the single
    predicate the service calls.
  * **Lazy, cached model load.** The Kokoro pipeline (model weights + espeak-ng)
    is loaded once on first use and cached. Importing this module is cheap and
    free of heavy deps, so unit tests can import it and exercise the routing
    logic without Kokoro installed.
  * **Output matches Polly's MP3 shape.** Kokoro renders 24 kHz mono float32.
    We encode to MP3 (mono) at the sample rate the equivalent Polly voice would
    have used — 24000 Hz for the neural English voices (Joanna/Matthew/Amy/
    Brian), 22050 Hz for the standard English voices — using ffmpeg.
  * **Never kills a tour.** Any failure raises ``KokoroUnavailable`` /
    ``KokoroSynthesisError``; the service catches it, logs
    ``[LOCAL-573] kokoro failed — falling back to Polly`` and uses Polly.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave

_log = logging.getLogger(__name__)

# Kokoro's native output sample rate (hexgrad/Kokoro-82M v1.0): 24 kHz mono.
KOKORO_NATIVE_SAMPLE_RATE = 24000

# ── English voice roster ─────────────────────────────────────────────────────
# All Polly en-* voices. Membership = "render with Kokoro under TTS_ENGINE=kokoro".
# Any voice NOT in this set (Tatyana, Lucia, Celine, Marlene, Zhiyu, Seoyeon, …)
# always goes to Polly.
_ENGLISH_FEMALE_VOICES = frozenset([
    "Joanna", "Amy", "Emma", "Ruth", "Ivy", "Kendra", "Kimberly", "Salli",
    "Nicole", "Olivia", "Aria", "Ayanda", "Raveena", "Kajal", "Niamh",
    "Gwyneth", "Hannah", "Danielle",
])
_ENGLISH_MALE_VOICES = frozenset([
    "Matthew", "Brian", "Joey", "Justin", "Kevin", "Stephen", "Gregory",
    "Russell", "Geraint", "Arthur", "Liam",
])
ENGLISH_VOICES = _ENGLISH_FEMALE_VOICES | _ENGLISH_MALE_VOICES

# Polly neural English voices — these default to 24000 Hz MP3; the rest 22050 Hz.
# Must mirror polly_tts_service.NEURAL_VOICES.
_NEURAL_ENGLISH_VOICES = frozenset(["Joanna", "Matthew", "Amy", "Brian"])

# Kokoro voice packs. Female English → af_heart (LOCAL-567 sample H, Michael's
# ear test). Male English → am_michael (Kokoro US male).
KOKORO_FEMALE_VOICE = "af_heart"
KOKORO_MALE_VOICE = "am_michael"


class KokoroUnavailable(RuntimeError):
    """Kokoro is not installed / weights not present / ffmpeg missing."""


class KokoroSynthesisError(RuntimeError):
    """Kokoro was available but synthesis failed."""


def should_use_kokoro(voice_id, engine=None):
    """Return True iff this request should be rendered by Kokoro.

    True only when the switch is on (``engine``/``TTS_ENGINE`` == 'kokoro') AND
    ``voice_id`` is an English Polly voice. Everything else → Polly.
    """
    eng = (engine if engine is not None else os.getenv("TTS_ENGINE", "polly"))
    if (eng or "polly").strip().lower() != "kokoro":
        return False
    return voice_id in ENGLISH_VOICES


def kokoro_voice_for(voice_id):
    """Map a Polly English voice_id to a Kokoro voice pack (gender-matched)."""
    if voice_id in _ENGLISH_MALE_VOICES:
        return KOKORO_MALE_VOICE
    return KOKORO_FEMALE_VOICE


def target_sample_rate_for(voice_id):
    """The MP3 sample rate the equivalent Polly voice would have produced.

    Neural English voices → 24000 Hz (Polly neural default), else 22050 Hz
    (Polly standard default). Reported so Kokoro MP3 matches today's shape.
    """
    return 24000 if voice_id in _NEURAL_ENGLISH_VOICES else 22050


# ── Lazy pipeline singleton ──────────────────────────────────────────────────
_pipeline = None
_pipeline_lock = threading.Lock()
_pipeline_load_failed = None  # cache the import/load error message


def _get_pipeline():
    """Load (once) and return the Kokoro KPipeline. Raises KokoroUnavailable."""
    global _pipeline, _pipeline_load_failed
    if _pipeline is not None:
        return _pipeline
    if _pipeline_load_failed is not None:
        raise KokoroUnavailable(_pipeline_load_failed)
    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            # Imported lazily: keeps module import cheap and test-friendly.
            from kokoro import KPipeline  # type: ignore
        except Exception as e:  # noqa: BLE001 - any import failure means "not installed"
            _pipeline_load_failed = f"kokoro import failed: {e}"
            raise KokoroUnavailable(_pipeline_load_failed) from e
        try:
            # 'a' = American English (lang_code). CPU is used automatically when
            # no CUDA device is present. Weights are expected to be present from
            # build time (see Dockerfile.polly-tts).
            _pipeline = KPipeline(lang_code="a")
        except Exception as e:  # noqa: BLE001
            _pipeline_load_failed = f"kokoro pipeline init failed: {e}"
            raise KokoroUnavailable(_pipeline_load_failed) from e
    return _pipeline


def warmup():
    """Best-effort pre-load of the pipeline (called at service start). Never raises."""
    try:
        _get_pipeline()
        _log.info("[LOCAL-573] Kokoro pipeline warmed up")
        return True
    except Exception as e:  # noqa: BLE001
        _log.warning(f"[LOCAL-573] Kokoro warmup skipped: {e}")
        return False


def _float_to_wav(samples, sample_rate, path):
    """Write a float32 [-1,1] numpy/array of mono samples to a 16-bit PCM WAV."""
    import numpy as np  # local import: only needed on the Kokoro path

    arr = np.asarray(samples, dtype="float32")
    arr = np.clip(arr, -1.0, 1.0)
    pcm16 = (arr * 32767.0).astype("<i2")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())


def _wav_to_mp3(wav_path, mp3_path, sample_rate):
    """Encode mono WAV → MP3 at the target sample rate using ffmpeg.

    Bitrate 48k for 24000 Hz (matches Polly neural MP3), 32k for 22050 Hz
    (matches Polly standard MP3). Mono. Raises KokoroSynthesisError on failure.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    bitrate = "48k" if sample_rate >= 24000 else "32k"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", wav_path,
        "-ac", "1",
        "-ar", str(sample_rate),
        "-b:a", bitrate,
        "-f", "mp3",
        mp3_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise KokoroUnavailable(f"ffmpeg not found: {e}") from e
    except subprocess.CalledProcessError as e:
        raise KokoroSynthesisError(
            f"ffmpeg encode failed: {e.stderr.decode('utf-8', 'ignore')[:300]}"
        ) from e


def synthesize_to_mp3(text, voice_id):
    """Render ``text`` with Kokoro and return MP3 bytes matching Polly's shape.

    Raises KokoroUnavailable if Kokoro/ffmpeg aren't usable, KokoroSynthesisError
    if rendering fails. The caller falls back to Polly on either.
    """
    if not text or not text.strip():
        raise KokoroSynthesisError("empty text")

    import numpy as np  # local import

    pipeline = _get_pipeline()
    k_voice = kokoro_voice_for(voice_id)
    sample_rate = target_sample_rate_for(voice_id)

    # KPipeline yields (graphemes, phonemes, audio) tuples, one per internal
    # chunk. Concatenate the float32 audio at Kokoro's native 24 kHz.
    try:
        segments = []
        for _, _, audio in pipeline(text, voice=k_voice):
            if audio is None:
                continue
            # audio may be a torch tensor or numpy array
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            segments.append(np.asarray(audio, dtype="float32").reshape(-1))
        if not segments:
            raise KokoroSynthesisError("kokoro produced no audio")
        full = np.concatenate(segments)
    except KokoroSynthesisError:
        raise
    except Exception as e:  # noqa: BLE001
        raise KokoroSynthesisError(f"kokoro inference failed: {e}") from e

    tmpdir = tempfile.mkdtemp(prefix="kokoro_")
    try:
        wav_path = os.path.join(tmpdir, "k.wav")
        mp3_path = os.path.join(tmpdir, "k.mp3")
        # Write at native rate; ffmpeg resamples to target on encode.
        _float_to_wav(full, KOKORO_NATIVE_SAMPLE_RATE, wav_path)
        _wav_to_mp3(wav_path, mp3_path, sample_rate)
        with open(mp3_path, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── [LOCAL-575] Single-header multi-chunk combine ────────────────────────────
# Defect: a stop over 2,000 chars is split into chunks by polly_tts_service, and
# each Kokoro chunk is encoded to its own MP3 (ffmpeg writes a Xing/Info header
# describing THAT chunk only). Byte-concatenating those MP3s yields a file whose
# FIRST header claims the first chunk's duration — so a player's timer trusts a
# duration far shorter than the real audio (tour 388: audio_1 header 121 s, real
# 204 s). Polly's raw MP3 frames carry no Xing header, which is why Polly tours
# never showed this.
#
# Fix: when a request renders in chunks, decode every chunk's MP3 back to raw
# PCM, concatenate the PCM, and encode ONE MP3 (one correct Xing header for the
# whole duration). Mixed fallback (some chunks rendered by Polly) is handled the
# same way: Polly's MP3 decodes to PCM just like Kokoro's, so the single output
# header is correct regardless of which engine produced each chunk.
#
# This lives in kokoro_engine (shared) so the in-process fallback path and the
# offline tour-repair tool use the exact same encoder as the host service.

# ffmpeg writes a Xing/Info header for CBR/VBR MP3 it encodes from a container
# input (wav/mp3) but NOT when the input is raw PCM piped as -f s16le and copied
# frame-by-frame. We always go PCM -> MP3 here, so exactly one Xing header is
# emitted for the whole stream.


def _mp3_bitrate_for(sample_rate):
    """Match the per-chunk encoder: 48k for >=24 kHz, 32k otherwise."""
    return "48k" if sample_rate >= 24000 else "32k"


def decode_mp3_to_pcm(mp3_bytes, sample_rate):
    """Decode MP3 bytes to raw signed-16-bit little-endian mono PCM at
    ``sample_rate`` using ffmpeg. Returns the PCM byte string.

    Used to turn already-encoded chunks (Kokoro or Polly) back into PCM so they
    can be concatenated and re-encoded as a single MP3 with one correct header.
    Raises KokoroUnavailable if ffmpeg is missing, KokoroSynthesisError on a
    decode failure.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ac", "1", "-ar", str(sample_rate),
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=mp3_bytes, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise KokoroUnavailable(f"ffmpeg not found: {e}") from e
    except subprocess.CalledProcessError as e:
        raise KokoroSynthesisError(
            f"ffmpeg decode failed: {e.stderr.decode('utf-8', 'ignore')[:300]}"
        ) from e
    return proc.stdout


def encode_pcm_to_mp3(pcm_bytes, sample_rate):
    """Encode raw s16le mono PCM at ``sample_rate`` to a single MP3 (one Xing
    header for the whole stream) using ffmpeg. Returns the MP3 byte string.

    Bitrate mirrors the per-chunk encoder (48k at >=24 kHz, else 32k) so the
    combined file matches today's shape. Raises KokoroUnavailable if ffmpeg is
    missing, KokoroSynthesisError on an encode failure.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    bitrate = _mp3_bitrate_for(sample_rate)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "s16le", "-ac", "1", "-ar", str(sample_rate),
        "-i", "pipe:0",
        "-ac", "1", "-ar", str(sample_rate), "-b:a", bitrate,
        "-f", "mp3", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=pcm_bytes, check=True, capture_output=True)
    except FileNotFoundError as e:
        raise KokoroUnavailable(f"ffmpeg not found: {e}") from e
    except subprocess.CalledProcessError as e:
        raise KokoroSynthesisError(
            f"ffmpeg encode failed: {e.stderr.decode('utf-8', 'ignore')[:300]}"
        ) from e
    return proc.stdout


def combine_mp3_chunks(chunks, voice_id):
    """Combine already-encoded MP3 ``chunks`` into ONE MP3 with a single, correct
    header, by decoding each chunk to PCM, concatenating, and re-encoding once.

    ``chunks`` is a non-empty iterable of MP3 byte strings (each may be a Kokoro
    or a Polly chunk — both decode to PCM identically). ``voice_id`` picks the
    target sample rate (24 kHz neural English, 22050 Hz otherwise), the same
    rate the per-chunk encoder used, so the combine is lossless in shape.

    A single chunk is returned unchanged (nothing to combine, no re-encode) to
    stay byte-for-byte with today when no splitting happened.
    """
    chunk_list = [c for c in chunks if c]
    if not chunk_list:
        raise KokoroSynthesisError("no chunks to combine")
    if len(chunk_list) == 1:
        return chunk_list[0]
    sample_rate = target_sample_rate_for(voice_id)
    pcm_parts = [decode_mp3_to_pcm(c, sample_rate) for c in chunk_list]
    combined_pcm = b"".join(pcm_parts)
    if not combined_pcm:
        raise KokoroSynthesisError("combined PCM is empty")
    return encode_pcm_to_mp3(combined_pcm, sample_rate)
