#!/usr/bin/env bash
# run_local643_live.sh — LOCAL-643 isolated live run in a DISPOSABLE container
# (name: local643-gen; --rm; spare published port 5099; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-643 branch tree (so stop_records.py and the
# STRUCTURED_STOPS render wiring are in the image) and runs TWO FRESH 3-stop
# museum tours (The National Gallery / The Courtauld Gallery) with
# STRUCTURED_STOPS=1, metered + hard-capped at $1.50 COMBINED by
# tests/live_run_meter.py with a RESERVE GATE.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local643_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local643-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local643_live"
NET="development_default"
GEN="local643-gen"
PORT="5110"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local643_live.log"

cleanup() {
  echo "[local643] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local643] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local643] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local643_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local643_build.log; exit 1; }

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
  -e STRUCTURED_STOPS=1
  -e COST_HARD_LIMIT_USD=1.50
  -e TEST_GEMINI_MAX_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local643_container.py:/app/run_local643_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
# Optional single-venue selector (LOCAL643_ONLY=COURTAULD) to run the second
# venue alone against the REMAINING combined budget.
[ -n "${LOCAL643_ONLY:-}" ] && args+=(-e "LOCAL643_ONLY=${LOCAL643_ONLY}")
args+=("${IMAGE}" python run_local643_container.py)

echo "[local643] ===== running 2 fresh museums (3 stops each, STRUCTURED_STOPS=1, combined cap \$1.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-643 full log at ${LOG} ####################"
echo "[local643] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL643_TOUR_IDS?=" "${LOG}" || true
