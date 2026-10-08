#!/usr/bin/env bash
# run_local630_live.sh — LOCAL-630 isolated live run in a DISPOSABLE container
# (name: local630-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-630 branch tree (so ALL branch fixes are in
# the image) and runs AT MOST TWO FRESH 3-stop museum tours — The National
# Gallery, London (the ticket venue; cache AND pool OFF) and the Art Institute of
# Chicago (never-generated famous museum) — metered + HARD-CAPPED at $1.50
# COMBINED by tests/live_run_meter.py. The harness refuses to START a second tour
# once combined spend + $0.90 reserve would exceed $1.50.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1 (audiotours), which
# critique.sh reads to score the spoken text. It does NOT use the stack's
# generator service, and never renames/replaces an audioura-* container. Image +
# container removed at the end. No DELETE.
#
# Usage: ./run_local630_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local630-gen-img"
ENV_FILE="$(readlink "${HERE}/.env" 2>/dev/null || echo "${HERE}/.env")"
OUT_DIR="${HERE}/tours/local630_live"
NET="development_default"
GEN="local630-gen"
SPARE_PORT="${SPARE_PORT:-5097}"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local630_live.log"

cleanup() {
  echo "[local630] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local630] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local630] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local630_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local630_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  -p "${SPARE_PORT}:5000"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e STOP_EDITOR=1
  -e COST_HARD_LIMIT_USD=1.50
  -e TEST_GEMINI_MAX_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local630_container.py:/app/run_local630_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local630_container.py)

echo "[local630] ===== running <=2 fresh museums (3 stops each, combined cap \$1.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-630 full log at ${LOG} ####################"
echo "[local630] tour IDs (for critique.sh):"
grep -E "LOCAL630_TOUR_IDS?=" "${LOG}" || true
