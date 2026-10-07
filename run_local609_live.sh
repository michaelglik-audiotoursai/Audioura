#!/usr/bin/env bash
# run_local609_live.sh — LOCAL-609 isolated live run in DISPOSABLE containers only
# (names: local609-gen, local609-pg; NEVER an audioura-* container). Builds
# Dockerfile.generator and runs ONE fresh 3-stop museum tour:
#   Isabella Stewart Gardner Museum, Boston, MA  (3 stops)  cap $1.50.
# A disposable Postgres (postgres:15-alpine) on a disposable network keeps the
# stop pool + cost_ledger isolated — no audioura-* container or shared DB is
# touched. Tour cache OFF (fresh). Prints the tour_cost_report.py table.
# Image + Postgres + network removed at the end.
#
# Usage: ./run_local609_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local609-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local609_live"
NET="local609-net"
PG="local609-pg"
GEN="local609-gen"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local609_live.log"

cleanup() {
  echo "[local609] cleanup ..."
  docker rm -f "${GEN}" >/dev/null 2>&1 || true
  docker rm -f "${PG}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
  docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local609] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local609] building ${IMAGE} ..."
docker build --build-arg GIT_SHA="$(cat "${HERE}/.git_sha")" \
  -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" \
  >/tmp/local609_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local609_build.log; exit 1; }

echo "[local609] disposable network + Postgres ..."
docker network create "${NET}" >/dev/null 2>&1 || true
docker rm -f "${PG}" >/dev/null 2>&1 || true
docker run -d --name "${PG}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours postgres:15-alpine >/dev/null
echo "[local609] waiting for Postgres ..."
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
args+=("${IMAGE}" python run_local609_gardner.py)

echo "[local609] ===== running Isabella Stewart Gardner Museum, Boston MA (3 stops, cap \$1.50) ====="
"${args[@]}" 2>&1 | tee "${LOG}" || true

echo ""
echo "#################### LOCAL-609 full log at ${LOG} ####################"
