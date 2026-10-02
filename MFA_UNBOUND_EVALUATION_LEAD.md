# LEAD's evaluation — "Picasso, Miro, Dali: Unbound" at the MFA, 3 stops

**Tour file:** `tours/MFA_UNBOUND_FOR_REVIEW.txt`
**Generated:** 2026-08-12 18:1x, in the container, `code_sha ce61b01`, cache disabled
**Result:** SUCCESS, 6,207 chars, 165.2s
**Rubric score:** **75.0** base at N=3

Write your own verdict next to mine — the point is to find where we disagree.

---

## Headline

**The facts are real and the prose is not.** Every named person in this tour exists and
belongs here: Louis Broder, Boris Fridman, Joan Miró, Freud, Dalí, Juan Gris, Pierre
Reverdy, Tériade. Nothing is invented. But three of the eight paragraphs contain
sentences I would not let out of the building, and one of them is a factual error that
has now survived three consecutive generations of this tour.

My honest read: **not shippable as-is, and close.** The defects are surface-level and
specific, not structural.

---

## What is genuinely good

**It refused to fabricate, and I watched it do so.** The first attempt at this tour
*failed completely* — the model proposed *The Weeping Woman*, *The Farm* and *The
Persistence of Memory*. Those are at the Tate, the National Gallery, and MoMA
respectively; none is at the MFA. The D1v2 gate dropped all three and returned
`unresolvable — clean fail` rather than writing a plausible tour about art that is not
there. **That is the single most important thing in this evaluation.** A year ago this
system would have written that tour.

**The exhibition checklist is doing real work.** Stop 1's publisher (`Louis Broder`),
credit line (`Gift of Boris Fridman`) and medium (`Illustrated book with 40 color
lithographs`) came out of the MFA's own page, reached through Wayback after Cloudflare
blocked the direct fetch. Those are not facts a language model would produce from memory.

**No invented sensory language.** No sea breezes, no warmth on your skin, no sounds of
footsteps. That class of defect — which cost us five rounds earlier this summer — is
absent.

**Orientation is physically actionable on stops 1 and 2.** "Position yourself to see the
entire spread", "Stand close to the display case". A listener can act on those.

---

## Defects, in the order I would fix them

### 1. `"Tériade's role as the Louis Broder"` — stop 3 (blocking)

Garbled to the point of meaninglessness, and it is the **second** time this exact
corruption has appeared. This afternoon's run produced *"handpicked by Tériade, the Louis
Broder, into a singular artistic object."* Two different generations, same broken
appositive, same two publishers fused.

It is also **self-contradictory**: the same paragraph opens with *"Louis Broder... commissioned
this work from Gris"* and closes by describing Tériade as "the Louis Broder."

And it is **factually wrong**: *Au Soleil du Plafond* (1955) was published by **Tériade**,
not Broder. Broder published stop 1's *Le Lézard aux plumes d'or*. The tour has swapped
the publisher of one work onto another and then mangled the sentence describing it.

A recurring corruption in the same slot across runs is a template defect, not a sampling
accident.

### 2. The Hogarth Press attribution — stop 2 (factual, third occurrence)

> "The Hogarth Press, known for its publication of Freud's groundbreaking works, produced
> this edition"

Hogarth published Freud's *text* in English in 1939. The **1974 Dalí-illustrated edition**
is a different object with a different publisher. The tour conflates the two, and it has
done so in every generation of this tour today. The sentence is sourced — it traces back
to the MFA page — which makes this a *reading* error, not a hallucination, and probably
fixable at the extraction step rather than in the prose.

### 3. Stop 3 never says where to stand

Stops 1 and 2 open with a physical instruction. Stop 3 opens with a definition of *livre
d'artiste*. In an audio guide, standing in a gallery, that is the difference between a
tour and an essay.

### 4. Stop 3 introduces Gris without introducing him

The orientation never names him. The body's first sentence is *"commissioned this work
from Gris"* — a bare surname for a listener who has not been told who that is. Stop 1
handles Miró correctly (*"a spanish painter and sculptor born in 1893"*), which shows the
mechanism exists and simply did not fire here.

### 5. Imbalance

Stop 1's body is three sentences and says almost nothing about the artwork — it covers
who commissioned it and who donated it, but never describes the 40 colour lithographs or
what Miró actually did. Stop 3 runs roughly four times longer. For a 3-stop tour the
listener feels this directly.

### 6. The thesis is repeated to death

*"revolutionized the book as an art form"* and its near-variants appear in the
orientation and in stops 2 and 3 — four times in 6,200 characters. It reads as a template
being satisfied rather than an argument being made.

### 7. `"a spanish painter"` — lowercase proper adjective (stop 1)

Trivial, but it is in the first body sentence of the tour, and it survived the style
validator.

---

## What I would dispatch next

| # | Fix | Why first |
|---|---|---|
| 1 | The publisher-appositive corruption | Reproducible across runs, produces meaningless text, and swaps a real attribution |
| 2 | Hogarth / 1974-edition conflation | A factual error that is stable across runs, so it is fixable |
| 3 | Orientation required on every stop | Cheap, and it is the difference between an audio guide and an essay |
| 4 | First-mention rule for people | Mechanism already exists on stop 1; it just needs to be mandatory |
| 5 | Per-stop length balance | Structural, affects the listen |

Defects 1 and 2 are the only ones I would call blocking.

---

## Where I might be wrong, and what I want you to check

- **Is 75.0 the right number for this?** My instinct says the rubric is generous here —
  a tour with a meaningless sentence and a wrong publisher should probably not score the
  same as the 8-stop Asian Arts tour did before today. If you read it as worse than 75,
  the rubric needs attention and that is a more valuable finding than the prose fixes.
- **Is the Hogarth error actually an error?** I am confident Hogarth published the 1939
  English text and did not publish the 1974 Dalí edition, but I have not verified the
  1974 publisher against the MFA's own checklist. If the MFA page itself says Hogarth,
  the defect is theirs and we are faithfully reporting it — which changes the fix.
- **Does stop 1's thinness bother you as much as it bothers me?** It is factually clean;
  it just does not describe the art. That may read as restraint rather than as a gap.

---

## Reproducing this

```bash
docker exec -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 audioura-tour-generator-1 \
  python -c "
import sys; sys.path.insert(0,'/app')
from generate_tour_text import generate_tour_text
generate_tour_text('Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA',
                   'museum','/app/tours/MFA_UNBOUND_FOR_REVIEW.txt',3)"
```

**Note the non-determinism.** Two runs of this exact command 10 minutes apart produced a
clean fail and a 75.0 tour. Candidate selection sometimes free-associates famous works
instead of using the exhibition checklist that was successfully retrieved. That is worth
a task in its own right — the checklist had 8,215 characters of real content sitting
there when the failing run proposed three works from other museums.
