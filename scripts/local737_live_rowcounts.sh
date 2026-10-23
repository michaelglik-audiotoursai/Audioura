#!/usr/bin/env bash
# local737_live_rowcounts.sh — LOCAL-737 live-test row counts.
#
# Reports per-track counts in the ISOLATED local737 Postgres (postgres-737),
# so a run can be shown "before" and "after" a single subscribed generation.
# Reads the throwaway stack only — never the shared postgres-2.
#
# Usage:
#   scripts/local737_live_rowcounts.sh before
#   scripts/local737_live_rowcounts.sh after
#
# It talks to the local737 postgres container by project label.
set -euo pipefail

LABEL="${1:-now}"
CID="$(docker ps -q -f "label=com.docker.compose.project=local737" -f "label=com.docker.compose.service=postgres-737" | head -n1)"
if [ -z "$CID" ]; then
  echo "postgres-737 container not found (is the local737 stack up?)" >&2
  exit 1
fi

echo "===== LOCAL-737 row counts [$LABEL] ====="
docker exec -i "$CID" psql -U admin -d audiotours -tA <<'SQL'
SELECT 'audio_tours total: ' || count(*) FROM audio_tours;
SELECT 'audio_tours by track:';
SELECT '  ' || COALESCE(track,'<null>') || ' = ' || count(*)
  FROM audio_tours GROUP BY track ORDER BY track;
SELECT 'audio_tour_versions total: ' || count(*) FROM audio_tour_versions;
SQL
echo "========================================="
