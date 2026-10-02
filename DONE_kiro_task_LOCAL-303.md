**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-303
**Base:** storied
**Branch:** kiro/local303-r7-concept

# R7 catches "azure waters" and misses "azure sky".

Read `DECISIONS.md` D190, `style_validator_detector.py`
(`check_r7_hallucinated_sensory`), `tours/LOCAL302_riviera_2stop_round35.txt`.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>`. **Never run `find` against `/` or `/Users/micha`** —
three sessions were lost that way (D213, D218), and it triggers macOS privacy
prompts on Michael's machine. **If a command has not returned in ~2 minutes it is
the wrong command.** **Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.80**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Run generation with `AUDIOURA_DB_TARGET=production` (the corpus lives there) and
report row counts; production real count must stay **29**.

## The measurement

An integration tour generated on the fully-merged pipeline this morning. R7
reported `0 sentences deleted`. LEAD counted five sensory fabrications in the
delivered text:

```
"the shimmering blue waters of the Mediterranean Sea will be on your right"
"The ancient lighthouse, set against the azure sky, invites exploration"
"The rocky shore offers a cool touch of sea spray"
"The fragrance of exotic gardens that hangs in the air, a sensory delight"
"The rough texture of the ancient stone buildings beneath your fingertips"
```

Fed to the detector directly, **all five return `[]`.** This one fires:

```
"facing the azure waters of the Mediterranean Sea, the sun-kissed peninsula..."  -> R7 HIT
```

**`azure waters` is caught. `azure sky` is not.** LOCAL-286 added patterns of the
form `azure|turquoise|cerulean|crystal-clear` **paired with** `waters|sea|
expanse`. The banned word is only banned next to the words it appeared next to
last time.

## Scope

**Make R7 detect the category, not the collocation.**

The rule it should express: *a sentence asserting a sensory experience the
listener cannot be guaranteed to have — sight, touch, smell, sound, temperature —
presented as fact, without a source.*

Two components, and you need both:

1. **A vocabulary of fabricated-sensory adjectives that fires regardless of what
   noun follows** — azure, shimmering, sun-kissed, sun-drenched, glistening,
   sparkling, verdant, lush, fragrant, rugged, craggy. Today these only fire in
   fixed pairs.
2. **A sensory-assertion shape**, independent of vocabulary — "the [texture/
   scent/sound/feel] of X [verb] beneath/against/in your Y", "a sensory delight",
   "offers a cool touch of". The last three examples above contain no banned
   adjective at all and are still fabrication.

## The line you must not cross

**Do not delete factual sentences that happen to contain a sensory word.** *"The
lighthouse is painted red and white"* is a fact. *"The lighthouse glows against
the azure sky"* is not. The distinction is whether the sentence carries verifiable
content, not whether it contains an adjective.

**Measure the false-positive rate before and after** across all of `tours/*.txt`.
D55's ceiling applies: the corpus-wide R7 rate must not rise more than 3×. If it
does, the rule is too broad — report the number rather than shipping it.

**Do not touch Directions or navigation text.** Those are exempt by design and
Michael has confirmed it.

## Verification

- All five sentences above must fire. Paste the detector output for each.
- These must **not** fire: *"The lighthouse is painted red and white"*, *"Monet
  painted here in 1888"*, *"The chapel dates to 1306"*.
- Corpus-wide R7 rate across `tours/*.txt`, before and after, with the ratio.
- Regenerate a **2-stop Riviera** tour and paste the delivered text. Report
  R7 deletions, word count, and cost against **587 words / $0.0241 / 51.6s**.
- Copy the tour to `/Users/micha/Audioura/tours/`.

## Also worth reporting, not fixing

That same tour scored **both stops THIN** — Stop 1 had **zero facts over two
sentences**. That is a corpus/selection problem, not R7's, and D170 keeps stop
selection free. Note whether your regenerated tour shows the same, but **do not
change selection** to improve it.

## Traps

- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Read the delivered tour as prose (D161) — R7 reported "0 deleted" on a tour
  with five fabrications, so the log is not evidence.
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria

- All five listed sentences detected; the three factual controls not detected.
- Detection is by category, not by fixed collocation.
- Corpus-wide false-positive ratio reported and within D55's 3×.
- Tour regenerated, copied, read as prose.
- Production real count still 29.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-303.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
