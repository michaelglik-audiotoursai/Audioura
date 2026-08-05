# French Riviera Cycling Tour - 2 Stops, Round 3 (LOCAL-244)

**End-to-end regeneration with prolog gating active (PHASE 5.9).**

> Total words: **488** (round 2 was 819).

> ## ⚠️ Read this first — LEAD's note, 2026-08-05 04:40
>
> **Stop 2, Corniche d'Or, is UNVERIFIED and was narrated anyway.** The
> stop-existence gate is listed as active in the table below, but it ran in
> LOG_ONLY mode — it recorded the verdict and did not drop the stop. So two of
> the six paragraphs describe a place we have no source for. Treat them the way
> you treated the Chikanobu print.
>
> Everything else held: **zero residual R10** in the delivered text, and the
> tour prolog passed through the gates for the first time (it has never been
> checked by anything before today — it is generated separately and injected
> after every gate finishes).
>
> **R1 still fires on four of six paragraphs.** That is your original
> complaint, unresolved.
>
> Word counts across the night: round 2 **819** → R10 on old text **191** →
> end-to-end **393** → R10 in-pipeline **505** → this, with the prolog gated,
> **488**. The variance is generation noise; what holds is that 40–75% of what
> the model writes unprompted is promise language with nothing behind it.


## Summary Table

| Field | Value |
|---|---|
| gates active | stop-existence, subject routine, **R10**, R9, CONTRADICTED, style retry, **PHASE 5.9 prolog gating** |
| model | gpt-3.5-turbo (default) |
| cost | $0.0092 (generation $0.0092 + subject $0.0000) |
| tokens | 11556 |
| cache hit | False |
| stops selected | Cap d'Antibes, Corniche d'Or |
| -> Cap d'Antibes | VERIFIED - COVERED |
| -> Corniche d'Or | UNVERIFIED - NO_CORPUS |
| promises found (subject, stops) | 0 |
| expanded (stops) | 0 |
| deleted (subject, stops) | 0 |
| **prolog words before gates** | **115** |
| **prolog words after gates** | **115** |
| **prolog R9 deletions** | **0** |
| **prolog R10 deletions** | **0** |
| **prolog subject expanded** | **0** |
| **prolog subject deleted** | **0** |
| **prolog collapsed** | **False** |
| R10 in-pipeline (stops) deletions | 4 |
| R10 residual in delivered text | 0 |
| generation time | 44.1s |
| date | 2026-08-05 04:16 |
| tour ID | 202 (is_test=true) |

## Word Counts

| Paragraph | Stop | Words | Style |
|---|---|---|---|
| P1 | Cap d'Antibes | 51 | R1_IMPERATIVE |
| P2 | Cap d'Antibes | 115 | R1_IMPERATIVE,R7_HALLUCINATED_SENSORY |
| P3 | Cap d'Antibes | 145 | clean |
| P1 | Corniche d'Or | 52 | R1_IMPERATIVE |
| P2 | Corniche d'Or | 108 | R1_IMPERATIVE |
| P3 | Corniche d'Or | 17 | R9_GENERIC |
| **Total** | | **488** | |
| Round 2 | | 819 | |

## Five-Way Word Count Comparison

```
Run                               Words   R10 position
------------------------------ --------   --------------------
Round 2                             819   (no R10)
LOCAL-240 re-applied                191   (R10 on old text)
LOCAL-241 end-to-end                393   (R10 post-processing)
LOCAL-243 (R10 in-pipeline)         505   (R10 in-pipeline)
LOCAL-244 (this run)                488   (R10 in-pipeline + prolog gated)
```

## Prolog Gating (LOCAL-244 — PHASE 5.9)

**Prolog word count before gates:** 115
**Prolog word count after gates:** 115
**Delta:** 0 words

### Prolog Deletions

None — prolog survived all gates intact.

---

## End-to-End Tour (generated text after all gates)

### Cap d'Antibes

**Existence:** VERIFIED (geographic_area)
**Coverage:** COVERED

#### Paragraph 1 (51 words)

Start cycling southeast on the main road, enjoy the view of the marina and yachts along the coast. Stand at the edge of Cap d'Antibes, overlooking the crystal-clear waters of the Mediterranean Sea. Look for the ancient stones of Villa Eilenroc, a symbol of 19th-century opulence that once hosted extravagant parties.

`[style: R1_IMPERATIVE]`

#### Paragraph 2 (115 words)

You are about to embark on a journey through the French Riviera, a tapestry woven with the whispers of bygone eras and the echoes of opulent tales. The azure waters and golden sands hold hidden stories beneath their sun-drenched glamour. Each stop on this tour reveals a different facet of this enchanting region: from the ancient stones of Villa Eilenroc, a symbol of 19th-century opulence that once hosted glittering parties, to the raw beauty of the Esterel Massif, where red cliffs plunge dramatically into the Mediterranean, unchanged since ancient traders navigated these waters. Join us as we uncover the secrets of this captivating destination, where every chapter holds a new revelation waiting to be discovered.

`[style: R1_IMPERATIVE,R7_HALLUCINATED_SENSORY]`

#### Paragraph 3 (145 words)

As you reach Cap d'Antibes, you are stepping into a place of historical significance. In 2023, Antibes boasted a population of 77,637, making it the second most populated in Alpes-Maritimes after Nice. The cape of Cap d'Antibes, alongside Cap Ferrat, is a prominent feature in the region's landscape. The gentle breeze off the sea carries the scent of salt and pine. Waves crashing against the rocks mingle with the calls of seagulls overhead. At Cap d'Antibes, history and natural beauty converge as the Tire-Poil trail winds for 2.7 kilometers, offering breathtaking views of the Lérins Islands and the Mercantour heights. This spot connects to our French Riviera cycling tour theme by showcasing the rich cultural heritage and stunning landscapes that have inspired artists like Claude Monet. Cycle towards the Corniche d'Or to uncover the secrets held by the majestic cliffs about the Riviera's storied past.

`[style: clean]`

### Corniche d'Or

**Existence:** UNVERIFIED (geographic_area)
**Coverage:** NO_CORPUS

#### Paragraph 1 (52 words)

As you cycle along the French Riviera, the Corniche d'Or offers a breathtaking vista of the Esterel Massif plunging into the azure Mediterranean Sea. Look to your left to witness the raw beauty of the red cliffs contrasting with the deep blue waters, creating a scene that has remained unchanged for centuries.

`[style: R1_IMPERATIVE]`

#### Paragraph 2 (108 words)

The Corniche d'Or is a scenic coastal road that winds its way along the rugged Esterel Massif, offering cyclists a mesmerizing view of nature's grandeur. The sheer cliffs of the Massif tower above, their reddish hues illuminated by the warm Mediterranean sun. The salty breeze carries the scent of pine trees and sea, immersing you in the timeless majesty of this ancient landscape. The contrast of the fiery cliffs against the cool waters serves as a reminder of nature's enduring power and the passage of time. As you continue your journey, let the rugged beauty of the Esterel Massif evoke a sense of wonder and awe within you.

`[style: R1_IMPERATIVE]`

#### Paragraph 3 (17 words)

From Cap d'Antibes to Corniche d'Or — a collection that spans more ground than these stops alone.

`[style: R9_GENERIC]`

---

## R10 Residual Check (on delivered text)

**R10 residual sentences in delivered text: 0**

Delivered text is clean — 0 R10 triggers remain.

---

## Run Summary

- Tour ID: 202 (is_test=true, lat/lng=NULL)
- audio_tours: 143 -> 144 (delta: +1)
- Nice list: [1, 12, 14, 17, 24, 29, 152] - UNCHANGED
- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)
- Total cost: $0.0092
- Generation time: 44.1s
- Total words (final): 488
- Prolog gating (PHASE 5.9): R9=0 del, R10=0 del, subject=0 exp/0 del
- R10 in-pipeline (stops): 4 deletions
- R10 residual: 0
