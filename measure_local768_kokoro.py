#!/usr/bin/env python3
"""[LOCAL-768] Measure Kokoro container render latency via /render.

Not shipped — a local measurement harness. Times a ~2,300-char English stop
(3 runs: the first is warm since the server warms at start, but we still report
run-by-run) and a 4-stop tour's texts, and writes the first MP3 to disk for a
playback/sample-rate check. Prints a table.
"""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5281"
VOICE = "Joanna"  # neural English female -> af_heart, 24 kHz

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
    body = json.dumps({"text": text, "voice": VOICE}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/render", data=body,
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


def main():
    print(f"BASE={BASE} VOICE={VOICE}")
    print(f"\n== 2,300-char stop ({len(STOP_2300)} chars), 3 runs ==")
    for i in range(1, 4):
        save = "/tmp/local768_stop.mp3" if i == 1 else None
        dt, nbytes = render(STOP_2300, save)
        print(f"  run {i}: {dt:.2f}s  ({nbytes} MP3 bytes)")

    print(f"\n== 4-stop tour ==")
    total = 0.0
    for i, text in enumerate(TOUR_4, 1):
        dt, nbytes = render(text)
        total += dt
        print(f"  stop {i}: {len(text)} chars -> {dt:.2f}s ({nbytes} bytes)")
    print(f"  tour total: {total:.2f}s for {sum(len(t) for t in TOUR_4)} chars")


if __name__ == "__main__":
    main()
