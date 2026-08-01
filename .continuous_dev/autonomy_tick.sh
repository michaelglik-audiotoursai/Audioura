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

# --- Dispatch any unclaimed task files. ---
# The dispatcher is idempotent: already-claimed files are skipped, and
# MAX_CONCURRENT bounds the worker count. Safe to run every 5 minutes.
/usr/bin/python3 "$REPO/kiro_dispatcher.py" >> "$LOG" 2>&1
echo "$(date -u +%FT%TZ) | tick complete (unpushed=$UNPUSHED)" >> "$LOG"
