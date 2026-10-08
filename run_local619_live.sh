#!/usr/bin/env bash
# run_local619_live.sh — LOCAL-619 isolated live run in a DISPOSABLE container
# (name: local619-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-619 branch tree (so ALL branch code — the
# unified conclusion builder tour_conclusion.py and the every-path wiring — is in
# the image) and runs THREE fresh 3-stop museum tours (Thyssen Madrid / Orsay
# Paris / Hamburger Kunsthalle), metered + hard-capped at $2.50 COMBINED by
# tests/live_run_meter.py.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1, which critique.sh reads to
# score the spoken text. It does NOT use the stack's generator service. Tour cache
# OFF (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local619_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local619-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local619_live"
NET="development_default"
GEN="local619-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local619_live.log"

cleanup() {
  echo "[local619] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local619] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local619] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local619_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local619_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e COST_HARD_LIMIT_USD=2.50
  -e TEST_GEMINI_MAX_USD=2.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local619_container.py:/app/run_local619_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local619_container.py)

echo "[local619] ===== running 3 museums (3 stops each, combined cap \$2.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-619 full log at ${LOG} ####################"
echo "[local619] tour IDs (for critique.sh):"
grep -E "LOCAL619_TOUR_IDS?=" "${LOG}" || true
