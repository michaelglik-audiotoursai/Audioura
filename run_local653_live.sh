#!/usr/bin/env bash
# run_local653_live.sh — LOCAL-653 isolated live verification in a DISPOSABLE
# container (name: local653-gen; --rm; spare published port 5130; NEVER an
# audioura-* service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-653 branch tree (so site_candidate_guard.py
# and the _verify_works_v2 wiring are in the image) and runs TWO FRESH tours:
#   1. The Courtauld, 3 stops, fresh
#   2. The Courtauld, 3 stops, fresh
# Metered + HARD-CAPPED at $1.50 COMBINED by tests/live_run_meter.py with a
# RESERVE GATE before each tour.
#
# The container joins development_default ONLY to INSERT each delivered tour as
# an additive is_test row into development-postgres-2-1, which critique.sh and
# detectors.py read to score the spoken text. Tour cache OFF + stop pool OFF
# (fresh). Image + container removed at the end. No DELETE. Rows: additive
# is_test only.
#
# Usage: ./run_local653_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local653-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local653_live"
NET="development_default"
GEN="local653-gen"
PORT="5130"          # spare published port (verified free; ticket: docker run -p <spare port>)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local653_live.log"

cleanup() {
  echo "[local653] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local653] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local653] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local653_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local653_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=1.50
  -e TEST_GEMINI_MAX_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local653_container.py:/app/run_local653_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local653_container.py)

echo "[local653] ===== running Courtauld(3) x2, fresh, combined cap \$1.50 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-653 full log at ${LOG} ####################"
echo "[local653] tour IDs + results (for critique.sh / detectors.py):"
grep -E "LOCAL653_TOUR_ID_|RESULT |OUTCOME |STOP TITLE|LOCAL-653 detectors|row count|spend for host" "${LOG}" || true
