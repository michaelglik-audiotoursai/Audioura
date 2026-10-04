#!/usr/bin/env python3
"""
[LOCAL-573] Shared caller-side timeout for POST /synthesize.
============================================================
Every service that calls the polly-tts ``/synthesize`` endpoint must size its
HTTP read timeout to the text length. Under ``TTS_ENGINE=kokoro`` the polly-tts
service renders English stops on the host Kokoro model (~16.5 s for a 2,300-char
stop, ~8.9x real time on this Mac); a flat ``timeout=30`` would abort a normal
long stop mid-render and lose its audio. Polly (short-text / non-English) is far
faster, so the same formula is safe there too — it only ever grants *more* time.

Formula (decided by LEAD):

    timeout = 30 + 0.05 * len(text)   seconds, capped at 180

  * 30 s floor covers model/connection warmup + short stops.
  * 0.05 s per character ≈ 115 s for a 2,300-char stop — comfortably above the
    ~16.5 s native render, leaving headroom for a cold pipeline or a queued
    render behind the single-render lock.
  * 180 s cap bounds the worst case so a wedged render cannot hang a caller
    indefinitely; past the cap the caller gives up and (per each caller) falls
    back to Polly / a placeholder.

This is the single source of truth — callers must not hardcode a bare number.
"""

TTS_TIMEOUT_BASE_SECONDS = 30.0
TTS_TIMEOUT_PER_CHAR_SECONDS = 0.05
TTS_TIMEOUT_MAX_SECONDS = 180.0


def synthesize_timeout(text):
    """Return the /synthesize HTTP timeout (seconds) for ``text``.

    ``timeout = 30 + 0.05 * len(text)``, capped at 180. Accepts a string (its
    length is used) or an int/float character count. ``None`` / empty → the base
    30 s. Never returns less than the base or more than the cap.
    """
    if text is None:
        n = 0
    elif isinstance(text, (int, float)):
        n = int(text)
    else:
        n = len(text)
    if n < 0:
        n = 0
    return min(
        TTS_TIMEOUT_MAX_SECONDS,
        TTS_TIMEOUT_BASE_SECONDS + TTS_TIMEOUT_PER_CHAR_SECONDS * n,
    )
