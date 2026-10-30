#!/usr/bin/env bash
# run_local830_live.sh — LOCAL-830 live proof in an OWN compose project
# (-p local830), never the shared audioura-* containers, never the live DB.
#
# Proves the category-scoped pool-reuse guard end to end against the REAL
# generator built from this worktree (mounted into the disposable generator
# container), POOL ON, with a seeded pooled "Sandals Restaurant" row for Mui Ne:
#
#   "Kitesurfing schools in Mui Ne, Vietnam" (5 stops) → NO restaurant, and the
#   Sandals row is STILL in the pool afterwards (category-scoped reuse — the
#   guard skips, never deletes).
#
# Budget: TASK_BUDGET_ID=LOCAL-830 TASK_BUDGET_USD=0.60, enforced by the
# generator env caps (TEST_GEMINI_MAX_USD / COST_HARD_LIMIT_USD) and recorded via
# tests/live_run_meter.py. With N<=K the delivery is served entirely from the
# seeded pool (no new generation), so spend is ~$0.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local830"
COMPOSE="docker-compose.local830-proof.yml"
DC=(docker compose -p "${PROJECT}" -f "${COMPOSE}")
ENV_FILE="${AUDIOURA_ENV_FILE:-/Users/micha/Audioura/.env}"
NETWORK="${PROJECT}_default"
PG_CONTAINER="local830-postgres"
GEN_IMAGE="${GEN_IMAGE:-audioura-tour-generator:latest}"
export LOCAL830_METER_DIR="${LOCAL830_METER_DIR:-/Users/micha/Audioura/meterlogs}"
mkdir -p "${LOCAL830_METER_DIR}"

say () { echo; echo "######## [local830] $* ########"; }

cleanup () {
  say "tearing down project ${PROJECT} (down -v — OWN ephemeral volume only)"
  "${DC[@]}" down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT

[ -f "${ENV_FILE}" ] || { echo "no .env at ${ENV_FILE}"; exit 2; }

say "starting isolated postgres (-p ${PROJECT})"
"${DC[@]}" up -d || { echo "compose up failed"; exit 1; }

say "waiting for postgres"
for i in $(seq 1 60); do
  docker exec "${PG_CONTAINER}" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 1
done

say "running the generator in a disposable container (POOL ON, worktree mounted)"
docker run --rm --name local830-tg \
  --network "${NETWORK}" \
  --env-file "${ENV_FILE}" \
  -e DATABASE_URL="postgresql://admin:password123@${PG_CONTAINER}:5432/audiotours" \
  -e STORIED_MODE=true \
  -e DISABLE_TOUR_CACHE=1 \
  -e TASK_BUDGET_ID=LOCAL-830 \
  -e TASK_BUDGET_USD=0.60 \
  -e TEST_GEMINI_MAX_USD=0.60 \
  -e COST_HARD_LIMIT_USD=0.60 \
  -v "${HERE}":/app -w /app \
  "${GEN_IMAGE}" \
  python -u run_local830_container.py
rc=$?

say "generator container exit code: ${rc}"
exit "${rc}"
