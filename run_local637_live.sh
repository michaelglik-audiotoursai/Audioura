#!/usr/bin/env bash
# run_local637_live.sh — LOCAL-637 isolated live run in a DISPOSABLE container
# (name: local637-gen; --rm; a spare published port 5098; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-637 branch tree (so the 429/5xx retry+
# backoff, the UNKNOWN city validation that keeps a high-confidence candidate,
# the dead-host cool-down, and the non-museum parenthetical-qualifier guard are
# in the image) and runs:
#   1) ONE fresh 3-stop museum tour (The Wallace Collection), metered + hard-
#      capped at $1.30 by tests/live_run_meter.py with a RESERVE GATE;
#   2) a FREE resolver-only National Gallery x3 check under an injected 429.
#
# The container joins development_default ONLY to INSERT the delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local637_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local637-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local637_live"
NET="development_default"
GEN="local637-gen"
PORT="5098"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local637_live.log"

cleanup() {
  echo "[local637] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local637] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local637] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local637_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local637_build.log; exit 1; }

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
  -v "${HERE}/run_local637_container.py:/app/run_local637_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local637_container.py)

echo "[local637] ===== running 1 fresh museum (Wallace, 3 stops, cap \$1.30) + resolver-only NG x3 under 429 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-637 full log at ${LOG} ####################"
echo "[local637] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL637_TOUR_IDS?=|LOCAL637_NG_RESOLVER=" "${LOG}" || true
