#!/usr/bin/env bash
# run_local624_live.sh — LOCAL-624 isolated live run in a DISPOSABLE container
# (name: local624-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-624 branch tree (so the type-match gloss
# guard + truncated-clause safety check are in the image) and runs TWO FRESH
# 2-stop museum tours never generated before (Wallraf-Richartz / Nationalmuseum),
# metered + hard-capped at $1.00 COMBINED by tests/live_run_meter.py.
#
# The container joins development_default ONLY to INSERT each delivered tour as
# an additive is_test row into development-postgres-2-1, which critique.sh reads
# to score the spoken text. It does NOT use the stack's generator service. Tour
# cache OFF (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local624_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local624-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local624_live"
NET="development_default"
GEN="local624-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local624_live.log"

cleanup() {
  echo "[local624] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local624] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local624] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local624_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local624_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e COST_HARD_LIMIT_USD=1.00
  -e TEST_GEMINI_MAX_USD=1.00
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local624_container.py:/app/run_local624_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local624_container.py)

echo "[local624] ===== running 2 fresh museums (2 stops each, combined cap \$1.00) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-624 full log at ${LOG} ####################"
echo "[local624] tour IDs (for critique.sh):"
grep -E "LOCAL624_TOUR_IDS?=" "${LOG}" || true
