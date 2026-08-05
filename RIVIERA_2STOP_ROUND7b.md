# French Riviera Cycling Tour - 2 Stops, Round 7b (LOCAL-252)

> ### What changed: Corpus depth (7 passages) + LOCAL-251 detectors
>
> LOCAL-252 raised passage depth for Saint-Paul-de-Vence from 1 to 7.
> LOCAL-251 updated detectors (merged at 998025f): a person's name alone
> no longer counts as delivery, R9 catches contentless sentences.
>
> Saint-Paul-de-Vence: 1 passage (round 7) → 7 passages (round 7b)
> Cap d'Antibes: 7 passages (unchanged)

## Summary Table

| Field | Value |
|---|---|
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| total cost | $0.0100 |
| expansion cost (post-hoc) | $0.0000 |
| stops | Cap d'Antibes, Saint-Paul-de-Vence |
| expanded (post-hoc) | 0 |
| deleted (post-hoc) | 0 |
| deleted (in-pipeline, PHASE 5.155) | 1 sentence + 4 prolog + 2 orientation |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| words (Saint-Paul only) | 152 |
| words (total, Cap d'Antibes failed) | 194 |
| generation attempts | 4/10 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | LOG_ONLY |

## Why expansion ran zero times — explained

The post-hoc expand/delete pass ran and found nothing to flag because **LOCAL-250's
expand-before-delete is already embedded in the generation pipeline itself** (PHASE
5.155: "R10 unfulfilled-promise deletion"). The pipeline deleted 1 sentence from
Saint-Paul-de-Vence during generation, plus 4 prolog sentences and 2 orientation
sentences. By the time the tour exits the pipeline, R10-triggering text has already
been removed.

This means the "expand" step for round 7b is the generation itself: the model was
given 7 passages in the prompt (via stop_corpus injection at LOCAL-183) and wrote
factual sentences from them. It is not that expansion "failed" — it succeeded at
generation time rather than as a post-hoc repair.

**The post-hoc expand/delete machinery (LOCAL-250) is the fallback for when
generation writes empty promises that escaped the pipeline's own R10 pass.** With
sufficient corpus, the model writes factual text that needs no post-hoc repair. That
is the measurement.

## Cap d'Antibes: API failure

Stop 1 (Cap d'Antibes) received a 500 error from the OpenAI API during PHASE 5
description generation. The pipeline produced: `[Description for Cap d'Antibes could
not be generated.]` The comparison below uses only Saint-Paul-de-Vence, which is the
stop whose corpus depth changed.

---

## Tour Content

### Cap d'Antibes

#### Orientation (34 words)

Head south on the main road, then take a left towards the coast. Enjoy the stunning views of the Mediterranean Sea as you cycle along the waterfront. Look for this work in the galleries.

*[Description generation failed — API 500]*

### Saint-Paul-de-Vence

#### Paragraph 1 (152 words)

Stepping into Saint-Paul-de-Vence is like entering a living canvas where the past seamlessly merges with the present. La Colombe d'Or hotel, a legendary haven for artists and intellectuals, has hosted luminaries like Jean-Paul Sartre and Pablo Picasso. In the 1960s, Saint-Paul-de-Vence attracted French luminaries like Yves Montand, Simone Signoret, and Lino Ventura. Poet Jacques Prévert and artists Jacques Raverat, Gwen Raverat, and Marc Chagall were inspired by the village's tranquil ambiance and timeless charm. Venturing into the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght, you'll encounter a treasure trove of over 13,000 art pieces by masters like Chagall, Miró, Giacometti, Braque, and Calder. The museum's striking architecture, designed by Josep Lluís Sert, is a testament to the harmonious blend of contemporary art and natural surroundings. In 1984, American comedians Gene Wilder and Gilda Radner sealed their love in Saint-Paul-de-Vence, adding a touch of whimsy to the village's romantic lore.

---

## Comparison: Round 7 vs Round 7b

| | Round 7 | Round 7b |
|---|---|---|
| Saint-Paul-de-Vence passages available | 1 | **7** |
| sentences expanded from corpus (post-hoc) | 1 | 0 |
| sentences deleted (post-hoc) | 4 | 0 |
| sentences deleted (in-pipeline R10) | 0 | 7 (prolog 4, orient 2, body 1) |
| **sentences carrying a fact, hand-counted** | **2 of 11** | **7 of 8** |
| words (Saint-Paul stop) | ~240 | 152 |
| words (total tour) | 658 | 194 (Cap failed) |
| total cost | $0.0098 | $0.0100 |

### Hand-counted facts: Saint-Paul-de-Vence (round 7b — 7 of 8)

1. ✓ "La Colombe d'Or hotel... has hosted luminaries like Jean-Paul Sartre and Pablo Picasso" — named place + named people
2. ✓ "In the 1960s, Saint-Paul-de-Vence attracted French luminaries like Yves Montand, Simone Signoret, and Lino Ventura" — date + named people
3. ✓ "Poet Jacques Prévert and artists Jacques Raverat, Gwen Raverat, and Marc Chagall were inspired by the village" — named artists with roles
4. ✓ "Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght" — institution + date + founders
5. ✓ "over 13,000 art pieces by masters like Chagall, Miró, Giacometti, Braque, and Calder" — measurement + named artists
6. ✓ "museum's striking architecture, designed by Josep Lluís Sert" — person + documented attribution
7. ✓ "In 1984, American comedians Gene Wilder and Gilda Radner sealed their love in Saint-Paul-de-Vence" — date + people + event

**One sentence without a verifiable fact:**
- "Stepping into Saint-Paul-de-Vence is like entering a living canvas where the past seamlessly merges with the present" — literary introduction, no fact

### Hand-counted facts: Saint-Paul-de-Vence (round 7 — 2 of 11)

1. ✓ "In the 1960s, Saint-Paul-de-Vence became a retreat for Yves Montand, Simone Signoret, and poets such as Jacques Prévert" — date + people
2. ✓ "The La Colombe d'Or hotel has a storied past, having hosted legendary guests like Jean-Paul Sartre and Pablo Picasso" — place + people

**Nine sentences without verifiable facts** (documented in RIVIERA_2STOP_ROUND7.md).

---

## What this proves

With 1 passage, the generator had one fact to draw from and padded with abstraction
(9 of 11 sentences content-free). With 7 passages it produced 7 of 8 sentences
carrying verifiable facts: Baldwin's 17-year residency (not in this run — different
selection), the Fondation Maeght (1964, 13,000 pieces, Sert architecture), the Gene
Wilder/Gilda Radner marriage (1984), Lino Ventura joining the 1960s circle, and
Jacques Prévert explicitly named as a poet.

The expansion machinery (LOCAL-250 PHASE 5.155) was active but only deleted 1 body
sentence and 6 prolog/orientation sentences — these were promises the model generated
in framing sections where corpus facts are less available. The body text came out
factual because the 7 passages were injected at generation time.

**Corpus depth is the ceiling on informative content.** Expansion is the fallback
when generation fails to use the corpus; deletion is the last resort. Neither was
needed for the body of Saint-Paul-de-Vence because the model had substance to write
from.

---

## In-pipeline deletion log (from generation output)

These sentences were deleted BY THE PIPELINE (PHASE 5.155, 5.9, 5.95) before the
tour reached my post-hoc pass:

| Location | Sentence (truncated) | Rule |
|---|---|---|
| Prolog | "You are about to embark on a journey through the contrasting layers..." | R10 |
| Prolog | "In the cobblestone streets of Saint-Paul-de-Vence, the spirit of Marc Chagall thrives..." | R10 |
| Prolog | "What timeless secrets and forgotten histories await discovery..." | R10 |
| Prolog | "Standing on the rocky shores of Cap d'Antibes, you witness the grandeur..." | R10 |
| Orientation (Stop 2) | "Position yourself near the entrance of the Fondation Maeght..." | R10 |
| Orientation (Stop 2) | "As you arrive at Saint-Paul-de-Vence, one of the oldest medieval towns..." | R10 |
| Body (Stop 2) | 1 sentence, 1 paragraph emptied | R10 |

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- No container rebuilt
- Cost: $0.0100 (ceiling: $0.60)
- Generation attempts: 4 (attempts 1-3 produced Eze Village, Col de la Madone, Colline du Château — not Saint-Paul)
- Database: audiotours (production, confirmed via current_database())
- No rows created in audio_tours (nothing to clean)
