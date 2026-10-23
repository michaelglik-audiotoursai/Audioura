#!/usr/bin/env bash
# run_local744_live.sh — LOCAL-744 isolated live run in a DISPOSABLE container
# (name: local744-gen; --rm; spare published port 5144; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-744 branch tree (so the screen-work
# disclosure + the existence-gate fix are in the image) and runs TWO FRESH PAID
# biking tours:
#   "the episode 1 of season 1 biking tour, Salem, MA"            (5 stops)
#   "the episode 1 of season 1 tour, Shreveport, Louisiana"       (5 stops)
#
# Metered + HARD-CAPPED at $1.00 for the WHOLE task by tests/live_run_meter.py
# with a RESERVE GATE before each tour. The container joins development_default
# ONLY to INSERT the delivered tours as additive is_test rows (lat/lng NULL) into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE (D141). Rows: additive is_test only.
#
# Usage: ./run_local744_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local744-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local744_live"
NET="development_default"
GEN="local744-gen"
PORT="5144"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local744_live.log"

cleanup() {
  echo "[local744] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local744] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local744] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local744_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local744_build.log; exit 1; }

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
  -e STOP_EXISTENCE_GATE_MODE=enforce
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local744_container.py:/app/run_local744_container.py:ro"
  -v "${HERE}/screen_work_tour.py:/app/screen_work_tour.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local744_container.py)

echo "[local744] ===== running Salem + Shreveport biking (5 each), task cap \$1.00 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-744 full log at ${LOG} ####################"
echo "[local744] key lines:"
grep -E "LOCAL744_TOUR_ID_|RESULT |ORIENTATION_OPENING|ORIENTATION_STATES|STOP TITLE|row count|spend for host|OUTCOME|LOCAL-744|DROPPED|VERIFIED|EXISTENCE-GATE" "${LOG}" || true
