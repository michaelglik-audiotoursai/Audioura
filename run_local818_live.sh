#!/usr/bin/env bash
# run_local818_live.sh — LOCAL-818 isolated live run in a DISPOSABLE container
# under project "local818". NEVER an audioura-* container, never -p audioura,
# never the live DB. Spins up its OWN throwaway postgres (local818-postgres) and
# runs run_local818_container.py on the audioura-tour-generator image with the
# branch code bind-mounted.
#
# [LOCAL-820] THE METER CONTRACT. LOCAL-818's original run (see the docstring in
# run_local818_container.py) bind-mounted ONLY "$PWD":/app. It set neither a
# /meterlogs mount nor PAID_API_LOG, so the baked-in paid-API meter wrote its
# rows to /meterlogs INSIDE the --rm container and they died with it — the task's
# two live tours (01:31Z / 01:39Z Oct 30) left ZERO rows in ~/Audioura/meterlogs.
# This wrapper carries the canonical meter args (the exact argv
# meter_container_env.docker_meter_args() returns): bind-mount the shared
# meterlog dir, write the canonical paid_api_calls.jsonl, install the meter via
# PYTHONPATH=/opt/meter, and tag every row METER_SERVICE=<task id> (+ an optional
# non-sensitive key suffix) so meter_report.py sums this task's spend.
#
# tests/test_local820_meter_wiring.py asserts this wrapper (and every
# run_local*_container.py / the shared isolated_test.py) carries these args.
#
# Usage: ./run_local818_live.sh [0|1]     # optional single-tour index
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local818"
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

echo "[local818] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local818] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
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
  -e NARRATION_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e TASK_BUDGET_ID=LOCAL-818
  -e TASK_BUDGET_USD=0.70
  -e TEST_GEMINI_MAX_USD=0.70
  -e COST_HARD_LIMIT_USD=0.70
)
# [LOCAL-820] THE METER CONTRACT — the canonical args from
# meter_container_env.docker_meter_args(task_id="LOCAL-818", meter_dir=_meter,
# host_meter_dir=~/Audioura/meterlogs, key_suffix=<last-4-of-key>). Keep these in
# sync with that helper; the guard test fails if any are missing.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-818
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
# Optional, non-sensitive key tag (last few chars of the paid-API key, never the
# key): export METER_KEY_SUFFIX before running to line rows up with the provider
# usage page per key.
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local818_container.py)
[ -n "${1:-}" ] && args+=("$1")

echo "[local818] ===== running LOCAL-818 live, cap \$0.70, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-818 live run done (rc=${RC}) ####################"
echo "[local818] meter rows (service=LOCAL-818) now in ${METER_DIR}/paid_api_calls.jsonl"
exit "${RC}"
