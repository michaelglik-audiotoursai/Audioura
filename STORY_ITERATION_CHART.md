# Story iteration chart — MFA Unbound, stop 2, *Moses and Monotheism*

Built by `story_iteration_chart.py`. One iteration = one focus fact, its own
queries, its own candidate story, the production deletion gates, then
`evaluate_story.valuation_index`.

**Read the `best` column.** It is a running best over *validated* stories, so a
flat stretch means those iterations bought nothing — that is the stopping point.

| # | focus fact | kept | validated | index | hist | detail | social | **best** |
|---|---|---|---|---|---|---|---|---|
| 1 | Dalí's 1974 illustrations for Freud's Moses an | 20 | ✅ | 55 | 24 | 55 | 57 | **55** |
| 2 | the 1938 London meeting between Salvador Dalí  | 20 | ✅ | 64 | 75 | 41 | 69 | **64** |
| 3 | Freud's thesis that Moses was Egyptian, and th | 20 | ✅ | 40 | 44 | 29 | 57 | **64** |
| 4 | how the Museum of Fine Arts Boston acquired th | 20 | ✅ | 52 | 24 | 29 | 69 | **64** |
| 5 | the printing and edition history of the Moses  | 20 | ✅ | 50 | 24 | 29 | 69 | **64** |
| 6 | why Picasso, Miró and Dalí are shown together  | 20 | ✅ | 48 | 42 | 21 | 57 | **64** |
| 7 | Dalí's surrealist reading of psychoanalysis in | 20 | ✅ | 57 | 66 | 39 | 57 | **64** |
| 8 | the livre d'artiste tradition and its Boston c | 20 | ✅ | 35 | 12 | 29 | 45 | **64** |

## The curve

```
   1 |██████████████████████████████████ best= 55 this= 55
   2 |████████████████████████████████████████ best= 64 this= 64
   3 |████████████████████████████████████████ best= 64 this= 40
   4 |████████████████████████████████████████ best= 64 this= 52
   5 |████████████████████████████████████████ best= 64 this= 50
   6 |████████████████████████████████████████ best= 64 this= 48
   7 |████████████████████████████████████████ best= 64 this= 57
   8 |████████████████████████████████████████ best= 64 this= 35
```

`█` running best over validated stories · `·` this iteration alone

## Where it stands

- iterations run: **8**
- best validated index: **64**
- iterations since the best improved: **6**
- stories rejected by a gate: **0 of 8**
- SERP queries spent: **80**

## Why it plateaus — read this before tuning anything (D467)

The flat stretch is a property of the **metric**, not of the material.
`valuation_index` is [`evaluate_story.py:342`](evaluate_story.py#L342):

```
sentence_count * 10   capped at 30   <- maxes at 3 sentences
agency_verbs   * 10   capped at 30
stakes_words   * 12   capped at 25
grounded_fraction * 15               <- proper nouns found in the museum corpus
```

Three consequences, all measured:

1. **The object is not in the formula.** `detail` — whether a sentence names a
   physical property of the thing in the case — is computed and then never
   added. That is measure 4 in `STORY_GATE_TIERS.md`, the known weakness
   (D449), and the index is blind to it.
2. **Sentences past the third are free.** 3 x 10 already caps that term, so
   Michael's "3-5 sentences" is scored as if it were always 3.
3. **Groundedness punishes specificity.** Raising the snippet cap from 5 to 20
   on the best iteration moved `detail` 0 -> 29 (the story finally said
   *"drypoints and lithographs on sheepskin"*) and `historic` 46 -> 66 — and
   the index **fell 61 -> 50**, because the new proper nouns are absent from
   the museum's own page. **The scorer repeats the gates' mistake: it treats
   absence from a narrow corpus as evidence against.**

So the plateau does not mean we stopped finding better stories. It means the
instrument stopped being able to see them.
