#!/usr/bin/env bash
# run_local620_live.sh — LOCAL-620 isolated live run in a DISPOSABLE container
# (name: local620-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-620 branch tree (so ALL branch code —
# story_type_classes.py, story_balance.py, story_prefs.py, the icon_evaluator
# deterministic class tagging, the balance wiring and the carry-over conclusion
# fixes — is in the image) and runs TWO fresh museum tours TWICE each
# (McMullen 5 stops, Lille 4 stops; no-prefs then social-seeded), metered +
# hard-capped at $2.50 COMBINED by tests/live_run_meter.py.
#
# The container joins development_default ONLY to INSERT each delivered tour as an
# additive is_test row into development-postgres-2-1 (and to seed ONE unique test
# user's user_class_prefs), which critique.sh reads to score the spoken text. It
# does NOT use the stack's generator service. Tour cache OFF. Image removed at the
# end. No DELETE.
#
# Usage: ./run_local620_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local620-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local620_live"
NET="development_default"
GEN="local620-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local620_live.log"

cleanup() {
  echo "[local620] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local620] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local620] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local620_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local620_build.log; exit 1; }

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e STORY_PREFS=1
  -e COST_HARD_LIMIT_USD=2.50
  -e TEST_GEMINI_MAX_USD=2.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  -v "${HERE}/run_local620_container.py:/app/run_local620_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local620_container.py)

echo "[local620] ===== running 2 museums x 2 passes (combined cap \$2.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-620 full log at ${LOG} ####################"
echo "[local620] tour IDs (for critique.sh):"
grep -E "LOCAL620_TOUR_IDS?=" "${LOG}" || true
