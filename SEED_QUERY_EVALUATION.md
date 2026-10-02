# Seed queries — results and evaluation

**37 queries · $0.0370 · 37s** — one query per seed, all three stops of `STEP0_BASELINE_20260820_1459.txt`.

Budget note: you authorised $13. Serper is $0.001/query, so the whole experiment cost **3.7 cents**. Cost is not a constraint at this scale and we can run far larger sweeps without approval.

## Headline: the ranking inverted

| stop | agents (D500) | anchored seeds | eventful | active | inert |
|---|---|---|---|---|---|
| Le Lézard aux plumes d’or (The Liz | 3/3 | 8 of 16 | **2** | 6 | 8 |
| Au Soleil du Plafond | 1/3 | 1 of 12 | **9** | 0 | 3 |
| Moses and Monotheism | 1/3 | 4 of 9 | **2** | 3 | 4 |

**Au Soleil du Plafond — the stop I called weakest — produced the most eventful material of the three, by a wide margin.** It has one agent in its matrix, no object record, and 1 anchored seed out of 12. Every static measurement said it was the poorest. Retrieval says the opposite.

That matters because every instrument we have built for *predicting* which stop can carry a story — worthiness score, agent count, anchored-seed ratio — pointed the wrong way here. They measure **what we already know about the stop**, and retrieval measures **what the world knows**. Those are different, and only the second one produces stories.

## Why Au Soleil won

Because it has a real event in it, and we never knew:

> *Gris died in 1927, having finished only half of the intended [work].*  
> *When the artist died the following year, the lithographs and text remained unfinished.*  
> *It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans.*  
> *It was not until 1955 when the book was published by Tériade.*

A man died with the work half-finished and his collaborator published a reduced version twenty-eight years later. That is a story with a change, an agent and something at stake — it satisfies your bar — and **none of it is in the baseline tour**, which says only that the project was "posthumously realized".

It also supplies a name the matrix never had: **Tériade**, the publisher. The `sponsor` role was empty for this stop.

## What the two seed classes actually bought

- **anchored**: 13 seeds — eventful 1 (7%), active 7, inert 5
- **evaluative**: 24 seeds — eventful 12 (50%), active 2, inert 10

**The evaluative seeds outperformed the anchored ones**, which I did not expect and which is worth keeping. My reasoning was that anchored seeds are checkable and evaluative ones are just our adjectives. True — but the evaluative query does not search the adjective, it searches for the EVENT that would justify it, and that is a better-shaped question than "confirm this name appears". Verification queries return catalogue entries; event queries return narrative.

## Failures worth seeing

**1. Two queries retrieved the wrong subject entirely.**

> *Dora Szampanier, Etching of destroyed synagogue — Drohobisz, Ukraine.*

`Juan Gris "Au Soleil du Plafond" destroyed` — the event term dominated and pulled an unrelated work. Counted as `eventful` by the instrument, because something certainly happens in it. **The kind classifier does not check relevance**, so a topically-wrong but dramatic result scores as success. Two of Au Soleil's nine eventful verdicts are this.

**2. One query is nonsense and I built it.**

`Freud "Le Lézard aux plumes d'or" Joan Miró` — Freud has nothing to do with the Miró book. The seed came from a sentence in stop 1's ORIENTATION that previews stop 3. Orientation text is tour scaffolding and should not produce seeds; `_PACKAGING` filters the closing recap but not the preview.

**3. Duplicate queries.** Several seeds in a stop reduce to the same query string — stop 2 issued `Juan Gris "Au Soleil du Plafond" unfinished` three times. About a quarter of the 37 were redundant. Harmless at 3.7 cents, wasteful at scale, and it means the effective sample is smaller than 37.

**4. The instrument was broken on the first run and reported 37/37 inert.** `classify_material` takes a LIST of passages; I passed a joined string, so it scanned character by character and every verdict came back inert with `sentences == chars`. Caught by running a text whose answer I already knew (D242 standing check 3) before believing a uniform zero — the same shape as D423, where a false zero nearly became a published finding.

## What I would conclude

1. **Seeds work.** 13 of 37 queries returned eventful material and several carry the story the tour is missing. That is a far better yield than step 3d's replenishment round, which returned 0 eventful on three consecutive runs.
2. **Predicting story-worthiness from the matrix does not work.** The matrix-based instruments ranked the stops exactly backwards. Step 2's worthiness score should not be trusted as a cost lever until this is understood.
3. **Relevance gating is the missing piece.** Event terms pull dramatic irrelevance. Any production use needs the retrieved sentence checked against the stop's own subject before it counts.
4. **Orientation and preview text must not produce seeds.**

## Per-seed detail

### Le Lézard aux plumes d’or (The Lizard with Golden Feathers)

| seed | class | query | kind | best retrieved sentence |
|---|---|---|---|---|
| 2.1 `revolutionized the book as an art form` | eval | `Joan Miró "Le Lézard aux plumes d’or" commissi` | **inert** | — |
| 2.2 `focusing on the livre d'artiste` | eval | `Joan Miró "Le Lézard aux plumes d’or" dispute` | **inert** | — |
| 4.1 `showcasing how artists express these c` | eval | `Joan Miró "Le Lézard aux plumes d’or" delayed` | **inert** | — |
| 5.1 `Broder's pivotal decision` | anch | `Broder "Le Lézard aux plumes d’or" Joan Miró` | **active** | Printed by Mourlot, Paris; published by Louis Broder, Paris. |
| 5.2 `allowing the artist to blend visual an` | eval | `Joan Miró "Le Lézard aux plumes d’or" commissi` | **inert** | — |
| 6.1 `Freud's exploration of` | anch | `Freud "Le Lézard aux plumes d’or" Joan Miró` | **inert** | — |
| 8.1 `drawing you into the surreal world tha` | anch | `Joan Miró "Le Lézard aux plumes d’or"` | **inert** | — |
| 10.1 `Louis Broder, a figure renowned for hi` | anch | `Louis Broder "Le Lézard aux plumes d’or" Joan ` | **inert** | — |
| 10.2 `the exhibition highlights` | eval | `Joan Miró "Le Lézard aux plumes d’or" history` | **inert** | — |
| 11.1 `Broder's decision to engage Miró was p` | anch | `Broder "Le Lézard aux plumes d’or" Joan Miró` | **active** | Printed by Mourlot, Paris; published by Louis Broder, Paris. |
| 11.2 `blending visual and textual narratives` | eval | `Joan Miró "Le Lézard aux plumes d’or" abandone` | **eventful** | In Paris he abandoned this ... |
| 12.1 `Boris Fridman, a supporter of the art ` | anch | `Boris Fridman "Le Lézard aux plumes d’or" Joan` | **active** | Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by M |
| 12.2 `Boston's holdings` | anch | `Boston "Le Lézard aux plumes d’or" Joan Miró` | **active** | Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by M |
| 13.1 `Fridman's contribution ensures` | anch | `Fridman "Le Lézard aux plumes d’or" Joan Miró` | **active** | Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by M |
| 13.2 `visitors can appreciate the intricate ` | eval | `Joan Miró "Le Lézard aux plumes d’or" destroye` | **eventful** | For technical reasons, Miró decided to destroy ... |
| 13.3 `offering a unique tactile experience a` | eval | `Joan Miró "Le Lézard aux plumes d’or" refused` | **active** | Le Lézard aux plumes d'or" (detail, 1971), illustrated book with ... ~ Joan Miró rejected the constraints of traditional |

### Au Soleil du Plafond

| seed | class | query | kind | best retrieved sentence |
|---|---|---|---|---|
| 2.1 `Pierre Reverdy, the French poet linked` | anch | `Pierre Reverdy "Au Soleil du Plafond" Juan Gri` | **eventful** | Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ... |
| 2.2 `revolutionized the concept of the book` | eval | `Juan Gris "Au Soleil du Plafond" delayed` | **eventful** | It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du  |
| 2.3 `exemplifying the collaborative spirit ` | eval | `Juan Gris "Au Soleil du Plafond" history` | **eventful** | Gris died in 1927, having finished only half of the intended ... |
| 3.1 `Gris's innovative vision` | eval | `Gris "Au Soleil du Plafond" unfinished` | **eventful** | When the artist died the following year, the lithographs and text remained unfinished. |
| 3.2 `Reverdy's poetic prowess` | eval | `Reverdy "Au Soleil du Plafond" refused` | **eventful** | During the Nazi occupation, he joined the Resistance, refused ... |
| 3.3 `resulting in a unique interlacing of i` | eval | `Juan Gris "Au Soleil du Plafond" unfinished` | **inert** | — |
| 4.1 `Gris's ability to transform visual art` | eval | `Gris "Au Soleil du Plafond" destroyed` | **eventful** | Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine. |
| 4.2 `Reverdy's capacity to infuse words wit` | eval | `Reverdy "Au Soleil du Plafond" unfinished` | **inert** | — |
| 6.1 `rarely emerge from the archives` | eval | `Juan Gris "Au Soleil du Plafond" destroyed` | **eventful** | Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine. |
| 6.2 `offering a glimpse into the transforma` | eval | `Juan Gris "Au Soleil du Plafond" refused` | **eventful** | Juan Gris, Loupire (Kahnweiler 1969), Au Soleil du Plafond ... refuse any sale due to unforeseen ... refused sale for wh |
| 7.1 `highlights how visual artists` | eval | `Juan Gris "Au Soleil du Plafond" unfinished` | **inert** | — |
| 8.1 `inviting reflection on art as a shared` | eval | `Juan Gris "Au Soleil du Plafond" commissioned` | **eventful** | It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond. |

### Moses and Monotheism

| seed | class | query | kind | best retrieved sentence |
|---|---|---|---|---|
| 1.1 `Dalí's vivid illustrations` | anch | `Dalí "Moses and Monotheism" Salvador Dalí` | **inert** | — |
| 2.1 `breathe life into Freud’s narrative be` | anch | `Freud’s "Moses and Monotheism" Salvador Dalí` | **active** | Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport  |
| 3.1 `infusing it with his characteristic su` | eval | `Salvador Dalí "Moses and Monotheism" refused` | **active** | After Salvador Dali (Spanish, 1904-1989), Moses and Monotheism, gold gilt patinated copper bas relief, 27 x 21in. (71 x  |
| 4.1 `Freud's exploration of` | anch | `Freud "Moses and Monotheism" Salvador Dalí` | **active** | Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport  |
| 4.2 `visualizing the psychological and spir` | eval | `Salvador Dalí "Moses and Monotheism" unfinishe` | **eventful** | He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoa |
| 5.1 `delves into the complexities of religi` | eval | `Salvador Dalí "Moses and Monotheism" destroyed` | **inert** | — |
| 5.2 `setting the stage for Dalí's evocative` | anch | `Dalí's "Moses and Monotheism" Salvador Dalí` | **inert** | — |
| 6.1 `the book itself is an artwork` | eval | `Salvador Dalí "Moses and Monotheism" unfinishe` | **inert** | — |
| 7.1 `bridging literary and visual art forms` | eval | `Salvador Dalí "Moses and Monotheism" unfinishe` | **eventful** | He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoa |

