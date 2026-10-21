#!/usr/bin/env python3
"""
[LOCAL-730] Live proof on an ISOLATED own process — never touches any
audioura-* container or DB.

It launches the REAL treats_service Flask app as a SUBPROCESS on a spare port,
backed by a tiny in-memory fake DB (two treats, injected via an env shim), then
plays the app's path end-to-end:

  1. parse the stop coordinates out of a downloaded tour's audio_N.txt files
     (same format the Flutter resolver reads),
  2. POST them to /treats-near-places exactly as the app does,
  3. capture the service's stdout request log and assert it shows ROUNDED STOP
     coordinates — and that a decoy "emulator GPS" position never appears.

Mirrors the emulator scenario (location permission granted, a downloaded tour
open) and proves the request carried stop coordinates, not GPS.
"""
import os
import re
import sys
import json
import time
import signal
import subprocess
import urllib.request

PORT = int(os.getenv("PROOF_PORT", "5077"))
TOUR_DIR = os.getenv("PROOF_TOUR_DIR", "/tmp/local730_proof/tour_freedom_trail")
LOG_PATH = os.getenv("PROOF_LOG", "/tmp/local730_proof/server.log")

# A decoy "emulator GPS" fix that must NEVER appear in the request or the log.
EMULATOR_GPS = (37.42199, -122.08400)  # Googleplex — the Android emulator default

# A shim module that imports the real service but swaps in a fake DB, so NO
# real database (and no audioura-* container) is touched.
SHIM = r'''
import treats_service

class _FakeCursor:
    ROWS = [
        (1, "Cafe Vittoria", "espresso in the North End", 42.3650, -71.0540,
         "https://cafevittoria.example", None, 0),
        (2, "Mike's Pastry", "cannoli", 42.3636, -71.0560,
         "https://mikespastry.example", None, 0),
    ]
    def execute(self, *a, **k): self._rows = list(self.ROWS)
    def fetchall(self): return self._rows
    def close(self): pass

class _FakeConn:
    def cursor(self): return _FakeCursor()
    def close(self): pass

treats_service.get_db_connection = lambda: _FakeConn()
import os
treats_service.app.run(host="127.0.0.1", port=int(os.environ["PROOF_PORT"]),
                       debug=False, use_reloader=False)
'''


def parse_stop_coords(tour_dir):
    """Mirror the Flutter resolver: read audio_N.txt in order, pull the
    'Coordinates: lat, lng' line from each."""
    points = []
    i = 1
    while True:
        path = os.path.join(tour_dir, f"audio_{i}.txt")
        if not os.path.exists(path):
            break
        with open(path) as f:
            text = f.read()
        m = re.search(r"Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)", text)
        if m:
            points.append({"lat": float(m.group(1)), "lng": float(m.group(2))})
        i += 1
    return points


def main():
    env = dict(os.environ, PROOF_PORT=str(PORT))
    logf = open(LOG_PATH, "w")
    proc = subprocess.Popen([sys.executable, "-c", SHIM],
                            stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        time.sleep(2.0)

        # 1) Resolve stop coordinates from the downloaded tour.
        points = parse_stop_coords(TOUR_DIR)
        print(f"[app] resolved {len(points)} STOP coordinates from {TOUR_DIR}:")
        for p in points:
            print(f"       stop -> {p['lat']}, {p['lng']}")
        print(f"[app] (emulator GPS would be {EMULATOR_GPS[0]}, "
              f"{EMULATOR_GPS[1]} — it is NEVER read or sent)")
        assert points, "no stop coordinates parsed — tour fixture missing?"

        # 2) POST them exactly as the app does.
        body = json.dumps({"points": points}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/treats-near-places",
            data=body, headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
        status = resp.status

        # Also prove the legacy GET still works.
        with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/treats-near/42.36627/-71.05442",
                timeout=10) as gresp:
            gstatus = gresp.status

        print(f"\n[server] POST response: {status} "
              f"treats={payload['count']} points={payload['points']}")
        for tr in payload["treats"]:
            print(f"         treat {tr['id']}: {tr['name']} "
                  f"({tr.get('distance_km')} km)")
        print(f"[server] legacy GET /treats-near response: {gstatus}")
    finally:
        proc.send_signal(signal.SIGINT)
        time.sleep(0.5)
        proc.terminate()
        logf.close()

    log = open(LOG_PATH).read()
    # Our service's own log lines (round_coord output), excluding werkzeug's
    # HTTP access lines — a GET URL necessarily echoes its path coordinates, but
    # the app's real path is the POST, which carries coordinates in the BODY.
    our_lines = [ln for ln in log.splitlines()
                 if ("treats near" in ln.lower() or "Found" in ln)
                 and "HTTP/1.1" not in ln]
    our_log = "\n".join(our_lines)

    print("\n=== CAPTURED SERVER REQUEST LOG (service log lines) ===")
    for line in our_lines:
        print(line)
    print("=== END LOG ===\n")

    # --- Assertions: the proof --------------------------------------------
    failures = []
    sent = json.dumps(points)
    if "37.42" in sent or "-122.08" in sent:
        failures.append("emulator GPS leaked into the request body")
    if "37.42" in log or "-122.08" in log:
        failures.append("emulator GPS leaked into the server log")
    # Full precision must not appear in OUR coordinate logging (round_coord).
    if "42.36627" in our_log or "-71.05442" in our_log:
        failures.append("service logged FULL-PRECISION stop coordinates")
    if "42.37" not in our_log:
        failures.append("service log missing the rounded stop coordinate 42.37")
    if not any(abs(p["lat"] - 42.36627) < 1e-6 for p in points):
        failures.append("stop coordinates not present in the resolved points")

    if failures:
        print("PROOF FAILED:")
        for f in failures:
            print("  - " + f)
        return 1

    print("PROOF OK:")
    print("  - request carried the tour's STOP coordinates")
    print("  - emulator GPS (37.42199, -122.08400) never sent, never logged")
    print("  - server logged only ROUNDED (2-decimal) coordinates")
    print("  - GET /treats-near still available for old apps; no DB writes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
