#!/usr/bin/env python3
"""[LOCAL-768] Measure IN-PROCESS Kokoro render latency via /synthesize.

Not shipped — a local measurement harness for the voice (polly-tts) image built
with Kokoro baked in (Dockerfile.polly-tts-kokoro), run with TTS_ENGINE=kokoro
and KOKORO_URL='' so English renders in-process. Hits the SAME /synthesize
endpoint the orchestrator uses (NOT a separate /render service — D667: no
separate service), so the numbers are what Subscribed on GCloud would see.

Times a ~2,300-char English stop (cold first, then 2 warm) and a 4-stop tour's
texts, writes the first MP3 to disk for a playback / sample-rate check, and
prints a table. English voice Joanna -> Kokoro af_heart, 24 kHz neural.

Usage:  python measure_local768_kokoro.py [BASE_URL]
        BASE_URL defaults to http://localhost:5281 (the -p 5281:5018 mapping).
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5281"
VOICE = "Joanna"  # neural English female -> Kokoro af_heart, 24 kHz

# A ~2,300-char English stop (museum narration register).
_SENT = (
    "The old mill on the river powered this town for over a century, its great "
    "waterwheel turning day and night to grind the grain that fed the valley. "
    "Workers came from every corner of the county, drawn by the promise of steady "
    "wages and the hum of machinery that never seemed to rest. "
)
STOP_2300 = (_SENT * 10)[:2300]

TOUR_4 = [
    (_SENT * 9)[:2100],
    (_SENT * 11)[:2600],
    (_SENT * 8)[:1900],
    (_SENT * 12)[:2800],
]


def render(text, save_path=None):
    """POST to /synthesize; return (seconds, mp3_byte_count). Raises on non-200."""
    body = json.dumps({"text": text, "voice_id": VOICE}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/synthesize", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    dt = time.time() - t0
    if save_path:
        with open(save_path, "wb") as f:
            f.write(data)
    return dt, len(data)


def health():
    with urllib.request.urlopen(f"{BASE}/health", timeout=30) as resp:
        return json.loads(resp.read())


def main():
    print(f"BASE={BASE} VOICE={VOICE}")
    try:
        print(f"/health: {json.dumps(health())}")
    except Exception as e:  # noqa: BLE001
        print(f"/health unreachable: {e}")

    print(f"\n== 2,300-char stop ({len(STOP_2300)} chars): cold, then 2 warm ==")
    labels = ["cold", "warm-1", "warm-2"]
    for i, label in enumerate(labels):
        save = "/tmp/local768_stop.mp3" if i == 0 else None
        dt, nbytes = render(STOP_2300, save)
        print(f"  {label}: {dt:.2f}s  ({nbytes} MP3 bytes)")

    print(f"\n== 4-stop tour ==")
    total = 0.0
    for i, text in enumerate(TOUR_4, 1):
        dt, nbytes = render(text)
        total += dt
        print(f"  stop {i}: {len(text)} chars -> {dt:.2f}s ({nbytes} bytes)")
    print(f"  tour total: {total:.2f}s for {sum(len(t) for t in TOUR_4)} chars")
    print("\nFirst stop MP3 written to /tmp/local768_stop.mp3 "
          "(check with: ffprobe /tmp/local768_stop.mp3)")


if __name__ == "__main__":
    main()
