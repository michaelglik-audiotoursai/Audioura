#!/usr/bin/env bash
# run_local602c_live.sh — LOCAL-602C r3 isolated live run in DISPOSABLE
# containers only (names: local602c-gen, local602c-pg; NEVER an audioura-*
# container). Builds Dockerfile.generator and runs:
#   Meow Wolf, Santa Fe, NM  (5 stops)  with VENUE_PREFLIGHT enabled, cap $1.50.
# A disposable Postgres (postgres:15-alpine) on a disposable network keeps the
# stop pool isolated — no audioura-* container or shared DB is touched. Image +
# Postgres + network removed at the end.
#
# Usage: ./run_local602c_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local602c-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local602c_live"
NET="local602c-net"
PG="local602c-pg"
GEN="local602c-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local602c_live.log"

cleanup() {
  echo "[local602c] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rm -f "${PG}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local602c] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local602c] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local602c_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local602c_build.log; exit 1; }

echo "[local602c] disposable network + Postgres ..."
docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f "${PG}" >/dev/null 2>&1 || true
docker run -d --name "${PG}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours postgres:15-alpine >/dev/null
echo "[local602c] waiting for Postgres ..."
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
  -e COST_HARD_LIMIT_USD=1.50
  -e LOCAL603_PREFLIGHT=1
  -v "${OUT_DIR}:/app/tours"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local602c_meowwolf.py)

echo "[local602c] ===== running Meow Wolf, Santa Fe NM (5 stops, cap \$1.50, preflight on) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-602C full log at ${LOG} ####################"
