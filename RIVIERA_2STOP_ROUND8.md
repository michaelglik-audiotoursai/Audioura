# French Riviera Cycling Tour - 2 Stops, Round 8 (LOCAL-251)

## Fact tally (hand-counted, per stop)

- **Cap d'Antibes:** 3/5 sentences carry a concrete fact (date, person+event, measurement, named work)
- **Villefranche-sur-Mer:** 2/8 sentences carry a concrete fact (date, person+event, measurement, named work)

> ### What changed: Namedrop is not delivery (LOCAL-251)
>
> Three fixes to the style validator:
> 1. A person's name alone no longer counts as concrete payload. It must be
>    paired with a date, event verb, or named work. "The legacy of artists
>    like Marc Chagall lingers in the air" now fires R10.
> 2. Mechanism 2 (poisoned neighbour) fixed as consequence — the name-drop
>    sentence no longer excuses its neighbour.
> 3. R9 extended to catch contentless metaphorical sentences ("bear the weight
>    of history", "a portal to a world where art and culture intertwine").
>
> Corpus-wide R9: 17 → 41 (2.4×, within 3× threshold).
> R10 also increased from 249 → ~321 due to fix 1 (name-drops no longer cancel).
>
> **Word counts:** Round 5: 680 | Round 6: 298 | Round 7: 658 | **Round 8: 479**
>
> The tour is **shorter** — that is the point. Sentences that said nothing
> are deleted. Expansion recovers what it can; deletion takes the rest.

## Summary Table

| Field | Value |
|---|---|
| fixes live | namedrop-not-delivery (LOCAL-251), expand-before-delete (LOCAL-250), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | $0.0057 |
| expansion cost | $0.0001 |
| total cost | $0.0058 |
| tokens (generation) | 7069 |
| stops | Cap d'Antibes, Villefranche-sur-Mer |
| expanded | 1 |
| deleted (R10) | 4 |
| deleted (R9) | 0 |
| passages spent | 1 |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 2/4 paragraphs |
| generation time | 39.7s |
| generation attempts | 1/3 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Tour Content

### Cap d'Antibes

#### Paragraph 1 (38 words)

Start at the main street near the Antibes train station. Head south towards the coast, follow the signs to Cap d'Antibes. Enjoy the view of the Mediterranean Sea along the way. Look for this work in the galleries.

#### Paragraph 2 (127 words)

You are about to embark on a journey through the elegant charm and rich history of the French Riviera, where each stop unveils a new chapter in the captivating tale of this sun-kissed paradise. As you arrive at the tip of Cap d'Antibes, the opulent Villa Eilenroc stands before you, a relic of the Belle Époque era that once inspired artists and writers with its lush gardens and grandeur. Moving deeper into the Riviera's past, hidden beneath the vibrant streets lies the Rue Obscure, a medieval passageway dating back to 1260, offering a glimpse into the enduring spirit of this modern town. Fitzgerald's Tender is the Night, published in 1934, offers a vivid portrayal of the Roaring Twenties, drawing inspiration from the vibrant life around Cap d'Antibes.

#### Paragraph 3 (8 words)

[Description for Cap d'Antibes could not be generated.]

### Villefranche-sur-Mer

#### Paragraph 1 (32 words)

Position yourself on the waterfront promenade of Villefranche-sur-Mer, with the azure Mediterranean Sea stretching out before you. Look out towards the deep natural harbor, known for its safe anchorage and historic significance.

#### Paragraph 2 (167 words)

As you stand on the promenade, take a moment to absorb the weight of history that envelops this picturesque town. Villefranche-sur-Mer, which translates to "Free City on Sea," has evolved into an essential port over the centuries, offering refuge to large ships in its depths of up to 95 meters. Explore the layers of time within Villefranche-sur-Mer by wandering through its winding streets and uncovering hidden gems. Delve into the history of Rue Obscure, a passageway dating back to 1260, where echoes of medieval life still resonate today. Step into the past as you traverse the cobblestone streets and breathe in the salty scent of the sea mingling with the aroma of freshly baked pastries from nearby cafes. The sound of seagulls overhead and the gentle lapping of waves against the shore provide a sensory backdrop to your exploration. With each step you take in Villefranche-sur-Mer, you are not merely a visitor but a time traveler, journeying through the centuries that have shaped this captivating coastal town.


---

## Expand/Delete Decision Table

| Sentence before | Corpus passage | Sentence after | Outcome |
|---|---|---|---|
| The stories woven within these luxurious villas and bustling... | For France lovers, Fitzgerald's Tender is the Night (1934) i... | Fitzgerald's Tender is the Night, published in 1934, offers ... | EXPANDED |
| This journey is a treasure trove of hidden tales waiting to ... | — | — | DELETED_NO_CORPUS |
| In Villefranche-sur-Mer, the bay's deep waters have witnesse... | — | — | DELETED_NO_CORPUS |
| Connect the threads of history as you gaze out at the expans... | — | — | DELETED_NO_CORPUS |
| Villefranche-sur-Mer stands as a testament to the intersecti... | — | — | DELETED_NO_CORPUS |

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

## Corpus-wide D55 compliance

| Metric | Before | After | Ratio | Threshold |
|---|---|---|---|---|
| R9 fires | 17 | 41 | 2.41× | 3.0× |
| R9 (filler path) | 17 | 16 | — | — |
| R9 (contentless, NEW) | 0 | 25 | — | — |
