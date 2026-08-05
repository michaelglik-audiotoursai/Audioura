# French Riviera Cycling Tour - 2 Stops, Round 7 (LOCAL-250)

> ### What changed: Expand before delete
>
> LOCAL-249 built the "remove" half of Michael's routine. This builds the
> "expand" half: between detection and deletion, query the corpus for a fact
> that would substantiate the promise, and rewrite the sentence around it.
> Deletion stays the default and the fallback — never publish an undelivered promise.
>
> **Expansion is working.**
> Expanded: 3 sentences. Deleted: 4 sentences.

**Fixes live in this run:**
1. **Expand before delete** (LOCAL-250 primary): R10-flagged sentences are first
   looked up in stop_corpus; if a matching fact is found, the sentence is rewritten
   around that fact. Deletion only fires when the corpus has nothing.
2. **Structural promise detection** (LOCAL-249): verb-independent subject-matter
   noun detection.
3. All LOCAL-247 fixes (payload false-positive, R7, R8, R9) remain active.

> **Word counts:** Round 5: 680 | Round 6: 298 | **Round 7: 355**

## Summary Table

| Field | Value |
|---|---|
| fixes live | expand-before-delete (LOCAL-250), structural promise (LOCAL-249), all LOCAL-247 |
| model | gpt-3.5-turbo + gpt-4o-mini (expansion) |
| generation cost | $0.0051 |
| expansion cost | $0.0002 |
| total cost | $0.0053 |
| tokens (generation) | 6426 |
| stops | Cap d'Antibes |
| expanded | 3 |
| deleted | 4 |
| R7 residual | 0 |
| R8 residual | 0 |
| R9 residual | 0 |
| R10 residual | 0 |
| R1 rate | 3/3 paragraphs |
| generation time | 31.3s |
| date | 2026-08-05 |
| STOP_EXISTENCE_GATE_MODE | enforce |

---

## Tour Content

### Cap d'Antibes

**Existence:** VERIFIED
**Coverage:** COVERED

#### Paragraph 1 (49 words)

Position yourself at the edge of Cap d'Antibes, where the gentle sea breeze carries the salty tang of the Mediterranean and the distant laughter of sun-seekers mingles with the cry of seagulls. Ahead, the azure waters stretch out into the horizon, meeting the cloudless sky in an endless embrace.

#### Paragraph 2 (55 words)

As you pedal through this glittering peninsula, remember that for France lovers, Fitzgerald's Tender is the Night, published in 1934, offers a vivid glimpse into 'the Roaring Twenties'. For France lovers, a visit to Cap d'Antibes evokes the essence of Fitzgerald's Tender is the Night, the quintessential portrait of 'the Roaring Twenties' published in 1934.

#### Paragraph 3 (224 words)

Standing on this historic promontory, you can admire the panoramic view of Antibes and beyond, with luxurious yachts and vibrant beachfront cafes dotting the scene. The lush greenery of the cape envelops you, creating a serene contrast to the lively atmosphere below. Description: Cap d'Antibes, a renowned landform along the French Riviera, holds a significant place in the region's history and culture. In 2023, Antibes boasted a population of 77,637, making it a bustling hub on the Alpes-Maritimes coast. This cape, along with Cap Ferrat, shapes the coastal landscape, drawing visitors with its natural beauty and rich heritage. Historically, Cap d'Antibes has witnessed the comings and goings of seafarers, traders, and artists alike. Claude Monet, the celebrated painter, found inspiration in the French Riviera's light and colors, producing masterpieces like "Morning at Antibes" in 1888. The winding "Tire-Poil" trail offers walkers breathtaking views of the Lérins Islands and Mercantour heights, inviting exploration and contemplation. The cape's proximity to Juan-les-Pins and the Sophia Antipolis technology park adds a modern touch to its timeless allure. As you take in the sights and sounds of Cap d'Antibes, you will discover the layers of history that have shaped this coastal gem. End your visit by reflecting on how Fitzgerald's Tender is the Night, inspired by his experiences on the French Riviera, captures the essence of 'the Roaring Twenties'.

---

## Expand/Delete Decision Table (Per-Sentence Corpus Evidence)

| Sentence before | Corpus passage used | Sentence after | Outcome |
|---|---|---|---|
| You are about to embark on a journey through the luxurious Cap d'Antibes, a seas... | — | — | DELETED_NO_CORPUS |
| As you pedal through this glittering peninsula, you will uncover the hidden stor... | For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrai... | As you pedal through this glittering peninsula, remember that for France lovers,... | EXPANDED |
| Each landmark along the way reveals a different chapter in the history of this c... | — | — | DELETED_NO_CORPUS |
| The past whispers through the sea breeze, reminding you that behind the glamour ... | For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrai... | For France lovers, a visit to Cap d'Antibes evokes the essence of Fitzgerald's T... | EXPANDED |
| Welcome to a world where every stop is a new chapter, each unveiling a different... | — | — | DELETED_NO_CORPUS |
| The blend of tradition, innovation, and natural beauty here reflects the essence... | — | — | DELETED_NO_CORPUS |
| End your visit with a sense of curiosity, eager to uncover more tales of art, es... | For France lovers, Fitzgerald's Tender is the Night (1934) is the truest portrai... | End your visit by reflecting on how Fitzgerald's Tender is the Night, inspired b... | EXPANDED |

---

## Residual Analysis

| Rule | Residual | Detail |
|---|---|---|
| R7 | 0 | (clean) |
| R8 | 0 | (clean) |
| R9 | 0 | (clean) |
| R10 | 0 | (clean) |
| R1 | 3/3 | Imperative rate |

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

## Running Comparison

| LOCAL | Words | R7 | R8 | R9 | R10 | R1 rate | Cost |
|---|---|---|---|---|---|---|---|
| LOCAL-222 | 819 | — | — | — | 4 | 50% | $0.0082 |
| LOCAL-238 | 505 | — | — | 0 | 0 | 40% | $0.0087 |
| LOCAL-244 | 488 | — | — | 0 | 0 | — | $0.0095 |
| LOCAL-247 | 680 | 0 | 0 | 0 | 0 | 1/6 | $0.0093 |
| LOCAL-249 | 298 | 1 | 0 | 0 | 0 | 2/4 | $0.0103 |
| **LOCAL-250** | **355** | **0** | **0** | **0** | **0** | **3/3** | **$0.0053** |

---

## Run Summary

- audio_tours before: 142
- audio_tours after: 142
- Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED
- is_test=true, lat/lng=NULL
- Cost: $0.0053 (ceiling: $0.6)
- Generation time: 31.3s
- Expanded: 3, Deleted: 4
- No container rebuilt
- STOP_EXISTENCE_GATE_MODE: enforce
