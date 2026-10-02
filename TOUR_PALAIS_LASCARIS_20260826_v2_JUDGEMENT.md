# Judgement — Palais Lascaris v2, 3 stops, build `1259f6e` (D533)

**2026-08-26.** Tour: `TOUR_PALAIS_LASCARIS_20260826_v2.md`. Regenerated from the requested
string, not from the previous stop list. Requested 3, delivered 3.

---

## Scorecard against the four things you asked for

| # | Ask | Result |
|---|---|---|
| 1 | Fix the fabrication | ✅ guard runs, no mismatch — **but see the caveat, it is narrower than the defect** |
| 2 | No repeated facts across stops | ⚠️ **partly.** 3 tellings → 2. One repeat kept deliberately; one whole story slipped past |
| 3 | Stop 3 should have real content | ✅ the object is described; **the best detail from run 3 was lost** |
| 4 | Re-run from the string, new documents | ✅ — **same three objects**, as predicted |

---

## 1. The fabrication

The guard **ran** — `no mismatches (30312 chars of corpus checked)` — and the Gautier
birth-year-as-founding-date did not recur. Stop 2 now says *"Antoine Gautier, a distinguished
Niçois collector of the nineteenth century"*, which is true and carries no false date.

**Two caveats, and the second is the important one.**

**(a) The guard did not run on the first re-run.** It crashed:
`Role guard error (non-fatal): sequence item 1: expected str instance, list found` —
`stop_corpus.passages` is a list for some rows, a string for others. It was wrapped in a
`try/except ... non-fatal`, so the tour completed normally and the line scrolled past.
**A non-fatal except around a check that never ran is indistinguishable from a check that
passed.** Fixed and pinned by a test, but the lesson is the same one as the stale container:
the thing looked done from outside.

**(b) The same class of defect recurred in a form the guard does not cover.** Stop 2:

> "In 1942, the city of Nice purchased the Palais Lascaris and undertook its transformation into
> a museum, a vision realized by **its opening as a public institution in 1946**."

The corpus says 1946 is when the palace was **classified as a historical monument** — which is
what stop 1 correctly says, in the same tour. The palace did not open as a museum in 1946.

**A year has been reattached to the wrong event, which is exactly the Gautier defect** — and my
guard checks `(person, year)` pairs only, so an event-year mismatch walks straight through. The
fix I built is narrower than the defect you asked me to fix. That is the honest position, and the
extension is the obvious next task.

## 2. Cross-stop repetition — partly

**What worked.** The 1942 purchase was told in all three stops on the previous run. Now:
removed from stop 3, and the guard reports its reasoning.

**What I deliberately did not do.** Stop 2's copy was **kept**:

```
[D533] REPEATED FACT kept in stop 2 — next sentence refers back to it
       ("This transformation permitted the public...")
```

That is the coherence guard added mid-round, after the previous run opened stops 2 and 3 with
*"This action set in motion…"* and *"Gautier's dedication saw…"* — both pointing at sentences the
guard had just deleted. Deletion is safe for **truth** (it cannot add a falsehood) but not for
**coherence**. So a repeat is now kept rather than orphaning the sentence after it.

**Net: you still hear the 1942 purchase twice**, at stops 1 and 2. Better than three times, not
what you asked for. The real fix is to regenerate the stop without the fact, not to cut text after
the fact — editing prose post-hoc can only ever trade one defect for another.

**And one whole story slipped past the guard entirely.** The Gautier bequest is told twice:

> stop 2: *"The instrumental collection at the Palais Lascaris owes its depth to Antoine Gautier,
> a distinguished Niçois collector… Gautier's bequest formed a core part of the museum's
> holdings…"*
> stop 3: *"Antoine Gautier, a 19th-century nicois collector and amateur musician, bequeathed
> numerous instruments to the museum, enriching the collection."*

Same story, twice, in adjacent stops. **My fact signature is `(year, entity)` and neither telling
carries a year — so both are invisible to it.** That is a real hole in the design, not a tuning
problem: a large share of what a listener experiences as "I have heard this already" is undated.

**The orphan guard is also incomplete.** Stop 3's body still opens mid-thought:

> " The building was declared a historical monument by 1946…"

*Which* building? The sentence naming it was removed. My regex catches demonstratives (*This*,
*That*, *Such*, *As a result*) but not **definite descriptions** — *"The building"*, *"The
palace"*. Widening it to `The <noun>` would refuse almost every removal, so this one needs a real
referent check, not a bigger regex. The leading space is from the same removal.

## 3. Stop 3 — fixed, and you were right about the cause

The diagnosis was not what either of us assumed. Stop 3 **was never starved**: it had 8 search
snippets and the ranker scored `usable=0`, while the **corpus gate — which runs before the search
— had already forbidden the narration from describing the object.** That is why it talked about
the building and admitted the viol's details were "limited" with 8 snippets about the viol sitting
unused. The gate verdict is now lifted once material arrives; all three stops were lifted this run.

Stop 3 now carries the object: *1652 viola da gamba*, *crafted in London*, *English consort
music*, *rich sonorous tones*, the Gautier bequest, and the viol's place in the line to the modern
orchestra.

**But the best detail from the previous run is gone.** Run 3 had *"worked in Aldgate, London,
between 1647 and 1656"* and *"signature heart-shaped motifs"* — the specifics from your Gemini
answer. This run has neither. The knowledge fallback did not fire (correctly — the stop had
snippets, so it was not starved), and the ranker's `usable=0` verdict means what reaches the
prompt is unstable run to run. **The retrieval is working; the selection from it is a lottery.**

Also worth watching: run 3 rendered the heart motif as *"heart-shaped sound holes"*, where the web
evidence says a heart carved into the **back of the scroll**. Different location, same motif —
a specific, checkable detail that moved. It is absent this run, so it is not a defect in this
tour, but it is the shape of error to watch for when the detail returns.

## 4. Same stops, as predicted

Harpe by Naderman, Sacqueboute by Schnitzer, Violes gambe by Turner — identical to the first run.
Stop **selection** is driven by the venue corpus and the LOCAL-349 yield scores, which D533 did not
touch. The stories changed; the objects did not. If you want different objects, that is a change to
selection, and it is a separate piece of work.

---

## Defects that survive from the first review, untouched

- **Stop 1's orientation is worse, not better.** It now previews all three stops *and* summarises
  stop 2's content (*"Then, at Sacqueboute ténor…, Gautier's bequest ensures preservation"*)
  before the listener has reached stop 1. ~250 words of preamble.
- **The closing line is still spliced**: *"There is also a tour of If you would like another
  museum tour, the Musee d Art Moderne…"*
- **"Londres" still ships untranslated** in an English tour.
- **The entity gate still does not run on unscoped museum tours** (`LOCAL-458 SKIPPED`), which
  remains backwards — plain museum tours get the least checking.

## Recommendation, in order

1. **Extend the role guard from `(person, year)` to `(event, year)`.** The 1946 "opened as a
   public institution" error is the same defect you asked me to fix, and my fix does not reach it.
2. **Give the fact guard undated signatures** — entity + relation, not just entity + year. The
   Gautier bequest story is the proof it is needed.
3. **Move de-repetition before generation, not after.** Every problem in section 2 comes from
   editing finished prose. Tell the stop-writer which facts are already spoken for.
4. Stop 1's orientation: stop previewing later stops.
5. Cosmetic: `Londres`, the spliced closing sentence, the leading space.

**No score.** D525 retired the rubric for these reports (base 75.0 across seven consecutive runs
on wildly different tours) and the stop index is not comparable across runs with different prose.
The defects above are worth more than a number would be.
