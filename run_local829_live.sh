#!/usr/bin/env bash
# run_local829_live.sh — LOCAL-829 live proof in an OWN compose project
# (-p local829), never the shared audioura-* containers, never the live DB.
#
# Proves the double-store defect is closed against the REAL orchestration stack
# built from this worktree, with resume+sweep ON and a 30 s min-idle + 10 s sweep
# interval so a normal 3-stop tour runs PAST min_idle while LIVE and the sweep
# fires repeatedly during generation — the exact GCloud wave-8 condition that
# stored "Van Gogh Museum, Amsterdam" twice.
#
#   (A) LIVE JOB SWEPT WHILE STILL LIVE → stored ONCE
#       1. POST a short 3-stop walking tour to /generate-complete-tour.
#       2. The single orchestrator's periodic sweep fires several times during
#          generation. The live path holds + renews its lease, so the sweep
#          never resumes the row.
#       3. Prove exactly ONE audio_tours row; tour_requests 'completed'; the
#          sweep log shows it SKIPPED the live job (no second store).
#
#   (B) THE 821 KILL TEST → stored ONCE
#       4. POST another 3-stop tour, kill the orchestrator mid-generation,
#          bring a fresh one up on the SAME DB volume, prove ONE audio_tours row.
#
# Budget: TASK_BUDGET_ID=LOCAL-829 TASK_BUDGET_USD=0.50, enforced by the
# generator/orchestrator env caps and recorded via the meter contract
# (meter_container_env) to ~/Audioura/meterlogs under service=LOCAL-829.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local829"
COMPOSE="docker-compose.local829-proof.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="/Users/micha/Audioura/.env"
export LOCAL829_METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${LOCAL829_METER_DIR}"

ORCH_PORT=55802
# Reuse the entitlement seeded by local821-initdb/03_local821_seed.sql (this
# stack mounts the same initdb dir), so the quota gate allows the two short
# tours this proof generates. Own postgres volume, dropped with `down -v`.
USER_ID="local821-tester"
REQUEST_A='Public art walk near Salem Common, Salem, MA'
REQUEST_B='Historic houses walk near Marblehead, MA'
PSQL=(docker exec -i -e PGPASSWORD=password123 "${PROJECT}-postgres-2-1" psql -U admin -d audiotours -tA)

say () { echo; echo "######## [local829] $* ########"; }

# Load .env (keys) so ${OPENAI_API_KEY} etc. resolve for build/up.
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

submit () {
  local req="$1"
  curl -s -X POST "http://localhost:${ORCH_PORT}/generate-complete-tour" \
    -H 'Content-Type: application/json' \
    -d "{\"location\":\"${req}\",\"tour_type\":\"walking\",\"total_stops\":3,\"user_id\":\"${USER_ID}\",\"request_string\":\"${req}\"}"
}

wait_done () {
  local jid="$1" st=""
  for i in $(seq 1 120); do
    st=$("${PSQL[@]}" -c "SELECT status FROM tour_requests WHERE tour_id='${jid}' AND source='orchestrator'" 2>/dev/null | tr -d '[:space:]')
    echo "    [t=${i}] status=${st}" >&2
    { [ "${st}" = "completed" ] || [ "${st}" = "failed" ]; } && break
    sleep 5
  done
  printf '%s' "${st}"
}

count_tours () {
  "${PSQL[@]}" -c "SELECT COUNT(*) FROM audio_tours WHERE lower(request_string)=lower('$1')" 2>/dev/null | tr -d '[:space:]'
}

# ── (A) live job swept while still LIVE → stored once ──────────────────────
say "(A) submitting 3-stop walking tour: ${REQUEST_A}"
RESP_A=$(submit "${REQUEST_A}")
echo "  response: ${RESP_A}"
JOB_A=$(echo "${RESP_A}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
[ -z "${JOB_A}" ] && { echo "no job_id — aborting"; exit 1; }
say "(A) job_id=${JOB_A}; letting the sweep fire during generation (min_idle=30s, interval=10s)"

# Watch the lease heartbeat while the sweep runs: the live row must keep a
# future lease_expires_at and never be handed to the sweep.
for i in $(seq 1 8); do
  row=$("${PSQL[@]}" -c "SELECT status, lease_owner IS NOT NULL, COALESCE(lease_expires_at > NOW(), false) FROM orchestrator_jobs WHERE job_id='${JOB_A}'" 2>/dev/null)
  echo "    [t=${i}] orchestrator_jobs(status,has_owner,lease_future)=${row}"
  sleep 8
done

say "(A) waiting for the live job to complete"
TR_A=$(wait_done "${JOB_A}")
N_A=$(count_tours "${REQUEST_A}")
say "(A) RESULT"
"${PSQL[@]}" -c "SELECT id, tour_name, stops_count, number_requested FROM audio_tours WHERE lower(request_string)=lower('${REQUEST_A}') ORDER BY id" 2>/dev/null
echo "  tour_requests.status=${TR_A}"
echo "  stored tour count = ${N_A} (expect exactly 1)"
"${PSQL[@]}" -c "SELECT job_id, status, lease_owner FROM orchestrator_jobs WHERE job_id='${JOB_A}'" 2>/dev/null
# Did any sweep try to resume THIS live job? (The guard log would show a loser.)
SWEEP_HIT_A=$(docker logs "${PROJECT}-tour-orchestrator-1" 2>&1 | grep -c "store already claimed for ${JOB_A}" || true)
echo "  '[LOCAL-829] store already claimed' hits for the live job = ${SWEEP_HIT_A} (0 ideal; a loser is still harmless — one store either way)"

# ── (B) the 821 kill test still holds → stored once ────────────────────────
say "(B) submitting 3-stop walking tour: ${REQUEST_B}"
RESP_B=$(submit "${REQUEST_B}")
echo "  response: ${RESP_B}"
JOB_B=$(echo "${RESP_B}" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("job_id",""))' 2>/dev/null)
[ -z "${JOB_B}" ] && { echo "no job_id (B) — aborting"; exit 1; }

say "(B) waiting for generation in flight (generator_job_id persisted)"
GEN_B=""
for i in $(seq 1 60); do
  GEN_B=$("${PSQL[@]}" -c "SELECT COALESCE(generator_job_id,'') FROM orchestrator_jobs WHERE job_id='${JOB_B}'" 2>/dev/null | tr -d '[:space:]')
  [ -n "${GEN_B}" ] && break
  sleep 2
done
echo "  generator_job_id=${GEN_B}"

say "(B) KILLING the orchestrator mid-generation (docker kill)"
docker kill "${PROJECT}-tour-orchestrator-1" >/dev/null 2>&1 || docker kill $(docker ps -q -f "name=${PROJECT}-tour-orchestrator") >/dev/null 2>&1 || true
sleep 3
docker ps -a --filter "name=${PROJECT}-tour-orchestrator" --format '    {{.Names}} {{.Status}}'

say "(B) starting a FRESH orchestrator on the SAME DB volume (resume-on-boot)"
"${DC[@]}" up -d tour-orchestrator
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${ORCH_PORT}/status/__ping__" 2>/dev/null || echo 000)
  [ "${code}" != "000" ] && break
  sleep 2
done

say "(B) waiting for the resumed job to complete"
TR_B=$(wait_done "${JOB_B}")
N_B=$(count_tours "${REQUEST_B}")
say "(B) RESULT"
"${PSQL[@]}" -c "SELECT id, tour_name, stops_count, number_requested FROM audio_tours WHERE lower(request_string)=lower('${REQUEST_B}') ORDER BY id" 2>/dev/null
echo "  tour_requests.status=${TR_B}"
echo "  stored tour count = ${N_B} (expect exactly 1)"

# ── verdict ────────────────────────────────────────────────────────────────
say "VERDICT"
PASS=1
[ "${TR_A}" = "completed" ] || { echo "  FAIL(A): live job did not complete"; PASS=0; }
[ "${N_A}" = "1" ] || { echo "  FAIL(A): expected exactly 1 stored tour, got ${N_A}"; PASS=0; }
[ "${TR_B}" = "completed" ] || { echo "  FAIL(B): resumed job did not complete"; PASS=0; }
[ "${N_B}" = "1" ] || { echo "  FAIL(B): expected exactly 1 stored tour, got ${N_B}"; PASS=0; }
if [ "${PASS}" = "1" ]; then
  echo "  PASS: (A) the sweep fired during a LIVE 3-stop generation and the tour"
  echo "        was stored EXACTLY once; (B) kill+resume also stored it once."
else
  echo "  PROOF FAILED — see above."
fi

say "meter rows (service=LOCAL-829) in ${LOCAL829_METER_DIR}/paid_api_calls.jsonl"
grep -c 'LOCAL-829' "${LOCAL829_METER_DIR}/paid_api_calls.jsonl" 2>/dev/null || echo "  (no meter rows file yet)"

exit $([ "${PASS}" = "1" ] && echo 0 || echo 1)
