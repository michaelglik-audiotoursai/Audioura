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

# An id+name manifest, refreshed every tick. A few KB, so unlike the 224 MB
# dumps it can be kept for a long time — and it is what actually attributes a
# loss. On 2026-08-05 the alarm said "145 -> 144" and nothing else; by the time
# anyone read it the snapshots that would have named the row had rotated out,
# and the deletion is still unattributed. Diffing the manifest names the row at
# the moment it disappears, which is the only moment the name still exists.
MANIFEST="$BK/.manifest_ids"
NEW_MANIFEST=$(mktemp)
docker exec development-postgres-2-1 psql -U admin -d audiotours -t -A -F'|' \
        -c "SELECT id, coalesce(is_test::text,'?'), left(coalesce(tour_name,''),60)
            FROM audio_tours ORDER BY id;" 2>/dev/null > "$NEW_MANIFEST"

# Alarm on row loss. This is the signal that would have caught the tour-29
# deletion within five minutes instead of by chance.
#
# Severity depends on WHAT was lost, not on the count moving. A task deleting
# its own is_test rows by captured id is required cleanup, and on 2026-08-05
# that fired a *** ROW LOSS *** that cost a morning to run down (LOCAL-244
# removing its own tours 200/201). An alarm that cries wolf on correct
# behaviour is one that stops being read — which is precisely how tour 29 went
# unnoticed. So: is_test rows log quietly, real tours still scream.
if [ "$COUNT" -lt "$LAST" ]; then
  REAL_LOST=0
  LOST_LINES=""
  if [ -s "$MANIFEST" ]; then
    while read -r lost_id; do
      LINE=$(grep -m1 "^${lost_id}|" "$MANIFEST")
      LOST_LINES="${LOST_LINES}    LOST ROW: ${LINE}\n"
      case "$LINE" in
        *"|true|"*) ;;                    # a test row cleaning up after itself
        *) REAL_LOST=$((REAL_LOST + 1)) ;;  # a real tour, or is_test unknown
      esac
    done < <(comm -23 <(cut -d'|' -f1 "$MANIFEST") <(cut -d'|' -f1 "$NEW_MANIFEST"))
    # Keep the pre-loss manifest as evidence; it is tiny and never rotated.
    cp "$MANIFEST" "$BK/manifest_preloss_$(date -u +%Y%m%dT%H%M%SZ).txt"
  else
    REAL_LOST=1   # no manifest to judge by — assume the worst and shout
  fi

  if [ "$REAL_LOST" -gt 0 ]; then
    MSG="$(date -u +%FT%TZ) | *** ROW LOSS: audio_tours went $LAST -> $COUNT ($REAL_LOST non-test) ***"
    echo "$MSG" >> "$BK/backup.log"
    printf "%b" "$MSG\n$LOST_LINES" >> "$HOME/Audioura/.continuous_dev/ALERTS.md"
  else
    MSG="$(date -u +%FT%TZ) | test-row cleanup: audio_tours went $LAST -> $COUNT, all is_test"
    echo "$MSG" >> "$BK/backup.log"
  fi
  printf "%b" "$LOST_LINES" >> "$BK/backup.log"
fi
mv "$NEW_MANIFEST" "$MANIFEST"
echo "$COUNT" > "$LAST_COUNT_FILE"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec development-postgres-2-1 pg_dump -U admin -d audiotours \
        -t audio_tours --data-only 2>/dev/null | gzip > "$BK/audio_tours_$STAMP.sql.gz"

# Keep the newest 12 snapshots. These are ~224 MB each because the table
# carries audio blobs, so 12 is already ~2.7 GB and the retention cannot be
# extended for the sake of investigation — the disk hit 98% on 2026-08-04.
ls -1t "$BK"/audio_tours_*.sql.gz 2>/dev/null | tail -n +13 | while read -r old; do
  rm -f "$old"
done

echo "$(date -u +%FT%TZ) | snapshot ok, rows=$COUNT" >> "$BK/backup.log"
