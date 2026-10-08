#!/usr/bin/env bash
# run_local631_live.sh — LOCAL-631 isolated CONCURRENT live run in a DISPOSABLE
# container (name: local631-gen; --rm; NEVER an audioura-* service container).
# Builds Dockerfile.generator from the LOCAL-631 branch tree and runs TWO fresh
# 2-stop museum tours (Musée Rodin + Rijksmuseum) AT THE SAME TIME (one thread
# each) to reproduce the bench-R0 concurrency bleed, metered + hard-capped at
# $1.20 COMBINED by tests/live_run_meter.py with a reserve gate.
#
# The container joins development_default ONLY to INSERT each delivered tour as
# an additive is_test row into development-postgres-2-1. It does NOT use the
# stack's generator service; all generation runs the branch code inside the
# disposable container. Tour cache OFF, stop pool OFF (fresh). Image removed at
# the end. No DELETE.
#
# Usage: ./run_local631_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local631-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local631_live"
NET="development_default"
GEN="local631-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local631_live.log"

cleanup() {
  echo "[local631] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local631] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local631] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local631_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local631_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e COST_HARD_LIMIT_USD=1.20
  -e TEST_GEMINI_MAX_USD=1.20
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local631_container.py:/app/run_local631_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local631_container.py)

echo "[local631] ===== running Rodin + Rijksmuseum CONCURRENTLY (2 stops each, combined cap \$1.20) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-631 full log at ${LOG} ####################"
echo "[local631] tour IDs (for critique.sh):"
grep -E "LOCAL631_TOUR_IDS?=" "${LOG}" || true
