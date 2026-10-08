#!/usr/bin/env bash
# run_local617_live.sh — LOCAL-617 isolated live run in a DISPOSABLE container
# (name: local617-gen; --rm; NEVER an audioura-* service container). Builds
# Dockerfile.generator from the LOCAL-617 branch tree and runs THREE fresh
# 3-stop museum tours (Boijmans / Kunstmuseum Basel / Bellas Artes Sevilla),
# metered + hard-capped at $2.50 COMBINED by tests/live_run_meter.py.
#
# The container joins the existing development_default network ONLY so it can
# INSERT each delivered tour as an additive is_test row into
# development-postgres-2-1, which ~/Audioura/.continuous_dev/calib/critique.sh
# reads to score the spoken text. It does NOT use the stack's generator service;
# all generation runs the branch code inside the disposable container. Tour cache
# OFF (fresh). Image removed at the end. No DELETE.
#
# Usage: ./run_local617_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local617-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${LOCAL617_OUT_DIR:-$HOME/.local617_live}"   # [safety] NEVER inside the
                                                      # external-SSD worktree: a
                                                      # writable bind-mount of a
                                                      # worktree subdir on Docker
                                                      # Desktop's external-SSD
                                                      # virtiofs wiped the whole
                                                      # worktree mid-run once. Keep
                                                      # the mutable mount on the
                                                      # internal disk.
NET="development_default"
GEN="local617-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local617_live.log"

cleanup() {
  echo "[local617] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local617] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local617] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local617_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local617_build.log; exit 1; }

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
  -v "${HERE}/run_local617_container.py:/app/run_local617_container.py:ro"
  -v "${HERE}/work_first_evidence.py:/app/work_first_evidence.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local617_container.py)

echo "[local617] ===== running 3 museums (3 stops each, combined cap \$2.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-617 full log at ${LOG} ####################"
echo "[local617] tour IDs (for critique.sh):"
grep -E "LOCAL617_TOUR_IDS?=" "${LOG}" || true
