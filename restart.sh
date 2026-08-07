#!/bin/bash
# restart.sh — one-command session handoff.
#
# Michael says "Restart"; the new session runs this and is current.
# Everything below is read from live state, never from memory, because a fresh
# session has none. Keep the output SHORT — it is read on every restart and a
# long briefing is the thing we are trying to avoid paying for.
#
# Usage:  bash restart.sh
# Writes: RESTART.md  (also prints to stdout)

cd "$(dirname "$0")" || exit 1
PSQL="docker exec development-postgres-2-1 psql -U admin -d audiotours -tAc"

{
echo "# RESTART briefing — generated $(date '+%Y-%m-%d %H:%M %Z')"
echo
echo "## Git"
echo '```'
echo "branch   $(git rev-parse --abbrev-ref HEAD)"
echo "HEAD     $(git log --oneline -1)"
echo "unpushed $(git rev-list --count origin/storied..storied 2>/dev/null) commits"
echo "dirty    $(git status --short | wc -l | tr -d ' ') files"
echo '```'
echo
echo "## Production safety"
REAL=$($PSQL "SELECT count(*) FROM audio_tours WHERE is_test IS NOT TRUE;" 2>/dev/null)
echo '```'
echo "audio_tours real rows: ${REAL:-UNREACHABLE}   (must be 29 — a drop is an incident, see CLAUDE.md)"
echo "cost_ledger rows:      $($PSQL 'SELECT count(*) FROM cost_ledger;' 2>/dev/null)"
echo '```'
if [ -f .continuous_dev/ALERTS.md ]; then
  RECENT=$(tail -40 .continuous_dev/ALERTS.md | grep -c "\*\*\*" 2>/dev/null)
  echo "ALERTS.md: $RECENT alert line(s) in the last 40 — read it if non-zero."
fi
echo
echo "## Queue"
echo '```'
echo "in flight:"
ps aux | grep "[k]iro-cli chat" | grep -oE "Task ID:\*\* LOCAL-[0-9]+" | sort -u | sed 's/^/   /' || echo "   (none)"
echo
echo "last 6 dispatcher events:"
tail -6 kiro_sessions_ran.md 2>/dev/null | cut -c1-118 | sed 's/^/   /'
echo '```'
echo
echo "## Re-dispatchable (last status ABANDONED — a bounce awaiting pickup)"
FOUND=0
for f in new_kiro_session_is_required_LOCAL-*.md; do
  [ -e "$f" ] || continue
  LAST=$(grep "task=$f" kiro_sessions_ran.md 2>/dev/null | tail -1 | sed -E 's/^- ([A-Z]+).*/\1/')
  if [ "$LAST" = "ABANDONED" ]; then
    echo "  - ${f#new_kiro_session_is_required_}"
    FOUND=1
  fi
done
[ "$FOUND" = "0" ] && echo "  (none — every task file is claimed or finished)"
echo
echo "## Parked (deliberately outside the dispatcher glob — do NOT re-dispatch)"
ls PARKED_kiro_task_*.md 2>/dev/null | sed 's/^/  - /' || echo "  (none)"
echo
echo "## Honest tour scores (corpus-loaded scorer, recompute — do not quote from memory)"
echo '```'
python3 - <<'PY' 2>/dev/null | sed 's/^/   /'
import sys, os
sys.path.insert(0, os.getcwd())
try:
    from tour_rubric_scorer import score_tour_file
    # Newest file per category, so this never goes stale as tours are regenerated.
    import glob
    def newest(pat):
        c = sorted(glob.glob(pat), key=os.path.getmtime, reverse=True)
        return c[0] if c else None
    picks = [(newest('tours/*museum_4stop*.txt'), 4), (newest('tours/*walking_4stop*.txt'), 4),
             (newest('tours/*restaurant_4stop*.txt'), 4), ('tours/LOCAL320_museum_8stop.txt', 8)]
    for f, n in [(a, b) for a, b in picks if a]:
        if os.path.exists(f):
            print(f"{os.path.basename(f)[:34]:36s} base={score_tour_file(f, n).base_score:5.1f}")
except Exception as e:
    print(f"(scorer unavailable: {type(e).__name__})")
PY
echo '```'
echo
echo "## Generating a tour from the host — REQUIRED env (D261)"
echo '```'
echo 'DISABLE_TOUR_CACHE=1 \'
echo 'DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \'
echo 'STORIED_MODE=true OPENAI_API_KEY=... python3 -c "..."'
echo '# no DISABLE_TOUR_CACHE -> you may score a CACHED tour (D262)'
echo '# no DATABASE_URL      -> stop-existence gate SILENTLY does not run (D261)'
echo '```'
echo
echo "## Read next, in this order"
echo '- `CLAUDE.md`            — RULE ZERO (do not stop and ask) + live-DB rules'
echo '- `DECISIONS.md`         — tail -120; D2xx are the recent rulings'
echo '- `.continuous_dev/STATUS.md` — tail -80; last tick'
echo '- `TOUR_REVIEW_current.md`     — current quality position (3x4stop.md is SUPERSEDED)'
echo
echo "## Standing checks that have caught something every time (D242)"
echo '1. Break the production code — confirm a test goes red. A test that cannot fail is not evidence.'
echo '2. `grep` for a production importer before believing a module does anything.'
echo '3. Re-run the agent'"'"'s own number against a case whose answer you already know.'
echo '4. Accent-fold every `stop_corpus` join (D243) — exact match on French titles silently reports absence.'
echo '5. Before writing ABANDONED, `kill -0` the `dispatcher_pid` in the STARTED line (D246).'
} | tee RESTART.md
