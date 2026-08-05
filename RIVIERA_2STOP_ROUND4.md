# French Riviera Cycling Tour - 2 Stops, Round 4 (LOCAL-246)

**End-to-end regeneration with orientation gating (PHASE 5.95) and epilog template fix.**

> Total words: **538** (round 3 was 724).


## Summary Table

| Field | Value |
|---|---|
| gates active | **stop-existence (ENFORCE)**, subject routine, **R10**, R9, CONTRADICTED, style retry, **PHASE 5.9 prolog gating**, **PHASE 5.95 orientation gating** |
| existence gate mode | **ENFORCE** (STOP_EXISTENCE_GATE_MODE=enforce) |
| model | gpt-3.5-turbo (default) |
| cost | $0.0072 |
| tokens | 8981 |
| cache hit | False |
| stops selected | Cap d'Antibes Coastal Path, La Croisette |
| -> Cap d'Antibes Coastal Path | VERIFIED - COVERED |
| -> La Croisette | VERIFIED - COVERED |
| R9 residual in delivered text | 0 |
| R10 residual in delivered text | 0 |
| R1 fires on | 1/6 paragraphs |
| generation time | 38.9s |
| date | 2026-08-05 |
| tour ID | N/A (file-only, no audio_tours row) (is_test=true) |

## Prolog Gating (PHASE 5.9)

**Prolog word count before gates:** 114
**Prolog word count after gates:** 64
**Delta:** -50 words

## Orientation Gating (PHASE 5.95) — LOCAL-246

**Orientation word count before gates:** 92
**Orientation word count after gates:** 92
**Delta:** 0 words (no deletions — orientation text was navigational/factual, correctly exempted)

### Post-gate injection points enumerated

| Injection point | Source | Gated? | Reason |
|---|---|---|---|
| Orientation text (per-stop) | LLM-generated, split from description | **YES (LOCAL-246)** | Same gap class as prolog — unfulfilled promises reach output |
| Prolog | LLM-generated, separate call | **YES (LOCAL-244)** | Already fixed |
| Directions/transitions (museum) | Deterministic templates | No | No LLM content; `f"Next: {name}."` |
| Directions/transitions (walking) | LLM via directions_generator.py | No | Navigation-exempt by D107; gating would be no-op (R9/R10 skip nav sentences) |
| Epilog (2-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Template emitted text R9 correctly deletes — template should not exist (carried zero facts despite LOCAL-44 stating "factual observation") |
| Epilog (≥3-stop closing) | Deterministic template | **REMOVED (LOCAL-246)** | Same — "three facets of a collection that spans centuries" is generic filler |
| Epilog (thread payoff) | Deterministic template from theme_thread_discoverer | No | R9 does not fire on it; contains specific thread name + stop names |
| Epilog (closing fact) | Documented story element (corpus) | No | Factual text mined from sources — not LLM narration |
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

---

## End-to-End Tour (generated text after all gates)

### Cap d'Antibes Coastal Path

**Existence:** VERIFIED (geographic_area)
**Coverage:** COVERED

#### Paragraph 1 (141 words)

Start at Antibes train station, head south on Avenue de Verdun, turn right onto Avenue de la Libération. You'll notice the transition from urban streets to coastal scenery as you approach. As you reach the Cap d'Antibes Coastal Path on your French Riviera cycling tour, you'll find yourself immersed in the rugged charm of the Mediterranean coast. Look out for the untamed nature meeting the sea, offering a serene and inspiring retreat for poets and artists alike.

As you glide along scenic paths, each chapter unfolds a different facet of this region's history and allure. Feel the rugged charm of the Mediterranean at the meeting point of sea and untamed nature, a haven for poets seeking inspiration. Then, stroll past the iconic Palais des Festivals, tracing the Riviera's evolution from a quiet fishing village to a luxurious playground for the elite.

#### Paragraph 2 (131 words)

Standing at the Cap d'Antibes Coastal Path, you are enveloped in the beauty of the French Riviera. The Cap d'Antibes, along with Cap Ferrat to the northeast, forms a stunning coastal landscape that has inspired countless creatives over the years. The path winds along the azure waters, offering breathtaking views of the Mediterranean Sea. The salty breeze carries the scent of the sea, and the sound of gentle waves lapping against the rocky shore creates a soothing ambiance. This stop aligns with the tour's theme of exploring the cultural and natural wonders of the French Riviera. The Cap d'Antibes Coastal Path showcases the region's unspoiled beauty and rich history, making it a must-visit for those seeking tranquility and inspiration. The coastline holds stories that deepen the allure of the French Riviera.

#### Paragraph 3 (49 words)

Head east along the Cap d'Antibes Coastal Path until you reach the roundabout at Boulevard John Fitzgerald Kennedy. Turn left onto Boulevard de la Croisette and continue straight. You'll pass by luxury boutiques and hotels as you make your way towards the famous Palais des Festivals on La Croisette.

### La Croisette

**Existence:** VERIFIED (geographic_area)
**Coverage:** COVERED

#### Paragraph 1 (138 words)

As you cycle along the vibrant French Riviera, you'll arrive at the iconic La Croisette in Cannes. Look out for the bustling promenade lined with luxury boutiques, palm trees swaying in the gentle sea breeze, and the azure waters of the Mediterranean glinting under the sun.

In 1946, the Cannes Film Festival faced disruption due to the French government's mobilization. The festival triumphantly returned the following year, showcasing films from 16 countries at the "Festival du film de Cannes." Today, La Croisette symbolizes glamour and prestige, with the Palais des Festivals et des Congrès hosting esteemed filmmakers and stars. Standing here, visitors can hear distant laughter, feel polished marble under their feet, and catch a whiff of salt in the air. This luxurious stop encapsulates Cannes' transformation from a quiet fishing village to a playground for the elite.

---

## R9/R10 Residual Check (on delivered text)

**R9 residual sentences in delivered text: 0**

Delivered text is clean — 0 R9 triggers remain.

**R10 residual sentences in delivered text: 0**

Delivered text is clean — 0 R10 triggers remain.

**R1 fires on: 1/6 paragraphs**
- P3: "As you glide along scenic paths, each chapter unfolds a different facet of this "

---

## Running Comparison

| LOCAL | Words | R9 residual | R10 residual | R1 rate | Cost | Key change |
|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | 4 | 50% (4/8) | $0.0082 | Baseline end-to-end |
| LOCAL-238 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline |
| LOCAL-241 | 393 | 0 | 0 | — | $0.0087 | End-to-end rerun |
| LOCAL-243 | 505 | 0 | 0 | 40% | $0.0087 | R10 in-pipeline (log_only gate) |
| LOCAL-244 | 488 | 0 | 0 | — | $0.0095 | Prolog gating (PHASE 5.9) |
| LOCAL-245 | 724 | 0 | 0* | 50% (3/6) | $0.0095 | Existence gate ENFORCE |
| **LOCAL-246** | **538** | **0** | **0** | **17%** (1/6) | **$0.0072** | **Orientation gating + epilog template removed** |

\* LOCAL-245 R10=0 in descriptions, but 1 unfulfilled promise survived in ungated Orientation text.

---

## Run Summary

- Tour ID: N/A (file-only, no audio_tours row) (is_test=true, lat/lng=NULL)
- audio_tours: 144 -> 144 (delta: +0)
- Nice list: [1, 12, 14, 17, 24, 29, 152] - UNCHANGED
- Model: gpt-3.5-turbo (TOUR_LLM_MODEL unset)
- Total cost: $0.0072
- Generation time: 38.9s
- Total words (final): 538
- Existence gate: ENFORCE (all delivered stops verified)
- R9 residual: 0
- R10 residual: 0
- Orientation before/after: 92/92 words
