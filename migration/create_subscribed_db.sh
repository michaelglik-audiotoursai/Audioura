#!/usr/bin/env bash
# ============================================================================
# create_subscribed_db.sh — Create audiotours_subscribed and apply schema
# LOCAL-211: Subscribed database preparation
# ============================================================================
#
# IDEMPOTENT: Safe to run multiple times. CREATE DATABASE checks existence,
# schema uses IF NOT EXISTS throughout.
#
# USAGE:
#   ./migration/create_subscribed_db.sh
#
# REQUIRES:
#   - development-postgres-2-1 container running (port 5433 on host)
#   - docker exec access
#
# ENVIRONMENT (all read from env, no hardcoded credentials):
#   DB_HOST       — default: localhost
#   DB_PORT       — default: 5433 (host-mapped port for postgres-2)
#   DB_USER       — default: admin
#   DB_PASSWORD   — default: password123  (dev-only default, never production)
#   POSTGRES_CONTAINER — default: development-postgres-2-1
# ============================================================================

set -euo pipefail

# Configuration from environment
CONTAINER="${POSTGRES_CONTAINER:-development-postgres-2-1}"
DB_USER="${DB_USER:-admin}"
DB_NAME="audiotours_subscribed"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_SQL="${SCRIPT_DIR}/sql/010_create_subscribed_database.sql"

echo "═══════════════════════════════════════════════════════════════"
echo "LOCAL-211: Create audiotours_subscribed database"
echo "═══════════════════════════════════════════════════════════════"
echo "Container: ${CONTAINER}"
echo "User:      ${DB_USER}"
echo "Database:  ${DB_NAME}"
echo "Migration: ${MIGRATION_SQL}"
echo ""

# ─── Step 1: Check container is running ─────────────────────────────────────
if ! docker inspect --format='{{.State.Running}}' "${CONTAINER}" 2>/dev/null | grep -q true; then
    echo "ERROR: Container '${CONTAINER}' is not running."
    echo "       Start it with: docker compose up -d postgres-2"
    exit 1
fi

# ─── Step 2: Create database if not exists (idempotent) ─────────────────────
echo "Step 1: Creating database '${DB_NAME}' (if not exists)..."
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d postgres -tc \
    "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1 \
    && echo "  Database already exists — skipping CREATE." \
    || {
        docker exec "${CONTAINER}" psql -U "${DB_USER}" -d postgres -c \
            "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
        echo "  Created database '${DB_NAME}'."
    }

# ─── Step 3: Apply schema migration ────────────────────────────────────────
echo ""
echo "Step 2: Applying schema migration..."
if [ ! -f "${MIGRATION_SQL}" ]; then
    echo "ERROR: Migration file not found: ${MIGRATION_SQL}"
    exit 1
fi

docker exec -i "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" < "${MIGRATION_SQL}"
echo "  Schema applied successfully."

# ─── Step 4: Verify ─────────────────────────────────────────────────────────
echo ""
echo "Step 3: Verification — tables in ${DB_NAME}:"
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "\dt"

echo ""
echo "Step 4: Row counts (all should be 0 except plans which has 3 seed rows):"
docker exec "${CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" -c "
SELECT schemaname, tablename,
       (xpath('/row/cnt/text()', xml_count))[1]::text::int AS row_count
FROM (
    SELECT schemaname, tablename,
           query_to_xml('SELECT count(*) AS cnt FROM ' || schemaname || '.' || tablename, false, true, '')
           AS xml_count
    FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename
) t;
"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Done. audiotours_subscribed is ready."
echo "═══════════════════════════════════════════════════════════════"
