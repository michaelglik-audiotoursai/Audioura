#!/usr/bin/env python3
"""GCS-KS1 — red -> green evidence for the user-stops kill switch, by effect.

Runs the REAL orchestrator and generator Flask apps in-process against a Flask
test client. Every paid call (OpenAI) and every external dependency (DB, quota,
the downstream generator HTTP call) is stubbed, so this spends nothing and needs
no network — but the code path that decides whether user-chosen stops survive is
the real one.

The decisive observable is the ``stops`` value that actually reaches generation:

  * flag unset  -> generation receives NO stops. The tour is built the normal way
                   (its stops are NOT the named ones), and an ignore log line is
                   emitted recording the field was present, with its count.
  * flag = true -> generation receives EXACTLY the named stops (today's behaviour).

Run:  python tests/run_gcs_ks1_killswitch_evidence.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAMED_STOPS = ["Bell Tower", "Rose Window", "Crypt"]

# What an automatic (no user stops) selection would look like — deliberately
# DIFFERENT names, so "not the named ones" is visible at a glance.
AUTO_STOPS = ["Auto Stop 1", "Auto Stop 2", "Auto Stop 3"]


def _banner(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def drive_orchestrator(flag_value):
    """POST /generate-complete-tour and capture the stops handed to generation.

    Returns (captured_stops, logs) where captured_stops is what the background
    generation thread was given — i.e. what will actually be generated.
    """
    # Set the flag BEFORE importing, though the module reads it fresh per request.
    if flag_value is None:
        os.environ.pop("USER_STOPS_ENABLED", None)
    else:
        os.environ["USER_STOPS_ENABLED"] = flag_value

    import importlib
    import tour_orchestrator_service as orch
    importlib.reload(orch)

    captured = {"stops": "<<never called>>"}
    logs = []

    # Capture the module's print() output (that is where the ignore line goes).
    import builtins
    real_print = builtins.print

    def _capturing_print(*args, **kwargs):
        line = " ".join(str(a) for a in args)
        logs.append(line)
        real_print(*args, **kwargs)

    # --- stubs: no DB, no quota service, no real generation thread ---
    orch.check_tour_quota = lambda uid, stops=10: {
        "allowed": True, "clamped_stops": stops, "used": 0, "remaining": 100,
    }
    # entitlements is imported lazily inside the handler; patch there too.
    import entitlements
    entitlements.check_tour_quota = orch.check_tour_quota

    orch.track_user_tour = lambda *a, **k: None
    orch.log_job_update = lambda *a, **k: None

    # Skip the psycopg2 usage-recording block by making psycopg2.connect raise —
    # the handler already tolerates that (it logs and continues).
    try:
        import psycopg2
        psycopg2.connect = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stubbed: no DB"))
    except Exception:
        pass

    # Capture what the generation thread is handed instead of running it.
    def _fake_thread_target(job_id, location, tour_type, total_stops,
                            user_id=None, request_string=None, language='en',
                            persona=None, is_test=None, stops=None):
        captured["stops"] = stops

    orch.orchestrate_tour_async = _fake_thread_target

    app = orch.app
    app.testing = True
    client = app.test_client()

    payload = {
        "location": "Old North Church, Boston",
        "tour_type": "",
        "user_id": "gcs_ks1_tester",
        "request_string": "a tour of the church",
        "user_stops": NAMED_STOPS,   # the field the mobile app actually sends
    }

    builtins.print = _capturing_print
    try:
        resp = client.post("/generate-complete-tour",
                           data=json.dumps(payload),
                           content_type="application/json")
    finally:
        builtins.print = real_print

    return resp, captured["stops"], logs


def main():
    _banner("REQUEST A — flag UNSET (default OFF): user_stops must be IGNORED")
    respA, stopsA, logsA = drive_orchestrator(None)
    print(f"\nHTTP {respA.status_code}: {respA.get_data(as_text=True)[:200]}")
    print(f"\nStops handed to generation: {stopsA!r}")
    ignore_lines = [l for l in logsA if "USER_STOPS_DISABLED" in l]
    print("Decisive log line(s):")
    for l in ignore_lines:
        print(f"   {l}")

    a_ok = (stopsA is None) and bool(ignore_lines)
    print(f"\n[A] stops is None (generated the normal way): {stopsA is None}")
    print(f"[A] ignore log line recorded with count: {bool(ignore_lines)}")

    _banner("REQUEST B — USER_STOPS_ENABLED=true: named stops must be HONOURED")
    respB, stopsB, logsB = drive_orchestrator("true")
    print(f"\nHTTP {respB.status_code}: {respB.get_data(as_text=True)[:200]}")
    print(f"\nStops handed to generation: {stopsB!r}")
    b_ok = (stopsB == NAMED_STOPS)
    print(f"\n[B] stops == the named stops: {b_ok}")
    no_ignore_when_on = not any("USER_STOPS_DISABLED" in l for l in logsB)
    print(f"[B] no ignore line when ON: {no_ignore_when_on}")

    _banner("RESULT")
    ok = a_ok and b_ok and no_ignore_when_on
    print(f"OFF ignores + logs : {a_ok}")
    print(f"ON honours + quiet : {b_ok and no_ignore_when_on}")
    print(f"\n{'PASS' if ok else 'FAIL'} — kill switch governs user-chosen stops by effect.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
