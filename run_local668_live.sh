#!/usr/bin/env bash
# run_local668_live.sh — LOCAL-668 isolated live run in a DISPOSABLE container
# (name: local668-gen; --rm; spare published port 5168). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds Dockerfile.generator
# from the LOCAL-668 branch tree (so the five fixes are in the image) and runs the
# ticket tour FRESH in TWO arms:
#   Ho Chi Minh City Museum of Fine Arts, Vietnam (5 stops, museum)
#     NORMAL arm  — no NARRATION_MODEL / RESEARCH_BACKEND override
#     CHEAP arm   — NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper
#
# Metered + HARD-CAPPED at $1.40 for the WHOLE TASK by tests/live_run_meter.py
# with a RESERVE GATE before each arm. The container joins development_default
# ONLY to INSERT the delivered tours as additive is_test rows into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local668_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local668-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local668_live"
NET="development_default"
GEN="local668-gen"
PORT="5168"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local668_live.log"

cleanup() {
  echo "[local668] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local668] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local668] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local668_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local668_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.40
  -e TEST_GEMINI_MAX_USD=1.40
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local668_container.py:/app/run_local668_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local668_container.py)

echo "[local668] ===== running HCMC museum (5): NORMAL + CHEAP, task cap \$1.40 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-668 full log at ${LOG} ####################"
echo "[local668] key lines:"
grep -E "LOCAL668_TOUR_ID_|RESULT |STOP TITLE|ADDRESS:|SOURCES:|\[LOCAL-668|\[LOCAL-667|THIN-VERIFY|FALLBACK|BLOCKER4b|LOCAL-16 GATE|row count|spend for host|OUTCOME|\[cost\]|PASS|FAIL|verification queries" "${LOG}" || true