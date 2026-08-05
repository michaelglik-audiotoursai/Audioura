#!/bin/zsh
# Durable continuous-development tick. Run by launchd every 5 minutes.
#
# WHY THIS EXISTS: Claude's review loop is session-scoped and dies with the
# session (crash, timeout, usage limit). The Kiro dispatcher is a plain
# Python script that needs nothing from Claude. This wrapper keeps task
# EXECUTION alive across session death, reboots and usage limits, so a
# 3-day unattended stretch keeps making progress even with no Claude
# session alive at all. Reviews still need a session — they queue up.
#
# Michael, 2026-07-31: "If all time-related credits are used, you should be
# able to revive yourself when time passes."

REPO="$HOME/Audioura"
CD="$REPO/.continuous_dev"
LOG="$CD/autonomy.log"

cd "$REPO" || exit 1

# Respect the pause sentinel — Michael can touch/rm it directly.
if [ -f "$CD/PAUSE" ]; then
  echo "$(date -u +%FT%TZ) | PAUSED (sentinel present)" >> "$LOG"
  exit 0
fi

# --- Gate: Subscribed work must not start until storied is fully pushed. ---
# Michael, 2026-07-31: "only start working on Subscribed AFTER Storied was
# fully pushed to original". Rather than have a human create the gate file,
# derive it from the fact itself.
UNPUSHED=$(git rev-list --count origin/storied..storied 2>/dev/null)
if [ -n "$UNPUSHED" ] && [ "$UNPUSHED" -eq 0 ]; then
  if [ ! -f "$REPO/SUBSCRIBED_CLEARED.md" ]; then
    cat > "$REPO/SUBSCRIBED_CLEARED.md" <<INNER
# SUBSCRIBED WORK CLEARED

storied is fully pushed to origin (0 commits ahead) as of $(date -u +%FT%TZ).
Michael's gate is satisfied: "only start working on Subscribed AFTER Storied
was fully pushed to original."

Subscribed task files may now be dispatched. Created automatically by
.continuous_dev/autonomy_tick.sh — derived from the push state itself, not
from anyone's say-so.
INNER
    echo "$(date -u +%FT%TZ) | GATE OPENED: storied fully pushed, Subscribed cleared" >> "$LOG"
  fi
else
  echo "$(date -u +%FT%TZ) | gate closed: $UNPUSHED commits still unpushed" >> "$LOG"
fi

# --- Snapshot audio_tours and alarm on row loss. ---
# Added 2026-08-01 after tour 29 and its translations were deleted during
# autonomous operation and only recovered by luck (ZIP still on disk).
"$CD/backup_tours.sh"

# --- Guard what Michael actually sees in the app. ---
# The row-loss alarm catches deletion; this catches the opposite failure —
# test tours becoming visible, which happened 2026-08-01 with row count UP.
"$CD/check_user_visible.sh"

# --- Reap orphaned kiro processes; quarantine tasks that keep dying. ---
# Added 2026-08-01: LOCAL-112/113 each died twice with no log, swap at 91%,
# and every death leaked an orphaned kiro-cli. The liveness check kept
# re-dispatching them into the same wall.
"$CD/reap_orphans.sh"

# --- Reclaim disk: drop worktrees whose branch is already merged. ---
# Added 2026-08-04 after 188 accumulated worktrees filled the disk to 98% and
# a dispatch failed mid-checkout. Nothing is lost; unmerged branches are kept.
"$CD/prune_worktrees.sh"

# --- Dispatch any unclaimed task files. ---
# The dispatcher is idempotent: already-claimed files are skipped, and
# MAX_CONCURRENT bounds the worker count. Safe to run every 5 minutes.
/usr/bin/python3 "$REPO/kiro_dispatcher.py" >> "$LOG" 2>&1
echo "$(date -u +%FT%TZ) | tick complete (unpushed=$UNPUSHED)" >> "$LOG"

# --- Secret scan of the pushed tip (LOCAL-207 / D81). ---
# Two live credentials sat on origin for months because nothing looked. This
# scans the last 20 commits each tick and alarms; it does not block.
if [ -f "$REPO/secret_scan.py" ]; then
  /usr/bin/python3 "$REPO/secret_scan.py" --range "origin/storied~20..origin/storied" >/tmp/secret_tick.out 2>&1
  # The scanner's own docs and tests carry invented fixtures by design; a
  # standing alarm on them would train us to ignore this line. Filter them out
  # and alarm only on what is left.
  # Drop findings LEAD has reviewed and cleared. Entries are pinned to a
  # specific commit:path:line — never a filename or a directory — so a real key
  # added to the same file tomorrow still fires. See secret_scan_cleared.txt.
  CLEARED="$CD/secret_scan_cleared.txt"
  REAL=$(grep -E "^\s+\[" /tmp/secret_tick.out \
         | grep -v "SUBMISSION_LOCAL-207.md" \
         | grep -v "tests/test_secret_scan.py" \
         | grep -v "secret_scan.py" \
         | while read -r line; do
             KEY=$(echo "$line" | sed -E 's/.*\] ([0-9a-f]+) [0-9-]+ ([^ ]+):([0-9]+).*/\1:\2:\3/')
             SHORT=$(echo "$KEY" | cut -c1-7)
             REST=$(echo "$KEY" | cut -d: -f2-)
             grep -qs "^${SHORT}:${REST}[[:space:]]" "$CLEARED" || echo "$line"
           done | wc -l | tr -d " ")
  if [ "$REAL" != "0" ]; then
    echo "$(date -u +%FT%TZ) | *** SECRET DETECTED in recent storied commits ($REAL finding/s) — see /tmp/secret_tick.out ***" >> "$CD/ALERTS.md"
  fi
fi
