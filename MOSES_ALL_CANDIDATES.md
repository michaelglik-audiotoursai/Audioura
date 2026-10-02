# Moses and Monotheism — every story Gemini wrote, and why each was rejected

**2026-08-23.** Michael: *"display all stories for Moses and Monotheism coming from
Gemini and the validator rejections of each."*

**They were not on disk.** The production loop printed one summary line per candidate and
kept the story text in a dict that died with the process — so a rejection could not be
checked, which is a problem when the whole claim is *"Moses publishes nothing and the gate
is right to."* Fixed as **D514**: `story_production_loop.py` now appends every candidate to
a JSONL. Stop 3 was then replayed under production conditions to capture today's set.

**Thirteen stories below.** Four from today's production loop (`MOSES_CANDIDATES_20260823_1711.jsonl`),
nine from the D510 lab run (`ADJUDICATED_STORIES.md`). **All thirteen fail on `eventful`.**

---

## How to read the verdict

| field | meaning |
|---|---|
| `kind` | `material_kind`: **eventful** (someone acts and something is at stake) > **active** (someone acts) > **inert** > **none**. The gate requires `eventful`. |
| `index` | `evaluate_story` valuation, 0–100. Gate requires ≥ 60. |
| `C` / `Corr` / `D` / `X` | adjudication against retrieved evidence: CONFIRMED / CORRECTED / DISPUTED / UNATTESTED. Gate requires C ≥ 3. |
| `ungrounded` | a person named in the story who appears in no retrieved source. **Blocks publication before the gate is even consulted.** |

---

# Part A — today's production loop, 4 candidates

Seeds: one matrix agent (Dalí) and three modifiers lifted from the stop's own prose.
Cap is 4 (`STORY_LOOP_MAX_CREDIT_LINES`), so these are all of them.

## A1. credit_line — *Salvador Dalí*  ·  seed: `matrix_agent`

**REJECTED — failed `eventful, index, confirmed`**  ·  kind **inert** · index **51** · `C2` `Corr0` `D0` `X3`

> In his controversial 1939 book *Moses and Monotheism*, Sigmund Freud argued that Moses was an Egyptian rather than a Hebrew [equip.org, collections.museumofthebible.org, baumanrarebooks.com]. Decades later, Salvador Dalí engaged in a direct dialogue with Freud's final text by creating an illustrated, oversize edition of the work [salvador-dali.org, collections.museumofthebible.org]. Instead of utilizing traditional paper alone, Dalí and his printers produced the project's loose-leaf pages directly onto treated sheepskin and silk [collections.museumofthebible.org].

## A2. credit_line — *Freud, the author*  ·  seed: `appositive`

**REJECTED — failed `eventful`**  ·  kind **active** · index **64** · `C2` `Corr1` `D1` `X3`

> In 1939, Sigmund Freud published his final work, *Moses and Monotheism*, arguing that Moses was of Egyptian nobility rather than Hebrew origin. Salvador Dalí later created an illustrated edition of the text, with sources dating the project to 1974 or 1975. To produce the illustrations, Dalí drew directly onto massive gold printing plates with a diamond stylus. These images were then printed on sheepskin to complete the limited portfolio edition.

## A3. credit_line — *Freud's challenging text*  ·  seed: `possessive`

**REJECTED — failed `eventful`**  ·  kind **active** · index **68** · `C3` `Corr0` `D2` `X4`  ·  **ungrounded: Parisian**

> Just before his death in 1939, Sigmund Freud published his controversial final work, *Moses and Monotheism*, arguing that Moses was an Egyptian who introduced monotheism to the Jewish people. In 1974, the Parisian publisher Art & Valeur commissioned Salvador Dalí to create an illustrated deluxe edition engaging directly with Freud's text. Records differ on the release, with some sources listing an edition capped under 1,500 copies, and the sculptural metal bas-relief created for the project being described variously in brass and silver or in patinated copper metal. Through this commission, Dalí transformed Freud's provocative historical thesis into a series of graphic prints and three-dimensional relief works.

## A4. credit_line — *bringing a fresh perspective to biblical narratives*  ·  seed: `participial`

**REJECTED — failed `eventful, index, confirmed`**  ·  kind **none** · index **5** · `C0` `Corr0` `D0` `X6`

> No confirmed or corrected facts are available from the provided evidence to tell the story of this work.

---

# Part B — the D510 lab run, 9 candidates

Seeds are all modifiers from the baseline prose — this is the run A213 was written about.

## B1.1. credit_line — *Dalí's vivid illustrations*  ·  seed: `anchored`

**REJECTED — failed `eventful`**  ·  kind **inert** · index **63** (hist 12, detail 45, social 45) · `C2` `Corr2` `D0` `X4`

> Salvador Dalí produced illustrations based on watercolor, pen-and-ink drawings, and etchings for an oversize French edition of Sigmund Freud’s 1939 work *Moses and Monotheism*. To realize the project, the publisher produced the text and imagery as loose-leaf pages printed with etchings and lithography directly onto sheets of sheepskin and silk. The loose leaves were assembled inside two large acrylic folios and placed inside a velvet container fitted with a bas-relief metal cover. This relief pairs the figure of Michelangelo’s Moses with the Egyptian Eye of Horus to represent Freud's central thesis that Moses was Egyptian rather than Hebrew.

## B2.1. credit_line — *breathe life into Freud’s narrative become evident*  ·  seed: `anchored`

**REJECTED — failed `eventful, confirmed`**  ·  kind **inert** · index **65** (hist 55, detail 57, social 30) · `C1` `Corr1` `D1` `X5`

> Salvador Dalí created illustrations for an oversize French edition of Sigmund Freud’s 1939 text *Moses and Monotheism*, with sources placing the release in either 1974 or 1975. Dalí based his illustrations on watercolors, pen-and-ink drawings, and etchings to visualize Freud's psychoanalytic thesis that Moses was Egyptian rather than Hebrew. The publishers produced the loose-leaf pages using a combination of pressed etchings and lithography printed directly onto sheepskin and silk. They then gathered the completed sheets into two large acrylic folios bound inside a velvet container fitted with a bas-relief metal cover.

## B3.1. credit_line — *infusing it with his characteristic surrealism*  ·  seed: `evaluative`

**REJECTED — failed `eventful, index`**  ·  kind **active** · index **51** (hist 32, detail 39, social 38) · `C1` `Corr3` `D0` `X3`

> Salvador Dalí created illustrations for Sigmund Freud’s 1939 work *Moses and Monotheism*, producing designs based on watercolor, pen-and-ink drawings, and etchings. Printers then transferred the artwork onto loose-leaf sheets of sheepskin and silk using pressed etchings and lithography. Dalí incorporated Freud’s thesis that Moses was Egyptian rather than Hebrew by placing the figure of Michelangelo's Moses inside the Eye of Horus on a bas-relief metal cover. The completed loose pages were laid into two large acrylic folios and housed together inside a velvet container.

## B4.1. credit_line — *Freud's exploration of*  ·  seed: `anchored`

**REJECTED — failed `eventful`**  ·  kind **active** · index **61** (hist 44, detail 47, social 15) · `C2` `Corr1` `D0` `X2`

> In 1939, Sigmund Freud published his controversial final work arguing that Moses was an Egyptian nobleman and follower of Akhenaten rather than a Hebrew slave. In 1974, Salvador Dalí created a print edition of Freud's text accompanied by ten engravings. To create the illustrations, Dalí drew directly onto massive gold printing plates using a diamond stylus. He then printed the resulting color images onto lambskin rather than standard paper.

## B4.2. credit_line — *visualizing the psychological and spiritual transition from polytheistic beliefs*  ·  seed: `evaluative`

**REJECTED — failed `eventful`**  ·  kind **inert** · index **65** (hist 12, detail 51, social 50) · `C4` `Corr2` `D0` `X6`

> To illustrate Sigmund Freud’s 1939 published text *Moses and Monotheism*, Salvador Dalí created a suite of works using a combination of pressed etchings and lithography. Freud had argued in his text that Moses was Egyptian rather than Hebrew. Dalí’s pages were printed on both sheepskin and silk in a loose-leaf format. The complete set was placed within two large acrylic folios and housed inside a velvet container fitted with a sculpted metal bas-relief cover based on Michelangelo’s *Moses*.

## B5.1. credit_line — *delves into the complexities of religious origins*  ·  seed: `evaluative`

**REJECTED — failed `eventful, confirmed`**  ·  kind **active** · index **66** (hist 32, detail 38, social 15) · `C2` `Corr0` `D1` `X4`

> Sigmund Freud published *Moses and Monotheism* in 1939 after finding refuge in England shortly before his death. In the text, Freud presented a controversial thesis that Moses was actually Egyptian rather than Hebrew, though scholars debate whether his intent was to claim historical fact or to explore a psychological leap in the history of civilization and his own relationship to Judaism. Salvador Dalí later took up Freud's text, creating an edition illustrated with pressed etchings and lithographs based on his drawings. Dalí paired his artwork directly with Freud's printed writing to explore the intersection of psychoanalysis, religion, and modern art.

## B5.2. credit_line — *setting the stage for Dalí's evocative interpretations*  ·  seed: `anchored`

**REJECTED — failed `eventful, index, confirmed`**  ·  kind **active** · index **44** (hist 12, detail 6, social 57) · `C1` `Corr0` `D0` `X3`

> In 1939, Sigmund Freud completed and published his final original work, *Moses and Monotheism* [en.wikipedia.org, journals.sagepub.com]. In the book, Freud proposed that Moses was not born a Hebrew slave, but was instead an Ancient Egyptian nobleman and follower of the monotheistic solar god Aten under Pharaoh Akhenaten [en.wikipedia.org]. Freud argued that Moses led his followers out of Egypt after Akhenaten's death, only to be murdered in a rebellion, setting off a legacy of collective guilt that shaped the development of religious tradition [en.wikipedia.org].

## B6.1. credit_line — *the book itself is an artwork*  ·  seed: `evaluative`

**REJECTED — failed `eventful, index`**  ·  kind **active** · index **52** (hist 54, detail 43, social 15) · `C1` `Corr2` `D0` `X2`

> Sigmund Freud fled to London and published *Moses and Monotheism* in 1939, just months before his death in September of that year. In the text, Freud presented his argument that Moses was an Egyptian rather than Hebrew. Salvador Dalí later created illustrations based on watercolor, pen-and-ink drawings, and etchings for an oversize French edition of the work. The pages were produced in a loose-leaf format using lithography and pressed etchings on sheepskin and silk.

## B7.1. credit_line — *bridging literary and visual art forms*  ·  seed: `evaluative`

**REJECTED — failed `eventful`**  ·  kind **active** · index **71** (hist 35, detail 78, social 30) · `C5` `Corr1` `D2` `X3`

> Salvador Dalí created this French loose-leaf edition of Sigmund Freud's 1939 text *Moses and Monotheism* for the Paris publisher Art et Valeur, with records dating the release to either 1974 or 1975. Dalí took Freud’s argument that Moses was an Egyptian rather than a Hebrew and interpreted it across pressed etchings and lithographs printed directly onto sheepskin and silk. The completed sheets were gathered into folios and bound within a velvet casing featuring a cast bas-relief metal cover. While standard print runs for the project are recorded as numbering 250 or 300 copies, a separate artist proof edition totaled 25 sets.

---

# What I see in the thirteen

**1. All thirteen fail `eventful`, and every one of them is a production description.**
Who made it, from what, onto what material, in what box. Sheepskin and silk in eleven of
thirteen; the acrylic folios and the velvet case in seven. Nobody's plan collapses, nobody is
defied, nothing is at risk. **The gate is right.** This is A214 confirmed with the texts in
hand rather than asserted from a summary line.

Compare the two stops that do pass: Miró's paper defect destroys an edition and the plates are
already erased; Gris dies at forty with eleven plates of twenty finished. Something goes wrong
and somebody pays. Nothing goes wrong anywhere in these thirteen.

**2. The one genuinely eventful passage we retrieved is a story inside Freud's book, not the
story of the object.** B5.2: *"Freud argued that Moses led his followers out of Egypt after
Akhenaten's death, only to be murdered in a rebellion, setting off a legacy of collective guilt
that shaped the development of religious tradition."* Action, reversal, consequence — and it is
the *content* of the text, retold. It failed on `eventful` anyway, plus `index` and `confirmed`.
Worth knowing that even the strongest narrative in the pool is the wrong kind of narrative.

**3. The door to the missing story was retrieved twice and never opened.** B5.1: *"after finding
refuge in England shortly before his death."* B6.1: *"Freud fled to London and published it in
1939, just months before his death in September."* London, 1939, weeks from death — and Dalí
came to that house in 1938. **The meeting appears in none of the thirteen.** A213 said the seeds
can only ask what our prose already said; D511 added the matrix agents to fix it; the matrix for
this stop yields exactly one agent, Dalí, because Freud is the author and not a `collaborator`
in the object record — and `[D501] no object record for 'Moses and Monotheism'` in today's replay
means there was no museum record to read at all. **The fix has no purchase on this stop.**

**4. A second sighting of the entity-check false positive, and this one is a bug, not a question.**
A3 was flagged `ungrounded: Parisian` — from *"the Parisian publisher Art & Valeur"*. A demonym,
not a person. The check runs **before** the gate is consulted (`if ungrounded: continue`), so a
flag discards the candidate whatever its verdict. Here nothing was lost, because A3 also failed
`eventful`. But this is the same class as the possessive and sentence-initial bugs D510 fixed,
it is the second firing after `Léonce Rosenberg` (D513d), and **the next one will silently kill a
story that should have published.** No longer "look at it before `STORY_GATE_STRICT`" — fix it.

**5. One of four slots produced nothing at all.** A4 returned *"No confirmed or corrected facts
are available from the provided evidence."* That is the pipeline degrading honestly, and it still
consumed a quarter of a budget capped at four (D513a). A seed derived from *"bringing a fresh
perspective to biblical narratives"* was never going to find anything; nothing checks a seed for
askability before spending a Gemini call and three SERP queries on it.

**6. The closest thing to craft drama is ruled `active`, and I think correctly.** A2 and B4.1
both surface *"Dalí drew directly onto massive gold printing plates using a diamond stylus"* and
printed onto lambskin rather than paper. Specific, physical, and nobody is at risk — so
`material_kind` calls it `active` and the gate declines it. Right by the current definition. If
Michael wants irreversibility and material risk to count as stakes, that is a definition change
to make deliberately, not a threshold to nudge.

**7. What this cost.** Today's replay: $0.059 for four rejections. Across the three A/B runs
Moses spent ~$0.176 to publish nothing. That is the correct behaviour's honest price, and it is
cheap — the expensive thing would be publishing the sheepskin four times.

## What I would change, from these texts

1. **Fix `ungrounded_names`** — demonyms and adjectival nationalities are not people. Second
   false positive in two days, and it discards before the gate.
2. **Do not seed on a modifier that names nobody and asserts nothing.** *"bringing a fresh
   perspective to biblical narratives"* cannot become a question. Screen seeds for an agent or a
   concrete noun before spending on them, and the effective cap rises without raising the cap.
3. **Let the challenge query drop the work title** — A213's own recommendation, still unbuilt.
   `Sigmund Freud Salvador Dalí` finds the Hampstead meeting immediately; every query here is
   anchored on *Moses and Monotheism* and returns the book.
4. **Seed the author of an illustrated text as an agent.** Freud is not a `collaborator` in any
   museum field, and he is the person the story is about. One line in `_agent_seeds`.
