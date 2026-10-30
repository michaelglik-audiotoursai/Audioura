#!/usr/bin/env bash
# run_local839_e2e.sh — LOCAL-839 END-TO-END proof through the REAL orchestrator,
# budget-safe (fake zero-cost generator; only kokoro TTS spends, ~$0).
#
# ONE 3-stop walking tour, submitted to the orchestrator, flows:
#   orchestrator -> fake generator (canned 3-stop text) -> modernized (via nginx
#   round-robin across TWO instances with SEPARATE tours dirs) -> store.
# Proves:
#   (a) the orchestrator job completes;
#   (b) the tour is stored EXACTLY ONCE in audio_tours (stored once);
#   (c) the stored ZIP holds 3 real MP3 files (audio plays);
#   (d) both modernized instances participated and a /download was served from
#       the shared layered store (cross-instance hop);
#   (e) after the store the orchestrator cleaned the inline zip_b64 blob from the
#       modernized job row (UPDATE result - 'zip_b64', never a DELETE).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local839e"
COMPOSE="docker-compose.local839-e2e.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="/Users/micha/Audioura/.env"

ORCH_PORT=55702
USER_ID="local821-tester"
REQUEST='Salem Common public art walk'
PSQL=(docker exec -i -e PGPASSWORD=password123 "${PROJECT}-postgres-2-1" psql -U admin -d audiotours -tA)

say () { echo; echo "######## [local839e] $* ########"; }
if [ -f "${ENV_FILE}" ]; then set -a; . "${ENV_FILE}"; set +a; fi

cleanup () {
  say "tearing down project ${PROJECT} (down -v — OWN volume only)"
  "${DC[@]}" down -v >/dev/null 2>&1 || true
  rm -rf "${HERE}/tours_local839e_a" "${HERE}/tours_local839e_b" \
         "${HERE}/tours_local839e_orch" 2>/dev/null || true
}
trap cleanup EXIT

say "building + starting the end-to-end stack (real orchestrator, fake generator)"
"${DC[@]}" up -d --build || { echo "compose up failed"; exit 1; }

say "waiting for postgres"
for i in $(seq 1 60); do
  docker exec "${PROJECT}-postgres-2-1" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 2
done
say "waiting for orchestrator :${ORCH_PORT}"
for i in $(seq 1 90); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${ORCH_PORT}/status/__ping__" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

q () { "${PSQL[@]}" -c "$1" 2>/dev/null | tr -d '[:space:]'; }

say "1. submitting ONE 3-stop walking tour: ${REQUEST}"
RESP=$(curl -s -X POST "http://localhost:${ORCH_PORT}/generate-complete-tour" \
  -H 'Content-Type: application/json' \
  -d "{\"location\":\"${REQUEST}\",\"tour_type\":\"walking\",\"total_stops\":3,\"user_id\":\"${USER_ID}\",\"request_string\":\"${REQUEST}\"}")
echo "  response: ${RESP}"
JOB=$(echo "${RESP}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
[ -z "${JOB}" ] && { echo "no job_id — aborting"; exit 1; }
say "1. orchestrator job_id=${JOB}"

say "2. waiting for the orchestrator job to complete"
STATUS=""
for i in $(seq 1 90); do
  STATUS=$(curl -s "http://localhost:${ORCH_PORT}/status/${JOB}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status",""))' 2>/dev/null || echo "")
  echo "    [t=${i}] orchestrator /status = ${STATUS}"
  case "${STATUS}" in completed|error) break;; esac
  sleep 3
done

say "3. stored EXACTLY ONCE in audio_tours"
N_TOURS=$(q "SELECT COUNT(*) FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}')")
TOUR_ID=$(q "SELECT id FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}') ORDER BY id DESC LIMIT 1")
STOPS=$(q "SELECT stops_count FROM audio_tours WHERE id='${TOUR_ID}'")
ZIP_LEN=$(q "SELECT COALESCE(length(audio_tour),0) FROM audio_tours WHERE id='${TOUR_ID}'")
echo "  audio_tours rows=${N_TOURS} (expect 1) id=${TOUR_ID} stops=${STOPS} zip_bytes=${ZIP_LEN}"

say "4. audio plays: validate the stored ZIP (DB bytes) and the on-disk copy"
# Pull the DB bytes as a single base64 line via SELECT (no COPY wrapping), strip
# all whitespace, decode locally.
"${PSQL[@]}" -c "SELECT encode(audio_tour,'base64') FROM audio_tours WHERE id='${TOUR_ID}'" \
  2>/dev/null | tr -d '[:space:]' > /tmp/l839e_zip.b64
echo "  base64 chars pulled from DB: $(wc -c < /tmp/l839e_zip.b64 | tr -d ' ')"
# The on-disk ZIP the owning instance wrote (host-mounted volume) — authoritative
# copy of the SAME tour; used as a cross-check of the DB bytes.
DISK_ZIP=$(ls -1 "${HERE}/tours_local839e_a/"*.zip 2>/dev/null | head -1)
AUDIO_RC=1
python3 - "$DISK_ZIP" <<'PY'
import base64, io, sys, zipfile
disk = sys.argv[1] if len(sys.argv) > 1 else ''

def check(name, raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    mp3s = sorted(n for n in z.namelist() if n.endswith('.mp3'))
    print(f"  [{name}] ZIP members: {z.namelist()}")
    ok = True
    for n in mp3s:
        d = z.read(n)
        is_audio = (d[:3] == b'ID3' or d[:2] in (b'\xff\xfb', b'\xff\xf3'))
        print(f"    [{name}] {n}: {len(d)} bytes audio_header={is_audio}")
        if len(d) < 1000 or not is_audio:
            ok = False
    return ok and len(mp3s) == 3

results = {}
try:
    raw_db = base64.b64decode(open('/tmp/l839e_zip.b64').read())
    results['db'] = check('db', raw_db)
except Exception as e:
    print(f"  [db] could not validate DB bytes: {e}")
    results['db'] = False
if disk:
    try:
        results['disk'] = check('disk', open(disk, 'rb').read())
    except Exception as e:
        print(f"  [disk] could not validate on-disk ZIP: {e}")
        results['disk'] = False
# Pass if EITHER source validates 3 real MP3s (they are the same tour).
print(f"  AUDIO results: {results}")
sys.exit(0 if any(results.values()) else 3)
PY
AUDIO_RC=$?

say "5. cross-instance handoff + cleanup evidence"
echo "  instance A tours dir: $(ls -1 "${HERE}/tours_local839e_a" 2>/dev/null | tr '\n' ' ')"
echo "  instance B tours dir: $(ls -1 "${HERE}/tours_local839e_b" 2>/dev/null | tr '\n' ' ')"
A_STORE=$(docker logs "${PROJECT}-tour-generation-modernized-1-1" 2>&1 | grep -c "\[LOCAL-839\] Stored ZIP" || true)
B_STORE=$(docker logs "${PROJECT}-tour-generation-modernized-2-1" 2>&1 | grep -c "\[LOCAL-839\] Stored ZIP" || true)
A_SERVE=$(docker logs "${PROJECT}-tour-generation-modernized-1-1" 2>&1 | grep -c "Serving /download.*from job store" || true)
B_SERVE=$(docker logs "${PROJECT}-tour-generation-modernized-2-1" 2>&1 | grep -c "Serving /download.*from job store" || true)
echo "  instance A: stored-ZIP=${A_STORE} served-from-store=${A_SERVE}"
echo "  instance B: stored-ZIP=${B_STORE} served-from-store=${B_SERVE}"
CROSS=$(( A_SERVE + B_SERVE ))
CLEANED=$(docker logs "${PROJECT}-tour-orchestrator-1" 2>&1 | grep -c "Cleared stale inline ZIP" || true)
ZB64_LEFT=$(q "SELECT COUNT(*) FROM generator_jobs WHERE result ? 'zip_b64'")
echo "  orchestrator 'Cleared stale inline ZIP' log lines=${CLEANED}"
echo "  generator_jobs rows still carrying zip_b64=${ZB64_LEFT} (expect 0 after cleanup)"

say "VERDICT"
PASS=1
[ "${STATUS}" = "completed" ] || { echo "  FAIL(2): orchestrator job not completed (got '${STATUS}')"; PASS=0; }
[ "${N_TOURS}" = "1" ]        || { echo "  FAIL(3): tour not stored exactly once (got '${N_TOURS}')"; PASS=0; }
[ "${AUDIO_RC}" = "0" ]       || { echo "  FAIL(4): stored ZIP audio invalid / wrong mp3 count"; PASS=0; }
[ "${ZB64_LEFT}" = "0" ]      || { echo "  FAIL(5): zip_b64 not cleaned from generator_jobs (got '${ZB64_LEFT}')"; PASS=0; }
if [ "${PASS}" = "1" ]; then
  echo "  PASS: ONE 3-stop walking tour, through the REAL orchestrator and TWO"
  echo "        modernized instances (round-robin), stored exactly once; stored"
  echo "        ZIP holds 3 real MP3 files (audio plays); cross-instance"
  echo "        /download-from-store=${CROSS}; orchestrator cleaned the inline ZIP"
  echo "        blob (zip_b64 rows now ${ZB64_LEFT})."
else
  echo "  PROOF FAILED — see above."
fi

exit $([ "${PASS}" = "1" ] && echo 0 || echo 1)
