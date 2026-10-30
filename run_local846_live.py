#!/usr/bin/env python3
"""run_local846_live.py — LOCAL-846 live, budget-enforced proof.

Drives the REAL production code in tour_orchestrator_service against an OWN
isolated Postgres (compose project local846, port 55846) — never the live DB,
never a shared audioura-* container. LOCAL-846 is a DB-finalisation fix, so no
LLM call is made: $0 of the $0.20 budget.

What it proves, end to end, through the production functions:

  SHORT TOUR (happy path):
    * simulate the orchestrator creating its own row (source='orchestrator',
      tour_id=job_id) AND the app tracking row exactly as production does
      (track_user_tour → tour_id = 'tour_'+job_id[:8], source='tracking');
    * call the real _set_tour_request_status(job_id, 'completed');
    * PROVE both rows are terminal ('completed') — the tracking row no longer
      sits at 'started' waiting for an app update that never comes.

  SIMULATED TRACKING-ROW DUPLICATE (the 830 double tap) + an ORPHAN:
    * a second tracking row for the same (secret_id, tour_id) — the double tap;
    * an orphan tracking row 'started' > 2 h with no orchestrator partner;
    * call the real _sweep_stale_tracking_rows();
    * PROVE the duplicate → 'failed' ('duplicate tracking row') and the orphan →
      'failed' ('stale tracking row'); a fresh (<2 h) row is left 'started'.

PASS requires every asserted row to reach its expected terminal state AND the
idempotent second sweep to change nothing.
"""
import os
import sys

# Point every psycopg2 connection the production code opens at the isolated DB.
os.environ["DB_HOST"] = os.environ.get("LOCAL846_DB_HOST", "localhost")
os.environ["DB_PORT"] = os.environ.get("LOCAL846_DB_PORT", "55846")
os.environ["DB_NAME"] = "audiotours"
os.environ["DB_USER"] = "admin"
os.environ["DB_PASSWORD"] = "password123"
# Keep the resume/sweep daemon OFF — we call the sweep function directly.
os.environ.setdefault("ORCH_RESUME_ENABLED", "false")

BUDGET_ID = os.environ.get("TASK_BUDGET_ID", "LOCAL-846")
BUDGET_USD = float(os.environ.get("TASK_BUDGET_USD", "0.20") or "0.20")

import psycopg2  # noqa: E402
import tour_orchestrator_service as orch  # noqa: E402


def _conn():
    return psycopg2.connect(
        host=os.environ["DB_HOST"], port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"], connect_timeout=5,
    )


def _seed_user(secret_id):
    with _conn() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO users (secret_id, app_version) VALUES (%s, 'local846-proof') "
            "ON CONFLICT (secret_id) DO NOTHING",
            (secret_id,),
        )
        c.commit()


def _insert_orch(job_id, secret_id, status="started"):
    with _conn() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source) "
            "VALUES (%s, %s, %s, NOW(), 'orchestrator') RETURNING id",
            (secret_id, job_id, status),
        )
        rid = cur.fetchone()[0]
        c.commit()
        return rid


def _insert_tracking(tour_id, secret_id, status="started", age_seconds=0,
                     request_string="see Nice old town"):
    with _conn() as c:
        cur = c.cursor()
        cur.execute(
            "INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at, source) "
            "VALUES (%s, %s, %s, %s, NOW() - (%s || ' seconds')::interval, 'tracking') RETURNING id",
            (secret_id, tour_id, request_string, status, str(int(age_seconds))),
        )
        rid = cur.fetchone()[0]
        c.commit()
        return rid


def _row(rid):
    with _conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT status, finished_at, request_string, source FROM tour_requests WHERE id = %s",
            (rid,),
        )
        r = cur.fetchone()
        return {"status": r[0], "finished_at": r[1], "request_string": r[2], "source": r[3]}


def main():
    print("=" * 72)
    print("LOCAL-846 LIVE PROOF — tracking rows reach a terminal state")
    print(f"  TASK_BUDGET_ID={BUDGET_ID}  cap=${BUDGET_USD:.2f}  (LLM spend: $0.00 — DB-only fix)")
    print(f"  DB: {os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']} "
          f"(isolated compose project local846 — NOT the live DB)")
    print("=" * 72)

    import uuid
    checks = []

    # ── Arm 1: short tour, happy path — mirror at finalize ────────────────────
    job_id = uuid.uuid4().hex
    secret_id = "SID-" + uuid.uuid4().hex[:10]
    tracking_tour_id = orch._tracking_tour_id_for(job_id)
    _seed_user(secret_id)
    orch_rid = _insert_orch(job_id, secret_id, status="started")
    trk_rid = _insert_tracking(tracking_tour_id, secret_id, status="started")
    print(f"\n[ARM 1] short tour job_id={job_id[:8]}…")
    print(f"  orchestrator row id={orch_rid} tour_id={job_id[:12]}… status=started")
    print(f"  tracking    row id={trk_rid} tour_id={tracking_tour_id} status=started")
    print("  → calling production _set_tour_request_status(job_id, 'completed')")
    orch._set_tour_request_status(job_id, "completed")
    o, t = _row(orch_rid), _row(trk_rid)
    print(f"  AFTER: orchestrator status={o['status']}  tracking status={t['status']} "
          f"finished_at={'set' if t['finished_at'] else 'NULL'}")
    checks.append(("ARM1 orchestrator completed", o["status"] == "completed"))
    checks.append(("ARM1 tracking MIRRORED to completed", t["status"] == "completed"))
    checks.append(("ARM1 tracking finished_at set", t["finished_at"] is not None))

    # ── Arm 2: duplicate (830 double tap) + orphan + fresh — the sweep ────────
    dup_secret = "SID-" + uuid.uuid4().hex[:10]
    _seed_user(dup_secret)
    dup_tour = "tour_" + uuid.uuid4().hex[:8]
    dup_old = _insert_tracking(dup_tour, dup_secret, status="started", age_seconds=20)
    dup_new = _insert_tracking(dup_tour, dup_secret, status="started", age_seconds=5)

    orphan_secret = "SID-" + uuid.uuid4().hex[:10]
    _seed_user(orphan_secret)
    orphan_tour = "tour_" + uuid.uuid4().hex[:8]
    orphan_rid = _insert_tracking(orphan_tour, orphan_secret, status="started",
                                  age_seconds=2 * 60 * 60 + 300)  # > 2 h

    fresh_secret = "SID-" + uuid.uuid4().hex[:10]
    _seed_user(fresh_secret)
    fresh_tour = "tour_" + uuid.uuid4().hex[:8]
    fresh_rid = _insert_tracking(fresh_tour, fresh_secret, status="started",
                                 age_seconds=60 * 30)  # 30 min — under threshold

    print(f"\n[ARM 2] duplicate double-tap on tour_id={dup_tour} "
          f"(older id={dup_old}, newer id={dup_new})")
    print(f"  orphan row id={orphan_rid} age>2h   fresh row id={fresh_rid} age=30m")
    print("  → calling production _sweep_stale_tracking_rows()")
    counts = orch._sweep_stale_tracking_rows()
    print(f"  sweep counts: {counts}")
    do, dn = _row(dup_old), _row(dup_new)
    orp, fr = _row(orphan_rid), _row(fresh_rid)
    print(f"  duplicate older status={do['status']} reason={do['request_string']!r}")
    print(f"  duplicate newer status={dn['status']} (kept)")
    print(f"  orphan status={orp['status']} reason={orp['request_string']!r}")
    print(f"  fresh  status={fr['status']} (left alone)")
    checks.append(("ARM2 duplicate older → failed", do["status"] == "failed"))
    checks.append(("ARM2 duplicate reason recorded",
                   "duplicate tracking row" in (do["request_string"] or "")))
    checks.append(("ARM2 duplicate newer kept non-terminal", dn["status"] == "started"))
    checks.append(("ARM2 orphan → failed", orp["status"] == "failed"))
    checks.append(("ARM2 orphan reason recorded",
                   "stale tracking row" in (orp["request_string"] or "")))
    checks.append(("ARM2 fresh (<2h) left 'started'", fr["status"] == "started"))

    # ── Arm 3: idempotency ────────────────────────────────────────────────────
    print("\n[ARM 3] idempotency — second sweep must change nothing")
    counts2 = orch._sweep_stale_tracking_rows()
    print(f"  second sweep counts: {counts2}")
    checks.append(("ARM3 second sweep is a no-op",
                   counts2 == {"mirrored": 0, "orphaned": 0, "duplicates": 0}))

    # ── No phantom in-progress tracking rows remain where they should be gone ─
    # The ARM1 tracking row (mirrored) and the orphan were finalised; they must
    # no longer be 'started'. The newest duplicate is DELIBERATELY kept 'started'
    # (it is the live request the double tap maps to), so it is NOT a phantom and
    # is excluded here.
    with _conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM tour_requests "
            "WHERE source='tracking' AND status='started' AND id = ANY(%s)",
            ([trk_rid, orphan_rid],),
        )
        phantom = cur.fetchone()[0]
    print(f"\n  phantom 'started' rows among the finalised/swept rows: {phantom} "
          f"(expected 0; the kept newest-duplicate stays 'started' by design)")
    checks.append(("no phantom in-progress rows among finalised/swept rows", phantom == 0))

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("LOCAL-846 PROOF SUMMARY")
    print("=" * 72)
    all_pass = True
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        all_pass = all_pass and ok
    print("-" * 72)
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}   "
          f"(LLM spend $0.00 / cap ${BUDGET_USD:.2f})")
    print("=" * 72)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
