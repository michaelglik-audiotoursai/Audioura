#!/usr/bin/env bash
# run_local599c_live.sh — LOCAL-599C r3 isolated live run in a DISPOSABLE container
# (never audioura-*). Builds Dockerfile.generator, runs MassArt Art Museum through
# the real generation path (which routes through stop_pool_orchestrator for the
# D611 opening section), on development_default so the stop-pool DB (postgres-2)
# resolves. OpenAI hard cap $2.00, tour cache OFF. Removes the image at the end.
#
# Usage: ./run_local599c_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local599c-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local599c_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local599c_live.log"

echo "[local599c] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local599c] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local599c_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local599c_build.log; exit 1; }

NAME="local599c-gen"
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
  -e COST_HARD_LIMIT_USD=2.00
  -v "${OUT_DIR}:/app/tours"
)
# Own env-file (project .env), so OPENAI_API_KEY / SERP_API_KEY etc. are present.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local599c_massart.py)

echo "[local599c] ===== running MassArt Art Museum, Boston, MA (7 stops, cap \$2) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo "[local599c] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-599B full log at ${LOG} ####################"
