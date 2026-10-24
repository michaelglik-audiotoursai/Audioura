#!/usr/bin/env bash
# run_local751_live.sh — LOCAL-751 isolated live run in a DISPOSABLE container
# (name: local751-gen; --rm; spare published port 5151; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-751 branch tree (so the exhibit-museum
# second-chance, the area clause-cut, and the named-place policy are in the
# image) and runs FOUR FRESH PAID tours:
#   "The Salem Witch Museum, Salem MA"                                   (4 stops)
#   "Salem Museum of Torture, Salem MA"                                  (4 stops)
#   "Walking tour in Danvers, MA including Witchcraft Victims Memorial"  (4 stops)
#   "Isabella Stewart Gardner Museum, Boston"            (4 stops, art regression)
#
# Metered + HARD-CAPPED at $1.50 for the WHOLE task by tests/live_run_meter.py
# with a RESERVE GATE before each tour. The container joins development_default
# ONLY to INSERT the delivered tours as additive is_test rows (lat/lng NULL) into
# development-postgres-2-1. Tour cache OFF + stop pool OFF (fresh). Image +
# container removed at the end. No DELETE (D141). Rows: additive is_test only.
#
# Usage: ./run_local751_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local751-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local751_live"
NET="development_default"
GEN="local751-gen"
PORT="5151"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local751_live.log"

cleanup() {
  echo "[local751] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local751] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local751] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local751_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local751_build.log; exit 1; }

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
  -e STOP_EXISTENCE_GATE_MODE=enforce
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local751_container.py:/app/run_local751_container.py:ro"
  -v "${HERE}/generate_tour_text.py:/app/generate_tour_text.py:ro"
  -v "${HERE}/area_resolver.py:/app/area_resolver.py:ro"
  -v "${HERE}/screen_work_tour.py:/app/screen_work_tour.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local751_container.py)

echo "[local751] ===== running 4 fresh tours (Salem Witch / Torture / Danvers / Gardner), task cap \$1.50 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-751 full log at ${LOG} ####################"
echo "[local751] key lines:"
grep -E "LOCAL751_TOUR_ID_|RESULT |ORIENTATION_OPENING|NAMED_PLACE_ANNOUNCEMENT|STOP TITLE|row count|spend|OUTCOME|exhibit_museum|Area resolution|Parsed:|tier=" "${LOG}" || true
