# French Riviera Cycling Tour — 2 Stops, Round 3 (LOCAL-239)

**Generated with venue-kind-corrected stop-existence gate ENFORCING, subject validate/expand/remove ON, R10+R9 applied.**

## Summary Table

| Field | Value |
|---|---|
| gates active | stop-existence with venue-kind fix (ENFORCING), subject routine, R10, R9, CONTRADICTED block, style retry |
| venue kind | geographic_area (relaxed verification: stop_corpus presence = sufficient) |
| stops selected | Cap d'Antibes, Eze Village |
| → Cap d'Antibes verification | VERIFIED — stop_corpus_geographic: stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera  |
| → Eze Village verification | VERIFIED — stop_corpus_geographic: stop_corpus(geographic): 'Eze Village' at 'French Riviera wa |
| promises found | 1 |
| expanded | 0 |
| deleted (subject routine) | 1 |
| R10 deletions | 1 sentences |
| R9 deletions | 1 sentences |
| model | gpt-3.5-turbo (default) |
| cost | ~$0.0010 subject routine + generation |
| date | 2026-08-05 01:46 |
| tour ID | 195 (is_test=true) |

## What Changed from Previous Round 3 (LOCAL-238)

LOCAL-238's Round 3 marked Villefranche-sur-Mer as **UNVERIFIED** due to a gate bug: the gate required passages to contain venue-name words like "Riviera" or "French", but geographic places' Wikipedia articles don't use our internal label "French Riviera walking area".

LOCAL-239 fixes this by classifying venues into **institution** vs **geographic_area**:
- **Institution** (has `sparql_works_json`): strict — stop must match a known work/title
- **Geographic area** (no `sparql_works_json`): relaxed — stop_corpus having a passage is sufficient proof it's a real place in the region

This corrects 15 false-negative Riviera stops (including Villefranche-sur-Mer, Eze Village, Cap Ferrat, Mont Boron) while keeping fabricated museum stops (Ulysses Grant au Japon, Kannon à mille bras) firmly UNVERIFIED.

---

### Cap d'Antibes

*(D64: Stop 1 contains the tour prolog inside it)*

**Existence verification:** VERIFIED — stop_corpus_geographic: stop_corpus(geographic): "Cap d'Antibes" at 'French Riviera walking area' (7 pas
**Venue kind:** geographic_area
**Coverage:** COVERED

#### Paragraph 1

Operational Details: Open 24/7 for outdoor exploration

`[style: clean | coverage: COVERED]`

#### Paragraph 2

Start biking east along the coastal road with stunning views of the Mediterranean Sea. Position yourself at the edge of Cap d'Antibes, where the Mediterranean Sea sprawls out endlessly before you. Feel the gentle sea breeze caress your skin as the distant cry of seagulls mingles with the rhythmic lapping of waves against the rocky shore.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 3

You are about to embark on a journey through the French Riviera, where the sun-drenched coasts and ancient villages hold a tapestry woven with the glamour of modern allure and whispers of medieval roots. Cycling through winding paths, you'll discover a blend of architectural marvels and forgotten tales that shape its identity. The ancient fortifications of the Garoupe Lighthouse stand sentinel against opulent villas, revealing a juxtaposition of past and present. Discover how the idyllic beauty of the French Riviera masks the secrets of its past as you unravel its intricate story through each chapter of this enchanting journey.

`[style: R1_IMPERATIVE | coverage: COVERED]`

#### Paragraph 4

Standing on the historic Cap d'Antibes, the convergence of past and present unfolds. The ancient fortifications of the Garoupe Lighthouse, a sentinel of bygone eras, starkly contrast with the opulent villas that line the coastline, symbolizing the enduring allure of this coastal haven. Here, in this picturesque setting, you witness the essence of Antibes unfold before you. The Cap d'Antibes, along with Cap Ferrat in Saint-Jean-Cap-Ferrat, frames the horizon, embodying the natural beauty that has drawn visitors for centuries. In this moment, let the azure hues of the Mediterranean Sea and the vibrant greens of the lush vegetation paint a vivid tableau of the French Riviera. The crisp sea air carries whispers of history, mingling with the contemporary pulse of yachting harbors and bustling town life. As you pedal onwards, the road to Eze Village beckons, promising a journey back through time, where each turn reveals a new facet of the region's captivating history and natural beauty.

`[style: R7_HALLUCINATED_SENSORY | coverage: COVERED]`

### Eze Village

**Existence verification:** VERIFIED — stop_corpus_geographic: stop_corpus(geographic): 'Eze Village' at 'French Riviera walking area' (1 passa
**Venue kind:** geographic_area
**Coverage:** COVERED

#### Paragraph 5

Operational Details: Shops and cafes open from morning till evening

`[style: clean | coverage: COVERED]`

#### Paragraph 6

[Description for Eze Village could not be generated.]

`[style: clean | coverage: COVERED]`

---

## Subject Routine: Deletions and Expansions (verbatim)

**1 promises found → 0 expanded, 1 deleted**

### Deletions

- **[Cap d'Antibes, Para 3]** *"As you wander through the exotic Jardin Exotique d'Eze, panoramic views whisper tales of ancient Provencal nobility and their long-lost gardens."*
  Reason: Source found but expansion could not deliver

## R10 / R9 Deletions (verbatim)

### R10 Unfulfilled-Promise Deletions (1 sentences)

- **[Cap d'Antibes]** *"Cap d'Antibes, with its rich tapestry of landscapes and stories, serves as a window into the enduring charm of the Côte d'Azur."*

### R9 Generic-Sentence Deletions (1 sentences)

- **[Eze Village]** *"From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone."*

---

## Run Summary

- Tour ID: 195 (is_test=true, lat/lng=NULL)
- audio_tours before: 140, after: 141 (delta: +1)
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓
- Generation time: 39.6s
- Total words (final): ~343
- Subject routine cost: $0.0010
- Total estimated cost: <$0.01 (well under $0.35 ceiling)
