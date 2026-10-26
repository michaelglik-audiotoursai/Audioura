#!/usr/bin/env bash
# run_local767_live.sh — LOCAL-767 isolated live run in a DISPOSABLE container
# (name local767-gen; NEVER an audioura-* container, never -p audioura). Builds
# Dockerfile.generator and runs "Newton City Hall, Newton, MA" (1 stop) twice
# through the real generation path:
#   RUN 1 — GEMINI unset   → LOUD fallback to standard stops, tour delivered
#   RUN 2 — GEMINI present → venue-parts path used
# Records audio_tours row counts (total + is_test) BEFORE and AFTER to prove the
# harness writes nothing (it calls generate_tour_text directly, which does not
# touch audio_tours). Meters paid calls to /meterlogs. Per-tour OpenAI cap $0.40,
# whole script ≤ $0.80. Removes the image at the end. Deletes NOTHING (D141).
#
# Usage: ./run_local767_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local767-gen-img"
NAME="local767-gen"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local767_live"
METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${OUT_DIR}" "${METER_DIR}"
LOG="${OUT_DIR}/local767_live.log"

NET="development_default"
PSQL_IMG="postgres:15"
PGENV=(-e PGPASSWORD=password123)
PSQL=(docker run --rm --network "${NET}" "${PGENV[@]}" "${PSQL_IMG}"
      psql -h postgres-2 -U admin -d audiotours -tAc)

row_counts () {
  "${PSQL[@]}" "select count(*)||' total, '||count(*) filter (where is_test)||' is_test' from audio_tours;" 2>/dev/null
}

echo "[local767] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local767] audio_tours BEFORE: $(row_counts)" | tee "${LOG}"

echo "[local767] building ${IMAGE} ..." | tee -a "${LOG}"
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local767_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -30 /tmp/local767_build.log; exit 1; }

args=(
  docker run --rm --name "${NAME}"
  --memory 3g --cpus 2
  --network "${NET}"
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e DB_HOST=postgres-2 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e COST_HARD_LIMIT_USD=0.40
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -v "${OUT_DIR}:/app/tours"
  -v "${METER_DIR}:/meterlogs"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=("${IMAGE}" python run_local767_live.py)

echo "[local767] ===== running Newton City Hall x2 (no-key + with-key), cap \$0.80 =====" | tee -a "${LOG}"
"${args[@]}" 2>&1 | tee -a "${LOG}"
RC=${PIPESTATUS[0]}

echo "[local767] audio_tours AFTER:  $(row_counts)" | tee -a "${LOG}"

echo "[local767] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-767 full log at ${LOG} (rc=${RC}) ####################"
exit "${RC}"
