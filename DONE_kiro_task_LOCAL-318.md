**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-318
**Base:** storied
**Branch:** kiro/local318-dangling-demonstrative

# "This chickpea flour pancake" — no pancake was ever mentioned.

Read `generate_tour_text.py` PHASE 5.7 (the dangling-reference scrub),
`unglossed_reference_gate.py`, `tours/LOCAL314v2_5stop_old_nice_restaurant.txt`.

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
LOCAL-317 is in `style_validator_detector.py`. Stay out of it.
Production real row count stays **29**.

## The defect

From a delivered tour, Stop 2 (Acchiardo):

> *"…Madalin's great-grandchildren continue to honor her culinary traditions…
> **This chickpea flour pancake**, cooked to a golden crisp, exemplifies the
> region's resourcefulness…"*

**No pancake has been mentioned.** The word "socca" appears exactly once in the
entire tour — in **Stop 4**, inside a `Specific Examples:` schema line that is
never spoken. A listener hears a demonstrative pointing at nothing.

**PHASE 5.7 ran on this tour** — the log shows *"Dangling-reference scrub
complete"* — and did not catch it.

Most likely cause: the scrub checks pronouns (*it*, *he*, *they*) but not
**demonstrative noun phrases** — *this X*, *these X*, *the aforementioned X* —
where X is a noun never introduced. Verify that before fixing; do not assume.

## Scope

**A demonstrative noun phrase must have an antecedent in the same stop.**

- Detect `this|these|that|those + <noun phrase>` where the head noun, or a
  synonym the stop has used, does not appear earlier **in the same stop's
  delivered text**.
- **Same stop, not same tour.** Stops are heard minutes apart and may be
  reordered or dropped; a reference across stops is already broken. Stop 4
  naming socca does not license Stop 2 saying "this pancake".
- **Schema lines never count as an antecedent.** `Specific Examples:`,
  `Type/Specialty:` and the rest are not spoken. That is precisely how this one
  slipped through.

**On finding one, prefer repair over deletion**: substitute the actual name if
the stop's corpus supplies it — *"Socca, a chickpea flour pancake, exemplifies…"*
— and delete the sentence only when it cannot be repaired. LOCAL-289 established
that pattern for the gloss degrade path; reuse the machinery rather than
inventing a second one.

## The line you must not cross

**Do not flag legitimate demonstratives.** These are fine and must NOT fire:

| must stay clean |
|---|
| "This restaurant opened in 1927." (the stop IS the restaurant) |
| "Chagall painted the ceiling. This work took two years." (antecedent present) |
| "These narrow streets wind through Vieux Nice." (the setting is established) |

The stop's own title is a valid antecedent. So is anything named earlier in the
same stop.

**Do not invent an antecedent.** If corpus does not supply the name, delete the
sentence. Writing in a plausible dish would be fabrication (D161, LOCAL-263).

## Verification
- The Acchiardo sentence is caught, and repaired or removed — show the before
  and after.
- The three clean cases above do not fire.
- Corpus-wide: how many delivered stops in `tours/*.txt` contain a dangling
  demonstrative? That number is the finding; report it whatever it is.
- Regenerate a 5-stop restaurant tour under a NEW filename and read it as prose.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). **D186:** spine stays on gpt-4o.
- Parse stop bodies with schema lines stripped — `tour_rubric_scorer.parse_tour`
  already does this correctly.

## Acceptance criteria
- Dangling demonstratives detected within a stop; schema lines excluded as
  antecedents.
- Repair preferred; deletion only when unrepairable; nothing invented.
- Three clean cases unaffected.
- Corpus-wide count reported.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-318.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
