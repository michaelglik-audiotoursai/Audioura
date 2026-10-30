#!/usr/bin/env bash
# run_local801_live.sh — LOCAL-801 isolated live run in DISPOSABLE containers
# under project "local801". NEVER an audioura-* container, never -p audioura,
# never the live DB. Spins up its OWN throwaway postgres (local801-postgres) and
# runs the TWO P1-flagged requests (Freedom Trail 5-stop walking; JP coffee
# 3-stop restaurant) through the real generation path on the existing
# audioura-tour-generator image with the LOCAL-801 branch code bind-mounted.
#
# DEFAULT ARM: no NARRATION_MODEL / TOUR_LLM_MODEL override (the gpt-4.1 cloud
# setting that produced the defects). RESEARCH_BACKEND=serper because Gemini
# prepaid credit is DEPLETED (LEAD 2026-10-28). HARD CAP $1.50 combined.
#
# Usage: ./run_local801_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local801"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${METER_DIR}"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local801] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local801] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
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
  -e RESEARCH_BACKEND=serper
  -e TEST_GEMINI_MAX_USD=1.50
  -e COST_HARD_LIMIT_USD=1.50
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e PYTHONPATH=/opt/meter
  -e METER_SERVICE=LOCAL-801
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}:/app" -w /app
)
# NOTE: deliberately NO -e TOUR_LLM_MODEL / NARRATION_MODEL — DEFAULT arm.
args+=(audioura-tour-generator:latest python -u run_local801_container.py)

echo "[local801] ===== running Freedom Trail (5) + JP coffee (3), DEFAULT arm, cap \$1.50 ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-801 live run done (rc=${RC}) ####################"
exit "${RC}"
