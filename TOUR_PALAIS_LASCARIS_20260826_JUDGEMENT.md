# Judgement — Palais Lascaris, 3 stops, build `5b8a30f` (D532)

**2026-08-26.** Tour: `TOUR_PALAIS_LASCARIS_20260826.md`. Requested 3 stops, delivered 3.

---

## First, the thing you need to know about this tour as evidence

**It does not exercise today's change.** "Musée du Palais Lascaris, Nice, France" names no
exhibition, so `_exhibition_scope` is None, the checklist path never runs, and the tour goes down
the permanent-collection **D1v2** route instead. No stop was page-sourced, no scope veto fired, no
stop was labelled.

That makes it a good **regression check** — D532 touched the shared POI structure and the
existence gate, and this tour proves the ordinary path still produces a full-length tour — and it
makes it **not** evidence that option B-real works. For that, see the last section: a second run on
the MFA exhibition, where the veto fired three times.

I am flagging this rather than quietly presenting the tour as a demonstration.

---

## Verdict

**Delivers, with three defects. One is a fabrication, and it is the serious one.**

| | |
|---|---|
| Stop count honoured | ✅ 3 requested, 3 delivered, `LOCAL-394` invariant OK |
| Stops real | ✅ 6/6 D1v2-verified against venue corpus, tier `exhibit_museum` |
| Existence gate | ✅ LOG_ONLY, 6/6 verified (100%), 0 would be dropped |
| **Fabricated date** | ❌ **Gautier's birth year shipped as a founding date** |
| **Unsourced attribution** | ❌ "researcher Fischer" survived a guard that reported dropping it |
| Cross-stop repetition | ❌ the 1942/1946 paragraph is told twice, stops 1 and 3 |
| Part 4 (callbacks) | ⚠️ omitted after failing verification twice |
| Story gate | ⚠️ 0 story units on all three stops |

---

## Defect 1 — a birth year became a founding date. This is a fabrication, and the source is right there.

The tour, stop 1:

> "…from François Joseph Naderman's harp studio in 1825 to **the quartet founded by Antoine
> Gautier in 1825**."

The corpus the tour was built from says:

> "Antoine Gautier, a passionate collector and amateur musician **born in Nice in 1825**…"

**1825 is when Gautier was born.** The tour has him founding a quartet as a newborn. This is not a
retrieval failure — the correct fact was in the retrieved passage, and the generation step
converted "born in" into "founded". Note the tell in the same sentence: *two different* 1825s,
Naderman's studio and Gautier's quartet. A date got smeared across two entities.

Also visible in the log, and it is the same shape:

```
'Antoine Gautier, a passionate collector and amateur musician born in'
    (person_descriptor) — no snippet contains this assertion
```

A checker did notice something wrong with this sentence and did not stop it.

**Why this one matters more than the other two:** every gate on this tour passed. `LOCAL-16`
green, existence gate 100%, D1v2 6/6. **A tour can clear every gate and still tell the listener
something the source contradicts**, because the gates verify that the *stop* exists, not that the
*sentence* is true. That is the same lesson as D525's "passed all nine checks AND contained a
mangled name", now with a date instead of a name.

## Defect 2 — a guard fired and the text shipped anyway

The tour, stop 2:

> "…meticulously documented in the Historic Brass Society Journal by **researcher Fischer**, who
> highlighted its significance…"

The log:

```
Glosses applied:
  • Historic Brass Society Journal → DEGRADED (name dropped)
```

**The degradation applied to a gloss, not to the body sentence.** The body kept the attribution,
including a named researcher the corpus never names. The Historic Brass Society Journal is real;
"researcher Fischer" is the tour's own addition, and it is exactly the kind of specific,
checkable-sounding citation a listener has no way to doubt.

Adjacent, and worth more than this one instance:

```
[LOCAL-458] entity gate SKIPPED: no exhibition scope (unscoped museum tour)
```

**The entity gate only runs on exhibition tours.** A plain museum tour — which is what most
requests are — gets *less* attribution checking than an exhibition one. That is backwards, and it
is a structural gap rather than a bug in this run.

## Defect 3 — the same paragraph twice

Stop 1: *"In 1942, the city of Nice purchased the Palais Lascaris, a seventeenth-century
aristocratic building, with the goal of transforming it into a museum… classified as a historical
monument in 1946."*

Stop 3: *"In 1942, the city of Nice purchased the seventeenth-century Palais Lascaris with the
intention of transforming it into a museum. In 1946, the palace was classified as a historical
monument…"*

Near-verbatim, two stops apart, in a three-stop tour. A listener walking the museum hears the
building's acquisition story told to them twice in about six minutes. The `CORPUS-GATE` logged
`verdict=VENUE_ONLY action=SHORTENED` on **all three** stops — the venue's history is the only
corpus material there is for these objects, so every stop reaches for the same paragraph. That is
the corpus-depth problem, not a prose problem.

---

## What is thin rather than wrong

**Stop 3 has no object in it.** It says so itself: *"While specific details about this viol's
appearance are limited."* Honest, and better than inventing — but it means the stop never names a
physical property of the thing the listener is standing in front of, which is the D468–D471 rule
that moved the score. 290 words about the building and the bequest, nothing about the viol.

**Stop 1's orientation front-loads the whole tour.** It names all three stops before the listener
has reached the first one, then says *"Your first stop is Harpe by Naderman"*. 455 words, most of
them scene-setting.

**"Violes gambe by William Turner (Londres, 1652)"** — the French corpus title ships untranslated
into an English tour. *Londres* should be *London*. Cosmetic, visible, easy.

**The closing line is broken:**

> "There is also a tour of If you would like another museum tour, the Musee d Art Moderne et d Art
> Contemporain nearby"

A template splice. Two sentences fused. Also note the accents are stripped there (`Musee d Art
Moderne`) while stop titles keep theirs.

**Part 4 was omitted.** Two attempts, both failed the same check — `date '1652' not found in any
stop description` — because stop 3 never states 1652 in its body, only in its title. So the tour
has no cross-stop callback section at all, and by the D530-era rubric arithmetic that is the
component with the largest single effect on the score.

**Story gate: 0 story units on all three stops**, `thesis_ok=False` throughout. Informational, does
not block delivery. These are competent museum-label paragraphs, not stories — nothing is at
stake in any of them, which is the "SAY WHAT IT COST" rule going unmet.

---

## The run that does exercise D532

Same build, same container, run alongside: `Picasso, Miro, Dali: Unbound exhibition at MFA,
Boston, MA`, 3 stops.

```
[LOCAL-364/D530] SHORTFALL: exhibition page yielded 2 work(s), listener requested 3
[D532] Provenance: 2 page-sourced, 3 knowledge-proposed
[D532] SCOPE VETO 'Woman in a Hat'            — dimension=form: painting vs livres d'artiste
[D532] SCOPE VETO 'The Farm'                  — dimension=form: painting vs livres d'artiste
[D532] SCOPE VETO 'The Persistence of Memory' — dimension=form: painting vs livres d'artiste
[D532] 2 stop(s): 2 confirmed by the venue page, 0 unconfirmed and labelled
[D530] ⚠️  LISTENER ASKED FOR 3 STOP(S), DELIVERING 2 — source='prose_llm'
```

**Phase 3A reached for famous paintings again — including The Persistence of Memory, the exact
work D530 recorded — and the veto stopped all three on the form dimension.** Against D530's run,
where five works went into D1v2 and **all five were dropped, including the museum's own two, for a
zero-stop tour**: the page-sourced works survived. The trust travelled.

**Three honest qualifications, none of them small:**

1. **The tour is still 2 stops, not 3.** B-real prevented fabrication; it did not fill the gap.
   Phase 3A proposes famous works, all of which are paintings, all of which get vetoed. The
   promotion path — the mechanism that was supposed to bring back *Au Soleil du Plafond* and
   *Moses and Monotheism* — **never fired, because Phase 3A never proposed them.** My worked
   example for you predicted "3 stops, all correct"; the live answer is 2 correct stops and an
   announced shortfall. **The missing piece is that Phase 3A is not told the declared form.** It
   is asked for works at the venue, so it returns the venue's greatest hits. Telling it the page
   declares livres d'artiste is the next change, and it is small.
2. **The 2 delivered stops are the same work twice** — `Le Lézard aux plumes d'or` and
   `Le Lézard aux plumes d'or (detail)`. That is D528 defect 1, the `(detail)` caption filter,
   which D530 left open and D532 did not touch. So the real delivered content is one work.
3. **0 stops were labelled**, so option C's disclosure has not been exercised end-to-end on a live
   tour. The code path is unit-tested; it has not yet spoken to a listener.

---

## Recommendation

**Ship the tour, fix the fabrication first.** In priority order:

1. **The birth-year/founding-date conversion.** A tour that passes every gate and still contradicts
   its own source is the worst failure mode we have, because nothing flags it. Start with the
   `person_descriptor` checker that noticed and did not act.
2. **Run the entity gate on unscoped museum tours.** It is skipped on exactly the tours that get
   the least other checking.
3. **Give Phase 3A the declared form** — the cheapest path from 2 correct stops to 3.
4. **The `(detail)` filter** (D528 defect 1, still open after three decisions).
5. Cosmetic: `Londres` → `London`, and the spliced closing sentence.

**Not recommended:** reading anything into the absence of a score. I did not compute a rubric
number, because D525 retired it for these reports — base 75.0 across seven consecutive runs on
tours that differed enormously, including a fictional one — and because the stop index is not
comparable across different stop sets (D528). Three runs of this venue would be needed for a
number that means anything, and the defects above are worth more than the number would be.
