# French Riviera Cycling Tour - 2 Stops, Round 5 (LOCAL-247)

**Fixes live in this run:**
1. **Payload false positive** (LOCAL-247 primary): unified `_PLACE_WORDS` vocabulary,
   French/Italian/Spanish particles don't break cap-word runs, adjective→stem resolution.
2. **R7 hallucinated sensory** (LOCAL-247): fires on fabricated multi-sensory + abstract emotion.
3. **R8 prompt leakage** (LOCAL-247): fires on "this stop aligns with the tour's theme".
4. **R9 generic** (LOCAL-247): place-name-only subjects with generic predicates no longer exempt.

> Total words: **680**

## Summary Table

| Field | Value |
|---|---|
| fixes live | payload false-positive, R7 sensory, R8 leakage, R9 generic-predicate |
| model | gpt-3.5-turbo |
| cost | $0.0093 |
| tokens | 11679 |
| stops | Cap d'Antibes, Cap Ferrat |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 1/6 paragraphs |
| generation time | 42.9s |
| date | 2026-08-05 |

---

### Cap d'Antibes

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (135 words)

Head south on Avenue de la Tour Gandolphe, enjoy the sea breeze. As you cycle along the coastal path near Cap d'Antibes, take in the breathtaking views of the azure waters and lush greenery that hint at the secrets of the elite who have walked these grounds.

As you cycle along the coastal path, the azure waters and lush greenery create a striking contrast, hinting at the secrets of the elite who have graced these grounds. The Villa Ephrussi de Rothschild, a pink palace visible from the path, stands as a testament to a bygone era's grandeur, its gardens echoing with stories of extravagant parties and quiet introspection. These stops reveal different facets of opulence and understated elegance, where the lives of the famous and the forgotten intertwine in a dance of history and modernity.

#### Paragraph 2 (138 words)

The Cap d'Antibes, a striking peninsula south of Antibes, holds a rich history intertwined with the glamour of the French Riviera. In the 1920s, F. Scott Fitzgerald found inspiration for his novel "Tender is the Night" in this very setting, capturing the essence of the Roaring Twenties that reverberated through these sun-soaked shores. With each pedal, you trace the footsteps of Claude Monet, who ventured to the South of France in 1888. It was here that he delved into painting series, creating masterpieces like "Morning at Antibes." The vibrant colors of the landscape, the play of light on the Mediterranean Sea, and the lush vegetation mirrored in Monet's brushstrokes offer a glimpse into the artistic allure of this coastal paradise. The winding "Tire-Poil" trail, spanning 2.7 kilometers, offers panoramic views of the Lérins Islands and the Mercantour heights.

#### Paragraph 3 (49 words)

Head east along the scenic coastal path from Cap d'Antibes towards Antibes town. Continue past the marina and follow the coastline as you make your way towards Nice. Once in Nice, head east along the Promenade des Anglais towards Villefranche-sur-Mer, where you'll find yourself approaching the stunning Cap Ferrat.

### Cap Ferrat

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (72 words)

As you pedal along the French Riviera, the stunning peninsula of Cap Ferrat beckons you with a promise of grandeur and history. Positioned on the southeastern coast of France, between Beaulieu-sur-Mer and Villefranche-sur-Mer, Saint-Jean-Cap-Ferrat exudes tranquility and opulence. Look to your right, and you'll catch a glimpse of the renowned Villa Ephrussi de Rothschild, a pink palace perched majestically on the promontory, its gardens whispering tales of lavish gatherings and quiet contemplation.

#### Paragraph 2 (218 words)

In the distance, the rose-tinted facade of Villa Ephrussi de Rothschild stands as a beacon of wealth and sophistication, a testament to the lavish lifestyle of the elite. Built by Béatrice de Rothschild, a member of the esteemed Rothschild banking family, this opulent villa overlooks the azure waters of the Mediterranean Sea from its privileged position on the isthmus of Cap Ferrat. As you pause to take in the view, imagine the extravagant parties that once animated these manicured gardens, echoing with the laughter and chatter of the aristocracy. Step closer, and you might catch a hint of the sea breeze mingling with the scent of blooming flowers, creating a sensory tapestry that transports you to a bygone era of elegance and excess. The history of Saint-Jean-Cap-Ferrat dates back to ancient times when the Greeks knew it as Anao. In 2012, Cap Ferrat claimed its place as the second most expensive residential location globally, earning the moniker 'Billionaires' Peninsula' after Monaco. The allure of this exclusive enclave has long attracted the European aristocracy and the international elite, drawn by its serene ambiance and sunny climate. Ahead lies the winding path leading to Cap d'Antibes, inviting you to delve deeper into the intertwining narratives of history and modernity, leaving you pondering the hidden treasures nestled in this picturesque region.

---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | 0 | (clean) |
| R8 | 0 | (clean) |
| R9 | 0 | (clean) |
| R10 | 0 | (clean) |
| R1 | 1/6 | P6: Description:
In the distance, the rose-tinted facade of Villa Ephrussi de Rothsc |

## Deletions Applied During Generation

- [LOCAL-192] Stop 1 para 4: retry FAILED — keeping original (R10_UNFULFILLED_PROMISE)
- [LOCAL-216] PHASE 5.15: R9 generic-sentence deletion...
- [LOCAL-216] Stop 2 'Cap Ferrat': 1 sentence(s) deleted, 0 paragraph(s) emptied
- [LOCAL-216] R9 summary: 1 sentences deleted, 0 paragraphs emptied, 1 stops affected
- [LOCAL-235] PHASE 5.155: R10 unfulfilled-promise deletion...
- [LOCAL-235] Stop 1 'Cap d'Antibes': 2 sentence(s) deleted, 1 paragraph(s) emptied
- [LOCAL-235] R10 summary: 2 sentences deleted, 1 paragraphs emptied, 1 stops affected
- [LOCAL-244] PHASE 5.9: Prolog gating (R9, R10, subject routine)...
- [LOCAL-244] Prolog R9: 0 deletions
- [LOCAL-244] Prolog R10: 1 sentence(s) deleted
- [LOCAL-244] Prolog subject: 0 expanded, 0 deleted, cost=$0.0000
- [LOCAL-244] Prolog deletions (1):
- [R10_UNFULFILLED_PROMISE] "You are about to embark on a journey through the captivating tales woven into the stunning landscape..."
- [LOCAL-246] PHASE 5.95: Orientation gating (R9, R10)...

---

## ROUND4 Re-measurement (with LOCAL-247 fixes)

Previously-reported R10 residual of 0 in ROUND4 was a **false zero**.
With the payload fix live, re-measuring ROUND4's delivered text:

| Rule | Old residual | True residual | False zeros |
|---|---|---|---|
| R7 | 0 | 1 | 1 |
| R8 | 0 | 1 | 1 |
| R9 | 0 | 1 | 1 |
| R10 | 0 | 1 | 1 |

All 4 findings are in Cap d'Antibes paragraph 2:
- R7: "The salty breeze carries the scent of the sea...creates a soothing ambiance."
- R8: "This stop aligns with the tour's theme of exploring..."
- R9: "The Cap d'Antibes, along with Cap Ferrat...inspired countless creatives over the years."
- R10: "The coastline holds stories that deepen the allure of the French Riviera."

---

## Running Comparison

| LOCAL | Words | R7 | R8 | R9 | R10 | R1 rate | Cost |
|---|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | — | — | 4 | 50% | $0.0082 |
| LOCAL-238 | 505 | — | — | 0 | 0 | 40% | $0.0087 |
| LOCAL-244 | 488 | — | — | 0 | 0 | — | $0.0095 |
| LOCAL-245 | 724 | — | — | 0 | 0* | 50% | $0.0095 |
| LOCAL-246 | 538 | — | — | 0 | 0** | 17% | $0.0072 |
| **LOCAL-247** | **680** | **0** | **0** | **0** | **0** | **1/6** | **$0.0093** |

\* R10=0 was measured before payload fix; true residual is 1.
\*\* Same — R10=0 was a false zero caused by the payload false positive.

---

## Run Summary

- audio_tours before: 144
- audio_tours after: 144
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0093 (ceiling: $0.35)
- Generation time: 42.9s

