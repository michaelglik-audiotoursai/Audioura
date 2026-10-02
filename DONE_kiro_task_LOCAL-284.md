**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-284
**Base:** storied
**Branch:** kiro/local284-selector-corpus-tiebreak

# Seven well-sourced objects sat unused while the tour picked five with no corpus.

Read `DECISIONS.md` **D170** (Michael's ruling on selection — binding),
D188, D187, D183, `generate_tour_text.py` (PHASE 3A / R4 replenishment),
`stop_existence_gate.py`.

## ⚠️ NO container rebuilds (D48). Ceiling **$1.00**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
LOCAL-280/282/283 are in `generate_tour_text.py` and the gate. Coordinate or
rebase; do not fight them.

## The measurement

A 5-stop Musée des Arts Asiatiques tour delivered **1.6 facts per stop**. Not
because corpus was thin — because it used five objects we hold **nothing** for,
while seven well-sourced ones went unused:

```
USED (0 passages each)              UNUSED (passages available)
  Les paysages de l'ame               La danse cosmique de Ganesh      6
  La geste de Bouddha                 Ulysses Grant au Japon           6
  L'art en exil - Ham Nghi            L'Armure d'Ando Naoyuki          6
  Hokusai - Voyage au pied du Fuji    Statue de Bouddha                6
  Armure du Clan Hotta                Kannon a mille bras              5
                                      Kannon, le bodhisattva           5
                                      Robe de pretre taoiste           4
```

The same class of miss as the Riviera, where corpus existed under "Old Town of
Antibes" while the selector drew "Old Town Antibes" (D187).

## Scope — and the constraint is the important half

Make the selector aware of corpus depth **as a tiebreak only.**

### Michael's ruling that binds this task

D170, this morning: *"I do not want to enforce anything artificial on the tour
generation: if they have different stops, so to be it. That is fine."*

He was asked again today whether this work could harm the Riviera tours. A
selector that prefers stops we happen to have scraped is a soft version of the
artificial constraint he rejected — it would quietly narrow every Riviera tour
toward Cap d'Antibes and Èze because that is where our corpus is deepest, **not
because they are the best stops**.

So:

- **Corpus depth breaks ties among candidates the selector already considers
  comparable.** It never promotes a minor stop over a notable one.
- **Never exclude a stop for having no corpus.** If Port de Nice belongs on the
  route, it goes on the route and the answer is to fix the corpus (LOCAL-277's
  method), not to route around it.
- **Variety must survive.** Report the distinct stops drawn across ≥5 runs
  before and after. If the after-set is materially narrower, that is a failure
  of this task, not a success.

### The museum case is different and clearer

For a **museum**, the candidate set is the venue's own canonical titles — a
closed list of real objects, all equally "notable". Choosing the seven we can
actually describe over five we cannot is not narrowing; it is competence. Apply
the preference more strongly here, and say in the submission why the museum case
differs from the geographic one.

## MUST NOT REGRESS — Michael's explicit concern

He asked: *"Can these make the Walking tours suffer?"* Prove they do not.

Run **≥3** 2-stop and **≥1** 8-stop Riviera tours. Report against today's
measured baselines:

| baseline | value |
|---|---|
| Cap d'Antibes + Port de Nice | **6.0** facts/stop |
| 8-stop Riviera | **8.8** facts/stop, **53** total |
| 2-stop words / time | ~700–800 / ~43s |
| distinct stops drawn across runs | report before and after |

**Below the baselines, or a materially narrower stop set, is a bounce.**

## Then measure the thing this is for

Regenerate the **5-stop Musée des Arts Asiatiques** tour. Report which objects
were chosen, their corpus depth, and facts per stop against the **1.6** baseline.

**Copy every generated plain-text file to `/Users/micha/Audioura/tours/`.**

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`.
  `audio_tours` before and after; Nice list `[1,12,14,17,24,29,152]`.
- Tests run against `audiotours_test` (D148).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read every delivered tour as prose (D161).
- **D186:** the spine stays on gpt-4o.
- Corpus lookup must use the normalised name matching LOCAL-277 added, or this
  will miss the same way the Riviera did.

## Acceptance criteria

- Corpus depth used as a tiebreak; never as an exclusion.
- Museum selection prefers objects with corpus; rationale for the difference
  stated.
- Riviera baselines held or improved, across ≥3 runs.
- Stop variety reported before and after; no material narrowing.
- Museum 5-stop facts/stop reported against 1.6.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-284.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ADDENDUM — LEAD, 2026-08-05 18:08. The Riviera bar in this task is unsound.

**Do not treat the fact-per-stop baselines in this task file as a pass/fail
gate.** LEAD set them and they are not valid regression bars.

D192, written after LOCAL-283 hit the same wall: the **8.8 facts/stop** figure
came from LOCAL-277's run, which drew the eight stops LOCAL-277 had **just
enriched**. LOCAL-283 drew eight different stops — two of them with zero corpus
— and came in at 5.4. That is the D183 confound, where facts per stop moves 4×
on selection alone, not a regression.

**What to report instead**, since stop selection is free (D170) and must stay so:

1. **The stops each run drew, with each one's corpus depth.** A run that draws
   Port de Monaco (0 passages) is not comparable to one that draws Èze (6).
2. **Facts per stop normalised against available passages** — facts delivered
   over passages available, per stop. That survives a varying draw.
3. **Distinct stops across runs, before and after.** This is the number that
   actually tests your change: if corpus-depth tiebreaking narrows the drawn set,
   that is the failure Michael was worried about, and it shows up here rather
   than in a fact count.

A raw per-tour fact count going down is **not** grounds to abandon the change,
and going up is **not** proof it worked. Report the normalised figures and the
stop sets, and state plainly what they do and do not show.

The rest of the task stands unchanged — tiebreak only, never exclusion, and the
museum case argued separately.
