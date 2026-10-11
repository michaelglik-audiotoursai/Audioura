#!/usr/bin/env bash
# run_local669b_live.sh — LOCAL-669B isolated live run in a DISPOSABLE container
# (name: local669b-gen; --rm; spare published port 5170). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds
# Dockerfile.generator from the LOCAL-669B branch tree (so identity_dedup +
# the highlights-first wiring are in the image) and runs the ticket tour FRESH,
# NORMAL ARM ONLY:
#   Ho Chi Minh City Museum of Fine Arts, Vietnam (5 stops, museum)
#
# Metered + HARD-CAPPED at $1.10 for the WHOLE 669B (ONE paid tour) by
# tests/live_run_meter.py. The container joins development_default ONLY to
# INSERT the delivered tour as an additive is_test row into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local669b_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local669b-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local669b_live"
NET="development_default"
GEN="local669b-gen"
PORT="5170"          # spare published port (5169 was 669's)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local669b_live.log"

cleanup() {
  echo "[local669b] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local669b] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local669b] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local669b_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local669b_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.10
  -e TEST_GEMINI_MAX_USD=1.10
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local669b_container.py:/app/run_local669b_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local669b_container.py)

echo "[local669b] ===== running HCMC museum (5): NORMAL only, task cap \$1.10 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-669B full log at ${LOG} ####################"
echo "[local669b] key lines:"
grep -E "LOCAL669B_TOUR_ID|OUTCOME|STOP TITLE|SOURCES:|\[LOCAL-669B|\[LOCAL-669|THIN-VERIFY|FALLBACK|VERIFIED|highlights:|grounded requests|row count|spend|breakdown|calls,|PASS|FAIL|\[cost\]" "${LOG}" || true
