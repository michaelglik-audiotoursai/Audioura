#!/bin/zsh
# Guard what Michael actually sees in the app.
#
# WHY: the row-loss alarm (backup_tours.sh) catches DELETION — that was the
# tour-29 incident. On 2026-08-01 the opposite happened: LOCAL-88 left 11
# test tours VISIBLE in Michael's Nice list, two of them named "Musée
# Matisse, Nice" and "Musée des Arts Asiatiques, Nice" — indistinguishable
# from real tours. Row count went UP, so the existing alarm stayed silent.
# It was caught only because LEAD happened to run the acceptance check.
#
# This watches the endpoint the app actually calls and alarms on ANY drift,
# in either direction.

CD="$HOME/Audioura/.continuous_dev"
ALERTS="$CD/ALERTS.md"
LOG="$HOME/audioura-backups/backup.log"

# Michael's real tours near Nice. Update deliberately when he gains or
# retires one — never to silence an alarm.
EXPECTED="1,12,14,17,21,24,27,28,29"

ACTUAL=$(curl -s -m 20 "http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50" 2>/dev/null \
  | /usr/bin/python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)          # unreachable service is not drift; stay silent
ts = d if isinstance(d, list) else d.get('tours', [])
print(','.join(str(t['id']) for t in sorted(ts, key=lambda x: x['id'])))
" 2>/dev/null)

# No answer at all: the service is down or restarting. Not drift.
[ -z "$ACTUAL" ] && exit 0

if [ "$ACTUAL" != "$EXPECTED" ]; then
  MSG="$(date -u +%FT%TZ) | *** USER-VISIBLE DRIFT: tours-near returned [$ACTUAL], expected [$EXPECTED] ***"
  echo "$MSG" >> "$ALERTS"
  echo "$MSG" >> "$LOG"
fi
