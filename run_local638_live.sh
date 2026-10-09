#!/usr/bin/env bash
# run_local638_live.sh — LOCAL-638 isolated live run in a DISPOSABLE container
# (name: local638-gen; --rm; a spare published port 5098; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-638 branch tree (so the four Note guards are
# in the image) and runs ONE FRESH 3-stop museum tour (The Frick Collection),
# metered + HARD-CAPPED at $1.00 by tests/live_run_meter.py with a RESERVE GATE.
#
# The container joins development_default ONLY to INSERT the delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image removed at the end. No DELETE. Only ONE tour is started.
#
# Usage: ./run_local638_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local638-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local638_live"
NET="development_default"
GEN="local638-gen"
PORT="5098"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local638_live.log"

cleanup() {
  echo "[local638] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local638] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local638] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local638_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local638_build.log; exit 1; }

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
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local638_container.py:/app/run_local638_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local638_container.py)

echo "[local638] ===== running 1 fresh museum (The Frick Collection, 3 stops, cap \$1.00) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-638 full log at ${LOG} ####################"
echo "[local638] tour ID (for critique.sh / detectors.py):"
grep -E "LOCAL638_TOUR_ID=" "${LOG}" || true
