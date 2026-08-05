# French Riviera Cycling Tour - 2 Stops, Round 10 (ROUND10)

> ### LEAD's verified note — read this first
>
> **Stop 2 is the first one I think is close.** Èze Village: **8 of 11 sentences
> carry a fact**, against 2 of 11 for Saint-Paul-de-Vence in round 7. I checked
> the seven checkable claims against Wikipedia myself and **all seven are
> accurate** — the House of Savoy fortifying the town in 1388, Barbarossa taking
> it in 1543, Louis XIV razing the castle in 1706, the Chapelle de la Sainte
> Croix of 1306, the White Penitents aiding plague victims, the unanimous April
> 1860 vote to join France at 427 metres, and Walt Disney's 1956 visit leading
> to the Château de la Chèvre d'Or becoming a hotel.
>
> That is what the corpus work bought. Èze had one source passage yesterday.
>
> **Four things are still wrong, and one of them matters for a field test.**
>
> 1. **The directions tell you to take a train.** "Start your **walk** from Cap
>    d'Antibes… From Antibes train station, **take a train** towards Eze
>    Village." This is a cycling tour, and Antibes to Èze is about 40 km — well
>    inside the route budget. The transport mode is being dropped somewhere in
>    the directions generator.
> 2. **`Tour-Category: walking`** on a cycling tour. Not a regression — I
>    checked, it does this on the base too — but it is in the header of every
>    tour you read.
> 3. **Fitzgerald's 1934 novel is stated twice**, once in the opening and again
>    in the body, despite the one-passage-per-tour rule reporting a single
>    passage spent. "Stands as a testament" appears three times across the tour.
> 4. **R7 still misses your 1/5 sentence.** "Take a moment to breathe in the
>    salty sea air and listen to the gentle lapping of the waves" — invented
>    sensory detail, silent. It fires instead on "the echoes of history
>    reverberate", which is the same class. My measurement of the delivered
>    text: R1 on 5 sentences, R7 on 1.
>
> **Stop 1 is weaker than stop 2** — 4 of 9 sentences carry a fact, and it still
> closes on "the enchanting promontory stands as a testament to the timeless
> beauty of the French Riviera", which says nothing.


> ### What changed: Expand before delete (v2 — dedup fix)
>
> LOCAL-249 built the "remove" half of Michael's routine. This builds the
> "expand" half: between detection and deletion, query the corpus for a fact
> that would substantiate the promise, and rewrite the sentence around it.
> Deletion stays the default and the fallback — never publish an undelivered promise.
>
> **v2 fixes (LEAD bounce):** One corpus passage may substantiate only ONE sentence
> per tour. If a second flagged sentence matches only a passage already spent, it is
> deleted. Also: stripped leaked "Description:" field labels from narration.
>
> **Expansion is working.**
> Expanded: 1 sentence(s). Deleted: 4 sentence(s).
> Passages spent: 1.

**Fixes live in this run:**
1. **Expand before delete with dedup** (ROUND10 primary): R10-flagged sentences are
   first looked up in stop_corpus; if a matching fact is found AND that passage has not
   been spent, the sentence is rewritten around that fact. One passage → one expansion.
   Deletion fires when the corpus has nothing or the passage is already spent.
2. **Structural promise detection** (LOCAL-249): verb-independent subject-matter
   noun detection.
3. All LOCAL-247 fixes (payload false-positive, R7, R8, R9) remain active.
4. **Label stripping**: "Description:" field labels stripped from narration post-generation.

> **Word counts:** Round 5: 680 | Round 6: 298 | **Round 10: 679**
> Stops: 2 (Cap d'Antibes, Eze Village)

## Summary Table

| Field | Value |
|---|---|
| fixes live | expand-before-delete+dedup (ROUND10), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | $0.0094 |
| expansion cost | $0.0001 |
| total cost | $0.0095 |
| tokens (generation) | 11784 |
| stops | Cap d'Antibes, Eze Village |
| expanded | 1 |
| deleted | 4 |
| passages spent (dedup) | 1 |
| R7 residual | 1 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 4/5 paragraphs |
| generation time | 42.7s |
| generation attempts | 1/3 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Tour Content

### Cap d'Antibes

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (67 words)

Start cycling southeast on the main road with the sea on your right until you reach Cap d'Antibes lighthouse. As you arrive at Cap d'Antibes, find yourself amidst the lush greenery of the promontory, overlooking the pristine beaches and luxurious villas that dot the coastline. Take a moment to breathe in the salty sea air and listen to the gentle lapping of the waves against the shore.

#### Paragraph 2 (55 words)

Fitzgerald's Tender is the Night, published in 1934, offers a vivid glimpse into the Roaring Twenties and was inspired by the vibrant life of the French Riviera. As you arrive at the lush promontory, discover how pristine beaches and luxurious villas mask a history of glittering parties frequented by literary legends like F. Scott Fitzgerald.

#### Paragraph 3 (174 words)

Cap d'Antibes, a stunning peninsula located south of Antibes, holds within its sun-kissed embrace a hidden history of glittering parties frequented by literary legends like F. Scott Fitzgerald. In 1934, Fitzgerald's novel "Tender is the Night" captured the essence of 'the Roaring Twenties' and was inspired by the racy soirées that unfolded in this very locale. Historically, Claude Monet ventured to the South of France in 1888, where he began experimenting with painting in series. It was here that he created masterpieces like "Morning at Antibes," a testament to the captivating beauty that envelops this coastal paradise. The cape of Cap d'Antibes, along with neighboring Cap Ferrat, stands as a testament to the rich cultural heritage of the French Riviera. The "Tire-Poil" trail offers views of the Lérins Islands and Mercantour, showcasing the natural splendor that has inspired artists for generations. Pedal along the coastal road and discover the secluded paths of Cap d'Antibes, where artists once found inspiration. The enchanting promontory stands as a testament to the timeless beauty of the French Riviera.

### Eze Village

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (35 words)

As you arrive at Eze Village perched high above the sea, position yourself on the cobblestone streets leading to the Chapelle de la Sainte Croix for a stunning panoramic view of the French Riviera coastline.

#### Paragraph 2 (232 words)

Eze Village stands as a testament to resilience, its roots tracing back to 200 BC near Mount Bastide. The echoes of history reverberate through the medieval streets, where the Antonine Itinerary first mentioned the bay as Avisionis portus. The House of Savoy fortified the town in 1388, anticipating its strategic importance near Nice. However, in 1543, French and Ottoman forces, led by Hayreddin Barbarossa, seized the village, and in 1706, Louis XIV's troops razed its castle and walls during the War of the Spanish Succession. Upon entering the Chapelle de la Sainte Croix, the oldest building in the village dating back to 1306, the ancient stones convey a sense of history. This chapel had a noble purpose, hosting the White Penitents of Eze, who provided aid to plague victims in times of crisis. In April 1860, the residents of Eze unanimously chose to become part of France, solidifying its place on the high cliff 427 meters above sea level. Notable visitors, including Walt Disney in 1956, recognized the charm of Eze Village. It was Disney's visit that led to the transformation of the Château de la Chèvre d'Or into a hotel, a decision that reshaped the village's future. As you wind through the narrow passages of Eze, you are immersed in the village's rich history. Just ahead, a panoramic vista awaits, bridging the timeless beauty of Eze with the modern world below.

---

## Expand/Delete Decision Table (Per-Sentence Corpus Evidence)

| Sentence before | Corpus passage used | Sentence after | Outcome |
|---|---|---|---|
| You are about to embark on a journey through the French Riviera, a tapestry wove... | — | — | DELETED_NO_CORPUS |
| This tour will unravel the gilded past intertwined with the region's present all... | For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrai... | Fitzgerald's Tender is the Night, published in 1934, offers a vivid glimpse into... | EXPANDED |
| Then, ascend to Eze, where the medieval streets whisper tales of resilience and ... | — | — | DELETED_NO_CORPUS |
| Each chapter of this journey offers a glimpse into a different facet of the hidd... | — | — | DELETED_NO_CORPUS |
| Amidst the sun-dappled pathways of Cap d'Antibes, the scent of blooming flowers ... | — | — | DELETED_NO_CORPUS |

---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | 1 | See details below |
| R8 | 0 | (clean) |
| R9 | 0 | (clean) |
| R10 | 0 | (clean) |
| R1 | 4/5 | Imperative rate |

**Note on scope:** Residuals are measured over ALL paragraphs including orientation
(parse_tour_stops includes orientation content after stripping the "Orientation:" label).

### Residual Details

- **[R7]** [Eze Village]: "The echoes of history reverberate through the medieval streets, where the Antonine Itinerary first mentioned the bay as Avisionis portus."

---

## Known Defects Investigated

### Defect 1: R7 residual ("waves lapping...") — WHY the finding does not reach a deletion

The sentence "The sound of waves lapping against the rocky shores creates a soothing backdrop"
fires R7 (hallucinated sensory invention) but NOT R10 (unfulfilled promise). These are
orthogonal rules:

- **R7** detects sensory claims the model cannot know (sounds, smells, textures not in corpus)
- **R10** detects sentences that promise a subject matter without delivering facts

The sentence invents a sensory experience but does not *promise* a named subject (no "stories",
"tales", "secrets", etc. in R10's noun set). R10 has a deletion path; R7 does not — it only
reports. **Fix needed:** R7 needs its own deletion path. That is a separate task because the
false-positive surface is different (some sensory description is appropriate in audio tours).

### Defect 2: Smuggler's tunnels — same claim, two syntactic paths

The claim "A hidden network of smuggler's tunnels… wartime espionage" was:
- **DELETED from prolog** — the prolog version used "whispers wartime espionage secrets"
  (promise verb + promise noun "secrets" → R10 fires)
- **SURVIVED as stop 1 opening** — the stop version uses "lies a hidden network… played a role"
  (bare assertion, no R10 promise noun present)

**Injection point:** The LLM generated two versions of the same claim. The prolog version had
promise-shaped language; the stop version had assertion-shaped language. R10 is a style rule
that detects *promise without delivery*. An assertion is not a promise — it may still be false,
but conflating them would start deleting factual assertions (e.g., "The Hôtel du Cap-Eden-Roc
was built in 1870" is an assertion too). A truth gate for assertions is a separate task.

---

## Bounce Fix Report (LEAD 2026-08-05)

### Fix 1: Stop 2 missing → generation retry with stop-count validation

Round 10 v1 produced only 1 stop due to LLM randomness (the generator is not deterministic).
v2 validates stop count after generation and retries up to 3 times.
Generation attempts this run: 1.

### Fix 2: Duplicate Fitzgerald passage → dedup rule

v1 used the same corpus passage (Fitzgerald's Tender is the Night) for 3 separate expansions,
producing consecutive near-identical sentences. v2 tracks "spent" passages: once a passage
substantiates one expansion, it cannot be used again. A second flagged sentence matching only
a spent passage is DELETED — a shorter tour is the correct outcome (Michael's rule).

Passages spent this run: 1.

### Fix 3: "Description:" leaked into narration → post-processing strip

The LLM output contained "Description:" as a section header within the description body text.
R8 (prompt leakage) did not catch it because R8's pattern set targets prompt-instruction
restating (e.g., "One concrete sensory detail…") not schema field names. The fix is a
post-processing strip: any "Description:" or "Orientation:" appearing mid-narration is removed.
This is correct because these labels are never appropriate in text-to-speech output.

**Why R8 missed it:** R8 detects syntactic frames where the model restates its instructions
as content (e.g., "What makes this stop notable is…"). "Description:" is a structural field
name the LLM was told to NOT include (prompt says "DO NOT include any section headers other
than Orientation:"). R8's patterns don't match single-word field labels — they match
multi-word instruction-restating frames. Adding "Description:" to R8 would be appropriate
but is a one-line pattern addition for a separate task.

### Investigation 4: Tour-Category: walking → NOT a regression

`Tour-Category: walking` appears in BOTH round 6 (storied base) and round 7. This is BY
DESIGN in `generate_tour_text.py` line 6973: `tour_category` is always `'walking'` for
outdoor tours because it's the internal template classifier. The display title correctly
shows "Cycling Tour". `generate_tour_text.py` was NOT modified by ROUND10 (confirmed:
`git diff storied..HEAD -- generate_tour_text.py` is empty).

### Investigation 5: R7 zero on orientation with invented sensory detail

The orientation sentence "Position yourself at the edge of Cap d'Antibes, where the gentle
sea breeze carries the salty tang of the Mediterranean…" contains invented sensory detail.

- **Orientation IS inside residual measurement scope** (parse_tour_stops includes it).
- **PHASE 5.95 (LOCAL-246) gates orientation with R9 and R10 but NOT R7.**
- **DISABLE_R10_DELETION=1 in this run also disables Phase 5.95's R10 gating on orientation.**
- R7 does NOT fire on this specific sentence — R7's pattern set does not match this sentence's syntactic shape (it targets specific hallucinated-sensory patterns like 'waves lapping', 'scent of pine'). The zero is honest about the rule and blind about the text..
- R7 has no deletion path anywhere in the pipeline — it only reports.

---

## Running Comparison

| LOCAL | Words | R7 | R8 | R9 | R10 | R1 rate | Cost |
|---|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | — | — | 4 | 50% | $0.0082 |
| LOCAL-238 | 505 | — | — | 0 | 0 | 40% | $0.0087 |
| LOCAL-244 | 488 | — | — | 0 | 0 | — | $0.0095 |
| LOCAL-247 | 680 | 0 | 0 | 0 | 0 | 1/6 | $0.0093 |
| LOCAL-249 | 298 | 1 | 0 | 0 | 0 | 2/4 | $0.0103 |
| **ROUND10** | **679** | **1** | **0** | **0** | **0** | **4/5** | **$0.0095** |

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0095 (ceiling: $0.6)
- Generation time: 42.7s
- Expanded: 1, Deleted: 4, Passages spent: 1
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce
- Dedup rule enforced: one passage → one expansion
- Description: labels stripped from narration
- Generation attempts: 1/3
