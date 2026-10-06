#!/usr/bin/env bash
# run_local585_live.sh — LOCAL-585 isolated live run in a DISPOSABLE container
# (never audioura-*). Builds Dockerfile.generator, runs Griffin + Athenaeum through
# the real generation path with its OWN env-file (the one the audioura-tour-
# generator-1 container uses, i.e. the project .env), on development_default so the
# stop-pool DB (postgres-2) resolves, OpenAI hard cap $2.00, tour cache OFF.
# audio_tours is only counted, never written/deleted. Removes the image at the end.
#
# Usage: ./run_local585_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="audioura-test-local585"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local585_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local585_live.log"

echo "[local585] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local585] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local585_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local585_build.log; exit 1; }

NAME="local585-gen-$(date +%s)"
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
# Own env-file (the audioura-tour-generator-1 container's env = project .env),
# so OPENAI_API_KEY etc. are present. Never reuse an audioura-* container.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local585_live.py)

echo "[local585] ===== running Griffin + Athenaeum ====="
"${args[@]}" 2>&1 | tee "${LOG}" \
  | grep -E "CASE |Stop [0-9]+:|STOP-1 AUDIT|is 'About|NOT framed|carries founder|covers architecture|NO 'consists|NO 'consists of a series|tour_kind|generation cost|SUMMARY|^  \{" || true

echo "[local585] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-585 full log at ${LOG} ####################"
