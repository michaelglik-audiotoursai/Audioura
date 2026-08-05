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
# 152 added 2026-08-04: the French Riviera cycling tour Michael asked LEAD to
# generate so he could compare it paragraph-by-paragraph with his field-tested
# tour 29. Real generation, real coords, is_test=false — a deliberate gain,
# not a leaked test artifact.
# 2026-08-05: 21, 27, 28 (Asian Arts Museum) retired at Michael's instruction.
# Their stops were invented — the venue has no venue_corpus row at all, so the
# model produced plausible object names and narrated them. His verdict on the
# Chikanobu print: "has nothing to do with Nice museum and should be excluded
# entirely as false." Coordinates nulled, not deleted; backup at
# ~/audioura-backups/coords_asian_arts_20260805T003824.json
EXPECTED="1,12,14,17,24,29,152"

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

# --- Unflagged test tours, anywhere on earth. ---
#
# WHY: the check above watches ONE location (Nice). On 2026-08-02 test suites
# run during a task created tour 132, "LOCAL49 Regression Test ... Walking
# Tour", with is_test=false and real Seattle coordinates. tours-near filters
# on is_test, so it was live at 47.6098/-122.3423 — and the Nice check stayed
# silent because it looks at Nice. A location-scoped guard cannot catch a
# tour planted somewhere else.
#
# tours-near filters on is_test, so an is_test=false row named like a test
# IS user-visible wherever it sits. Alarm on the flag, not on the place.
UNFLAGGED=$(docker exec development-postgres-2-1 psql -U admin -d audiotours -t -A \
  -c "SELECT string_agg(id::text, ',' ORDER BY id) FROM audio_tours
      WHERE tour_name ~ '(LOCAL[0-9]+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)'
        AND is_test IS NOT TRUE;" 2>/dev/null)

if [ -n "$UNFLAGGED" ]; then
  MSG="$(date -u +%FT%TZ) | *** UNFLAGGED TEST TOURS VISIBLE: ids [$UNFLAGGED] — is_test is not true, tours-near will serve them ***"
  echo "$MSG" >> "$ALERTS"
  echo "$MSG" >> "$LOG"
fi
