#!/usr/bin/env python3
"""LOCAL-628 one-shot live driver. Generates ONE tour fresh (cache+pool off),
with the stop editor ON, prints the [LOCAL-628] log lines, the per-tour cost, and
inserts the delivered tour into audio_tours as an is_test row so critique.sh can
read it. Reserve gate: aborts a tour that would exceed $0.90.
"""
import os
import sys
import json
import time

LOCATION = sys.argv[1]
STOPS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
OUT = sys.argv[3] if len(sys.argv) > 3 else "/app/tours/local628_live.txt"

os.environ["STORIED_MODE"] = "true"
os.environ["STOP_EDITOR"] = "1"
os.environ["DISABLE_STOP_POOL"] = "1"
os.environ["DISABLE_TOUR_CACHE"] = "1"
os.environ.setdefault("ATTESTATION_MODE", "log_only")

import generate_tour_text as gtt

t0 = time.time()
tour_text, out_file, coords = gtt.generate_tour_text(
    LOCATION, "walking", OUT, total_stops=STOPS)
elapsed = time.time() - t0

cost = getattr(gtt, "_LAST_GENERATION_COST", {}) or {}
print("\n==== LOCAL-628 ONE-SHOT RESULT ====")
print(f"location: {LOCATION}")
print(f"stops_requested: {STOPS}")
print(f"elapsed_s: {elapsed:.1f}")
print(f"delivery_path: {getattr(gtt, '_LAST_DELIVERY_PATH', '?')}")
print(f"cost_record: {json.dumps(cost)}")
print(f"edited_marker_present: {'<!-- LOCAL-628:stop-editor:v1 -->' in (tour_text or '')}")

# Persist as an is_test row so critique.sh (reads audio_tours) can score it.
try:
    import psycopg2
    db = os.environ.get("DATABASE_URL",
                        "postgresql://admin:password123@postgres-2:5432/audiotours")
    conn = psycopg2.connect(db)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO audio_tours (tour_name, request_string, number_requested, "
            "tour_content, stops_count, creator_type, storied_mode, is_test, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,NOW()) RETURNING id",
            (LOCATION, LOCATION, STOPS, tour_text, STOPS, "test", True))
        new_id = cur.fetchone()[0]
    conn.close()
    print(f"audio_tours_id: {new_id}")
except Exception as e:
    print(f"DB insert failed (non-fatal for critique via file): {type(e).__name__}: {e}")
