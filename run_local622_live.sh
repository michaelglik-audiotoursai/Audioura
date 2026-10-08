#!/usr/bin/env bash
# run_local622_live.sh — LOCAL-622 isolated live run in a DISPOSABLE container
# (name: local622-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-622 branch tree (so the external-lookup
# budget + the generator-side /cancel + status changes are all in the image) and
# runs ONE fresh 5-stop Kunsthaus Zürich tour, metered + hard-capped at $1.00 by
# tests/live_run_meter.py.
#
# After the run it prints:
#   * the engine [TIMING] TOTAL line (external_lookups is auditable), and
#   * the paid_api_calls totals for THIS container's host:
#         SELECT ... FROM paid_api_calls WHERE host = '<container hostname>'
#
# The container joins development_default ONLY to INSERT the delivered tour as an
# additive is_test row into development-postgres-2-1 and to read the meter table.
# It does NOT use the stack's generator service. Tour cache OFF. Image removed at
# the end. No DELETE.
#
# Usage: ./run_local622_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local622-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local622_live"
NET="development_default"
GEN="local622-gen"
PG="development-postgres-2-1"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local622_live.log"

cleanup() {
  echo "[local622] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local622] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local622] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local622_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local622_build.log; exit 1; }

# Fixed container hostname so the paid_api_calls host filter is deterministic.
HOSTNAME_622="local622gen"

args=(
  docker run --rm --name "${GEN}" --hostname "${HOSTNAME_622}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e COST_HARD_LIMIT_USD=1.00
  -e TEST_GEMINI_MAX_USD=1.00
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local622_container.py:/app/run_local622_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local622_container.py)

echo "[local622] ===== running Kunsthaus Zürich (5 stops, cap \$1.00) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-622 TIMING ####################"
grep -E "\[TIMING\] TOTAL|LOOKUP-BUDGET|LOCAL-622\] OSM lookup budget" "${LOG}" || true

echo ""
echo "#################### paid_api_calls (host=${HOSTNAME_622}) ####################"
docker exec "${PG}" psql -U admin -d audiotours -c \
  "SELECT service, kind, count(*) AS calls, round(sum(usd),4) AS usd
     FROM paid_api_calls WHERE host = '${HOSTNAME_622}'
     GROUP BY service, kind ORDER BY usd DESC;" 2>&1 || true
docker exec "${PG}" psql -U admin -d audiotours -c \
  "SELECT count(*) AS total_calls, round(sum(usd),4) AS total_usd
     FROM paid_api_calls WHERE host = '${HOSTNAME_622}';" 2>&1 || true

echo ""
echo "#################### LOCAL-622 full log at ${LOG} ####################"
grep -E "LOCAL622_TOUR_ID=" "${LOG}" || true
