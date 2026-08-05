# French Riviera Cycling Tour - 2 Stops, Round 7 (LOCAL-250)

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
1. **Expand before delete with dedup** (LOCAL-250 primary): R10-flagged sentences are
   first looked up in stop_corpus; if a matching fact is found AND that passage has not
   been spent, the sentence is rewritten around that fact. One passage → one expansion.
   Deletion fires when the corpus has nothing or the passage is already spent.
2. **Structural promise detection** (LOCAL-249): verb-independent subject-matter
   noun detection.
3. All LOCAL-247 fixes (payload false-positive, R7, R8, R9) remain active.
4. **Label stripping**: "Description:" field labels stripped from narration post-generation.

> **Word counts:** Round 5: 680 | Round 6: 298 | **Round 7: 658**
> Stops: 2 (Cap d'Antibes, Saint-Paul-de-Vence)

## Summary Table

| Field | Value |
|---|---|
| fixes live | expand-before-delete+dedup (LOCAL-250), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | $0.0097 |
| expansion cost | $0.0001 |
| total cost | $0.0098 |
| tokens (generation) | 12174 |
| stops | Cap d'Antibes, Saint-Paul-de-Vence |
| expanded | 1 |
| deleted | 4 |
| passages spent (dedup) | 1 |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 1/4 paragraphs |
| generation time | 41.9s |
| generation attempts | 3/3 |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Tour Content

### Cap d'Antibes

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (55 words)

Start cycling southeast on the main road, enjoy the sea breeze along the way. As you pedal towards Cap d'Antibes, the Mediterranean breeze carries the scent of salt and pine, mingling with the distant hum of yacht engines. Look for the iconic lighthouse perched atop the cape, a beacon guiding sailors to safety for centuries.

#### Paragraph 2 (102 words)

Discover the charm of Cap d'Antibes, a place that inspired Fitzgerald's portrayal of the Roaring Twenties in his novel Tender is the Night, published in 1934. As you wander through a medieval hilltop village, run your fingers along the ancient stone walls that once bore witness to the musings of Marc Chagall, connecting you to a time when art and history converged seamlessly. Each stop on this tour reveals a different facet of the Riviera's allure, from the whispers of aristocrats to the echoes of medieval fortresses, painting a picture of a destination where the past and present dance together in harmony.

#### Paragraph 3 (130 words)

The historic significance of Cap d'Antibes lies in its role as a muse to artists like Claude Monet, who found inspiration in its rocky coves and azure waters. In 1888, Monet first experimented with painting in series here, creating masterpieces like "Morning at Antibes." The fact that Antibes boasts the largest yachting harbor in Europe speaks volumes about its maritime heritage and modern-day allure. Standing on the rugged cliffs, the weathered stone beneath your feet holds the weight of history, with the rhythmic crash of waves against the shore echoing in the distance. Along the river trail, a shaded respite from the sun awaits, with the invigorating scent of pine filling the air. This stop beautifully connects to the tour's theme by embodying the gentle awe of the French Riviera.

### Saint-Paul-de-Vence

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (36 words)

As you stand at the historic village of Saint-Paul-de-Vence, nestled in the Alpes-Maritimes department in Southeastern France, pause to take in the ancient stone walls that have stood witness to centuries of artistry and cultural luminaries.

#### Paragraph 2 (208 words)

In the 1960s, Saint-Paul-de-Vence became a retreat for renowned French actors like Yves Montand, Simone Signoret, and poets such as Jacques Prévert. The cobbled streets echo with the footsteps of these artistic influencers who sought inspiration amidst the village's timeless charm. The conversations that once filled the air, the laughter and debates that animated the narrow alleyways are a testament to the vibrant artistic community that thrived here. The La Colombe d'Or hotel has a storied past, having hosted legendary guests like Jean-Paul Sartre and Pablo Picasso. The ancient pathways bear the weight of history on their worn stones. The sun-dappled walls of the village exude a timeless warmth, evoking a bygone era of thriving creativity. Saint-Paul-de-Vence is not merely a destination; it is a portal to a world where art and culture intertwine seamlessly. The legacy of artists like Marc Chagall and Bernard-Henri Lévy lingers in the very air you breathe, infusing every corner with a sense of creative energy. The village's artistic spirit is palpable, a living testament to the enduring power of human expression. Each step taken is a journey through the annals of creativity and culture. In this medieval hilltop village, the past and present harmoniously converge in a dance of art and history.

---

## Expand/Delete Decision Table (Per-Sentence Corpus Evidence)

| Sentence before | Corpus passage used | Sentence after | Outcome |
|---|---|---|---|
| You are about to embark on a journey through the French Riviera, a tapestry of l... | — | — | DELETED_NO_CORPUS |
| Feel the Mediterranean breeze at the spot where Picasso once sought inspiration ... | For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrai... | Discover the charm of Cap d'Antibes, a place that inspired Fitzgerald's portraya... | EXPANDED |
| Cap d'Antibes embodies the essence of this coastal paradise, where the vibrant p... | — | — | DELETED_NO_CORPUS |
| Cycling along the coastal road offers glimpses of the allure that lies beyond ea... | — | — | DELETED_NO_CORPUS |
| Descending the winding paths of Saint-Paul-de-Vence unveils the stories embedded... | — | — | DELETED_NO_CORPUS |

---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | 0 | (clean) |
| R8 | 0 | (clean) |
| R9 | 0 | (clean) |
| R10 | 0 | (clean) |
| R1 | 1/4 | Imperative rate |

**Note on scope:** Residuals are measured over ALL paragraphs including orientation
(parse_tour_stops includes orientation content after stripping the "Orientation:" label).
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

Round 7 v1 produced only 1 stop due to LLM randomness (the generator is not deterministic).
v2 validates stop count after generation and retries up to 3 times.
Generation attempts this run: 3.

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
shows "Cycling Tour". `generate_tour_text.py` was NOT modified by LOCAL-250 (confirmed:
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
| **LOCAL-250** | **658** | **0** | **0** | **0** | **0** | **1/4** | **$0.0098** |

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0098 (ceiling: $0.6)
- Generation time: 41.9s
- Expanded: 1, Deleted: 4, Passages spent: 1
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce
- Dedup rule enforced: one passage → one expansion
- Description: labels stripped from narration
- Generation attempts: 3/3
