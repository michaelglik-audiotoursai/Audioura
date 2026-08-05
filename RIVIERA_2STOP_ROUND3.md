# French Riviera Cycling Tour — 2 Stops, Round 3 (LOCAL-240)

**Regenerated with LOCAL-240 structural R10 widening (promise noun + promise verb shape detection).**

## Summary Table

| Field | Value |
|---|---|
| gates active | stop-existence with venue-kind fix (ENFORCING), subject routine, **R10 (widened LOCAL-240)**, R9, CONTRADICTED block, style retry |
| R10 change | structural detection: promise noun + verb of possession/concealment (LOCAL-240) |
| venue kind | geographic_area (relaxed verification: stop_corpus presence = sufficient) |
| stops selected | Cap d'Antibes, Eze Village |
| → Cap d'Antibes verification | VERIFIED — stop_corpus_geographic |
| → Eze Village verification | VERIFIED — stop_corpus_geographic |
| promises found (subject routine) | 1 |
| expanded | 0 |
| deleted (subject routine) | 1 |
| R10 deletions | 8 sentences |
| R9 deletions | 1 sentences |
| model | gpt-3.5-turbo (tour 195 — same generation, R10 re-applied) |
| cost | $0.00 (no LLM call — R10 re-applied to existing tour 195 text) |
| date | 2026-08-05 02:21 |
| tour ID | 195 (is_test=true) |

## What Changed from Previous Round 3 (LOCAL-239)

LOCAL-239's Round 3 applied R10 to the same text but scored **0 hits** on paragraph 3 —
the exact paragraph Michael scored 2/5 with *"senseless combination of words… no
interconnectedness."*

LOCAL-240 widens R10 from a regex phrase list to **structural shape detection**:
a sentence triggers if it contains both a **promise noun** (tale, story, secret,
chapter, tapestry, whispers, roots, essence, juxtaposition, legacy) AND a **verb of
possession/concealment** (hold, mask, reveal, discover, carry, shape, stand sentinel,
unravel, weave). This catches "villages hold a tapestry" and "masks the secrets"
which the old phrase-only list missed entirely.

Additionally: `lighthouse` added to `_place_suffixes` so that "Garoupe Lighthouse"
is correctly classified as a place name (not a person), preventing false self-delivery.

**Result: R10 now fires on all 5 promise fragments from paragraph 3, plus 3 more from paragraph 4.**

---

### Cap d'Antibes

*(D64: Stop 1 contains the tour prolog inside it)*

**Existence verification:** VERIFIED — stop_corpus_geographic
**Venue kind:** geographic_area
**Coverage:** COVERED

#### Paragraph 1

Open 24/7 for outdoor exploration

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 2

Start biking east along the coastal road with stunning views of the Mediterranean Sea. Position yourself at the edge of Cap d'Antibes, where the Mediterranean Sea sprawls out endlessly before you. Feel the gentle sea breeze caress your skin as the distant cry of seagulls mingles with the rhythmic lapping of waves against the rocky shore.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 3

Standing on the historic Cap d'Antibes, the convergence of past and present unfolds. Here, in this picturesque setting, you witness the essence of Antibes unfold before you. The Cap d'Antibes, along with Cap Ferrat in Saint-Jean-Cap-Ferrat, frames the horizon, embodying the natural beauty that has drawn visitors for centuries. In this moment, let the azure hues of the Mediterranean Sea and the vibrant greens of the lush vegetation paint a vivid tableau of the French Riviera. As you pedal onwards, the road to Eze Village beckons, promising a journey back through time, where each turn reveals a new facet of the region's captivating history and natural beauty.

`[style: clean | coverage: COVERED]`

### Eze Village

**Existence verification:** VERIFIED — stop_corpus_geographic
**Venue kind:** geographic_area
**Coverage:** COVERED

#### Paragraph 4

Shops and cafes open from morning till evening

`[style: clean | coverage: COVERED]`

#### Paragraph 5

Look for this work in the galleries.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 6

[Description for Eze Village could not be generated.]

`[style: clean | coverage: COVERED]`

---

## Subject Routine: Deletions and Expansions (verbatim)

**1 promise found → 0 expanded, 1 deleted**

### Deletions

- **[Cap d'Antibes, Para 3]** *"As you wander through the exotic Jardin Exotique d'Eze, panoramic views whisper tales of ancient Provencal nobility and their long-lost gardens."*
  Reason: Source found but expansion could not deliver

## R10 / R9 Deletions (verbatim)

### R10 Unfulfilled-Promise Deletions (8 sentences)

- **[Cap d'Antibes]** *"Cycling through winding paths, you'll discover a blend of architectural marvels and forgotten tales that shape its identity."*
- **[Cap d'Antibes]** *"Cap d'Antibes, with its rich tapestry of landscapes and stories, serves as a window into the enduring charm of the Côte d'Azur."*
- **[Cap d'Antibes]** *"You are about to embark on a journey through the French Riviera, where the sun-drenched coasts and ancient villages hold a tapestry woven with the glamour of modern allure and whispers of medieval roots."*
- **[Cap d'Antibes]** *"As you wander through the exotic Jardin Exotique d'Eze, panoramic views whisper tales of ancient Provencal nobility and their long-lost gardens."*
- **[Cap d'Antibes]** *"The ancient fortifications of the Garoupe Lighthouse stand sentinel against opulent villas, revealing a juxtaposition of past and present."*
- **[Cap d'Antibes]** *"The crisp sea air carries whispers of history, mingling with the contemporary pulse of yachting harbors and bustling town life."*
- **[Cap d'Antibes]** *"Discover how the idyllic beauty of the French Riviera masks the secrets of its past as you unravel its intricate story through each chapter of this enchanting journey."*
- **[Cap d'Antibes]** *"The ancient fortifications of the Garoupe Lighthouse, a sentinel of bygone eras, starkly contrast with the opulent villas that line the coastline, symbolizing the enduring allure of this coastal haven."*

### R9 Generic-Sentence Deletions (1 sentences)

- **[Eze Village]** *"From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone."*

---

## R10 Boundary Verification (LOCAL-240)

### Must-fire (round 3 paragraph 3, verbatim) — ALL PASS ✓

| Fragment | Fires? |
|---|---|
| "villages hold a tapestry woven with… whispers of medieval roots" | ✓ FIRE |
| "forgotten tales that shape its identity" | ✓ FIRE |
| "masks the secrets of its past" | ✓ FIRE |
| "its intricate story through each chapter" | ✓ FIRE |
| "stand sentinel against opulent villas, revealing a juxtaposition of past and present" | ✓ FIRE |

### Must-NOT-fire (his rewrite prose) — ALL PASS ✓

| Sentence | Fires? |
|---|---|
| "In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide." | ✓ CLEAN |
| "The Antonine Itinerary mentions the bay of Èze as Avisionis portus." | ✓ CLEAN |
| "F. Scott Fitzgerald based the opening hotel of his 1934 novel on Eden-Roc." | ✓ CLEAN |
| "…the Hôtel du Cap-Eden-Roc, built here in 1870, at the southern tip." | ✓ CLEAN |
| "Start cycling south on the main road…" | ✓ CLEAN |

### Tour 180 — 12 fires (was 11, +1 new catch) ✓

The 11 existing hits remain; 1 new sentence caught by structural detection:
- *"As you wind through the picturesque landscapes, you'll uncover the timeless allure that ha…"*

---

## Run Summary

- Tour ID: 195 (is_test=true, lat/lng=NULL) — R10 re-applied, no new DB row
- audio_tours: 141 (unchanged)
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓
- Total words (final): ~191
- R10 corpus-wide: 171 → 355 fires (2.39% → 4.95%)
- Total cost: $0.00 (no LLM call)
