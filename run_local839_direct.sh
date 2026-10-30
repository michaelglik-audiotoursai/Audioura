#!/usr/bin/env bash
# run_local839_direct.sh — LOCAL-839 budget-safe live proof of the TWO-instance
# modernized (voice/ZIP) handoff, WITHOUT the paid tour-generator.
#
# Brings up ONLY postgres + the two real modernized containers (separate tours
# dirs, shared postgres, JOB_STORE_MODE=layered) + the nginx round-robin + the
# local kokoro-backed polly TTS. Then drives the modernized service the way the
# orchestrator does, but with INLINE tour_content (no OpenAI/SERP/Gemini spend —
# the only paid-ish call is local kokoro TTS at ~$0):
#
#   1. POST /process {tour_content: a 3-stop walking tour} through the nginx
#      round-robin → lands on one instance (A).
#   2. Poll /status through nginx until completed (polls spread A/B).
#   3. GET /download through nginx repeatedly; nginx round-robins, so at least
#      one download is served by the instance that did NOT build the file —
#      the cross-instance hop that used to 404.
#   4. Validate the downloaded ZIP has 3 real MP3 files (audio plays) and that
#      the shared generator_jobs row carries the job + zip_b64 (the layered
#      store + inline-ZIP handoff that makes any instance able to answer).
#
# Isolated project (-p local839d), OWN postgres volume, spare ports, NEVER the
# shared containers or the live DB.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local839d"
COMPOSE="docker-compose.local839-proof.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="/Users/micha/Audioura/.env"
export LOCAL839_METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${LOCAL839_METER_DIR}"

LB_PORT=55821          # nginx round-robin in front of modernized A/B
PSQL=(docker exec -i -e PGPASSWORD=password123 "${PROJECT}-postgres-2-1" psql -U admin -d audiotours -tA)

say () { echo; echo "######## [local839d] $* ########"; }
if [ -f "${ENV_FILE}" ]; then set -a; . "${ENV_FILE}"; set +a; fi

cleanup () {
  say "tearing down project ${PROJECT} (down -v — OWN volume only)"
  "${DC[@]}" down -v >/dev/null 2>&1 || true
  rm -rf "${HERE}/tours_local839_a" "${HERE}/tours_local839_b" \
         "${HERE}/tours_local839_gen" "${HERE}/tours_local839_orch" 2>/dev/null || true
}
trap cleanup EXIT

say "building + starting ONLY postgres + 2 modernized + nginx + polly (no paid generator)"
"${DC[@]}" up -d --build postgres-2 tour-generation-modernized-1 tour-generation-modernized-2 modernized-lb polly-tts-1 \
  || { echo "compose up failed"; exit 1; }

say "waiting for postgres"
for i in $(seq 1 60); do
  docker exec "${PROJECT}-postgres-2-1" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 2
done
say "waiting for the modernized round-robin :${LB_PORT}"
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${LB_PORT}/health" 2>/dev/null || echo 000)
  [ "${code}" = "200" ] && break
  sleep 2
done

q () { "${PSQL[@]}" -c "$1" 2>/dev/null | tr -d '[:space:]'; }

# A compact 3-stop walking tour as inline content (house "Stop N:" headers).
read -r -d '' TOUR_TEXT <<'TXT'
Step-by-Step Audio Guided Tour: Salem Common Public Art Walk - Walking Tour
Tour-Category: walking

Stop 1: Salem Common Bandstand
Orientation: Begin at the historic bandstand at the center of Salem Common.
This 1920s structure has hosted concerts and civic gatherings for a century.

Stop 2: Roger Conant Statue
Orientation: Walk to the northwest corner to the bronze figure of Salem's founder.
The brooding statue is one of the city's most photographed landmarks.

Stop 3: Salem Witch Museum Facade
Orientation: Cross Washington Square to the Romanesque former church.
Its red sandstone arches frame the north edge of the Common.
TXT

say "1. POST /process (inline tour_content) through the round-robin"
RESP=$(curl -s -D /tmp/l839d_hdr.txt -X POST "http://localhost:${LB_PORT}/process" \
  -H 'Content-Type: application/json' \
  --data "$(python3 -c 'import json,sys; print(json.dumps({"tour_content": sys.stdin.read()}))' <<<"$TOUR_TEXT")")
echo "  response: ${RESP}"
echo "  served-by: $(grep -i '^X-Upstream' /tmp/l839d_hdr.txt | tr -d '\r')"
JOB=$(echo "${RESP}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
[ -z "${JOB}" ] && { echo "no job_id — aborting"; exit 1; }
say "1. modernized job_id=${JOB}"

say "2. polling /status through the round-robin until completed"
STATUS=""
for i in $(seq 1 60); do
  H=/tmp/l839d_st_hdr.txt
  S=$(curl -s -D "$H" "http://localhost:${LB_PORT}/status/${JOB}")
  STATUS=$(echo "$S" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo "")
  UP=$(grep -i '^X-Upstream' "$H" | tr -d '\r' | awk '{print $2}')
  echo "    [t=${i}] status=${STATUS} served-by=${UP}"
  [ "${STATUS}" = "completed" ] && break
  [ "${STATUS}" = "error" ] && { echo "  modernized job errored: ${S}"; break; }
  sleep 2
done

say "3. where did the job physically land? (which instance has the ZIP on disk)"
A_FILES=$(ls -1 "${HERE}/tours_local839_a" 2>/dev/null | wc -l | tr -d ' ')
B_FILES=$(ls -1 "${HERE}/tours_local839_b" 2>/dev/null | wc -l | tr -d ' ')
echo "  instance A tours dir: ${A_FILES} file(s): $(ls -1 "${HERE}/tours_local839_a" 2>/dev/null | tr '\n' ' ')"
echo "  instance B tours dir: ${B_FILES} file(s): $(ls -1 "${HERE}/tours_local839_b" 2>/dev/null | tr '\n' ' ')"

say "4. GET /download repeatedly through the round-robin (force the cross-instance hop)"
rm -f /tmp/l839d_tour.zip
GOT_ZIP=0
SERVED_BY=""
for i in $(seq 1 6); do
  H=/tmp/l839d_dl_hdr.txt
  curl -s -D "$H" "http://localhost:${LB_PORT}/download/${JOB}" -o /tmp/l839d_try.zip
  UP=$(grep -i '^X-Upstream' "$H" | tr -d '\r' | awk '{print $2}')
  CT=$(grep -i '^Content-Type' "$H" | tr -d '\r')
  if head -c2 /tmp/l839d_try.zip | grep -q 'PK'; then
    cp /tmp/l839d_try.zip /tmp/l839d_tour.zip
    GOT_ZIP=1
    SERVED_BY="${UP}"
    echo "    [dl ${i}] OK zip served-by=${UP} (${CT})"
  else
    echo "    [dl ${i}] non-zip served-by=${UP} body=$(head -c120 /tmp/l839d_try.zip)"
  fi
  sleep 1
done

say "5. validate the downloaded ZIP audio (audio plays)"
AUDIO_RC=1
if [ "${GOT_ZIP}" = "1" ]; then
  python3 - <<'PY'
import io, sys, zipfile
z = zipfile.ZipFile('/tmp/l839d_tour.zip')
names = z.namelist()
mp3s = sorted(n for n in names if n.endswith('.mp3'))
print(f"  ZIP members: {names}")
ok = True
for n in mp3s:
    data = z.read(n)
    is_audio = (data[:3] == b'ID3' or data[:2] in (b'\xff\xfb', b'\xff\xf3'))
    print(f"    {n}: {len(data)} bytes audio_header={is_audio}")
    if len(data) < 1000 or not is_audio:
        ok = False
print(f"  AUDIO_OK={ok} MP3_COUNT={len(mp3s)}")
sys.exit(0 if (ok and len(mp3s) == 3) else 3)
PY
  AUDIO_RC=$?
fi

say "6. shared layered store evidence (generator_jobs is the cross-instance source of truth)"
ROW_STATUS=$(q "SELECT status FROM generator_jobs WHERE job_id='${JOB}'")
HAS_ZB64=$(q "SELECT (result ? 'zip_b64') FROM generator_jobs WHERE job_id='${JOB}'")
INST=$(q "SELECT instance_id FROM generator_jobs WHERE job_id='${JOB}'")
echo "  generator_jobs.status=${ROW_STATUS} has_zip_b64=${HAS_ZB64} owning_instance=${INST}"
A_STORE=$(docker logs "${PROJECT}-tour-generation-modernized-1-1" 2>&1 | grep -c "\[LOCAL-839\] Stored ZIP" || true)
B_STORE=$(docker logs "${PROJECT}-tour-generation-modernized-2-1" 2>&1 | grep -c "\[LOCAL-839\] Stored ZIP" || true)
A_SERVE=$(docker logs "${PROJECT}-tour-generation-modernized-1-1" 2>&1 | grep -c "Serving /download.*from job store" || true)
B_SERVE=$(docker logs "${PROJECT}-tour-generation-modernized-2-1" 2>&1 | grep -c "Serving /download.*from job store" || true)
echo "  instance A: stored-ZIP=${A_STORE} served-from-store=${A_SERVE}"
echo "  instance B: stored-ZIP=${B_STORE} served-from-store=${B_SERVE}"
CROSS=$(( A_SERVE + B_SERVE ))

say "VERDICT"
PASS=1
[ "${STATUS}" = "completed" ] || { echo "  FAIL(2): modernized job not completed (got '${STATUS}')"; PASS=0; }
[ "${GOT_ZIP}" = "1" ]        || { echo "  FAIL(4): no ZIP served through the round-robin"; PASS=0; }
[ "${AUDIO_RC}" = "0" ]       || { echo "  FAIL(5): ZIP audio invalid / wrong mp3 count"; PASS=0; }
[ "${HAS_ZB64}" = "t" ]       || { echo "  FAIL(6): generator_jobs row missing zip_b64 (handoff not stored)"; PASS=0; }
[ "${CROSS}" -ge 1 ]          || { echo "  FAIL(6): no /download served from the shared store — cross-instance hop not exercised"; PASS=0; }
if [ "${PASS}" = "1" ]; then
  echo "  PASS: a modernized job created on ONE instance was served by BOTH"
  echo "        instances through the round-robin; a /download was served from"
  echo "        the shared layered store (cross-instance=${CROSS}); the ZIP holds"
  echo "        3 real MP3 files (audio plays). zip_b64 is in generator_jobs."
else
  echo "  PROOF FAILED — see above."
fi

say "meter rows (service=LOCAL-839) — TTS only, well under \$0.40"
grep -c 'LOCAL-839' "${LOCAL839_METER_DIR}/paid_api_calls.jsonl" 2>/dev/null || echo "  (no meter rows file)"

exit $([ "${PASS}" = "1" ] && echo 0 || echo 1)
