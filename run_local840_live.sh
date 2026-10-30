#!/usr/bin/env bash
# run_local840_live.sh — LOCAL-840 isolated live run in DISPOSABLE containers
# under project "local840". NEVER an audioura-* container, never the live/shared
# DB. Spins up its OWN throwaway postgres (local840-postgres), SEEDS it with the
# REAL cached rows (Rijks Q190804 + Orsay Q23402) from the shared LOCAL-826B seed
# fixture, then runs run_local840_container.py on the audioura-tour-generator
# IMAGE with the BRANCH code bind-mounted.
#
# BOUNCE of LOCAL-837. Proves the per-work STORY RESEARCH step
# (work_story_research.py): each selected work's own Wikipedia article is fetched
# (Wikidata QID, EN + local language), the human-event passages are kept and the
# provenance/metadata dropped, and those passages are fed to the story pass as the
# PRIMARY material — replacing the Serper provenance snippets that made 837 land
# Orsay 0/5, Rijks 2/5.
#
# Cheap museum arm, DISABLE_STOP_POOL=1, STORY_PASS_MODEL=gpt-4.1 (the 837 cheap-
# arm remedy), two tours (Orsay 5 + Rijks 5).
# BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-840 TASK_BUDGET_USD=0.90 (whole-task cap).
# PASS = >= 3/5 stops clear the story bar per tour, cost/tour <= $0.45.
#
# THE METER CONTRACT (LOCAL-819/820): bind-mount the shared meterlog dir, write a
# DEDICATED paid_api_calls_local840_accept.jsonl so the enforced $0.90 cap governs
# THIS acceptance run, install the meter via PYTHONPATH=/opt/meter, tag every row
# METER_SERVICE=LOCAL-840. No shared meter rows are rewritten.
#
# Usage: ./run_local840_live.sh [0|1]     # optional single-tour index
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local840"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
ACCEPT_LOG="/meterlogs/paid_api_calls_local840_accept.jsonl"
# Reuse the REAL cached rows for the two venues this ticket needs — identical to
# the 826B/832B/837 fixture (Rijks Q190804 + Orsay Q23402).
SEED_SQL="${HERE}/tests/fixtures/local826b/seed_real_cached_rows.sql"
mkdir -p "${METER_DIR}"
# Start the acceptance ledger empty so the enforced cap governs this run only.
: > "${METER_DIR}/paid_api_calls_local840_accept.jsonl"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local840] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local840] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
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

echo "[local840] creating cache tables on the throwaway DB"
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
  echo "[local840] seeding REAL cached rows for Q23402 (Orsay) + Q190804 (Rijks)"
  docker exec -i "${PG_NAME}" psql -U admin -d audiotours -v ON_ERROR_STOP=0 < "${SEED_SQL}"
  docker exec "${PG_NAME}" psql -U admin -d audiotours -c \
    "SELECT 'venue_corpus' t, qid, corpus_version::text v FROM venue_corpus
     UNION ALL SELECT 'venue_works_cache', qid||'/'||language, source FROM venue_works_cache
     ORDER BY 1,2;"
else
  echo "[local840] WARNING: seed file ${SEED_SQL} not found — running without seed"
fi

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
  -e CHEAP_ARM_CATEGORIES=museum
  -e NARRATION_MODEL=gpt-4.1-mini
  -e SERPER_RESEARCH_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e SERP_PROVIDER=serper
  -e WORK_STORY_RESEARCH=1
  -e WORK_RESEARCH_COST_CEILING=0.03
  -e TASK_BUDGET_ID=LOCAL-840
  -e TASK_BUDGET_USD=0.90
  -e PER_TOUR_PASS_USD=0.45
  -e TEST_GEMINI_MAX_USD=0.90
  -e COST_HARD_LIMIT_USD=0.90
)
# [LOCAL-820] THE METER CONTRACT — canonical args, dedicated acceptance ledger.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG="${ACCEPT_LOG}"
  -e METER_SERVICE=LOCAL-840
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")
# [LOCAL-837] cheap-arm remedy: lift ONLY the story pass to gpt-4.1 (narration
# stays mini). Default to gpt-4.1 for this acceptance; overridable.
args+=(-e "STORY_PASS_MODEL=${STORY_PASS_MODEL:-gpt-4.1}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local840_container.py)
[ -n "${1:-}" ] && args+=("$1")

echo "[local840] ===== running LOCAL-840 live, cap \$0.90, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-840 live run done (rc=${RC}) ####################"
exit "${RC}"
