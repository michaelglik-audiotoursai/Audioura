#!/usr/bin/env bash
# run_local858b_live.sh — LOCAL-858B isolated live run in a DISPOSABLE container
# under project "local858b". NEVER an audioura-* container, never -p audioura,
# never the live DB. Spins up its OWN throwaway postgres (local858b-postgres) and
# runs run_local858b_container.py on the audioura-tour-generator image with the
# branch code bind-mounted.
#
# CLOUD-LIKE: K_SERVICE=local858b is set; LANDMARK_LIVE_LOOKUP is deliberately
# NOT passed (the generator's own setdefault on the walking path must turn it on —
# ticket item 1). The container runs the Ben Thanh walk TWICE: once with Wikidata
# reachable, once with LANDMARK_WIKIDATA_BLOCKED=1 (simulating the Cloud Run
# 429/egress block) so the SECOND authority (Serper /places → Nominatim) proves
# the pins land without Wikidata.
#
# [LOCAL-820] THE METER CONTRACT — bind-mount the shared meterlog dir, write the
# canonical paid_api_calls.jsonl, install the meter via PYTHONPATH=/opt/meter,
# tag every row METER_SERVICE=LOCAL-858B. The whole-task budget
# (TASK_BUDGET_ID/USD) refuses to start / aborts mid-run at $0.35.
#
# Usage: ./run_local858b_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local858b"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
TASK_BUDGET_DIR="${HOME}/.audioura_task_budgets"
mkdir -p "${METER_DIR}" "${TASK_BUDGET_DIR}"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local858b] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local858b] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  -v "${HERE}/local778-initdb:/docker-entrypoint-initdb.d:ro" \
  postgres:15 >/dev/null

for i in $(seq 1 20); do
  if docker exec "${PG_NAME}" pg_isready -U admin -d audiotours >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[local858b] waiting for initdb schema (audio_tours table)…"
for i in $(seq 1 60); do
  if docker exec "${PG_NAME}" psql -U admin -d audiotours -tAc \
       "SELECT to_regclass('public.audio_tours') IS NOT NULL" 2>/dev/null | grep -q t; then
    echo "[local858b] schema ready after ${i}s"
    break
  fi
  sleep 1
done

args=(
  docker run --rm --name "${TG_NAME}"
  --memory 3g --cpus 2
  --network "${NET}"
)
# .env FIRST so our explicit -e below OVERRIDE it — DATABASE_URL must point at the
# throwaway postgres, never the live DB that .env may name.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(
  -e DATABASE_URL=postgresql://admin:password123@${PG_NAME}:5432/audiotours
  -e DB_HOST="${PG_NAME}" -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e STOP_EXISTENCE_GATE_MODE=log_only
  -e NARRATION_MODEL=gpt-4.1-mini
  -e STORY_PASS_MODEL=gpt-4.1
  -e RESEARCH_BACKEND=serper
  -e TEST_GEMINI_MAX_USD=0.35
  -e COST_HARD_LIMIT_USD=0.35
  # CLOUD-LIKE: the Cloud Run service marker. LANDMARK_LIVE_LOOKUP is NOT passed —
  # the generator must set it itself (ticket item 1).
  -e K_SERVICE=local858b
)
# Strip LANDMARK_LIVE_LOOKUP from the inherited .env so the setdefault path is
# genuinely exercised (the .env may set it). Docker has no "unset"; we pass an
# empty value, which run_local858b_container.py treats as unset at start.
args+=(-e LANDMARK_LIVE_LOOKUP=)
# [LOCAL-820/827] THE METER CONTRACT.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-858B
  -e AUDIOURA_TASK_BUDGET_DIR=/task_budgets
  -e TASK_BUDGET_ID=LOCAL-858B
  -e TASK_BUDGET_USD=0.35
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${TASK_BUDGET_DIR}:/task_budgets"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local858b_container.py)

echo "[local858b] ===== running LOCAL-858B live, cap \$0.35, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-858B live run done (rc=${RC}) ####################"
echo "[local858b] meter rows (service=LOCAL-858B) now in ${METER_DIR}/paid_api_calls.jsonl"
exit "${RC}"
