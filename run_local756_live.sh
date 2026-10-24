#!/usr/bin/env bash
# run_local756_live.sh — LOCAL-756 isolated live run in a DISPOSABLE container
# (name: local756-gen; --rm; spare published port 5156; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-756 branch tree and runs the four arms in
# run_local756_container.py:
#   Salem Witch Museum (4) FRESH, then CACHE HIT (same request)
#   Danvers walking (4) with a seeded pool (named-place gate)
#   Isabella Stewart Gardner Museum (4) — art regression
#
# Metered + HARD-CAPPED at $1.50 by tests/live_run_meter.py with a reserve gate.
# Paid calls are ALSO written to the shared meter log (mounted /meterlogs,
# PAID_API_LOG=/meterlogs/paid_api_calls.jsonl). Container joins
# development_default to INSERT additive is_test rows (lat/lng NULL) into
# development-postgres-2-1 and to seed/clean up ONLY its own is_test pool rows.
# Image + container removed at the end. No DELETE of audio_tours.
#
# Usage: ./run_local756_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local756-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local756_live"
NET="development_default"
GEN="local756-gen"
PORT="5156"
METERLOGS="/Users/micha/Audioura/meterlogs"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local756_live.log"

cleanup() {
  echo "[local756] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local756] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local756] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local756_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local756_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -p "${PORT}:5000"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e COST_HARD_LIMIT_USD=1.50
  -e TEST_GEMINI_MAX_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -e STOP_EXISTENCE_GATE_MODE=enforce
  -e STOP_EDITOR=1
  -e STOP_EDITOR_ENABLED=1
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -v "${METERLOGS}:/meterlogs"
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local756_container.py:/app/run_local756_container.py:ro"
  -v "${HERE}/generate_tour_text.py:/app/generate_tour_text.py:ro"
  -v "${HERE}/exhibition_discovery.py:/app/exhibition_discovery.py:ro"
  -v "${HERE}/stop_pool_orchestrator.py:/app/stop_pool_orchestrator.py:ro"
  -v "${HERE}/stop_pool_store.py:/app/stop_pool_store.py:ro"
  -v "${HERE}/area_resolver.py:/app/area_resolver.py:ro"
  -v "${HERE}/screen_work_tour.py:/app/screen_work_tour.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local756_container.py)

echo "[local756] ===== running 4 arms (Salem fresh+hit / Danvers / Gardner), task cap \$1.50 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-756 full log at ${LOG} ####################"
echo "[local756] key lines:"
grep -E "LOCAL756_TOUR_ID_|RESULT |ORIENTATION_OPENING|NAMED_PLACE_ANNOUNCEMENT|STOP TITLE|row count|spend|OUTCOME|exhibit_museum|tier=|pool NOT served|EXHIBIT VERIFIED|Built exhibit" "${LOG}" || true
