# Judgement — Restaurant tour in Monaco: story gate 3 of 3 (D551/D552)

**2026-08-29.** Tour: `TOUR_MONACO_RESTAURANT_20260829_v4.md`.
**Le Louis XV – Alain Ducasse · La Montgolfière · Café de Paris Monte-Carlo.** 694 words.

---

## The three things Michael asked

### 1. "Did we establish the minimum size?" — yes, two floors

- **`_RETRY_FLOOR = 120`** — hard floor; below it a stop counts as hollowed out
- **`_THIN_FLOOR = 300`** — the target that triggers *"add another story"*

Café de Paris has landed between them on every run (164–253). **The trigger fires every time; what
it was not doing was telling the stories properly** — one headline instead of two full episodes.
That instruction is now explicit, and the result is below.

### 2. The Crêpe Suzette story, told in full

> *"In 1896, **Henri Charpentier** accidentally created the famed Crêpe Suzette here when a pan
> ignited in front of the Prince of Wales, who promptly requested it be named after a young
> Frenchwoman in his entourage, **Suzette**. The following year, in 1897, **André Michelin** added
> to the café's lore by crashing his automobile through its front windows during the
> Marseille–Nice–Monte-Carlo motor race, providing unexpected publicity."*

Both episodes Michael cited are there — the naming of the dish, with Charpentier and Suzette named,
and the Michelin crash. His complaint was that the tour *"abruptly stopped without explaining who
Suzette was"*; it now explains it.

**The retrieval was never the problem.** Gemini had already returned Charpentier and Suzanne
Reichenberg by name, plus La Belle Otero and Liane de Pougy, the 1929 Grand Prix terrace used as a
triage post, and the SBM's undercover spotters watching for ruined gamblers. **The narration was
compressing rich facts into headlines.** The story block now requires two episodes, each told with
every person the fact names, what went wrong, what came of it — and where a fact explains why
something is called what it is, that explanation delivered.

### 3. Restaurants only — verified, not assumed

Museums call the knowledge fallback with `focus='object'` and **never reach the restaurant
question**. They were never at risk. But the previous change also routed `focus='place'` — walking
and biking stops — through it, and the biking tour is work Michael has already accepted. **Narrowed
to `focus == 'restaurant'`.** Confirmed inside the container.

## Story gate: 3 of 3 — a first

```
✓ PASS  Le Louis XV        story_units=1
✓ PASS  La Montgolfière    story_units=1
✓ PASS  Café de Paris      story_units=1
```

Every previous tour on every path topped out at 1 or 2. This is the first time every stop carries a
verified story-unit — ≥3 sentences with a named person, real actions and an arc.

## Two corrupted sentences, found and fixed

The previous run shipped:

> *"the future King Edward, **the first British monarch of his house, VII**, then Prince of Wales"*
> *"with journalists and diplomats gathering **III and Princess Grace** navigated international
> tensions"*

The `LOCAL-269` reference gate matches a royal name **without its numeral** — so it spliced a gloss
inside *"Edward VII"*, and dropped *"Prince Rainier"* leaving *"III"* stranded. **The gate is old
and correct for ordinary names; a tour full of Rainier III, Edward VII and Albert II is what
exposed it.** Fixed by extending the matched span over a trailing Roman numeral, guarded so an
initial is not mistaken for one (*"Henri C. Charpentier"* must not become *"Henri C"*).

Verified absent from this run: no orphaned numeral, no gloss inside a regnal name.

## What I would still fix, and one thing to check before accepting

**1. A contested name is stated as fact.** Michael's source says **Édouard** Michelin; the tour says
**André**. Asked directly, Gemini's own answer is:

> *"Historical accounts are uncertain and conflict… most detailed racing records and local Monaco
> historical archives specifically name **Édouard** Michelin as the driver."*

So the record is genuinely disputed **and the tour picked the less-supported name and asserted it
flatly.** The structuring pass is instructed to preserve hedges, but only hedges that survive into
the retrieved prose — here the source stated it confidently. **A "contested fact" signal is real
missing work**, not a one-off typo, and it is the honest reason not to call this finished.

**2. The tour is short this run — 694 words**, against 978 and 995 on the two before it. Le Louis XV
alone went 495 → 250. **This is run-to-run variance, not a regression from the regnal fix**, which
only alters name spans; but the spread is wide enough that stop length is not yet under control.

**3. `closure_scan` remains the weakest component** — three false positives this week against zero
true positives the corpus had not already caught. It did not misfire here. **Demote to advisory.**

## Recommendation

**Accept for mobile testing, with the Michelin name corrected or hedged.** The blocker Michael set
— *"without stories about people we cannot go to release"* — is cleared: 3 of 3 stops carry them,
including both episodes he named.

For the phone: **server IP `192.168.0.136`**, and request a location not yet generated, or
`tour_cache` will answer instead of the pipeline.
