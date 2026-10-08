#!/usr/bin/env bash
# run_local634_live.sh — LOCAL-634 isolated live run in a DISPOSABLE container
# (name: local634-gen; --rm; spare published port 5099; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-634 branch tree (so the dropped-word
# editor reject+repair, the unseen-work callback guard, the title-line guard, the
# provenance-sentence namesake guard, the reserve-capture and the text-level
# dangling-opener guard are all in the image) and runs TWO FRESH 3-stop museum
# tours (Courtauld / Reina Sofia), metered + hard-capped at $1.30 COMBINED by
# tests/live_run_meter.py.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local634_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local634-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local634_live"
NET="development_default"
GEN="local634-gen"
PORT="5099"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local634_live.log"

cleanup() {
  echo "[local634] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local634] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local634] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local634_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local634_build.log; exit 1; }

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
  -e STOP_EDITOR=1
  -e COST_HARD_LIMIT_USD=1.30
  -e TEST_GEMINI_MAX_USD=1.30
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local634_container.py:/app/run_local634_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local634_container.py)

echo "[local634] ===== running 2 fresh museums (3 stops each, combined cap \$1.30) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-634 full log at ${LOG} ####################"
echo "[local634] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL634_TOUR_IDS?=" "${LOG}" || true
