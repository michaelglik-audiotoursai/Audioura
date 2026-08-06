**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-307
**Base:** storied
**Branch:** kiro/local307-quality-guardrails

# ⛔ GATED — DO NOT RUN until LOCAL-304 AND LOCAL-306 are merged.

**Self-abort check. Run this FIRST and stop if it fails:**

```bash
cd ~/Audioura
git log --oneline storied | grep -q "Merge LOCAL-304" \
  && git log --oneline storied | grep -q "Merge LOCAL-306" \
  && echo GATE-OPEN || { echo "GATE CLOSED — 304/306 not merged. Aborting."; exit 0; }
```

**Why the gate exists, concretely.** The current fact detector scored a stop
containing chlorite, eight arms, a rosary, modakas, the Pala-Sena dynasty, Shiva
and Parvati as **THIN with one fact**. A guardrail built on today's scorer would
regenerate that stop — spending money and latency to replace good work with
something probably worse. LOCAL-304 fixes the detector; LOCAL-306 provides the
in-flight scoring hook. Neither is optional.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>`. **Never run `find` against `/` or `/Users/micha`**
(D213, D218). **If a command has not returned in ~2 minutes it is the wrong
command.** **Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## What Michael asked for

> *"guardrails for low-score tours to be regenerated or alert users about the
> reasoning like 'not enough information', 'not enough trusted sources'."*

## The decision this task implements

**Regenerating is right when we failed. Telling the user is right when the world
is thin.** That maps exactly onto the split LOCAL-305 introduces:

| cause | action |
|---|---|
| **PIPELINE-LOST** — a stop verified then vanished; a stop with corpus produced thin prose; a generation error | **regenerate silently, once** |
| **UNAVAILABLE** — tier-1 finds no further real places; stops have no corpus and none is obtainable | **do not regenerate. Tell the user.** |

Retrying an UNAVAILABLE tour produces the same tour and charges twice.

## Scope

### 1. Regeneration, bounded
- **At most one retry per tour.** Never a loop.
- Only on a PIPELINE-LOST diagnosis.
- If the retry scores no better, **deliver the better of the two** and log it.
  Never deliver nothing.
- Log both scores and the decision.

### 2. Honest user-facing messages

When the shortfall is UNAVAILABLE, say so plainly and specifically:

| situation | message |
|---|---|
| fewer real places than requested | *"We found 3 well-documented places for this area rather than the 6 you asked for. Here is the shorter tour."* |
| places exist, sources are thin | *"We have limited documented history for some of these stops. The tour is shorter on detail than usual."* |
| venue verified, no per-object material | *"This venue is confirmed, but we found little published detail about its individual works."* |

**Write these as a user would want to read them.** No apology, no jargon, no
"quality score". State what we found and what they are getting. Michael's
standing rule against empty exhortation applies here too — say the fact, not a
feeling about it.

### 3. Thresholds — propose, do not invent

Derive candidate thresholds from the corpus distribution **after** LOCAL-304
recalibrates it, and state the measured percentiles behind each. Report them in
the submission; **do not enable gating until Michael has seen the numbers.**
Ship the mechanism defaulted **off** behind a flag.

## The line you must not cross

**Never silently deliver less than asked.** The count must always be visible even
when the shortfall is legitimate.

**Never regenerate more than once**, and never let a regeneration make the user
wait without telling them something is happening.

**Never pad to clear a threshold.** If a tour is thin because the material is
thin, the honest output is a shorter tour and a clear message — not filler. This
is the fabrication the whole programme exists to prevent.

**Do not let a low score suppress a tour entirely.** Some tour is better than
none; the message carries the caveat.

## Verification
- A PIPELINE-LOST case: show the diagnosis, the single retry, both scores, the
  delivered choice.
- An UNAVAILABLE case (pick a genuinely obscure location): show that **no**
  retry occurred and the message the user receives.
- Confirm no tour is ever suppressed, and the requested/delivered count is always
  visible.
- Cost and added latency per tour, including the retry case.
- Production real row count still **29**.

## Acceptance criteria
- Regeneration bounded to one, PIPELINE-LOST only, better-of-two delivered.
- UNAVAILABLE never retried; a specific, non-apologetic message is emitted.
- Thresholds proposed with measured percentiles; gating defaults **off**.
- No padding, no suppression, count always visible.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-307.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
