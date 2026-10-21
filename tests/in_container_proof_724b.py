#!/usr/bin/env python3
"""in_container_proof_724b.py — run INSIDE the orchestrator container (D684).

Proves, through the REAL tour_orchestrator_service.store_audio_tour serving
path writing to this stack's isolated postgres:

  B) A newly stored ORIGINAL is RATED before it could appear in /tours-near:
     store_audio_tour rates in the same transaction that makes the row
     listable, so the committed row already carries content_rating, and the
     real map_delivery listing predicate agrees.

  C) With OPENAI_API_KEY BLANKED, a new tour cannot be rated and is HELD
     (content_rating NULL, review_status 'pending') — NOT listable — instead of
     being committed unrated and shown as general.

Mode is chosen by argv[1] = 'rated' | 'held'. Prints a single RESULT line the
outer proof harness greps.
"""
import os
import sys
import uuid
import zipfile

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/map_delivery")

import tour_orchestrator_service as orch  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "rated"

# Build a tiny ZIP the store can read.
orch.TOURS_DIR = "/tmp"
zip_path = "/tmp/proof_%s.zip" % mode
with zipfile.ZipFile(zip_path, "w") as z:
    z.writestr("tour.mp3", b"stop-audio")

name = "LOCAL724B Proof %s %s" % (mode, uuid.uuid4().hex[:8])
# A clearly-GENERAL tour text (> 200 chars) so a working rater returns 'general'.
content = ("The old cathedral has stood on this square since 1377. Its nave, "
           "rose window and cloister are among the finest Gothic work in the "
           "region, and the adjoining museum holds illuminated manuscripts. "
           "This walking tour visits the facade, the crypt and the bell tower. ") * 2

res = orch.store_audio_tour(
    name, "req:" + name, zip_path, lat=41.9, lng=12.5,
    tour_content=content, stops_count=3, is_test=False, job_id="proof-" + mode)

# Read the stored row's rating columns straight from the DB.
import psycopg2  # noqa: E402
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "postgres-2"), dbname=os.getenv("DB_NAME", "audiotours"),
    user=os.getenv("DB_USER", "admin"), password=os.getenv("DB_PASSWORD", "password123"),
    port=os.getenv("DB_PORT", "5432"))
cur = conn.cursor()
cur.execute("SELECT id, content_rating, review_status FROM audio_tours "
            "WHERE tour_name = %s", (name,))
row = cur.fetchone()
conn.close()

# Inline copy of map_delivery/app.py:_content_visible (pure function) so this
# proof needs only the orchestrator image. NULL rating == general; pending /
# rejected / not_allowed are hidden; mature needs adult.
def _content_visible(content_rating, review_status, adult):
    r = (content_rating or "general").strip().lower()
    s = (review_status or "").strip().lower()
    if r == "not_allowed":
        return False
    if s in ("pending", "rejected"):
        return False
    if r == "mature":
        return bool(adult)
    return True

tid, rating, status = row
visible = _content_visible(rating, status, False)
print("STORE_ACTION=%s" % res.get("action"))
print("ROW id=%s content_rating=%r review_status=%r listable=%s"
      % (tid, rating, status, visible))

if mode == "rated":
    ok = (rating is not None) and (status is None) and visible
    print("RESULT rated: %s (a new tour is RATED before it can list)"
          % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)
else:  # held
    ok = (rating is None) and (status == "pending") and (not visible)
    print("RESULT held: %s (OPENAI blanked -> new tour HELD, not listable)"
          % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)
