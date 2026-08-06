**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-294
**Base:** storied
**Branch:** kiro/local294-sparql-landmark-quality

# The SPARQL landmark query admits cantons and railway stations.

Read `SUBMISSION_LOCAL-293.md` (which fixed the Wikipedia path and scoped itself
honestly), `area_resolver.py` — `_sparql_coordinate_query()` and
`_sparql_p131_query()`.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
LOCAL-292 is in the description-generation path. Stay out of it.

## The measurement

LOCAL-293 fixed Path 3 — Wikipedia section headings no longer become landmarks.
LEAD's A/B on `discover_landmarks("Nice, France")`:

```
storied before 293:  79 landmarks, 49 without QID
storied after  293:  50 landmarks, 20 without QID
```

**The remaining 20 come from the SPARQL path, not Wikipedia.** Sample:

```
Church of Gesù, Nice
Canton of Nice-9            <- administrative division
Gare du Sud                 <- railway station
Villa La Belle Époque
Palais des Congrès Acropolis
Nice CP station             <- railway station
```

Two distinct problems:

1. **Entities with no QID stored.** All 50 have coordinates, but 20 carry no
   QID. A SPARQL result should always have one — find out whether the query
   omits it, the parser drops it, or these arrive by another route.
2. **Non-POI entity types.** "Canton of Nice-9" is an administrative division and
   "Nice CP station" is a transit stop. Both are real Wikidata entities with real
   coordinates, so they pass every existence check — and neither is a place a
   listener would visit on a tour.

## Scope

**Filter the SPARQL result by entity type, and populate the QID.**

- Every `Landmark` from any path must carry a QID. Fix whichever step loses it.
- **Exclude administrative divisions** (canton, arrondissement, commune,
  department, region) and **transit infrastructure** (railway station, bus stop,
  metro station) by Wikidata `instance of` (P31), not by name pattern.
- Keep what a tour would actually visit: museums, monuments, churches, squares,
  parks, beaches, castles, viewpoints, historic buildings.

**Use P31, not a name blocklist.** LOCAL-293's task said the same thing about
headings and it was the right call: a blocklist treats today's symptom and the
next area has different names. "Canton of Nice-9" must be excluded because
Wikidata says it is a canton, not because the string contains "Canton".

## The line you must not cross

**Do not exclude a real POI because its type is unusual.** If P31 returns
something not on the keep-list, keep it and log the type — a missing landmark is
worse than an odd one. Report the types encountered so the lists can be tuned
against evidence rather than guesses.

**Do not regress LOCAL-293.** Path 3 resolution must still work; the one real
place it recovers (Place Masséna, Q3389982) must still appear for Nice.

## Verification

Run `discover_landmarks` for **French Riviera, Nice, Cannes and Menton**. Report:

- landmark count and no-QID count per area, before and after, against the
  measured baseline of **50 / 20** for Nice;
- every entity excluded, with its P31 type — so LEAD can confirm no real POI
  was lost;
- the P31 types encountered that were neither kept nor excluded.

Then generate **one 8-stop Riviera tour** and confirm delivery has not regressed
from the 8/8 LOCAL-290 reached. Copy it to `/Users/micha/Audioura/tours/`.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read the delivered tour as prose (D161).
- **D186:** the spine stays on gpt-4o.
- `tests/test_local115_referral_abuse_controls_guard.py` calls `sys.exit()` at
  module scope and aborts any `pytest tests/` run that collects it. Pre-existing
  — run your suites by filename.

## Acceptance criteria

- Every Landmark carries a QID; the no-QID count for Nice is 0.
- Administrative divisions and transit stops excluded via P31, not by name.
- Unknown P31 types are kept and logged, not silently dropped.
- Every exclusion listed with its type.
- Place Masséna still recovered for Nice; 8-stop delivery not regressed.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-294.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
