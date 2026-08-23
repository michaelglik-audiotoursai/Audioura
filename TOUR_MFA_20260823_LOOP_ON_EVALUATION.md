# Picasso, Miró, Dalí: Unbound — regenerated with the story loop in production

**2026-08-23, 12:24–13:00 EDT. LEAD's own evaluation, written before Michael read the tour.**

Michael's instruction, 2026-08-22: *"regenerate the whole tour with all stories now in
place, write it to a document and open it in VS Code, then give LEAD's own evaluation of
the tour and each stop."* And: *"comparing one tour old vs new gives me nothing as old can
be random and so is new."*

So this is the A/B, not a single pair — **six full generations, arms alternating**
(OFF, ON, OFF, ON, OFF, ON) so the hour's drift in Serper results and page availability
falls on both arms equally. 36 minutes wall clock, ~$1.1 total, driver `run_ab_d511.sh`,
log `AB_D511_20260823_1224.log`, scorer `score_ab_d511.py` (one instrument for both arms —
the release-check script scores itself and the loop script does not, so scoring from the
`.txt` on disk is what makes the two comparable).

---

## 1. The headline, stated the way I would want it stated to me

| | runs | tour-mean index | sd | range |
|---|---|---|---|---|
| loop **OFF** | 3 | **58.0** | 7.22 | 49.7 – 62.3 |
| loop **ON** | 3 | **63.2** | 1.35 | 61.7 – 64.0 |
| | | **+5.2** | | pooled sd 5.45 |

**The delta is real-looking and I cannot call it significant.** Welch t = 1.24 at df ≈ 2.1;
p ≈ 0.33. And there is a sharper way to see the same thing:

> **Drop the one bad OFF run (49.7) and the gap collapses from +5.2 to +1.0.**

That is the honest reading. The loop did not raise the good runs. It prevented a bad one.
OFF spans 12.6 points across three runs; ON spans 2.3. If that holds up, the loop's product
is **reliability, not ceiling** — which is worth having, and is not what a "+5 points"
headline would have implied.

Three runs per arm is D480's rule and it is the minimum, not a comfortable n. I would not
push this to Michael as "the loop works" on this evidence. I would say: **it looks like it
raises the floor, and one more triple per arm would settle it** (~35 min, ~$1).

### Per-stop, where it gets interesting

| stop | OFF mean | ON mean | delta | story passed the gate |
|---|---|---|---|---|
| Le Lézard aux plumes d'or | 61.3 | 73.0 | **+11.7** | 1 of 3 runs |
| Au Soleil du Plafond | 58.3 | 74.0 | **+15.7** | **3 of 3 runs** |
| Moses and Monotheism | 54.3 | 42.7 | **−11.7** | 0 of 3 runs |

**The Moses row is the control, and it is the most useful number in this table.** The loop
wrote nothing on Moses in any run — it publishes nothing when nothing passes the gate, so
its text is mechanically identical in kind to the OFF arm. It still moved 11.7 points.
**That is pure generation noise, and it is the same size as the gains.** So the +11.7 and
+15.7 on the other two stops cannot be attributed to the loop on n=3 either, however much
the mechanism suggests they should be.

What the mechanism *does* support: on the stops where a story passed, the delivered text
gained four to five sentences of adjudicated, source-checked narrative that the OFF arm
does not contain at all. That is visible by reading, below, and does not depend on the index.

### Cost and time, per tour, 3 stops

| | wall | of which the loop | added cost |
|---|---|---|---|
| OFF | 191–208 s | — | — |
| ON | 438–612 s | 290–465 s | **$0.10–0.17** |

The loop roughly **triples wall-clock time** and adds ~$0.05/stop, as designed. 612 s on the
first ON run is the worst case; it fell to 438 s by the third as the page cache warmed.

---

## 2. The tour — loop ON, run 3, `TOUR_LOOP_20260823_1253.txt`

Featured because its tour-mean (64.0) is the ON arm's mean and it is the only run where two
of three stops carried a gated story. Verbatim, as generated.

---

### Stop 1 — Le Lézard aux plumes d'or (The Lizard with Golden Feathers), Joan Miró

> **Orientation:** The Picasso, Miro, Dali: Unbound exhibition at the MFA in Boston showcases
> the revolutionary livre d'artiste, transforming books into artistic masterpieces. Rarely
> seen, these deeply collaborative ventures redefine the intersection of images, words, and
> typography. Within Gallery 184, you'll encounter the extraordinary works by Spanish
> artists — Joan Miró's intricate "Le Lézard aux plumes d'or," a vibrant exploration of
> belief systems and nature's transformation. Next, immerse yourself in the surreal wonder
> of Salvador Dali's "Au Soleil du Plafond," inviting contemplation on the boundary between
> reality and dreams. Conclude your journey with Pablo Picasso's "Moses and Monotheism," a
> testament to the power of artistic reinterpretation. […] As you stand in the Linde Family
> Gallery, position yourself to face "Le Lézard aux plumes d'or" by Joan Miró.
>
> **Body:** Louis Broder published Joan Miró's "Le Lézard aux plumes d'or" in 1971, bringing
> to life a limited edition illustrated book featuring 40 vibrant lithographs. This
> collaboration marked a significant achievement in the art publishing world […] The book was
> printed by the renowned Mourlot Frères, a Parisian atelier known for its exceptional
> lithographic work […] Broder, a dedicated supporter of the arts, deliberately commissioned
> Miró for this edition […] The Louis Broder's vellum chosen for this book adds a tactile
> richness […] The piece was generously donated to the Museum of Fine Arts, Boston, by Boris
> Fridman […] As you explore the exhibition, consider how such collaborations between artist,
> publisher, and printer create a lasting legacy within the art world.
>
> **— the loop's story begins here —**
>
> Joan Miró wrote an original surrealist poem and illustrated it with a series of lithographs
> for publisher Louis Broder in 1967. After printing began, Miró and Broder discovered that a
> manufacturing defect in the paper was altering and degrading the colors. Because the
> original printing plates had already been erased, they had to abandon the entire initial
> edition. Miró was forced to create a completely new set of compositions from scratch,
> alongside pages reproducing his own handwritten text, finally publishing the completed
> project in 1971.

### Stop 2 — Au Soleil du Plafond, Juan Gris

> **Body:** In 1916-1917, L. Rosenberg conceived the idea for the book "Au Soleil du Plafond,"
> enlisting artist Juan Gris to design it. However, Gris passed away in 1927, leaving the
> project unfinished, with only half of the intended work completed. Pierre Reverdy, a french
> poet of the surrealist movement, provided the poetic text […] The esteemed printer Mourlot
> Frères, a renowned lithography studio in france, executed the lithographs […] Together,
> these collaborators achieved a harmonious fusion of art and text, advancing the exhibition's
> thesis that the livre d'artiste was a profoundly collaborative endeavor.
>
> **— the loop's story begins here —**
>
> Art dealer Léonce Rosenberg initiated this project with poet Pierre Reverdy and painter Juan
> Gris, with some sources dating its start to 1916–1917 and others to 1920. The original plan
> paired twenty poems by Reverdy with twenty corresponding plates by Gris. When Gris died of
> kidney failure in 1927 at age forty, the work came to a halt with only eleven illustrations
> finished. Nearly thirty years later, publisher Tériade revived the abandoned project. The
> book was finally printed by Mourlot Frères in 1955 as a posthumous tribute to Gris.

### Stop 3 — Moses and Monotheism, Salvador Dalí

> **Body:** In 1974, Salvador Dalí crafted a series of illustrations for Sigmund Freud's
> challenging text "Moses and Monotheism." Freud, the author, proposed a controversial
> hypothesis suggesting Moses was an Egyptian priest of Akhenaten, bringing a fresh perspective
> to biblical narratives. This synthesis of Dalí's surrealist imagery with Freud's
> psychoanalytic theories exemplifies the exhibition's thesis that collaborative artistic and
> literary efforts can transform a book into an art form of its own. Each illustration Dalí
> created magnifies Freud's provocative ideas, highlighting the potency of image and text when
> melded in such a revolutionary manner. This exhibit not only showcases Dalí's artistic
> prowess but also reflects how artists and authors of the time came together to challenge
> traditional narratives and redefine the book as a visual and intellectual canvas.

**No story. The gate published nothing, which per Michael's ruling is correct behaviour.**

---

## 3. My evaluation, stop by stop

### Stop 1 — the loop delivered exactly what it was built for, and it is bolted on

**The story is the best four sentences in this tour.** A defective paper stock degrading the
colours, plates already erased so there is no going back, the artist starting the whole thing
again from nothing, four years lost. Action, obstacle, and a cost somebody actually paid.
This is the Christie's Lot Essay material that D510's page-fetch fix unlocked, and it is the
first time it has reached a delivered tour rather than an adjudication table.

**But the seam is audible.** The descriptive prose ends on *"consider how such collaborations
between artist, publisher, and printer create a lasting legacy within the art world"* — a
closing sentence, a wrap-up — and then the story starts. The wiring is
`description.rstrip() + ' ' + story` (`generate_tour_text.py:14209`): plain concatenation,
no paragraph break, no transition, and no check for whether the prose has already finished
speaking. A listener hears the stop end and then restart.

**And it repeats itself.** The prose says Broder published in 1971 and *"deliberately
commissioned Miró"*; the story then explains that the commission was 1967 and 1971 was the
salvage. Not a contradiction, but the reader is told about the same commission twice, the
second time better. The second telling should have replaced the first.

**Three defects that have nothing to do with the loop:**

1. **The orientation misattributes two of the three works in this tour.** *"Salvador Dali's
   'Au Soleil du Plafond'"* — that is Gris and Reverdy. *"Pablo Picasso's 'Moses and
   Monotheism'"* — that is Dalí and Freud. **Both are contradicted by the stop headings in the
   same document**, twelve and twenty-six lines further down. This is the single worst thing
   in the tour: a visitor is told the wrong artist for two works while standing in the room
   with them. It appears in **1 of 6 runs**, which makes it intermittent, not systematic —
   and intermittent is harder to catch, not easier.
2. **Two different galleries in one orientation** — *"Within Gallery 184"* and then *"As you
   stand in the Linde Family Gallery."*
3. ***"The Louis Broder's vellum chosen for this book"*** — ungrammatical, and it reads as if
   the vellum were Broder's rather than the edition's.

### Stop 2 — the story passed on all three runs, and it is fighting the paragraph above it

**This is the loop's most reliable stop: 3 of 3.** The story is good — Gris dead at forty of
kidney failure, eleven plates of a planned twenty, the book finished thirty years later as a
tribute by a different publisher.

**The duplication here is severe enough to be a release blocker on its own.** Both halves of
the stop tell the same story:

| the prose says | the story then says |
|---|---|
| Rosenberg conceived it, 1916–1917 | Rosenberg initiated it, 1916–1917 or 1920 |
| Gris died 1927, project unfinished | Gris died 1927, of kidney failure, at forty |
| about half the work completed | eleven of a planned twenty |
| Mourlot Frères executed the lithographs | Mourlot printed it, in 1955 |

The listener hears the whole life of this book twice inside one stop, ninety seconds apart.
The append strategy has no way to notice, because it never reads the prose it appends to.

There is also a **contradiction hidden in that duplication**: the prose says Mourlot *"executed
the lithographs, ensuring the precision and quality that Gris's intricate designs demanded"* —
which places the printer at Gris's side — while the story establishes the printing happened
in 1955, twenty-eight years after Gris died. The story is right. The prose is a plausible
sentence that quietly asserts something false.

**Copy defects:** *"a french poet"*, *"a renowned lithography studio in france"* — lowercase,
twice. *"L. Rosenberg"* in the first sentence and *"Léonce Rosenberg"* in the sixth, same man.

### Stop 3 — the gate is right and the stop is empty

**Five sentences and four of them are praise.** *"exemplifies the exhibition's thesis"*,
*"magnifies Freud's provocative ideas"*, *"showcases Dalí's artistic prowess"*, *"redefine the
book as a visual and intellectual canvas."* Strip the evaluation and one fact survives: Dalí
illustrated Freud's text, and Freud argued Moses was Egyptian.

**The gate publishing nothing here is correct and I would not lower it.** A214 already settled
that. What this run adds is that **D511's fix for A213 did not reach this stop, and I can say
exactly why.**

A213's finding was that credit_lines mined from our own prose can only ask about what our prose
already said — which is why the Freud/Dalí meeting in Hampstead in 1938, retrievable the whole
time, was never asked for. D511's answer was to seed from the **matrix agents** as well. The log
shows what that bought here:

```
[D511] stop 3: Moses and Monotheism
[D511] 4 credit_line(s) to try (1 from the matrix, 3 from the text)
```

**One matrix agent: Dalí.** Freud is the *author of the text*, and the museum's object record
does not carry him in `collaborator`, `publisher` or `printed_by` — so the one person whose
story is worth telling is not a seed. The other three slots go back to the same evaluative
prose A213 diagnosed. **The London meeting is still missing, three runs out of three, and the
mechanism that was supposed to find it structurally cannot.**

**Also still wrong here:** *"In 1974"* is asserted flatly when the sources disagree between 1974
and 1975 — the loop's own adjudicator flagged that disagreement, but the descriptive prose it
never touched states one date as fact. And *"an Egyptian priest of Akhenaten"* overstates
Freud, who argued Moses was an Egyptian adherent of Akhenaten's monotheism.

---

## 4. What I found in the machinery while this ran

**(a) The loop can never reach the candidate that made it work in the lab.**
`story_production_loop.py:164` — `seeds = seeds[:MAX_CREDIT_LINES]`, default **4**. In
`ADJUDICATED_EVALUATION.md`, Le Lézard passed at **credit_line 13.1, having examined 14 of 16**.
Matrix agents are placed first, and Le Lézard has four of them, so the log reads *"4 credit_line(s)
to try (4 from the matrix, 0 from the text)"* — **not one prose seed is ever tried on that stop.**
The lab result that justified building this is unreachable in production by construction. Across
all nine stop-attempts: **every stop that hit the cap of 4 failed; every acceptance happened by the
third candidate.** That is consistent with either "the cap is fine" or "the cap is the ceiling",
and the two are distinguishable for about $0.20 by raising `STORY_LOOP_MAX_CREDIT_LINES` to 14 on
one stop.

**(b) The `work_stories` cache cannot connect on any host run, and says so quietly.**
`work_story_searcher.py:124` rewrites `@localhost:` to `@postgres-2:` — a container hostname that
does not resolve on the Mac. D261 *mandates* `DATABASE_URL=…@localhost:5433/…` for host runs, so
the two rules are in direct conflict and the cache logs `Read error: could not translate host name
"postgres-2"` on every run, then returns `None` and proceeds. Every host tour re-mines from scratch.
**For this A/B it was a help, not a harm** — a working cache would have contaminated runs 2 and 3
with run 1's material — but it is a silent, permanent cache miss in every host-side run we have done.

**(c) Retrieval is still the art market, D495 notwithstanding.** The pages actually fetched for
stop 2 were abebooks, araderbooks, iberlibro, 1stdibs, invaluable, baumanrarebooks, christies,
art-books. The −5 market penalty demotes them but there is nothing to promote above them, so they
are what gets read. The one scholarly source that appeared, `metmuseum.org/art/collection/search/356117`,
**returned HTTP 429 four times and was dropped**. D496's tiers 1–3 as a retrieval *preference* remain
unbuilt, and this is what that costs.

**(d) The entity check fired on a real person.** `UNGROUNDED:Léonce Rosenberg` on stop 3 of run 1 —
Rosenberg is genuine, he is in the adjudicated lab story, and he appears in the delivered text of
run 3. Whether that firing was correct depends on whether he was in *that run's* retrieved evidence,
which I have not verified. `ADJUDICATED_EVALUATION.md` §5 reports 0 of 37 flagged after the fix;
this is the first firing since, and it deserves the by-hand look before `STORY_GATE_STRICT` is ever
turned on.

---

## 5. Would I ship this?

**No — and the reason is not the story loop, which is the best thing in the tour.**

Three things block it, in order:

1. **The orientation named the wrong artist for two of three works.** Once in six runs. A tour
   that is confidently wrong about who made the thing you are looking at is worse than a dull one.
   Nothing in the pipeline currently checks the orientation's attributions against the stop
   headings it sits above — and that check is cheap and local.
2. **Every stop that gets a story now says everything twice.** The append is concatenation. Until
   the story either replaces the overlapping prose or the prose is generated knowing a story is
   coming, the loop makes stops longer and more redundant at the same time as it makes them better.
3. **One stop in three publishes no story at all**, and on Moses that is three runs out of three.
   The gate is behaving correctly; the retrieval is not delivering.

**What I would do next, in this order** — (1) fix the append seam and de-duplicate, which is the
only one of the three that is purely ours and needs no network; (2) add the orientation-attribution
check; (3) spend $0.20 raising the credit_line cap on Le Lézard to find out whether the cap is the
ceiling; (4) D496's tiers 1–3 as retrieval preference, which is the only thing that will ever fix
Moses.

**What I would not do:** lower the gate. Moses publishing nothing is the system telling the truth.

---

## Artifacts

| file | what |
|---|---|
| `TOUR_LOOP_20260823_1253.txt` | the featured tour, loop ON (also `_1227`, `_1241`) |
| `TOUR_MFA_RELEASE_20260823_1224.txt` | loop OFF baseline (also `_1238`, `_1249`) |
| `AB_D511_20260823_1224.log` | all six generations, 5,485 lines |
| `AB_D511_SCORES.json` | 18 scored stops |
| `run_ab_d511.sh`, `score_ab_d511.py` | the driver and the single scoring instrument |
