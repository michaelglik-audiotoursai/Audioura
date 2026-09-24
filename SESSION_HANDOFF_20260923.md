# Handoff — Storied_Tours, 2026-09-23 evening

Written for the session that picks up after `/clear`. Run `bash restart.sh` first;
this file covers only what restart.sh cannot derive from live state.

## Where the tour work stands

**Round 7 is closed.** Two independent kiro critiques produced ten defects. Four are
fixed and verified gone in regenerated tours; four were dispatched and merged today;
one is retired as moot; one is in flight.

| fix | status |
|---|---|
| D583 word-splices (`Archdiocesethe`) | fixed, 4 -> 0 in round 8 |
| D586 placeholder stop shipped as content | fixed, scorer catches it, 0 in round 8 |
| D584 person-cap (capped a venue called "church", missed Cuenin) | fixed, tests added |
| D585 `named_people` counter | fixed after three wrong attempts |
| LOCAL-527 fabricated attribution | merged; catches both round-8 cases |
| LOCAL-529 one name four spellings | merged |
| LOCAL-530 verb with its object deleted | merged |
| LOCAL-532 best anecdote told twice | merged, **with a LEAD correction — see below** |
| LOCAL-528 anachronism on a part | COMPLETED, 1 commit, **unreviewed** |
| LOCAL-531 never emit a placeholder | RETIRED, moot |

**LOCAL-533 (instrument grounding cost) is released and pending.**

**Round 9 was generating when this was written** (`run_round9.py`, log
`round9_run.log`, output `TOURS_FOR_REVIEW/round9/`). Michael asked whether to review
round 7; the answer was no — it is two generations stale — so round 9 exists to give
him tours worth reading. **Check it finished and score it.**

## The one thing that must not be forgotten

**LOCAL-532 shipped a defect that review caught.** Its event-matching deleted the
Lindbergh landing from BOTH stop 3 and stop 4 of the real LOGAN_1, because both
matched stop 1's PREVIEW ("At the upcoming stops, you'll learn about ... the historic
landing of Charles Lindbergh"). A preview is not a telling; the tour would have
promised its best anecdote and never delivered it. Fixed in `derepetition_guard.py`
via `_IS_PREVIEW`. **The general lesson, which cost real money three times today:
read what a change DID to real text, not what its report claimed.**

## What is still wrong, and is the same single problem

Everything deterministic is fixed and stays fixed. **What survives is every defect
requiring knowledge of the world**, and all of it scores CLEAN:

- Gustave Eiffel building Boston Logan (round 7 AND round 8, moved between stops)
- "Founded in 1868 by St. Mary Help of Christians" — the church's DEDICATION rendered
  as its founder
- Lindbergh landing in 1927 on a jet bridge, in a stop that correctly dates Massport
  to 1959

LOCAL-527 now scores the first two. LOCAL-528 addresses the third.

Also recorded: **`geo_refutation` is imported by `tour_quality`, `sentence_split` and
`user_stops_validate` — never by `generate_tour_text`.** Refutation scores tours after
the fact; it does not gate generation. Unresolved, and Michael has not ruled on it.

## Cost — measured, see COST_PER_TOUR.md

~**$0.21** for a 4-stop tour (CHURCH_1 $0.2462 / LOGAN_1 $0.1703). **That number
excludes grounding**, which bills ~3.5c per REQUEST independent of tokens. The two
move on opposite levers, so tuning tokens first can raise the real bill while the
printed number falls. LOCAL-533 exists to split them. **Do not optimise before it
lands.** Caching is NOT the open problem: 166 cached rows, a repeat verified at $0.00
in 0.2s; the lever is hit rate (stop-pool, D581).

## Infrastructure — two incidents today, both fixed, both instructive

1. **Docker wedged for hours.** The socket accepted connections instantly and never
   answered: `com.docker.backend` alive, the Linux VM gone. App restarts do not fix
   it — kill the backend process (`pkill -9 com.docker.backend`) and relaunch. Data
   intact, 168 rows. **Never Reset to factory: `postgres_data` is a named volume and
   the backup is `-t audio_tours --data-only`, one table, no schema.**

2. **The dispatcher released 35 tasks when 4 were intended** — 97 kiro processes,
   ~10GB of worktrees against 7.9GB free. Killed mid-checkout, nothing lost. Two
   fixes: **D587** an allowlist (`.continuous_dev/RELEASED.txt`, absent file =
   dispatch NOTHING, fails closed) and **D589** a `worktree_setup_failed` record no
   longer blocks a task forever, since that task never ran.
   **What creates those duplicate task files is STILL UNKNOWN** — nothing in the tick
   chain writes them. The allowlist makes it harmless; the cause is open.

3. **`pkill -f` matches your own shell's command line.** It killed my own round-8
   generation mid-run. Filter PIDs in Python instead. Michael's Kiro CLI desktop app
   must always be spared.

## Open questions for Michael

- **Hard drive**: he wants it for active work (Docker volumes, worktrees). Real
  listings gathered; Amazon renders prices client-side so they could not be read.
- **Igor / Subscribed**: modules LOCAL-521/522/523/525 are merged; **LOCAL-524 (E2E)
  FAILED.** The breakdown starts from making that pass, not from a blank page.
  Nothing was done on Subscribed today — it lost to tier-1 work every time.

## Test suite

Full suite with the DB up: **16 minutes, 45 failed / 3160 passed**. With the DB down
it was 2h12m and 52 failures — the DB is why. **The 45 are pre-existing**; verified
against a baseline worktree at `3162bed`, which gives the identical 21 failures on
the same ten files. A suite this slow is one nobody runs before merging, which is how
four red tests got in today (D588).
