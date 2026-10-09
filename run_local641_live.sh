#!/usr/bin/env bash
# run_local641_live.sh — LOCAL-641 isolated live run in a DISPOSABLE container
# (name: local641-gen; --rm; spare published port 5098; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-641 branch tree (so the _overall_from_new
# Stop-1 scoping fix and the neutralised fix_orientation_work_mismatch detector
# are in the image) and runs TWO FRESH 3-stop museum tours (The Courtauld Gallery
# / The National Gallery), metered + hard-capped at $1.30 COMBINED by
# tests/live_run_meter.py with a RESERVE GATE.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local641_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local641-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local641_live"
NET="development_default"
GEN="local641-gen"
PORT="5098"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local641_live.log"

cleanup() {
  echo "[local641] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local641] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local641] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local641_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local641_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.30
  -e TEST_GEMINI_MAX_USD=1.30
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local641_container.py:/app/run_local641_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
# Optional single-venue selector (LOCAL641_ONLY=NATIONAL_GALLERY) to run the
# second venue alone against the REMAINING combined budget.
[ -n "${LOCAL641_ONLY:-}" ] && args+=(-e "LOCAL641_ONLY=${LOCAL641_ONLY}")
args+=("${IMAGE}" python run_local641_container.py)

echo "[local641] ===== running 2 fresh museums (3 stops each, combined cap \$1.30) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-641 full log at ${LOG} ####################"
echo "[local641] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL641_TOUR_IDS?=" "${LOG}" || true
