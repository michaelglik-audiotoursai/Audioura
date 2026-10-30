#!/usr/bin/env bash
# run_local799_live.sh — LOCAL-799 isolated live run in DISPOSABLE containers
# under project "local799". NEVER an audioura-* container, never -p audioura,
# never the live DB. Spins up its OWN throwaway postgres (local799-postgres) and
# runs ONE tour (the exact tour-467 request) through the real generation path on
# the existing audioura-tour-generator image with the branch code bind-mounted.
#
# Usage: ./run_local799_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local799"
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

echo "[local799] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local799] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  postgres:15 >/dev/null

# Give postgres a moment to accept connections (area-cache reads/writes are
# non-fatal, but a reachable empty DB keeps the log clean).
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
  -e TEST_GEMINI_MAX_USD=1.00
  -e COST_HARD_LIMIT_USD=1.00
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e PYTHONPATH=/opt/meter
  -e METER_SERVICE=LOCAL-799
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}:/app" -w /app
)
args+=(audioura-tour-generator:latest python -u run_local799_container.py)

echo "[local799] ===== running tour-467 request (cap \$1.00) ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-799 live run done (rc=${RC}) ####################"
exit "${RC}"
