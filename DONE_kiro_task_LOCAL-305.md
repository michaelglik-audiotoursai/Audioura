**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-305
**Base:** storied
**Branch:** kiro/local305-missing-stop-fairness

# A stop we lost and a stop the world never had should not cost the same.

Read `EVALUATION_INDEX_PROPOSAL.md` (Michael approved it), `DECISIONS.md`
**D202**, **D221**, `tour_rubric_scorer.py`, `stop_existence_gate.py`.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>`. **Never run `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.60**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**LOCAL-304 is editing `analyze_stop` in the same file.** You are in
`compute_score` / `classify_stop`. Coordinate or rebase; do not fight it.

## What Michael approved

> *"I am not convinced that obtaining less stops than requested should not be
> punished as severely as it does now, especially if we have data available; if
> not — meaning Internet has less reliable data for some esoteric tours — I maybe
> willing to make its influence smaller."*

He is right, and the rubric cannot currently tell the two cases apart. Both cost
**−1.0 × share**, identical to FABRICATED.

## Scope

### 1. Split MISSING by cause

```
PIPELINE-LOST   −1.0  × share    proposed, exists, and WE lost it
UNAVAILABLE     −0.15 × share    the area genuinely offers fewer real places
FABRICATED      −1.5  × share    misleading costs more than omitting
```

**The cause is now determinable and was not before.** LOCAL-290 separated "not in
our corpus" from "not real": a stop that fails the tier-1 existence check is
genuinely absent from the world; a stop that verified and then vanished to a
generation error or a gate drop is ours. The gate already logs the reason for
every drop — use that, do not re-derive it.

Classify each shortfall:
- selector proposed fewer than N, but tier-1 finds no further real candidates in
  the area → **UNAVAILABLE**
- a stop verified and was then lost (generation failure, drop without
  replenishment, empty-stop removal) → **PIPELINE-LOST**
- **cannot tell → PIPELINE-LOST.** Default to blaming ourselves; the opposite
  default lets our bugs hide behind "the internet is thin here".

### 2. Report coverage separately from quality

```
quality    per-stop score of what was delivered
coverage   delivered ÷ achievable
achievable stops in this area passing a genuine existence check
```

Today these are fused, so a selector bug and thin prose move the same number.
Emit both on `TourScore` and print both. **Do not remove the requested count** —
"5 of 8" must stay visible even when all three were UNAVAILABLE.

### 3. Normalise quality against obtainable corpus

A stop with 6 passages delivering 6 facts has done everything available to it; a
stop with 6 passages delivering 1 has not. LOCAL-291 already computes
groundedness per stop, so the denominator exists. Scoring both against a fixed
absolute bar punishes the first for the world's stinginess.

## The line you must not cross

**UNAVAILABLE must be earned, not assumed.** It requires a positive finding that
no further real candidate exists — a tier-1 check that came back empty. Absence
of *our* corpus is never sufficient; that is D162, and LOCAL-290 exists because
we made exactly that mistake.

**Do not let UNAVAILABLE reach zero cost.** A 2-stop tour of a rich city is worth
more of a listener's hour than a 2-stop tour of a place with nothing in it. −0.15
is a nudge; 0 would say the two are equal.

**FABRICATED stays uncomputable** (D200). Raising its weight to −1.5 does not
make it assignable by the scorer.

## Verification

- Unit tests for each classification path, including the cannot-tell default.
- Rescore `tours/LOCAL290_8stop_1.txt` (7 of 8 delivered) and report which class
  the missing stop falls into, with the gate-log evidence.
- Rescore `tours/LOCAL303_museum_8stop_gate.txt` (8 of 8) — coverage must be 1.0
  and the total unchanged by this task.
- Corpus-wide: how many tours change band, and in which direction.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- Production real row count must stay **29**.

## Acceptance criteria
- MISSING split into PIPELINE-LOST / UNAVAILABLE with the stated weights.
- UNAVAILABLE requires a positive tier-1 finding; cannot-tell defaults to PIPELINE-LOST.
- FABRICATED at −1.5 and still operator-only.
- `coverage` and `quality` reported separately; requested count still visible.
- Quality normalised against available passages.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-305.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
