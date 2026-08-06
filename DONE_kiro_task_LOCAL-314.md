**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-314
**Base:** storied
**Branch:** kiro/local314-restaurant-corpus

# Restaurant tours now generate. They contain nothing.

Read `SUBMISSION_LOCAL-313.md`, `SUBMISSION_LOCAL-277.md` (the corpus method that
works), `SUBMISSION_LOCAL-283.md` (harvest-on-verification),
`tours/LOCAL313_5stop_old_nice_restaurant.txt`.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
```
Use `command -v <name>`. **Never `find` against `/` or `/Users/micha`** (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**
**Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$1.50**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
Production real row count stays **29**.

## The measurement

LOCAL-313 fixed verification — 0/6 became 8/8, and a 5-stop Old Nice tour now
delivers 5 stops with correct addresses. **Every stop scores THIN with 0 facts.**

Stop 5, Chez Palmyre, in full:

> *"As you meander through the winding streets of Vieux Nice, Chez Palmyre
> emerges as a beacon of culinary tradition. Nestled along a narrow lane, its
> modest facade belies the warmth within… In the golden glow of its interior,
> time seems to slow. The scent of garlic and herbs weaves through the cozy
> space, echoing decades of Niçoise hospitality."*

Not one verifiable claim. The detector is correct; this is invented atmosphere.

**And the facts exist.** LEAD found these in a single web search:

```
Chez Palmyre  — opened 1926 by Palmyre Moni; 25 seats; taken over 2010 by
                Vincent Verneveaux, trained under Guy Savoy and Jacques
                Maximin; three-course menu at €20, changed every third week
Bistrot d'Antoine — 27 Rue de la Préfecture; Gault&Millau listed; pâté croûte,
                boudin en pastilla, cod with tarama yuzu
```

We verified these restaurants against Nominatim and Wikipedia **and threw the
sources away** — exactly the waste LOCAL-283 identified for museums.

## Scope

**Build `stop_corpus` for dining stops, from sources that describe restaurants.**

1. **Harvest on verification.** LOCAL-313 already fetches Nominatim/Wikipedia to
   verify. Persist what those responses contain — address, cuisine type, opening
   year where present — as passages with source URLs, exactly as LOCAL-252/277
   do. Free; the fetch already happens.
2. **Add a culinary source for substance.** Guide entries and press carry what a
   listener wants: founding year, chef, signature dishes, price band. Gault&Millau
   has structured entries; general web search finds the rest.
3. **Every passage carries a date, a named person, a documented event, a dish, or
   a price.** That is the LOCAL-277 bar that took Riviera stops from 1.5 to 6.0
   facts. *"Warm atmosphere"* is not a passage.

## The line you must not cross

**Never synthesise.** Harvested text is extracted, not written. If a restaurant
has no published detail, store nothing and let the stop be thin — a thin honest
stop beats an invented rich one. This is the whole programme (D161, LOCAL-263).

**A passage about Niçoise cuisine in general is not a passage about this
restaurant.** D157: five Matisse stops once shared the museum's own Wikipedia
article, inflating passage counts while giving the generator nothing.

**Do not touch the LOCAL-313 verification path.** It works — 8/8. You are adding
harvest alongside it.

## Verification

- Regenerate the **5-stop Old Nice restaurant tour**. Report facts per stop
  against the current **0.0**, and copy it to `/Users/micha/Audioura/tours/`
  under a NEW filename — do **not** overwrite
  `LOCAL313_5stop_old_nice_restaurant.txt`, Michael is reading it.
- Show 3 sample passages with source URLs. LEAD will fetch and compare.
- Chez Palmyre's stop must contain at least the founding year or the chef.
- Confirm museum and biking corpus paths unregressed.
- **Read the delivered tour as prose (D161)** and say plainly whether it reads
  like a tour worth listening to.

## Traps
- **Run every example you paste** (D97, D103). Judge protected files from
  `git merge-base` (D147). 429 = search failure, not "no data" (D220).
- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, after `SELECT is_test` returns true.
- **D186:** the spine stays on gpt-4o.

## Acceptance criteria
- Dining stops carry `stop_corpus` passages with source URLs.
- Facts per stop materially above 0.0; reported honestly if not.
- Nothing synthesised; no venue-level filler passed off as per-restaurant.
- Michael's existing tour file untouched.
- `git status --short` clean. No container rebuilt.

## PROCESS
Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-314.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⛔ BOUNCED by LEAD — 2026-08-06 14:1x. The harvester works; the quality filter does not.

**Keep the harvest mechanism. It is proven.** Corpus now exists for all six
restaurants and one stop is genuinely transformed.

## The evidence, and it is the clearest we have

**Acchiardo — harvested from Forbes:**

> *"Since 1927, Acchiardo has remained true to its roots… The Acchiardo family
> has been serving classic Niçoise cuisine for nearly a century… The socca, a
> chickpea pancake, reflects the city's Italian influences, while the daube, a
> hearty beef stew, embodies the French heart of Niçoise cooking."*

Dates, dishes, family history. **This is what the task was for.**

**Le Bistrot d'Antoine — harvested from Yelp and a scoring blog:**

> *"the clinking of cutlery and the cheerful hum of conversation… the aroma of
> garlic, herbs, and simmering sauces fills the air… the clatter of pans from
> the open kitchen… earning the restaurant high marks in creativity and
> execution."*

**Zero facts.** Same pipeline, same day. The only difference is the source.

## What went wrong

The task required: *"Every passage carries a date, a named person, a documented
event, a dish, or a price. 'Warm atmosphere' is not a passage."* That filter was
not applied. What got stored:

```
Chez Palmyre          Yelp business listing — "Try Our New Menu - 5 rue Droite,
                      96 Photos, +3349385..."
Le Bistrot d'Antoine  Yelp USER REVIEW — "Went again in Feb 2018 This is about
                      our favorite restaurant"
Le Bistrot d'Antoine  blog scorecard — "Creativity: 7.5/10 · Execution: 8.5/10"
Acchiardo             Forbes — "Since 1927..."          <- the only good one
```

**One of these is worse than useless.** *"earning the restaurant high marks in
creativity and execution"* in the delivered tour is the blog's 7.5/10 laundered
into a sentence that reads like a fact. We have taken an anonymous blogger's
rating and presented it as a property of the restaurant. That is a fabrication
route we did not previously have.

## The fix

**Filter passages at harvest, on content not on source.**

Keep a passage only if it contains at least one of: a **year**, a **named
person**, a **named dish**, a **price**, or a **documented event**. Reject
everything else — including everything from a review site that is just opinion,
photos counts, phone numbers or star ratings.

- **Never store a rating or review score.** Not as a passage, not as context.
  The Bistrot line above shows why.
- **Prefer press and guides** — Forbes, Gault&Millau, local press — over
  aggregators. Acchiardo demonstrates the difference in a single stop.
- **A restaurant with no qualifying passage gets none.** Thin and honest beats
  atmospheric and invented. The stop will score THIN and that is the correct
  answer.

## Also, and this is not yours to fix

R7 did not catch *"the aroma of garlic, herbs, and simmering sauces fills the
air"* or *"the clinking of cutlery"*, despite LOCAL-303 widening it this morning.
Report it; a separate task will handle it.

## Verification
- Passage-level: for each of the six restaurants, list every stored passage and
  the rule that admitted it. LEAD will fetch the URLs and check.
- No passage containing a rating, score, photo count or phone number survives.
- Regenerate the 5-stop tour under a **new filename** — do not overwrite
  `LOCAL314_5stop_old_nice_restaurant.txt`.
- Report facts per stop against the current **0, 0, 1, 0, 2**.
- **State plainly how many restaurants ended with zero qualifying passages.**
  That number is a finding, not a failure.
