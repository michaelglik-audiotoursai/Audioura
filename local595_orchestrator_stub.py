#!/usr/bin/env python3
"""local595_orchestrator_stub.py — LOCAL-595 / LOCAL-595B live-check harness.

A minimal stand-in for the tour-orchestrator's generate path that exercises the
REAL enforcement module (subscription_levels / entitlements) but STUBS the
generator entirely — zero OpenAI / Gemini / TTS spend.

It mirrors the exact gate + lifecycle the production orchestrator uses:
    request time : check_operation -> 429 on refusal -> clamp ->
                   write tour_requests row 'started' -> RESERVE pack unit
    async outcome:
      * fresh success -> mark row 'completed', reservation STANDS
      * cache hit     -> mark row 'completed', RELEASE reservation  (defect 3)
      * failure       -> mark row 'failed',    RELEASE reservation  (defect 2)

The `outcome` field in the request body selects which async result to simulate
(fresh | cache_hit | fail). Nothing external is ever called — $0.00 spend.

Built as its OWN container (local595-orchestrator) on development_default. It
never touches any audioura-* container.
"""
import os
import sys
import uuid

import psycopg2
from flask import Flask, request, jsonify

sys.stdout.reconfigure(line_buffering=True)
app = Flask(__name__)


def _db():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432'),
    )


def _set_tour_request_status(job_id, status):
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE tour_requests SET status = %s, finished_at = NOW()
            WHERE tour_id = %s AND source = 'orchestrator'
        """, (status, job_id))
        conn.commit()
        cur.close()
    finally:
        conn.close()


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "local595-orchestrator-stub-r2"})


@app.route('/generate-complete-tour', methods=['POST'])
def generate():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    total_stops = int(data.get('total_stops', 5))
    outcome = str(data.get('outcome', 'fresh')).lower()  # fresh | cache_hit | fail

    if not user_id or not user_id.strip():
        return jsonify({"allowed": False, "error_code": "level_cannot_generate",
                        "message": "A valid user id is required."}), 401

    # ── REAL enforcement, identical to the production orchestrator ──
    from entitlements import check_operation, reserve_operation, release_operation
    quota = check_operation(user_id, 'generate', requested_stops=total_stops)
    if not quota['allowed']:
        print(f"[LIVE595] generate DENIED for {user_id}: {quota.get('error_code')}")
        return jsonify(quota), 429

    total_stops = quota['clamped_stops']

    # Record the generation exactly as the orchestrator does (source='orchestrator',
    # status 'started'), then RESERVE the pack unit. Generator is stubbed.
    job_id = str(uuid.uuid4())
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO users (secret_id, plan, is_test) VALUES (%s, 'l2', TRUE) "
                    "ON CONFLICT (secret_id) DO NOTHING", (user_id,))
        cur.execute("""
            INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
            VALUES (%s, %s, 'started', NOW(), 'orchestrator')
        """, (user_id, job_id))
        conn.commit()
        cur.close()
    finally:
        conn.close()

    reserve_operation(user_id, 'generate')
    print(f"[LIVE595] RESERVED for {user_id}: level={quota.get('level')} stops={total_stops} job={job_id}")

    # ── Simulate the async outcome ──
    if outcome == 'fail':
        _set_tour_request_status(job_id, 'failed')
        release_operation(user_id, 'generate')
        print(f"[LIVE595] FAILED job={job_id} — row 'failed', reservation released")
        return jsonify({"allowed": True, "delivered": False, "outcome": "fail",
                        "level": quota.get('level'), "job_id": job_id}), 200
    if outcome == 'cache_hit':
        _set_tour_request_status(job_id, 'completed')
        release_operation(user_id, 'generate')
        print(f"[LIVE595] CACHE HIT job={job_id} — row 'completed', reservation released (defect 3)")
        return jsonify({"allowed": True, "delivered": True, "outcome": "cache_hit",
                        "level": quota.get('level'), "job_id": job_id}), 200
    # fresh success
    _set_tour_request_status(job_id, 'completed')
    print(f"[LIVE595] FRESH SUCCESS job={job_id} — row 'completed', reservation stands")
    return jsonify({"allowed": True, "delivered": True, "outcome": "fresh",
                    "level": quota.get('level'), "job_id": job_id,
                    "note": "generator stubbed — no OpenAI spend"}), 200


@app.route('/entitlements/me', methods=['GET'])
def me():
    """Report fresh_used/ops_used + today's completed count for the walk."""
    user_id = request.args.get('user_id')
    conn = _db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT level, fresh_used, ops_used FROM device_entitlement WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.execute("""
            SELECT COUNT(*) FROM tour_requests
            WHERE secret_id = %s AND source='orchestrator'
              AND status='completed' AND started_at::date = CURRENT_DATE
        """, (user_id,))
        completed_today = cur.fetchone()[0]
        cur.close()
    finally:
        conn.close()
    if not row:
        return jsonify({"user_id": user_id, "level": "l1", "fresh_used": 0,
                        "ops_used": 0, "completed_today": completed_today}), 200
    return jsonify({"user_id": user_id, "level": row[0], "fresh_used": row[1],
                    "ops_used": row[2], "completed_today": completed_today}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
