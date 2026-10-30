#!/usr/bin/env bash
# run_local838_live.sh — LOCAL-838 isolated live run in a DISPOSABLE container
# under project "local838". NEVER an audioura-* container, never -p audioura,
# never the live DB. Spins up its OWN throwaway postgres (local838-postgres) and
# runs run_local838_container.py on the audioura-tour-generator image with the
# branch code bind-mounted.
#
# [LOCAL-820] THE METER CONTRACT — bind-mount the shared meterlog dir, write the
# canonical paid_api_calls.jsonl, install the meter via PYTHONPATH=/opt/meter,
# tag every row METER_SERVICE=LOCAL-838. The whole-task budget
# (TASK_BUDGET_ID/USD) refuses to start / aborts mid-run at $0.40.
#
# Usage: ./run_local838_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local838"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"   # host dir meter_report.py sweeps
mkdir -p "${METER_DIR}"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local838] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local838] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  -v "${HERE}/local778-initdb:/docker-entrypoint-initdb.d:ro" \
  postgres:15 >/dev/null

for i in $(seq 1 20); do
  if docker exec "${PG_NAME}" pg_isready -U admin -d audiotours >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[local838] waiting for initdb schema (audio_tours table)…"
for i in $(seq 1 60); do
  if docker exec "${PG_NAME}" psql -U admin -d audiotours -tAc \
       "SELECT to_regclass('public.audio_tours') IS NOT NULL" 2>/dev/null | grep -q t; then
    echo "[local838] schema ready after ${i}s"
    break
  fi
  sleep 1
done

args=(
  docker run --rm --name "${TG_NAME}"
  --memory 3g --cpus 2
  --network "${NET}"
)
# .env FIRST so our explicit -e below OVERRIDE it — DATABASE_URL must point at the
# throwaway postgres, never the live DB that .env may name.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(
  -e DATABASE_URL=postgresql://admin:password123@${PG_NAME}:5432/audiotours
  -e DB_HOST="${PG_NAME}" -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e STOP_EXISTENCE_GATE_MODE=log_only
  -e NARRATION_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e TASK_BUDGET_ID=LOCAL-838
  -e TASK_BUDGET_USD=0.40
  -e TEST_GEMINI_MAX_USD=0.40
  -e COST_HARD_LIMIT_USD=0.40
)
# [LOCAL-820] THE METER CONTRACT — keep these in sync with
# meter_container_env.docker_meter_args(task_id="LOCAL-838", ...).
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-838
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
# Optional, non-sensitive key tag (last few chars of the paid-API key, never the
# key): export METER_KEY_SUFFIX before running to line rows up with the provider
# usage page per key.
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local838_container.py)

echo "[local838] ===== running LOCAL-838 live, cap \$0.40, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-838 live run done (rc=${RC}) ####################"
echo "[local838] meter rows (service=LOCAL-838) now in ${METER_DIR}/paid_api_calls.jsonl"
exit "${RC}"
