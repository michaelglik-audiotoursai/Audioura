# Judgement — Palais Lascaris v3, 3 stops, build `3bde6e8` (D534)

**2026-08-26.** Tour: `TOUR_PALAIS_LASCARIS_20260826_v3.md`. Regenerated from the requested
string. Requested 3, delivered 3.

---

## Your three asks

| # | Ask | Result |
|---|---|---|
| 1 | ANY information not repeated across stops | ✅ **your 1946 case is fixed**; one repeat kept on purpose, reason below |
| 2 | Stops 2 and 3 too small — add another story | ⚠️ **stop 3 yes (259→378w), stop 2 no (226→246w)** |
| 3 | Fix all you can, regenerate | ✅ 4 regenerations; **2 defects found in my own fixes and repaired** |

**Size, measured across the day:** v2 994 words → v3 890 → v4 963 → **v3-final 1,049**.
Stop 3 now clears the 300-word bar; stop 2 does not.

---

## 1. Repetition — your case is closed

The 1946 monument classification, told at stops 1 and 3 in the version you read, appears **once**.
So does the 1942 purchase. `check_cross_stop_fact_repetition` on the delivered text returns one
signature, discussed below.

**Why it escaped before, precisely.** Neither sentence had a capitalised subject — *"**This
decision** set the stage for its classification…"* / *"**The building** was declared…"*. My
signature was `(year, proper-noun)`, so it was blind to both. Word overlap is ~0.35. And
embeddings scored it below any usable threshold, measured, because stop 3's sentence buried the
shared claim under three other clauses. It needed **two** detectors, not a better threshold:
semantic for paraphrase, and `(year, uncommon-noun)` for the diluted case.

**Your orientation note changed the design, not just my recommendation.** The preview restates
every stop by construction. Counting it as a first telling produced **four false positives** on
the real tour and would have had stop 2 regenerated for describing its own object. It is now
exempt in both detectors, with your words in the code and a test that fails if the exemption is
removed.

**One repeat survives, deliberately:**

```
[D533] REPEATED FACT kept in stop 3 (1581/sacqueboute)
       — next sentence refers back to it ("These historical instruments trace the l...")
```

Removing it would leave *"These historical instruments…"* pointing at nothing. That guard exists
because an earlier run of mine did exactly that — stops opening with *"This action set in
motion…"* after I deleted the action.

## 2. Size — half done, and the reason is the corpus

**Stop 3: 259 → 378 words**, and it now passes the story gate (`story_units=1` — a named person,
real actions, an arc). **Stop 2: 226 → 246**, still under the 300 bar.

**You asked what our size is. It was 120 words**, which is why nothing ever fired: stop 2 was 226
and stop 3 was 259, both clear of it. A story-unit is separately defined as ≥3 sentences with a
named person, real actions and an arc — and every stop in the tour you reviewed scored **zero**.
I added a second bar at 300 words (`TOUR_THIN_STOP_FLOOR`) that triggers the existing rotation.

**What the v3 run taught, and it is the useful finding:**

```
[LOCAL-491] step 7b: rotating to the venue fact — institutional context
```

All three stops rotated to the **same** next fact — the museum's institutional history — which is
exactly the material the repetition ban forbids. **The two new mechanisms were fighting**, and
stop 2 came out *shorter* (226 → 179). Underneath: `D489` reported every stop as
`volume=VENUE_ONLY`. Every retrieved snippet was about the *museum*, none about the *instrument*.
**There was no second object-level story to rotate to.**

That is now fixed at the retrieval end — the knowledge fallback's trigger was a snippet count
(`< 2`), and these stops had 7, so it never fired. The real condition is *absence of object-level
material*, which the corpus gate already knew. Retriggered on that, it fetched 4/4/5 web-grounded
high-confidence facts and stop 2 gained *"active since before 1545"*, *"the oldest known example
of its kind"*, and the bell garland bearing Schnitzer's mark.

**Why stop 2 still falls short, honestly:** the fallback delivers **facts**, and the story gate
wants a **story**. More facts is not more story, and stop 2's material is a maker and an object
with no episode attached — nobody does anything with a consequence. Padding it would have been
easy and I instructed against it explicitly. **A short honest stop beats a padded one**, and
that is where stop 2 sits.

## 3. Two defects in my own fixes

**(a) A user-facing false statement.** The v4 tour told listeners about the Turner viol:
*"the museum's listing doesn't name this one, so it may or may not be out today."* **That viol is
in the permanent collection** — D1v2-verified against the venue's own corpus. I had reused D532's
`confirmation='knowledge'` flag, which means *"the venue's listing does not name this **work**"*,
to mean *"some **facts** came from the web"*. Two claims, one flag, and option C spoke the wrong
one. Telling a listener a genuine exhibit might be absent spends the exact trust the disclosure
exists to protect. Fixed; verified absent from this tour.

**(b) The guard broke coherence before it broke anything else.** Deleting a repeated sentence left
the next one dangling. Deletion is safe for **truth** — it cannot add a falsehood — but not for
**coherence**. The repair is now regeneration with a ban on the *information*, so nothing is cut
out from under a following sentence.

---

## What still needs doing

1. **Stop 2 needs an episode, not more facts.** The retrieval now finds object-level material; the
   gap is that none of it is a story. This is the `story_units` problem and it is the real
   remaining quality ceiling — 1 of 3 stops passes.
2. **The closing line is still spliced**: *"There is also a tour of If you would like another
   museum tour, the Musee d Art Moderne…"* — untouched all day, and it is the most visible defect
   left in the artifact.
3. **"Londres"** still ships untranslated in an English tour.
4. **The entity gate still does not run on unscoped museum tours** (`LOCAL-458 SKIPPED`).
5. **`(event, year)` role checking.** The v2 tour's *"opening as a public institution in 1946"* was
   the Gautier defect in a form my `(person, year)` guard cannot see. It did not recur here, but
   nothing prevents it.

**Dropped from my previous recommendations at your instruction:** stop 1's orientation preview.
You like it, it stays, and the repetition guards are built around keeping it.

**No score.** D525 retired the rubric for these reports and the stop index is not comparable
across runs with different prose.
