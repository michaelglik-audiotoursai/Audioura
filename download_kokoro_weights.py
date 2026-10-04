#!/usr/bin/env python3
"""
[LOCAL-573] Build-time Kokoro weight warm-up.
=============================================
Run once during `docker build` so the Kokoro-82M weights and the English voice
packs (af_heart female, am_michael male) are downloaded into the image layer
instead of on the first live request. A tiny synthesis forces every lazy
download (model snapshot + both voice tensors + the espeak/misaki data) to
happen now.

If this fails during build the build fails loudly — better than shipping an
image that would silently fall back to Polly on every English request.
"""

import sys


def main():
    from kokoro import KPipeline

    # 'a' = American English.
    pipeline = KPipeline(lang_code="a")

    # Force the download + first inference for BOTH voices we route to.
    for voice in ("af_heart", "am_michael"):
        got_audio = False
        for _, _, audio in pipeline("Audioura build warm up.", voice=voice):
            if audio is not None:
                got_audio = True
        if not got_audio:
            print(f"[LOCAL-573] WARN: no audio produced for warm-up voice {voice}")
    print("[LOCAL-573] Kokoro weights + voice packs baked into image.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"[LOCAL-573] FATAL: Kokoro weight bake failed: {e}", file=sys.stderr)
        sys.exit(1)
