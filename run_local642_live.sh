#!/usr/bin/env bash
# run_local642_live.sh — LOCAL-642 isolated live run in a DISPOSABLE container
# (name: local642-gen; --rm; a spare published port 5099; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-642 branch tree (so the flatten/dup fix is
# in the image) and runs ONE FRESH 3-stop museum tour (The National Gallery),
# metered + HARD-CAPPED at $0.90 by tests/live_run_meter.py with a RESERVE GATE.
#
# The container joins development_default ONLY to INSERT the delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image + container removed at the end. No DELETE. At most ONE tour.
#
# Usage: ./run_local642_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local642-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local642_live"
NET="development_default"
GEN="local642-gen"
PORT="5099"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local642_live.log"

cleanup() {
  echo "[local642] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local642] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local642] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local642_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local642_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=0.90
  -e TEST_GEMINI_MAX_USD=0.90
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local642_container.py:/app/run_local642_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local642_container.py)

echo "[local642] ===== running 1 fresh museum (National Gallery, 3 stops, cap \$0.90) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-642 full log at ${LOG} ####################"
echo "[local642] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL642_TOUR_ID_|RESULT " "${LOG}" || true
