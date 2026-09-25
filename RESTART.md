# RESTART briefing — generated 2026-09-23 21:57 EDT

## Git
```
branch   storied
HEAD     63419e9 Merge LOCAL-545: ALERTS.md goes 5990 lines -> 18, and empty now means something
unpushed 4 commits
dirty    5 files
```

## Production safety
```
audio_tours real rows: 36
  A DROP is an incident (CLAUDE.md). Growth is normal — Michael generating a tour
  adds a row, and its translation adds another. 29 was a snapshot, never a law.
cost_ledger rows:      843
```
ALERTS.md: *** 4 URGENT alert line(s) — READ .continuous_dev/ALERTS.md NOW ***
task_hygiene.log: 1 routine event(s) in the last 200 — informational, auto-refiled, not an emergency.

## Queue
```
in flight:

last 6 dispatcher events:
   - STARTED   | task=new_kiro_session_is_required_LOCAL-546.md | at=2026-09-23T21:31:28-04:00 | base=storied | dispatche
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-543.md | id=TLOCAL-543 | branch=LOCAL-543-evidence-carries-no-so
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-545.md | id=TLOCAL-545 | branch=LOCAL-545-split-alert-channels |
   - COMPLETED | task=new_kiro_session_is_required_LOCAL-546.md | id=TLOCAL-546 | branch=LOCAL-546-surname-collision | ba
   - STARTED   | task=new_kiro_session_is_required_LOCAL-547.md | at=2026-09-23T21:49:27-04:00 | base=storied | dispatche
   - STARTED   | task=new_kiro_session_is_required_LOCAL-548.md | at=2026-09-23T21:49:27-04:00 | base=storied | dispatche
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
  475:- [ ] **2026-10-07 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #1).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  480:- [ ] **2026-10-22 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #2).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  485:- [ ] **2026-11-06 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #3).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  490:- [ ] **2026-11-21 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #4).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  495:- [ ] **2026-12-06 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #5).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  500:- [ ] **2026-12-21 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #6).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  505:- [ ] **2027-01-05 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #7).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  510:- [ ] **2027-01-20 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #8).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  515:- [ ] **2027-02-04 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #9).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five 
  520:- [ ] **2027-02-19 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #10).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five
  525:- [ ] **2027-03-06 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #11).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five
  530:- [ ] **2027-03-21 — CHECK THE THREE PAID ACCOUNTS (15-day cycle #12).** Michael's standing request, 2026-09-22, after an empty OpenAI balance killed five

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
