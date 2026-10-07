#!/usr/bin/env bash
# run_local603_live.sh — LOCAL-603 (D618) isolated live run in a DISPOSABLE
# container (name local603-gen; NEVER an audioura-* container). Builds
# Dockerfile.generator and runs TWO single-venue requests through the real
# generation path:
#   1. WNDR museum, Boston, MA (7 stops)              → expect venue_closed refusal
#   2. Griffin Museum of Photography, Winchester (5)  → still delivers
# Reports the MEASURED preflight cost per call (requests, queries, $) and the
# venue_preflight_cache row count. OpenAI per-tour cap $1.00; total budget $2.
# Tour cache OFF. Removes the image at the end.
#
# Usage: ./run_local603_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local603-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local603_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local603_live.log"

echo "[local603] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local603] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local603_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local603_build.log; exit 1; }

NAME="local603-gen"
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
  -e COST_HARD_LIMIT_USD=1.00
  -v "${OUT_DIR}:/app/tours"
)
# Own env-file (project .env), so OPENAI_API_KEY / GEMINI_API_KEY / SERP_API_KEY are present.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local603_preflight.py)

echo "[local603] ===== running WNDR + Griffin (preflight gate + Plan B), total cap \$2 ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo "[local603] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-603 full log at ${LOG} ####################"
