#!/usr/bin/env bash
# run_local667_live.sh — LOCAL-667 isolated live run in a DISPOSABLE container
# (name: local667-gen; --rm; spare published port 5167; NEVER an audioura-*
# service container, never `docker compose -p audioura`). Builds
# Dockerfile.generator from the LOCAL-667 branch tree (so the three fixes —
# split-title collapse, thin-Wikidata source verification, building/collection-
# area stops — are in the image) and runs ONE FRESH PAID museum tour:
#   Ho Chi Minh City Museum of Fine Arts, Vietnam (5 stops): the ticket request.
#
# NORMAL ARM: no NARRATION_MODEL, no RESEARCH_BACKEND override (gemini grounding
# available via GEMINI_API_KEY in .env). Metered + HARD-CAPPED at $0.80 for the
# WHOLE task by tests/live_run_meter.py with a RESERVE GATE before the tour. The
# container joins development_default ONLY to INSERT the delivered tour as an
# additive is_test row into development-postgres-2-1. Tour cache OFF + stop pool
# OFF (fresh). Image + container removed at the end. No DELETE. Rows: additive
# is_test only.
#
# Usage: ./run_local667_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local667-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local667_live"
NET="development_default"
GEN="local667-gen"
PORT="5167"          # spare published port
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local667_live.log"

cleanup() {
  echo "[local667] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local667] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local667] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local667_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local667_build.log; exit 1; }

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
  -e COST_HARD_LIMIT_USD=0.80
  -e TEST_GEMINI_MAX_USD=0.80
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local667_container.py:/app/run_local667_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local667_container.py)

echo "[local667] ===== running HCMC museum (5), ONE paid tour, task cap \$0.80 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-667 full log at ${LOG} ####################"
echo "[local667] key lines:"
grep -E "LOCAL667_TOUR_ID_|RESULT |STOP TITLE|SOURCES:|\[LOCAL-667|\[D1\]|\[D1v2\]|Tier:|THIN-VERIFY|FALLBACK|LOCAL-16 GATE|row count|spend for host|OUTCOME|\[cost\]|PASS|FAIL" "${LOG}" || true
