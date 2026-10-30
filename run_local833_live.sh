#!/usr/bin/env bash
# run_local833_live.sh — LOCAL-833 live proof in an OWN compose project
# (-p local833), never the shared audioura-* containers, never the live DB.
#
# Proves a generator job that goes SILENT (its instance recycled mid-job — here
# simulated by `docker kill` of the generator) becomes TERMINAL and its
# orchestrator_jobs row goes terminal too, so the LOCAL-821/829 sweep stops
# re-taking it. This is the exact GCloud_Storied wave-9 defect (generator job
# ac864a08 stuck 'processing' forever, orchestrator_jobs 03ec8b1a never
# terminal, swept every cycle).
#
#   1. POST a 3-stop walking tour to /generate-complete-tour; the orchestrator
#      starts generation and persists generator_job_id on the durable record.
#      Record device_entitlement.fresh_used (the reserved pack unit).
#   2. KILL the GENERATOR mid-job (docker kill) — the generator_jobs row is left
#      'processing' with no further progress (the silent job).
#   3. Bring a FRESH generator up on the SAME DB. With GEN_JOB_STALE_SECONDS=30,
#      the silent row is > 30 s old, so the generator's stale rule flips it to
#      'error' (stale-on-read + the 15 s stale sweep).
#   4. PROVE:
#        (a) generator_jobs.status = 'error'  (generator side)
#        (b) orchestrator_jobs.status = 'error'  (durable record terminal)
#        (c) tour_requests.status = 'failed'  (request terminal)
#        (d) device_entitlement.fresh_used back to its pre-request value (refund)
#        (e) the sweep goes QUIET: the terminal row is never offered again
#            (no audio_tours row stored; orchestrator_jobs stays 'error').
#
# Budget: TASK_BUDGET_ID=LOCAL-833 TASK_BUDGET_USD=0.30, enforced by the
# generator/orchestrator env caps and recorded via the meter contract.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local833"
COMPOSE="docker-compose.local833-proof.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="/Users/micha/Audioura/.env"
export LOCAL833_METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${LOCAL833_METER_DIR}"

ORCH_PORT=55902
USER_ID="local821-tester"   # seeded by local821-initdb/03_local821_seed.sql (L3 pack)
REQUEST='Public art walk near Salem Common, Salem, MA'
PSQL=(docker exec -i -e PGPASSWORD=password123 "${PROJECT}-postgres-2-1" psql -U admin -d audiotours -tA)

say () { echo; echo "######## [local833] $* ########"; }

if [ -f "${ENV_FILE}" ]; then set -a; . "${ENV_FILE}"; set +a; fi

cleanup () {
  say "tearing down project ${PROJECT} (down -v — OWN volume only)"
  "${DC[@]}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "building + starting the isolated stack"
"${DC[@]}" up -d --build || { echo "compose up failed"; exit 1; }

say "waiting for postgres"
for i in $(seq 1 60); do
  docker exec "${PROJECT}-postgres-2-1" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 2
done
say "waiting for orchestrator :${ORCH_PORT}"
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${ORCH_PORT}/status/__ping__" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

q () { "${PSQL[@]}" -c "$1" 2>/dev/null | tr -d '[:space:]'; }

submit () {
  curl -s -X POST "http://localhost:${ORCH_PORT}/generate-complete-tour" \
    -H 'Content-Type: application/json' \
    -d "{\"location\":\"${REQUEST}\",\"tour_type\":\"walking\",\"total_stops\":3,\"user_id\":\"${USER_ID}\",\"request_string\":\"${REQUEST}\"}"
}

# ── 1. submit ──────────────────────────────────────────────────────────────
FRESH_BEFORE=$(q "SELECT COALESCE(fresh_used,0) FROM device_entitlement WHERE user_id='${USER_ID}'")
say "1. fresh_used BEFORE submit = ${FRESH_BEFORE}"
say "1. submitting 3-stop walking tour: ${REQUEST}"
RESP=$(submit)
echo "  response: ${RESP}"
JOB=$(echo "${RESP}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
[ -z "${JOB}" ] && { echo "no job_id — aborting"; exit 1; }
say "1. job_id=${JOB}"

# ── 2. wait until generation is in flight (generator_job_id persisted) ───────
say "2. waiting for generator_job_id to be persisted (generation in flight)"
GEN=""
for i in $(seq 1 60); do
  GEN=$(q "SELECT COALESCE(generator_job_id,'') FROM orchestrator_jobs WHERE job_id='${JOB}'")
  [ -n "${GEN}" ] && break
  sleep 2
done
echo "  generator_job_id=${GEN}"
FRESH_RESERVED=$(q "SELECT COALESCE(fresh_used,0) FROM device_entitlement WHERE user_id='${USER_ID}'")
echo "  fresh_used after reserve = ${FRESH_RESERVED} (expect ${FRESH_BEFORE} + 1)"
echo "  generator_jobs.status = $(q "SELECT status FROM generator_jobs WHERE job_id='${GEN}'")"

# ── 3. KILL the generator mid-job, then bring a FRESH one up on the same DB ──
say "3. KILLING the generator mid-job (docker kill) — the generator_jobs row goes silent"
docker kill "${PROJECT}-tour-generator-1" >/dev/null 2>&1 || docker kill $(docker ps -q -f "name=${PROJECT}-tour-generator") >/dev/null 2>&1 || true
sleep 3
docker ps -a --filter "name=${PROJECT}-tour-generator" --format '    {{.Names}} {{.Status}}'
echo "  generator_jobs.status right after kill = $(q "SELECT status FROM generator_jobs WHERE job_id='${GEN}'") (still 'processing' — silent)"

say "3. bringing a FRESH generator up on the SAME DB (so /status answers again; stale rule fires)"
"${DC[@]}" up -d tour-generator
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:55900/health" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

# ── 4a. generator side: the silent job becomes 'error' (stale) ───────────────
say "4a. waiting for the generator's stale rule to flip the silent job to 'error' (GEN_JOB_STALE_SECONDS=30)"
GEN_STATUS=""
for i in $(seq 1 40); do
  GEN_STATUS=$(q "SELECT status FROM generator_jobs WHERE job_id='${GEN}'")
  echo "    [t=${i}] generator_jobs.status=${GEN_STATUS}"
  [ "${GEN_STATUS}" = "error" ] && break
  sleep 3
done
echo "  generator_jobs row:"
"${PSQL[@]}" -c "SELECT job_id, status, error->>'error_code' AS code, LEFT(error->>'error',80) AS why FROM generator_jobs WHERE job_id='${GEN}'" 2>/dev/null

# ── 4b/c. orchestrator side: durable record + request go terminal ────────────
say "4b/c. waiting for orchestrator_jobs + tour_requests to go terminal"
ORCH_STATUS="" ; TR_STATUS=""
for i in $(seq 1 60); do
  ORCH_STATUS=$(q "SELECT status FROM orchestrator_jobs WHERE job_id='${JOB}'")
  TR_STATUS=$(q "SELECT status FROM tour_requests WHERE tour_id='${JOB}' AND source='orchestrator'")
  echo "    [t=${i}] orchestrator_jobs=${ORCH_STATUS} tour_requests=${TR_STATUS}"
  { [ "${ORCH_STATUS}" = "error" ] || [ "${ORCH_STATUS}" = "completed" ]; } && \
  { [ "${TR_STATUS}" = "failed" ] || [ "${TR_STATUS}" = "completed" ]; } && break
  sleep 5
done
echo "  orchestrator_jobs row:"
"${PSQL[@]}" -c "SELECT job_id, status, resume_attempts, LEFT(error,80) AS why FROM orchestrator_jobs WHERE job_id='${JOB}'" 2>/dev/null

# ── 4d. refund: fresh_used back to pre-request value ─────────────────────────
FRESH_AFTER=$(q "SELECT COALESCE(fresh_used,0) FROM device_entitlement WHERE user_id='${USER_ID}'")
say "4d. fresh_used AFTER failure = ${FRESH_AFTER} (expect ${FRESH_BEFORE} — pack unit refunded)"

# ── 4e. sweep goes quiet: observe several sweep cycles, row stays terminal ───
say "4e. observing the sweep for ~40 s — a terminal row must NOT be re-taken"
STABLE=1
for i in $(seq 1 8); do
  s=$(q "SELECT status FROM orchestrator_jobs WHERE job_id='${JOB}'")
  echo "    [t=${i}] orchestrator_jobs.status=${s}"
  [ "${s}" = "error" ] || [ "${s}" = "completed" ] || STABLE=0
  sleep 5
done
N_TOURS=$(q "SELECT COUNT(*) FROM audio_tours WHERE lower(request_string)=lower('${REQUEST}')")
echo "  stored audio_tours for this request = ${N_TOURS} (expect 0 — nothing was delivered)"
# Count how many times the sweep logged a resume ATTEMPT for this job after it
# went terminal; the resume-attempt cap + terminal row should keep this bounded.
RESUME_LOGS=$(docker logs "${PROJECT}-tour-orchestrator-1" 2>&1 | grep -c "resuming job ${JOB}" || true)
echo "  '[sweep] resuming job ${JOB}' log lines (bounded; cap=3) = ${RESUME_LOGS}"

# ── verdict ──────────────────────────────────────────────────────────────────
say "VERDICT"
PASS=1
[ "${GEN_STATUS}" = "error" ]   || { echo "  FAIL(4a): generator_jobs not 'error' (got '${GEN_STATUS}')"; PASS=0; }
[ "${ORCH_STATUS}" = "error" ]  || { echo "  FAIL(4b): orchestrator_jobs not terminal 'error' (got '${ORCH_STATUS}')"; PASS=0; }
[ "${TR_STATUS}" = "failed" ]   || { echo "  FAIL(4c): tour_requests not 'failed' (got '${TR_STATUS}')"; PASS=0; }
[ "${FRESH_AFTER}" = "${FRESH_BEFORE}" ] || { echo "  FAIL(4d): fresh_used not refunded (${FRESH_BEFORE} -> ${FRESH_AFTER})"; PASS=0; }
[ "${STABLE}" = "1" ]           || { echo "  FAIL(4e): row left terminal state during the sweep window"; PASS=0; }
[ "${N_TOURS}" = "0" ]          || { echo "  FAIL(4e): a tour was stored for a failed request (${N_TOURS})"; PASS=0; }
if [ "${PASS}" = "1" ]; then
  echo "  PASS: a silent generator job went 'error' (generator stale rule), the"
  echo "        orchestrator_jobs row went terminal 'error', tour_requests 'failed'"
  echo "        with the pack unit refunded, and the sweep stayed QUIET (no re-take,"
  echo "        no stored tour)."
else
  echo "  PROOF FAILED — see above."
fi

say "meter rows (service=LOCAL-833)"
grep -c 'LOCAL-833' "${LOCAL833_METER_DIR}/paid_api_calls.jsonl" 2>/dev/null || echo "  (no meter rows file yet)"

exit $([ "${PASS}" = "1" ] && echo 0 || echo 1)
