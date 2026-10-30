#!/usr/bin/env bash
# run_local848_profile.sh — LOCAL-848 in-container MEMORY PROFILE in DISPOSABLE
# containers under project "local848p". NEVER an audioura-* container, never the
# live/shared DB. Spins up its OWN throwaway postgres, SEEDS it with the REAL
# cached rows (Rijks Q190804 + Orsay Q23402) from the shared LOCAL-826B fixture,
# then runs run_local848_container.py (tracemalloc ON) on the
# audioura-tour-generator IMAGE with the BRANCH code bind-mounted.
#
# PROFILE mode runs with a generous --memory so tracemalloc can complete and
# report WHERE the memory goes (per-phase RSS + top-10 allocation sites). The
# 512m reproduction / after-fix gate lives in run_local848_live.sh.
#
# Cheap museum arm, DISABLE_STOP_POOL=1, STORY_PASS_MODEL=gpt-4.1.
# BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-848 TASK_BUDGET_USD=0.60 (whole-task cap).
#
# THE METER CONTRACT (LOCAL-819/820): bind-mount the shared meterlog dir, write a
# DEDICATED paid_api_calls_local848_profile.jsonl, install the meter via
# PYTHONPATH=/opt/meter, tag every row METER_SERVICE=LOCAL-848.
#
# Usage: ./run_local848_profile.sh [museum|walking|both]   (default museum)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local848p"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
ACCEPT_LOG="/meterlogs/paid_api_calls_local848_profile.jsonl"
SEED_SQL="${HERE}/tests/fixtures/local826b/seed_real_cached_rows.sql"
MEM="${MEM:-3g}"           # generous so tracemalloc can finish and report
WHICH="${1:-museum}"
mkdir -p "${METER_DIR}"
: > "${METER_DIR}/paid_api_calls_local848_profile.jsonl"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local848p] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local848p] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  postgres:15 >/dev/null

for i in $(seq 1 30); do
  if docker exec "${PG_NAME}" pg_isready -U admin -d audiotours >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[local848p] creating cache tables on the throwaway DB"
docker exec -i "${PG_NAME}" psql -U admin -d audiotours >/dev/null 2>&1 <<'SQL'
CREATE TABLE IF NOT EXISTS venue_corpus (
    qid TEXT PRIMARY KEY,
    venue_name TEXT,
    official_url TEXT,
    canonical_titles_json JSONB NOT NULL,
    story_elements_json JSONB,
    sparql_works_json JSONB,
    pages_json JSONB,
    language TEXT,
    tier TEXT,
    corpus_version INT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS venue_works_cache (
    qid TEXT NOT NULL,
    language TEXT NOT NULL,
    works_json JSONB NOT NULL,
    source TEXT,
    cache_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    PRIMARY KEY (qid, language)
);
SQL

if [ -f "${SEED_SQL}" ]; then
  echo "[local848p] seeding REAL cached rows for Q23402 (Orsay) + Q190804 (Rijks)"
  docker exec -i "${PG_NAME}" psql -U admin -d audiotours -v ON_ERROR_STOP=0 < "${SEED_SQL}" >/dev/null 2>&1
else
  echo "[local848p] WARNING: seed file ${SEED_SQL} not found — running without seed"
fi

args=(
  docker run --rm --name "${TG_NAME}"
  --memory "${MEM}" --cpus 2
  --network "${NET}"
)
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(
  -e DATABASE_URL=postgresql://admin:password123@${PG_NAME}:5432/audiotours
  -e DB_HOST="${PG_NAME}" -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e STOP_EXISTENCE_GATE_MODE=log_only
  -e CHEAP_ARM_CATEGORIES=museum
  -e NARRATION_MODEL=gpt-4.1-mini
  -e SERPER_RESEARCH_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e SERP_PROVIDER=serper
  -e WORK_STORY_RESEARCH=1
  -e WORK_RESEARCH_COST_CEILING=0.03
  -e MALLOC_ARENA_MAX=2
  -e LOCAL848_TRACEMALLOC=1
  -e TASK_BUDGET_ID=LOCAL-848
  -e TASK_BUDGET_USD=0.60
  -e PER_TOUR_PASS_USD=0.45
  -e TEST_GEMINI_MAX_USD=0.60
  -e COST_HARD_LIMIT_USD=0.60
)
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG="${ACCEPT_LOG}"
  -e METER_SERVICE=LOCAL-848
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")
args+=(-e "STORY_PASS_MODEL=${STORY_PASS_MODEL:-gpt-4.1}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local848_container.py "${WHICH}")

echo "[local848p] ===== PROFILE (mem=${MEM}, which=${WHICH}), cap \$0.60 ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-848 profile done (rc=${RC}) ####################"
exit "${RC}"
