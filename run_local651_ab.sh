#!/usr/bin/env bash
# run_local651_ab.sh — LOCAL-651 live A/B in a DISPOSABLE container
# (name: local651-gen; --rm; spare published port 5121; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from THIS branch tree (so fast_pipeline.py + the overlaps
# are in the image) and runs FOUR FRESH tours:
#   1. Courtauld 3 stops  FAST_PIPELINE OFF
#   2. Courtauld 3 stops  FAST_PIPELINE ON
#   3. Walters   3 stops  FAST_PIPELINE OFF
#   4. Walters   3 stops  FAST_PIPELINE ON
# Metered + HARD-CAPPED at $3.00 COMBINED by tests/live_run_meter.py with a
# RESERVE GATE before each tour. Joins development_default ONLY to INSERT each
# delivered tour as an additive is_test row into development-postgres-2-1. Tour
# cache OFF + stop pool OFF. Image + container removed at the end. No DELETE.
#
# Usage: ./run_local651_ab.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local651-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local651_ab"
NET="development_default"
GEN="local651-gen"
PORT="5121"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local651_ab.log"

cleanup() {
  echo "[local651] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local651] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local651] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local651_ab_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local651_ab_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=3.00
  -e TEST_GEMINI_MAX_USD=3.00
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local651_ab_container.py:/app/run_local651_ab_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local651_ab_container.py)

echo "[local651] ===== Courtauld(3) + Walters(3), OFF vs ON, combined cap \$3.00 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-651 A/B log at ${LOG} ####################"
echo "[local651] tour IDs + results + timing + call counts:"
grep -E "LOCAL651_TOUR_ID_|RESULT |OUTCOME |\[TIMING\]|\[TIMING-SUB\]   |\[detectors\]|\[paid_api_calls\]|\[cost\]|row count|spend for host" "${LOG}" || true
