#!/usr/bin/env bash
# run_local616_live.sh — LOCAL-616 isolated live run in DISPOSABLE containers only
# (names: local616-gen, local616-pg; NEVER an audioura-* container). Builds
# Dockerfile.generator and runs TWO fresh 3-stop museum tours via
# run_local616_container.py:
#   1. Musée Granet, Aix-en-Provence, France    (3 stops)
#   2. Groeningemuseum, Bruges, Belgium          (3 stops)
# Combined cap $1.50 (metered via tests/live_run_meter.py). A disposable Postgres
# (postgres:15-alpine) on a disposable network keeps the stop pool + cost_ledger
# isolated — no audioura-* container or shared DB is touched. Tour cache OFF
# (fresh). Image + Postgres + network removed at the end.
#
# Usage: ./run_local616_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local616-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local616_live"
NET="local616-net"
PG="local616-pg"
GEN="local616-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local616_live.log"

cleanup() {
  echo "[local616] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rm -f "${PG}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local616] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local616] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local616_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local616_build.log; exit 1; }

echo "[local616] disposable network + Postgres ..."
docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f "${PG}" >/dev/null 2>&1 || true
docker run -d --name "${PG}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours postgres:15-alpine >/dev/null
echo "[local616] waiting for Postgres ..."
for i in $(seq 1 30); do
  docker exec "${PG}" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 1
done

args=(
  docker run --rm --name "${GEN}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DATABASE_URL=postgresql://admin:password123@${PG}:5432/audiotours
  -e DB_HOST="${PG}" -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e TEST_GEMINI_MAX_USD=1.50
  -e COST_HARD_LIMIT_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
  # .dockerignore excludes *_container.py from the image build context, so the
  # harness script is bind-mounted into /app at runtime (read-only).
  -v "${HERE}/run_local616_container.py:/app/run_local616_container.py:ro"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local616_container.py)

echo "[local616] ===== running two museums (3 stops each, combined cap \$1.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-616 full log at ${LOG} ####################"
