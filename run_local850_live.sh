#!/usr/bin/env bash
# run_local850_live.sh — LOCAL-850 isolated live run in DISPOSABLE containers
# under project "local850". NEVER an audioura-* container, never the live/shared
# DB. Spins up its OWN throwaway postgres (local850-postgres) with EMPTY cache
# tables (NO seed — the resolver must resolve "Rijks Museum Amsterdam" from
# scratch, which is the whole point), then runs run_local850_container.py on the
# audioura-tour-generator IMAGE with the BRANCH code bind-mounted.
#
# Proves: "Rijks Museum Amsterdam, Netherlands" (5) -> Rijksmuseum (Q190804),
# Amsterdam, NEVER Kröller-Müller / Honfleur; "Musee d Orsay Paris" (5) -> Orsay.
# POOL IS ON (the ticket requires it; an unresolved venue must not be pooled).
#
# BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-850 TASK_BUDGET_USD=0.60; per-tour <= $0.40.
# Cheap museum arm + STORY_PASS_MODEL=gpt-4.1 (story pass only; narration mini).
#
# THE METER CONTRACT (LOCAL-819/820): bind-mount the shared meterlog dir, write a
# DEDICATED paid_api_calls_local850_accept.jsonl so the enforced cap governs THIS
# run, install the meter via PYTHONPATH=/opt/meter, tag rows METER_SERVICE=LOCAL-850.
#
# Usage: ./run_local850_live.sh [0|1]     # optional single-tour index
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local850"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
ACCEPT_LOG="/meterlogs/paid_api_calls_local850_accept.jsonl"
mkdir -p "${METER_DIR}"
: > "${METER_DIR}/paid_api_calls_local850_accept.jsonl"

cleanup () {
  docker rm -f "${TG_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local850] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local850] starting throwaway postgres ${PG_NAME} (own data, never live DB)"
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

echo "[local850] creating EMPTY cache + pool tables on the throwaway DB (NO seed)"
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
  -e STOP_EXISTENCE_GATE_MODE=log_only
  -e CHEAP_ARM_CATEGORIES=museum
  -e NARRATION_MODEL=gpt-4.1-mini
  -e SERPER_RESEARCH_MODEL=gpt-4.1-mini
  -e RESEARCH_BACKEND=serper
  -e SERP_PROVIDER=serper
  -e STORY_PASS_MODEL=gpt-4.1
  -e TASK_BUDGET_ID=LOCAL-850
  -e TASK_BUDGET_USD=0.60
  -e PER_TOUR_PASS_USD=0.40
  -e TEST_GEMINI_MAX_USD=0.60
  -e COST_HARD_LIMIT_USD=0.60
)
# [LOCAL-820] THE METER CONTRACT — canonical args, dedicated acceptance ledger.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG="${ACCEPT_LOG}"
  -e METER_SERVICE=LOCAL-850
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local850_container.py)
[ -n "${1:-}" ] && args+=("$1")

echo "[local850] ===== running LOCAL-850 live, cap \$0.60, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-850 live run done (rc=${RC}) ####################"
exit "${RC}"
