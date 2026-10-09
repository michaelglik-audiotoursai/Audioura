#!/usr/bin/env bash
# run_local648_live.sh — LOCAL-648 isolated live run in a DISPOSABLE container
# (name: local648-gen; --rm; spare published port 5116; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-648 branch tree (so serper_research.py, the
# RESEARCH_BACKEND router, and the story_production_loop r1 wiring are in the
# image) and runs, under ONE combined $2.50 cap:
#   PHASE 1  offline A/B — Gemini grounded vs Serper research, 6 museums;
#   PHASE 2  two FRESH live tours with RESEARCH_BACKEND=serper (Courtauld 3 +
#            Walters 3), each stored as an additive is_test row.
#
# Metered + HARD-CAPPED at $2.50 COMBINED by tests/live_run_meter.py, with a
# RESERVE GATE before each live tour.
#
# The container joins development_default ONLY to read/insert into
# development-postgres-2-1 (hostname postgres-2 on that network), which
# critique.sh / detectors.py read to score the spoken text. Tour cache OFF +
# stop pool OFF (fresh). Image + container removed at the end. No DELETE. Rows:
# additive is_test only.
#
# Usage: ./run_local648_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local648-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local648_live"
METER_DIR="${HERE}/tours/local648_live/meterlogs"
NET="development_default"
GEN="local648-gen"
PORT="5116"          # spare published port (ticket: docker run ... -p <spare port>)
mkdir -p "${OUT_DIR}" "${METER_DIR}"
LOG="${OUT_DIR}/local648_live.log"

cleanup() {
  echo "[local648] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local648] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local648] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local648_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local648_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -p "${PORT}:5000"
  -e DB_HOST=postgres-2 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e COST_HARD_LIMIT_USD=2.50
  -e TEST_GEMINI_MAX_USD=2.50
  -e LOCAL648_OFFLINE_BUDGET=1.00
  -e LOCAL603_PREFLIGHT=1
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -v "${OUT_DIR}:/app/tours"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}/run_local648_container.py:/app/run_local648_container.py:ro"
  -v "${HERE}/measure_local648_overlap.py:/app/measure_local648_overlap.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local648_container.py)

echo "[local648] ===== offline A/B (6 museums) + Serper live tours (Courtauld 3 + Walters 3), combined cap \$2.50 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-648 full log at ${LOG} ####################"
echo "[local648] tour IDs (for critique.sh / detectors.py):"
grep -E "LOCAL648_TOUR_ID_|RESULT |GROUNDING|RESULT COURTAULD|RESULT WALTERS" "${LOG}" || true
echo "[local648] offline measurement JSON (written into the mounted tours dir):"
ls -la "${OUT_DIR}/LOCAL648_overlap_measurement.json" 2>/dev/null || echo "  (not found; see the log for the inline SUMMARY)"
