# Story iteration chart — MFA Unbound, stop 2, *Moses and Monotheism*

Built by `story_iteration_chart.py`. One iteration = one focus fact, its own
queries, its own candidate story, the production deletion gates, then
`evaluate_story.valuation_index`.

**Read the `best` column.** It is a running best over *validated* stories, so a
flat stretch means those iterations bought nothing — that is the stopping point.

| # | focus fact | kept | validated | index | hist | detail | social | **best** |
|---|---|---|---|---|---|---|---|---|
| 1 | Dalí's 1974 illustrations for Freud's Moses an | 5 | ✅ | 38 | 44 | 41 | 57 | **38** |
| 2 | the 1938 London meeting between Salvador Dalí  | 5 | ✅ | 37 | 67 | 0 | 57 | **38** |
| 3 | Freud's thesis that Moses was Egyptian, and th | 5 | ✅ | 47 | 46 | 0 | 69 | **47** |
| 4 | how the Museum of Fine Arts Boston acquired th | 5 | ✅ | 26 | 30 | 0 | 57 | **47** |
| 5 | the printing and edition history of the Moses  | 5 | ✅ | 36 | 34 | 0 | 69 | **47** |
| 6 | why Picasso, Miró and Dalí are shown together  | 5 | ✅ | 37 | 34 | 0 | 77 | **47** |
| 7 | Dalí's surrealist reading of psychoanalysis in | 5 | ✅ | 37 | 47 | 0 | 69 | **47** |
| 8 | the livre d'artiste tradition and its Boston c | 5 | ✅ | 39 | 12 | 8 | 80 | **47** |

## The curve

```
   1 |████████████████████████████████ best= 38 this= 38
   2 |████████████████████████████████ best= 38 this= 37
   3 |████████████████████████████████████████ best= 47 this= 47
   4 |████████████████████████████████████████ best= 47 this= 26
   5 |████████████████████████████████████████ best= 47 this= 36
   6 |████████████████████████████████████████ best= 47 this= 37
   7 |████████████████████████████████████████ best= 47 this= 37
   8 |████████████████████████████████████████ best= 47 this= 39
```

`█` running best over validated stories · `·` this iteration alone

## Where it stands

- iterations run: **8**
- best validated index: **47**
- iterations since the best improved: **5**
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
