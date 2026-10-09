#!/usr/bin/env bash
# run_local650_live.sh — LOCAL-650B isolated live run in a DISPOSABLE container
# (name: local650b-gen; --rm; spare published port 5116; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-650B branch tree (theme_stop_guard
# selection-time detectors, walking_directions_guard with verified-coords-only
# distances, current_affairs_coverage, the directions_generator target guard,
# the PHASE 3A + GEO-CHECK theme constraint) and runs TWO FRESH tours:
#   1. Boston walking (5 stops) — the evidence tour (557): no theme-phrase stop
#      (rejected at SELECTION), directions lead to the NEXT stop, distances only
#      from verified P625 coords, current-affairs honesty.
#   2. The Courtauld Gallery museum canary (3 stops) — the museum path must not
#      change (0 directions missing, no run-on header, LOCAL-650B guards no-op).
# Metered + HARD-CAPPED at $1.20 COMBINED by tests/live_run_meter.py with a
# RESERVE GATE before each tour.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image + container removed at the end. No DELETE. Rows: additive
# is_test only.
#
# Usage: ./run_local650_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local650b-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local650b_live"
NET="development_default"
GEN="local650b-gen"
PORT="5116"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local650_live.log"

cleanup() {
  echo "[local650] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local650] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local650] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local650_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local650_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -p "${PORT}:5000"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e COST_HARD_LIMIT_USD=1.20
  -e TEST_GEMINI_MAX_USD=1.20
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local650_container.py:/app/run_local650_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local650_container.py)

echo "[local650] ===== running Boston walking (5) + Courtauld museum (3), combined cap \$1.20 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-650B full log at ${LOG} ####################"
echo "[local650b] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL650_TOUR_ID_|RESULT |WALKING RESULT|MUSEUM RESULT|FIX1|FIX2|FIX3|LOCAL-650B" "${LOG}" || true
