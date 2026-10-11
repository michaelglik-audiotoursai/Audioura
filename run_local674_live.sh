#!/usr/bin/env bash
# run_local674_live.sh — LOCAL-674 live A/B in TWO DISPOSABLE containers launched
# at the SAME MOMENT (names local674-gemini / local674-serper_plus; --rm; spare
# ports 5191/5192; NEVER an audioura-* service container, never
# `docker compose -p audioura`). Builds Dockerfile.generator from the LOCAL-674
# worktree (so serper_plus_research + the WALKING_RESEARCH flag are in the image)
# and runs ONE FRESH PAID walking tour per arm:
#
#   arm gemini      — WALKING_RESEARCH unset (default): grounded Gemini per stop.
#   arm serper_plus — WALKING_RESEARCH=serper_plus: the LOCAL-674 winner.
#
# Everything else is held EQUAL (CHEAP_ARM_CATEGORIES=museum so museum envs do not
# bleed into walking; FAST_PIPELINE; cache+pool OFF). Each arm is metered +
# HARD-CAPPED at $0.70 by tests/live_run_meter.py with a reserve gate. Containers
# join development_default ONLY to INSERT the delivered tour as an additive
# is_test row. Image + containers removed at the end. No DELETE.
#
# Usage: ./run_local674_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local674-generator:latest"
ENV_FILE="$(readlink -f "${HERE}/.env")"
OUT_DIR="${HERE}/tours/local674_live"
METER_DIR="/Users/micha/Audioura/meterlogs"
NET="development_default"
mkdir -p "${OUT_DIR}"

cleanup() {
  echo "[local674] cleanup ..."
  docker rm -f local674-gemini local674-serper_plus >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local674] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local674] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local674_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local674_build.log; exit 1; }

run_arm() {
  local arm="$1" port="$2"
  local args=(
    docker run --rm --name "local674-${arm}"
    --memory 3g --cpus 2
    --network "${NET}"
    -p "${port}:5000"
    -e ARM="${arm}"
    -e DB_HOST=development-postgres-2-1 -e DB_PORT=5432 -e DB_NAME=audiotours
    -e DB_USER=admin -e DB_PASSWORD=password123
    -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
    -e STORIED_MODE=true
    -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1
    -e FAST_PIPELINE=1
    -e CHEAP_ARM_CATEGORIES=museum
    -e COST_HARD_LIMIT_USD=0.70 -e TEST_GEMINI_MAX_USD=0.70
    -e LOCAL603_PREFLIGHT=1 -e STOP_EDITOR=1 -e STOP_EDITOR_ENABLED=1
    -v "${OUT_DIR}:/app/tours"
    -v "${METER_DIR}:/meterlogs"
    -v "${HERE}/run_local674_container.py:/app/run_local674_container.py:ro"
  )
  [ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
  args+=("${IMAGE}" python run_local674_container.py)
  "${args[@]}" >"${OUT_DIR}/local674_${arm}.log" 2>&1
}

echo "[local674] ===== launching BOTH arms at the same moment ====="
run_arm gemini 5191 &
PID_G=$!
run_arm serper_plus 5192 &
PID_S=$!
wait $PID_G; wait $PID_S

echo ""
echo "#################### LOCAL-674 A/B logs ####################"
for arm in gemini serper_plus; do
  echo "===== arm=${arm} ====="
  grep -E "LOCAL674_TOUR_ID_|OUTCOME|STOP TITLE|GROUNDING|cost\] tour_total|spend for host|walking_research_backend|complete" \
    "${OUT_DIR}/local674_${arm}.log" || true
  echo ""
done
