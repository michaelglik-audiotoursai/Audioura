**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-316
**Base:** storied
**Branch:** kiro/local316-painting-vocabulary

# "Oil on canvas" is not a material, as far as the detector is concerned.

Read `SUBMISSION_LOCAL-315.md`, `DECISIONS.md` **D200**, `tour_rubric_scorer.py`
(`analyze_stop`, `_MATERIAL_CONTEXT_RE`).

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
Production real row count stays **29**.

## The measurement

The blind-spot monitor flagged Musée National Marc Chagall at **median fact
density 0.000** against a corpus median of 0.264. LOCAL-315 diagnosed it and
LEAD confirmed independently:

```
"canvas"        appears in 29 zero-fact Chagall stops
"oil on canvas" in 3 more
materials vocabulary contains: canvas NO, oil NO, gouache NO
```

The stops carry real material facts. The detector cannot see them.

**Why LOCAL-304 missed this, and it matters.** That task was told to widen *"by
category, not by list-extension"*, and it complied: it added
`_MATERIAL_CONTEXT_RE` matching *"crafted from X"*, *"carved from X"*, *"cast in
X"*. Sound for sculpture. But **"oil on canvas" contains none of those verbs** —
it is a bare medium phrase, a different grammatical construction. The structural
rule generalised across the forms its author considered and stopped there.

That is the same failure R7 had with collocations, one layer up.

## Scope

**Count painting and print media.**

- Bare medium phrases: *oil on canvas*, *oil on linen*, *huile sur toile*,
  *huile sur lin*, *gouache on paper*, *tempera on panel*, *acrylic on board*.
  Note the French forms — this corpus is bilingual and Chagall's catalogue is
  French.
- Support nouns as materials when they appear in that construction: canvas,
  linen, panel, board, paper, vellum.
- Print and technique terms: lithograph, etching, engraving, aquatint, drypoint,
  screenprint, woodcut, fresco, mosaic, stained glass, vitrail.

**Generalise where you can.** *"<medium> on <support>"* is a recognisable shape
and will cover media nobody has listed. Prefer that to a longer word list, but do
not force it — if a bare list is the honest answer for print techniques, say so.

## The line you must not cross

**Do not inflate the count.** The corpus distribution is currently RICH 7.7% /
ADEQUATE 26.6% / THIN 65.7% over ~2000 stops. Report it before and after. A large
swing toward RICH means the rule is too loose — report the number rather than
shipping it.

**These must still count as zero facts:** *"a beautiful painting"*, *"rich
colours"*, *"the artist's vision"*, *"a masterpiece of composition"*.

**Do not change any threshold.** If the distribution moves enough to warrant
recalibration, say so with the measured percentiles and stop; that is a separate
decision.

## Verification
- Chagall median density before and after; it should move off 0.000.
- Five specific zero-fact Chagall stops shown before and after, with the terms
  now counted.
- Corpus-wide distribution before and after.
- The four generic phrases above still score 0.
- Asian Arts Museum unregressed — it was 0.408 median.
- Re-run `blindspot_monitor.py` and report whether Chagall is still flagged.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). The corpus is bilingual; French terms matter.

## Acceptance criteria
- Painting and print media counted; French forms included.
- Chagall median off 0.000; per-stop evidence shown.
- Corpus distribution reported before/after; no large swing to RICH.
- Generic art language still scores 0; Asian Arts unregressed.
- No threshold changed.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-316.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
