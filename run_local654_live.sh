#!/usr/bin/env bash
# run_local654_live.sh — LOCAL-654 isolated live verification in a DISPOSABLE
# container (name: local654-gen; --rm; spare published port 5121; NEVER an
# audioura-* service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from THIS branch's tree (so the hardened
# sentence_split.py is in the image) and runs TWO FRESH tours with the cheap
# arm ON:
#   1. Uffizi Gallery, Florence              3 stops  ON
#   2. The Art Institute of Chicago, Chicago 3 stops  ON
# Env (ON): NARRATION_MODEL=gpt-4.1-mini  RESEARCH_BACKEND=serper  PARALLEL_STOPS=1
# Metered + HARD-CAPPED at $1.20 COMBINED by tests/live_run_meter.py with a
# RESERVE GATE before each tour.
#
# The container joins development_default ONLY to INSERT each delivered tour as
# an additive is_test row into development-postgres-2-1 (detectors.py /
# critique.sh read it to score the spoken text). Tour cache OFF + stop pool OFF
# (fresh). Image + container removed at the end. NO DELETE. Rows: additive
# is_test only.
#
# Usage: ./run_local654_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local654-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local654_live"
NET="development_default"
GEN="local654-gen"
PORT="5121"          # spare published port (verified free)
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local654_live.log"

cleanup() {
  echo "[local654] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local654] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local654] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local654_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local654_build.log; exit 1; }

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
  -e NARRATION_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e PARALLEL_STOPS=1
  -e COST_HARD_LIMIT_USD=1.20
  -e TEST_GEMINI_MAX_USD=1.20
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local654_container.py:/app/run_local654_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local654_container.py)

echo "[local654] ===== running Uffizi(3) + AIC(3), cheap arm ON, combined cap \$1.20 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-654 full log at ${LOG} ####################"
echo "[local654] tour IDs + results (for detectors.py / critique.sh):"
grep -E "LOCAL654_TOUR_ID_|RESULT |OUTCOME |\[LOCAL-654\]|\[detectors\]|row count|spend for host" "${LOG}" || true
