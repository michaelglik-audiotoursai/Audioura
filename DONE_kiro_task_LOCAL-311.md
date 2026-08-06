**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-311
**Base:** storied
**Branch:** kiro/local311-versioned-evaluator

# The evaluator must be swappable without fear, and every score must say which algorithm produced it.

Read `tour_scoring_service.py`, `tour_rubric_scorer.py`, `DECISIONS.md`
**D200**, **D225**.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.60**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**LOCAL-309 is editing `compute_score` and LOCAL-310 is adding a monitor.**
Coordinate or rebase; do not fight them. Production real count stays **29**.

## What Michael asked for

> *"Make evaluation routine separate from the callers, so we can later change
> evaluation routine and not be afraid that the changes will break something.
> Make evaluation routine have ID and date. So later on we could know what kind
> of evaluation algorithm we used and when."*
> *"Make every tour be evaluated and recorded in our database for internal
> review."*

## What already exists — read before building

LOCAL-306 delivered most of the recording half: a `tour_scores` table with
`scored_at`, `code_sha`, `scorer_version`, `per_stop`, `scoring_ms`,
`is_rescore`, `previous_score_id`, `delta`. **Do not rebuild it.**

The gaps are the two halves of Michael's first sentence.

## Scope

### 1. A real interface boundary

Callers currently reach into scorer internals — `parse_tour`, `analyze_stop`,
`classify_stop`, `compute_score` — and wire them together themselves. That is
what makes the algorithm frightening to change: four entry points, each with
callers depending on their shape.

Define **one** entry point, e.g. `evaluate(tour_text, n_requested, **context)
-> Evaluation`, and make every caller use it. The `Evaluation` object carries
the score, the per-stop detail, the algorithm id and the timestamp.

**Internals become private.** After this, changing `analyze_stop` must not be
able to break a caller, because no caller may touch it.

### 2. Algorithm identity that means something

`SCORER_VERSION = "LOCAL-306-v1"` is a hand-edited constant in the *service*,
not a property of the *algorithm*. Someone changing thresholds in
`tour_rubric_scorer.py` will not think to bump a string in another file.

- Move the version next to the algorithm it describes.
- Include the values that change the answer — the band thresholds, the weights —
  so two scores are comparable **only if** their algorithm id matches.
- **A registry**: given an algorithm id, a reader can recover what that version
  did. A score from three months ago must be interpretable.
- Bump automatically or fail loudly if thresholds change without a bump. A stale
  version string is worse than none, because it silently claims comparability.

### 3. Every tour, every path

Verify — do not assume — that a score is recorded for a tour generated via **each**
path: the orchestrator, direct `generate_tour_text`, and an edit. Report which
paths were already covered and which you had to add.

## The line you must not cross

**Do not change any score.** This is refactoring plus identity. Rescoring
`tours/LOCAL303_museum_8stop_gate.txt` before and after must give **identical
numbers** — paste both.

**Do not break LOCAL-306's contracts**: delivery byte-identical, no LLM calls,
sub-200ms, gates nothing.

**Do not version by git SHA alone.** `code_sha` already exists and records the
commit; it does not tell a reader what the algorithm *did*. The id must be
meaningful without checking out the repo.

## Verification
- One public entry point; grep showing no caller touches internals.
- Identical scores before/after on the museum tour.
- Threshold change without a version bump fails loudly — demonstrate it.
- A score row from each of the three generation paths.
- Registry lookup for at least two versions.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). Read a delivered tour as prose (D161).

## Acceptance criteria
- Single entry point; internals private; no caller reaches past it.
- Algorithm id includes threshold/weight identity, with a registry.
- Stale-version detection demonstrated.
- All three paths record; coverage stated.
- Scores provably unchanged.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-311.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⛔ BOUNCED by LEAD — 2026-08-06 13:1x. The new entry point changes every score.

**The architecture is right and stays.** `evaluate()` as a single public entry,
`Evaluation` carrying `algorithm_id` / `algorithm_version` /
`algorithm_config_hash` / `scored_at` / `scoring_ms`, a config hash that tracks
threshold identity (`LOCAL-311-v1@41db0d2f`), and a registry — that is exactly
what Michael asked for and it works. 13ms. Keep all of it.

## The defect

The submission says *"Scores provably unchanged."* They are not.

```
same tree, same tour (tours/LOCAL303_museum_8stop_gate.txt, N=8)

  your tour_rubric_scorer, called directly    101.6   (corr +26.6)
  your evaluate()                              82.8   (corr  +7.8)
```

**Cause, isolated:** `evaluate()` never performs the `callbacks_to`
cross-population step. `score_tour_file` does it:

```python
for sa in analyses:
    for ref_idx in sa.callbacks_from:
        for other_sa in analyses:
            if other_sa.index == ref_idx:
                other_sa.callbacks_to.append(sa.index)
```

Without it, only `callbacks_from` is populated, so `compute_score` sees half the
callback set and the correlation bonus computes at +7.8 instead of +26.6.
Reproduced exactly: skipping that loop yields 82.8, matching `evaluate()` to the
decimal.

## Why this matters more than 19 points

A single entry point exists so the algorithm can change **without fear**. An
entry point that quietly returns a different number than the path it replaces is
the opposite — it reprices every tour in the database on the day it lands, and
the submission would have told us nothing had changed.

Note also: the **base score is unaffected** (75.0 either way). Only the bonus
moves. That is why this slipped through — anyone checking the headline
`base_score` would see no difference.

## The fix

Move the cross-population inside `evaluate()`, or better, inside `compute_score`
where it cannot be forgotten by a future caller. If it belongs to scoring, it
should not live in the caller — that is the same coupling this task exists to
remove.

Then **prove it**: paste both numbers from both paths for at least two tours, one
with callbacks and one without.

## One more thing, minor

`_compute_config_hash()` takes a required `config` argument, so the stale-version
guard could not be exercised from outside. Give it a zero-argument form or a
documented way to invoke it, and demonstrate the guard firing when a threshold
changes — the task asked for that and the submission asserts it without showing
it.

## Not in scope for the fix

Whether the correlation bonus *should* be counted at all is a separate question
(D201: LEAD believes it is unsound). Do not resolve it here by deleting the
cross-population. If the number changes, it must change deliberately and be
announced — not as a side effect of a refactor.
