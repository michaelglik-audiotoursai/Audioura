#!/usr/bin/env python3
"""run_local614_live.py — LOCAL-614 isolated live McMullen run + critique seed.

Runs INSIDE a disposable container (docker run --rm --name local614-gen …), never
against the audioura-* stack. Generates ONE real McMullen Museum of Art tour,
7 stops, with the stop POOL ON (DISABLE_STOP_POOL is NOT set), metered and hard-
capped at $1 by tests/live_run_meter.py (LOCAL-613, TEST_GEMINI_MAX_USD).

It then stores the delivered tour_content in the development-postgres-2-1
``audio_tours`` table (is_test=true, creator_type='Test') and prints the new row
id, so ~/.continuous_dev/calib/critique.sh <id> can read and score the SAME text
the five LOCAL-614 fixes produced.

No DELETE. The only row this writes is one additive audio_tours test row.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

# [LOCAL-613] Meter + hard-cap this isolated run at $1 (all providers combined).
try:
    import live_run_meter as _lrm
    _lrm.auto_meter("LOCAL-614")
except Exception as _e:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({_e}): run not metered/capped")

# Load .env (API keys) the same way the other harnesses do.
_envfile = os.path.join(HERE, ".env")
if os.path.exists(_envfile):
    for line in open(_envfile):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ["STORIED_MODE"] = "true"
# Pool ON (do NOT disable it). A hard per-run LLM ceiling as belt-and-suspenders;
# the $1 combined cap in live_run_meter is the authoritative stop.
os.environ.setdefault("COST_HARD_LIMIT_USD", "1.00")

LOCATION = os.environ.get("LOCAL614_LOCATION",
                          "McMullen Museum of Art, Boston College, Boston, MA")
TOUR_TYPE = os.environ.get("LOCAL614_TYPE", "museum")
STOPS = int(os.environ.get("LOCAL614_STOPS", "7"))
_OUTDIR = os.path.join(HERE, "tours") if os.path.isdir(os.path.join(HERE, "tours")) else HERE
OUT = os.path.join(_OUTDIR, "LOCAL614_mcmullen.txt")

import generate_tour_text as g  # noqa: E402

print("=" * 74)
print(f"LOCAL-614 live: {LOCATION} / {TOUR_TYPE} / {STOPS} stops  (pool ON, cap $1)")
print("=" * 74, flush=True)

t0 = time.time()
text, _out, raw_coords = g.generate_tour_text(LOCATION, TOUR_TYPE, OUT, STOPS)
wall = time.time() - t0

cost = dict(getattr(g, "_LAST_GENERATION_COST", {}) or {})
path = getattr(g, "_LAST_DELIVERY_PATH", "?")
n_stops = len(re.findall(r"^Stop\s+\d+:", text or "", re.M))
lat, lng = (raw_coords or (None, None))

print("\n" + "=" * 74)
print("LOCAL-614 RESULT")
print("=" * 74)
print(f"  delivery_path   : {path}")
print(f"  delivered stops : {n_stops}")
print(f"  new_cost (LLM)  : ${cost.get('total_cost', 0.0):.4f}")
print(f"  tour total      : ${cost.get('tour_total_cost', 0.0):.4f}")
print(f"  wall            : {wall:.0f}s")
print(f"  chars           : {len(text) if text else 0}")

if not text or n_stops == 0:
    print("FAIL: no tour text generated.")
    sys.exit(1)

# ── Store the delivered text so critique.sh can read it ──────────────────────
import psycopg2  # noqa: E402

dburl = os.environ.get("DATABASE_URL")
conn = psycopg2.connect(dburl) if dburl else psycopg2.connect(
    host=os.environ.get("DB_HOST", "postgres-2"),
    port=os.environ.get("DB_PORT", "5432"),
    dbname=os.environ.get("DB_NAME", "audiotours"),
    user=os.environ.get("DB_USER", "admin"),
    password=os.environ.get("DB_PASSWORD", "password123"),
)
conn.autocommit = True
tour_name = f"LOCAL-614 McMullen test {int(time.time())}"
with conn.cursor() as cur:
    cur.execute(
        """
        INSERT INTO audio_tours
            (tour_name, request_string, number_requested, lat, lng,
             tour_content, stops_count, creator_type, storied_mode, is_test,
             track, tour_kind, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'Test', true, true,
                'beta', 'full', %s)
        RETURNING id
        """,
        (tour_name, LOCATION, STOPS, lat, lng, text, n_stops,
         "LOCAL-614 isolated live run (critique seed)"),
    )
    new_id = cur.fetchone()[0]
conn.close()

print(f"  STORED audio_tours id = {new_id}  (is_test=true, creator_type='Test')")
print(f"  CRITIQUE: ~/Audioura/.continuous_dev/calib/critique.sh {new_id}")
print("=" * 74, flush=True)
# A machine-readable line the launcher greps for the id.
print(f"LOCAL614_TOUR_ID={new_id}")
