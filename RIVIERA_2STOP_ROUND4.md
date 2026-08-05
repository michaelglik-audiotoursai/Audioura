# French Riviera Cycling Tour - 2 Stops, Round 4 (LOCAL-246)

**End-to-end regeneration with orientation gating (PHASE 5.95).**

> Total words: **639** (round 3 was 724).


## Summary Table

| Field | Value |
|---|---|
| gates active | **stop-existence (ENFORCE)**, subject routine, **R10**, R9, CONTRADICTED, style retry, **PHASE 5.9 prolog gating**, **PHASE 5.95 orientation gating** |
| existence gate mode | **ENFORCE** (STOP_EXISTENCE_GATE_MODE=enforce) |
| model | gpt-3.5-turbo (default) |
| cost | $0.0093 |
| tokens | 11579 |
| cache hit | False |
| stops selected | Cap d'Antibes, Villefranche-sur-Mer |
| -> Cap d'Antibes | VERIFIED - COVERED |
| -> Villefranche-sur-Mer | VERIFIED - COVERED |
| R10 residual in delivered text | 0 |
| R1 fires on | 1/6 paragraphs |
| generation time | 47.3s |
| date | 2026-08-05 |
| tour ID | N/A (file-only, no audio_tours row) (is_test=true) |

## Prolog Gating (PHASE 5.9)

**Prolog word count before gates:** 106
**Prolog word count after gates:** 0
**Delta:** -106 words

## Orientation Gating (PHASE 5.95) — LOCAL-246

**Orientation word count before gates:** 99
**Orientation word count after gates:** 99
**Delta:** 0 words (no deletions — orientation text was navigational/factual, correctly exempted)

### Post-gate injection points enumerated

| Injection point | Source | Gated? | Reason |
|---|---|---|---|
| Orientation text (per-stop) | LLM-generated, split from description | **YES (LOCAL-246)** | Same gap class as prolog — unfulfilled promises reach output |
| Prolog | LLM-generated, separate call | **YES (LOCAL-244)** | Already fixed |
| Directions/transitions (museum) | Deterministic templates | No | No LLM content; `f"Next: {name}."` |
| Directions/transitions (walking) | LLM via directions_generator.py | No | Navigation-exempt by D107; gating would be no-op (R9/R10 skip nav sentences) |
| Epilog | Deterministic templates + corpus facts | No | No LLM prose; template strings + mined factual text |
| Operational details | Extracted visitor info (hours/prices) | No | Factual data, not narration |
| Sources line | Domain names from corpus | No | Metadata, not narration |
| Tour title / category | Metadata | No | Not narration |

### Boundary verification

| must survive | result | reason |
|---|---|---|
| "Start cycling south on the main road…" | ✓ SURVIVES | nav=True → R9/R10 skip |
| "From this vantage point the bay is visible below." | ✓ SURVIVES | Starts with preposition (Gate A) → R1 silent; no promise noun → R10 silent |

| must be caught | result | reason |
|---|---|---|
| "take a moment to absorb the whispers of centuries" | ✓ CAUGHT by R10 | 'whispers' ∈ promise nouns + structural verb match |
| "delve into its storied past" | △ NOT CAUGHT | 'storied'=adjective, 'past'=noun, neither in R10 promise set. D55 prohibits detector change. |

## Delivered Tour Text

```
Step-by-Step Audio Guided Tour: French Riviera cycling tour, France - Cycling Tour
Tour-Category: walking

Stop 1: Cap d'Antibes

Address: Cap d'Antibes, 06160 Antibes, France

Coordinates: 43.5410, 7.0956

Type/Specialty: Scenic coastal area

Specific Examples: Beautiful beaches, historic lighthouse, luxury villas

Orientation: Start cycling south on the main road, continue until you reach the Cap d'Antibes. Enjoy the stunning views of the Mediterranean Sea along the way. As you arrive at Cap d'Antibes on your French Riviera cycling tour, take in the stunning views of the Mediterranean Sea from this picturesque peninsula located south of Antibes. Find a comfortable spot to soak in the beauty of the coastline and the historic significance of this iconic location.

Description:
The Cap d'Antibes holds a special place in history, with its rocky cliffs and lush greenery offering a serene retreat from the bustling city life. In 1888, renowned artist Claude Monet found inspiration in the vibrant Mediterranean light here, leading to the creation of masterpieces like "Morning at Antibes." The coastal path along the cape provides a glimpse into the past, where Impressionist painters sought solace and creativity amidst the natural beauty. The rhythmic crashing of waves against the rocks creates a soothing soundtrack to accompany your exploration of this historic site. Cap d'Antibes embodies the essence of the French Riviera's allure with its rich cultural heritage and breathtaking vistas. The Tire-Poil trail winds through the region, offering panoramic views of the Lérins Islands and the Mercantour heights, showcasing the natural splendor of the area.

Directions: As you leave Cap d'Antibes, head towards the coast and follow the scenic route along the Mediterranean Sea towards Nice. Once you reach Nice, continue east along the coast until you arrive in Villefranche-sur-Mer. You'll pass by beautiful beaches, charming cafes, and the iconic Promenade des Anglais along the way. Enjoy the stunning views as you walk towards your destination.

Stop 2: Villefranche-sur-Mer

Address: Villefranche-sur-Mer, France

Coordinates: 43.7034, 7.3110

Type/Specialty: Charming seaside town

Specific Examples: Colorful buildings, citadel, sandy beaches

Orientation: As you arrive at Villefranche-sur-Mer on your French Riviera cycling tour, you find yourself at a seaside resort town nestled to the east of Nice and southwest of Monaco. The name itself, translating to "Free City on Sea" in Old French, hints at the historical significance of this charming location.

It once served as a strategic naval base, offering safe anchorage for large ships and reaching impressive depths of 95 meters (320 feet). This bay, one of the deepest natural harbors in the Mediterranean, has witnessed the ebb and flow of centuries, its waters reflecting the stories of conquest and serenity. As you stand on the shores of Villefranche-sur-Mer, the echoes of history reverberate through the salty sea breeze. The strategic importance of this harbor can be traced back through the annals of time, connecting it to pivotal moments in maritime history. The undersea Canyon of Villefranche, a 1,700-foot abyss just off the coastline, serves as a silent witness to the ever-changing tides of human endeavor. Amidst the quaint streets and colorful buildings of Villefranche-sur-Mer, the juxtaposition of ancient fortifications and modern-day cafes creates a tapestry of time, blending the past with the present in a harmonious dance of existence. This stop on your journey through the French Riviera cycling tour invites you to explore not just the physical beauty of the landscape but also the layered history that lies beneath the surface. The artistic legacy of this town is intertwined with its maritime heritage, painting a vivid picture of a place where time stands still, even as the waves continue to lap against the shore. Just ahead, the historic streets beckon you to delve deeper into their storied past, promising a journey through time and memory as you pedal onward.

From Cap d'Antibes to Villefranche-sur-Mer — a collection that spans more ground than these stops alone.


```

## Residual Analysis (measured by LOCAL-246 on delivered text)

**R10 residual:** 0 sentence(s)
- (none)

**R1 fires on:** 1/6 paragraphs (17%)
- P3: "Description:
The Cap d'Antibes holds a special place in history, with its rocky "

## Running Comparison

| Round | Words | R10 residual | R1 rate | Cost | Key change |
|---|---|---|---|---|---|
| Round 1 (LOCAL-222) | 819 | 4 | 50% (4/8) | $0.0082 | Baseline end-to-end |
| Round 1b (rule-on-old) | 191 | 0 | 0% (0/3) | $0.00 | R10 applied to existing text |
| Round 2 (LOCAL-238) | 505 | 0 | 40% | $0.0087 | R10 in-pipeline |
| Round 2b (LOCAL-244) | 488 | 0 | — | $0.0095 | Prolog gating (PHASE 5.9) |
| Round 3 (LOCAL-245) | 724 | 0* | 50% (3/6) | $0.0095 | Existence gate ENFORCE |
| **Round 4 (LOCAL-246)** | **639** | **0** | **17%** (1/6) | **$0.0093** | **Orientation gating (PHASE 5.95)** |

\* Round 3 R10=0 in descriptions, but 1 unfulfilled promise survived in ungated Orientation text.

## Run Summary

- Tour ID: N/A (file-only, no audio_tours row) (is_test=true, lat/lng=NULL)
- audio_tours: 144 -> 144 (delta: +0)
- Nice list: [1, 12, 14, 17, 24, 29, 152] - UNCHANGED
- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)
- Total cost: $0.0093
- Generation time: 47.3s
- Total words (final): 639
- Existence gate: ENFORCE (all delivered stops verified)
- R10 residual: 0
- Orientation before/after: 99/99 words (0 deletions — orientation was clean navigation/factual text)
