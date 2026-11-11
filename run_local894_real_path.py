#!/usr/bin/env python3
"""run_local894_real_path.py -- LOCAL-894 live proof through the REAL orchestrator path.

    POST /generate-complete-tour {location: <the DESCRIPTION>, tour_type: "driving",
                                  stops: [8 strings], is_test: true}

to OUR OWN stack (compose project -p local894; ports 26002 / 26000 / DB 55994; NEVER the
shared audioura-* containers).

    docker compose -p local894 -f docker-compose.local894-proof.yml up -d --build
    python3 run_local894_real_path.py --selfcheck
    TASK_BUDGET_ID=LOCAL-894 TASK_BUDGET_USD=0.50 python3 run_local894_real_path.py --run

ONE full tour only. Artifacts -> submission_artifacts/local894/ (tour text + evidence
JSON + report). Logs and meter files stay in ./_local894_meterlogs/ (never committed).
"""
import argparse
import json
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

TASK = "LOCAL-894"
PROJECT = "local894"
COMPOSE = "docker-compose.local894-proof.yml"
ORCH = os.environ.get("LOCAL894_ORCH", "http://localhost:26002")
DB_URL = os.environ.get("LOCAL894_DB_URL",
                        "postgresql://admin:password123@localhost:55994/audiotours")
METER_DIR = os.path.join(_HERE, "_local894_meterlogs")
ART_DIR = os.path.join(_HERE, "submission_artifacts", "local894")

sys.path.insert(0, os.path.join(_HERE, "tests"))
from test_local894_user_list_integrity import REQUEST, STOPS, EXPECTED_TITLES  # noqa: E402

TOPICS_OF_INTEREST = None  # derived from the request by user_list_integrity


def parse_stops(text):
    """[(n, title, coords|None, body)] from the delivered tour."""
    parts = re.split(r"(?mi)^Stop\s+(\d+):\s*(.+)$", text or "")
    res = []
    for i in range(1, len(parts) - 2, 3):
        body = parts[i + 2]
        m = re.search(r"(?mi)^Coordinates:\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", body)
        res.append((int(parts[i]), parts[i + 1].strip(),
                    (float(m.group(1)), float(m.group(2))) if m else None, body))
    return res


def content_sentences(body):
    prose = [l for l in body.splitlines()
             if l.strip() and not re.match(r"(?i)^(coordinates|type/specialty|directions|"
                                           r"orientation|address|hours):", l.strip())]
    return [s for s in re.split(r"(?<=[.!?])\s+", " ".join(prose)) if len(s.split()) >= 3]


def assess(text, orch_log, gen_log):
    import user_list_integrity as uli
    stops = parse_stops(text)
    titles = [s[1] for s in stops]
    rows = []
    rows.append(("8 stops, in the user's order, with the user's titles (qualifiers stripped)",
                 titles == EXPECTED_TITLES, titles))
    rows.append(("no ghost stop / no 'could not be confirmed' announcement",
                 "could not be confirmed" not in (text or "").lower()
                 and len(titles) == 8, ""))
    m = re.search(r"\[LOCAL-894\] location is a description .*?location='([^']+)' "
                  r"scope='([^']+)'", gen_log or "")
    rows.append(("location/scope derived from the description (Mui Ne/Ham Tien; Binh Thuan region)",
                 bool(m) and ("Mui Ne" in m.group(1) or "Ham Tien" in m.group(1))
                 and "Binh Thuan" in m.group(2), m.groups() if m else "no line"))
    low = (text or "").lower()
    rows.append(("driving register: no street/pavement/look-around template",
                 not re.search(r"look around you at the street|the pavement", low), ""))
    return rows, titles


def report(rows, title):
    print(f"\n=== {title} ===")
    ok = True
    for label, passed, detail in rows:
        ok &= bool(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}"
              + (f"  -- {str(detail)[:240]}" if detail not in ("", None) else ""))
    return ok


def _post(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _logs(service):
    cmd = ["docker", "compose", "-p", PROJECT, "-f", os.path.join(_HERE, COMPOSE),
           "logs", "--no-color", "--no-log-prefix", service]
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout


def _meter_total():
    import meter_guard
    return meter_guard.meter_rows(os.path.join(METER_DIR, "paid_api_calls.jsonl"))[1]


def cmd_selfcheck():
    t = ("Stop 1: " + EXPECTED_TITLES[0] + "\nCoordinates: 10.9, 108.2\nOne two three. Four five six.\n")
    st = parse_stops(t)
    assert st[0][1] == EXPECTED_TITLES[0] and st[0][2] == (10.9, 108.2)
    assert len(content_sentences(st[0][3])) == 2
    print("selfcheck OK")
    return 0


def cmd_run():
    import task_budget
    if os.environ.get("TASK_BUDGET_ID") != TASK:
        sys.exit(f"refusing live run: launch with TASK_BUDGET_ID={TASK}")
    if os.environ.get("AUDIOURA_TASK_BUDGET_DIR"):
        sys.exit("refusing: AUDIOURA_TASK_BUDGET_DIR must be unset (default ledger dir only)")
    cap = float(os.environ.get("TASK_BUDGET_USD", "0.50"))
    spent = task_budget.spent_so_far(TASK)
    print(f"[LOCAL-894] ledger spent_so_far={spent} of cap ${cap:.2f}")
    if spent + 0.20 > cap:
        sys.exit("refusing: not enough ledger headroom for one more run (unproven, hand to LEAD)")
    os.makedirs(ART_DIR, exist_ok=True)
    os.makedirs(METER_DIR, exist_ok=True)
    meter0 = _meter_total()
    gen_log, audit_ran, ok = "", False, False
    try:
        t0 = time.time()
        job = _post(f"{ORCH}/generate-complete-tour",
                    {"location": REQUEST, "tour_type": "driving", "total_stops": 8,
                     "user_id": "local821-tester", "stops": STOPS, "is_test": True}, 120)
        jid = job.get("job_id")
        print(f"job {jid} submitted: {json.dumps(job)[:200]}")
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
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT tour_name, tour_content FROM audio_tours WHERE is_test "
                    "ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        tour_name, text = (row[0], row[1] or "") if row else ("", "")
        open(os.path.join(ART_DIR, "tour.txt"), "w", encoding="utf-8").write(text)
        orch_log = _logs("tour-orchestrator")
        gen_log = _logs("tour-generator")
        open(os.path.join(METER_DIR, "orch.log"), "w", encoding="utf-8").write(orch_log)
        open(os.path.join(METER_DIR, "gen.log"), "w", encoding="utf-8").write(gen_log)

        rows, titles = assess(text, orch_log, gen_log)
        rows.insert(0, ("job completed", status == "completed", status))
        rows.append(("title <= 60 chars, no sentence fragment",
                     bool(tour_name) and len(tour_name) <= 60 and "." not in tour_name,
                     f"{tour_name!r} ({len(tour_name)})"))
        ok = report(rows, "LOCAL-894 CHECKS")

        # ---- the report the task asks for ----
        pins = re.findall(r"\[D762\] user-stop pins resolved (\d+)/(\d+)[^\n]*", orch_log)
        stops = parse_stops(text)
        print("\n--- REPORT ---")
        print("stop titles in order:")
        for n, t, c, b in stops:
            print(f"  {n}. {t}   pin={c}   sentences={len(content_sentences(b))}")
        print("pins (orchestrator log):", pins[-1] if pins else "no line",
              "| stops with Coordinates in the delivered text:",
              f"{sum(1 for s in stops if s[2])}/{len(stops)}")
        print("title:", repr(tour_name))
        for l in re.findall(r"\[LOCAL-894\] location is a description[^\n]*", gen_log)[:1]:
            print("location/scope:", l.strip()[:400])
        for l in re.findall(r"\[LOCAL-474\] tour_type=[^\n]*", gen_log)[:1]:
            print("category:", l.strip())
        for l in re.findall(r"Detected tour category[^\n]*", gen_log)[:1]:
            print("           ", l.strip())
        print("topic support (evidence found vs requested):")
        for l in re.findall(r"\[LOCAL-894\] Stop \d+ [^\n]*topic support[^\n]*", gen_log):
            print("  ", l.strip()[:400])
        ev_path = os.path.join(METER_DIR, "evidence_bundle.json")
        ev = {}
        if os.path.exists(ev_path):
            ev = json.load(open(ev_path, encoding="utf-8"))
            json.dump(ev, open(os.path.join(ART_DIR, "evidence_bundle.json"), "w",
                               encoding="utf-8"), ensure_ascii=False, indent=2)
        try:
            import run_cloud_parity_proof_884 as h884
            audit, audit_ok = h884.independent_audit(text, ev)
            audit_ran = True
            json.dump(audit, open(os.path.join(ART_DIR, "audit.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            uns = audit.get("unsupported")
            print("audit unsupported count:", len(uns) if isinstance(uns, list) else uns)
        except Exception as e:
            print(f"  audit failed to run: {type(e).__name__}: {e}")
    finally:
        import meter_guard
        usd = max(0.0, _meter_total() - meter0)
        rows_n = meter_guard.count_rows(os.path.join(METER_DIR, "paid_api_calls.jsonl"))
        verdict = meter_guard.check_meter(rows_n, usd, gen_log, audit_ran)
        rec = verdict["record_usd"]
        task_budget.record_run(TASK, rec, note="real orchestrator path, 1 full tour"
                               + ("" if verdict["ok"] else " (ESTIMATE: meter undercount)"))
        print(f"\n[LOCAL-894] {verdict['message']}")
        print(f"[LOCAL-894] run metered ${rec:.4f}; ledger now "
              f"${task_budget.spent_so_far(TASK)} of ${cap:.2f}")
    print(f"\n=== {'ALL PASS' if ok else 'SOME FAILED (report as-is, do not re-run)'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        sys.exit(cmd_selfcheck())
    if a.run:
        sys.exit(cmd_run())
    ap.print_help()
