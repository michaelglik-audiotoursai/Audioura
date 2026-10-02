**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-291
**Base:** storied
**Branch:** kiro/local291-groundedness

# ⛔ GATED — DO NOT RUN UNTIL LOCAL-289 AND LOCAL-290 ARE MERGED.

**Self-abort check. Run this FIRST and stop if it fails:**

```bash
cd ~/Audioura
git log --oneline storied | grep -q "Merge LOCAL-289" \
  && git log --oneline storied | grep -q "Merge LOCAL-290" \
  && echo GATE-OPEN || { echo "GATE CLOSED — 289/290 not merged. Aborting."; exit 0; }
```

Michael's instruction, 2026-08-05 23:5x: *"hold this task until LOCAL-289 and
LOCAL-290 are completed. Then execute it."*

The reason is measurement, not sequencing: both tasks change how much real
corpus exists, and this task's thresholds must be calibrated on the corpus as it
will be, not as it is tonight. Tonight's ungrounded rate is 20%; after 290 it
should fall. **Re-measure before choosing any threshold.**

## Ceiling **$1.50**. NO container rebuilds (D48).
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## What this is

Michael: *"Is it possible to identify FABRICATED stops and start counting them
into the evaluation index?"*

Yes — but **corpus absence is not fabrication**, and building it that way would
repeat D162 and the LOCAL-290 bug at the scoring layer. Measured tonight over
recent Riviera tours: 118 fact-claims, **80% grounded** in `stop_corpus`, 20%
not. Every ungrounded sample LEAD could check was **true**:

```
Saint-Paul-de-Vence      Marc Chagall          — lived and buried there
Villa Ephrussi           Baroness Béatrice     — she built it
Villa Ephrussi           Aaron Messiah         — its architect
Château de la Napoule    Henry Clews Jr        — restored it
Marineland Antibes       1970                  — opening year
```

Two of those are the same person counted twice ("Baroness Béatrice" /
"Béatrice Ephrussi") because the corpus says "Béatrice de Rothschild" — the D187
name-matching problem inflating the ungrounded count. Fix that normalisation
first or every number here is wrong.

## Scope — three tiers, in this order

### 1. CONTRADICTED — wire the existing signal into the score

PHASE 5.16 already computes a CONTRADICTED block and **the scorer never reads
it.** A conflict between corpus and narration is *evidence of error*, not absence
of evidence, so it is the one signal that can safely score negative.

Add `CONTRADICTED` as a computed classification in `tour_rubric_scorer.py`
alongside RICH/ADEQUATE/THIN. Weight: **−1.0 × share**, the existing FABRICATED
weight. Report how often it fires across the corpus.

### 2. UNGROUNDED — a ceiling, never a penalty

Compute per stop: fraction of fact-claims (distinct dates, named people, named
works) present in that stop's `stop_corpus` passages.

- **It must not reduce the score.** An ungrounded fact is unverified, not false.
- **It caps the band:** a stop below a groundedness floor cannot be classified
  RICH however dense it is. Choose the floor from the re-measured distribution
  and state the number you measured.
- Emit the ungrounded claims as a **corpus worklist** — this is exactly what
  LOCAL-283's harvester should ingest.

### 3. Adjudication — only the ungrounded remainder

For claims still ungrounded after (2), one batched call per stop against fetched
Wikipedia/Wikidata: **supported / contradicted / not found**. Only `contradicted`
maps to CONTRADICTED; `not found` stays UNGROUNDED.

Michael, 2026-08-05: *"I am willing to pay for the reliability."* Budget ~2–3
claims per stop; estimate and report actual cost per tour against the $0.026 a
2-stop tour costs today. **If the measured cost exceeds $0.05/tour, stop and
report rather than shipping it on.**

## The line you must not cross

**Nothing may be scored FABRICATED for being absent from our data.** That is the
whole point of this task's design. A negative score requires positive evidence of
error — a contradiction, not a gap.

**FABRICATED must remain assignable by an operator override** and must stay
uncomputable from density alone (D200).

## Verification

Re-measure the grounded/ungrounded split after 289+290, on ≥5 Riviera tours and
≥2 museum tours. Report the split, the CONTRADICTED rate, the chosen floor with
its justification, and per-tour adjudication cost. Copy all tours to
`/Users/micha/Audioura/tours/`.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). Read tours as prose (D161). Spine stays gpt-4o (D186).
- `stop_corpus` columns are `passages_json`, `passage_count` — **not** `passages`.

## Acceptance criteria

- CONTRADICTED computed and scored −1.0 × share; firing rate reported.
- Groundedness computed; used only as a RICH ceiling, never as a penalty.
- Name normalisation applied before judging groundedness.
- Ungrounded claims emitted as a corpus worklist.
- Adjudication limited to the ungrounded remainder, cost reported per tour.
- Operator override to FABRICATED still works.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-291.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
