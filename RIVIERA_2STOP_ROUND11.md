# French Riviera Cycling Tour - 2 Stops, Round 11 (LOCAL-253)

> ### What changed: Transport-mode-aware directions (LOCAL-253)
>
> The directions generator now receives the tour's transport mode and uses
> mode-appropriate language (cycling verbs, not walking verbs). A post-
> generation guard rejects directions containing motorways, public transport,
> or wrong-mode verbs on cycling tours. Previously the mode was lost at the
> call boundary: `generate_walking_directions` was called without the
> `transport_mode` parameter, hardcoding walking language for all outdoor tours.
>
> **Defect:** `generate_tour_text.py` line 7675 called
> `generate_walking_directions(poi_name, next_poi["name"], location, api_key)`
> — the `transport_mode` variable was in scope but never passed. The function
> then used a hardcoded "walking directions" system prompt for all outdoor tours.

> **Word count:** 790
> **Stops:** 2 (Cap d'Antibes, Saint-Paul-de-Vence)
> **Generation cost:** $0.0091
> **Generation time:** 39.8s
> **Attempts:** 1/3
> **STOP_EXISTENCE_GATE_MODE:** enforce

## Summary Table

| Field | Value |
|---|---|
| fix | LOCAL-253: transport_mode passed to directions_generator |
| model | gpt-3.5-turbo |
| generation cost | $0.0091 |
| tokens | 11385 |
| stops | Cap d'Antibes, Saint-Paul-de-Vence |
| word count | 790 |
| directions mode | cycling |
| mode guard violations | none |
| generation time | 39.8s |
| generation attempts | 1/3 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Per-Leg Directions (Verbatim)

### Leg 1
**Mode used:** cycling

> Start your ride at Cap d'Antibes and pedal east along the scenic coastal road. Enjoy the stunning views of the Mediterranean Sea as you cycle towards Antibes Old Town. From there, continue your journey north, passing through picturesque villages like Saint-Paul-de-Vence along the way. Happy cycling!

**Violations:** none ✓

---

## Tour Content

### Cap d'Antibes

**Fact tally:** 10 of 17 sentences carry a verifiable fact

#### Paragraph 1 (71 words)

Start cycling southeast on the coastal road, enjoy the sea breeze along the way. As you arrive at Cap d'Antibes on your French Riviera cycling tour, you'll find yourself at the stunning peninsula located south of Antibes and east of Juan-les-Pins. The salty breeze from the sparkling waters of the Mediterranean Sea will greet you as you take in the panoramic views of the Lérins Islands and the heights of Mercantour.

#### Paragraph 2 (134 words)

You are about to embark on a journey through the enchanting landscapes and forgotten tales of the French Riviera, where opulence intertwines with artistic mystery like a tangled vine reaching for the sun. Along the sun-drenched shores and hilltop villages, you'll uncover the secrets hidden beneath the glamorous facade that have inspired artists and aristocrats alike. Feel the salty breeze that once stirred F. Scott Fitzgerald's timeless prose as you gaze upon the sparkling waters that captivated his imagination. Then, venture to the Maeght Foundation and delve into the vivid art collection that reveals the untold stories of the Riviera's creative soul, connecting the past with the present in a tapestry of culture and history. This journey is a book of connected chapters, each revealing a different facet of this captivating region's dual identity.

#### Paragraph 3 (189 words)

Cap d'Antibes, a symbol of beauty and luxury, holds a historical significance dating back to the early 20th century when it became a coveted destination for the elite. In 2023, Antibes had a population of 77,637, solidifying its position as a vibrant coastal city. The cape itself, along with Cap Ferrat in Saint-Jean-Cap-Ferrat, defines the picturesque landscape of the French Riviera. Scott Fitzgerald's words from "Tender is the Night," inspired by the Roaring Twenties that once animated this very coast. In 1888, Claude Monet painted his masterpiece "Morning at Antibes" here, capturing the ethereal blue light that envelops the region. The scenic route along the river, with its invigorating shade, provides a glimpse into the daily life of locals who traverse these paths. The blend of history, nature, and artistic inspiration at Cap d'Antibes encapsulates the essence of the French Riviera's cultural heritage, offering a fusion of tradition and modernity that continues to allure visitors from around the world. As you pedal forward, the waves carry stories to the artists' retreat ahead, where creativity and history intertwine to offer an immersive experience along the enchanting coastline of the Mediterranean.

### Saint-Paul-de-Vence

**Fact tally:** 8 of 10 sentences carry a verifiable fact

#### Paragraph 1 (53 words)

As you arrive in the ancient town of Saint-Paul-de-Vence, perched atop a hill in the French Riviera, take a moment to absorb the timeless beauty that has attracted artists and luminaries for centuries. Look for the Fondation Maeght, a beacon of artistic expression that holds the untold stories of the Riviera's creative soul.

#### Paragraph 2 (230 words)

In the heart of Saint-Paul-de-Vence, the Fondation Maeght stands as a testament to modern art's vibrant presence in this medieval enclave. Established in 1964 by Marguerite and Aimé Maeght, this museum overlooks the town and houses a remarkable collection of over 13,000 pieces, including works by renowned artists such as Chagall, Miró, Giacometti, Braque, and Calder. Designed by Spanish architect Josep Lluís Sert, the building itself is a masterpiece of modernist architecture, blending seamlessly with the surrounding landscape. The Fondation Maeght's inauguration on July 28, 1964, marked a pivotal moment in the art world, as declared by André Malraux, who emphasized the importance of creating a unique space for modern art to flourish. This cultural hub offers a window into a universe where creativity knows no bounds, where each brushstroke and sculpture tells a story of innovation and inspiration. Saint-Paul-de-Vence has long been a haven for the famous, drawing notable figures like American writer James Baldwin, who called this town home for 17 years until his passing in 1987. As you explore the Fondation Maeght and the charming streets of Saint-Paul-de-Vence, let the whispers of artistic genius guide you through a journey of revelation and wonder. Just beyond the ancient walls, imagine the laughter of Picasso and the vibrant colors of Chagall echoing through the centuries, inviting you to delve deeper into the rich cultural tapestry of this enchanting town.

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- Cost: $0.0091 (ceiling: $0.6)
- Generation time: 39.8s
- Generation attempts: 1/3
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce

---

## Running Comparison

| LOCAL | Words | Directions Mode | Cost |
|---|---|---|---|
| ROUND10 | 679 | walking (BUG) | $0.0095 |
| **ROUND11** | **790** | **cycling (FIXED)** | **$0.0091** |
