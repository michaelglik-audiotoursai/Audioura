**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-317
**Base:** storied
**Branch:** kiro/local317-r7-restaurant-register

# R7 has never been tested against a restaurant.

Read `DECISIONS.md` **D236**, `SUBMISSION_LOCAL-303.md`,
`style_validator_detector.py` (`check_r7_hallucinated_sensory`),
`tours/LOCAL314v2_5stop_old_nice_restaurant.txt`.

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

Four sensory fabrications from delivered restaurant tours, run against R7 on
current `storied`:

```
MISSED  the aroma of garlic, herbs, and simmering sauces fills the air
MISSED  the clinking of cutlery and the cheerful hum of conversation spill onto the cobblestones
MISSED  The sounds from the kitchen and the gentle hum of conversations reflect the rhythm of daily life
MISSED  The scent of garlic and herbs weaves through the cozy space
```

**Four of four.** LOCAL-303 widened R7 this morning from collocations to
concepts, and it now catches *"azure sky"*, *"shimmering waters"*, *"the rough
texture of the ancient stone beneath your fingertips"*. It catches the coastal
register it was built against and none of the culinary one.

**This is the third instance of one pattern** (D236): R7 caught `azure waters`
and missed `azure sky`; the material rule caught `carved from chlorite` and
missed `oil on canvas`; now R7 catches sea-and-stone and misses kitchen-and-food.
**Each fix generalises exactly as far as the examples that prompted it.**

## Scope

**Extend R7 to the culinary sensory register**, and do it by asserted-experience
shape rather than by adding food words.

The rule R7 expresses: *a sentence asserting a sensory experience the listener
cannot be guaranteed to have, presented as fact, without a source.* A kitchen
smell is exactly that — we have no evidence the garlic is cooking today.

Cover at least:
- **Smell asserted as present**: "the aroma/scent/fragrance of X fills/hangs
  in/weaves through/wafts".
- **Ambient sound asserted as present**: "the clinking of X", "the hum of
  conversation", "the clatter of pans", "the sounds from the kitchen".
- **Ambient warmth/light in an interior**: "the golden glow of its interior",
  "the warmth within".

**Do not add a food-word list.** *"The scent of jasmine fills the courtyard"* has
the identical fault and no food in it — LOCAL-303 left that one uncaught too and
it is in scope here.

## The line you must not cross

**A dish named as a fact is not a sensory claim.** These must NOT fire:

| must stay clean |
|---|
| "The menu features socca and ratatouille." |
| "Daube is a beef stew braised in wine." |
| "Panisses are crispy chickpea fritters." |
| "The restaurant has served Niçoise cuisine since 1927." |

That distinction is the whole task. Naming a dish is content; asserting the
listener can smell it is fabrication.

**Measure the false-positive rate.** Corpus-wide R7 on parsed stop bodies is
currently **2.77%** (556/20048). D55's ceiling is 3× the pre-LOCAL-303 baseline
of 1.49%, i.e. **4.47%**. Report before and after; exceeding it means too broad.

## Verification
- All four listed sentences fire; the four dish-fact controls stay clean.
- *"The scent of jasmine fills the courtyard as you approach."* fires.
- Corpus-wide rate before/after on **parsed stop bodies**, not raw text — raw
  text includes schema blocks and gives a misleading number (LEAD made that
  mistake reviewing LOCAL-303).
- Regenerate a **5-stop Old Nice restaurant tour** under a NEW filename; report
  R7 deletions and read it as prose (D161).

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). **D186:** spine stays on gpt-4o.
- Directions and navigation text are exempt by design; do not touch them.

## Acceptance criteria
- The four misses now fire; the four dish-facts stay clean; jasmine fires.
- Corpus rate reported on parsed bodies, within 4.47%.
- Tour regenerated under a new filename and read as prose.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-317.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
