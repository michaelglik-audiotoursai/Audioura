**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-309
**Base:** storied
**Branch:** kiro/local309-verified-unavailable

# Do not trust the log. Search, then decide whether to penalise.

Read `EVALUATION_INDEX_PROPOSAL.md`, `DECISIONS.md` **D162**, **D221**,
**D225**, `tour_rubric_scorer.py`, `stop_existence_gate.py` (the tier-1 path).

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.80**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Production real row count must stay **29**.

## Michael's ruling, 2026-08-06

> *"Missing tour should be penalized only if there is data; otherwise, we should
> do a quick internet search and if we find data, then penalize; otherwise do
> not."*
> *"Fabricated stop should be penalized 3 times more than omitted stop for
> unlegitimate reason. If the reason was legitimate as no data was available, we
> do not penalize... But we should not trust the log, we should do a quick
> Internet search to see if the data really is not available."*

## Scope

### 1. New weights

```
FABRICATED                      -3.0 x share     (was -1.5)
PIPELINE_LOST                   -1.0 x share     (unchanged)
UNAVAILABLE, search-confirmed    0.0 x share     (was -0.15)
UNAVAILABLE, unverified         -1.0 x share     (treat as PIPELINE_LOST)
```

**The last line is the whole point.** UNAVAILABLE at zero cost is only available
to a shortfall that a **live search** confirms. Absent that search, the shortfall
is our failure and costs the full amount. This inverts the incentive: it is now
cheaper to look than to assume.

### 2. The search itself

When a tour delivers fewer stops than requested, for each missing slot run a
**bounded** lookup for further real candidates in the area — Wikipedia/Wikidata
first, since `stop_existence_gate` already has that tier-1 path; reuse it rather
than building a parallel one.

- **Cap it.** At most one query per missing stop, at most 5 per tour, with a
  timeout. A scoring pass must never hang on the network.
- **Cache by area.** Two tours of the same area on the same day must not both
  pay. Cache the "no further candidates" verdict with a timestamp.
- **Record the evidence.** Persist what was searched and what came back, so the
  verdict is auditable later. A zero-cost UNAVAILABLE with no recorded search is
  a bug.
- **On search failure — network error, rate limit, timeout — classify
  PIPELINE_LOST.** Never let an infrastructure failure buy a free pass.

### 3. Cost

Report measured cost per tour. Only missing stops trigger a search, so a tour
delivering N of N costs nothing extra. If it exceeds **$0.01/tour** on average,
say so rather than shipping it.

## The line you must not cross

**This is D162 as a scoring rule.** LEAD spent eight days treating "our search
didn't show it" as proof of absence and deleted real corpus over it; LOCAL-290
found the same error automated in the existence gate. A search that returns
nothing is weak evidence, and it must be **our** search failing to find a
**real** place that earns the zero — not our corpus lacking it.

**Do not weaken the existence gate to manufacture UNAVAILABLE verdicts.** A
fabricated place must still fail. The Lyon-proximity case must still fail.

**FABRICATED stays operator-only** (D200). Tripling its weight does not make it
computable.

## Verification
- Unit tests for all four classifications, including search-failure → PIPELINE_LOST.
- A tour with a genuine shortfall in a rich area (Riviera): search should find
  candidates → PIPELINE_LOST → penalised.
- A tour in a genuinely thin area: search finds nothing → UNAVAILABLE → 0 cost.
  Show the recorded evidence for both.
- Measured cost per tour; cache hit rate on a repeat run.
- Rescore `tours/LOCAL303_museum_8stop_gate.txt` (8/8) — must be unchanged.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- Wikidata rate-limits under load and returns 429 (D220). Handle it as search
  failure → PIPELINE_LOST, not as "no data".

## Acceptance criteria
- Weights as above; unverified UNAVAILABLE costs the full -1.0.
- Search bounded, cached, evidence persisted, failures fail closed.
- Existence gate not weakened; fabricated and out-of-region still rejected.
- Cost reported; 8/8 tours unaffected.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-309.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
