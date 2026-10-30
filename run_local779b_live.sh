#!/usr/bin/env bash
# run_local779b_live.sh — LOCAL-779B isolated live run in a DISPOSABLE container
# (name local779b-tg; NEVER an audioura-* container, never -p audioura). Runs ONE
# tour per container (index via $1) through the real generation path on the
# existing audioura-tour-generator image with the branch code bind-mounted.
#
# Usage: ./run_local779b_live.sh <0|1|2>
#   0 — "middle eastern restaurants near me, west Roxbury, MA" (2) DINING
#   1 — "Italian restaurants in the North End, Boston"         (3) DINING
#   2 — "walking tour: gyms near me, west Roxbury, MA"         (2) BUSINESS
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IDX="${1:-0}"
NAME="local779b-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
NET="development_default"
mkdir -p "${METER_DIR}"

PGENV=(-e PGPASSWORD=password123)
PSQL=(docker run --rm --network "${NET}" "${PGENV[@]}" postgres:15
      psql -h postgres-2 -U admin -d audiotours -tAc)

row_counts () {
  "${PSQL[@]}" "select count(*)||' total, '||count(*) filter (where is_test)||' is_test' from audio_tours;" 2>/dev/null
}

echo "[local779b] audio_tours BEFORE: $(row_counts)"

args=(
  docker run --rm --name "${NAME}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e DB_HOST=postgres-2 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e STOP_EXISTENCE_GATE_MODE=log_only
  -e TEST_GEMINI_MAX_USD=1.20
  -e COST_HARD_LIMIT_USD=1.20
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e PYTHONPATH=/opt/meter
  -e METER_SERVICE=LOCAL-779
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}:/app" -w /app
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(audioura-tour-generator python -u run_local779b_container.py "${IDX}")

echo "[local779b] ===== running tour index ${IDX} (cap \$1.20) ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "[local779b] audio_tours AFTER:  $(row_counts)"
echo "#################### LOCAL-779B tour ${IDX} done (rc=${RC}) ####################"
exit "${RC}"
