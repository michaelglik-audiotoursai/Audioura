# My judgement on the tour of 2026-08-24, 12:23

Companion to **`TOUR_MFA_20260824_1223.md`**, which is the tour verbatim. Written after reading
it line by line, not from the scores.

**One generation. Not a best-of, not a worst-of** — the run was launched once and this is what
came out.

---

## 1. Your four fixes, and whether each one actually landed

| # | asked for | in this tour |
|---|---|---|
| 1 | no bracketed citations; cite only on disagreement, inside the sentence | **0 brackets.** Every previous run had 3–4 |
| 2 | no intra-sentence duplication | **fired 0 times — and one instance got through.** See §2 |
| 3 | no spoken `Closing:` / `Narration:` label | **gone.** `Orientation:` and `Directions:` kept, as you said |
| 4 | generate once | **once** |

### (1) Citations

Stop 3 now tells a disagreement the way you asked for — in words, no brackets:

> "While some records note that the illustrations were printed on lambskin, others describe the
> sheets as sheepskin and silk."

That is the whole rule working: the disagreement is material, so it is told; the agreement is
just stated. Two changes were needed, not one. The PART 2 prompt now forbids brackets and asks
for attribution by institution ("Christie's records eleven plates; Sotheby's lists twelve"), and
a deterministic stripper stands behind it — a prompt is a request, not a contract, and the loop's
*first* prompt still asks for sources in brackets, which is correct because the adjudicator needs
to know what backs what.

### (3) The label

`Closing:` is gone from the tour and stays in the scorer's pattern, so the tours already on disk
score exactly as before — 75.0, 66.7, 75.0, which I checked because that was the risk. I also had
to teach the scorer to recognise a **news-only** closing, which D519 made possible by removing
the Treat Page: before that, a closing reading only *"We can also generate news articles…"*
matched nothing except the label I was deleting, and its proper nouns would have started counting
as narration facts.

---

## 2. Where I got it wrong, again — the duplicate moved and my rule did not follow

**The sentence you objected to is in this tour, in a new position.** Stop 1:

> "This work is now part of the Museum of Fine Arts' collection, thanks to the generous gift of
> Boris Fridman, **the collector who gave this work to the museum**."

The gift is given twice, exactly as before. My rule only looked at clauses in the *middle* of a
sentence — the 10:36 example had it there — and this one puts it at the **end**. I excluded the
final clause to protect trailing participles like *"…, enriching the museum's collection"*, but
those were already protected by the requirement that the clause open with a determiner or a
relative pronoun. The exclusion bought nothing and cost the fix.

**It is fixed now and proven against this exact sentence**, which is why I am not asking you to
take it on faith:

> "This work is now part of the Museum of Fine Arts' collection, thanks to the generous gift of
> Boris Fridman."

All six control appositives still survive untouched, including two new trailing-clause cases.

**I did not regenerate to make this document look better.** You said generate once, and the point
of that instruction is that a tour I ran again after a fix is a different measurement, not a
better one. So the tour above is the tour, with the defect in it, and the fix will show in the
next one you ask for.

---

## 3. What is genuinely better

**Stop 3 is the best stop of the day.** It reads as one continuous account with nothing repeated
and nothing bracketed:

> In 1916, art dealer Léonce Rosenberg brought together the poet Pierre Reverdy and the painter
> Juan Gris… The original plan paired twenty of Reverdy's poems with plates by Gris, but work came
> to an abrupt halt when Gris died of kidney failure in 1927 at just forty years old… Nearly
> thirty years later, publisher Tériade revived and reconceived the abandoned project. When the
> portfolio finally appeared in 1955, Reverdy issued the text as a tribute to the memory of the
> friend who had died decades before.

Rosenberg is new — no previous run named who brought the two men together. The cause of death and
the age are new. And the last sentence is the first time the tour has landed an emotional beat
without being told to.

**The index spread is the tightest measured**: 68 / 70 / 72, mean 69.7, against ranges of 44–77
and 69–82 in the two earlier runs today and 64.3–72.3 across the three D515 runs. One run proves
nothing about variance, but no stop was weak, which has not been true before.

---

## 4. What I would not ship

### (a) Stop 2 states the priest error as fact, and nothing contradicts it

> "Sigmund Freud… proposing the controversial theory that Moses was an **Egyptian priest**."

Freud argued Moses was an Egyptian **nobleman**. On 08-23 this stop carried both versions and my
checker caught it because both were present. **Here only the wrong one is present, so the check
stays silent** — it was written to find a self-contradiction, and a tour that is confidently
wrong in one direction is a different and worse thing. The story that would have corrected it
went elsewhere this run.

### (b) Stop 1 is bloated and says the exhibition's thesis three times

Not intra-sentence, so §2's fix cannot see it — three different sentences making the same point:

> "…exemplifies the exhibition's argument that books can be revolutionary art forms."
> "…highlights the role of such collaborations in reshaping the book as an art form."
> "…resonating with the broader themes of the 'Picasso, Miró, Dalí: Unbound' exhibition."

Stop 1 is roughly twice the length of stops 2 and 3 and carries the least. **This is the next
duplication problem** and it is between sentences within one stop, which is the gap between D518
(story vs prose) and D521 (inside one sentence).

### (c) The orientation for stop 1 describes stop 2's work, using a template artifact

> "**At this work:** Le Lézard aux plumes d'or…, witness Miró's surreal exploration of
> metamorphosis. **At this work:** Moses and Monotheism, Dalí's illustrations offer…"

Two problems in one line: the listener standing at stop 1 is told about stop 3's Moses, and
*"At this work:"* is a spoken template seam of exactly the kind you asked me to remove in item 3.
I did not fix it because you named `Narration` and `Closing`; this is the same family and I would
treat it the same way.

### (d) A wrong exhibition, stop 2

> "Dalí's illustrations became an integral part of the exhibition **'Dalí: Disruption and
> Devotion'** at the Museum of Fine Arts, Boston…"

That is a different MFA exhibition. The listener is standing in *Unbound*.

### (e) The missing space, fifth sighting in six runs

`…mythic creature.Published by Louis Broder…`. Untouched, as agreed — but it is now 5 of 6 and it
is not intermittent.

---

## 5. The numbers

| | D515 (D516, 3 runs) | 10:26 | 10:36 | **12:23 — this tour** |
|---|---|---|---|---|
| stop index mean | 67.8 | 75.7 | 63.7 | **69.7** |
| range | 64.3–72.3 | 69–82 | 44–77 | **68–72** |
| rubric base | 66.7 / 75.0 / 75.0 | 75.0 | 75.0 | **75.0** |
| loop cost | $0.045–0.060 | $0.046 | $0.044 | **$0.044** |
| bracketed citations | 3 | 4 | 3 | **0** |
| spoken `Closing:` | yes | yes | yes | **no** |

**The rubric base has been 75.0 for four consecutive runs and has stopped telling us anything.**
The stop index moves 12 points between runs of identical code, so neither number can currently
detect a change of the size these fixes make. What they measure is visible by reading: no
brackets, no label, no repeated clause — except the one in §2.

---

## 6. What I would do next, in order

1. **Sentence-to-sentence duplication inside one stop** (§4b) — the gap between the two fixes
   already built, and stop 1 is twice as long as it should be because of it.
2. **The priest/nobleman error stated unopposed** (§4a). The checker needs to know the true
   version, not just spot a self-contradiction.
3. **`At this work:` and the cross-stop orientation** (§4c) — same family as the label you asked
   me to remove.
4. **Three runs** under everything built today, before any number above is treated as real.
5. **Your two D515 amendments**, still unruled: require at least one confirmed-or-corrected claim,
   and treat `C0 X0` as a failed adjudication.
