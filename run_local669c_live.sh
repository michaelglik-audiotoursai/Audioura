#!/usr/bin/env bash
# run_local669c_live.sh — LOCAL-669C isolated live run in a DISPOSABLE container
# (name: local669c-gen; --rm; spare published port 5171). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds
# Dockerfile.generator from the LOCAL-669C branch tree (so the final identity
# gate + the broadened highlights trigger + the bilingual titles are in the
# image) and runs the ticket tour FRESH on BOTH arms:
#   Ho Chi Minh City Museum of Fine Arts, Vietnam (5 stops, museum)
#   NORMAL arm (gpt-4.1 / Gemini grounded) then CHEAP arm (gpt-4.1-mini / Serper)
#
# Metered + HARD-CAPPED at $1.80 for the WHOLE 669C task (both arms combined) by
# tests/live_run_meter.py. The container joins development_default ONLY to
# INSERT the delivered tours as additive is_test rows into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local669c_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local669c-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local669c_live"
NET="development_default"
GEN="local669c-gen"
PORT="5171"          # spare published port (5170 was 669B's)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local669c_live.log"

cleanup() {
  echo "[local669c] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local669c] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local669c] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local669c_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local669c_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.80
  -e TEST_GEMINI_MAX_USD=1.80
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local669c_container.py:/app/run_local669c_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local669c_container.py)

echo "[local669c] ===== running HCMC museum (5): NORMAL then CHEAP, task cap \$1.80 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-669C full log at ${LOG} ####################"
echo "[local669c] key lines:"
grep -E "LOCAL669C_.*_TOUR_ID|OUTCOME|STOP TITLE|\[LOCAL-669C|\[LOCAL-669B|\[LOCAL-669\]|highlights:|grounded requests|row count|spend|breakdown|calls,|PASS|FAIL|\[cost\]|SUMMARY|TOTAL task spend" "${LOG}" || true
