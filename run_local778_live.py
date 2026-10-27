#!/usr/bin/env python3
"""run_local778_live.py — LOCAL-778 live proof against the OWN local778 stack.

Submits the three brief venues to the isolated local778 orchestrator (spare port
55002), polls to completion, and reports reused_stops / researched_stops / $ per
run plus audio_tours row counts. Budget <= $2.00.

Never touches the shared audioura-* stack or development-postgres-2-1.
"""
import json
import sys
import time
import urllib.request

ORCH = "http://localhost:55002"
PG = dict(host="localhost", port=55433, dbname="audiotours",
          user="admin", password="password123")
UID = "local778-tester"


def _post(path, body):
    req = urllib.request.Request(
        ORCH + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())


def _get(path):
    with urllib.request.urlopen(ORCH + path, timeout=60) as r:
        return json.loads(r.read().decode())


def _db():
    import psycopg2
    return psycopg2.connect(**PG)


def _cost_for_job(job_id):
    """Read our_cost_usd from cost_ledger for this job, if present."""
    try:
        c = _db()
        cur = c.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='cost_ledger'")
        cols = {r[0] for r in cur.fetchall()}
        cost_col = 'our_cost_usd' if 'our_cost_usd' in cols else (
            'total_cost_usd' if 'total_cost_usd' in cols else None)
        if cost_col and 'job_id' in cols:
            cur.execute(f"SELECT {cost_col} FROM cost_ledger WHERE job_id=%s", (job_id,))
            rows = cur.fetchall()
            c.close()
            if rows:
                return sum(float(x[0] or 0) for x in rows)
        c.close()
    except Exception as e:
        print(f"   (cost read skipped: {e})")
    return None


def _audio_tours_count():
    c = _db(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    n = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM audio_tours WHERE original_tour_id IS NULL")
    o = cur.fetchone()[0]
    c.close()
    return n, o


def _ensure_device(uid):
    """Seed an L2 device + user for this uid (each venue uses its own device so
    the 1/day cap does not block the three-venue proof — the cap and concurrency
    guard are proven separately by the unit tests)."""
    c = _db(); cur = c.cursor()
    cur.execute("INSERT INTO users (secret_id, plan) VALUES (%s,'l2') "
                "ON CONFLICT (secret_id) DO NOTHING", (uid,))
    cur.execute("INSERT INTO device_entitlement (user_id, level) VALUES (%s,'l2') "
                "ON CONFLICT (user_id) DO UPDATE SET level='l2'", (uid,))
    c.commit(); c.close()


def run_one(label, location, tour_type, total_stops, uid):
    print(f"\n===== {label}: {location!r} ({total_stops} stops) uid={uid} =====")
    _ensure_device(uid)
    before_n, before_o = _audio_tours_count()
    resp = _post("/generate-complete-tour", {
        "location": location, "tour_type": tour_type,
        "total_stops": total_stops, "user_id": uid,
    })
    job_id = resp.get("job_id")
    print(f"   job_id={job_id} queued={resp.get('status')}")
    if not job_id:
        print(f"   REFUSED / no job: {resp}")
        return
    status, data = None, {}
    deadline = time.time() + 1500  # 25 min cap
    while time.time() < deadline:
        time.sleep(8)
        try:
            data = _get(f"/status/{job_id}")
        except Exception as e:
            print(f"   poll error: {e}")
            continue
        status = data.get("status")
        if status in ("completed", "error", "failed"):
            break
        print(f"   ... {status}: {data.get('progress','')[:70]}")
    print(f"   FINAL status={status}")
    if status != "completed":
        print(f"   message={data.get('message')} error_code={data.get('error_code')}")
    cost = _cost_for_job(job_id)
    after_n, after_o = _audio_tours_count()
    print(f"   $ (cost_ledger our_cost_usd) = {cost}")
    print(f"   audio_tours: total {before_n}->{after_n}, originals {before_o}->{after_o}")
    return job_id


if __name__ == "__main__":
    print("LOCAL-778 live proof — reuse-first (own stack, spare ports)")
    n0, o0 = _audio_tours_count()
    print(f"audio_tours at start: total={n0} originals={o0}")
    # (1) Venue the DB already has a tour for, same stop count -> full reuse.
    run_one("V1 full-reuse", "Salem Witch Museum, Salem, MA", "museum", 4,
            "local778-v1")
    # (2) Same venue, MORE stops than stored -> reuse 4 + research the rest.
    run_one("V2 hybrid", "Salem Witch Museum, Salem, MA", "museum", 5,
            "local778-v2")
    # (3) A brand-new place -> fully researched (fresh path).
    run_one("V3 fresh", "Gyms near me, West Roxbury, MA", "walking", 2,
            "local778-v3")
    nF, oF = _audio_tours_count()
    print(f"\naudio_tours at end: total={nF} originals={oF}")
