#!/usr/bin/env bash
# run_local592_live.sh — LOCAL-592 isolated live run in a DISPOSABLE container
# (never audioura-*). Builds Dockerfile.generator, runs Athenaeum (5) + Griffin (7)
# through the real generation path with its OWN env-file (the one the
# audioura-tour-generator-1 container uses, i.e. the project .env), on
# development_default so the stop-pool DB (postgres-2) resolves. OpenAI hard cap
# $1.00 (< $2 ticket cap), tour cache OFF. audio_tours is only counted, never
# written/deleted. Removes the image at the end.
#
# Usage: ./run_local592_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local592-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local592_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local592_live.log"

echo "[local592] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local592] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local592_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local592_build.log; exit 1; }

NAME="local592-gen-$(date +%s)"
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
# Own env-file (the audioura-tour-generator-1 container's env = project .env),
# so OPENAI_API_KEY etc. are present. Never reuse an audioura-* container.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local592_live.py)

echo "[local592] ===== running Athenaeum (5) + Griffin (7) ====="
"${args[@]}" 2>&1 | tee "${LOG}"

echo "[local592] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-592 full log at ${LOG} ####################"
