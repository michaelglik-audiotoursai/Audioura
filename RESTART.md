# RESTART briefing — generated 2026-08-26 10:37 EDT

## Git
```
branch   storied
HEAD     b15290d Handoff for the /clear: the container is stale, and that outranks more measurement
unpushed 0 commits
dirty    1 files
```

## Production safety
```
audio_tours real rows: 31
  A DROP is an incident (CLAUDE.md). Growth is normal — Michael generating a tour
  adds a row, and its translation adds another. 29 was a snapshot, never a law.
cost_ledger rows:      628
```
ALERTS.md: 40 alert line(s) in the last 40 — read it if non-zero.

## Queue
```
in flight:

last 6 dispatcher events:
   - STARTED   | task=new_kiro_session_is_required_LOCAL-467.md | at=2026-08-24T19:27:55-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-466.md | id=TLOCAL-466 | branch=LOCAL-466-multi-story | base=sto
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-467.md | id=TLOCAL-467 | branch=LOCAL-467-gallery-attribution | 
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-465.md | id=TLOCAL-465 | branch=LOCAL-465-exhibition-not-found |
   - STARTED   | task=new_kiro_session_is_required_LOCAL-468.md | at=2026-08-25T01:11:14-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-468.md | id=TLOCAL-468 | branch=LOCAL-468-seed-diversity | base=
```

## Re-dispatchable (last status ABANDONED — a bounce awaiting pickup)
  (none — every task file is claimed or finished)

## Parked (deliberately outside the dispatcher glob — do NOT re-dispatch)
  - PARKED_kiro_task_LOCAL-335.md
  - PARKED_kiro_task_LOCAL-398.md
  - PARKED_kiro_task_LOCAL-399.md
  - PARKED_kiro_task_LOCAL-416.md
  - PARKED_kiro_task_LOCAL-428.md
  - PARKED_kiro_task_LOCAL-452_SUPERSEDED_by_455.md
  - PARKED_kiro_task_LOCAL-454_partial.md
  - PARKED_kiro_task_LOCAL-455_r2_failed.md
  - PARKED_kiro_task_LOCAL-456.md
  - PARKED_kiro_task_LOCAL-457.md
  - PARKED_kiro_task_LOCAL-460_wrong_spec.md

## Honest tour scores (corpus-loaded scorer, recompute — do not quote from memory)
```
   LOCAL347_museum_4stop.txt            base= 81.2
   LOCAL346b_walking_4stop.txt          base= 87.5
   LOCAL352b_restaurant_4stop.txt       base= 68.8
   LOCAL320_museum_8stop.txt            base= 81.2
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
  5:- [ ] **2026-08-26 — NEXT SESSION: the container is STALE, and that outranks more measurement.**
  106:- [ ] **2026-08-24 — NEXT SESSION'S TASK LIST, Michael's instruction before /clear.**
  163:- [ ] **2026-08-22 — NEXT SESSION'S FIRST TASK, Michael's instruction before /clear:**
  199:- [ ] **2026-08-19 — Boston Globe credential: MICHAEL DEFERRED TO THE WEEK OF 08-24.**
  222:- [ ] **2026-08-19 morning — READ THESE TWO FILES FIRST, they are open in VS Code:**
  226:- [ ] **ONE DECISION IS YOURS AND BLOCKS NOTHING ELSE: which "story" definition wins?**
  233:- [ ] **2026-08-19 — THE NEXT WORK IS RETRIEVAL, NOT PROMPTING.** With the story in its
  317:- [ ] 2026-08-12 20:5x — **Two guards are broken; do not trust them.**

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
