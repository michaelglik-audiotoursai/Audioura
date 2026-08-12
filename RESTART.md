# RESTART briefing — generated 2026-08-12 16:27 EDT

## Git
```
branch   storied
HEAD     26b6955 D408: LOCAL-447 merge record — Wayback rejected by measurement, wiring gated off
unpushed 194 commits
dirty    17 files
```

## Production safety
```
audio_tours real rows: 31
  A DROP is an incident (CLAUDE.md). Growth is normal — Michael generating a tour
  adds a row, and its translation adds another. 29 was a snapshot, never a law.
cost_ledger rows:      515
```
ALERTS.md: 17 alert line(s) in the last 40 — read it if non-zero.

## Queue
```
in flight:

last 6 dispatcher events:
   - STARTED   | task=new_kiro_session_is_required_LOCAL-446.md | at=2026-08-12T14:56:52-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-446.md | id=TLOCAL-446 | branch=LOCAL-446-llm-wikimedia-substitu
   - STARTED   | task=new_kiro_session_is_required_LOCAL-447.md | at=2026-08-12T15:36:29-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-447.md | id=TLOCAL-447 | branch=LOCAL-447-wayback-wikipedia-chai
   - STARTED   | task=new_kiro_session_is_required_LOCAL-448.md | at=2026-08-12T15:59:33-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-448.md | id=TLOCAL-448 | branch=LOCAL-448-db-first-correctness |
```

## Re-dispatchable (last status ABANDONED — a bounce awaiting pickup)
  (none — every task file is claimed or finished)

## Parked (deliberately outside the dispatcher glob — do NOT re-dispatch)
  - PARKED_kiro_task_LOCAL-335.md
  - PARKED_kiro_task_LOCAL-398.md
  - PARKED_kiro_task_LOCAL-399.md
  - PARKED_kiro_task_LOCAL-416.md
  - PARKED_kiro_task_LOCAL-428.md

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
