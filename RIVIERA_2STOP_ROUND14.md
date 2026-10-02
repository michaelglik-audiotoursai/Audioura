# French Riviera Cycling Tour - 2 Stops, Round 14 (ROUND14)

> ### What changed: LOCAL-257 — Fragment checker quoted-span fix, determiner restoration
>
> `_has_finite_main_verb` now masks quoted spans ("Tender is the Night") before verb search.
> `_restore_determiner` adds "The" when R1 rewrite strips the article with the imperative.
> Chagall misplacement at Cap d'Antibes traced: LLM fabrication, no corpus support.

**Word count:** 555
**Stops:** 2 (Cap d'Antibes, Eze Village)

## Flags Set

| Flag | Value |
|---|---|
| STOP_EXISTENCE_GATE_MODE | enforce |
| STORIED_MODE | true |
| DISABLE_STYLE_RETRY | NOT SET (ON) |
| DISABLE_R1_REWRITE | NOT SET (ON) |
| DISABLE_R7_DELETION | NOT SET (ON) |
| DISABLE_R9_DELETION | NOT SET (ON) |
| DISABLE_R10_DELETION | NOT SET (ON) |
| DISABLE_CONTRADICTED_BLOCK | NOT SET (ON) |
| DISABLE_SUBJECT_ROUTINE | 1 (OFF) |
| DISABLE_TOUR_CACHE | 1 (OFF) |

## Summary Table

| Field | Value |
|---|---|
| generation cost | $0.0098 |
| total tokens | 12187 |
| stops | Cap d'Antibes, Eze Village |
| R1 rewritten | 2 |
| R1 deleted | 0 |
| R1 residual (post-pipeline) | 3 |
| R7 residual | 0 |
| Description: labels | 0 |
| Fragment sentences (narration) | 1 |
| Missing determiners | 0 |
| generation time | 41.8s |
| generation attempts | 1/3 |
| word count | 555 |
| date | 2026-08-05 |

## Fragment Sentences (narration, fixed checker)

- Happy cycling!

## Missing Determiners

*(none detected)*

## Fact Tally Per Stop

- **Cap d'Antibes**: 2 facts
  - Stop 1: Cap d'Antibes

Address: Cap d'Antibes, 06160 Antibes, France

Coordinates: 43.5411, 7.1213

Type/Specialty: Coastal Scenic Point

Specific Exa
  - In 2023, Antibes boasted a population of 77,637, establishing itself as the second-most populous area in Alpes-Maritimes after Nice.
- **Eze Village**: 7 facts
  - Stop 2: Eze Village

Address: 06360 Èze, France

Coordinates: 43.7284, 7.3613

Type/Specialty: Medieval Hilltop Village

Specific Examples: Narrow cob
  - The village of Èze, first settled around 200 BC near Mount Bastide, holds within its stone walls a tapestry of stories woven through time.
  - By 1388, Èze came under the rule of the House of Savoy, who fortified the town strategically due to its proximity to Nice.
  - The village endured the tumult of warfare, with French and Ottoman troops seizing it in 1543, and the walls being razed by Louis XIV in 1706 during th
  - In a pivotal moment of modern history, the people of Èze voted unanimously for the village to become a part of France in April 1860.
  - Perched 427 meters above sea level, Èze offers a breathtaking view that captivated even Walt Disney when he visited in 1956.
  - At the heart of Èze Village stands the Chapelle de la Sainte Croix, a solemn sanctuary dating back to 1306.

## Tour Content

Step-by-Step Audio Guided Tour: French Riviera cycling tour, France - Cycling Tour
Tour-Category: walking

Stop 1: Cap d'Antibes

Address: Cap d'Antibes, 06160 Antibes, France

Coordinates: 43.5411, 7.1213

Type/Specialty: Coastal Scenic Point

Specific Examples: Stunning views of the Mediterranean Sea, luxury villas, sandy beaches

Orientation: Start biking south on the main road, enjoy the sea breeze along the coastal route. As you approach the stunning Cap d'Antibes on your French Riviera cycling tour, the salty sea breeze carries the faint scent of pine trees, hinting at the lush landscape that awaits you. The Yourself on the eastern side of the cape, where secluded beaches and pine groves once sheltered the private lives of European nobility, creating a hidden paradise away from prying eyes can be found here.

At Cap d'Antibes, the historical significance of this exquisite location unfolds before you. In 2023, Antibes boasted a population of 77,637, establishing itself as the second-most populous area in Alpes-Maritimes after Nice. The cape, along with Cap Ferrat in Saint-Jean-Cap-Ferrat, forms a picturesque duo of prominent landforms in the region. Upon the rugged terrain of Cap d'Antibes, the crunch of gravel under your bike tires resonates with the azure Mediterranean Sea in the background. The secluded beaches and lush pine groves are reminders of the area's rich history, where European nobility once sought refuge in this idyllic corner of the French Riviera. The winding paths and hidden coves of the cape were once a secluded paradise for the elite, shielded from the public eye.

Directions: Hey there cyclist! Start your ride from Cap d'Antibes and pedal east along the scenic coastal road. Enjoy the stunning views of the Mediterranean Sea as you make your way towards Eze Village. Keep riding until you reach the charming village perched on the hilltop overlooking the sea. Happy cycling!

Stop 2: Eze Village

Address: 06360 Èze, France

Coordinates: 43.7284, 7.3613

Type/Specialty: Medieval Hilltop Village

Specific Examples: Narrow cobblestone streets, panoramic views, exotic gardens

Orientation: Cliff is gazing out towards the shimmering Mediterranean Sea below.

The village of Èze, first settled around 200 BC near Mount Bastide, holds within its stone walls a tapestry of stories woven through time. The Antonine Itinerary, a historical document, mentions the bay of Èze as Avisionis portus, linking the village to maritime trade routes of antiquity. By 1388, Èze came under the rule of the House of Savoy, who fortified the town strategically due to its proximity to Nice. The village endured the tumult of warfare, with French and Ottoman troops seizing it in 1543, and the walls being razed by Louis XIV in 1706 during the War of the Spanish Succession. In a pivotal moment of modern history, the people of Èze voted unanimously for the village to become a part of France in April 1860. Perched 427 meters above sea level, Èze offers a breathtaking view that captivated even Walt Disney when he visited in 1956. It was his visit that sparked the transformation of the Château de la Chèvre d'Or into a renowned hotel by Robert Wolf. At the heart of Èze Village stands the Chapelle de la Sainte Croix, a solemn sanctuary dating back to 1306. This chapel served as a meeting place for the White Penitents of Èze, who provided aid to plague victims, embodying the village's enduring spirit of compassion and resilience.



---

## Comparison to Round 13

| Metric | Round 13 | Round 14 |
|---|---|---|
| Word count | 542 | 555 |
| R1 residual | 3 | 3 |
| R7 residual | 0 | 0 |
| Description: labels | 0 | 0 |
| Fragment sentences | 0 (17 w/ metadata, 1 true) | 1 |
| Missing determiners | 1 (undetected) | 0 |
| Cost | $0.0097 | $0.0098 |

## Round 13 True Fragment Count (fixed checker)

With the LOCAL-257 fix (quoted-span masking), the round 13 checker finds:
- **1 narration fragment**: `Scott Fitzgerald's "Tender is the Night," a vivid portrayal...`
- 4 metadata lines (headers/addresses) — not narration
- The old checker reported 0 narration fragments (fooled by 'is' inside the title)

## Chagall Misplacement (Stop 1, Cap d'Antibes)

**Source investigation:**
- Cap d'Antibes corpus (stop_corpus ids 227, 236): **0 mentions of Chagall**
- Saint-Paul-de-Vence corpus (id 230): mentions Chagall in Fondation Maeght passage
- "clandestine atelier" appears in **0 corpus passages** — entirely fabricated
- Chagall is correctly placed at Saint-Paul-de-Vence (stop 2) in the same tour

**Conclusion:** LLM cross-stop contamination. The prompt included both stops' corpus,
and the model placed a Saint-Paul-de-Vence fact at Cap d'Antibes with fabricated detail.
The existence gate verifies stop-level passage presence, not per-sentence fact provenance.
Fixing this class of error requires per-fact attribution checking (not cheap).
