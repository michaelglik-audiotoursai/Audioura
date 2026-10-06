#!/usr/bin/env bash
# run_local590_live.sh — LOCAL-590 two-step live run in ISOLATED, disposable
# containers (never audioura-*). Runs step1 (full N1), step2 (pool N2), baseline
# (full N2, pooling disabled) as THREE separate container invocations that share
# the pool via the dev DB — so no single process accumulates three generations.
# Builds Dockerfile.generator once, runs each step on development_default (so
# postgres-2 resolves), caps resources, appends JSON results to a host file, and
# removes the image at the end.
#
# Usage: ./run_local590_live.sh griffin        (or: boston_common)
set -uo pipefail

SCENARIO="${1:-griffin}"
HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="audioura-test-local590"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local590_live"
mkdir -p "${OUT_DIR}"
RESULTS="${OUT_DIR}/local590_results.jsonl"

echo "[local590] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local590_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -20 /tmp/local590_build.log; exit 1; }

run_step () {
  local step="$1"
  local name="${IMAGE}-${SCENARIO}-${step}-$(date +%s)"
  local args=(
    docker run --rm --name "${name}"
    --memory 3g --cpus 2
    --network development_default
    -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
    -e DB_HOST=postgres-2
    -e DB_PORT=5432
    -e DB_NAME=audiotours
    -e DB_USER=admin
    -e DB_PASSWORD=password123
    -e STORIED_MODE=true
    -e COST_HARD_LIMIT_USD=2.00
    -v "${OUT_DIR}:/host_out"
  )
  [ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
  args+=("${IMAGE}" python run_local590_live.py "${SCENARIO}" "${step}")
  echo "[local590] ===== running ${SCENARIO}/${step} ====="
  "${args[@]}" 2>&1 | tee "/tmp/local590_${SCENARIO}_${step}.log" | grep -E "RESULT|pool:|POOL STORE|POOL DELIVERY|pool exclusion|CACHE (HIT|MISS|STORE)|delivered_stops|total_cost|reused_stops|new_stops|rewritten|requested|Tour total|\[driver\]|END " || true
}

# step1 seeds the pool; step2 reuses it; baseline is the no-pool comparison.
run_step step1
run_step step2
run_step baseline

echo "[local590] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-590 RESULTS (${SCENARIO}) ####################"
cat "${RESULTS}" 2>/dev/null || echo "(no results file)"
