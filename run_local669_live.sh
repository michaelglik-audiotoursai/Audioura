#!/usr/bin/env bash
# run_local669_live.sh — LOCAL-669 isolated live run in a DISPOSABLE container
# (name: local669-gen; --rm; spare published port 5169). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds Dockerfile.generator
# from the LOCAL-669 branch tree (so grounded_highlights + the wiring are in the
# image) and runs the ticket tour FRESH in TWO arms:
#   Ho Chi Minh City Museum of Fine Arts, Vietnam (5 stops, museum)
#     NORMAL arm  — no NARRATION_MODEL / RESEARCH_BACKEND override (Gemini grounded)
#     CHEAP arm   — NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper
#
# Metered + HARD-CAPPED at $1.20 for the WHOLE TASK by tests/live_run_meter.py
# with a RESERVE GATE before each arm. The container joins development_default
# ONLY to INSERT the delivered tours as additive is_test rows into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local669_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local669-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local669_live"
NET="development_default"
GEN="local669-gen"
PORT="5169"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local669_live.log"

cleanup() {
  echo "[local669] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local669] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local669] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local669_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local669_build.log; exit 1; }

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
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local669_container.py:/app/run_local669_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local669_container.py)

echo "[local669] ===== running HCMC museum (5): NORMAL + CHEAP, task cap \$1.20 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-669 full log at ${LOG} ####################"
echo "[local669] key lines:"
grep -E "LOCAL669_TOUR_ID_|RESULT |STOP TITLE|ADDRESS:|SOURCES:|\[LOCAL-669|\[LOCAL-667|THIN-VERIFY|FALLBACK|VERIFIED|highlights:|row count|spend for host|OUTCOME|\[cost\]|PASS|FAIL" "${LOG}" || true
