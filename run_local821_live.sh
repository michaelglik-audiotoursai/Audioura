#!/usr/bin/env bash
# run_local821_live.sh — LOCAL-821 live proof in an OWN compose project
# (-p local821), never the shared audioura-* containers, never the live DB.
#
# Proves BOTH halves of LOCAL-821 against the REAL orchestration stack built
# from this worktree:
#
#   (A) RESUME AFTER SIGTERM/teardown
#       1. POST a short 3-stop walking tour to /generate-complete-tour.
#       2. Wait until generation is in flight (generator job running), then
#          `docker kill` the orchestrator — the exact teardown that lost tour 279.
#       3. Bring a FRESH orchestrator up on the SAME postgres volume. With
#          ORCH_RESUME_ENABLED=true it re-attaches to the already-running /
#          finished generator job (orchestrator_jobs + generator_jobs) and
#          finishes the tour.
#       4. Prove the tour is stored EXACTLY once (one audio_tours row;
#          tour_requests 'completed').
#
#   (B) IDENTICAL REQUEST NEVER OVERWRITES
#       5. Capture the stored tour's content+stops, POST the IDENTICAL request
#          again, and prove the first tour's content/stops are UNCHANGED
#          (cache hit, number_requested incremented), never rewritten.
#
# Budget: TASK_BUDGET_ID=LOCAL-821 TASK_BUDGET_USD=0.60, enforced by the
# generator/orchestrator env caps and recorded via the meter contract
# (meter_container_env) to ~/Audioura/meterlogs under service=LOCAL-821.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local821"
COMPOSE="docker-compose.local821-proof.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="/Users/micha/Audioura/.env"
export LOCAL821_METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${LOCAL821_METER_DIR}"

ORCH_PORT=55102
USER_ID="local821-tester"
REQUEST='Public art walk near Salem Common, Salem, MA'
PSQL=(docker exec -i "${PROJECT}-postgres-2-1" psql -U admin -d audiotours -tA)

say () { echo; echo "######## [local821] $* ########"; }

# Load .env (keys) for the build/up so ${OPENAI_API_KEY} etc. resolve.
if [ -f "${ENV_FILE}" ]; then set -a; . "${ENV_FILE}"; set +a; fi

cleanup () {
  say "tearing down project ${PROJECT} (down -v — OWN volume only)"
  "${DC[@]}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "building + starting the isolated stack"
"${DC[@]}" up -d --build || { echo "compose up failed"; exit 1; }

# Wait for postgres + orchestrator health.
say "waiting for postgres"
for i in $(seq 1 60); do
  docker exec "${PROJECT}-postgres-2-1" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 2
done
say "waiting for orchestrator :${ORCH_PORT}"
for i in $(seq 1 60); do
  curl -sf "http://localhost:${ORCH_PORT}/status/__ping__" >/dev/null 2>&1 && break || true
  # /status/<id> returns 404 for unknown id, which still means the app is up.
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${ORCH_PORT}/status/__ping__" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

# ── (A) submit, kill mid-generation, resume ────────────────────────────────
say "(A) submitting 3-stop walking tour"
RESP=$(curl -s -X POST "http://localhost:${ORCH_PORT}/generate-complete-tour" \
  -H 'Content-Type: application/json' \
  -d "{\"location\":\"${REQUEST}\",\"tour_type\":\"walking\",\"total_stops\":3,\"user_id\":\"${USER_ID}\",\"request_string\":\"${REQUEST}\"}")
echo "  response: ${RESP}"
JOB_ID=$(echo "${RESP}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
if [ -z "${JOB_ID}" ]; then echo "no job_id — aborting"; exit 1; fi
say "job_id=${JOB_ID}"

# Wait until the generator job id is persisted (generation is really in flight),
# then kill the orchestrator. Poll orchestrator_jobs for generator_job_id.
say "(A) waiting for generation to be in flight (generator_job_id persisted)"
GEN_JID=""
for i in $(seq 1 60); do
  GEN_JID=$("${PSQL[@]}" -c "SELECT COALESCE(generator_job_id,'') FROM orchestrator_jobs WHERE job_id='${JOB_ID}'" 2>/dev/null | tr -d '[:space:]')
  [ -n "${GEN_JID}" ] && break
  sleep 2
done
echo "  generator_job_id=${GEN_JID}"
ORCH_STATUS=$("${PSQL[@]}" -c "SELECT status FROM orchestrator_jobs WHERE job_id='${JOB_ID}'" 2>/dev/null | tr -d '[:space:]')
echo "  orchestrator_jobs.status=${ORCH_STATUS}"

say "(A) KILLING the orchestrator mid-generation (docker kill) — simulating SIGKILL teardown"
docker kill "${PROJECT}-tour-orchestrator-1" >/dev/null 2>&1 || docker kill $(docker ps -q -f "name=${PROJECT}-tour-orchestrator") >/dev/null 2>&1 || true
sleep 3
echo "  orchestrator container state:"
docker ps -a --filter "name=${PROJECT}-tour-orchestrator" --format '    {{.Names}} {{.Status}}'

# tour_requests should still be 'started' (not completed) right after the kill.
TR_AFTER_KILL=$("${PSQL[@]}" -c "SELECT status FROM tour_requests WHERE tour_id='${JOB_ID}' AND source='orchestrator'" 2>/dev/null | tr -d '[:space:]')
echo "  tour_requests.status after kill = ${TR_AFTER_KILL}"

say "(A) starting a FRESH orchestrator on the SAME DB volume (resume-on-boot)"
"${DC[@]}" up -d tour-orchestrator
# Wait for the fresh orchestrator to come up and run its resume/sweep.
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${ORCH_PORT}/status/__ping__" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

say "(A) waiting for the resumed job to complete (tour_requests -> completed)"
TR_FINAL=""
for i in $(seq 1 120); do
  TR_FINAL=$("${PSQL[@]}" -c "SELECT status FROM tour_requests WHERE tour_id='${JOB_ID}' AND source='orchestrator'" 2>/dev/null | tr -d '[:space:]')
  echo "    [t=${i}] tour_requests.status=${TR_FINAL}"
  [ "${TR_FINAL}" = "completed" ] && break
  [ "${TR_FINAL}" = "failed" ] && break
  sleep 5
done

say "(A) RESULT — audio_tours rows for this request"
"${PSQL[@]}" -c "SELECT id, tour_name, stops_count, number_requested, LENGTH(tour_content) AS content_len FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}') ORDER BY id" 2>/dev/null
N_TOURS=$("${PSQL[@]}" -c "SELECT COUNT(*) FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}')" 2>/dev/null | tr -d '[:space:]')
echo "  stored tour count = ${N_TOURS} (expect exactly 1)"
echo "  orchestrator_jobs final:"
"${PSQL[@]}" -c "SELECT job_id, generator_job_id, status, lease_owner FROM orchestrator_jobs WHERE job_id='${JOB_ID}'" 2>/dev/null

# Capture the stored tour's content hash + stops for the (B) unchanged proof.
TOUR_ID=$("${PSQL[@]}" -c "SELECT id FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}') ORDER BY id LIMIT 1" 2>/dev/null | tr -d '[:space:]')
BEFORE_HASH=$("${PSQL[@]}" -c "SELECT md5(COALESCE(tour_content,'')) FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
BEFORE_STOPS=$("${PSQL[@]}" -c "SELECT COALESCE(stops_count,-1) FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
BEFORE_NREQ=$("${PSQL[@]}" -c "SELECT number_requested FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
echo "  tour ${TOUR_ID}: content md5=${BEFORE_HASH} stops=${BEFORE_STOPS} number_requested=${BEFORE_NREQ}"

# ── (B) identical request must not overwrite ───────────────────────────────
say "(B) submitting the IDENTICAL request again"
RESP2=$(curl -s -X POST "http://localhost:${ORCH_PORT}/generate-complete-tour" \
  -H 'Content-Type: application/json' \
  -d "{\"location\":\"${REQUEST}\",\"tour_type\":\"walking\",\"total_stops\":3,\"user_id\":\"${USER_ID}\",\"request_string\":\"${REQUEST}\"}")
echo "  response: ${RESP2}"
JOB_ID2=$(echo "${RESP2}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
say "(B) waiting for the second request to finish"
for i in $(seq 1 120); do
  st=$("${PSQL[@]}" -c "SELECT status FROM tour_requests WHERE tour_id='${JOB_ID2}' AND source='orchestrator'" 2>/dev/null | tr -d '[:space:]')
  echo "    [t=${i}] second request status=${st}"
  { [ "${st}" = "completed" ] || [ "${st}" = "failed" ]; } && break
  sleep 5
done

say "(B) RESULT — the ORIGINAL tour must be byte-for-byte unchanged"
AFTER_HASH=$("${PSQL[@]}" -c "SELECT md5(COALESCE(tour_content,'')) FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
AFTER_STOPS=$("${PSQL[@]}" -c "SELECT COALESCE(stops_count,-1) FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
AFTER_NREQ=$("${PSQL[@]}" -c "SELECT number_requested FROM audio_tours WHERE id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
N_VERS=$("${PSQL[@]}" -c "SELECT COUNT(*) FROM audio_tour_versions WHERE tour_id=${TOUR_ID}" 2>/dev/null | tr -d '[:space:]')
echo "  before: md5=${BEFORE_HASH} stops=${BEFORE_STOPS} nreq=${BEFORE_NREQ}"
echo "  after : md5=${AFTER_HASH} stops=${AFTER_STOPS} nreq=${AFTER_NREQ}"
echo "  audio_tour_versions for tour ${TOUR_ID} = ${N_VERS} (expect 0 — no replacement)"
"${PSQL[@]}" -c "SELECT id, tour_name, stops_count, number_requested FROM audio_tours WHERE lower(request_string) LIKE lower('${REQUEST}%') ORDER BY id" 2>/dev/null

say "VERDICT"
PASS=1
[ "${TR_FINAL}" = "completed" ] || { echo "  FAIL(A): resumed job did not complete"; PASS=0; }
[ "${N_TOURS}" = "1" ] || { echo "  FAIL(A): expected exactly 1 stored tour, got ${N_TOURS}"; PASS=0; }
[ "${BEFORE_HASH}" = "${AFTER_HASH}" ] && [ -n "${BEFORE_HASH}" ] || { echo "  FAIL(B): tour content changed after identical request"; PASS=0; }
[ "${BEFORE_STOPS}" = "${AFTER_STOPS}" ] || { echo "  FAIL(B): stop count changed after identical request"; PASS=0; }
[ "${N_VERS}" = "0" ] || { echo "  FAIL(B): a version was archived — the tour was replaced"; PASS=0; }
if [ "${PASS}" = "1" ]; then
  echo "  PASS: (A) killed mid-generation, fresh orchestrator resumed and stored the tour ONCE;"
  echo "        (B) identical request left the tour byte-for-byte unchanged (cache hit, nreq ${BEFORE_NREQ}->${AFTER_NREQ})."
else
  echo "  PROOF FAILED — see above."
fi

say "meter rows (service=LOCAL-821) in ${LOCAL821_METER_DIR}/paid_api_calls.jsonl"
grep -c 'LOCAL-821' "${LOCAL821_METER_DIR}/paid_api_calls.jsonl" 2>/dev/null || echo "  (no meter rows file yet)"

exit $([ "${PASS}" = "1" ] && echo 0 || echo 1)
