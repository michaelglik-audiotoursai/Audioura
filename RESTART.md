# RESTART briefing — generated 2026-08-10 14:17 EDT

## Git
```
branch   storied
HEAD     ceb61bf D291: the MFA exhibition tour generates and is about the exhibition
unpushed 1 commits
dirty    5 files
```

## Production safety
```
audio_tours real rows: 31
  A DROP is an incident (CLAUDE.md). Growth is normal — Michael generating a tour
  adds a row, and its translation adds another. 29 was a snapshot, never a law.
cost_ledger rows:      307
```
ALERTS.md: 17 alert line(s) in the last 40 — read it if non-zero.

## Queue
```
in flight:

last 6 dispatcher events:
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-370.md | id=TLOCAL-370 | branch=kiro/local-370 | base=storied | 
   - STARTED   | task=new_kiro_session_is_required_LOCAL-371.md | at=2026-08-10T13:16:20-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-371.md | id=TLOCAL-371 | branch=kiro/local-371 | base=storied | 
   - STARTED   | task=new_kiro_session_is_required_LOCAL-372.md | at=2026-08-10T13:33:26-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-372.md | id=TLOCAL-372 | branch=kiro/local-372 | base=storied | 
   - STARTED   | task=new_kiro_session_is_required_LOCAL-373.md | at=2026-08-10T14:07:38-04:00 | base=storied | dispatche
```

## Re-dispatchable (last status ABANDONED — a bounce awaiting pickup)
  (none — every task file is claimed or finished)

## Parked (deliberately outside the dispatcher glob — do NOT re-dispatch)
  - PARKED_kiro_task_LOCAL-335.md

## Honest tour scores (corpus-loaded scorer, recompute — do not quote from memory)
```
   LOCAL347_museum_4stop.txt            base= 81.2
   LOCAL346b_walking_4stop.txt          base= 87.5
   LOCAL352b_restaurant_4stop.txt       base= 68.8
   LOCAL320_museum_8stop.txt            base= 75.0
```

## Generating a tour from the host — REQUIRED env (D261)
```
DISABLE_TOUR_CACHE=1 \
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
STORIED_MODE=true OPENAI_API_KEY=... python3 -c "..."
# no DISABLE_TOUR_CACHE -> you may score a CACHED tour (D262)
# no DATABASE_URL      -> stop-existence gate SILENTLY does not run (D261)
```

## Pending reminders for Michael

## Read next, in this order
- `CLAUDE.md`            — RULE ZERO (do not stop and ask) + live-DB rules
- `DECISIONS.md`         — tail -120; D2xx are the recent rulings
- `.continuous_dev/STATUS.md` — tail -80; last tick
- `TOUR_REVIEW_current.md`     — current quality position (3x4stop.md is SUPERSEDED)

## Standing checks that have caught something every time (D242)
1. Break the production code — confirm a test goes red. A test that cannot fail is not evidence.
2. `grep` for a production importer before believing a module does anything.
3. Re-run the agent's own number against a case whose answer you already know.
4. Accent-fold every `stop_corpus` join (D243) — exact match on French titles silently reports absence.
5. Before writing ABANDONED, `kill -0` the `dispatcher_pid` in the STARTED line (D246).
