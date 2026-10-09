#!/usr/bin/env bash
# run_local655_live.sh — LOCAL-655 isolated live run in a DISPOSABLE container
# (name: local655-gen; --rm; spare published port 5117; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-655 branch tree (so current_affairs_news.py
# and the delivery-time news pass are in the image) and runs TWO FRESH tours:
#   1. Boston walking (5 stops) — the ticket tour (557 class). Must SEARCH the
#      news (query log) and inject dated/attributed/balanced items, or append the
#      honest note only if nothing usable was found.
#   2. The Courtauld Gallery museum canary (3 stops) — the news pass must be a
#      strict NO-OP (no search, no "In recent news:", no honest note).
# Metered + HARD-CAPPED at $1.20 for the WHOLE TASK by tests/live_run_meter.py
# with a RESERVE GATE before each tour.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1. Tour cache OFF + stop pool
# OFF (fresh). Image + container removed at the end. No DELETE. Rows: additive
# is_test only.
#
# Usage: ./run_local655_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local655-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local655_live"
NET="development_default"
GEN="local655-gen"
PORT="5117"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local655_live.log"

cleanup() {
  echo "[local655] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local655] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local655] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local655_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local655_build.log; exit 1; }

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
  -v "${HERE}/run_local655_container.py:/app/run_local655_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local655_container.py)

echo "[local655] ===== running Boston walking (5) + Courtauld museum (3), task cap \$1.20 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-655 full log at ${LOG} ####################"
echo "[local655] tour IDs + news summary (for critique.sh / detectors.py):"
grep -E "LOCAL655_TOUR_ID_|RESULT |WALKING RESULT|NEWS ITEM|NEWS search|query:|CANARY|honest note" "${LOG}" || true
