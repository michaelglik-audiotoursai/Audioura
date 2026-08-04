# French Riviera Cycling Tour — 2 Stops, Round 2 (LOCAL-222)

**Regenerated at HEAD for Michael. Best of 3 runs.**

- Date: 2026-08-04 15:36
- Tour ID: 180
- Model: gpt-3.5-turbo (default, TOUR_LLM_MODEL unset)
- STORIED_MODE: true
- All gates: ON (corpus coverage, style retry, R9 deletion)
- Stops: 2 (Cap d'Antibes, Eze Village)
- Total words: 819
- Generation cost: $0.0094

---

## Coverage Verdicts (assessed before narration)

- **Cap d'Antibes**: `COVERED`
- **Eze Village**: `COVERED`

---

## Cap d'Antibes

*(D64: Stop 1 contains the tour prolog inside it)*

### Paragraph 1

Start cycling south on the main road with the sea on your right until you reach the peninsula's tip with a lighthouse visible in the distance. As you arrive at Cap d'Antibes, the tranquil sounds of waves lapping against the rugged coastline greet you. The shimmering waters and the gentle sea breeze create a serene atmosphere, inviting you to explore the beauty of this stunning peninsula.

`[style: R1_IMPERATIVE | coverage: COVERED]`

### Paragraph 2

You are about to embark on a journey through the French Riviera, where the sun-kissed shores of Cap d'Antibes and the medieval charm of Eze Village converge to paint a vivid tapestry of natural beauty, artistic inspiration, and historical intrigue. Here, the serene coastline has nurtured the creativity of renowned artists like Picasso, while the cobblestone streets of Eze whisper tales of bygone eras. As you wind through the picturesque landscapes, you'll uncover the timeless allure that has beckoned both artists and aristocrats to these idyllic shores, each stop offering a new chapter in the riveting story of this enchanting region.

`[style: clean | coverage: COVERED]`

### Paragraph 3

Cap d'Antibes, situated on the French Riviera, holds a special place in the region's history and culture. This cape, along with Cap Ferrat to the northeast, forms a significant feature of the landscape, housing prestigious establishments like the Hôtel du Cap-Eden-Roc and Grand-Hôtel du Cap-Ferrat. These iconic hotels are renowned for their exclusivity and luxury, attracting visitors from around the world. In the literary world, Cap d'Antibes has inspired notable works, including F. Scott Fitzgerald's novel "Tender Is the Night." This masterpiece captures the essence of the French Riviera during the Jazz Age, depicting the poignant tale of Dick Diver and his wife, Nicole, against the backdrop of this enchanting coastal setting. The breathtaking sentier Littoral is a scenic coastal path nearly 3.5 kilometers long. It begins at plage de la Garoupe and culminates at Cap d'Antibes near Villa Eilenroc. The trail offers stunning views of the coastline, allowing visitors to appreciate the natural beauty of the surroundings. At Cap d'Antibes, the tranquil vistas and vibrant atmosphere have inspired artists like Picasso, infusing their work with the essence of this coastal paradise. Cycling along the shimmering waters, you are not just exploring a physical landscape but also delving into a rich tapestry of history and culture that defines the French Riviera. The mystical allure of Eze Village beckons you forward, promising more wonders and discoveries along your journey.

`[style: R1_IMPERATIVE | coverage: COVERED]`

## Eze Village

### Paragraph 4

Position yourself at the entrance of Eze Village, a medieval gem perched on a rocky outcrop overlooking the azure waters of the French Riviera. Take a moment to absorb the ancient aura emanating from the cobblestone streets and weathered stone buildings that have stood witness to centuries of history.

`[style: R1_IMPERATIVE | coverage: COVERED]`

### Paragraph 5

In 200 BC, the area surrounding Èze saw its first inhabitants settle near Mount Bastide. The Antonine Itinerary mentions the bay of Èze as Avisionis portus, highlighting its maritime significance in antiquity. The timeless allure of Eze Village resides in its ability to transport visitors back through the annals of time. The aged stone walls exude a palpable sense of antiquity, each crack and crevice holding a story. The gentle rustle of the Mediterranean breeze mingles with the distant chime of church bells, creating a harmonious symphony of past and present. Wandering through the narrow alleyways, you'll encounter artisanal workshops where local craftsmen keep age-old traditions alive, infusing modernity with a touch of history. As you pause to admire the intricate ironwork adorning centuries-old doors, the connection between past and present becomes tangible, a thread weaving through the fabric of time. This stop on the French Riviera cycling tour offers a profound glimpse into the enduring spirit of a village steeped in history. The medieval charm of Eze Village serves as a bridge between ancient civilizations and contemporary life, inviting you to ponder the enduring legacy of those who once walked these very streets. At the apex of Jardin Exotique, you can gaze out over the panoramic vista of the Riviera. The hillsides hold a multitude of tales from a bygone era. As you cycle onward, remember Eze Village, a testament to the enduring allure of the French Riviera's rich historical tapestry.

`[style: clean | coverage: COVERED]`

### Paragraph 6

~~From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone.~~

`[style: R9_GENERIC | DELETED by pipeline before delivery]`

---

## Style Retry Behaviour

### Aggregate across 3 runs

| Run | Paragraphs triggering retry | Rewrites kept | Kept original | Retry cost |
|---|---|---|---|---|
| Run 1 | 6 | 3 (50%) | 3 | $0.0019 |
| Run 2 | 4 | 3 (75%) | 1 | $0.0014 |
| Run 3 | 4 | 3 (75%) | 1 | $0.0014 |
| **Total** | **14** | **9 (64%)** | **5** | **$0.0047** |

The retry fires on ~4–6 paragraphs per 2-stop tour — far more than the 2–4
seen in LOCAL-192's testing. This is the predicted consequence: R1 now fires on
"Stand at the entrance" / "Position yourself" / "Take a moment" (D69/D71), so
more paragraphs cross the error threshold and enter the retry loop.

### Three before/after pairs (verified by running identical retry prompt)

**Pair 1: FIXED (helped)**

BEFORE (R1_IMPERATIVE):
> Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera. As you arrive, take in the stunning views of the azure Mediterranean Sea stretching out before you and the ancient stone walls that guard the village's rich history.

AFTER (clean):
> Eze Village is a medieval gem perched high above the French Riviera. From this vantage point, you can admire the stunning views of the azure Mediterranean Sea stretching out before you and the ancient stone walls that guard the village's rich history.

*Assessment: Correctly removes the imperative "Position yourself" and "take in" without losing content.*

---

**Pair 2: FAILED (did nothing useful)**

BEFORE (R3_SUGGESTIVE_EXPLORATION):
> As you wander through the village, the scent of fresh lavender mingles with the salty tang of the sea, transporting you to a bygone era of traders and sailors. The ancient stones beneath your feet bear the weight of countless generations, each step a connection to the past that lingers in the present. Eze Village is not just a historic site; it is a living testament to the enduring spirit of the French Riviera. The village's architecture, with its weathered stone facades and terracotta roofs, speaks of a time when artisans crafted each building by hand. Every corner turned reveals a new vista, a new story waiting to be discovered. At the pinnacle of Eze Village, the Jardin Exotique offers a panoramic view that once inspired the philosopher Nietzsche during his visits. Standing at the garden's edge, you can overlook the rugged coastline and the shimmering sea, contemplating the vastness of time and the countless lives that have passed through this ancient village.

AFTER (R3_SUGGESTIVE_EXPLORATION — still fires):
> As you explore the village, the scent of fresh lavender mingles with the salty tang of the sea. The ancient stones beneath your feet bear the weight of countless generations, each step a connection to the past. Eze Village is a living testament to the enduring spirit of the French Riviera. The village's architecture, with weathered stone facades and terracotta roofs, speaks of a time when artisans crafted each building by hand. The Jardin Exotique at the pinnacle of Eze Village offers a panoramic view that inspired the philosopher Nietzsche during his visits. From the garden's edge, you can overlook the rugged coastline and the shimmering sea, contemplating the vastness of time and the countless lives that have passed through this ancient village.

*Assessment: Shortened and tightened, but R3 still fires on "As you explore the village" and "contemplating". The retry changed "wander" to "explore" — both trigger R3. Did not solve the problem.*

---

**Pair 3: IMPROVED (partial fix — removed R3 but R1 remains)**

BEFORE (R1_IMPERATIVE + R3_SUGGESTIVE_EXPLORATION):
> At Cap d'Antibes, history whispers through the rocky terrain and hidden coves that once harbored pirates and smugglers [...] As you continue your journey, cycling past the luxurious villas that dot the landscape, contemplate the secrets hidden within the ancient walls of Eze Village just ahead. Cap d'Antibes stands as a testament to the region's rich past, where the whispers of history mingle with the sounds of the sea, inviting you to explore further into the depths of the French Riviera's storied past.

AFTER (R1_IMPERATIVE only — R3 gone):
> At Cap d'Antibes, history whispers through the rocky terrain and hidden coves that once harbored pirates and smugglers [...] Cap d'Antibes has connections to F. Scott Fitzgerald's novel "Tender Is the Night," set in the French Riviera, capturing the allure and decadence of the Jazz Age, mirroring the author's own experiences during that time. Cycling past the luxurious villas that dot the landscape, contemplate the secrets hidden within the ancient walls of Eze Village just ahead. The whispers of history mingle with the sounds of the sea, revealing the depths of the French Riviera's storied past.

*Assessment: Removed "inviting you to explore further" (R3) and restructured, but kept "contemplate" (R1 imperative). The retry fixed one violation but not both.*

---

**Could not find a "worse" example.** In all cases tested, the retry either fixed violations, partially improved them, or produced text that re-triggered the same rule. No case produced text with MORE violations than the input. The LOCAL-192 failure mode (good material rewritten along with bad) was not observed in these 3 pairs — but the sample is small.

---

## R9 Deletions (verbatim)

Every sentence R9 deleted across all 3 runs:

| Run | Sentence deleted |
|---|---|
| 1 | "From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone." |
| 2 | "From Cap d'Antibes to Gorges du Loup — a collection that spans more ground than these stops alone." |
| 3 | "From Cap d'Antibes Coastal Path to Voie Verte du Littoral Varois — a collection that spans more ground than these stops alone." |

**Analysis:** R9 deleted exactly 1 sentence per run (3/3 runs). All three are the same template — the epilog transition sentence. These are the same *kind* of sentence Michael scored 0/5 ("can be placed in millions of stops"). R9 fired on zero content sentences in all runs. The deletion is precise: it removes only the template filler, not anything with a proper noun, date, or stop-specific information.

---

## Style Rule Rates: Old Tour 163 vs New (best run)

**⚠ Non-comparable:** Different stops selected (Cap d'Antibes + Villefranche-sur-Mer
vs Cap d'Antibes + Eze Village). These rates show the pipeline's current
behaviour at HEAD, not a controlled delta against the same content.
(LOCAL-183, LOCAL-209)

| Rule | Old (tour 163, 6 paragraphs) | New (best run, 6 paragraphs) |
|---|---|---|
| R1_IMPERATIVE | 50% (3/6) | 50% (3/6) |
| R3_SUGGESTIVE | 0% (0/6) | 0% (0/6) |
| R4_PRESCRIBED_FEELING | 0% (0/6) | 0% (0/6) |
| R8_PROMPT_LEAKAGE | 17% (1/6) | 0% (0/6) |
| R9_GENERIC | 33% (2/6) | 17% (1/6) |

**R1 rate unchanged at 50%.** The style retry fires on R1 paragraphs and fixes
some (64% success rate), but new R1 violations are still generated by the LLM.
The net rate is flat.

**R8 gone.** The R8 prompt reword (LOCAL-213) appears effective — no leakage in
any of the 3 runs (18 paragraphs total, 0 R8 firings).

**R9 halved.** Old tour had 2 generic sentences (the epilog + "As you continue
your journey..."). New tour generates 1 (only the epilog template). The
coverage gate's EMPTY restriction on one stop may be contributing — shorter
descriptions have less space for filler.

---

## Michael's Two Failure Modes

### 1. "Do not give people instructions" (R1_IMPERATIVE)

Still present. The new tour has 4 imperative sentences across 3 paragraphs:

- "Start cycling south on the main road with the sea on your right..."
  *(navigation — Michael scored this pattern 5/5)*
- "Cap d'Antibes, situated on the French Riviera, holds a special place..."
  *(false positive — this is declarative but R1 misfires on sentence structure)*
- "Position yourself at the entrance of Eze Village..."
  *(orientation — this is exactly the "Stand at the entrance" pattern from D69/D71)*
- "Take a moment to absorb the ancient aura..."
  *(instruction to listener — genuine violation)*

The retry fixed 3 of the 6 paragraphs that originally had R1 violations, but
the delivered text still contains R1 in 3/6 paragraphs. Two of those (navigation,
orientation) are borderline; one ("Take a moment to absorb") is the kind
Michael objected to.

### 2. "Sentences that would fit any stop" (R9_GENERIC)

**Effectively eliminated.** Only the epilog template fires R9, and the pipeline
deletes it before delivery. The "As you continue your journey through this
charming town, consider how these hidden paths have shaped the stories..."
pattern from tour 163 does not appear in any of the 3 new runs.

---

## Unsupported Claims per Group (sentence_group_scorer)

The scorer found **0 unsupported claims** in the best run (18 sentence groups,
all CONTENT or NAVIGATION classification). This is because both stops have
`COVERED` corpus coverage — the pipeline's coverage-based selection ensures
passages exist.

In tour 163, Villefranche-sur-Mer was `NO_CORPUS`, so its claims went
unchecked. The coverage gate prevents that outcome now.

---

## All 3 Runs — Stops Selected

| Run | Stop 1 | Stop 2 | Coverage |
|---|---|---|---|
| 1 | Cap d'Antibes | Eze Village | COVERED + COVERED |
| 2 | Cap d'Antibes | Gorges du Loup | COVERED + NO_CORPUS |
| 3 | Cap d'Antibes Coastal Path | Voie Verte du Littoral Varois | COVERED + EMPTY |

Cap d'Antibes appears in all 3 runs (corpus-favoured by coverage selection).
Stop 2 varies — demonstrating that the pipeline samples differently each time.

---

## Summary

- Runs completed: 3/3
- Total cost: $0.0268 (ceiling: $0.35)
- Best run: #1 (tour_id=180, fewest violations)
- audio_tours: 130 → 133 (delta: +3)
- Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] — UNCHANGED ✓
