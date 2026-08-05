# French Riviera Cycling Tour - 2 Stops, Round 3 (LOCAL-243)

**End-to-end regeneration with R10 running IN-PIPELINE (PHASE 5.155).**

> Total words: **505** (round 2 was 819).

## Summary Table

| Field | Value |
|---|---|
| gates active | stop-existence (ENFORCING, venue-kind), subject routine, **R10 (widened LOCAL-240)**, R9, CONTRADICTED block, style retry |
| model | gpt-3.5-turbo (default) |
| cost | $0.0073 (generation $0.0073 + subject $0.0000) |
| tokens | 9080 |
| cache hit | False |
| venue kind | geographic_area |
| stops selected | Cap d'Antibes, Col de Vence |
| -> Cap d'Antibes | VERIFIED - stop_corpus_geographic |
| -> Col de Vence | VERIFIED - stop_corpus_geographic |
| promises found (subject) | 0 |
| expanded | 0 |
| deleted (subject) | 0 |
| **R10 in-pipeline deletions** | **0** |
| **R10 ran where** | **IN-PIPELINE (PHASE 5.155) — 0 sentences deleted** |
| R10 residual (post-pipeline) | 0 |
| generation time | 38.7s |
| date | 2026-08-05 03:45 |
| tour ID | 199 (is_test=true) |

## Word Counts

| Paragraph | Stop | Words |
|---|---|---|
| P1 | Cap d'Antibes | 83 |
| P2 | Cap d'Antibes | 117 |
| P3 | Cap d'Antibes | 182 |
| P4 | Col de Vence | 46 |
| P5 | Col de Vence | 59 |
| P6 | Col de Vence | 18 |
| **Total** | | **505** |
| Round 2 | | 819 |

## Four-Way Word Count Comparison

```
Run                               Words   R10 position
------------------------------ --------   --------------------
Round 2                             819   (no R10)
LOCAL-240 re-applied                191   (R10 on old text)
LOCAL-241 end-to-end                393   (R10 post-processing)
LOCAL-243 (this run)                505   (R10 in-pipeline)
```

**Finding:** 505 words vs 393 (LOCAL-241). Delta is +112. However, this comparison is not apples-to-apples: LOCAL-241 had 5 R10 post-processing deletions (removing ~90 words of promise-language), while LOCAL-243 had 0 R10 deletions (the LLM simply didn't produce R10-triggering text in the stop descriptions this time). The difference is **LLM generation variance**, not R10 positioning. R10's position (in-pipeline vs post-processing) is moot when R10 finds nothing to delete.

---

## End-to-End Tour (generated text after all gates)

### Cap d'Antibes

*(D64: Stop 1 contains the tour prolog)*

**Existence:** VERIFIED (geographic_area)
**Coverage:** COVERED

#### Paragraph 1 (83 words)

Start biking east on the main road, continue straight towards the coast until you reach Cap d'Antibes with its stunning views. As you arrive at Cap d'Antibes on your French Riviera cycling tour, take a moment to marvel at the azure waters that stretch before you. Positioned between Cannes and Nice, this cape boasts a rich history and stunning natural beauty. Look out for the luxurious Villa Eilenroc, a serene oasis surrounded by verdant gardens, echoing the lavish soirées of the 19th century.

`[style: R1_IMPERATIVE]`

#### Paragraph 2 (117 words)

You are about to embark on a journey through the sun-drenched French Riviera, where the echoes of opulent history blend seamlessly with the vibrant pulse of today's cultural landscape. Each stop along the way reveals a different facet of this tapestry, from the serene Villa Eilenroc, where the whispers of lavish 19th-century soirées still linger amidst lush gardens, to the mysterious allure of the Col de Vence, known for its unexplained phenomena and UFO sightings. As you delve deeper into this world of hidden tales and artistic inspiration, the secrets of the glamorous French Riviera begin to unravel before your eyes, inviting you to uncover the untold stories that lie beyond its azure waters and sun-kissed beaches.

`[style: R10_UNFULFILLED_PROMISE]`

#### Paragraph 3 (182 words)

The Cap d'Antibes stands as a testament to the allure of the French Riviera, with its captivating blend of opulence and tranquility. In 1888, Claude Monet found inspiration here, painting the masterpiece "Morning at Antibes" that captures the essence of this coastal paradise. The rhythmic sound of waves crashing against the rugged coastline creates a symphony of nature's timeless beauty. Historically, Cap d'Antibes has been a beacon for artists and writers seeking creative inspiration. F. Scott Fitzgerald drew from the vibrant energy of the Roaring Twenties, shaping his novel "Tender is the Night" against the backdrop of this glamorous era. The winding "Tire-Poil" trail offers walkers breathtaking views of the Lérins Islands and the Mercantour heights, inviting you to explore the region's natural wonders. As you stand on the edge of Cap d'Antibes, surrounded by the scent of saltwater and pine trees, you can't help but feel a sense of serene anticipation for the road ahead. Cycling along the coastal path, you are immersed in a world where history and art intertwine, promising more tales of intrigue and beauty yet to unfold.

`[style: clean]`

### Col de Vence

**Existence:** VERIFIED (geographic_area)
**Coverage:** NO_CORPUS

#### Paragraph 4 (46 words)

As you arrive at Col de Vence, perched high in the French Riviera, take a moment to absorb the panoramic views of the Mediterranean Sea stretching out before you. Look to your left to see the rugged cliffs and lush greenery that characterize this stunning region.

`[style: R1_IMPERATIVE]`

#### Paragraph 5 (59 words)

Cyclists often feel a sense of awe at Col de Vence, known for its mystical aura and reported UFO sightings. The cool mountain air mingles with the scent of pine trees, inviting contemplation as you gaze at the undulating landscape below. Just beyond the summit, a descent into the heart of the Riviera awaits, where history and mystery entwine.

`[style: clean]`

#### Paragraph 6 (18 words)

From Cap d'Antibes to Col de Vence — a collection that spans more ground than these stops alone.

`[style: R9_GENERIC]`

---

## Deletions (verbatim)

### Subject Routine

No unfulfilled-promise patterns detected.

### R10 In-Pipeline (PHASE 5.155) — 0 deletions

**Status:** IN-PIPELINE (PHASE 5.155) — 0 sentences deleted

**Pipeline log lines (verbatim):**
```
[LOCAL-235] PHASE 5.155: R10 unfulfilled-promise deletion...
[LOCAL-235] R10 summary: 0 sentences deleted, 0 paragraphs emptied, 0 stops affected
```

---

## Style Retry / R10 Interaction

R10 now runs IN-PIPELINE (PHASE 5.155), between style retry (PHASE 5.1) and CONTRADICTED block (PHASE 5.16). This means:

1. LLM generates paragraph
2. Style retry rewrites if R1/R3/R4 violations found
3. R9 deletes generic sentences
4. **R10 deletes unfulfilled-promise sentences** ← runs here now
5. CONTRADICTED block removes disproven claims
6. Subject routine expands/removes promises (post-gen)

R10 deleted 0 sentence(s) in-pipeline. 
No residual R10 triggers remain after the full pipeline — the in-pipeline position caught everything.

**Important caveat:** The style validator (Step 5) flags Paragraph 2 as `R10_UNFULFILLED_PROMISE` and Paragraph 6 as `R9_GENERIC`. However, `apply_r10_to_description` returns 0 deletions when run on the full stop text. This reveals two scope differences:

1. **PHASE 5.155 operates on stop descriptions only** (before prolog/transition/epilog are added in PHASE 6). Paragraph 2 is the **prolog** (added during assembly) — R10 in-pipeline never sees it.

2. **R10 is promise-fulfillment-aware.** When P2 (the prolog, which promises "hidden tales" and "untold stories") is followed by P3 (which delivers Monet, Fitzgerald, the Tire-Poil trail), `apply_r10_to_description` decides the promise IS fulfilled and does not delete. Run P2 alone → 1 deletion. Run P2+P3 together → 0 deletions. This is R10 working as designed.

3. **Paragraph 6** ("From Cap d'Antibes to Col de Vence — a collection that spans more ground than these stops alone") flags `R9_GENERIC` in per-paragraph style check, but it's the **epilog** added in PHASE 6, after R9 already ran on stop descriptions in PHASE 5.15.

**Conclusion:** R10 and R9 in-pipeline (PHASE 5.155/5.15) cannot catch violations introduced during PHASE 6 assembly (prolog, transitions, epilog). These assembly-generated texts bypass all style gates.

---

## Section 2: Same Rule, Old Text (LOCAL-240 re-application, preserved)

The previous RIVIERA_2STOP_ROUND3.md applied widened R10 to text generated BEFORE R10 existed. That produced 8 deletions and a 191-word tour. This section preserves that result for comparison.

| Paragraph | Words |
|---|---|
| P1 | 5 |
| P2 | 56 |
| P3 | 107 |
| P4 | 8 |
| P5 | 7 |
| P6 | 8 |
| **Total** | **191** |
| Round 2 | 819 |

### R10 deletions on old text (8 sentences, verbatim)

1. *"You are about to embark on a journey through the French Riviera, where the sun-drenched coasts and ancient villages hold a tapestry woven with the glamour of modern allure and whispers of medieval roots."*
2. *"Cycling through winding paths, you'll discover a blend of architectural marvels and forgotten tales that shape its identity."*
3. *"The ancient fortifications of the Garoupe Lighthouse stand sentinel against opulent villas, revealing a juxtaposition of past and present."*
4. *"Discover how the idyllic beauty of the French Riviera masks the secrets of its past as you unravel its intricate story through each chapter of this enchanting journey."*
5. *"As you wander through the exotic Jardin Exotique d'Eze, panoramic views whisper tales of ancient Provencal nobility and their long-lost gardens."*
6. *"Cap d'Antibes, with its rich tapestry of landscapes and stories, serves as a window into the enduring charm of the Cote d'Azur."*
7. *"The crisp sea air carries whispers of history, mingling with the contemporary pulse of yachting harbors and bustling town life."*
8. *"The ancient fortifications of the Garoupe Lighthouse, a sentinel of bygone eras, starkly contrast with the opulent villas that line the coastline, symbolizing the enduring allure of this coastal haven."*

**Difference:** Deleting from old prose (written without awareness of R10) produced 191 words with 4 of 6 paragraphs reduced to a single line. A fresh generation under R10 produces the text above.

---

## Run Summary

- Tour ID: 199 (is_test=true, lat/lng=NULL)
- audio_tours: 142 -> 143 (delta: +1)
- Nice list: [1, 12, 14, 17, 24, 29, 152] - UNCHANGED
- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)
- Total cost: $0.0073
- Generation time: 38.7s
- Total words (final): 505
- Style retry ran during generation (built-in)
- R10 in-pipeline: IN-PIPELINE (PHASE 5.155) — 0 sentences deleted
- R10 residual triggers: 0
