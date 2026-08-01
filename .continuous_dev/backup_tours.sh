#!/bin/zsh
# Snapshot audio_tours before anything can destroy it again.
#
# WHY: on 2026-08-01 tour 29 (Michael's French Riviera biking tour, which he
# had downloaded and field-tested) plus its two translations 34/35 vanished
# from audio_tours during autonomous operation. Recovery was only possible
# because the ZIP and source text happened to still be on disk. Nothing
# guaranteed that. This makes recovery guaranteed.
#
# Run from the launchd tick. Keeps the last 12 snapshots.

BK="$HOME/audioura-backups"
mkdir -p "$BK"

COUNT=$(docker exec development-postgres-2-1 psql -U admin -d audiotours -t -A \
        -c "SELECT count(*) FROM audio_tours;" 2>/dev/null)

# Refuse to snapshot if the DB is unreachable — an empty "backup" that
# overwrites nothing is fine, but one that looks valid is worse than none.
if [ -z "$COUNT" ]; then
  echo "$(date -u +%FT%TZ) | BACKUP SKIPPED: database unreachable" >> "$BK/backup.log"
  exit 0
fi

LAST_COUNT_FILE="$BK/.last_count"
LAST=$(cat "$LAST_COUNT_FILE" 2>/dev/null || echo 0)

# Loud alarm on row loss. This is the signal that would have caught the
# tour-29 deletion within five minutes instead of by chance.
if [ "$COUNT" -lt "$LAST" ]; then
  echo "$(date -u +%FT%TZ) | *** ROW LOSS: audio_tours went $LAST -> $COUNT ***" >> "$BK/backup.log"
  echo "$(date -u +%FT%TZ) | *** ROW LOSS: audio_tours went $LAST -> $COUNT ***" \
       >> "$HOME/Audioura/.continuous_dev/ALERTS.md"
fi
echo "$COUNT" > "$LAST_COUNT_FILE"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec development-postgres-2-1 pg_dump -U admin -d audiotours \
        -t audio_tours --data-only 2>/dev/null | gzip > "$BK/audio_tours_$STAMP.sql.gz"

# Keep the newest 12 snapshots; drop the rest.
ls -1t "$BK"/audio_tours_*.sql.gz 2>/dev/null | tail -n +13 | while read -r old; do
  rm -f "$old"
done

echo "$(date -u +%FT%TZ) | snapshot ok, rows=$COUNT" >> "$BK/backup.log"
