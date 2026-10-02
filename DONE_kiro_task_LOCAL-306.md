**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-306
**Base:** storied
**Branch:** kiro/local306-inflight-scoring

# Score every tour before delivery, and record it. Gate nothing yet.

Read `tour_rubric_scorer.py`, `generate_tour_text.py` (PHASE 6 assembly),
`tour_orchestrator_service.py`, `DECISIONS.md` **D200**, **D204**.

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
LOCAL-304 and LOCAL-305 are editing `tour_rubric_scorer.py`. **You import it, you
do not modify it.** If you need a change there, say so in the submission instead.

## What Michael asked for

> *"evaluating the tour in-flight, meaning just before providing it to the clients
> for listening… one, for recording and keeping track about our performance; two,
> evaluating your clients editing tours ability… three, guardrails for a
> low-score tour to be regenerated or alert users."*

This task is **one and two only.** Guardrails are LOCAL-307 and are deliberately
gated behind the scorer becoming trustworthy.

## ⛔ THIS TASK CHANGES NO TOUR AND BLOCKS NO DELIVERY

Score, persist, log. **Nothing may be regenerated, withheld, altered or delayed
because of a score.** The reason is concrete: the current detector scored a stop
containing chlorite, eight arms, a rosary, modakas and the Pala-Sena dynasty as
**THIN with one fact**. A guardrail today would regenerate good work. LOCAL-304
fixes that; until it lands, we record and observe.

## Scope

### 1. Score at assembly, persist the result

After the final gated text exists and before delivery, run the rubric and store:

```
tour_id, scored_at, code_sha,
n_requested, n_delivered,
base, structural, correlation, venue_identity, total,
per_stop  [{index, title, classification, facts, sentences, density,
            filler, groundedness}],
scorer_version
```

New table `tour_scores`, one row per scoring event — **not** one per tour. A tour
scored again after an edit gets a second row. That history is the product.

**Additive schema only** (allowed without asking, per CLAUDE.md, but declare it in
the submission). Add it to `tests/init_test_db.sh` too.

### 2. Re-score after a client edit, and report the delta

When a tour is edited, score it again and record what moved:

```
facts_before -> facts_after, per stop
classifications that changed band
sourced facts removed by the edit
unsourced claims added by the edit
```

**Score the tour, never the user.** *"This edit removed 3 sourced facts and added
2 unsourced claims"* is useful. *"Your edit scored 62"* is presumptuous — a user
who shortens a tour or adds personal commentary has made it worse by our rubric
and better for themselves. **Emit the delta; emit no verdict.** No wording
anywhere in this task's output may evaluate the person.

### 3. Cost and latency

Scoring is rule-based: **no LLM calls, no network**. Measure and report the added
latency per tour; if it exceeds ~200ms, say so rather than shipping it.

## The line you must not cross

**Do not gate, retry, or modify delivery.** Not even for a catastrophic score.
That is LOCAL-307, after LOCAL-304.

**Do not score partial text.** Score the final assembled tour, after every gate —
scoring mid-pipeline measures something the listener never receives.

**Do not write scores to production from a test run.** Honour
`AUDIOURA_DB_TARGET` (LOCAL-296) and remember it governs in-process access only
(D221).

## Verification

- Generate a 2-stop Riviera and an 8-stop museum tour; show the persisted rows.
- Show the added latency per tour.
- Simulate an edit (remove a sourced sentence, add an unsourced one), re-score,
  and paste the delta output. Confirm it contains **no judgement of the user**.
- Confirm delivery is byte-identical with scoring on and off — the tour text must
  not change.
- Production `audio_tours` real count still **29**; report before and after.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- Read a delivered tour as prose before reporting (D161).
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria
- Every generated tour produces a `tour_scores` row before delivery.
- Re-scoring after an edit produces a second row plus a factual delta.
- No verdict on the user anywhere.
- Delivery byte-identical with scoring enabled; nothing gated.
- Latency measured and reported; no LLM calls.
- Schema addition declared and added to `init_test_db.sh`.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-306.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
