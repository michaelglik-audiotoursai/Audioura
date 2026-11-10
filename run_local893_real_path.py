#!/usr/bin/env python3
"""run_local893_real_path.py — LOCAL-893 parity harness through the REAL orchestrator path.

The earlier parity harnesses called itinerary_import.preview_stops in-process and so
never saw the D762 /preview-stops HTTP call time out. This one does what the cloud does:

    POST /generate-complete-tour {location, tour_type:"walking", total_stops:10,
                                  user_id, stops:[10 RAW strings], is_test:true}

to OUR OWN orchestrator + generator containers (compose project -p local893, ports
25002 / 25000 / DB 55993; NEVER the shared audioura-* containers), then asserts on the
orchestrator and generator LOGS and the stored tour.

    docker compose -p local893 -f docker-compose.local893-proof.yml up -d --build
    python3 run_local893_real_path.py --selfcheck          # offline log-assert check
    python3 run_local893_real_path.py --profile            # /preview-stops timing only
    TASK_BUDGET_ID=LOCAL-893 TASK_BUDGET_USD=0.50 python3 run_local893_real_path.py --run

--run loads the cloud cache snapshot into the proof DB, profiles /preview-stops, does
ONE full tour, and records the metered spend into the cumulative ledger. Artifacts go
to submission_artifacts/local893/; logs and meter files stay in ./_local893_meterlogs/.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "tests"))
sys.path.insert(0, os.path.join(_HERE, "_meter"))

TASK = "LOCAL-893"
PROJECT = "local893"
COMPOSE = "docker-compose.local893-proof.yml"
ORCH = os.environ.get("LOCAL893_ORCH", "http://localhost:25002")
GEN = os.environ.get("LOCAL893_GEN", "http://localhost:25000")
DB_URL = os.environ.get("LOCAL893_DB_URL",
                        "postgresql://admin:password123@localhost:55993/audiotours")
METER_DIR = os.path.join(_HERE, "_local893_meterlogs")
ART_DIR = os.path.join(_HERE, "submission_artifacts", "local893")
SNAP_DIR = os.path.expanduser(
    os.environ.get("CLOUD_CACHE_SNAPSHOT_DIR", "~/Audioura/cloud_cache_snapshot"))

CITY = "Ho Chi Minh City"
LOCATION = "Ho Chi Minh City, Vietnam"
# Michael's RAW strings exactly as the cloud request carried them (wave 43).
RAW_STOPS = [
    "Cathedral", "Post Office", "Book Street", "Independence Palace",
    "War Remnants Museum", "Opera House_Đồng Khởi", "City Hall & Nguyễn Huệ",
    "Café Apartments 42", "Bạch Đằng Pier (tour-bus + waterbus)", "Thi Bar",
]
EXPECT_TITLES = ["Cathedral", "Post Office", "Book Street", "Independence Palace",
                 "War Remnants Museum", "Opera House", "City Hall",
                 "Café Apartments 42", "Bạch Đằng Pier", "Thi Bar"]
OPERA_PIN = (10.776390, 106.702780)
PREVIEW_TARGET_S = 8.0


def haversine_m(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ── log assertions (pure functions, unit-testable) ───────────────────────────
def assess_orch_log(text):
    """Return [(label, ok, detail)] for the orchestrator log of the raw-string request."""
    out = []
    m = re.search(r"\[D762\] user-stop pins resolved (\d+)/(\d+)", text)
    out.append(("D762 log shows `pins resolved 10/10`",
                bool(m) and m.group(1) == "10" and m.group(2) == "10",
                m.group(0) if m else "no 'pins resolved' line"))
    bad = [l for l in text.splitlines()
           if "PREVIEW FAILED" in l or "pin resolve error" in l
           or "pin resolve skipped" in l]
    out.append(("no preview failure / fallback in the orchestrator log", not bad,
                bad[:2] or "none"))
    t = re.search(r"\[D762\] /preview-stops OK in ([\d.]+)s", text)
    out.append(("orchestrator's own /preview-stops call finished", bool(t),
                f"{t.group(1)}s" if t else "no timing line"))
    return out


def assess_gen_log(text):
    out = []
    name_only = [l for l in text.splitlines() if "via name_only" in l]
    out.append(("no `name_only` fallback in the generator log", not name_only,
                name_only[:2] or "none"))
    raw_titles = [l for l in text.splitlines()
                  if re.search(r"user stop resolved '[^']*(_Đồng|& Nguy|\(tour-bus)", l)]
    out.append(("no raw title reached the generator", not raw_titles, raw_titles[:2] or "none"))
    out.append(("[LOCAL-883] grounding gate ran on 10 stops",
                bool(re.search(r"\[LOCAL-883\] grounding gate: 10 stop", text)), ""))
    out.append(("[LOCAL-889] coverage total logged",
                "[LOCAL-889] coverage total" in text, ""))
    return out


def parse_stops_with_coords(text):
    """[(n, title, (lat, lng) | None, body)] from the delivered tour text."""
    parts = re.split(r"(?mi)^Stop\s+(\d+):\s*(.+)$", text or "")
    res = []
    for i in range(1, len(parts) - 2, 3):
        body = parts[i + 2]
        m = re.search(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", body)
        res.append((int(parts[i]), parts[i + 1].strip(),
                    (float(m.group(1)), float(m.group(2))) if m else None, body))
    return res


def assess_tour(text, evidence_chars=None):
    """Titles / Opera pin / Café coords + the wave-43 checklist (harness criteria)."""
    import run_cloud_parity_proof as base
    stops = parse_stops_with_coords(text)
    out = []
    titles = [s[1] for s in stops]
    low_titles = [t.lower() for t in titles]
    ok_titles = len(titles) == 10 and all(
        e.lower() in lt for e, lt in zip(EXPECT_TITLES, low_titles)) and not any(
        any(x in t for x in ("_", "&", "(", ")")) for t in titles)
    out.append(("clean titles (no `_street`, `& street`, `(…)`)", ok_titles, titles))
    op = next((s for s in stops if "opera" in s[1].lower()), None)
    d = haversine_m(op[2], OPERA_PIN) if op and op[2] else None
    out.append(("Opera pin within 50 m of 10.776390,106.702780",
                d is not None and d <= 50, f"{d:.0f} m" if d is not None else "no coordinates"))
    cafe = next((s for s in stops if "caf" in s[1].lower()), None)
    out.append(("Café Coordinates present", bool(cafe and cafe[2]),
                cafe[2] if cafe else "no Café stop"))
    for label, ok in base._criteria(text, lambda *a, **k: None):
        out.append((f"wave-43 checklist: {label}", ok, ""))
    for label, ok, detail in base.evaluate_888(text, evidence_chars):
        out.append((f"888: {label}", ok, detail))
    return out


def report(rows, title):
    print(f"\n=== {title} ===")
    ok = True
    for label, passed, detail in rows:
        ok &= bool(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}"
              + (f"  — {str(detail)[:200]}" if detail not in ("", None) else ""))
    return ok


# ── plumbing ─────────────────────────────────────────────────────────────────
def _post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _logs(service, since=None):
    cmd = ["docker", "compose", "-p", PROJECT, "-f", os.path.join(_HERE, COMPOSE),
           "logs", "--no-color", "--no-log-prefix"]
    if since:
        cmd += ["--since", since]
    cmd.append(service)
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout


def _meter_total():
    import meter_guard
    return meter_guard.meter_rows(os.path.join(METER_DIR, "paid_api_calls.jsonl"))[1]


def profile_preview():
    """POST the generator's /preview-stops on the 10 raw strings; return (secs, json)."""
    t0 = time.time()
    r = _post(f"{GEN}/preview-stops", {"text": "\n".join(RAW_STOPS), "city": CITY}, 120)
    return time.time() - t0, r


def cmd_selfcheck():
    ok_log = ("[D762] /preview-stops OK in 5.2s (try 1)\n"
              "[D762] user-stop pins resolved 10/10 (city Ho Chi Minh City)\n")
    bad_log = ("[D762] user-stop pin resolve error: Read timed out (read timeout=20)\n"
               "ERROR [D762] PREVIEW FAILED — generating from raw strings (x)\n")
    assert all(p for _, p, _ in assess_orch_log(ok_log))
    assert not any(p for _, p, _ in assess_orch_log(bad_log))
    assert not assess_gen_log("[LOCAL-852] user stop resolved 'Thi Bar' (no coord — geocode "
                              "by name) via name_only\n")[0][1]
    assert haversine_m(OPERA_PIN, OPERA_PIN) == 0
    text = ("Stop 6: Opera House\nCoordinates: 10.776400, 106.702800\nbody\n"
            "Stop 7: City Hall\nCoordinates: 10.77647, 106.70097\nbody\n")
    st = parse_stops_with_coords(text)
    assert len(st) == 2 and st[0][2] == (10.7764, 106.7028)
    print("selfcheck OK")
    return 0


def cmd_profile():
    import task_budget
    if os.environ.get("TASK_BUDGET_ID") != TASK:
        sys.exit(f"refusing: launch with TASK_BUDGET_ID={TASK}")
    os.makedirs(METER_DIR, exist_ok=True)
    m0 = _meter_total()
    try:
        secs, r = _profile_and_print()
    finally:
        usd = max(0.0, _meter_total() - m0)
        task_budget.record_run(TASK, round(usd, 6), note="/preview-stops profile only")
        print(f"[LOCAL-893] profile metered ${usd:.4f}; ledger now "
              f"${task_budget.spent_so_far(TASK)}")
    return 0 if secs < PREVIEW_TARGET_S else 1


def _profile_and_print():
    secs, r = profile_preview()
    print(f"/preview-stops: {secs:.2f}s, {r.get('count')} stops, "
          f"{r.get('unresolved_count')} unresolved")
    for s in r.get("stops", []):
        print(f"  {s['name']!r:28} {s.get('source')} -> {s.get('matched_name')!r}")
    print(f"  target < {PREVIEW_TARGET_S}s: {'PASS' if secs < PREVIEW_TARGET_S else 'FAIL'}")
    return secs, r


def cmd_run():
    import task_budget
    if os.environ.get("TASK_BUDGET_ID") != TASK:
        sys.exit(f"refusing live run: launch with TASK_BUDGET_ID={TASK}")
    if os.environ.get("AUDIOURA_TASK_BUDGET_DIR"):
        sys.exit("refusing: AUDIOURA_TASK_BUDGET_DIR must be unset (default ledger dir only)")
    cap = float(os.environ.get("TASK_BUDGET_USD", "0.50"))
    spent = task_budget.spent_so_far(TASK)
    print(f"[LOCAL-893] ledger spent_so_far={spent} of cap ${cap:.2f}")
    if spent + 0.20 > cap:
        sys.exit("refusing: not enough ledger headroom for one more run (unproven, hand to LEAD)")
    os.makedirs(ART_DIR, exist_ok=True)
    os.makedirs(METER_DIR, exist_ok=True)
    import run_cloud_parity_proof as base
    print("\n=== LOAD CLOUD CACHE SNAPSHOT into the proof DB (:55993) ===")
    base.load_snapshot(SNAP_DIR, DB_URL, log=print)

    rows = []
    meter0 = _meter_total()      # profile + tour both count toward this run
    gen_log, audit_ran, ok = "", False, False
    try:
        # 1. profile /preview-stops on the 10 raw strings
        secs, pv = profile_preview()
        print(f"\n/preview-stops direct: {secs:.2f}s ({pv.get('count')} stops, "
              f"{pv.get('unresolved_count')} unresolved)")
        rows.append((f"/preview-stops under {PREVIEW_TARGET_S:.0f}s for 10 stops",
                     secs < PREVIEW_TARGET_S, f"{secs:.2f}s"))
        gen_pv_log = _logs("tour-generator")
        pv_timing = re.findall(r"\[LOCAL-893\] preview timing:.*", gen_pv_log)
        for l in pv_timing[-1:]:
            print("  ", l)
        # 2. ONE full tour through the real orchestrator path (the profile above spends
        #    pennies of Places/Serper; it is part of this run's metered total)
        marker = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        t0 = time.time()
        job = _post(f"{ORCH}/generate-complete-tour",
                    {"location": LOCATION, "tour_type": "walking", "total_stops": 10,
                     "user_id": "local821-tester", "stops": RAW_STOPS, "is_test": True}, 120)
        jid = job.get("job_id")
        print(f"\njob {jid} submitted: {json.dumps(job)[:200]}")
        status = None
        while time.time() - t0 < 1800:
            time.sleep(20)
            try:
                st = json.loads(urllib.request.urlopen(f"{ORCH}/status/{jid}", timeout=30).read())
            except Exception as e:
                print("  status err", str(e)[:80])
                continue
            status = st.get("status")
            print(f"  [{int(time.time() - t0):4d}s] {status} {st.get('progress', '')[:80]}")
            if status in ("completed", "failed", "error"):
                break
        secs_total = time.time() - t0
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT tour_content FROM audio_tours WHERE is_test ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        text = (row[0] if row else "") or ""
        open(os.path.join(ART_DIR, "saigon_real_path.txt"), "w", encoding="utf-8").write(text)
        orch_log = _logs("tour-orchestrator")
        gen_log = _logs("tour-generator")
        open(os.path.join(METER_DIR, "orch.log"), "w", encoding="utf-8").write(orch_log)
        open(os.path.join(METER_DIR, "gen.log"), "w", encoding="utf-8").write(gen_log)
        rows.append(("job completed", status == "completed", f"{status} in {secs_total:.0f}s"))
        ok = report(rows, "PREVIEW + JOB")
        ok &= report(assess_orch_log(orch_log), "ORCHESTRATOR LOG (D762)")
        ok &= report(assess_gen_log(gen_log), "GENERATOR LOG")
        ev_chars = None
        ev_path = os.path.join(METER_DIR, "evidence_bundle.json")
        ev = {}
        if os.path.exists(ev_path):
            ev = json.load(open(ev_path, encoding="utf-8"))
            ev_chars = {k: len((v or "").strip()) for k, v in ev.items()}
        ok &= report(assess_tour(text, ev_chars), "TOUR (titles / pins / wave-43 checklist)")
        # 3. independent audit on the same evidence
        audit_ran = False
        try:
            import run_cloud_parity_proof_884 as h884
            audit, audit_ok = h884.independent_audit(text, ev)
            audit_ran = True
            json.dump(audit, open(os.path.join(ART_DIR, "saigon_real_path_audit.json"), "w",
                                  encoding="utf-8"), ensure_ascii=False, indent=2)
            uns = audit.get("unsupported")
            n = len(uns) if isinstance(uns, list) else None
            print(f"\n  audit unsupported = {n}")
            ok &= bool(audit_ok)
        except Exception as e:
            print(f"  audit failed to run: {type(e).__name__}: {e}")
            ok = False
    finally:
        # 4. meter -> cumulative ledger (always)
        import meter_guard
        usd = max(0.0, _meter_total() - meter0)
        rows_n = meter_guard.count_rows(os.path.join(METER_DIR, "paid_api_calls.jsonl"))
        verdict = meter_guard.check_meter(rows_n, usd, gen_log, audit_ran)
        rec = verdict["record_usd"]
        task_budget.record_run(TASK, rec, note="real orchestrator path, 1 full tour"
                               + ("" if verdict["ok"] else " (ESTIMATE: meter undercount)"))
        print(f"\n[LOCAL-893] {verdict['message']}")
        print(f"[LOCAL-893] run metered ${rec:.4f}; ledger now "
              f"${task_budget.spent_so_far(TASK)} of ${cap:.2f}")
    print(f"\n=== {'ALL PASS' if ok else 'SOME FAILED (report as-is, do not re-run)'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--profile", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        sys.exit(cmd_selfcheck())
    if a.profile:
        sys.exit(cmd_profile())
    if a.run:
        sys.exit(cmd_run())
    ap.print_help()
