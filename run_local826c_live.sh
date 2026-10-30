#!/usr/bin/env bash
# run_local826c_live.sh — LOCAL-826C isolated live run in DISPOSABLE containers
# under project "local826c". NEVER an audioura-* container, never the live/shared
# DB. Spins up its OWN throwaway postgres (local826c-postgres), SEEDS it with the
# REAL cached rows copied read-only from the live DB (same seed as 826B: stale
# pre-826 venue_corpus + refreshed venue_works_cache for Q23402 + Q190804), then
# runs run_local826c_container.py on the audioura-tour-generator image with the
# BRANCH code bind-mounted. Cheap museum arm, DISABLE_STOP_POOL=1, ONE tour
# (Rijks, 5 stops), hard cap $0.50.
#
# THE METER CONTRACT (LOCAL-819/820): canonical args — bind-mount the shared
# meterlog dir, write the canonical paid_api_calls.jsonl, install the meter via
# PYTHONPATH=/opt/meter, tag every row METER_SERVICE=LOCAL-826C. TASK_BUDGET_ID/
# TASK_BUDGET_USD arm the LOCAL-817 budget and the meter mount guard.
#
# Usage: ./run_local826c_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local826c"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
SEED_SQL="${HERE}/tests/fixtures/local826b/seed_real_cached_rows.sql"
mkdir -p "${METER_DIR}"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local826c] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local826c] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
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

echo "[local826c] creating cache tables on the throwaway DB"
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
  echo "[local826c] seeding REAL cached rows for Q23402 + Q190804 from ${SEED_SQL}"
  docker exec -i "${PG_NAME}" psql -U admin -d audiotours -v ON_ERROR_STOP=0 < "${SEED_SQL}"
  echo "[local826c] seeded rows:"
  docker exec "${PG_NAME}" psql -U admin -d audiotours -c \
    "SELECT 'venue_corpus' t, qid, corpus_version::text v FROM venue_corpus
     UNION ALL SELECT 'venue_works_cache', qid||'/'||language, source FROM venue_works_cache
     ORDER BY 1,2;"
else
  echo "[local826c] WARNING: seed file ${SEED_SQL} not found — running without seed"
fi

args=(
  docker run --rm --name "${TG_NAME}"
  --memory 3g --cpus 2
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
  -e TASK_BUDGET_ID=LOCAL-826C
  -e TASK_BUDGET_USD=0.50
  -e TEST_GEMINI_MAX_USD=0.50
  -e COST_HARD_LIMIT_USD=0.50
)
# [LOCAL-820] THE METER CONTRACT — canonical args.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-826C
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local826c_container.py)

echo "[local826c] ===== running LOCAL-826C live, cap \$0.50, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-826C live run done (rc=${RC}) ####################"
exit "${RC}"
