#!/usr/bin/env bash
# run_local651_profile.sh — LOCAL-651 Step 1 PROFILE run in a DISPOSABLE
# container (name: local651-gen; --rm; spare published port 5121; NEVER an
# audioura-* service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from THIS branch tree (so the [TIMING-SUB] instrumentation
# is in the image) and runs ONE fresh Courtauld 3-stop tour, FAST_PIPELINE OFF,
# to produce the [TIMING-SUB] aggregate table.
#
# Metered + capped by tests/live_run_meter.py. The container joins
# development_default ONLY to INSERT the delivered tour as an additive is_test
# row into development-postgres-2-1. Cache OFF + stop pool OFF. Image + container
# removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local651_profile.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local651-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local651_profile"
NET="development_default"
GEN="local651-gen"
PORT="5121"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local651_profile.log"

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
  >/tmp/local651_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local651_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.50
  -e TEST_GEMINI_MAX_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local651_profile.py:/app/run_local651_profile.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local651_profile.py)

echo "[local651] ===== profiling Courtauld(3), FAST_PIPELINE OFF, cap \$1.50 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-651 profile log at ${LOG} ####################"
echo "[local651] phase + sub-step timing:"
grep -E "LOCAL651_PROFILE_TOUR_ID|OUTCOME|\[TIMING\]|\[TIMING-SUB\]|row count|spend for host" "${LOG}" || true
