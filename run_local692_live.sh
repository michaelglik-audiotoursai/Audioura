#!/usr/bin/env bash
# run_local692_live.sh — LOCAL-692 evaluation in DISPOSABLE containers
# (name: local692-gen; --rm; spare published port 5192). NEVER an audioura-*
# service container, NEVER `docker compose -p audioura`. Builds
# Dockerfile.generator from the LOCAL-692 branch tree so the artist-life backend,
# the museum writer instruction and the Vietnamese name aid are in the image.
#
# Runs THREE venues, each BEFORE and AFTER in ONE container per venue:
#   1. Ho Chi Minh City Museum of Fine Arts, Vietnam — 5 works (museum)
#   2. Isabella Stewart Gardner Museum, Boston        — 4 stops (museum)
#   3. Walking tour of Boston, Massachusetts          — 5 stops (walking)
# All works PINNED via LOCAL692_FORCED_STOPS so BEFORE/AFTER narrate the same
# real works (no invented Vermeer). DATABASE_URL is set so the stop-existence
# gate runs (D261/D262); editor scoring is gpt-4.1 x3 (production).
#
# Whole-task budget <= $4.00. Per-venue COST_HARD_LIMIT_USD caps each container;
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
  local slug="$1" venue="$2" stops="$3" cap="$4" category="$5" forced="$6"
  echo "[local692] ===== ${slug}: ${venue} (${stops} ${category} stops) cap \$${cap} =====" | tee -a "${LOG}"
  local args=(
    docker run --rm --name "${GEN}"
    --memory 3g --cpus 2
    --network "${NET}"
    -p "${PORT}:5000"
    -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
    -e DB_USER=admin -e DB_PASSWORD=password123
    # [LOCAL-692B / D261/D262] DATABASE_URL so the stop-existence gate's DB
    # connection runs (without it the gate silently does NOT run).
    -e DATABASE_URL="postgresql://admin:password123@development-postgres-2-1:5432/audiotours"
    -e STORIED_MODE=true
    -e DISABLE_TOUR_CACHE=1
    -e DISABLE_STOP_POOL=1
    -e STOP_EXISTENCE_GATE_MODE=log_only
    -e EDITOR_SCORE_MODEL=gpt-4.1
    -e EDITOR_SCORE_RUNS=3
    -e COST_HARD_LIMIT_USD="${cap}"
    -e TEST_GEMINI_MAX_USD="${cap}"
    -e LOCAL603_PREFLIGHT=1
    -e LOCAL692_VENUE="${venue}"
    -e LOCAL692_STOPS="${stops}"
    -e LOCAL692_SLUG="${slug}"
    -e LOCAL692_CATEGORY="${category}"
    -e LOCAL692_FORCED_STOPS="${forced}"
    -v "${OUT_DIR}:/app/tours"
    -v "${HERE}/run_local692_container.py:/app/run_local692_container.py:ro"
  )
  [ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
  args+=("${IMAGE}" python run_local692_container.py)
  "${args[@]}" 2>&1 | tee -a "${LOG}" || true
}

# [LOCAL-692B] PINNED works (LOCAL692_FORCED_STOPS) so BEFORE and AFTER narrate
# the SAME real works — the LOCAL-692 first run let the generator invent "The
# Girl with the Pearl Earring" (a Vermeer, not in HCMC). A non-existent work in
# a museum tour is a bounce; pinning removes that confound and exercises every
# name fix (Lê Thị Lựu / Nguyễn Sáng).
HCMC_STOPS="Vườn xuân Trung Nam Bắc|Thiếu nữ bên hoa huệ|Thanh niên thành đồng|Sơn nữ|Em Thúy"
GARDNER_STOPS="The Rape of Europa|Portrait of a Woman in a Green Dress|Self-Portrait, Aged 23|El Jaleo"
BOSTON_STOPS="Faneuil Hall|Massachusetts State House|Granary Burying Ground|Old North Church|Boston Athenaeum"

# Whole-task budget <= $4.00. HCMC ($1.60), Gardner ($1.20), Boston walk ($1.20).
run_venue "HCMC"    "Ho Chi Minh City Museum of Fine Arts, Vietnam" "5" "1.60" "museum"  "${HCMC_STOPS}"
run_venue "GARDNER" "Isabella Stewart Gardner Museum, Boston, MA"   "4" "1.20" "museum"  "${GARDNER_STOPS}"
run_venue "BOSTON"  "Walking tour of Boston, Massachusetts, USA"    "5" "1.20" "walking" "${BOSTON_STOPS}"

echo ""
echo "#################### LOCAL-692 full log at ${LOG} ####################"
echo "[local692] key lines:"
grep -E "LOCAL692_TOUR_ID_|RESULT |STOP:|SOURCES\[|SUMMARY|words/stop|stories/stop|distinct|name_faults|editor_score|EXISTENCE-GATE|LOCAL-692B|artist cache|story ladder|row count|audio_tours (BEFORE|AFTER)|spend for host|OUTCOME|reserve-gate|LOCAL692_RESULTS_JSON" "${LOG}" || true
