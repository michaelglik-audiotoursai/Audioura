# System evaluation — relevance gating, and Serper vs Gemini

**37 Serper + 37 Gemini grounded = 74 retrievals · ~$0.185 · 212s.** Budget was $13; this used about 1.4% of it.

Raw evidence is in **`SEED_RAW_RESULTS.md`** — every result, every sentence, every verdict. This document only interprets it.

## 1. The relevance gate works, and it cost us real material

| | inert | active | eventful |
|---|---|---|---|
| SERP before gate | 13 | 11 | 13 |
| SERP after gate | 18 | 8 | 11 |

**13 eventful → 11.** Two of the eventful verdicts were the gate's target: sentences that describe a real event happening to somebody else. The clearest:

> *Dora Szampanier, Etching of destroyed synagogue — Drohobisz, Ukraine.*

Retrieved for `Gris "Au Soleil du Plafond" destroyed`, scored **eventful** before gating. It is now `inert`, and seed 4.1 correctly reports that it found nothing.

**21% of all retrieved sentences (126 of 574) were judged irrelevant.** That is the noise the event-shaped queries were pulling in and nothing downstream was measuring.

### The gate took two attempts, and the first failure is worth recording

Version 1 changed **nothing** — every verdict identical. The rescue clause for anaphoric sentences (*"When the artist died the following year..."* names nobody and is one of the best sentences we retrieved) was inheriting subject from context, and I passed **all eight snippets concatenated** as that context. So every sentence inherited relevance from its neighbours.

Fixing that to per-snippet context changed **zero rows** — because the Szampanier line sits in an SEO aggregator snippet that genuinely reads *"Juan Gris, The Pipe, from Au Soleil du Plafond, 1955 ... Related Searches. Dora Szampanier, Etching of destroyed..."*. Its own snippet does name the work.

The rule that finally works is a **competing proper noun**: a sentence naming somebody who is not ours is not anaphoric — it is about them. That moved 5 verdicts.

## 2. Gemini lost, decisively

| | inert | active | eventful | no-info |
|---|---|---|---|---|
| Serper | 18 | 8 | **11** | — |
| Gemini grounded | 34 | 3 | **0** | 8 |

**Gemini returned zero eventful material on all 37 questions.** Eight times it correctly declared `NO RELIABLE INFORMATION` — which is honest and worth something — but it never once surfaced an event Serper missed.

This is a real result and it contradicts the premise of step 4. D482's argument for a second model was **cross-model agreement as a grounding signal**. On this evidence there is nothing to agree with: one engine finds events, the other finds nothing.

I would not generalise it too far. The prompt asked for attributable facts and forbade speculation, which is a harder task than Serper's — Serper is not answering the question, it is returning documents that a human then reads. The comparison is retrieval-vs-answering as much as Google-vs-Gemini.

## 3. The stop ranking held

| stop | SERP eventful (gated) | Gemini eventful |
|---|---|---|
| Le Lézard aux plumes d’or (The Liz | **2** of 16 | 0 |
| Au Soleil du Plafond | **7** of 12 | 0 |
| Moses and Monotheism | **2** of 9 | 0 |

**Au Soleil du Plafond still wins after gating — 7 of 12.** The stop with one agent, no object record and 1 anchored seed out of 12. D504's finding survives the correction that removed its two false positives.

## 4. What the material actually says

The Au Soleil sentences that survived gating, in the order a story would use them:

> *Gris died in 1927, having finished only half of the intended ...*

> *It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond.*

> *It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond.*

Gris began the book, died with half of it done, and Reverdy — with Tériade publishing — brought out a reduced version 28 years later. Change, agent, stakes. It clears your bar, and **none of it is in the tour**, which says only "posthumously realized".

## 5. What I would do next, and what I would not

**Would:** feed these gated sentences to the story pass for Au Soleil and see whether the generator can build the Gris/Reverdy/Tériade story from them. That is the first end-to-end test of the whole seed chain, and it is cheap.

**Would:** treat `Tériade` as a matrix `sponsor` — retrieval found the agent the object record could not.

**Would not:** wire any of this into production yet. Five modules now exist with no production caller — `object_record`, `story_hooks`, `story_seeds`, `story_relevance`, and `story_roles` beyond one log line. That is the exact pattern the 7-step plan opened by complaining about, and I am adding to it.

**Open question for you:** the gate keeps `weak` sentences (anaphoric, subject established by their own snippet). That is generous by design — retrieval is scarce and a wrongly-dropped story costs more than a weak sentence competing. If you would rather it were strict, it is one flag.
