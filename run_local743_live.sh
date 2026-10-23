#!/usr/bin/env bash
# run_local743_live.sh — LOCAL-743 isolated live run in a DISPOSABLE container
# (name: local743-gen; --rm; spare published port 5143; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-743 branch tree (so the heading-variant
# normalisation + field-label leak fix are in the image) and runs ONE FRESH PAID
# tour:
#   "the episode 1 of season 1 biking tour, Salem, MA" (5 stops, biking).
#
# Metered + HARD-CAPPED at $0.60 for the WHOLE task by tests/live_run_meter.py
# with a RESERVE GATE before the tour. The container joins development_default
# ONLY to INSERT the delivered tour as an additive is_test row into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE. Rows: additive is_test only.
#
# Usage: ./run_local743_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local743-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local743_live"
NET="development_default"
GEN="local743-gen"
PORT="5143"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local743_live.log"

cleanup() {
  echo "[local743] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local743] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local743] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local743_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local743_build.log; exit 1; }

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
  -v "${HERE}/run_local743_container.py:/app/run_local743_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local743_container.py)

echo "[local743] ===== running Salem biking (5), ONE paid tour, task cap \$0.60 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-743 full log at ${LOG} ####################"
echo "[local743] key lines:"
grep -E "LOCAL743_TOUR_ID_|RESULT |LOCAL-743|row count|spend for host|OUTCOME|STORED|cost\]" "${LOG}" || true
