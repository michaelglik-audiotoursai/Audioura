#!/usr/bin/env bash
# run_local600_live.sh — LOCAL-600 (D616) isolated live run in a DISPOSABLE
# container (name local600-gen; NEVER an audioura-* container). Builds
# Dockerfile.generator and runs MassArt Art Museum through the real generation
# path (which routes through stop_pool_orchestrator for the D611 opening section
# and the D616 grouping + shortfall), on development_default so the stop-pool DB
# (postgres-2) resolves. OpenAI hard cap $1.50, tour cache OFF. Removes the image
# at the end.
#
# Usage: ./run_local600_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local600-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local600_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local600_live.log"

echo "[local600] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local600] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local600_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local600_build.log; exit 1; }

NAME="local600-gen"
args=(
  docker run --rm --name "${NAME}"
  --memory 3g --cpus 2
  --network development_default
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e DB_HOST=postgres-2
  -e DB_PORT=5432
  -e DB_NAME=audiotours
  -e DB_USER=admin
  -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e COST_HARD_LIMIT_USD=1.50
  -v "${OUT_DIR}:/app/tours"
)
# Own env-file (project .env), so OPENAI_API_KEY / SERP_API_KEY etc. are present.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local600_massart.py)

echo "[local600] ===== running MassArt Art Museum, Boston, MA (7 stops, cap \$1.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo "[local600] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-600 full log at ${LOG} ####################"
