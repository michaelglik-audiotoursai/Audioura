**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-304
**Base:** storied
**Branch:** kiro/local304-fact-detector

# The fact detector scored a rich stop as THIN with one fact.

Read `DECISIONS.md` **D200**, `TOUR_EVALUATION_museum_8stop.md`,
`tour_rubric_scorer.py` (`analyze_stop`).

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>`. **Never run `find` against `/` or `/Users/micha`** —
three sessions were lost that way (D213, D218) and it triggers macOS privacy
prompts on Michael's machine. **If a command has not returned in ~2 minutes it is
the wrong command.** **Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.60**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Generation uses `AUDIOURA_DB_TARGET=production` (corpus lives there); production
real row count must stay **29**.

## The measurement

Stop 3 of the 8-stop museum tour is scored **THIN, 1 distinct fact over 8
sentences**. Its actual content:

> "In the **10th century**, this piece crafted from **chlorite** captures Ganesh
> in a dynamic dance… **eight arms**… The **tambourine** symbolizes… the
> **rosary's** beads… Ganesh's **axe**… the **serpent's** tail… a bowl of
> **modakas**… Originating from the **Bengale** region… the **Pala-Sena
> dynasty**… Ganesh, the son of **Shiva** and **Parvati**."

What the detector saw:

```
dates:        ['10th century']
named_people: []
materials:    []
measurements: []
-> distinct_fact_count = 1
```

A reader counts twelve or more. **This is the blocklist problem again** — the
same flaw LOCAL-293 and LOCAL-294 were dispatched to remove elsewhere, now in the
fact detector LEAD wrote two nights ago.

## Scope — four gaps, all structural

1. **Materials are a hardcoded 12-item list** (schist, lacquer, bronze, cypress,
   silk, gold leaf, wood, cedar, metalwork, lost-wax, embroidery, woodblock).
   `chlorite` is not on it. Neither are terracotta, marble, granite, jade, ivory,
   porcelain, sandstone, alabaster, or anything a non-Asian venue would use.
2. **Measurements require digits** — `\d+\s*(m|cm|kg|arms?|…)`. "eight arms",
   "eleven heads", "three centuries" never match.
3. **Deities and mythological figures are invisible.** The person filter needs a
   verb of doing or a role noun within 90 characters; "embodies", "symbolizes",
   "originating" are not on that list, and Shiva is not a "person" by any rule.
4. **Dynasties, regions and named periods are not a category at all** — Pala-Sena,
   Heian, Bengale, Edo, Meiji.

**Widen by category, not by adding words to a list.** A materials list that grows
whenever a tour mentions a new stone has the same failure mode next month. Prefer
structural signals: a proper noun immediately following "crafted from" / "carved
from" / "made of" is a material whatever it is; "the X dynasty" / "the X period"
is a period whatever X is; a spelled-out numeral before a countable noun is a
measurement.

## The line you must not cross

**Do not inflate the count.** The point is to stop missing real facts, not to
find more of them. Adding generic nouns as "facts" would make every stop look
RICH and destroy the index's usefulness in the other direction.

**Re-measure the whole corpus.** Report the RICH/ADEQUATE/THIN distribution
across `tours/*.txt` before and after. It is currently **5.1% / 24.7% / 70.2%**
over 1,732 stops. A large swing toward RICH means the detector became too
generous — say so rather than shipping it.

**The thresholds may need recalibrating afterwards** (RICH ≥3 facts, density
≥0.50; ADEQUATE ≥2, ≥0.20). If the distribution shifts, propose new numbers with
the measured percentiles — do not silently keep the old ones.

## Verification

- Stop 3 of `tours/LOCAL303_museum_8stop_gate.txt` must count **≥8** facts.
  Paste the detected lists.
- These must **not** become facts: "beautiful views", "rich history", "a sense of
  wonder", "the atmosphere".
- Corpus distribution before/after, with any threshold changes justified from
  measured percentiles.
- Rescore `LOCAL303_museum_8stop_gate.txt` and report base score against the
  current **71.9**.

## Traps
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base` (D147).
- `test_local294_sparql_quality.py` errors under full-suite load from Wikidata
  429s and passes standalone (D220). Not yours.

## Acceptance criteria
- All four gaps closed by category, not by list-extension.
- Stop 3 counts ≥8 facts; the four generic phrases above count 0.
- Corpus distribution reported before/after; thresholds recalibrated if needed.
- LOCAL303 tour rescored against 71.9.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-304.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
