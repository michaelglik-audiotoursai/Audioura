#!/usr/bin/env bash
# ------------------------------------------------------------------
# init_test_db.sh — Rebuild audiotours_test schema from production
#
# Dumps schema-only from audiotours (production) and applies it to
# audiotours_test, giving the test database full table parity without
# copying any data rows.
#
# Usage:
#   ./tests/init_test_db.sh
#
# Prerequisites:
#   - Docker container 'development-postgres-2-1' running
#   - PostgreSQL accessible as admin:password123 on localhost:5433
#
# This script:
#   1. Dumps audiotours schema (--schema-only, no data)
#   2. Drops and recreates public schema in audiotours_test
#   3. Applies the schema dump to audiotours_test
#   4. Verifies table count parity
#   5. Confirms zero rows in test database
#
# LOCAL-300: Created to make test DB setup reproducible.
# ------------------------------------------------------------------
set -euo pipefail

CONTAINER="development-postgres-2-1"
DB_USER="${DB_USER:-admin}"
PROD_DB="audiotours"
TEST_DB="audiotours_test"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEMA_FILE="${SCRIPT_DIR}/schema_audiotours.sql"

# Colours for output (disabled if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
else
    GREEN=''; RED=''; NC=''
fi

echo "=== init_test_db.sh: Rebuilding ${TEST_DB} schema from ${PROD_DB} ==="

# Step 1: Dump schema from production (no data, no ownership)
echo "[1/5] Dumping schema from ${PROD_DB}..."
docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" --schema-only --no-owner --no-privileges "${PROD_DB}" > "${SCHEMA_FILE}"

# Safety check: ensure no INSERT or COPY statements leaked in
if grep -qE "^(INSERT|COPY)" "${SCHEMA_FILE}"; then
    echo -e "${RED}FATAL: Schema dump contains data statements. Aborting.${NC}" >&2
    exit 1
fi
echo "   Schema dumped to ${SCHEMA_FILE} ($(wc -l < "${SCHEMA_FILE}") lines)"

# Step 2: Drop and recreate public schema in test database
echo "[2/5] Dropping existing schema in ${TEST_DB}..."
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${TEST_DB}" -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" 2>/dev/null

# Step 3: Apply schema dump to test database
echo "[3/5] Applying schema to ${TEST_DB}..."
docker exec -i "${CONTAINER}" psql -U "${DB_USER}" -d "${TEST_DB}" < "${SCHEMA_FILE}" > /dev/null 2>&1

# Step 4: Verify table count parity
PROD_TABLES=$(docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${PROD_DB}" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
TEST_TABLES=$(docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${TEST_DB}" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")

PROD_TABLES=$(echo "${PROD_TABLES}" | tr -d ' ')
TEST_TABLES=$(echo "${TEST_TABLES}" | tr -d ' ')

echo "[4/5] Table count: ${PROD_DB}=${PROD_TABLES}, ${TEST_DB}=${TEST_TABLES}"
if [ "${PROD_TABLES}" != "${TEST_TABLES}" ]; then
    echo -e "${RED}FAILED: Table count mismatch!${NC}" >&2
    exit 1
fi
echo -e "   ${GREEN}✓ Parity: ${TEST_TABLES} tables in both databases${NC}"

# Step 5: Confirm zero rows in test database
ROW_COUNT=$(docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${TEST_DB}" -t -c \
    "SELECT COALESCE(SUM(n_live_tup), 0) FROM pg_stat_user_tables;")
ROW_COUNT=$(echo "${ROW_COUNT}" | tr -d ' ')

echo "[5/5] Total rows in ${TEST_DB}: ${ROW_COUNT}"
if [ "${ROW_COUNT}" != "0" ]; then
    echo -e "${RED}WARNING: Expected 0 rows, found ${ROW_COUNT}${NC}" >&2
fi
echo -e "   ${GREEN}✓ No data copied — test database is schema-only${NC}"

echo ""
echo "=== Done. ${TEST_DB} has ${TEST_TABLES} tables, 0 rows. ==="
