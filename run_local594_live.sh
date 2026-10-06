#!/usr/bin/env bash
# run_local594_live.sh — LOCAL-594 isolated live run in a DISPOSABLE container
# (never audioura-*). Builds Dockerfile.generator and runs the McMullen Museum of
# Art (Boston College) 7-stop tour through the real generation path TWICE in one
# container:
#   AFTER  — the LOCAL-594 cut (<= 1 grounded request/stop, r2 ungrounded).
#   BEFORE — the pre-cut behaviour (grounded r2 + unbounded per-stop budget +
#            grounded leads provider), to measure what the cut removed.
# AFTER runs first (cheap) so a cost trip still leaves a usable AFTER result.
#
# Total cap $3 INCLUDING Gemini grounding (COST_HARD_LIMIT_USD). Tour cache +
# stop pool OFF (fresh grounding each time). audio_tours DB is only counted,
# never written/deleted. Image removed at the end.
#
# Usage: ./run_local594_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local594-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local594_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local594_live.log"

echo "[local594] stamping git sha ..."
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local594] building ${IMAGE} ..."
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local594_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local594_build.log; exit 1; }

NAME="local594-gen"
common=(
  --rm --name "${NAME}"
  --memory 3g --cpus 2
  --network development_default
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e DB_HOST=postgres-2 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e COST_HARD_LIMIT_USD=3.00
  -v "${OUT_DIR}:/app/tours"
)
[ -f "${ENV_FILE}" ] && common+=(--env-file "${ENV_FILE}")

echo "[local594] ===== AFTER (cut): STORY_LOOP_MAX_GROUNDED=1, leads ungrounded =====" | tee "${LOG}"
docker run "${common[@]}" \
  -e LOCAL594_LABEL=AFTER \
  -e STORY_LOOP_MAX_GROUNDED=1 \
  "${IMAGE}" python run_local594_mcmullen.py 2>&1 | tee -a "${LOG}"

echo "" | tee -a "${LOG}"
echo "[local594] ===== BEFORE (baseline): grounded r2 + unbounded budget + grounded leads =====" | tee -a "${LOG}"
# STORY_LOOP_MAX_GROUNDED huge = ground every credit_line's narrate; the pre-cut
# code grounded r2 too — we approximate the baseline request count with the
# driver's per-stop tap and the whole-tour counter. STORY_LEADS_GROUNDED=1
# restores the redundant grounded leads provider the cut dropped.
docker run "${common[@]}" \
  -e LOCAL594_LABEL=BEFORE \
  -e STORY_LOOP_MAX_GROUNDED=99 \
  -e STORY_LOOP_R2_GROUNDED=1 \
  -e STORY_LEADS_GROUNDED=1 \
  "${IMAGE}" python run_local594_mcmullen.py 2>&1 | tee -a "${LOG}"

echo "[local594] cleanup image ..."
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo ""
echo "#################### LOCAL-594 full log at ${LOG} ####################"
