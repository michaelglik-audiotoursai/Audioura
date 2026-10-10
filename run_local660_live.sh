#!/usr/bin/env bash
# run_local660_live.sh — LOCAL-660 isolated live run in a DISPOSABLE container
# (name: local660-gen; --rm; spare published port 5120; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-660 branch tree (so the four defect fixes
# are in the image) and runs ONE FRESH PAID tour: Boston walking (5 stops).
#
# Metered + HARD-CAPPED at $1.00 for the WHOLE task by tests/live_run_meter.py
# with a RESERVE GATE before the tour. The container joins development_default
# ONLY to INSERT the delivered tour as an additive is_test row into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local660_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local660-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local660_live"
NET="development_default"
GEN="local660-gen"
PORT="5120"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local660_live.log"

cleanup() {
  echo "[local660] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local660] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local660] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local660_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local660_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.00
  -e TEST_GEMINI_MAX_USD=1.00
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local660_container.py:/app/run_local660_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local660_container.py)

echo "[local660] ===== running Boston walking (5), ONE paid tour, task cap \$1.00 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-660 full log at ${LOG} ####################"
echo "[local660] key lines:"
grep -E "LOCAL660_TOUR_ID_|RESULT |LOCAL-660\]|\[PASS\]|\[FAIL\]|row count|spend for host|OUTCOME|STORED|DIR:|STOP TITLE" "${LOG}" || true
