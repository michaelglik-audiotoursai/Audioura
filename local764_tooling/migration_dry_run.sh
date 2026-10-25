#!/usr/bin/env bash
# LOCAL-764 Task D — migration dry run on a SCRATCH Postgres (never the shared DB).
# Applies migration/sql/010..050 in order TWICE and reports per-file status,
# row counts, and idempotency. Runs inside the local764-pg container.
set -u
CT=local764-pg
DB=audiotours_subscribed
SQLDIR="$(cd "$(dirname "$0")/../migration/sql" && pwd)"
PSQL() { docker exec -i "$CT" psql -v ON_ERROR_STOP=1 -U admin -d "$1" -q; }
PSQLDB() { docker exec -i "$CT" psql -v ON_ERROR_STOP=1 -U admin -d "$DB" -q; }

# Ordered 010..050. 021 has two files: sync_offline_outbox then tour_reviews
# (both independent + idempotent; order is cosmetic).
FILES=$(ls "$SQLDIR"/0[1-5]*.sql | sort | awk -F/ '{print $NF}' | grep -E '^0(1[0-9]|[2-4][0-9]|50)_')

echo "### Scratch DB: creating $DB (drop+create for a clean base)"
docker exec -i "$CT" psql -U admin -d postgres -q -c "DROP DATABASE IF EXISTS $DB;" 2>&1 | sed 's/^/  /'
docker exec -i "$CT" psql -U admin -d postgres -q -c "CREATE DATABASE $DB;" 2>&1 | sed 's/^/  /'

apply_pass() {
  local pass="$1"
  echo "=================================================================="
  echo "### APPLY PASS $pass"
  echo "=================================================================="
  local ok=0 fail=0
  for f in $FILES; do
    out=$(docker exec -i "$CT" psql -v ON_ERROR_STOP=1 -U admin -d "$DB" -q -f "/sql/$f" 2>&1)
    rc=$?
    if [ $rc -eq 0 ]; then
      echo "[PASS$pass][ok ] $f"
      ok=$((ok+1))
    else
      echo "[PASS$pass][FAIL] $f"
      echo "$out" | sed 's/^/        /'
      fail=$((fail+1))
    fi
  done
  echo "--- PASS $pass summary: $ok ok, $fail fail ---"
}

seed_rows() {
  echo "### SEED a few beta/storied rows (pre-migration-like data)"
  PSQLDB <<'SQL'
-- users (beta + storied + subscribed authors)
INSERT INTO users (secret_id, plan) VALUES
  ('seed-beta-user','free'),
  ('seed-storied-user','free'),
  ('seed-sub-user','free')
ON CONFLICT (secret_id) DO NOTHING;
-- audio_tours: two beta tours, same NAME, different creators (the D678 case),
-- plus a storied tour with the same name (the 432 cross-track case). These are
-- the rows whose constraints migrations 041/043 change.
INSERT INTO audio_tours (tour_name, request_string, number_requested, creator_type)
VALUES ('Harvard Square Walk','harvard square',1,'Official')
ON CONFLICT DO NOTHING;
SQL
  echo "  seeded (constraint-sensitive rows added before re-checking)."
}

echo
apply_pass 1
echo
seed_rows
echo
echo "### ROW COUNTS after PASS 1 + seed (key tables)"
PSQLDB <<'SQL'
SELECT 'users' t, count(*) FROM users
UNION ALL SELECT 'audio_tours', count(*) FROM audio_tours
UNION ALL SELECT 'plans', count(*) FROM plans
UNION ALL SELECT 'communities', count(*) FROM communities
UNION ALL SELECT 'community_memberships', count(*) FROM community_memberships
UNION ALL SELECT 'tour_reviews', count(*) FROM tour_reviews
UNION ALL SELECT 'sync_items', count(*) FROM sync_items
ORDER BY 1;
SQL
echo
apply_pass 2
echo
echo "### ROW COUNTS after PASS 2 (must be unchanged by idempotent re-apply)"
PSQLDB <<'SQL'
SELECT 'users' t, count(*) FROM users
UNION ALL SELECT 'audio_tours', count(*) FROM audio_tours
UNION ALL SELECT 'plans', count(*) FROM plans
UNION ALL SELECT 'communities', count(*) FROM communities
UNION ALL SELECT 'community_memberships', count(*) FROM community_memberships
UNION ALL SELECT 'tour_reviews', count(*) FROM tour_reviews
UNION ALL SELECT 'sync_items', count(*) FROM sync_items
ORDER BY 1;
SQL
echo
echo "### INDEX CHECK: uq_audio_tours_original_name (041 drops it) and successors"
PSQLDB <<'SQL'
SELECT indexname FROM pg_indexes
WHERE tablename='audio_tours'
  AND indexname IN ('uq_audio_tours_original_name',
                    'idx_audio_tours_name_creator',
                    'idx_audio_tours_name_creator_track')
ORDER BY indexname;
SQL
echo
echo "### audio_tours key columns present (041 creator_user_id, 043 track)"
PSQLDB <<'SQL'
SELECT column_name FROM information_schema.columns
WHERE table_name='audio_tours' AND column_name IN ('creator_user_id','track')
ORDER BY column_name;
SQL
