#!/usr/bin/env bash
# run_local826_live.sh — LOCAL-826 isolated live run in DISPOSABLE containers
# under project "local826". NEVER an audioura-* container, never the live/shared
# DB. Spins up its OWN throwaway postgres (local826-postgres) and runs
# run_local826_container.py on the audioura-tour-generator image with the branch
# code bind-mounted. Cheap museum arm, DISABLE_STOP_POOL=1, two tours, hard cap
# $0.90.
#
# THE METER CONTRACT (LOCAL-819/820): canonical args — bind-mount the shared
# meterlog dir, write the canonical paid_api_calls.jsonl, install the meter via
# PYTHONPATH=/opt/meter, tag every row METER_SERVICE=LOCAL-826. TASK_BUDGET_ID/
# TASK_BUDGET_USD arm the LOCAL-817 budget and (LOCAL-822) the meter mount guard.
#
# Usage: ./run_local826_live.sh [0|1]     # optional single-tour index
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local826"
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

echo "[local826] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local826] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  postgres:15 >/dev/null

for i in $(seq 1 20); do
  if docker exec "${PG_NAME}" pg_isready -U admin -d audiotours >/dev/null 2>&1; then
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
  -e CHEAP_ARM_CATEGORIES=museum
  -e NARRATION_MODEL=gpt-4.1-mini
  -e SERPER_RESEARCH_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e SERP_PROVIDER=serper
  -e TASK_BUDGET_ID=LOCAL-826
  -e TASK_BUDGET_USD=0.90
  -e TEST_GEMINI_MAX_USD=0.90
  -e COST_HARD_LIMIT_USD=0.90
)
# [LOCAL-820] THE METER CONTRACT — canonical args (keep in sync with
# meter_container_env.docker_meter_args).
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-826
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local826_container.py)
[ -n "${1:-}" ] && args+=("$1")

echo "[local826] ===== running LOCAL-826 live, cap \$0.90, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-826 live run done (rc=${RC}) ####################"
echo "[local826] meter rows (service=LOCAL-826) now in ${METER_DIR}/paid_api_calls.jsonl"
exit "${RC}"
