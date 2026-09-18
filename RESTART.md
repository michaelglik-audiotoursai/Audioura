# RESTART briefing — generated 2026-09-17 12:55 EDT

## Git
```
branch   storied
HEAD     c61b8d3 D565: the agreed sequence after build 26, and measure cost before the purpose work lands
unpushed 0 commits
dirty    8 files
```

## Production safety
```
audio_tours real rows: 36
  A DROP is an incident (CLAUDE.md). Growth is normal — Michael generating a tour
  adds a row, and its translation adds another. 29 was a snapshot, never a law.
cost_ledger rows:      684
```
ALERTS.md: 40 alert line(s) in the last 40 — read it if non-zero.

## Queue
```
in flight:

last 6 dispatcher events:
   - STARTED   | task=new_kiro_session_is_required_LOCAL-483.md | at=2026-09-16T18:11:40-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-483.md | id=TLOCAL-483 | branch=LOCAL-483-webview-console-to-log
   - STARTED   | task=new_kiro_session_is_required_LOCAL-484.md | at=2026-09-16T21:59:50-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-484.md | id=TLOCAL-484 | branch=LOCAL-484-listen-stop-count-stal
   - STARTED   | task=new_kiro_session_is_required_LOCAL-485.md | at=2026-09-16T22:17:24-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-485.md | id=TLOCAL-485 | branch=LOCAL-485-venue-class-routing | 
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
  5:- [ ] **2026-09-15 — MAC MINI FIRMWARE/OS UPDATE IS PENDING. Read this BEFORE and AFTER the reboot.**
  45:- [ ] **2026-09-03 — iOS IS LIVE ON TESTFLIGHT. First iOS build this project has shipped.**
  79:- [ ] **2026-08-30 — MOBILE TESTING IS LIVE. Read D538-D556 in DECISIONS.md, then this.**
  157:- [ ] **2026-08-26 — the container was stale. FIXED 10:4x, see D531. The rest of this item stands.**
  258:- [ ] **2026-08-24 — NEXT SESSION'S TASK LIST, Michael's instruction before /clear.**
  315:- [ ] **2026-08-22 — NEXT SESSION'S FIRST TASK, Michael's instruction before /clear:**
  351:- [ ] **2026-08-19 — Boston Globe credential: MICHAEL DEFERRED TO THE WEEK OF 08-24.**
  374:- [ ] **2026-08-19 morning — READ THESE TWO FILES FIRST, they are open in VS Code:**
  378:- [ ] **ONE DECISION IS YOURS AND BLOCKS NOTHING ELSE: which "story" definition wins?**
  385:- [ ] **2026-08-19 — THE NEXT WORK IS RETRIEVAL, NOT PROMPTING.** With the story in its
  469:- [ ] 2026-08-12 20:5x — **Two guards are broken; do not trust them.**

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
