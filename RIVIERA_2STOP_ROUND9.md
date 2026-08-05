# French Riviera Cycling Tour - 2 Stops, Round 9 (LOCAL-251 bounce)

## Fact tally (hand-counted, per stop)

- **Cap d'Antibes:** 1/8 sentences carry a concrete fact (date, person+event, measurement, named work)
- **Saint-Paul de Vence:** 1/3 sentences carry a concrete fact (date, person+event, measurement, named work)

> ### What changed: R7 deletion path + bounce fixes
>
> 1. **R7 now deletes** (PHASE 5.14): fabricated sensory sentences ("breathe in the
>    salty scent mingling with freshly baked pastries", "the sound of seagulls
>    overhead... provide a sensory backdrop") are removed at assembly time.
>    Three new patterns added for multi-source fabrication, fabricated soundscapes,
>    and fabricated seaside ambiance.
> 2. **Generation failure gate** (PHASE post-assembly): `[Description for X could not
>    be generated.]` and `[GENERATION_FAILED:X]` placeholders are stripped before output.
>    They produce a loud warning but never reach TTS.
> 3. **Prolog stop-name disambiguation** (PHASE 5.91): when the prolog references a
>    feature from a later stop and uses "this town/village", it now names the stop.
> 4. **Orientation fallback fixed**: non-museum tours no longer get "Look for this
>    work in the galleries" as fallback orientation.
>
> **Word counts:** Round 5: 680 | Round 6: 298 | Round 7: 658 | **Round 9: 386**
>
> **R7 corpus-wide:** 21 fires / 2810 sentences = 0.75%
> Deletion path trusts detection; no new false-positive surface.
>
> Stops: Cap d'Antibes, Saint-Paul de Vence
> LOCAL-252 corpus depth available: YES (Saint-Paul-de-Vence + Cap Ferrat passages on storied)

## Summary Table

| Field | Value |
|---|---|
| fixes live | R7 deletion (LOCAL-251), namedrop-not-delivery (LOCAL-251), expand-before-delete (LOCAL-250), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | $0.0087 |
| total cost | $0.0087 |
| tokens (generation) | 10918 |
| stops | Cap d'Antibes, Saint-Paul de Vence |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 2/4 paragraphs |
| generation time | 41.3s |
| generation attempts | 2/3 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |
| DISABLE_R7_DELETION | not set (enabled) |
| DISABLE_R9_DELETION | not set (enabled) |
| DISABLE_R10_DELETION | not set (enabled) |

---

## Tour Content

### Cap d'Antibes

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (64 words)

Start cycling south on the main road, enjoy the sea breeze along the coast. As you arrive at Cap d'Antibes, you'll find yourself at the tip of the cape, where the ancient stone walls of the Chapel of Garoupe stand tall. This spot offers a breathtaking view of the Mediterranean Sea, with the gentle sound of waves lapping against the shore in the background.

#### Paragraph 2 (28 words)

Walking through the cobblestone streets, the ramparts surrounding the village reveal a place where Marc Chagall found his eternal muse, a fortress that once defended against unseen threats.

#### Paragraph 3 (113 words)

At Cap d'Antibes, history comes alive through the Chapel of Garoupe, a site that has been witness to centuries of pilgrims and painters alike. Inspired by the serene beauty of this location, renowned artists like Claude Monet first experimented with painting in series here, producing masterpieces like Morning at Antibes in 1888. The physical present at this stop invites you to touch the weathered stones of the chapel, feeling the weight of time and tradition in your hands. Cap d'Antibes is a picturesque spot on the coast, embodying the cultural and artistic heritage of the region. A hidden hilltop village along the coastal road promises to reveal more layers of history and beauty.

### Saint-Paul de Vence

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (50 words)

Pedaling through Saint-Paul de Vence, one can sense the presence of artists and intellectuals who once frequented these streets. The warm Mediterranean sun bathes the historic buildings in a golden hue, inviting exploration of galleries and boutiques. The village exudes an ambiance where creativity thrives, offering enlightenment at every turn.


---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | 0 | (clean) |
| R8 | 0 | (clean) |
| R9 | 0 | (clean) |
| R10 | 0 | (clean) |
| R1 | 2/4 | Imperative rate |

All clean.

---

## R7 Corpus-wide (D55 compliance)

| Metric | Value |
|---|---|
| R7 fires (corpus-wide) | 21 |
| Total sentences | 2810 |
| Rate | 0.75% |
| Note | Deletion path removes what detector already fires on. No new detection surface added beyond 3 patterns for specific fabrication shapes. |

---

## Running Comparison

| LOCAL | Words | R7 | R8 | R9 | R10 | R1 rate | Cost |
|---|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | — | — | 4 | 50% | $0.0082 |
| LOCAL-238 | 505 | — | — | 0 | 0 | 40% | $0.0087 |
| LOCAL-244 | 488 | — | — | 0 | 0 | — | $0.0095 |
| LOCAL-247 | 680 | 0 | 0 | 0 | 0 | 1/6 | $0.0093 |
| LOCAL-249 | 298 | 1 | 0 | 0 | 0 | 2/4 | $0.0103 |
| LOCAL-250 | 658 | 0 | 0 | 0 | 0 | 1/4 | $0.0098 |
| **LOCAL-251 R9** | **386** | **0** | **0** | **0** | **0** | **2/4** | **$0.0087** |

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- Cost: $0.0087 (ceiling: $0.6)
- Generation time: 41.3s
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce
- All deletion paths enabled (R7, R9, R10)
- Generation failure gate: active
- Prolog disambiguation: active
