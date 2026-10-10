#!/usr/bin/env bash
# run_local663_live.sh — LOCAL-663 isolated live run in a DISPOSABLE container
# (name: local663-gen; --rm; spare published port 5121; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-663 branch tree (so both fixes are in the
# image) and runs ONE FRESH PAID tour: Boston walking (5 stops).
#
# Metered + HARD-CAPPED at $0.60 for the WHOLE task by tests/live_run_meter.py
# with a RESERVE GATE before the tour. The container joins development_default
# ONLY to INSERT the delivered tour as an additive is_test row into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local663_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local663-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local663_live"
NET="development_default"
GEN="local663-gen"
PORT="5121"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local663_live.log"

cleanup() {
  echo "[local663] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local663] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local663] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local663_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local663_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=0.60
  -e TEST_GEMINI_MAX_USD=0.60
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local663_container.py:/app/run_local663_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local663_container.py)

echo "[local663] ===== running Boston walking (5), ONE paid tour, task cap \$0.60 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-663 full log at ${LOG} ####################"
echo "[local663] key lines:"
grep -E "LOCAL663_TOUR_ID_|RESULT |LOCAL-663\]|\[PASS\]|\[FAIL\]|row count|spend for host|OUTCOME|STORED|STOP TITLE|\[cost\]" "${LOG}" || true
