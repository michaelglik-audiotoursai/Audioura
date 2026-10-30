#!/usr/bin/env bash
# run_local821b_live.sh — LOCAL-821B live proof.
#
# Proves the NARROW defect behind the 465 event is fixed: when a tour's ZIP
# lives in the DB column audio_tours.audio_tour (GCloud shape), a replace is now
# FULLY REVERSIBLE — the old ZIP BYTES are archived and a restore brings back
# text, stops AND audio byte-for-byte.
#
# This proof costs $0 in LLM spend: it drives the REAL production store path
# (tour_orchestrator_service.store_audio_tour) and the REAL restore tool
# (restore_tour_version.py) directly, with synthetic ZIP bytes, against a
# THROWAWAY Postgres in its OWN compose project. It never touches the shared
# audioura-* containers and never writes the live DB.
#
# Flow:
#   1. store_audio_tour(... text=v1, audio=ZIP_v1) -> INSERT; ZIP_v1 bytes land
#      in audio_tours.audio_tour. Record md5(ZIP_v1).
#   2. store_audio_tour(... SAME name/creator/track, text=v2, audio=ZIP_v2)
#      -> REPLACED (D622 default). The OLD ZIP_v1 bytes are archived in
#      audio_tour_versions.zip_bytes FIRST; the live row now holds ZIP_v2.
#   3. restore_tour_version.py <id> 1 --apply -> the live row's audio_tour is
#      restored to ZIP_v1. Prove md5(live audio) == md5(ZIP_v1).
#
# Budget: TASK_BUDGET_ID=LOCAL-821B TASK_BUDGET_USD=0.40. No paid API is called
# here (pure DB + local code), so spend is $0; the cap is a backstop.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local821b"
PG_CONTAINER="${PROJECT}-pg"
PG_PORT=55433
export TASK_BUDGET_ID=LOCAL-821B
export TASK_BUDGET_USD=0.40

say () { echo; echo "######## [local821b] $* ########"; }

cleanup () {
  say "tearing down ${PG_CONTAINER} (OWN throwaway Postgres only)"
  docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "starting throwaway Postgres (${PG_CONTAINER}) on :${PG_PORT}"
docker rm -f "${PG_CONTAINER}" >/dev/null 2>&1 || true
docker run -d --name "${PG_CONTAINER}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=audiotours \
  -p ${PG_PORT}:5432 postgres:15 >/dev/null || { echo "could not start postgres"; exit 1; }

say "waiting for postgres health"
for i in $(seq 1 60); do
  docker exec "${PG_CONTAINER}" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 1
done

# Minimal audio_tours shape the store path needs; store_audio_tour self-heals the
# rest (creator_user_id, track, tour_content, number_requested, audio_tour, …)
# and builds audio_tour_versions via _ensure_versioning_objects (incl. zip_bytes).
say "seeding a minimal audio_tours table (store path self-heals the rest)"
docker exec -i "${PG_CONTAINER}" psql -U admin -d audiotours -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
CREATE TABLE IF NOT EXISTS audio_tours (
    id SERIAL PRIMARY KEY,
    tour_name VARCHAR(255) NOT NULL,
    request_string TEXT NOT NULL,
    audio_tour BYTEA,
    number_requested INTEGER NOT NULL DEFAULT 0,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    tour_content TEXT,
    content_language VARCHAR(8),
    storied_mode BOOLEAN DEFAULT FALSE,
    stops_count INTEGER,
    zip_filename VARCHAR(512),
    is_test BOOLEAN DEFAULT FALSE,
    original_tour_id INTEGER
);
SQL

say "running the replace + restore md5 round-trip through the REAL code"
DB_HOST=localhost DB_PORT=${PG_PORT} DB_NAME=audiotours DB_USER=admin DB_PASSWORD=password123 \
TOURS_DIR="$(mktemp -d)" \
python3 - "$HERE" <<'PY'
import hashlib, os, sys, tempfile, zipfile
sys.path.insert(0, sys.argv[1])
import tour_orchestrator_service as orch
import restore_tour_version as rtv

tmp = os.environ["TOURS_DIR"]

def make_zip(name, payload):
    p = os.path.join(tmp, name)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("audio_1.mp3", payload)
    with open(p, "rb") as f:
        return p, f.read()

NAME = "GCloud DB-ZIP Tour (local821b)"
CREATOR = "curator-local821b"
TRACK = "subscribed"

# 1. INSERT v1 with ZIP bytes landing in audio_tours.audio_tour.
z1_path, z1_bytes = make_zip("v1.zip", b"ORIGINAL-ZIP-BYTES-v1-%s" % os.urandom(8))
r1 = orch.store_audio_tour(NAME, "req:"+NAME, z1_path, 1.0, 2.0,
        tour_content="v1 text", stops_count=4, is_test=True,
        track=TRACK, job_id="job-v1", user_id=CREATOR)
assert r1["action"] == "inserted", r1
md5_v1 = hashlib.md5(z1_bytes).hexdigest()
print(f"  [1] INSERT v1: action={r1['action']} md5(ZIP_v1)={md5_v1}")

# 2. REPLACE with different text + different ZIP bytes (D622 default).
z2_path, z2_bytes = make_zip("v2.zip", b"NEW-ZIP-BYTES-v2-%s" % os.urandom(8))
r2 = orch.store_audio_tour(NAME, "req:"+NAME, z2_path, 1.0, 2.0,
        tour_content="v2 text changed", stops_count=7, is_test=True,
        track=TRACK, job_id="job-v2", user_id=CREATOR)
assert r2["action"] == "replaced", r2
tour_id = r2["existing_tour_id"]
md5_v2 = hashlib.md5(z2_bytes).hexdigest()
print(f"  [2] REPLACE v2: action={r2['action']} id={tour_id} md5(ZIP_v2)={md5_v2}")

import psycopg2
def connect():
    return psycopg2.connect(host="localhost", port=os.environ["DB_PORT"],
        dbname="audiotours", user="admin", password="password123")

# Prove the old bytes were archived and the live row holds v2.
conn = connect(); cur = conn.cursor()
cur.execute("SELECT zip_bytes FROM audio_tour_versions WHERE tour_id=%s AND version_no=1", (tour_id,))
arch = cur.fetchone()[0]
cur.execute("SELECT audio_tour FROM audio_tours WHERE id=%s", (tour_id,))
live_after_replace = cur.fetchone()[0]
conn.close()
md5_arch = hashlib.md5(bytes(arch)).hexdigest() if arch is not None else None
md5_live2 = hashlib.md5(bytes(live_after_replace)).hexdigest()
print(f"  [2] archived zip_bytes md5={md5_arch}  live audio md5={md5_live2}")
assert md5_arch == md5_v1, f"archived bytes != original v1 ({md5_arch} != {md5_v1})"
assert md5_live2 == md5_v2, "live row should hold v2 bytes after replace"

# 3. RESTORE v1 via the REAL tool (--apply), prove md5(live audio) == md5(ZIP_v1).
rtv.TOURS_DIR = tmp
rc = rtv.restore(tour_id, 1, apply_changes=True)
assert rc == 0, f"restore rc={rc}"
conn = connect(); cur = conn.cursor()
cur.execute("SELECT tour_content, stops_count, audio_tour FROM audio_tours WHERE id=%s", (tour_id,))
c, s, live_after_restore = cur.fetchone()
conn.close()
md5_restored = hashlib.md5(bytes(live_after_restore)).hexdigest()
print(f"  [3] RESTORE v1: text={c!r} stops={s} live audio md5={md5_restored}")

ok = (md5_restored == md5_v1 and c == "v1 text" and s == 4)
print()
print(f"  md5(ZIP_v1 original) = {md5_v1}")
print(f"  md5(live after restore) = {md5_restored}")
print(f"  EQUAL: {md5_restored == md5_v1}")
print()
print("  LOCAL-821B LIVE PROOF: " + ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
PY
RC=$?

say "VERDICT"
if [ "${RC}" = "0" ]; then
  echo "  PASS: replace archived the OLD ZIP bytes; restore round-tripped audio md5 to the original."
  echo "  LLM spend: \$0 (pure DB + local code; no paid API called)."
else
  echo "  PROOF FAILED — see above."
fi
exit ${RC}
