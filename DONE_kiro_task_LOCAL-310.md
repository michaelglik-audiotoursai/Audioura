**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-310
**Base:** storied
**Branch:** kiro/local310-blindspot-monitor

# Catch the detector's blind spots we do not know about yet.

Read `DECISIONS.md` **D200**, **D219**, `TOUR_EVALUATION_museum_8stop.md`,
`tour_rubric_scorer.py`, `groundedness_check.py`.

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
LOCAL-309 is in `compute_score`. You are adding a **separate** monitor module.
Production real row count must stay **29**.

## Michael's question

> *"We made a mistake counting facts, that generated incorrect numbers. I do not
> know what to do if we are not aware of that fact, so I am listening to your
> proposal."*

The Ganesh stop scored **1 fact** where a reader counts twelve — chlorite, eight
arms, a rosary, modakas, the Pala-Sena dynasty, Shiva, Parvati. LOCAL-304 fixed
those four categories. **The next blind spot is by definition one nobody has
thought of**, so a better vocabulary is not the answer.

**The answer is a cross-check against an independent signal.** Build one.

## Scope — a monitor, not a detector change

### 1. Corpus-vs-detector discrepancy (free, and the strongest signal)

We already know, per stop, how many corpus passages exist and how many facts were
detected. **A stop with rich corpus and few detected facts is either a generation
failure or a detector blind spot, and both deserve an alarm.**

Compute a discrepancy score per stop and flag the outliers. Report the worst 20
across `tours/*.txt` with passage count, detected facts, and the stop text, so a
reviewer can see instantly which of the two causes it is.

**This would have caught the Ganesh stop**: 6 passages, 1 detected fact. Verify
that it does — that is the acceptance test for this part.

### 2. Per-venue distribution check (free)

Group stops by venue and compare fact-density distributions. **A venue scoring
systematically below the corpus median is a vocabulary suspicion, not necessarily
a quality finding.** Asian-art tours scoring below Riviera ones is exactly the
shape the chlorite gap produced. Report per-venue medians and flag any venue more
than one standard deviation below.

### 3. LLM spot-check (costs money — sample, do not sweep)

On a **5% sample** of stops, ask a model to count verifiable facts independently
and compare with the detector. **Systematic one-directional divergence is the
blind-spot signal**; scattered disagreement is noise.

- Batch the sample into as few calls as possible.
- Report measured cost. If it exceeds **$0.05 per full corpus run**, reduce the
  sample rather than the rigour.
- **This is a diagnostic, not a scorer.** The LLM's count must never enter a
  tour's score — it exists to tell us the regex is wrong.

## The line you must not cross

**Do not change `analyze_stop` or any threshold.** This task adds a monitor that
reports. If it finds a blind spot, that is a finding for a follow-up task, not
something to fix here — mixing detection and repair in one change makes both
unreviewable.

**Do not let the monitor run in the delivery path.** It is an offline analysis
over `tours/*.txt`, invoked deliberately. Nothing about generation may slow down
or depend on it.

**Report what you find, and do not tune it away.** If the discrepancy check
flags 200 stops, that is the finding. Suppressing it to make the output tidy
defeats the purpose.

## Verification
- The Ganesh stop (`tours/LOCAL303_museum_8stop_gate.txt` stop 3, pre-LOCAL-304
  text if available, else current) appears in the discrepancy output.
- Worst-20 list produced with passage counts, detected facts and stop text.
- Per-venue medians reported; any venue >1σ below flagged.
- LLM spot-check on 5%, with measured cost and the divergence direction.
- **State plainly whether the monitor found any blind spot LEAD does not already
  know about.** "None found" is a valid and useful result.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- Wikidata/OpenAI rate limits: handle, do not retry blindly (D220).

## Acceptance criteria
- Three checks implemented as an offline monitor; nothing in the delivery path.
- Ganesh-class discrepancy demonstrably caught.
- No change to `analyze_stop` or any threshold.
- Cost measured and within budget.
- Findings reported honestly, including "none".
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-310.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
