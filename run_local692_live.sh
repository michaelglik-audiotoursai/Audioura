#!/usr/bin/env bash
# run_local692_live.sh — LOCAL-692 evaluation in DISPOSABLE containers
# (name: local692-gen; --rm; spare published port 5192). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds
# Dockerfile.generator from the LOCAL-692 branch tree so the artist-life backend,
# the museum writer instruction and the Vietnamese name aid are in the image.
#
# Runs TWO venues, each BEFORE (object backend) and AFTER (artist_life) in ONE
# container per venue:
#   1. Ho Chi Minh City Museum of Fine Arts, Vietnam — 5 stops
#   2. Isabella Stewart Gardner Museum, Boston        — 4 stops
#
# Whole-task budget <= $3.00. Per-venue COST_HARD_LIMIT_USD caps each container;
# the harness has a RESERVE GATE before each arm. Rows: additive is_test only,
# into development-postgres-2-1. No DELETE. Image + containers removed at end.
#
# Usage: ./run_local692_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local692-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local692_live"
NET="development_default"
GEN="local692-gen"
PORT="5192"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local692_live.log"
: > "${LOG}"

cleanup() {
  echo "[local692] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local692] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local692] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local692_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local692_build.log; exit 1; }

run_venue() {
  local slug="$1" venue="$2" stops="$3" cap="$4"
  echo "[local692] ===== ${slug}: ${venue} (${stops} stops) cap \$${cap} =====" | tee -a "${LOG}"
  local args=(
    docker run --rm --name "${GEN}"
    --memory 3g --cpus 2
    --network "${NET}"
    -p "${PORT}:5000"
    -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
    -e DB_USER=admin -e DB_PASSWORD=password123
    -e STORIED_MODE=true
    -e DISABLE_TOUR_CACHE=1
    -e DISABLE_STOP_POOL=1
    -e COST_HARD_LIMIT_USD="${cap}"
    -e TEST_GEMINI_MAX_USD="${cap}"
    -e LOCAL603_PREFLIGHT=1
    -e LOCAL692_VENUE="${venue}"
    -e LOCAL692_STOPS="${stops}"
    -e LOCAL692_SLUG="${slug}"
    -v "${OUT_DIR}:/app/tours"
    -v "${HERE}/run_local692_container.py:/app/run_local692_container.py:ro"
  )
  [ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
  args+=("${IMAGE}" python run_local692_container.py)
  "${args[@]}" 2>&1 | tee -a "${LOG}" || true
}

# HCMC first ($1.60 of the $3.00 task budget), then ISG ($1.40).
run_venue "HCMC" "Ho Chi Minh City Museum of Fine Arts, Vietnam" "5" "1.60"
run_venue "ISG"  "Isabella Stewart Gardner Museum, Boston, MA"   "4" "1.40"

echo ""
echo "#################### LOCAL-692 full log at ${LOG} ####################"
echo "[local692] key lines:"
grep -E "LOCAL692_TOUR_ID_|RESULT |STOP:|SOURCES\[|SUMMARY|words/stop|distinct|name_faults|editor_score|row count|audio_tours (BEFORE|AFTER)|spend for host|OUTCOME|reserve-gate|LOCAL692_RESULTS_JSON" "${LOG}" || true
