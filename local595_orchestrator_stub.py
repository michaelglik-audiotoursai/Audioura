#!/usr/bin/env python3
"""local595_orchestrator_stub.py — LOCAL-595 live-check harness.

A minimal stand-in for the tour-orchestrator's generate path that exercises the
REAL enforcement module (entitlements.check_operation / consume_operation) but
STUBS the generator entirely — zero OpenAI / Gemini / TTS spend. It mirrors the
exact gate sequence the production orchestrator uses (see
tour_orchestrator_service.py: check_operation -> 429 on refusal -> clamp ->
record tour_requests row -> consume_operation).

It is built as its OWN container (local595-orchestrator) on development_default.
It never touches any audioura-* container.
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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "local595-orchestrator-stub"})


@app.route('/generate-complete-tour', methods=['POST'])
def generate():
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    total_stops = int(data.get('total_stops', 5))

    if not user_id or not user_id.strip():
        return jsonify({"allowed": False, "error_code": "level_cannot_generate",
                        "message": "A valid user id is required."}), 401

    # ── REAL enforcement, identical to the production orchestrator ──
    from entitlements import check_operation, consume_operation
    quota = check_operation(user_id, 'generate', requested_stops=total_stops)
    if not quota['allowed']:
        print(f"[LIVE595] generate DENIED for {user_id}: {quota.get('error_code')}")
        return jsonify(quota), 429

    total_stops = quota['clamped_stops']

    # Ensure the device's user row exists (FK for tour_requests), then record the
    # generation exactly as the orchestrator does (source='orchestrator'). The
    # generator itself is stubbed — no external calls, no spend.
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

    consume_operation(user_id, 'generate')
    print(f"[LIVE595] generate ALLOWED for {user_id}: level={quota.get('level')} stops={total_stops} job={job_id}")
    return jsonify({
        "allowed": True, "level": quota.get('level'),
        "job_id": job_id, "total_stops": total_stops,
        "note": "generator stubbed — no OpenAI spend",
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
