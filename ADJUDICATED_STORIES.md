# 37 adjudicated stories — challenged, corrected, and sourced

**123 Serper challenge queries + 37 Gemini adjudications · ~$0.345 · 184s**

Each story went through four stages (D509):

1. **Round 1** — Gemini answers *"What story can be told to visitors of {exhibition} about {work}, {credit_line}?"* (D507)
2. **Claims extracted** — the sentences carrying something checkable: a number, a material, a date, a technique
3. **Challenged** — Serper queries built from *the claim's own terms*, not the work's, so a page disagreeing about those specifics can surface
4. **Adjudicated** — the round-1 answer and the retrieved evidence handed back to Gemini, which marks every claim CONFIRMED / CORRECTED / DISPUTED / UNATTESTED **against the evidence, not from memory**, and only then writes the story

**Michael's rule (c), 2026-08-22:** an unattested claim loses its appeal to authority but keeps its underlying fact where another source corroborates it — and **where sources genuinely disagree, the story says so**, because the disagreement is interesting and shows the accuracy we are aiming at.


---

# Le Lézard aux plumes d’or (The Lizard with Golden Feathers)


## credit_line 2.1 — *evaluative*

> **revolutionized the book as an art form with its deep collaboration**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 3` · story kind **inert** · **tells a disagreement**

### THE STORY

Joan Miró collaborated with art publisher Louis Broder to create *Le Lézard aux plumes d’or* (*The Lizard with Golden Feathers*), pairing his own writing with original color lithographs. The printing was executed in Paris by the printmaker Mourlot. Historical records and auction catalogues disagree on the precise timeline of the work: some sources record suites and plates dating to 1967, while others document the finished portfolio and book appearing in 1971. Sources also diverge on the final composition count, citing editions that contain 15, 18, or 40 lithographs.

<details><summary>Round 1 (before challenge)</summary>

> * Joan Miró originally created an entire suite of lithographs for the project in 1967 to illustrate his own poetic text [PerQueryResult(index="1.1.2", PerQueryResult(index="2.1.2")].
> * After printing the initial run, Miró and publisher Louis Broder discovered a chemical defect in the specially manufactured paper that reacted with and altered the ink colors [PerQueryResult(index="2.1.1", PerQueryResult(index="2.1.4")].
> * Because the printing stones had already been effaced, the collaboration could not simply reprint the original series, leading them to scrap the initial run [PerQueryResult(index="2.1.1", PerQueryResult(index="2.1.2")].
> * Rather than abandoning the costly setback, Miró completely restarted the project, creating an entirely new set of compositions that Mourlot printed for Broder's final 1971 edition [PerQueryResult(index="2.1.1", PerQueryResult(index="2.1.2")].

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

* CONFIRMED Joan Miró created lithographs for *Le Lézard aux plumes d'or* to illustrate his own text — [artsy.net], [parkwestgallery.com], [coleccionbbva.com]
* CONFIRMED The project was published by Louis Broder — [moma.org], [sothebys.com], [artsy.net]
* CONFIRMED Mourlot served as the printer for the publication — [moma.org], [sothebys.com]
* DISPUTED The creation date of the suite is either 1967 or 1971 — [christies.com] and [masterworksfineart.com] date versions/plates to 1967; [choicecontemporary.com], [sothebys.com], [tretyakovgallerymagazine.com], [composition.gallery], and [facebook.com] date the project/book to 1971
* UNATTESTED A chemical defect in the specially manufactured paper reacted with and altered the ink colors — no retrieved source supports this
* UNATTESTED The printing stones had already been effaced, preventing a reprint and forcing the initial run to be scrapped — no retrieved source supports this
* UNATTESTED Miró completely restarted the project and created an entirely new set of compositions after a costly setback — no retrieved source supports this
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** After printing the initial run, Miró and publisher Louis Broder discovered a chemical defect in the specially manufactured paper that reacted with and  
**query:** `"Le Lézard aux plumes d’or" printing publisher paper initial` → 13 relevant sentence(s)

  - `composition.gallery` (unverified) — Le Lézard aux plumes d'or (The Lizard with Golden Feathers) - Illustrated book with 15 lithographs printed in colors, on BFK Rives wove paper - Signed in ...
  - `moma.org` (tier1) — Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ...
  - `moma.org` (tier1) — Publisher Louis Broder , Paris.
  - `moma.org` (tier1) — Printer Mourlot, Paris.

**claim:** Rather than abandoning the costly setback, Miró completely restarted the project, creating an entirely new set of compositions that Mourlot printed fo  
**query:** `"Le Lézard aux plumes d’or" abandoning printed 1971 rather` → 10 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `sothebys.com` (market) — Le lézard aux plumes d'or, a 1971 project published by Louis Broder and printed by Mourlot in Paris.
  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `tretyakovgallerymagazine.com` (unverified) — Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971).

**claim:** Joan Miró originally created an entire suite of lithographs for the project in 1967 to illustrate his own poetic text  
**query:** `"Le Lézard aux plumes d’or" 1967 originally created entire` → 12 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `masterworksfineart.com` (unverified) — Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no.
  - `masterworksfineart.com` (unverified) — Artist: Joan Miró (1893 - 1983).

</details>


## credit_line 2.2 — *evaluative*

> **focusing on the livre d'artiste**

`CONFIRMED 3` · `CORRECTED 1` · `DISPUTED 2` · `UNATTESTED 5` · story kind **inert**

### THE STORY

Joan Miró worked with publisher Louis Broder to create a 1967 first edition of *Le Lézard aux plumes d'or* featuring his own poetry alongside his prints. However, that original 1967 version was lost and differed from the work seen today. While some records trace the project's origins to the 1960s, others place its conception in 1971, when Broder officially released a revised illustrated book. The final 1971 edition was published in a limited run, with sources variously recording edition sizes such as 100 copies.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró wrote the surrealist poem himself and hand-lettered the text across the leaves. 
> 
> The project was originally slated for publication in 1967 after four years of collaboration between Miró and publisher Louis Broder. 
> 
> After printing the first set of lithographs, Miró and Broder discovered that a chemical defect in the chosen paper had altered and compromised the ink colors. 
> 
> Because the original zinc lithography plates had already been effaced, Miró had to redraw completely new compositions from scratch. 
> 
> The revised portfolio was finally printed by Mourlot and issued by Broder in 1971 in an edition of 150 copies.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Joan Miró wrote the poetry himself and combined it with his prints — [choicecontemporary.com]
* UNATTESTED Joan Miró hand-lettered the text across the leaves — no retrieved source supports this
* DISPUTED The project's origins date to 1967 (or earlier) vs. 1971 — [christies.com], [sothebys.com], [gazette-drouot.com], and [phillips.com] note a 1967 first edition/work in the 1960s; [artsy.net] says it was originally conceived in 1971
* CONFIRMED Miró collaborated with publisher Louis Broder on the 1967 edition — [sothebys.com]
* UNATTESTED Miró and Broder worked together for four years prior to 1967 — no retrieved source supports this
* UNATTESTED A chemical defect in the chosen paper altered and compromised the ink colors after the first printing — no retrieved source supports this
* CORRECTED The 1967 first version was lost and different -> [gazette-drouot.com] describes a "lost (and different) first edition" — [gazette-drouot.com]
* UNATTESTED The original zinc lithography plates had already been effaced, forcing Miró to redraw new compositions from scratch — no retrieved source supports this
* CONFIRMED A version of the portfolio was issued by Louis Broder in 1971 — [christies.com], [artsy.net]
* UNATTESTED Mourlot printed the 1971 edition — no retrieved source supports this
* DISPUTED Edition size of the 1971 release was 150 copies — [masterworksfineart.com] cites an edition of 100; no retrieved source mentions 150

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because the original zinc lithography plates had already been effaced, Miró had to redraw completely new compositions from scratch.  
**query:** `"Le Lézard aux plumes d’or" zinc plates effaced original` → 9 relevant sentence(s)

  - `moma.org` (tier1) — Plate (folio 31 verso) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).
  - `choicecontemporary.com` (unverified) — aux plumes d'or (The Lizard with Golden Feathers) created in 1971 as a vibrant fusion of poetry, printmaking, and sculptural techniques.
  - `composition.gallery` (unverified) — Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...
  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

**claim:** The revised portfolio was finally printed by Mourlot and issued by Broder in 1971 in an edition of 150 copies.  
**query:** `"Le Lézard aux plumes d’or" printed 1971 150 copies revised` → 14 relevant sentence(s)

  - `facebook.com` (reject) — ly/6185aJOQd : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs ( ...
  - `bonhams.com` (unverified) — Joan Miró (Spanish, 1893-1983).
  - `bonhams.com` (unverified) — 7, from Le lézard aux plumes d'or (M.
  - `bonhams.com` (unverified) — Lithograph in colors on wove paper with Miró watermark, signed in pencil ...

**claim:** The project was originally slated for publication in 1967 after four years of collaboration between Miró and publisher Louis Broder.  
**query:** `"Le Lézard aux plumes d’or" 1967 publisher project originally` → 9 relevant sentence(s)

  - `christies.com` (market) — Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — The present work is from the first edition of e Lezard aux Plumes d'Or published in 1967.
  - `sothebys.com` (market) — Miró's letters to Louis Broder chronicle the creation of the 1967 edition of Le Lézard aux plumes d'or, now known as Le Lézard aux plumes d'or I.
  - `gazette-drouot.com` (unverified) — An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or.

**claim:** After printing the first set of lithographs, Miró and Broder discovered that a chemical defect in the chosen paper had altered and compromised the ink  
**query:** `"Le Lézard aux plumes d’or" printing paper lithographs broder` → 11 relevant sentence(s)

  - `christies.com` (market) — Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M.
  - `christies.com` (market) — paper wrappers and parchment-covered boards with lithograph signed in pencil.
  - `masterworksfineart.com` (unverified) — Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971.
  - `masterworksfineart.com` (unverified) — from the edition of 100 in pencil in the image lower left.

</details>


## credit_line 4.1 — *evaluative*

> **showcasing how artists express these concepts through their unrivaled creativity**

`CONFIRMED 0` · `CORRECTED 0` · `DISPUTED 2` · `UNATTESTED 3` · story kind **inert** · **tells a disagreement**

### THE STORY

Joan Miró produced *Le Lézard aux plumes d’or* across multiple distinct editions and working phases. Records from the project diverge on its exact development and scope: some sources document an initial version completed by the printer Célestin in 1967 containing 15 or 18 lithographs, while others trace the first version to 1963–1966. A later release followed, dated by different records to 1971 with up to forty color lithographs, or to a 1972 second version (*Lézard II*). Today, surviving impressions exist under both the 1967 and 1971 designations.

<details><summary>Round 1 (before challenge)</summary>

> * Joan Miró created the lithographs to accompany a surrealist poem he had originally written in the late 1930s.
> * The portfolio was originally completed in 1967, but Miró and publisher Louis Broder discovered that defects in the paper stock had degraded the printed colors.
> * Because of these paper flaws, Miró and Broder decided to reject and destroy the entire initial print run.
> * Since the original printing stones and plates had already been ground down or erased, the initial compositions could not be reprinted.
> * Miró was forced to redraw an entirely new set of compositions from scratch, delaying publication until 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
### PART 1 — ADJUDICATE

* UNATTESTED Joan Miró created the lithographs to accompany a surrealist poem he had originally written in the late 1930s. — no retrieved source supports this
* DISPUTED The portfolio was originally completed in 1967, but Miró and publisher Louis Broder discovered that defects in the paper stock had degraded the printed colors. — sothebys.com says printing was finished in 1967 (and multiple sources date versions to 1967 or 1971), while gazette-drouot.com dates "Lézard I" to 1963–1966; paper defects and Louis Broder are not mentioned in the retrieved sources
* UNATTESTED Because of these paper flaws, Miró and Broder decided to reject and destroy the entire initial print run. — no retrieved source supports this
* UNATTESTED Since the original printing stones and plates had already been ground down or erased, the initial compositions could not be reprinted. — no retrieved source supports this
* DISPUTED Miró was forced to redraw an entirely new set of compositions from scratch, delaying publication until 1971. — galeriearenthon.com and gazette-drouot.com confirm multiple distinct versions ("1st version", "Lézard I", and "Lézard II"), but sources dispute the dates and contents across 1967, 1971, and 1972, with plate counts varying between 15, 18, 22, and 40; the claim of being forced to redraw from scratch due to erased plates is not supported

***

###
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The portfolio was originally completed in 1967, but Miró and publisher Louis Broder discovered that defects in the paper stock had degraded the printe  
**query:** `"Le Lézard aux plumes d’or" 1967 publisher paper printed` → 11 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `artsy.net` (market) — From Van der Vorst- Art, Joan Miró, Le Lézard aux plumes d'or (1967), Color lithograph on on wove paper with Miro watermark, 35.5 × 99 cm.
  - `composition.gallery` (unverified) — Le Lézard aux plumes d'or (The Lizard with Golden Feathers) - Illustrated book with 15 lithographs printed in colors, on BFK Rives wove paper - Signed in ...

**claim:** Because of these paper flaws, Miró and Broder decided to reject and destroy the entire initial print run.  
**query:** `"Le Lézard aux plumes d’or" paper reject destroy print` → 9 relevant sentence(s)

  - `gazette-drouot.com` (unverified) — Miró, Joan Le Lézard aux plumes d'or.
  - `gazette-drouot.com` (unverified) — Set of 22 lithographs, including 14 from Lézard I (1963-1966) and 8 from Lézard II (1972).
  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `mchampetier.com` (unverified) — Original signed lithograph de Miro Joan : Le Lézard aux Plumes d'Or, 1967.

**claim:** Miró was forced to redraw an entirely new set of compositions from scratch, delaying publication until 1971.  
**query:** `"Le Lézard aux plumes d’or" delaying 1971 forced redraw` → 7 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `martinlawrence.com` (unverified) — "Untitled (M.794)" is a lithograph on Kochi Japan paper created by Joan Miró in 1971.
  - `martinlawrence.com` (unverified) — From the edition of 290, the artwork is signed 'Miró' lower right and ...
  - `choicecontemporary.com` (unverified) — Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).

</details>


## credit_line 5.1 — *anchored*

> **Broder's pivotal decision**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 4` · story kind **active**

### THE STORY

Publisher Louis Broder commissioned Joan Miró to create an illustrated book based on the artist's own poems. Miró completed a first version of the work, known as *Le Lézard aux plumes d'or I*, in 1967. After that initial edition was lost, Miró produced a second, different series of lithographs. The project culminated in 1971 with Broder's publication of the final book, *Le Lézard aux plumes d'or II*.

<details><summary>Round 1 (before challenge)</summary>

> Publisher Louis Broder commissioned Joan Miró to create a lavish illustrated book accompanying Miró's own original poem. 
> 
> Miró completed a full initial set of lithographs in 1967 at the Mourlot atelier. 
> 
> After the run was pulled, Broder and Miró discovered that a manufacturing defect in the paper was causing the printed colors to alter and deteriorate. 
> 
> Broder made the pivotal decision to reject the entire printing and destroy the edition rather than publish an imperfect work. 
> 
> Because the original lithographic stones had already been effaced, Miró had to redraw completely new compositions from scratch, delaying the final publication until 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Publisher Louis Broder commissioned Joan Miró to create an illustrated book accompanying Miró's own original poem. — [parkwestgallery.com], [facebook.com]
* CONFIRMED Miró produced an initial edition of color lithographs for *Le Lézard aux plumes d’or* in 1967 (referred to as a first edition / *Le Lézard aux plumes d'or I*). — [sothebys.com], [gazette-drouot.com], [instagram.com]
* UNATTESTED Miró completed the initial set at the Mourlot atelier. — no retrieved source supports this (mourloteditions.com only notes Broder as publisher for a pulled print, not that the 1967 set was made at the Mourlot atelier)
* UNATTESTED A manufacturing defect in the paper caused the printed colors to alter and deteriorate. — no retrieved source supports this
* UNATTESTED Broder made the pivotal decision to reject the entire printing and destroy the edition rather than publish an imperfect work. — no retrieved source supports this
* UNATTESTED The original lithographic stones had already been effaced, forcing Miró to redraw completely new compositions from scratch. — no retrieved source supports this
* CONFIRMED The final illustrated book edition (*Le Lézard aux plumes d'or II*) was published in 1971, containing different compositions from the lost 1967 first edition. — [instagram.com], [parkwestgallery.com], [gazette-drouot.com]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Broder made the pivotal decision to reject the entire printing and destroy the edition rather than publish an imperfect work.  
**query:** `"Le Lézard aux plumes d’or" reject printing destroy publish` → 11 relevant sentence(s)

  - `facebook.com` (reject) — publication of the book “Le Lézard aux plumes d'or”, published by Louis Broder.
  - `facebook.com` (reject) — In it, the artist illustrated his own poems.
  - `gazette-drouot.com` (unverified) — An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or.
  - `mchampetier.com` (unverified) — Original lithograph de Miro Joan : Le lézard aux plumes d'or, plate 17.

**claim:** Because the original lithographic stones had already been effaced, Miró had to redraw completely new compositions from scratch, delaying the final pub  
**query:** `"Le Lézard aux plumes d’or" stones effaced delaying 1971` → 2 relevant sentence(s)

  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper ...
  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper ...

**claim:** Publisher Louis Broder commissioned Joan Miró to create a lavish illustrated book accompanying Miró's own original poem.  
**query:** `"Le Lézard aux plumes d’or" publisher commissioned broder create` → 15 relevant sentence(s)

  - `facebook.com` (reject) — publication of the book “Le Lézard aux plumes d'or”, published by Louis Broder.
  - `facebook.com` (reject) — In it, the artist illustrated his own poems.
  - `sothebys.com` (market) — Miró's letters to Louis Broder chronicle the creation of the 1967 edition of Le Lézard aux plumes d'or, now known as Le Lézard aux plumes d'or I.
  - `parkwestgallery.com` (unverified) — Le Lezard aux Plumes d'or II” (1971), Joan Miro.

**claim:** After the run was pulled, Broder and Miró discovered that a manufacturing defect in the paper was causing the printed colors to alter and deteriorate.  
**query:** `"Le Lézard aux plumes d’or" paper printed pulled broder` → 15 relevant sentence(s)

  - `liveauctioneers.com` (market) — Joan Miro (Spanish, 1893-1983) abstract color lithograph on Japan Nacre paper, plate 14 from Le Lezard aux plumes d'or (The Lizard with Golden Feathers).
  - `swanngalleries.com` (unverified) — JOAN MIRÓ Le Lézard aux Plumes d'Or.
  - `swanngalleries.com` (unverified) — 360x495 mm; 14 1/4x19 1/2 inches, full margins.
  - `instagram.com` (reject) — Joan Miró – Le Lézard aux plumes d'or (1967)⁣ ⁣ A stunning color lithograph on wove paper with the Miró watermark, published by Louis Broder ...

</details>


## credit_line 5.2 — *evaluative*

> **allowing the artist to blend visual and textual narratives seamlessly**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 3` · story kind **inert**

### THE STORY

In 1967, printing was completed on an edition of *Le Lézard aux plumes d’or* created by Joan Miró in collaboration with publisher Louis Broder. Shortly after the run was finished, Miró and Broder discovered a defect in the paper that distorted the printed colors. Because of this error, the original 1967 project was halted. The artist and publisher then reworked the project to produce and release the finished edition of color lithographs in 1971.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró served as both the author and the illustrator of *Le Lézard aux plumes d’or*, hand-writing the poetic text directly across the lithographic plates rather than using set typography. 
> 
> Miró originally prepared an entire edition of the work around 1967 in collaboration with publisher Louis Broder and the Mourlot workshop. 
> 
> Broder and Miró halted and abandoned the completed 1967 run after discovering a defect in the paper that distorted the intended printing colors. 
> 
> Because the original printing plates had already been discarded, Miró was forced to redraw all of the compositions from scratch to produce the finished 1971 edition.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED Joan Miró served as both the author and the illustrator of *Le Lézard aux plumes d’or*, hand-writing the poetic text directly across the lithographic plates rather than using set typography. — no retrieved source supports this
* CONFIRMED Miró originally prepared an entire edition of the work around 1967 in collaboration with publisher Louis Broder — [sothebys.com], [instagram.com]
* UNATTESTED Miró collaborated specifically with the Mourlot workshop for the 1967 printing — no retrieved source supports this (sources name Celestin / Louis Broder)
* CONFIRMED Broder and Miró halted and abandoned the completed 1967 run after discovering an error in the paper that distorted the colors — [sothebys.com]
* CONFIRMED Miró produced the finished edition in 1971 — [facebook.com], [instagram.com], [masterworksfineart.com], [artsy.net]
* UNATTESTED Because the original printing plates had already been discarded, Miró was forced to redraw all of the compositions from scratch — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Broder and Miró halted and abandoned the completed 1967 run after discovering a defect in the paper that distorted the intended printing colors.  
**query:** `"Le Lézard aux plumes d’or" halted abandoned 1967 paper` → 8 relevant sentence(s)

  - `facebook.com` (reject) — 1967 hand-signed lithograph image size: 13.75 x 19.75" Untitled (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi ...
  - `instagram.com` (reject) — Joan Miró – Le Lézard aux plumes d'or (1967)⁣ ⁣ A stunning color lithograph on wove paper with the Miró watermark, published by Louis Broder ...
  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `invaluable.com` (market) — Miró, Joan (1893-1983) "Le Lézard aux plumes d'or" 1967-1971, color ...

**claim:** Because the original printing plates had already been discarded, Miró was forced to redraw all of the compositions from scratch to produce the finishe  
**query:** `"Le Lézard aux plumes d’or" printing plates 1971 original` → 10 relevant sentence(s)

  - `choicecontemporary.com` (unverified) — Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).
  - `masterworksfineart.com` (unverified) — Title: Plate III from Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ; Reference: C.
  - `artsy.net` (market) — From Le Coin des Arts, Joan Miró, Le lézard aux plumes d'or (1971), Lithograph on paper, 41 × 56 cm.
  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.

**claim:** Miró originally prepared an entire edition of the work around 1967 in collaboration with publisher Louis Broder and the Mourlot workshop.  
**query:** `"Le Lézard aux plumes d’or" 1967 publisher originally prepared` → 13 relevant sentence(s)

  - `sothebys.com` (market) — In 1967, Celestin finished printing Le Lézard aux plumes d'or.
  - `sothebys.com` (market) — Shortly afterwards, Miró and Broder discovered an error in the paper distorted the ...
  - `artsy.net` (market) — Available for sale from American Fine Art Inc., Joan Miró, Le Lézard Aux Plumes D'or (1971), Lithograph, 13 × 19 in.
  - `christies.com` (market) — Joan Miró (1893-1983) Composition pour 'Le lézard aux plumes d'or' signed and dated 'Miró III/64' (lower left) oil and wax crayon on paper 14 x 19 7/8 in.

**claim:** Joan Miró served as both the author and the illustrator of *Le Lézard aux plumes d’or*, hand-writing the poetic text directly across the lithographic   
**query:** `"Le Lézard aux plumes d’or" plates served author illustrator` → 10 relevant sentence(s)

  - `facebook.com` (reject) — ly/6185aJOQd : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs ( ...
  - `tretyakovgallerymagazine.com` (unverified) — Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971).
  - `emuseum.toledomuseum.org` (unverified) — Le lézard aux plumes d'or.
  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on ...

</details>


## credit_line 6.1 — *anchored*

> **Freud's exploration of**

`CONFIRMED 0` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 1` · story kind **none**

### THE STORY

No reliable information about this work was provided in the sources. As a result, no verified account of its creation or history can be given at this time.

<details><summary>Round 1 (before challenge)</summary>

> NO RELIABLE INFORMATION

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

UNATTESTED NO RELIABLE INFORMATION — no retrieved source supports this
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

</details>


## credit_line 8.1 — *anchored*

> **drawing you into the surreal world that Joan Miró has crafted**

`CONFIRMED 0` · `CORRECTED 0` · `DISPUTED 3` · `UNATTESTED 2` · story kind **active**

### THE STORY

Joan Miró created *Le Lézard aux plumes d’or* to accompany a series of his own poems, collaborating with publisher Louis Broder on editions dating to 1967 and 1971. While auction and collection records document impressions surviving from 1967 as part of a set of 18 lithographs, other sources record the finalized 1971 publication as containing 15 color lithographs, with some catalog descriptions listing up to 40 plates and covers. Miró printed these compositions on wove paper carrying his own custom watermark. Both the 1967 prints and the 1971 book release remain central examples of his combined work as writer and printmaker.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró originally created eighteen color lithographs for the project in 1967 to accompany a surrealist poem he had written himself.
> 
> After the initial printing was completed, Miró and publisher Louis Broder discovered defects in the paper that caused the ink colors to deteriorate.
> 
> Because of the defective paper, Miró and Broder rejected the entire 1967 printing and ordered the sheets to be destroyed.
> 
> The original lithographic stones had already been effaced, making an exact reprint of the 1967 compositions impossible.
> 
> The project was delayed for four years until Miró completely redesigned and drew a brand-new set of lithographs, finally published by Broder in 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
### PART 1 — ADJUDICATE

* DISPUTED Joan Miró originally created eighteen color lithographs for the project in 1967 to accompany a surrealist poem he had written himself. — [christies.com] refers to the 1967 version as "from the set of 18"; [artsy.net] notes it illustrates "the artist's own poems"; but other sources describe the editions as having 15 lithographs ([composition.gallery], [artsy.net]) or 40 color lithographs ([facebook.com], [instagram.com]).
* UNATTESTED After the initial printing was completed, Miró and publisher Louis Broder discovered defects in the paper that caused the ink colors to deteriorate. — no retrieved source supports this
* DISPUTED Because of the defective paper, Miró and Broder rejected the entire 1967 printing and ordered the sheets to be destroyed. — [artsy.net], [invaluable.com], [instagram.com], and [christies.com] document surviving 1967 prints in circulation, while no retrieved source mentions destruction of the sheets.
* UNATTESTED The original lithographic stones had already been effaced, making an exact reprint of the 1967 compositions impossible. — no retrieved source supports this
* DISPUTED The project was delayed for four years until Miró completely redesigned and drew a brand-new set of lithographs, finally published by Broder in 1971. — [facebook.com], [app.mearto.com], [choicecontemporary.com], and [zuckerartbooks.com] confirm a 1971 publication date by Broder following the 1967 work, but the retrieved sources do not document why the project spanned 1967 to 1971 or whether it was a brand-new redesign.

---

###
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because of the defective paper, Miró and Broder rejected the entire 1967 printing and ordered the sheets to be destroyed.  
**query:** `"Le Lézard aux plumes d’or" paper rejected 1967 printing` → 11 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `artsy.net` (market) — From Forum Auctions, Joan Miró, 1 plate, Le Lézard aux Plumes D'Or (Mourlot 448) (1967), Lithograph printed in colours,, 35 × 50 cm.
  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `invaluable.com` (market) — Joan Miró (1893-1983) Untitled, from Le lézard aux plumes d'or (Mourlot 525; Cramer bk.148), 1967.

**claim:** After the initial printing was completed, Miró and publisher Louis Broder discovered defects in the paper that caused the ink colors to deteriorate.  
**query:** `"Le Lézard aux plumes d’or" printing publisher paper initial` → 13 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `composition.gallery` (unverified) — Le Lézard aux plumes d'or (The Lizard with Golden Feathers) - Illustrated book with 15 lithographs printed in colors, on BFK Rives wove paper - Signed in ...
  - `artsy.net` (market) — UNTITLED from Le Lezard aux Plumes d'Or, 1971 ; Materials.

**claim:** The original lithographic stones had already been effaced, making an exact reprint of the 1967 compositions impossible.  
**query:** `"Le Lézard aux plumes d’or" stones effaced 1967 original` → 4 relevant sentence(s)

  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper ...
  - `imprint.swanngalleries.com` (unverified) — Le Lézard aux Plumes d'Or.
  - `instagram.com` (reject) — Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's vellum ...
  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper ...

**claim:** The project was delayed for four years until Miró completely redesigned and drew a brand-new set of lithographs, finally published by Broder in 1971.  
**query:** `"Le Lézard aux plumes d’or" delayed published 1971 project` → 10 relevant sentence(s)

  - `moma.org` (tier1) — Plate (folio 31 verso) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).
  - `choicecontemporary.com` (unverified) — Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...
  - `artsy.net` (market) — One of fifteen color lithographs illustrating the text Le Lezard aux Plumes d'Or, a series of the artist's own poems.
  - `artsy.net` (market) — Published by Louis Broder, Paris; printed ...

</details>


## credit_line 10.1 — *anchored*

> **Louis Broder, a figure renowned for his commitment to the art of the book**

`CONFIRMED 1` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 3` · story kind **active** · **tells a disagreement**

### THE STORY

Joan Miró created *Le Lézard aux plumes d’or* alongside publisher Louis Broder to illustrate the artist's own handwritten poems. Sources disagree on the timeline of the initial attempt: some records state the project embarked in 1963, while others date the first suite of lithographs to 1967. That first version became a lost and altered edition, forcing Miró to execute entirely new, different compositions. Broder finally published the completed book in 1971.

<details><summary>Round 1 (before challenge)</summary>

> * Joan Miró originally completed a first suite of color lithographs for the project in 1967 to illustrate his own handwritten poetic text.
> * Publisher Louis Broder and Miró discovered after printing that defects in the paper were causing chemical deterioration and discoloration of the inks.
> * Because of this flaw, Broder and Miró refused the edition and ordered the defective printed sheets destroyed.
> * Since the original lithographic stones had already been planed down and erased, the original images could not simply be reprinted.
> * Miró was forced to redraw and execute entirely new compositions, delaying the final publication of the book until 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* DISPUTED Joan Miró originally completed a first suite of color lithographs for the project in 1967 to illustrate his own handwritten poetic text. — [bonhams.com] states work on the first edition embarked in 1963; [christies.com] and [artsy.net] date the first suite to 1967 (while [facebook.com] and [coleccionbbva.com] confirm it illustrates his own handwritten poems).
* UNATTESTED Publisher Louis Broder and Miró discovered after printing that defects in the paper were causing chemical deterioration and discoloration of the inks. — no retrieved source supports this
* UNATTESTED Because of this flaw, Broder and Miró refused the edition and ordered the defective printed sheets destroyed. — no retrieved source supports this
* UNATTESTED Since the original lithographic stones had already been planed down and erased, the original images could not simply be reprinted. — no retrieved source supports this
* CONFIRMED Miró was forced to redraw and execute entirely new compositions, delaying the final publication of the book until 1971. — [gazette-drouot.com] confirms a "lost (and different) first edition", and [artsy.net], [invaluable.com], and [etsy.com] confirm the published edition dates to 1971.

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Publisher Louis Broder and Miró discovered after printing that defects in the paper were causing chemical deterioration and discoloration of the inks.  
**query:** `"Le Lézard aux plumes d’or" publisher printing paper broder` → 10 relevant sentence(s)

  - `bonhams.com` (unverified) — In 1963, Joan Miro and his publisher Louis Broder embarked on the first edition of "Le Lezard aux plumes d'or", a series of 18 colour lithographs to accompany a ...
  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi Japan paper image size: 13.25 x 19".
  - `etsy.com` (unverified) — Joan Miró — Le Lézard aux plumes d'or (1971) #4 — Original Color Lithograph ...
  - `etsy.com` (unverified) — Publisher: Louis Broder, Paris Edition: Limited to 195 proofs

**claim:** Because of this flaw, Broder and Miró refused the edition and ordered the defective printed sheets destroyed.  
**query:** `"Le Lézard aux plumes d’or" refused printed destroyed broder` → 15 relevant sentence(s)

  - `gazette-drouot.com` (unverified) — An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or.
  - `facebook.com` (reject) — Le Lézard aux plumes d'or”, published by Louis Broder.
  - `facebook.com` (reject) — In it, the artist illustrated his own poems.
  - `facebook.com` (reject) — The friendship between Joan Miró and Louis Broder lasted ...

**claim:** Miró was forced to redraw and execute entirely new compositions, delaying the final publication of the book until 1971.  
**query:** `"Le Lézard aux plumes d’or" delaying 1971 forced redraw` → 7 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — It consists of fifteen lithographs, accompanied by a poem by Miró, handwritten by the artist himself
  - `martinlawrence.com` (unverified) — "Untitled (M.794)" is a lithograph on Kochi Japan paper created by Joan Miró in 1971.
  - `martinlawrence.com` (unverified) — From the edition of 290, the artwork is signed 'Miró' lower right and ...
  - `choicecontemporary.com` (unverified) — Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).

**claim:** Joan Miró originally completed a first suite of color lithographs for the project in 1967 to illustrate his own handwritten poetic text.  
**query:** `"Le Lézard aux plumes d’or" 1967 originally completed lithographs` → 10 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `masterworksfineart.com` (unverified) — Le Lezard Aux Plumes d'Or (The Lizard with Golden Feathers), Pl.
  - `artsy.net` (market) — From Van der Vorst- Art, Joan Miró, Le Lézard aux plumes d'or (1967), Color lithograph on on wove paper with Miro watermark, 35.5 × 99 cm.

</details>


## credit_line 10.2 — *evaluative*

> **the exhibition highlights**

`CONFIRMED 4` · `CORRECTED 1` · `DISPUTED 0` · `UNATTESTED 4` · story kind **active**

### THE STORY

In 1967, Joan Miró and printer Celestin completed a first edition of lithographs to accompany a poem written by Miró for publisher Louis Broder. Shortly after printing, Miró and Broder discovered an error in the paper that distorted the lithographs. While the 1967 first edition was largely lost or abandoned, individual surviving plates from that run still surface in collections today. Miró went back to work to produce a different, completed edition, which Broder published on Rives paper in 1971.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró not only created the lithographs but also wrote the original surrealist poem and hand-wrote the text across the pages.
> 
> Miró initially completed a full first edition of lithographs for the project in 1967.
> 
> A defect in the paper's chemical composition was discovered after printing, which caused unwanted color alterations across the impressions.
> 
> Because the original printing plates had already been erased or scratched off, Miró and publisher Louis Broder decided to destroy nearly the entire 1967 print run.
> 
> Miró had to restart the entire visual suite from scratch, resulting in the completed 1971 publication on BFK Rives paper.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Joan Miró wrote the poem for the project — [theredfinch.net]
* UNATTESTED Joan Miró hand-wrote the text across the pages — no retrieved source supports this
* CONFIRMED Miró completed a first edition of lithographs for the project in 1967 — [sothebys.com], [christies.com], [gazette-drouot.com]
* CONFIRMED A defect/error in the paper distorted the lithographs after printing — [sothebys.com]
* UNATTESTED The defect was specifically in the paper's chemical composition causing unwanted color alterations — no retrieved source supports this
* UNATTESTED The original printing plates had already been erased or scratched off — no retrieved source supports this
* UNATTESTED Miró and publisher Louis Broder decided to destroy nearly the entire 1967 print run — no retrieved source supports this
* CORRECTED The 1967 edition was completely destroyed -> A lost (and different) first edition existed, though some plates and individual prints from 1967 still survive — [gazette-drouot.com], [christies.com], [invaluable.com], [artsy.net]
* CONFIRMED The completed publication was published in 1971 by Louis Broder on Rives paper — [theredfinch.net], [bidsquare.com], [composition.gallery], [facebook.com]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because the original printing plates had already been erased or scratched off, Miró and publisher Louis Broder decided to destroy nearly the entire 19  
**query:** `"Le Lézard aux plumes d’or" printing plates erased publisher` → 13 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `gazette-drouot.com` (unverified) — An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or.

**claim:** Miró had to restart the entire visual suite from scratch, resulting in the completed 1971 publication on BFK Rives paper.  
**query:** `"Le Lézard aux plumes d’or" 1971 rives paper restart` → 11 relevant sentence(s)

  - `composition.gallery` (unverified) — Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...
  - `facebook.com` (reject) — ly/6185aJOQd : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs ( ...
  - `instagram.com` (reject) — Joan Miró – Le Lézard aux plumes d'or (1967)⁣ ⁣ A stunning color lithograph on wove paper with the Miró watermark, published by Louis Broder ...
  - `bidsquare.com` (unverified) — Le Lezard Aux Plumes D'or; Medium: Original lithograph on Rives paper; Condition: Excellent.

**claim:** A defect in the paper's chemical composition was discovered after printing, which caused unwanted color alterations across the impressions.  
**query:** `"Le Lézard aux plumes d’or" paper printing defect paper's` → 14 relevant sentence(s)

  - `swanngalleries.com` (unverified) — JOAN MIRÓ Le Lézard aux Plumes d'Or.
  - `swanngalleries.com` (unverified) — 342x485 mm; 13 1/2x19 1/8 inches, full margins.
  - `mchampetier.com` (unverified) — Le Lézard aux Plumes d'Or, Poster 1971 ; Number : Without ; Paper : Coated paper ; Illustration size : 47,5x 52,5 cm ; Paper size (or piece size) : 49,5 x 70 cm ...
  - `invaluable.com` (market) — Joan Miró (1893-1983) Untitled, from Le lézard aux plumes d'or (Mourlot 525; Cramer bk.148), 1967.

**claim:** Miró initially completed a full first edition of lithographs for the project in 1967.  
**query:** `"Le Lézard aux plumes d’or" 1967 initially completed edition` → 12 relevant sentence(s)

  - `christies.com` (market) — Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — The present work is from the first edition of e Lezard aux Plumes d'Or published in 1967.
  - `artsy.net` (market) — Joan Miró, 'Le Lézard aux Plumes d'Or (one plate)' · Increased Interest.
  - `artsy.net` (market) — Le Lézard aux Plumes d'Or (one plate), 1967.

</details>


## credit_line 11.1 — *anchored*

> **Broder's decision to engage Miró was pivotal**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 5` · story kind **active**

### THE STORY

Publisher Louis Broder collaborated with Joan Miró to create *Le Lézard aux plumes d’or*, an illustrated book featuring the artist's own poetry. In 1967, printer Celestin completed a run of the lithographs, but Miró and Broder soon discovered an error in the paper that distorted the prints. The artists had to address the defective paper before the work could finally be released. Sources date the completed publication to 1971, though some records cite second-version plates from 1972.

<details><summary>Round 1 (before challenge)</summary>

> Publisher Louis Broder engaged Joan Miró to create an illustrated book based on the artist's own surrealist poem, which Miró had written between 1936 and 1939.
> 
> Miró completed a first suite of lithographs for the project in 1967.
> 
> Shortly after printing, Broder and Miró discovered a defect in the specially manufactured paper that caused chemical reactions and altered the colors of the inks.
> 
> Because the initial printing was deemed unusable, Broder and Miró rejected the run and ordered the printed sheets destroyed.
> 
> The original lithographic stones had already been effaced, preventing a direct reprinting of the first version.
> 
> Miró was forced to redraw an entirely new set of compositions, delaying the final publication until 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Publisher Louis Broder published an illustrated book based on Joan Miró's own poems — [facebook.com]
* UNATTESTED Miró had written the poem between 1936 and 1939 — no retrieved source supports this
* CONFIRMED Miró / Celestin completed a printing of lithographs for the project in 1967 — [sothebys.com]
* CONFIRMED Shortly afterwards, Broder and Miró discovered an error in the paper that distorted the lithographs — [sothebys.com]
* UNATTESTED The defect caused chemical reactions and altered the colors of the inks — no retrieved source supports this specific phrasing (only that an error in the paper distorted the lithographs)
* UNATTESTED Broder and Miró rejected the run and ordered the printed sheets destroyed — no retrieved source supports this
* UNATTESTED The original lithographic stones had already been effaced, preventing a direct reprinting of the first version — no retrieved source supports this
* UNATTESTED Miró was forced to redraw an entirely new set of compositions — no retrieved source supports this
* DISPUTED The final publication / completion year was 1971 — [facebook.com], [instagram.com], and [artnet.com] date the finished illustrated book/lithographs to 1971; [gazette-drouot.com] lists plates from "Lézard II" dated to 1972

---

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because the initial printing was deemed unusable, Broder and Miró rejected the run and ordered the printed sheets destroyed.  
**query:** `"Le Lézard aux plumes d’or" printing rejected printed destroyed` → 12 relevant sentence(s)

  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `gazette-drouot.com` (unverified) — Miró, Joan Le Lézard aux plumes d'or.
  - `gazette-drouot.com` (unverified) — Set of 22 lithographs, including 14 from Lézard I (1963-1966) and 8 from Lézard II (1972).
  - `michelfillion.com` (unverified) — "Le lézard aux plumes d'or".

**claim:** Publisher Louis Broder engaged Joan Miró to create an illustrated book based on the artist's own surrealist poem, which Miró had written between 1936   
**query:** `"Le Lézard aux plumes d’or" publisher 1936 1939 broder` → 19 relevant sentence(s)

  - `facebook.com` (reject) — book “Le Lézard aux plumes d'or”, published by Louis Broder.
  - `facebook.com` (reject) — In it, the artist illustrated his own poems.
  - `facebook.com` (reject) — The friendship between Joan Miró and Louis Broder ...
  - `facebook.com` (reject) — book “Le Lézard aux plumes d'or”, published by Louis Broder.

**claim:** Shortly after printing, Broder and Miró discovered a defect in the specially manufactured paper that caused chemical reactions and altered the colors   
**query:** `"Le Lézard aux plumes d’or" printing paper shortly broder` → 14 relevant sentence(s)

  - `sothebys.com` (market) — In 1967, Celestin finished printing Le Lézard aux plumes d'or.
  - `sothebys.com` (market) — Shortly afterwards, Miró and Broder discovered an error in the paper distorted the lithographs' ...
  - `christies.com` (market) — Joan Miró (1893-1983) Composition pour 'Le lézard aux plumes d'or' signed and dated 'Miró III/64' (lower left) oil and wax crayon on paper 14 x 19 7/8 in.
  - `artnet.com` (market) — Untitled (from Le Lézard aux Plumes d'Or), 1971.

**claim:** The original lithographic stones had already been effaced, preventing a direct reprinting of the first version.  
**query:** `"Le Lézard aux plumes d’or" stones effaced original lithographic` → 4 relevant sentence(s)

  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front ...
  - `imprint.swanngalleries.com` (unverified) — Le Lézard aux Plumes d'Or.
  - `instagram.com` (reject) — Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's vellum.
  - `instagram.com` (reject) — : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front ...

</details>


## credit_line 11.2 — *evaluative*

> **blending visual and textual narratives seamlessly**

`CONFIRMED 1` · `CORRECTED 1` · `DISPUTED 1` · `UNATTESTED 3` · story kind **inert** · **tells a disagreement**

### THE STORY

Joan Miró collaborated with art publisher Louis Broder to pair his own poems with original lithographs for *Le Lézard aux plumes d’or*. Sources disagree on the fate of the project's first 1967 version: some record that an initial edition was published that year, while others state it was canceled after early trial prints yielded only a heavy image. Ultimately, an edition of the illustrated work was published in 1971.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró originally created a full set of lithographs in 1967 to illustrate his own poetry for publisher Louis Broder. 
> 
> After printing, Miró and Broder discovered a defect in the paper manufacturing that altered the ink colors. 
> 
> Because the original printing stones had already been effaced, Miró and Broder chose to destroy the entire initial run rather than release a flawed edition. 
> 
> Miró then undertook the laborious task of drawing an entirely new set of lithographs from scratch, delaying the final publication until 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

CONFIRMED Joan Miró created a set of lithographs to illustrate his own poetry for publisher Louis Broder — galeriearenthon.com
DISPUTED The initial 1967 edition was destroyed/canceled vs. published — imprint.swanngalleries.com says it was canceled after a few trials because printing gave only a heavy image; christies.com says the present work is from the first edition published in 1967
UNATTESTED After printing, Miró and Broder discovered a defect in the paper manufacturing that altered the ink colors — no retrieved source supports this
UNATTESTED Because the original printing stones had already been effaced, Miró and Broder chose to destroy the entire initial run rather than release a flawed edition — no retrieved source supports this
UNATTESTED Miró then undertook the laborious task of drawing an entirely new set of lithographs from scratch — no retrieved source supports this
CORRECTED delaying the final publication until 1971 -> publication occurred in 1971 — composition.gallery, phillips.com, scribd.com
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because the original printing stones had already been effaced, Miró and Broder chose to destroy the entire initial run rather than release a flawed ed  
**query:** `"Le Lézard aux plumes d’or" printing stones effaced destroy` → 2 relevant sentence(s)

  - `imprint.swanngalleries.com` (unverified) — Le Lézard aux Plumes d'Or.
  - `imprint.swanngalleries.com` (unverified) — printing it gave only a heavy image and was canceled after a few trial ...

**claim:** Joan Miró originally created a full set of lithographs in 1967 to illustrate his own poetry for publisher Louis Broder.  
**query:** `"Le Lézard aux plumes d’or" 1967 publisher originally created` → 12 relevant sentence(s)

  - `christies.com` (market) — Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — The present work is from the first edition of e Lezard aux Plumes d'Or published in 1967.
  - `composition.gallery` (unverified) — Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...
  - `galeriearenthon.com` (unverified) — Le Lézard aux plumes d'or is a collaboration between Miró and the art publisher Louis Broder.

**claim:** After printing, Miró and Broder discovered a defect in the paper manufacturing that altered the ink colors.  
**query:** `"Le Lézard aux plumes d’or" printing paper broder discovered` → 13 relevant sentence(s)

  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi Japan paper image size: 13.25 x 19".
  - `etsy.com` (unverified) — The artwork includes black.
  - `etsy.com` (unverified) — Joan Miró — Le Lézard aux plumes d'or (1971) #2 — Original Color ...
  - `composition.gallery` (unverified) — It can be used to print artwork or text onto paper or other suitable materials.

**claim:** Miró then undertook the laborious task of drawing an entirely new set of lithographs from scratch, delaying the final publication until 1971.  
**query:** `"Le Lézard aux plumes d’or" delaying 1971 undertook laborious` → 5 relevant sentence(s)

  - `scribd.com` (unverified) — realized a rhythmic unity between writing and drawing.
  - `scribd.com` (unverified) — Miró's Lizard with Golden Feathers (Le Lézard aux plumes d'or), pub- lished in 1971, is a minimally ...
  - `yumpu.com` (unverified) — LE LEZARD AUX PLUMES D'OR (M.
  - `yumpu.com` (unverified) — Color lithograph, 1971, on wove paper with the Miro<br />.

</details>


## credit_line 12.1 — *anchored*

> **Boris Fridman, a supporter of the art community**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 4` · story kind **inert** · **tells a disagreement**

### THE STORY

Joan Miró collaborated with art publisher Louis Broder to create the illustrated book *Le Lézard aux plumes d’or*, combining his own written text with his original color lithographs. Records dispute when this project began: one source dates the start of their first edition of eighteen lithographs to 1963, while auction records document prints from the set created in 1967. A subsequent edition of lithographs for the work was completed and released in 1971.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró originally created an initial version of the lithographs for this project in 1967. 
> 
> After printing began, Miró and publisher Louis Broder discovered manufacturing defects in the paper that altered and degraded the colors of the inks. 
> 
> Because the initial run had to be abandoned and the original lithographic stones had already been effaced, Miró had to start over entirely and produce brand-new lithographs for the 1971 release. 
> 
> The book is uniquely personal because the accompanying poetic text was written by Miró himself between 1936 and 1939, rather than adapted from another author. 
> 
> Collector Boris Fridman, who founded one of Russia’s earliest private personal computer enterprises, spent decades collecting and championing 20th-century *livres d’artiste* before donating works to major museum collections.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

DISPUTED Joan Miró originally created an initial version in 1967 — bonhams.com says he and publisher Louis Broder embarked on the first edition in 1963; christies.com and masterworksfineart.com date lithographs from this set/series to 1967
UNATTESTED After printing began, Miró and publisher Louis Broder discovered manufacturing defects in the paper that altered and degraded the colors of the inks. — no retrieved source supports this
UNATTESTED Because the initial run had to be abandoned and the original lithographic stones had already been effaced, Miró had to start over entirely and produce brand-new lithographs for the 1971 release. — no retrieved source supports this
CONFIRMED A release/edition was produced in 1971 — facebook.com, etsy.com, invaluable.com, artsy.net, museoreinasofia.es, zuckerartbooks.com
CONFIRMED Le Lézard aux plumes d'or was created in collaboration with publisher Louis Broder — bonhams.com, facebook.com, artsy.net
CONFIRMED The accompanying text was written by Miró himself — artsy.net ("combines the artist's illustrations with his [own text]")
UNATTESTED The text was written between 1936 and 1939 — no retrieved source supports this
UNATTESTED Collector Boris Fridman founded one of Russia’s earliest private personal computer enterprises and collected livres d’artiste before donating works to museums — no retrieved source supports this
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Because the initial run had to be abandoned and the original lithographic stones had already been effaced, Miró had to start over entirely and produce  
**query:** `"Le Lézard aux plumes d’or" abandoned stones effaced 1971` → 0 relevant sentence(s)


**claim:** After printing began, Miró and publisher Louis Broder discovered manufacturing defects in the paper that altered and degraded the colors of the inks.  
**query:** `"Le Lézard aux plumes d’or" printing publisher paper broder` → 10 relevant sentence(s)

  - `bonhams.com` (unverified) — In 1963, Joan Miro and his publisher Louis Broder embarked on the first edition of "Le Lezard aux plumes d'or", a series of 18 colour lithographs to accompany a ...
  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi Japan paper image size: 13.25 x 19".
  - `etsy.com` (unverified) — The artwork includes black.
  - `etsy.com` (unverified) — Joan Miró — Le Lézard aux plumes d'or (1971) #2 — Original Color ...

**claim:** The book is uniquely personal because the accompanying poetic text was written by Miró himself between 1936 and 1939, rather than adapted from another  
**query:** `"Le Lézard aux plumes d’or" 1936 1939 uniquely personal` → 12 relevant sentence(s)

  - `facebook.com` (reject) — Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper front and cover); publisher's ...
  - `museoreinasofia.es` (unverified) — Joan Miró, Le lézard aux plumes d'or (detail), 1971.
  - `museoreinasofia.es` (unverified) — Joan Miró, Sans titre ...
  - `zuckerartbooks.com` (unverified) — Joan Miro' Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers),, 1971 236.

**claim:** Joan Miró originally created an initial version of the lithographs for this project in 1967.  
**query:** `"Le Lézard aux plumes d’or" 1967 originally created initial` → 11 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `artsy.net` (market) — Le Lézard aux plumes d'or is the result of a collaboration between Miró and art publisher Louis Broder.
  - `artsy.net` (market) — The book combines the artist's illustrations with his ...

</details>


## credit_line 12.2 — *anchored*

> **Boston's holdings**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 2` · `UNATTESTED 5` · story kind **active** · **tells a disagreement**

### THE STORY

Joan Miró created *Le Lézard aux plumes d’or* (The Lizard with Golden Feathers) as an illustrated series based on his own poetic writings. The project was printed in Paris by Mourlot and published by Louis Broder. Sources disagree on the timeline and contents of the final release: some records date initial plates to 1967 while others place the edition entirely in 1971, and accounts vary as to whether the completed work contains fifteen original lithographs or forty.

<details><summary>Round 1 (before challenge)</summary>

> Miró originally authored the surrealist poem and executed a complete run of lithographic plates for this book in 1967. 
> 
> Midway through printing, Miró and publisher Louis Broder discovered a chemical defect in the specially manufactured paper that caused the inks to alter and degrade. 
> 
> Because the original lithographic zinc plates and stones had already been effaced or damaged, the entire first print run had to be discarded and mostly destroyed. 
> 
> Miró had to redesign and redraw a completely new set of compositions from scratch before the project could finally be printed and issued in 1971. 
> 
> The completed volume features forty lithographs printed by Mourlot alongside the text of Miró’s poem reproduced directly in the artist's own handwriting. 
> 
> This edition entered the Museum of Fine Arts, Boston collection as a gift from Boris Fridman.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* DISPUTED Miró authored a poem and produced plates for the work in 1967 before completing the edition in 1971 — multiple sources cite 1967 plates ([artsy.net], [galeriearenthon.com], [mutualart.com], [masterworksfineart.com]); other sources cite the publication/creation year strictly as 1971 ([academia.edu], [ktima-logos.gr], [choicecontemporary.com], [facebook.com])
* UNATTESTED Midway through printing, Miró and publisher Louis Broder discovered a chemical defect in the specially manufactured paper that caused the inks to alter and degrade. — no retrieved source supports this
* UNATTESTED Because the original lithographic zinc plates and stones had already been effaced or damaged, the entire first print run had to be discarded and mostly destroyed. — no retrieved source supports this
* UNATTESTED Miró had to redesign and redraw a completely new set of compositions from scratch before the project could finally be printed and issued in 1971. — no retrieved source supports this
* DISPUTED The completed volume contains forty lithographs — [facebook.com] says it is an "illustrated book with forty color lithographs"; [academia.edu] says it contains "fifteen original lithographs"
* CONFIRMED The work was published by Louis Broder — [academia.edu], [artsy.net]
* CONFIRMED The lithographs were printed by Mourlot — [artsy.net]
* CONFIRMED The lithographs illustrate poetic texts written by Miró — [parkwestgallery.com], [academia.edu]
* UNATTESTED The text of Miró’s poem was reproduced directly in the artist's own handwriting. — no retrieved source supports this
* UNATTESTED This edition entered the Museum of Fine Arts, Boston collection as a gift from Boris Fridman. — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Midway through printing, Miró and publisher Louis Broder discovered a chemical defect in the specially manufactured paper that caused the inks to alte  
**query:** `"Le Lézard aux plumes d’or" printing publisher paper midway` → 7 relevant sentence(s)

  - `ferragempratik.com.br` (unverified) — Le Lézard aux Plumes d\'Or - Original Lithograph ...
  - `ferragempratik.com.br` (unverified) — Le Lézard aux Plumes d\'Or is a beautiful color lithograph on tissue paper, realized … ...
  - `academia.edu` (tier1) — Miró paired his poem Le lézard aux plumes d'or (Paris: Louis Broder, 1971) with fifteen original lithographs, and Max Ernst's collage- novels La femme 100 ...
  - `ktima-logos.gr` (unverified) — Le Lézard aux Plumes d\'Or - Original Lithograph by Joan Mirò - 1971.

**claim:** Miró originally authored the surrealist poem and executed a complete run of lithographic plates for this book in 1967.  
**query:** `"Le Lézard aux plumes d’or" plates 1967 originally authored` → 12 relevant sentence(s)

  - `composition.gallery` (unverified) — Plate III from Espriu-Miró, 1975.
  - `composition.gallery` (unverified) — Le lézard aux plumes d' or -II.
  - `composition.gallery` (unverified) — Le lézard aux plumes d' or ...
  - `artsy.net` (market) — From Forum Auctions, Joan Miró, 1 plate, Le Lézard aux Plumes D'Or (Mourlot 448) (1967), Lithograph printed in colours,, 35 × 50 cm.

**claim:** Miró had to redesign and redraw a completely new set of compositions from scratch before the project could finally be printed and issued in 1971.  
**query:** `"Le Lézard aux plumes d’or" printed 1971 redesign redraw` → 7 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `martinlawrence.com` (unverified) — "Untitled (M.794)" is a lithograph on Kochi Japan paper created by Joan Miró in 1971.
  - `martinlawrence.com` (unverified) — From the edition of 290, the artwork is signed 'Miró' lower right and ...
  - `parkwestgallery.com` (unverified) — "Le Lezard aux Plumes d'or II" (1971, Lithographs are printed designs made by drawing on lithographic (grease-treated) stones with a grease ...

**claim:** The completed volume features forty lithographs printed by Mourlot alongside the text of Miró’s poem reproduced directly in the artist's own handwriti  
**query:** `"Le Lézard aux plumes d’or" printed completed volume features` → 8 relevant sentence(s)

  - `composition.gallery` (unverified) — Discover this lithograph by Joan Miró from 1971, from the Le Lézard aux Plumes d'Or portfolio.
  - `facebook.com` (reject) — ly/6185aJOQd : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs ( ...
  - `parkwestgallery.com` (unverified) — “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.
  - `mutualart.com` (market) — View One Plate, from Le Lézard aux Plumes d'Or (1967) By Miró Joan; Lithograph printed in colours; 336 x 482 mm (13 1/4 x 19 in); Signed; Edition.

</details>


## credit_line 13.1 — *anchored*

> **Fridman's contribution ensures**

`CONFIRMED 1` · `CORRECTED 1` · `DISPUTED 1` · `UNATTESTED 4` · story kind **active** · **tells a disagreement**

### THE STORY

Joan Miró collaborated with art publisher Louis Broder to create *Le Lézard aux plumes d’or*, illustrating a surrealist text of the artist's own poems. After producing an initial suite of lithographs in 1967, the completed illustrated book was printed by Mourlot Frères and published by Broder in 1971. Sources disagree on the exact contents of the resulting editions: auction records identify a 1967 set of 18 lithographs, while accounts of the 1971 book describe it variously as containing 15 lithographs or a suite of 40 color lithographs.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró based the project on a surrealist poem he composed between 1936 and 1939.
> 
> The artist and publisher Louis Broder originally printed a full suite of lithographs for the book in 1967.
> 
> After printing, they discovered paper defects that caused severe color distortion and deterioration.
> 
> Because the original printing stones and plates had been ground down or discarded, the original compositions could not be reprinted.
> 
> Miró was forced to redraw entirely new lithographs from scratch, delaying the completed publication until 1971.
> 
> Boris Fridman’s gift allows the Museum of Fine Arts, Boston to display this final 1971 edition as part of its rare livres d'artistes exhibition.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED Joan Miró based the project on a surrealist poem he composed between 1936 and 1939. — no retrieved source supports this (sources confirm it illustrates his own poetic surreal text, but do not attest to the 1936–1939 composition dates)
* CONFIRMED The artist and publisher Louis Broder originally printed a suite of lithographs for the book in 1967. — [artsy.net], [christies.com], [mymagicalattic.blogspot.com], [mfa.org]
* UNATTESTED After printing, they discovered paper defects that caused severe color distortion and deterioration. — no retrieved source supports this
* UNATTESTED Because the original printing stones and plates had been ground down or discarded, the original compositions could not be reprinted. — no retrieved source supports this
* CORRECTED Miró was forced to redraw entirely new lithographs from scratch, delaying the completed publication until 1971. -> Miró created lithographs for *Le Lézard aux plumes d’or* across 1967 and 1971, with the completed illustrated book published by Louis Broder in 1971. — [christies.com], [mfa.org], [artsy.net], [mymagicalattic.blogspot.com]
* DISPUTED The number of lithographs in the 1971 publication — [composition.gallery] and [mymagicalattic.blogspot.com] state it features 15 lithographs; [instagram.com] and [facebook.com] state it is an illustrated book with 40 color lithographs (while [christies.com] notes an earlier 1967 set of 18).
* UNATTESTED Boris Fridman’s gift allows the Museum of Fine Arts, Boston to display this final 1971 edition as part of its rare livres d'artistes exhibition. — no retrieved source supports this (sources confirm the MFA Boston holds the 1971 work, but do not mention Boris Fridman or the specific exhibition title)

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The artist and publisher Louis Broder originally printed a full suite of lithographs for the book in 1967.  
**query:** `"Le Lézard aux plumes d’or" publisher printed 1967 artist` → 12 relevant sentence(s)

  - `artsy.net` (market) — Le Lézard aux plumes d'or is the result of a collaboration between Miró and art publisher Louis Broder.
  - `artsy.net` (market) — The book combines the artist's illustrations with his ...
  - `composition.gallery` (unverified) — Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...
  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.

**claim:** Joan Miró based the project on a surrealist poem he composed between 1936 and 1939.  
**query:** `"Le Lézard aux plumes d’or" 1936 1939 project surrealist` → 10 relevant sentence(s)

  - `choicecontemporary.com` (unverified) — Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).
  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi Japan paper image size: 13.25 x 19".
  - `atlantis-press.com` (unverified) — Feathers” (“Le Lézard aux plumes d'or”).
  - `atlantis-press.com` (unverified) — poetic surreal text ...

**claim:** Miró was forced to redraw entirely new lithographs from scratch, delaying the completed publication until 1971.  
**query:** `"Le Lézard aux plumes d’or" delaying 1971 forced redraw` → 7 relevant sentence(s)

  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `martinlawrence.com` (unverified) — "Untitled (M.794)" is a lithograph on Kochi Japan paper created by Joan Miró in 1971.
  - `martinlawrence.com` (unverified) — From the edition of 290, the artwork is signed 'Miró' lower right and ...
  - `choicecontemporary.com` (unverified) — Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).

**claim:** Boris Fridman’s gift allows the Museum of Fine Arts, Boston to display this final 1971 edition as part of its rare livres d'artistes exhibition.  
**query:** `"Le Lézard aux plumes d’or" 1971 fridman’s allows museum` → 12 relevant sentence(s)

  - `instagram.com` (reject) — Le Lézard aux plumes d'or.
  - `instagram.com` (reject) — Joan Miró (Spanish, 1893–1983) 1971.
  - `facebook.com` (reject) — Le Lézard aux plumes d'or Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs (including wrapper front and ...
  - `mfa.org` (tier1) — Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

</details>


## credit_line 13.2 — *evaluative*

> **visitors can appreciate the intricate dance between lithography**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 2` · story kind **inert** · **tells a disagreement**

### THE STORY

Joan Miró authored the text and created the lithographs for *Le Lézard aux plumes d’or*, which was produced with publisher Louis Broder. A complete initial run was finished in 1967, but Miró and Broder discovered that a defect in the specially commissioned paper reacted with the printing and distorted the work. To fix the issue, Miró created a second set of lithographs, which delayed the final release of the book. While most records place the completed publication in 1971, some sources date the second series of lithographs to 1972.

<details><summary>Round 1 (before challenge)</summary>

> * Joan Miró created *Le Lézard aux plumes d’or* to illustrate his own surrealist poetry rather than the work of an outside author.
> * Miró and publisher Louis Broder began collaborating on the project in 1963 and completed printing an initial full set of lithographs in 1967.
> * A defect in the paper reacted poorly with the inks and ruined the colors across the initial print run.
> * Because the original zinc printing plates had already been destroyed after printing, the initial run could not simply be reprinted.
> * Miró had to start over completely and redraw a new set of lithographs from scratch, delaying the final publication until 1971.
> * This publication served as the final collaborative project between Miró and Broder before the publisher's death.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
### PART 1 — ADJUDICATE

* CONFIRMED Joan Miró created *Le Lézard aux plumes d’or* to illustrate his own poetry rather than the work of an outside author. — [moma.org], [facebook.com]
* CONFIRMED Miró and publisher Louis Broder completed printing an initial set of lithographs in 1967. — [sothebys.com], [artsy.net]
* CONFIRMED A defect in the paper reacted with the ink/printing and distorted or ruined the initial run. — [sothebys.com], [christies.com]
* UNATTESTED Because the original zinc printing plates had already been destroyed after printing, the initial run could not simply be reprinted. — no retrieved source supports this
* DISPUTED The final publication date resulting from the redraw was 1971 — [composition.gallery], [martinlawrence.com], [museoreinasofia.es] date it to 1971; [gazette-drouot.com] dates the second series (Lézard II) to 1972
* UNATTESTED This publication served as the final collaborative project between Miró and Broder before the publisher's death. — no retrieved source supports this

---

###
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Miró and publisher Louis Broder began collaborating on the project in 1963 and completed printing an initial full set of lithographs in 1967.  
**query:** `"Le Lézard aux plumes d’or" publisher 1963 printing 1967` → 11 relevant sentence(s)

  - `sothebys.com` (market) — In 1967, Celestin finished printing Le Lézard aux plumes d'or.
  - `sothebys.com` (market) — Shortly afterwards, Miró and Broder discovered an error in the paper distorted the ...
  - `gazette-drouot.com` (unverified) — Miró, Joan Le Lézard aux plumes d'or.
  - `gazette-drouot.com` (unverified) — Set of 22 lithographs, including 14 from Lézard I (1963-1966) and 8 from Lézard II (1972).

**claim:** A defect in the paper reacted poorly with the inks and ruined the colors across the initial print run.  
**query:** `"Le Lézard aux plumes d’or" paper print defect reacted` → 12 relevant sentence(s)

  - `christies.com` (market) — Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — reacting with the specially commissioned paper.
  - `christies.com` (market) — By the time this defect had come to ...
  - `facebook.com` (reject) — (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on Kochi Japan paper image size: 13.25 x 19".

**claim:** Miró had to start over completely and redraw a new set of lithographs from scratch, delaying the final publication until 1971.  
**query:** `"Le Lézard aux plumes d’or" delaying 1971 completely redraw` → 9 relevant sentence(s)

  - `moma.org` (tier1) — Author Joan Miró ; Medium Lithograph from an illustrated book with forty lithographs (including wrapper front and cover) ; Dimensions composition (irreg.): 13 3/8 ...
  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...
  - `martinlawrence.com` (unverified) — "Untitled (M.794)" is a lithograph on Kochi Japan paper created by Joan Miró in 1971.
  - `martinlawrence.com` (unverified) — From the edition of 290, the artwork is signed 'Miró' lower right and ...

**claim:** This publication served as the final collaborative project between Miró and Broder before the publisher's death.  
**query:** `"Le Lézard aux plumes d’or" publisher publication served collaborative` → 15 relevant sentence(s)

  - `facebook.com` (reject) — publication of the book “Le Lézard aux plumes d'or”, published by Louis Broder.
  - `facebook.com` (reject) — In it, the artist illustrated his own poems.
  - `mfa.org` (tier1) — Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers.
  - `museoreinasofia.es` (unverified) — Joan Miró, Le lézard aux plumes d'or (detail), 1971.

</details>


## credit_line 13.3 — *evaluative*

> **offering a unique tactile experience and inviting viewers to ponder the narrative beyond the page**

`CONFIRMED 1` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 5` · story kind **inert**

### THE STORY

Joan Miró produced the series of color lithographs for the illustrated book *Le Lézard aux plumes d’or* (*The Lizard with Golden Feathers*). While major records and galleries document the limited-edition book as released in 1971, several individual plates from the suite are dated to 1967 across auction records. The resulting 1971 publication assembled these lithographic plates alongside Miró's work into a single limited edition.

<details><summary>Round 1 (before challenge)</summary>

> Joan Miró originally created the lithographs for *Le Lézard aux plumes d’or* alongside his own handwritten poetry starting in 1967. 
> 
> During the initial printing run, the inks chemically reacted with the specially commissioned paper, causing severe defects. 
> 
> Because the original lithographic stones and plates had already been erased before the chemical defect was discovered, the entire first edition had to be scrapped. 
> 
> Miró and publisher Louis Broder decided to start the multi-year project over from scratch, leading Miró to create a brand-new set of plates that was ultimately published in 1971.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED Joan Miró created lithographs alongside his own handwritten poetry — no retrieved source supports this
* DISPUTED The creation date of the prints is 1967 vs. 1971 — [christies.com], [artsy.net] (Van der Vorst), [fineart.ha.com], and [live.dumoart.com] date prints to 1967; [masterworksfineart.com], [composition.gallery], and [artsy.net] (Cramer Books 148) date them to 1971
* UNATTESTED Inks chemically reacted with specially commissioned paper, causing severe defects during the initial printing run — no retrieved source supports this
* UNATTESTED The original lithographic stones and plates had already been erased before the defect was discovered — no retrieved source supports this
* UNATTESTED The entire first edition had to be scrapped — no retrieved source supports this
* UNATTESTED Miró and publisher Louis Broder decided to start over from scratch and create a brand-new set of plates — no retrieved source supports this
* CONFIRMED *Le Lézard aux plumes d’or* was published as a limited edition illustrated book featuring lithographs by Joan Miró in 1971 — [composition.gallery]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Miró and publisher Louis Broder decided to start the multi-year project over from scratch, leading Miró to create a brand-new set of plates that was u  
**query:** `"Le Lézard aux plumes d’or" publisher plates published 1971` → 12 relevant sentence(s)

  - `masterworksfineart.com` (unverified) — Title: Plate III from Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ; Reference: C.
  - `composition.gallery` (unverified) — Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...
  - `moma.org` (tier1) — Plate (folio 11) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).
  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.

**claim:** Joan Miró originally created the lithographs for *Le Lézard aux plumes d’or* alongside his own handwritten poetry starting in 1967.  
**query:** `"Le Lézard aux plumes d’or" 1967 originally created lithographs` → 10 relevant sentence(s)

  - `christies.com` (market) — Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.
  - `christies.com` (market) — 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...
  - `artsy.net` (market) — From Van der Vorst- Art, Joan Miró, Le Lézard aux plumes d'or (1967), Color lithograph on on wove paper with Miro watermark, 35.5 × 99 cm.
  - `coleccionbbva.com` (unverified) — Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

</details>


---

# Au Soleil du Plafond


## credit_line 2.1 — *anchored*

> **Pierre Reverdy, the French poet linked to Surrealism**

`CONFIRMED 5` · `CORRECTED 0` · `DISPUTED 2` · `UNATTESTED 4` · story kind **eventful**

### THE STORY

The collaboration between writer Pierre Reverdy and artist Juan Gris was originally planned in 1916 or 1917. Work halted when Gris died in 1927 at age forty, leaving only eleven completed images—described by one source as half of the intended total. The artist's son kept the eleven gouaches as his father had left them. The long-abandoned project was finally brought to print in Paris in 1955, credited in records to publisher Tériade Éditeur and Editions Verve.

<details><summary>Round 1 (before challenge)</summary>

> The project was originally planned around 1916 or 1917 by art dealer and publisher Léonce Rosenberg, pairing Pierre Reverdy's poems directly with Juan Gris's lithographs.
> 
> Production stalled and remained unfinished when Gris died prematurely in 1927 at age forty, having completed only eleven of the intended twenty illustrations.
> 
> Nearly thirty years later, publisher Tériade revived the abandoned project in collaboration with Reverdy.
> 
> Reverdy wrote out the texts in his own handwriting so they could be printed in facsimile alongside Gris's surviving prints as a posthumous tribute to his friend.
> 
> The completed book was finally published in 1955 in Paris by Tériade Éditeur in a limited print run.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED The project was originally planned around 1916 or 1917 — [1stdibs.com]
* UNATTESTED Planned specifically by "art dealer and publisher Léonce Rosenberg" — [metmuseum.org] truncates to "planned by L." and provides no full name or title.
* CONFIRMED Pierre Reverdy wrote the text and Juan Gris designed/illustrated the work — [metmuseum.org]
* CONFIRMED Juan Gris died in 1927 at age forty — [araderbooks.com], [academia.edu], [metmuseum.org]
* CONFIRMED Gris completed only eleven images before the project was abandoned/stalled — [emuseum.toledomuseum.org], [newyorker.com], [auctions.nyshowplace.com]
* DISPUTED Gris completed eleven of twenty intended illustrations — [metmuseum.org] says he finished "only half of the intended" (implying twenty-two if eleven were done); your text stated twenty.
* DISPUTED Publisher of the 1955 edition — [abebooks.com] lists "Tériade Éditeur, Paris"; [1stdibs.com] lists "Editions Verve, Paris, under [Tériade]".
* CONFIRMED Published in 1955 in Paris — [abebooks.com], [1stdibs.com]
* UNATTESTED Tériade revived the project nearly thirty years later in collaboration with Reverdy — no retrieved source mentions this specific collaboration detail.
* UNATTESTED Reverdy wrote out the texts in facsimile handwriting as a posthumous tribute — no retrieved source mentions Reverdy's handwriting, facsimile printing, or a tribute.
* UNATTESTED The completed book was issued in a limited print run — no retrieved source mentions the print run size.

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The project was originally planned around 1916 or 1917 by art dealer and publisher Léonce Rosenberg, pairing Pierre Reverdy's poems directly with Juan  
**query:** `"Au Soleil du Plafond" 1916 1917 publisher project` → 17 relevant sentence(s)

  - `metmuseum.org` (tier1) — Au Soleil du Plafond ...
  - `metmuseum.org` (tier1) — This book was originally planned by L.
  - `metmuseum.org` (tier1) — Gris died in 1927, having finished only half of the intended ...
  - `1stdibs.com` (market) — Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after) ...

**claim:** The completed book was finally published in 1955 in Paris by Tériade Éditeur in a limited print run.  
**query:** `"Au Soleil du Plafond" published 1955 print completed` → 12 relevant sentence(s)

  - `metmuseum.org` (tier1) — Artwork Details ; Title: Au Soleil du Plafond ; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine) ; Author: Written by Pierre Reverdy ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `araderbooks.com` (unverified) — Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...
  - `auctions.nyshowplace.com` (unverified) — After Juan Gris (Spanish, 1887-1927) "Au Soleil du Plafond" Portfolio, (11) eleven lithographs in colors on Arches paper, "Moulin a ...

**claim:** Production stalled and remained unfinished when Gris died prematurely in 1927 at age forty, having completed only eleven of the intended twenty illust  
**query:** `"Au Soleil du Plafond" died 1927 production stalled` → 11 relevant sentence(s)

  - `newyorker.com` (tier2) — The volume has just been published, under the title “Au Soleil du Plafond ...
  - `newyorker.com` (tier2) — The son kept the eleven gouaches as his father had left ...
  - `academia.edu` (tier1) — Between 1911 and his death in 1927, Gris produced a rich and varied body of ...
  - `academia.edu` (tier1) — Au soleil du plafond.

**claim:** Nearly thirty years later, publisher Tériade revived the abandoned project in collaboration with Reverdy.  
**query:** `"Au Soleil du Plafond" publisher abandoned nearly thirty` → 17 relevant sentence(s)

  - `abebooks.com` (market) — Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.
  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond.
  - `emuseum.toledomuseum.org` (unverified) — Artist Juan Gris (Spanish, 1887-1927).
  - `emuseum.toledomuseum.org` (unverified) — The project was abandoned with only 11 images completed.

</details>


## credit_line 2.2 — *evaluative*

> **revolutionized the concept of the book as art**

`CONFIRMED 5` · `CORRECTED 1` · `DISPUTED 1` · `UNATTESTED 7` · story kind **eventful**

### THE STORY

*Au Soleil du Plafond* was originally conceived as a collaboration pairing twenty poems by Pierre Reverdy with twenty illustrations by Juan Gris. The project was cut short when Gris died at age forty in 1927, having completed only eleven of the intended lithographic plates. Publisher Tériade later took up the unfinished work, having the lithographs printed by the Mourlot workshop. While one source records a publication date of 1948, other records place its official release in Paris in 1955.

<details><summary>Round 1 (before challenge)</summary>

> Art dealer Léonce Rosenberg originally commissioned *Au Soleil du Plafond* around 1916–1917 to pair twenty poems by Pierre Reverdy with twenty illustrations by Juan Gris. 
> 
> The project stalled due to dealer inaction and was derailed when Gris died in 1927 at age forty, having finished only eleven of the intended plates. 
> 
> Publisher Tériade revived the abandoned project roughly thirty years later in direct collaboration with Reverdy. 
> 
> Because ten illustrations were missing, the creators abandoned the original portfolio concept of twenty paired prints and completely reconceived the book's format. 
> 
> Fernand Mourlot’s workshop finally printed the lithographs and Reverdy's handwritten texts for publication in 1955 as a posthumous tribute to Gris.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

UNATTESTED Léonce Rosenberg originally commissioned the work — no retrieved source supports this  
UNATTESTED The project was commissioned around 1916–1917 — no retrieved source supports this (only an isolated date "18 May 1916" appears without commission details)  
CONFIRMED Originally planned to pair twenty poems by Pierre Reverdy with twenty illustrations by Juan Gris — [academia.edu]  
UNATTESTED The project stalled due to dealer inaction — no retrieved source supports this  
CONFIRMED Gris died in 1927 at age forty — [abebooks.com], [araderbooks.com], [emuseum.toledomuseum.org]  
CONFIRMED Gris finished only eleven intended illustrations/lithographs — [brill.com]  
CONFIRMED Tériade published the project — [brill.com], [emuseum.toledomuseum.org], [abebooks.com], [baumanrarebooks.com]  
UNATTESTED Tériade revived the project roughly thirty years later in direct collaboration with Reverdy — no retrieved source supports this  
CORRECTED Because ten illustrations were missing -> Because nine illustrations were missing (twenty planned minus eleven finished) — [academia.edu], [brill.com]  
UNATTESTED The creators abandoned the original portfolio concept and completely reconceived the book's format — no retrieved source supports this  
CONFIRMED Mourlot's workshop printed the lithographs — [emuseum.toledomuseum.org], [baumanrarebooks.com]  
UNATTESTED Reverdy's handwritten texts were printed — no retrieved source supports this  
DISPUTED Publication date — [brill.com] (first entry) mentions Paris: Tériade, 1948; [brill.com] (second entry), [emuseum.toledomuseum.org], and [baumanrarebooks.com] say Paris: Tériade / Éditions Verve, 1955  
UNATTESTED Published specifically as a posthumous tribute to Gris — no retrieved source supports this  

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Art dealer Léonce Rosenberg originally commissioned *Au Soleil du Plafond* around 1916–1917 to pair twenty poems by Pierre Reverdy with twenty illustr  
**query:** `"Au Soleil du Plafond" commissioned 1916 1917 dealer` → 13 relevant sentence(s)

  - `academia.edu` (tier1) — Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...
  - `academia.edu` (tier1) — dealer of 18 May 1916.
  - `dokumen.pub` (unverified) — Au soleil du plafond.' ” French Studies 43, no 2: 302–19.
  - `brill.com` (unverified) — Paris: Tériade, 1948.

**claim:** The project stalled due to dealer inaction and was derailed when Gris died in 1927 at age forty, having finished only eleven of the intended plates.  
**query:** `"Au Soleil du Plafond" died 1927 plates project` → 15 relevant sentence(s)

  - `abebooks.com` (market) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `abebooks.com` (market) — Juan Gris, 1887-1927) final body of work, as he died of kidney failure at only 40 years old ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `araderbooks.com` (unverified) — Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old ...

**claim:** Publisher Tériade revived the abandoned project roughly thirty years later in direct collaboration with Reverdy.  
**query:** `"Au Soleil du Plafond" publisher abandoned tériade revived` → 9 relevant sentence(s)

  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...
  - `academia.edu` (tier1) — These works were intended to be included in the book Au soleil du plafond, planned to consist of twenty poems by Pierre Reverdy, illustrated by twenty ...
  - `brill.com` (unverified) — Paris: Tériade, 1948.
  - `brill.com` (unverified) — Au soleil du plafond.

**claim:** Fernand Mourlot’s workshop finally printed the lithographs and Reverdy's handwritten texts for publication in 1955 as a posthumous tribute to Gris.  
**query:** `"Au Soleil du Plafond" printed 1955 fernand mourlot’s` → 13 relevant sentence(s)

  - `metmuseum.org` (tier1) — The Met CollectionSearch ArtAu Soleil du Plafond.
  - `metmuseum.org` (tier1) — Au Soleil du Plafond ...
  - `abebooks.com` (market) — From au Soleil du Plafond.
  - `abebooks.com` (market) — ; Publisher: Paris: Tériade Editeur.

</details>


## credit_line 2.3 — *evaluative*

> **exemplifying the collaborative spirit that defines the MFA's exhibition**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 3` · story kind **active**

### THE STORY

Work on *Au Soleil du Plafond* ground to a halt when Juan Gris died in 1927 at the age of forty. While some accounts note that he left behind eleven completed gouaches, other records state he left eleven completed lithographs. Nearly thirty years later, publisher Tériade revived the project in collaboration with the author Pierre Reverdy. Tériade published the finished volume in Paris in 1955.

<details><summary>Round 1 (before challenge)</summary>

> Art dealer Léonce Rosenberg originally initiated the project around 1916 with the plan that Juan Gris would create twenty gouaches to pair with twenty poems by Pierre Reverdy.
> 
> The project ground to a halt when Gris died in 1927 at the age of forty, having completed only eleven of the intended illustrations.
> 
> Nearly thirty years later, publisher Tériade revived the collaboration alongside Reverdy.
> 
> Fernand Mourlot’s workshop translated Gris’s surviving gouaches into lithographs alongside lithographic reproductions of Reverdy’s handwriting.
> 
> Because ten images were missing, Reverdy and Tériade completely redesigned the book's format to present it as a posthumous tribute to Gris.
> 
> The resulting *livre d'artiste* was finally released in Paris in 1955, decades after its creators first conceived it.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED Art dealer Léonce Rosenberg originally initiated the project around 1916 with the plan that Juan Gris would create twenty gouaches to pair with twenty poems by Pierre Reverdy. — no retrieved source supports this (sources mention Rosenberg, Gris, Reverdy, and 1916 in fragments, but do not state Rosenberg initiated the project or specify twenty gouaches / twenty poems)
* CONFIRMED The project ground to a halt when Gris died in 1927 at the age of forty — [abebooks.com], [araderbooks.com], [iberlibro.com]
* DISPUTED Gris completed only eleven gouaches — [iberlibro.com] states Gris left behind "11 completed lithographs"; other sources do not specify the medium as gouaches
* CONFIRMED Nearly thirty years later, publisher Tériade revived the collaboration alongside Reverdy — [metmuseum.org], [araderbooks.com]
* UNATTESTED Fernand Mourlot’s workshop translated Gris’s surviving gouaches into lithographs alongside lithographic reproductions of Reverdy’s handwriting — no retrieved source supports this
* UNATTESTED Because ten images were missing, Reverdy and Tériade completely redesigned the book's format to present it as a posthumous tribute to Gris — no retrieved source supports this
* CONFIRMED The resulting work was published in Paris in 1955 by Tériade — [art-books.com], [abebooks.com]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The project ground to a halt when Gris died in 1927 at the age of forty, having completed only eleven of the intended illustrations.  
**query:** `"Au Soleil du Plafond" halt died 1927 project` → 17 relevant sentence(s)

  - `abebooks.com` (market) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `abebooks.com` (market) — Juan Gris, 1887-1927) final body of work, as he died of kidney failure at only 40 years old ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `araderbooks.com` (unverified) — Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old ...

**claim:** Art dealer Léonce Rosenberg originally initiated the project around 1916 with the plan that Juan Gris would create twenty gouaches to pair with twenty  
**query:** `"Au Soleil du Plafond" 1916 dealer léonce rosenberg` → 17 relevant sentence(s)

  - `art-books.com` (unverified) — Le Livre From au Soleil du Plafond.
  - `art-books.com` (unverified) — Paris: Tériade Editeur, 1955.
  - `abebooks.com` (market) — 1916) and are therefore included in this catalogue ...
  - `abebooks.com` (market) — au Soleil du Plafond.

**claim:** Nearly thirty years later, publisher Tériade revived the collaboration alongside Reverdy.  
**query:** `"Au Soleil du Plafond" publisher nearly thirty tériade` → 15 relevant sentence(s)

  - `abebooks.com` (market) — Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.
  - `metmuseum.org` (tier1) — The project was taken up by Ténade some thirty years later, with the collaboration of the author (Reverdy).
  - `metmuseum.org` (tier1) — Au Soleil du Plafond; Designer: Designed by Juan ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.

</details>


## credit_line 3.1 — *evaluative*

> **Gris's innovative vision**

`CONFIRMED 5` · `CORRECTED 1` · `DISPUTED 0` · `UNATTESTED 5` · story kind **eventful**

### THE STORY

In 1916 or 1917, art dealer Léonce Rosenberg commissioned a collaborative book titled *Au Soleil du Plafond*, pairing twenty poems by Pierre Reverdy with illustrations by Juan Gris. The project stalled during World War I and remained unfinished when Gris died in 1927, leaving behind eleven gouaches (though one record describes him as having completed half of the twenty planned illustrations). The son kept the eleven gouaches as his father had left them until publisher Tériade (Éditions Verve) finally brought the work to realization in 1955. For that release, printer Mourlot Frères produced the eleven lithographs after Gris's original compositions to accompany Reverdy's text.

<details><summary>Round 1 (before challenge)</summary>

> * *Au Soleil du Plafond* was originally conceived around 1916–1917 and commissioned by art dealer Léonce Rosenberg as a collaborative *livre d’artiste* pairing twenty poems by Pierre Reverdy with plates by Juan Gris.
> * The project stalled and remained unfinished after Gris completed only eleven gouache compositions and died prematurely of kidney failure in 1927 at age forty.
> * Publisher Tériade resurrected the abandoned endeavor nearly three decades later with Reverdy's active involvement.
> * Reverdy conceived the revised publication as a tribute to his deceased friend, writing a new preface reflecting on their partnership beyond the grave.
> * Master printer Fernand Mourlot translated Gris’s original 1916–1917 gouaches into eleven color lithographs alongside lithographed text of Reverdy's handwriting.
> * The finished volume was finally released in 1955 in a limited edition printed on Arches paper.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

* CONFIRMED *Au Soleil du Plafond* was conceived around 1916–1917 and commissioned by Léonce Rosenberg as a collaboration pairing twenty poems by Pierre Reverdy with plates/illustrations by Juan Gris — [1stdibs.com], [academia.edu]
* CONFIRMED The project stalled and remained unfinished after Gris died in 1927 — [alamy.com], [academia.edu]
* UNATTESTED Gris died prematurely of kidney failure at age forty — no retrieved source supports this
* CORRECTED Gris completed only eleven gouache compositions -> Gris completed eleven gouaches, though one source notes he completed "half the illustrations for the twenty poems" — [newyorker.com], [brill.com], [academia.edu]
* CONFIRMED Publisher Tériade published the book/project in 1955 — [emuseum.toledomuseum.org], [brill.com]
* UNATTESTED Tériade resurrected the endeavor nearly three decades later with Reverdy's active involvement — no retrieved source supports this
* UNATTESTED Reverdy conceived the revised publication as a tribute to his deceased friend, writing a new preface reflecting on their partnership beyond the grave — no retrieved source supports this
* CONFIRMED Mourlot (Mourlot Frères) printed the lithographs for Tériade's edition featuring 11 illustrations by Juan Gris — [emuseum.toledomuseum.org], [brill.com]
* UNATTESTED Lithographed text of Reverdy's handwriting — no retrieved source supports this
* CONFIRMED The volume was released in 1955 published by Tériade (Éditions Verve) — [emuseum.toledomuseum.org], [brill.com]
* UNATTESTED Limited edition printed on Arches paper — no retrieved source supports this
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** *Au Soleil du Plafond* was originally conceived around 1916–1917 and commissioned by art dealer Léonce Rosenberg as a collaborative *livre d’artiste*   
**query:** `"Au Soleil du Plafond" 1916 1917 commissioned plates` → 12 relevant sentence(s)

  - `academia.edu` (tier1) — Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...
  - `academia.edu` (tier1) — The gouaches belong to a group of drawings that Rosenberg commissioned from Gris in ...
  - `dokumen.pub` (unverified) — Au soleil du plafond.' ” French Studies 43, no 2: 302–19.
  - `scribd.com` (unverified) — Reverdy, Pierre: Au soleil du plafond.

**claim:** Master printer Fernand Mourlot translated Gris’s original 1916–1917 gouaches into eleven color lithographs alongside lithographed text of Reverdy's ha  
**query:** `"Au Soleil du Plafond" printer 1916 1917 master` → 16 relevant sentence(s)

  - `instagram.com` (reject) — Au soleil du plafond, de Pierre Reverdy ( ...
  - `1stdibs.com` (market) — This first project was executed in 1916 or 1917.
  - `1stdibs.com` (market) — The lack of these XX ...
  - `1stdibs.com` (market) — Au Soleil du Plafond, Gris collectible print, Gris modernist lithograph.

**claim:** The project stalled and remained unfinished after Gris completed only eleven gouache compositions and died prematurely of kidney failure in 1927 at ag  
**query:** `"Au Soleil du Plafond" died 1927 project stalled` → 17 relevant sentence(s)

  - `alamy.com` (unverified) — Au soleil du plafond), 1916, post-Cubist color lithograph still life ...
  - `alamy.com` (unverified) — stalled during World War I and remained unfinished at the time of Gris's death.
  - `newyorker.com` (tier2) — The volume has just been published, under the title “Au Soleil du Plafond ...
  - `newyorker.com` (tier2) — The son kept the eleven gouaches as his father had left ...

**claim:** Publisher Tériade resurrected the abandoned endeavor nearly three decades later with Reverdy's active involvement.  
**query:** `"Au Soleil du Plafond" publisher abandoned tériade resurrected` → 12 relevant sentence(s)

  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...
  - `academia.edu` (tier1) — These works were intended to be included in the book Au soleil du plafond, planned to consist of twenty poems by Pierre Reverdy, illustrated by twenty ...
  - `brill.com` (unverified) — Paris: Tériade, 1948.
  - `brill.com` (unverified) — Au soleil du plafond.

</details>


## credit_line 3.2 — *evaluative*

> **Reverdy's poetic prowess**

`CONFIRMED 2` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 3` · story kind **eventful**

### THE STORY

Artist Juan Gris set out to create illustrations for Pierre Reverdy's twenty poems in the folio *Au soleil du plafond*. The project came to an abrupt halt when Gris died in 1927, leaving the work unfinished. Sources differ on the exact scope of his progress, with some noting he completed eleven images and others recording that he finished only half of the intended illustrations. The abandoned collaboration remained unpublished for decades until the publisher Tériade finally released the book in Paris in 1955.

<details><summary>Round 1 (before challenge)</summary>

> The project was originally planned around 1916–1917 by art dealer Léonce Rosenberg. 
> 
> The original plan called for Juan Gris to illustrate each of Pierre Reverdy's twenty poems with an individual plate. 
> 
> Production stalled and remained unfinished when Gris died of kidney failure in 1927 at age 40, having completed only 11 gouaches. 
> 
> Nearly thirty years later, the art publisher Tériade revived the abandoned project with Reverdy. 
> 
> Published posthumously in 1955, the book was framed by Reverdy as a tribute to the memory of his prematurely deceased friend.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED The project was originally planned around 1916–1917 by art dealer Léonce Rosenberg. — no retrieved source supports this
* DISPUTED The original plan called for Juan Gris to illustrate each of Pierre Reverdy's twenty poems with an individual plate. — emuseum.toledomuseum.org says Gris intended illustrations for the twenty poems but also says the project was abandoned with only 11 images completed (which is 11 of 20, not exactly half); metmuseum.org and emuseum.toledomuseum.org state he completed only "half" of the intended illustrations
* UNATTESTED Gris died of kidney failure at age 40. — no retrieved source supports the cause of death or specific age (sources only list his lifespan as 1887–1927)
* CONFIRMED Production was abandoned/postponed after Gris died in 1927 having completed only 11 images / half of the illustrations. — metmuseum.org, emuseum.toledomuseum.org, dokumen.pub
* CONFIRMED The publisher Tériade published the book *Au soleil du plafond* in 1955. — abebooks.com, academia.edu, dokumen.pub, tretyakovgallerymagazine.com
* UNATTESTED Published posthumously, the book was framed by Reverdy as a tribute to the memory of his prematurely deceased friend. — no retrieved source supports this framing/tribute detail

---

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Production stalled and remained unfinished when Gris died of kidney failure in 1927 at age 40, having completed only 11 gouaches.  
**query:** `"Au Soleil du Plafond" died 1927 production stalled` → 17 relevant sentence(s)

  - `metmuseum.org` (tier1) — Gris died in 1927, having finished only half of the intended illustrations.
  - `metmuseum.org` (tier1) — Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887 ...
  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond.
  - `emuseum.toledomuseum.org` (unverified) — Artist Juan Gris (Spanish, 1887-1927).

**claim:** Nearly thirty years later, the art publisher Tériade revived the abandoned project with Reverdy.  
**query:** `"Au Soleil du Plafond" publisher abandoned nearly thirty` → 18 relevant sentence(s)

  - `abebooks.com` (market) — Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.
  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond.
  - `emuseum.toledomuseum.org` (unverified) — Artist Juan Gris (Spanish, 1887-1927).
  - `emuseum.toledomuseum.org` (unverified) — The project was abandoned with only 11 images completed.

**claim:** Published posthumously in 1955, the book was framed by Reverdy as a tribute to the memory of his prematurely deceased friend.  
**query:** `"Au Soleil du Plafond" published 1955 posthumously framed` → 7 relevant sentence(s)

  - `1stdibs.com` (market) — This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...
  - `researchgate.net` (unverified) — anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.
  - `researchgate.net` (unverified) — destructive wind: Le vent noir qui tordait les ...
  - `academia.edu` (tier1) — It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond.

**claim:** The original plan called for Juan Gris to illustrate each of Pierre Reverdy's twenty poems with an individual plate.  
**query:** `"Au Soleil du Plafond" plate original called illustrate` → 13 relevant sentence(s)

  - `etsy.com` (unverified) — May include: A vintage book cover with the title "Au soleil du plafond" ...
  - `etsy.com` (unverified) — May include: A page from a book with text about the artist Juan Gris and.
  - `tretyakovgallerymagazine.com` (unverified) — A double-page spread from the book Pierre Reverdy.
  - `tretyakovgallerymagazine.com` (unverified) — Au Soleil du plafond Paris, 1955.

</details>


## credit_line 3.3 — *evaluative*

> **resulting in a unique interlacing of images and words**

`CONFIRMED 4` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 4` · story kind **eventful** · **tells a disagreement**

### THE STORY

The collaboration on *Au Soleil du Plafond* began in 1916 between painter Juan Gris and poet Pierre Reverdy. The undertaking was brought to an abrupt halt when Gris died of kidney failure in 1927 at forty years old. Accounts differ on what state the artwork was left in: some records state Gris completed only half of the intended illustrations, while others note he left behind eleven completed lithographs. Decades later, publisher Tériade revived the stalled project and released the first edition in Paris in 1955, with printmaker Fernand Mourlot producing the prints.

<details><summary>Round 1 (before challenge)</summary>

> *Léonce Rosenberg* originally commissioned *Au Soleil du Plafond* around 1916–1917 as a collaborative project where Juan Gris was intended to create an illustration for each of Pierre Reverdy's twenty poems.
> 
> The project was halted when Gris died prematurely of kidney failure in 1927, having completed only eleven gouache compositions.
> 
> Publisher *Tériade* revived the unfinished project nearly three decades later, working with Reverdy to adapt and publish it posthumously in 1955 as a tribute to Gris. 
> 
> Master printmaker *Fernand Mourlot* translated Gris's original 1916–1917 gouaches into color lithographs alongside lithographic facsimiles of Reverdy’s handwritten poems to achieve their interlacing.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

- UNATTESTED Léonce Rosenberg originally commissioned *Au Soleil du Plafond* — no retrieved source supports this (metmuseum.org only notes "originally planned by L.").
- CONFIRMED The project began around 1916 as a collaboration between Juan Gris and poet Pierre Reverdy — [emuseum.toledomuseum.org]
- UNATTESTED Gris was intended to create an illustration for each of Pierre Reverdy's twenty poems — no retrieved source supports this.
- CONFIRMED Gris died of kidney failure in 1927, bringing the project to a halt — [abebooks.com], [araderbooks.com], [iberlibro.com]
- DISPUTED Whether Gris left behind eleven gouache compositions or eleven lithographs — [iberlibro.com] says he left behind "11 completed lithographs"; [metmuseum.org] and [etsy.com] state he finished "only half" of the intended work; gouaches are not mentioned in the retrieved text.
- CONFIRMED Publisher Tériade published the book in Paris in 1955 — [metmuseum.org], [abebooks.com], [art-books.com]
- UNATTESTED Tériade worked with Reverdy to adapt and publish the project posthumously as a tribute to Gris — no retrieved source supports this.
- CONFIRMED Fernand Mourlot printed the work — [metmuseum.org]
- UNATTESTED Mourlot translated original gouaches into color lithographs alongside lithographic facsimiles of Reverdy's handwritten poems to achieve their interlacing — no retrieved source supports this.
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Léonce Rosenberg* originally commissioned *Au Soleil du Plafond* around 1916–1917 as a collaborative project where Juan Gris was intended to create an  
**query:** `"Au Soleil du Plafond" commissioned 1916 1917 léonce` → 17 relevant sentence(s)

  - `metmuseum.org` (tier1) — Au Soleil du Plafond ...
  - `metmuseum.org` (tier1) — This book was originally planned by L.
  - `metmuseum.org` (tier1) — Gris died in 1927, having finished only half of the intended ...
  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond.

**claim:** The project was halted when Gris died prematurely of kidney failure in 1927, having completed only eleven gouache compositions.  
**query:** `"Au Soleil du Plafond" halted died 1927 project` → 16 relevant sentence(s)

  - `abebooks.com` (market) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `abebooks.com` (market) — Juan Gris, 1887-1927) final body of work, as he died of kidney failure at only 40 years old ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `araderbooks.com` (unverified) — Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old ...

**claim:** Publisher *Tériade* revived the unfinished project nearly three decades later, working with Reverdy to adapt and publish it posthumously in 1955 as a   
**query:** `"Au Soleil du Plafond" publisher publish 1955 tériade` → 17 relevant sentence(s)

  - `metmuseum.org` (tier1) — Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887 ...
  - `metmuseum.org` (tier1) — Published by Tériade , Paris; Printer: Printed by Fernand Mourlot (French ...
  - `abebooks.com` (market) — Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.
  - `art-books.com` (unverified) — Le Livre From au Soleil du Plafond.

**claim:** Master printmaker *Fernand Mourlot* translated Gris's original 1916–1917 gouaches into color lithographs alongside lithographic facsimiles of Reverdy’  
**query:** `"Au Soleil du Plafond" printmaker 1916 1917 master` → 18 relevant sentence(s)

  - `etsy.com` (unverified) — Juan Gris, Moulin à Cafe (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph ...
  - `etsy.com` (unverified) — Gris died in 1927, having finished only half of ...
  - `vascularandwoundclinic.co.za` (unverified) — 1916-1917 and 1925-1927.In 1910, already settled in Paris, Juan Gris met ...
  - `vascularandwoundclinic.co.za` (unverified) — From au Soleil du Plafond.

</details>


## credit_line 4.1 — *evaluative*

> **Gris's ability to transform visual art**

`CONFIRMED 1` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 4` · story kind **eventful**

### THE STORY

Work on *Au Soleil du Plafond* stalled following the death of Juan Gris in 1927. Gris had completed only eleven gouaches before his passing. Nearly thirty years after the project was originally conceived, publisher Tériade revived the materials. Tériade brought the collection of poems and lithographs together and finally published the book in 1955.

<details><summary>Round 1 (before challenge)</summary>

> Art dealer Léonce Rosenberg originally commissioned the project around 1916 to feature twenty poems by Pierre Reverdy paired with twenty illustrations by Juan Gris. 
> 
> Production stalled when Gris died prematurely of kidney failure in 1927, having completed only eleven gouaches. 
> 
> Because ten illustrations were missing, the publisher had to redesign the entire format rather than release the intended twenty-plate portfolio. 
> 
> Nearly thirty years after the project began, publisher Tériade revived and completed the book as a posthumous tribute to Gris. 
> 
> The resulting *livre d'artiste* was printed by Mourlot Frères and published in 1955.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED Art dealer Léonce Rosenberg originally commissioned the project around 1916 to feature twenty poems by Pierre Reverdy paired with twenty illustrations by Juan Gris. — no retrieved source supports this [metmuseum.org mentions "originally planned by L." and academia.edu mentions 1916/Reverdy/Gris, but Rosenberg, twenty poems, and twenty illustrations are not attested in the text]
* UNATTESTED Production stalled when Gris died prematurely of kidney failure in 1927, having completed only eleven gouaches. — no retrieved source supports this [academia.edu/metmuseum.org confirm Gris died in 1927 and newyorker.com/metmuseum.org confirm eleven gouaches / half finished, but kidney failure is not attested]
* UNATTESTED Because ten illustrations were missing, the publisher had to redesign the entire format rather than release the intended twenty-plate portfolio. — no retrieved source supports this
* CONFIRMED Nearly thirty years after the project began, publisher Tériade revived and completed the book as a posthumous tribute to Gris. — [christies.com] and [araderbooks.com]
* UNATTESTED The resulting *livre d'artiste* was printed by Mourlot Frères and published in 1955. — no retrieved source supports this [christies.com, abebooks.com, and instagram.com confirm publication in 1955, but Mourlot Frères is not attested]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Art dealer Léonce Rosenberg originally commissioned the project around 1916 to feature twenty poems by Pierre Reverdy paired with twenty illustrations  
**query:** `"Au Soleil du Plafond" commissioned 1916 dealer léonce` → 9 relevant sentence(s)

  - `christies.com` (market) — It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond.
  - `academia.edu` (tier1) — Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...
  - `scribd.com` (unverified) — Reverdy, Pierre: Au soleil du plafond.
  - `scribd.com` (unverified) — Jul) I924,pages 182-486 ...

**claim:** Production stalled when Gris died prematurely of kidney failure in 1927, having completed only eleven gouaches.  
**query:** `"Au Soleil du Plafond" died 1927 production stalled` → 11 relevant sentence(s)

  - `newyorker.com` (tier2) — The volume has just been published, under the title “Au Soleil du Plafond ...
  - `newyorker.com` (tier2) — The son kept the eleven gouaches as his father had left ...
  - `academia.edu` (tier1) — Between 1911 and his death in 1927, Gris produced a rich and varied body of ...
  - `academia.edu` (tier1) — Au soleil du plafond.

**claim:** Nearly thirty years after the project began, publisher Tériade revived and completed the book as a posthumous tribute to Gris.  
**query:** `"Au Soleil du Plafond" publisher nearly thirty project` → 19 relevant sentence(s)

  - `metmuseum.org` (tier1) — Au Soleil du Plafond ...
  - `metmuseum.org` (tier1) — This book was originally planned by L.
  - `metmuseum.org` (tier1) — Gris died in 1927, having finished only half of the intended ...
  - `abebooks.com` (market) — Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.

</details>


## credit_line 4.2 — *evaluative*

> **Reverdy's capacity to infuse words with structural beauty**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 3` · story kind **eventful**

### THE STORY

Author Pierre Reverdy and artist Juan Gris originally set out to create the collaborative work *Au Soleil du Plafond*. The project was halted when Gris died in 1927, having completed only half of the illustrations planned for Reverdy's twenty poems. Decades later, publisher Tériade took up the unfinished book and formally published it in Paris in 1955.

<details><summary>Round 1 (before challenge)</summary>

> Juan Gris and Pierre Reverdy originally began collaborating on *Au Soleil du Plafond* in 1916 with the dealer and publisher Léonce Rosenberg. 
> 
> The original publication effort collapsed during World War I and was left incomplete following Gris’s death in 1927. 
> 
> Publisher Tériade finally realized and printed the project decades later in 1955. 
> 
> The resulting volume paired Reverdy's handwritten text with eleven full-page color lithographs based on Gris’s work.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Juan Gris and Pierre Reverdy collaborated on *Au Soleil du Plafond* — metmuseum.org / art-books.com / abebooks.com
* UNATTESTED Juan Gris and Pierre Reverdy originally began collaborating in 1916 with the dealer and publisher Léonce Rosenberg — no retrieved source supports this
* UNATTESTED The original publication effort collapsed during World War I — no retrieved source supports this
* CONFIRMED The project was left incomplete following Juan Gris's death in 1927 — emuseum.toledomuseum.org / art-books.com
* CONFIRMED Publisher Tériade published the project in 1955 — art-books.com / abebooks.com
* UNATTESTED The resulting volume paired Reverdy's handwritten text with eleven full-page color lithographs based on Gris's work — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Publisher Tériade finally realized and printed the project decades later in 1955.  
**query:** `"Au Soleil du Plafond" publisher printed 1955 tériade` → 15 relevant sentence(s)

  - `metmuseum.org` (tier1) — Title: Au Soleil du Plafond ; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine) ; Author: Written by Pierre Reverdy (French, 1889– ...
  - `art-books.com` (unverified) — Le Livre From au Soleil du Plafond.
  - `art-books.com` (unverified) — Paris: Tériade Editeur, 1955.
  - `abebooks.com` (market) — From au Soleil du Plafond.

**claim:** Juan Gris and Pierre Reverdy originally began collaborating on *Au Soleil du Plafond* in 1916 with the dealer and publisher Léonce Rosenberg.  
**query:** `"Au Soleil du Plafond" 1916 publisher pierre reverdy` → 20 relevant sentence(s)

  - `metmuseum.org` (tier1) — Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)
  - `art-books.com` (unverified) — Pierre Reverdy 1889-1960 illustrated by Juan Gris.
  - `art-books.com` (unverified) — Le Livre From au Soleil du Plafond.
  - `art-books.com` (unverified) — The publisher is known as Tériade (1897- ...

**claim:** The original publication effort collapsed during World War I and was left incomplete following Gris’s death in 1927.  
**query:** `"Au Soleil du Plafond" 1927 original publication effort` → 16 relevant sentence(s)

  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond.
  - `emuseum.toledomuseum.org` (unverified) — Artist Juan Gris (Spanish, 1887-1927).
  - `emuseum.toledomuseum.org` (unverified) — Gris died in 1927, having only completed half the illustrations for the twenty poems.
  - `art-books.com` (unverified) — Le Livre From au Soleil du Plafond.

</details>


## credit_line 6.1 — *evaluative*

> **rarely emerge from the archives**

`CONFIRMED 4` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 3` · story kind **active**

### THE STORY

In 1916, poet Pierre Reverdy and artist Juan Gris began working together on the project *Au Soleil du Plafond*. It took until 1955 for the art publisher Tériade to bring the work into print in Paris. In that edition, Reverdy published a scaled-back version of their original plans alongside lithographs produced after Gris's designs.

<details><summary>Round 1 (before challenge)</summary>

> Juan Gris and poet Pierre Reverdy began developing *Au Soleil du Plafond* around 1916 as a collaborative project where poems and images were conceived in direct dialogue. 
> 
> The publication was derailed and left unfinished following Gris’s premature death in 1927 at the age of forty. 
> 
> The project remained unrealized for nearly four decades until the art publisher Tériade revived it and brought it to completion in 1955. 
> 
> Reverdy published a scaled-back edition of their original plan, issuing the text and Gris's illustrations as a suite of unbound lithographs.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

CONFIRMED Juan Gris and poet Pierre Reverdy collaborated on *Au Soleil du Plafond* starting around 1916 — poetrysociety.org / alamy.com
UNATTESTED Poems and images were conceived in direct dialogue — no retrieved source supports this
UNATTESTED The publication was derailed and left unfinished following Gris’s premature death in 1927 at the age of forty — no retrieved source supports this (only Gris's lifespan 1887–1927 is attested in 1stdibs.com)
CONFIRMED Tériade published the book in 1955 — araderbooks.com
CONFIRMED Reverdy published a scaled-back edition of their original plans in 1955 — henripeyrefi.ws.gc.cuny.edu
CONFIRMED The work includes text and lithographs after Juan Gris — araderbooks.com / 1stdibs.com
UNATTESTED The publication was issued specifically as an unbound suite of lithographs — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The project remained unrealized for nearly four decades until the art publisher Tériade revived it and brought it to completion in 1955.  
**query:** `"Au Soleil du Plafond" publisher 1955 project remained` → 15 relevant sentence(s)

  - `1stdibs.com` (market) — This exquisite lithograph after Juan Gris (1887–1927), titled Bouteille (Bottle), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...
  - `araderbooks.com` (unverified) — Au soleil du plafond.
  - `araderbooks.com` (unverified) — Paris: Tériade Éditeur, [1955].
  - `araderbooks.com` (unverified) — Folio (16 ½” x 12 ½”, 420 x 320 mm): 66 leaves, 1–152 [4] (tribute to Gris, blank, ...

**claim:** Juan Gris and poet Pierre Reverdy began developing *Au Soleil du Plafond* around 1916 as a collaborative project where poems and images were conceived  
**query:** `"Au Soleil du Plafond" 1916 pierre reverdy developing` → 17 relevant sentence(s)

  - `alamy.com` (unverified) — Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.
  - `alamy.com` (unverified) — Pierre Reverdy, 1916 (published 1955), Color Lithograph on Paper | ArchiVerse.
  - `jstor.org` (tier2) — Asp Au soleil du plafond et autres po?mes (Paris ...
  - `jstor.org` (tier2) — Pierre Reverdy a choisi de s'abstenir de publier ...

**claim:** The publication was derailed and left unfinished following Gris’s premature death in 1927 at the age of forty.  
**query:** `"Au Soleil du Plafond" 1927 publication derailed unfinished` → 2 relevant sentence(s)

  - `scribd.com` (unverified) — Image and radiography of Juan Gris 189.
  - `scribd.com` (unverified) — Reverdy, Pierre: Au soleil du plafond.

**claim:** Reverdy published a scaled-back edition of their original plan, issuing the text and Gris's illustrations as a suite of unbound lithographs.  
**query:** `"Au Soleil du Plafond" published reverdy scaled-back edition` → 13 relevant sentence(s)

  - `henripeyrefi.ws.gc.cuny.edu` (tier1) — It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond.
  - `poetrysociety.org` (unverified) — In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...
  - `etsy.com` (unverified) — Juan Gris, Bouteille (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph.
  - `researchgate.net` (unverified) — anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.

</details>


## credit_line 6.2 — *evaluative*

> **offering a glimpse into the transformative collaborations of early-20th-century artists**

`CONFIRMED 2` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 3` · story kind **active**

### THE STORY

*Au Soleil du Plafond* originated as a collaboration between the artist Juan Gris and the poet Pierre Reverdy, dating back to 1916. The project was left unrealized during Gris's lifetime and was taken up some thirty years later by the publisher Tériade in collaboration with Reverdy. In 1955, Tériade published the completed volume in Paris, featuring eleven colored lithographs alongside Reverdy's texts.

<details><summary>Round 1 (before challenge)</summary>

> The illustrated book was originally commissioned around 1916–1917 by the art dealer Léonce Rosenberg. 
> 
> The initial project stalled and was left incomplete after Juan Gris produced only 11 of the planned 20 gouaches before his premature death in 1927. 
> 
> Nearly thirty years later, publisher Tériade revived the project in collaboration with Pierre Reverdy to finally bring the volume to fruition. 
> 
> When published in 1955, Reverdy intended the finished work as a posthumous tribute to his late friend and collaborator.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* UNATTESTED The illustrated book was originally commissioned around 1916–1917 by the art dealer Léonce Rosenberg. — no retrieved source supports this
* UNATTESTED The initial project stalled and was left incomplete after Juan Gris produced only 11 of the planned 20 gouaches before his premature death in 1927. — no retrieved source supports this
* CONFIRMED Nearly thirty years later, publisher Tériade revived the project in collaboration with Pierre Reverdy to finally bring the volume to fruition. — [metmuseum.org]
* CONFIRMED The work was published in 1955. — [artsy.net], [abebooks.co.uk], [bonhams.com]
* UNATTESTED Reverdy intended the finished work as a posthumous tribute to his late friend and collaborator. — no retrieved source supports this

---

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** When published in 1955, Reverdy intended the finished work as a posthumous tribute to his late friend and collaborator.  
**query:** `"Au Soleil du Plafond" published 1955 reverdy intended` → 16 relevant sentence(s)

  - `metmuseum.org` (tier1) — Title: Au Soleil du Plafond ; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine) ; Author: Written by Pierre Reverdy (French, 1889– ...
  - `artsy.net` (market) — Au soleil du plafond Paris, Tériade Éditeur, 1955.
  - `artsy.net` (market) — 11 coloured lithographs, velin paper.
  - `artsy.net` (market) — 17 1/10 × 13 2/5 in | 43.5 × 34 cm.

**claim:** The initial project stalled and was left incomplete after Juan Gris produced only 11 of the planned 20 gouaches before his premature death in 1927.  
**query:** `"Au Soleil du Plafond" 1927 initial project stalled` → 16 relevant sentence(s)

  - `alamy.com` (unverified) — Au soleil du plafond), 1916, post-Cubist color lithograph still life ...
  - `alamy.com` (unverified) — 1927 Boulogne-sur-Seine), Gris collaborated with his friend, the poet Pierre ...
  - `openlibrary.org` (unverified) — Cover of: Au soleil du plafond et autres poèmes.
  - `openlibrary.org` (unverified) — Au soleil du plafond et autres poèmes.

**claim:** Nearly thirty years later, publisher Tériade revived the project in collaboration with Pierre Reverdy to finally bring the volume to fruition.  
**query:** `"Au Soleil du Plafond" publisher nearly thirty tériade` → 16 relevant sentence(s)

  - `abebooks.co.uk` (unverified) — Au soleil du plafond (Hardcover).
  - `abebooks.co.uk` (unverified) — Gris, Juan; Pierre Reverdy.
  - `abebooks.co.uk` (unverified) — Published by Tériade Éditeur, Paris, 1955.
  - `metmuseum.org` (tier1) — The project was taken up by Ténade some thirty years later, with the collaboration of the author (Reverdy).

</details>


## credit_line 7.1 — *evaluative*

> **highlights how visual artists**

`CONFIRMED 2` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 3` · story kind **eventful**

### THE STORY

Artist Juan Gris and writer Pierre Reverdy originally set out to create *Au soleil du plafond* with twenty planned illustrations. The project stalled when Gris died in 1927, leaving only eleven completed gouaches. Gris's son kept the eleven gouaches as his father left them, and the publisher Tériade later revived the project under Reverdy's supervision to produce a volume featuring Gris's eleven lithographs. While most records indicate that Tériade completed and published the work in 1955, other sources date the publication to 1948.

<details><summary>Round 1 (before challenge)</summary>

> The project was originally initiated around 1915–1916 under the direction of art dealer Léonce Rosenberg. 
> 
> Juan Gris and Pierre Reverdy conceived the livre d'artiste together to create text and imagery in harmony, intending to produce 20 illustrations corresponding to 20 poems. 
> 
> Work stalled when Gris died prematurely in 1927, leaving only 11 completed illustrations based on his gouaches. 
> 
> Publisher Tériade revived and completed the unfinished collaboration nearly thirty years later in 1955 alongside Reverdy. 
> 
> The missing artwork forced the creators to completely reconceive the book's planned portfolio structure as a posthumous tribute to Gris.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
### PART 1 — ADJUDICATE

* **UNATTESTED** The project was originally initiated around 1915–1916 under the direction of art dealer Léonce Rosenberg. — no retrieved source supports this
* **CONFIRMED** Juan Gris and Pierre Reverdy collaborated on the book *Au Soleil du Plafond*, which was intended to feature twenty poems/illustrations. — [emuseum.toledomuseum.org], [academia.edu]
* **UNATTESTED** Juan Gris and Pierre Reverdy conceived the livre d'artiste together to create text and imagery in harmony. — no retrieved source supports this
* **CONFIRMED** Juan Gris died in 1927 leaving 11 completed gouaches/illustrations. — [academia.edu], [newyorker.com], [dokumen.pub], [brill.com]
* **DISPUTED** Publication / completion date by Tériade — [academia.edu], [dokumen.pub], and [emuseum.toledomuseum.org] state it was published/completed in 1955 under Reverdy's supervision; [brill.com] dates the Tériade publication to 1948.
* **UNATTESTED** The missing artwork forced the creators to completely reconceive the book's planned portfolio structure as a posthumous tribute to Gris. — no retrieved source supports this

---

###
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Work stalled when Gris died prematurely in 1927, leaving only 11 completed illustrations based on his gouaches.  
**query:** `"Au Soleil du Plafond" died 1927 stalled prematurely` → 16 relevant sentence(s)

  - `newyorker.com` (tier2) — The volume has just been published, under the title “Au Soleil du Plafond ...
  - `newyorker.com` (tier2) — The son kept the eleven gouaches as his father had left ...
  - `academia.edu` (tier1) — Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...
  - `academia.edu` (tier1) — But Gris died in 1927, having only completed half the illustrations for the twenty ...

**claim:** Publisher Tériade revived and completed the unfinished collaboration nearly thirty years later in 1955 alongside Reverdy.  
**query:** `"Au Soleil du Plafond" publisher 1955 tériade revived` → 11 relevant sentence(s)

  - `emuseum.toledomuseum.org` (unverified) — Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...
  - `academia.edu` (tier1) — These works were intended to be included in the book Au soleil du plafond ...
  - `academia.edu` (tier1) — Tériade completed the book in 1955, under Reverdy's supervision.
  - `brill.com` (unverified) — Paris: Tériade, 1948.

</details>


## credit_line 8.1 — *evaluative*

> **inviting reflection on art as a shared divine expression**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 3` · story kind **eventful**

### THE STORY

In 1916, art dealer Léonce Rosenberg brought poet Pierre Reverdy and painter Juan Gris together to collaborate on *Au Soleil du Plafond*. The project came to an abrupt halt when Gris died of kidney failure in 1927 at only 40 years old, leaving behind 11 completed lithographs. Years later, publisher Tériade revived the undertaking. In 1955, Reverdy and Tériade finally published a scaled-back edition featuring Gris's 11 surviving color lithographs.

<details><summary>Round 1 (before challenge)</summary>

> Art dealer Léonce Rosenberg originally planned the publication around 1916 to 1917 as an illustrated collaboration between poet Pierre Reverdy and Juan Gris.
> 
> The initial plan called for Gris to create a matching plate for each of Reverdy's twenty poems.
> 
> The project was halted when Gris died of kidney failure in 1927 at age 40, having completed only 11 of the planned illustrations.
> 
> Nearly thirty years later, publisher Tériade revived and restructured the unfinished project with Reverdy.
> 
> The book was published in 1955 with Reverdy's handwritten texts reproduced alongside lithographs based on Gris's surviving compositions.
> 
> Reverdy framed the posthumous volume as a reunion with his deceased friend through work that transcended mortality.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Art dealer Léonce Rosenberg originally planned the publication around 1916 as a collaboration between Pierre Reverdy and Juan Gris. — [vascularandwoundclinic.co.za], [metmuseum.org], [poetrysociety.org]
* UNATTESTED The initial plan called for Gris to create a matching plate for each of Reverdy's twenty poems. — no retrieved source supports this
* CONFIRMED The project was halted when Gris died of kidney failure in 1927 at age 40, having completed 11 lithographs. — [abebooks.com], [araderbooks.com], [iberlibro.com], [artsy.net]
* CONFIRMED Tériade published the book in 1955. — [artsy.net], [henripeyrefi.ws.gc.cuny.edu], [tretyakovgallerymagazine.com]
* UNATTESTED Reverdy's handwritten texts were reproduced alongside lithographs based on Gris's surviving compositions. — no retrieved source supports this
* UNATTESTED Reverdy framed the posthumous volume as a reunion with his deceased friend through work that transcended mortality. — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The project was halted when Gris died of kidney failure in 1927 at age 40, having completed only 11 of the planned illustrations.  
**query:** `"Au Soleil du Plafond" halted died 1927 project` → 16 relevant sentence(s)

  - `abebooks.com` (market) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `abebooks.com` (market) — Juan Gris, 1887-1927) final body of work, as he died of kidney failure at only 40 years old ...
  - `araderbooks.com` (unverified) — Au soleil du plafond was José Victoriano González-Pérez (pseud.
  - `araderbooks.com` (unverified) — Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old ...

**claim:** Art dealer Léonce Rosenberg originally planned the publication around 1916 to 1917 as an illustrated collaboration between poet Pierre Reverdy and Jua  
**query:** `"Au Soleil du Plafond" 1916 1917 dealer léonce` → 18 relevant sentence(s)

  - `vascularandwoundclinic.co.za` (unverified) — In 1916, Léonce Rosenberg, Gris\'s dealer, brought them together to ...
  - `vascularandwoundclinic.co.za` (unverified) — From au Soleil du Plafond.
  - `gazette-drouot.com` (unverified) — From: *Au Soleil du Plafond*.
  - `gazette-drouot.com` (unverified) — From: *Au Soleil du ...

**claim:** The book was published in 1955 with Reverdy's handwritten texts reproduced alongside lithographs based on Gris's surviving compositions.  
**query:** `"Au Soleil du Plafond" published 1955 reverdy's handwritten` → 14 relevant sentence(s)

  - `metmuseum.org` (tier1) — Title: Au Soleil du Plafond ; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine) ; Author: Written by Pierre Reverdy (French, 1889– ...
  - `artsy.net` (market) — Au soleil du plafond Paris, Tériade Éditeur, 1955.
  - `artsy.net` (market) — 11 coloured lithographs ...
  - `poetrysociety.org` (unverified) — In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...

**claim:** The initial plan called for Gris to create a matching plate for each of Reverdy's twenty poems.  
**query:** `"Au Soleil du Plafond" plate initial called create` → 15 relevant sentence(s)

  - `etsy.com` (unverified) — May include: A vintage book cover with the title "Au soleil du plafond" ...
  - `etsy.com` (unverified) — May include: A page from a book with text about the artist Juan Gris and.
  - `tretyakovgallerymagazine.com` (unverified) — A double-page spread from the book Pierre Reverdy.
  - `tretyakovgallerymagazine.com` (unverified) — Au Soleil du plafond Paris, 1955.

</details>


---

# Moses and Monotheism


## credit_line 1.1 — *anchored*

> **Dalí's vivid illustrations**

`CONFIRMED 2` · `CORRECTED 1` · `DISPUTED 0` · `UNATTESTED 4` · story kind **active**

### THE STORY

Sigmund Freud published his controversial work *Moses and Monotheism* in 1939. Salvador Dalí later created illustrations, drawings, and printed text for an oversize French edition of the psychoanalyst's text. When the two men crossed paths in 1938, Freud saw confirmation of his own theories in the painter's work. Dalí, however, interpreted the encounter as a death sentence on surrealism itself.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created these illustrations for a luxury *livre d'artiste* edition of Sigmund Freud’s controversial final 1939 book, *Moses and Monotheism*. 
> 
> Published in Paris in the mid-1970s by Éditions Art & Valeur, the suite was issued in a limited edition of 250 copies. 
> 
> Rather than standard paper, the publisher and artist chose to print the color lithographs and drypoint etchings directly onto sheets of soft lambskin suede. 
> 
> The entire suite was issued unbound and housed within a custom burgundy suede portfolio box fitted with a cast metal relief cover. 
> 
> Dalí idolized Freud and based his surrealist visual language on psychoanalytic theories, though Freud famously remarked to him during their sole 1938 meeting that he was interested in Dalí's conscious craft rather than his unconscious mind.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Salvador Dalí created illustrations for Sigmund Freud's 1939 book *Moses and Monotheism* — [collections.museumofthebible.org], [daliparis.com], [facebook.com]
* CONFIRMED Sigmund Freud's 1939 work *Moses and Monotheism* was controversial — [scribd.com]
* UNATTESTED Dalí's suite was published in Paris in the mid-1970s by Éditions Art & Valeur in a limited edition of 250 copies — no retrieved source supports this
* UNATTESTED The color lithographs and drypoint etchings were printed directly onto sheets of soft lambskin suede — no retrieved source supports this
* UNATTESTED The entire suite was issued unbound and housed within a custom burgundy suede portfolio box fitted with a cast metal relief cover — no retrieved source supports this
* UNATTESTED Dalí idolized Freud and based his surrealist visual language on psychoanalytic theories — no retrieved source supports this
* CORRECTED Freud famously remarked during their sole 1938 meeting that he was interested in Dalí's conscious craft rather than his unconscious mind -> Freud saw in Dalí's work confirmation of some of his ideas, which Dalí interpreted in 1938 as a "death sentence on surrealism" — [scribd.com], [facebook.com]

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created these illustrations for a luxury *livre d'artiste* edition of Sigmund Freud’s controversial final 1939 book, *Moses and Monothei  
**query:** `"Moses and Monotheism" 1939 salvador created illustrations` → 12 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.
  - `daliparis.com` (unverified) — Moses and Monotheism is a book written in 1939 by Sigmund Freud.
  - `daliparis.com` (unverified) — The book consists of three essays and is an extension of Freud's work on ...
  - `facebook.com` (reject) — This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism," contains illustrations based on watercolor, pen ...

**claim:** Dalí idolized Freud and based his surrealist visual language on psychoanalytic theories, though Freud famously remarked to him during their sole 1938   
**query:** `"Moses and Monotheism" 1938 idolized surrealist visual` → 12 relevant sentence(s)

  - `instagram.com` (reject) — Inspired by Sigmund Freud's Moses and Monotheism, Kahlo imagined humanity's search for creation and belief through an extraordinary symbolic ...
  - `fridakahlo.org` (unverified) — However, In 1945, when Don Jose Domingo Lavin asked Frida Kahlo to read the book Moses and Monotheism by Sigmund Freud - whose psychoanalysis works Surrealism ...
  - `88invisiblemirrors.blog` (unverified) — If taken sequentially from his earliest work On Aphasia (1891) to Moses and Monotheism (1939), the story of psychoanalysis can be read as an ...
  - `scribd.com` (unverified) — and his controversial Moses and Monotheism Freud saw in Dali's work confirmation of some of (1939 [1934-1938]).

</details>


## credit_line 2.1 — *anchored*

> **breathe life into Freud’s narrative become evident**

`CONFIRMED 2` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 4` · story kind **eventful**

### THE STORY

In 1939, only months before his death, Sigmund Freud published *Moses and Monotheism*, his final and most controversial book. Decades later, Salvador Dalí produced an illustrated edition containing Freud's text accompanied by ten engravings and additional drawings. While some records date Dalí's portfolio to 1974, other sources date its publication to 1975.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created his illustration portfolio for Sigmund Freud's 1939 text *Moses and Monotheism* decades after Freud's death, publishing it in 1974 through Éditions Art et Valeur in Paris. 
> 
> Dalí drew the suite's drypoint etchings directly onto printing plates using a diamond stylus, printing the finished series over lithography onto sheets of lambskin. 
> 
> Dalí long regarded Freud as an intellectual hero and specifically praised *Moses and Monotheism* as Freud's most ambitious and tragic work. 
> 
> The exhibition *Picasso, Miró, Dalí: Unbound* at the Museum of Fine Arts, Boston highlights the edition as a dialogue where an artist interprets a foundational psychoanalytic text within the *livre d'artiste* format.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
PART 1 — ADJUDICATE

- CONFIRMED Salvador Dalí illustrated Sigmund Freud's *Moses and Monotheism* — [collections.museumofthebible.org], [vksart.com]
- CONFIRMED Sigmund Freud's *Moses and Monotheism* was published in 1939 — [jstor.org], [facebook.com], [cambridge.org]
- DISPUTED Salvador Dalí's edition of *Moses and Monotheism* was published in 1974 — [vksart.com] says 1974; [salvadordaliprintgallery.com] and [artsy.net] say 1975
- UNATTESTED Dalí's portfolio was published through Éditions Art et Valeur in Paris — no retrieved source supports this
- UNATTESTED Dalí created the suite using drypoint etchings drawn directly with a diamond stylus over lithography onto sheets of lambskin — no retrieved source supports this (note: [vksart.com] mentions ten engravings; [salvadordaliprintgallery.com] mentions drypoint plates generally)
- UNATTESTED Dalí regarded Freud as an intellectual hero and praised *Moses and Monotheism* as his most ambitious and tragic work — no retrieved source supports this
- UNATTESTED The exhibition *Picasso, Miró, Dalí: Unbound* at the Museum of Fine Arts, Boston highlights the edition as a dialogue in the *livre d'artiste* format — no retrieved source supports this
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created his illustration portfolio for Sigmund Freud's 1939 text *Moses and Monotheism* decades after Freud's death, publishing it in 19  
**query:** `"Moses and Monotheism" 1939 publishing 1974 salvador` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.
  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `jstor.org` (tier2) — (1904) to Moses and Monotheism (1939).
  - `jstor.org` (tier2) — Egyptian, had begged Freud not to publish ...

**claim:** Dalí drew the suite's drypoint etchings directly onto printing plates using a diamond stylus, printing the finished series over lithography onto sheet  
**query:** `"Moses and Monotheism" printing plates suite's drypoint` → 10 relevant sentence(s)

  - `salvadordaliprintgallery.com` (unverified) — Due to the fragile nature of the burrs, drypoint plates have a limited print ...
  - `salvadordaliprintgallery.com` (unverified) — MOSES AND MONOTHEISM, 1975 · Surrealist Visions, 1976 · PAPILLONS ANCIENNES ...
  - `tandemantiguedades.com` (unverified) — Moses and Monotheism” and “Ten Recipes for Immortality ...
  - `artsy.net` (market) — Salvador Dalí, 'Moses and Monotheism - Nightmare of Moses', 1975 ...

</details>


## credit_line 3.1 — *evaluative*

> **infusing it with his characteristic surrealism**

`CONFIRMED 1` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 6` · story kind **active**

### THE STORY

Sigmund Freud published *Moses and Monotheism* in 1939 as his final book, advancing the controversial thesis that Moses was an Egyptian follower of monotheism. In 1974, Salvador Dalí produced a new, oversize French edition of Freud's text accompanied by his own artwork. Sources describe Dalí's visual contributions differently: one record notes the volume contains ten engravings, while another states the illustrations are based on pen-and-ink and watercolor drawings.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created the illustrated edition of Sigmund Freud's final 1939 book, *Moses and Monotheism*, in 1974 for the Parisian publishing house Art et Valeur.
> 
> Dalí held a lifelong reverence for Freud's psychoanalytic theories, writing in 1957 that Freud's thesis on Moses was the psychoanalyst's most ambitious, difficult, and tragic argumentation.
> 
> To produce the imagery, Dalí engraved drawings using a diamond stylus directly onto massive gold plates.
> 
> The publisher printed the limited run of illustrations onto soft lambskin rather than standard paper.
> 
> Because animal skin shrinks and shifts in response to changes in ambient humidity, the resulting folios presented significant flattening and framing challenges for collectors and preservers.
> 
> The completed set was issued unbound inside Plexiglas folders and encased within a burgundy suede portfolio featuring a molded metal bas-relief cover based on Michelangelo's sculpture of Moses.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Salvador Dalí created an edition of Sigmund Freud's 1939 book *Moses and Monotheism* (Freud's last publication) in 1974 — [vksart.com], [dokumen.pub], [cambridge.org]
* UNATTESTED Dalí created the edition for the Parisian publishing house Art et Valeur — no retrieved source supports this
* UNATTESTED Dalí held a lifelong reverence for Freud's psychoanalytic theories, writing in 1957 that Freud's thesis on Moses was the psychoanalyst's most ambitious, difficult, and tragic argumentation — no retrieved source supports this
* DISPUTED The medium used to produce the illustrations — [vksart.com] says the edition consists of Freud's text accompanied by ten engravings; [collections.museumofthebible.org] says it contains illustrations based on watercolor, pen-and-ink drawings
* UNATTESTED Dalí engraved drawings using a diamond stylus directly onto massive gold plates — no retrieved source supports this
* UNATTESTED The publisher printed the limited run of illustrations onto soft lambskin rather than standard paper — no retrieved source supports this
* UNATTESTED Animal skin shrinks and shifts in response to changes in ambient humidity, presenting flattening and framing challenges — no retrieved source supports this
* UNATTESTED The completed set was issued unbound inside Plexiglas folders and encased within a burgundy suede portfolio featuring a molded metal bas-relief cover based on Michelangelo's sculpture of Moses — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created the illustrated edition of Sigmund Freud's final 1939 book, *Moses and Monotheism*, in 1974 for the Parisian publishing house Ar  
**query:** `"Moses and Monotheism" 1939 1974 publishing salvador` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — This oversize French edition of Sigmund Freud's 1939 published work, Moses and Monotheism, contains illustrations based on watercolor, pen-and-ink drawings ...
  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `facebook.com` (reject) — In 1939, only months before his death, Freud sent a copy of Moses and Monotheism from London to his niece Pauline — affectionately ...
  - `jstor.org` (tier2) — (1904) to Moses and Monotheism (1939).

**claim:** The publisher printed the limited run of illustrations onto soft lambskin rather than standard paper.  
**query:** `"Moses and Monotheism" publisher printed paper limited` → 15 relevant sentence(s)

  - `ebay.com` (unverified) — Moses and Monotheism by Sigmund Freud 1951 HC 1st Ed-3rd Printing VG ; Binding.
  - `pmc.ncbi.nlm.nih.gov` (tier1) — by D Titelman · 2026 — Freud's father religion: refinding Moses and Monotheism in 2023 · Abstract · Introduction · Anna Freud in Jerusalem · It's hard to be a Jew: Freud, ...
  - `zoraweb.com` (unverified) — 92 MOSES AND MONOTHEISM.
  - `zoraweb.com` (unverified) — part of my treatise on Moses.

**claim:** Dalí held a lifelong reverence for Freud's psychoanalytic theories, writing in 1957 that Freud's thesis on Moses was the psychoanalyst's most ambitiou  
**query:** `"Moses and Monotheism" 1957 lifelong reverence freud's` → 10 relevant sentence(s)

  - `tandfonline.com` (unverified) — The second part of this article explores Freud's Moses and Monotheism as a psychoanalytic attempt to address the historical roots of anti- ...
  - `quest-cdecjournal.it` (unverified) — In this respect, Moses and Monotheism seems to be a work more pertinent to historical psychology than to psychological history.
  - `dokumen.pub` (unverified) — On Freud's “Moses and Monotheism” discusses key themes in Sigmund Freud's final book, Moses and Monotheism, written between 1934 and 1939.
  - `iep.utm.edu` (tier1) — The answer, they suggest, could be offered by him in Moses and Monotheism only in terms of what he saw as essential to Judaism itself, a rigorous, spiritually ...

**claim:** To produce the imagery, Dalí engraved drawings using a diamond stylus directly onto massive gold plates.  
**query:** `"Moses and Monotheism" plates produce imagery engraved` → 11 relevant sentence(s)

  - `dokumen.pub` (unverified) — The exclusion of Abraham's article from Moses and Monotheism is, as the feminist Estelle Roith argues, another symptom of Freud's need to suppress the maternal ...
  - `jstor.org` (tier2) — Said (2003, 27-30) has called Moses and Monotheism a "Spätwerk" or a composition in Freud's late ...
  - `facebook.com` (reject) — Moses and Monotheism (1939), in which he advanced the controversial argument that Moses was not a Jew but an Egyptian follower of the ...
  - `invisibleculturejournal.com` (unverified) — In Moses and Monotheism, Freud famously remarked that the ...

</details>


## credit_line 4.1 — *anchored*

> **Freud's exploration of**

`CONFIRMED 1` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 5` · story kind **active** · **tells a disagreement**

### THE STORY

In 1939, Sigmund Freud published his final original book, *Moses and Monotheism*, while living in London during a time of war and illness. Decades later, Salvador Dalí engaged in a direct dialogue with the psychoanalyst by creating a portfolio to accompany Freud's text with engravings. While some sources date Dalí's publication to 1974, others list it as appearing in 1975. Freud's original text had prompted widespread debate among intellectuals upon release, and Dalí revived the controversial work by pairing the written volume with his own suite of ten prints.

<details><summary>Round 1 (before challenge)</summary>

> * The portfolio was created in 1974 to illustrate Sigmund Freud’s controversial 1939 book, which argued that Moses was an Egyptian nobleman and follower of Akhenaten rather than a Hebrew slave.
> * Dalí revered Freud as one of his greatest intellectual influences and wrote in his 1957 journal that *Moses and Monotheism* was Freud's "best and most tragic" work.
> * Dalí engraved his designs with a diamond stylus directly onto massive gold plates before printing them.
> * The publisher, Art et Valeur in Paris, produced the edition on soft sheepskin, a material notorious for shrinking and warping in response to changing humidity.
> * The project serves in the exhibition as an example of a *livre d'artiste* where a visual artist interprets an existing foundational text rather than originating the work alongside a living writer.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* DISPUTED Date of Dalí's portfolio — vksart.com and salvador-dali.org state 1974; salvadordaliprintgallery.com lists 1975
* CONFIRMED Freud's *Moses and Monotheism* was published in 1939 — [facebook.com], [en.wikipedia.org], [journals.sagepub.com]
* UNATTESTED Freud's book argued that Moses was an Egyptian nobleman and follower of Akhenaten rather than a Hebrew slave — no retrieved source supports this
* UNATTESTED Dalí revered Freud as one of his greatest intellectual influences and wrote in his 1957 journal that *Moses and Monotheism* was Freud's "best and most tragic" work — no retrieved source supports this
* UNATTESTED Dalí engraved his designs with a diamond stylus directly onto massive gold plates before printing them — no retrieved source supports this
* UNATTESTED The publisher, Art et Valeur in Paris, produced the edition on soft sheepskin, a material notorious for shrinking and warping in response to changing humidity — no retrieved source supports this
* UNATTESTED The project serves in the exhibition as an example of a *livre d'artiste* where a visual artist interprets an existing foundational text rather than originating the work alongside a living writer — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The portfolio was created in 1974 to illustrate Sigmund Freud’s controversial 1939 book, which argued that Moses was an Egyptian nobleman and follower  
**query:** `"Moses and Monotheism" 1974 1939 portfolio created` → 10 relevant sentence(s)

  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `matpsil.com` (unverified) — Moses and monotheism (Freud, 2010) with special interest on what it means to be Jewish for Freud.
  - `matpsil.com` (unverified) — «To try to put all religions in the same ...
  - `facebook.com` (reject) — Moses and Monotheism” (1939)—attempted to comprehend a world besieged by war and illness.

**claim:** Dalí engraved his designs with a diamond stylus directly onto massive gold plates before printing them.  
**query:** `"Moses and Monotheism" plates printing engraved designs` → 12 relevant sentence(s)

  - `salvadordaliprintgallery.com` (unverified) — MOSES AND MONOTHEISM, 1975 · Surrealist Visions, 1976 · PAPILLONS ...
  - `baumanrarebooks.com` (unverified) — Moses and Monotheism rare book for sale.
  - `baumanrarebooks.com` (unverified) — This First Edition by Sigmund FREUD ...
  - `baumanrarebooks.com` (unverified) — printing process; aquatint plates can often be hand colored, however.

**claim:** Dalí revered Freud as one of his greatest intellectual influences and wrote in his 1957 journal that *Moses and Monotheism* was Freud's "best and most  
**query:** `"Moses and Monotheism" 1957 revered greatest intellectual` → 12 relevant sentence(s)

  - `en.wikipedia.org` (tier1) — Moses and Monotheism is a 1939 book about the origins of monotheism written by Sigmund Freud, the founder of psychoanalysis.
  - `en.wikipedia.org` (tier1) — It is Freud's final original ...
  - `dokumen.pub` (unverified) — The responses to Moses and Monotheism from intellectuals and psychoanalysts around the world spanned the spectrum.
  - `dokumen.pub` (unverified) — But the book clearly reverberated ...

</details>


## credit_line 4.2 — *evaluative*

> **visualizing the psychological and spiritual transition from polytheistic beliefs**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 2` · `UNATTESTED 6` · story kind **inert**

### THE STORY

In his 1939 final publication *Moses and Monotheism*, Sigmund Freud argued that Moses was not originally Jewish. Salvador Dalí later created a suite of illustrations to accompany Freud's text, engaging directly with the psychoanalyst's controversial thesis. While some records date Dalí's work to 1939, other sources state the edition was published in 1974 with ten engravings.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created this 1974 suite to illustrate Sigmund Freud's final 1939 book, which theorized that Moses was an Egyptian nobleman devoted to the monotheistic cult of Aten rather than an ethnic Hebrew. 
> 
> Dalí considered Freud an intellectual hero and used a diamond stylus to draw the compositions directly onto gold printing plates. 
> 
> The publisher, Éditions Art & Valeur in Paris, produced the suite as an edition of ten color drypoints and lithographs printed onto sheepskin. 
> 
> Printing on sheepskin posed significant material challenges, as the hide is highly sensitive to humidity and frequently shrinks or warps out of frame. 
> 
> The portfolio was issued in a burgundy suede clamshell case mounted with a sculpted metal bas-relief based on Michelangelo’s *Moses*.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Salvador Dalí illustrated Sigmund Freud's book *Moses and Monotheism* — [collections.museumofthebible.org], [salvador-dali.org], [vksart.com]
* DISPUTED Date of Dalí's suite / work — [vksart.com] and [salvador-dali.org] say 1974; [mutualart.com] lists 1939
* CONFIRMED *Moses and Monotheism* was Freud's final publication/work from 1939 — [vksart.com], [jstor.org]
* CONFIRMED Freud's book theorized that Moses was not originally a Jew / ethnic Hebrew — [escholarship.org]
* UNATTESTED Freud theorized Moses was an Egyptian nobleman devoted to the monotheistic cult of Aten — no retrieved source supports this
* UNATTESTED Dalí considered Freud an intellectual hero — no retrieved source supports this
* UNATTESTED Dalí used a diamond stylus to draw the compositions directly onto gold printing plates — no retrieved source supports this
* UNATTESTED The publisher was Éditions Art & Valeur in Paris — no retrieved source supports this
* DISPUTED Format and technique of the suite — [vksart.com] states it consists of Freud's text accompanied by ten engravings; earlier answer said ten color drypoints and lithographs printed onto sheepskin ([collections.museumofthebible.org] notes text with illustrations and additional drawings, but sheepskin/lithographs are unmentioned)
* UNATTESTED Printing on sheepskin posed material challenges due to humidity sensitivity and warping — no retrieved source supports this
* UNATTESTED The portfolio was issued in a burgundy suede clamshell case mounted with a sculpted metal bas-relief based on Michelangelo’s *Moses* — no retrieved source supports this

---

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created this 1974 suite to illustrate Sigmund Freud's final 1939 book, which theorized that Moses was an Egyptian nobleman devoted to th  
**query:** `"Moses and Monotheism" 1974 1939 salvador created` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.
  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `mutualart.com` (market) — Salvador Dalí · Moses And Monotheism, 1939.
  - `salvador-dali.org` (unverified) — In Moïse et le Monothéisme (Moses and Monotheism) from 1974, the artist engages in a dialogue with Sigmund Freud through the text that the great Austrian ...

**claim:** Dalí considered Freud an intellectual hero and used a diamond stylus to draw the compositions directly onto gold printing plates.  
**query:** `"Moses and Monotheism" printing plates considered intellectual` → 12 relevant sentence(s)

  - `dokumen.pub` (unverified) — The complete and final version of Moses and Monotheism was at the printer's in Holland.
  - `dokumen.pub` (unverified) — Too old and ill to attend, Freud sent Anna from London to represent ...
  - `artunderwraps.com` (unverified) — Moses and Monotheism, An Outline of Psycho-analysis, and other works, Volume XXIV: Indexes and Bibliographies; published from 1956-1974.
  - `escholarship.org` (unverified) — Moses and Monotheism has often been read as a statement of Freud's rela- tions with Judaism.

</details>


## credit_line 5.1 — *evaluative*

> **delves into the complexities of religious origins**

`CONFIRMED 4` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 5` · story kind **active**

### THE STORY

In 1939, Sigmund Freud published his final book, *Moses and Monotheism*, after finding refuge in England. The text sparked widespread controversy by arguing that Moses was not Jewish, but rather an ancient Egyptian. In 1974, Salvador Dalí produced a dedicated edition of Freud's work featuring his own illustrations and an original preface.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created his illustration suite for Sigmund Freud's *Moses and Monotheism* in 1974 as part of the *livre d'artiste* tradition.
> 
> Freud had published the underlying text in 1939 while exiled in London, advancing the controversial psychoanalytic thesis that Moses was an Egyptian nobleman who transmitted Atenist monotheism to the Israelites and was later murdered by his followers.
> 
> Dalí deeply idolized Freud, having met him in London in 1938 just before the psychoanalyst died, and frequently turned to Freud's theories on myth, religion, and the subconscious throughout his career.
> 
> In addition to contributing original lithographs and etchings to the 1974 edition, Dalí wrote his own preface to Freud's text.
> 
> The work forms part of a larger sequence of graphic suites exploring Jewish history and biblical themes that Dalí produced under commercial contracts during the late 1960s and 1970s.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Salvador Dalí created an illustration suite for Sigmund Freud's *Moses and Monotheism* in 1974 — [vksart.com] (also [collections.museumofthebible.org], [facebook.com])
* UNATTESTED Dalí created his illustration suite as part of the *livre d'artiste* tradition — no retrieved source supports this
* CONFIRMED Freud published the text in 1939 while in England / exile — [tandfonline.com], [facebook.com]
* CONFIRMED Freud advanced the controversial thesis that Moses was an Egyptian — [facebook.com], [tandfonline.com]
* UNATTESTED Freud advanced the thesis that Moses transmitted Atenist monotheism and was later murdered by his followers — no retrieved source supports this
* UNATTESTED Dalí deeply idolized Freud, having met him in London in 1938 just before the psychoanalyst died, and frequently turned to Freud's theories on myth, religion, and the subconscious throughout his career — no retrieved source supports this
* UNATTESTED Dalí contributed lithographs and etchings to the 1974 edition — no retrieved source supports this (sources specify "ten engravings" or "drawings")
* CONFIRMED Dalí wrote his own preface to Freud's text — [daguerre.fr]
* UNATTESTED The work forms part of a larger sequence of graphic suites exploring Jewish history and biblical themes that Dalí produced under commercial contracts during the late 1960s and 1970s — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Freud had published the underlying text in 1939 while exiled in London, advancing the controversial psychoanalytic thesis that Moses was an Egyptian n  
**query:** `"Moses and Monotheism" published 1939 underlying exiled` → 9 relevant sentence(s)

  - `facebook.com` (reject) — First published in 1939.....In Moses and Monotheism, Freud speculates that Moses was not Jewish, but actually born into Ancient Egyptian ...
  - `tandfonline.com` (unverified) — by R Pinkas · 2025 · Cited by 2 — Freud found refuge in England, where he published his last book, Moses and Monotheism, in 1939.
  - `reddit.com` (reject) — Sigmund Freud's book Moses and Monotheism (German: Der Mann Moses und die monotheistische Religion) from 1939 makes the claim that Judaism comes ...
  - `pmc.ncbi.nlm.nih.gov` (tier1) — by D Titelman · 2026 — In this reading, Moses and Monotheism stands out not as Freud's rejection of Judaism but, on the contrary, as a testimony to his re-alignment ...

**claim:** Dalí deeply idolized Freud, having met him in London in 1938 just before the psychoanalyst died, and frequently turned to Freud's theories on myth, re  
**query:** `"Moses and Monotheism" 1938 died deeply idolized` → 12 relevant sentence(s)

  - `facebook.com` (reject) — In 1939, Sigmund Freud finished his last book, "Moses and Monotheism", shortly before his death.
  - `facebook.com` (reject) — It caused outrage and drew much criticism ...
  - `dokumen.pub` (unverified) — On Freud's “Moses and Monotheism” discusses key themes in Sigmund Freud's final book, Moses and Monotheism, written between 1934 and 1939.
  - `bookey.app` (unverified) — In "Moses and Monotheism," Sigmund Freud delves into the intricate relationships between Judaism and Christianity through the lens of religion and cultural ...

**claim:** Salvador Dalí created his illustration suite for Sigmund Freud's *Moses and Monotheism* in 1974 as part of the *livre d'artiste* tradition.  
**query:** `"Moses and Monotheism" 1974 salvador created illustration` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.
  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `daguerre.fr` (unverified) — FREUD (Sigmund) Moses and Monotheism.
  - `daguerre.fr` (unverified) — Translated from the German by Anne Berman; [preface and illustrations by Salvador Dali].

**claim:** In addition to contributing original lithographs and etchings to the 1974 edition, Dalí wrote his own preface to Freud's text.  
**query:** `"Moses and Monotheism" 1974 addition contributing original` → 13 relevant sentence(s)

  - `pmc.ncbi.nlm.nih.gov` (tier1) — by D Titelman · 2026 — In this reading, Moses and Monotheism stands out not as Freud's rejection of Judaism but, on the contrary, as a testimony to his re-alignment ...
  - `dokumen.pub` (unverified) — On Freud's “Moses and Monotheism” discusses key themes in Sigmund Freud's final book, Moses and Monotheism, written between 1934 and 1939.
  - `tandfonline.com` (unverified) — by R Pinkas · 2022 · Cited by 5 — Freud began writing Moses and Monotheism in 1934, at the age of 78.
  - `tandfonline.com` (unverified) — The first two parts, 'Moses an Egyptian' and 'If Moses was an Egyptian', ...

</details>


## credit_line 5.2 — *anchored*

> **setting the stage for Dalí's evocative interpretations**

`CONFIRMED 3` · `CORRECTED 0` · `DISPUTED 0` · `UNATTESTED 4` · story kind **active**

### THE STORY

In 1939, Sigmund Freud published *Moses and Monotheism* as his final original book on the origins of religion. Salvador Dalí later took Freud's text as direct influence to produce his own artistic suite titled *Moses and Monotheism*. To create the project, Dalí had the work executed on custom parchment material made in conjunction with Art et Valeur.

<details><summary>Round 1 (before challenge)</summary>

> * Sigmund Freud published *Moses and Monotheism* in 1939 as his final completed book, arguing the provocative thesis that Moses was an Egyptian nobleman devoted to Atenism rather than a native Hebrew.
> * Salvador Dalí considered Freud one of his foremost intellectual heroes and created this illustrated suite in 1974 to visually interpret Freud's foundational text.
> * The project was published as a luxury *livre d'artiste* edition by Éditions Art et Valeur in Paris.
> * The portfolio was produced as a collaborative endeavor combining fine-art printmaking techniques, including original drypoints and lithographs printed directly onto sheepskin parchment.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED: Sigmund Freud published *Moses and Monotheism* in 1939 as his final book — [theses.gla.ac.uk], [en.wikipedia.org], [archive.org], [journals.sagepub.com]
* UNATTESTED: Freud argued the provocative thesis that Moses was an Egyptian nobleman devoted to Atenism rather than a native Hebrew — no retrieved source supports this
* CONFIRMED: Salvador Dalí created an artwork suite influenced by Sigmund Freud's *Moses and Monotheism* — [artsy.net], [whybuyart.blogspot.com]
* UNATTESTED: Salvador Dalí considered Freud one of his foremost intellectual heroes and created this illustrated suite in 1974 — no retrieved source supports this
* CONFIRMED: The project was produced on custom material/parchment with Art et [Valeur] — [whybuyart.blogspot.com]
* UNATTESTED: The project was published as a luxury *livre d'artiste* edition in Paris — no retrieved source supports this
* UNATTESTED: The portfolio was produced as a collaborative endeavor combining fine-art printmaking techniques, including original drypoints and lithographs printed directly onto sheepskin parchment — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** The portfolio was produced as a collaborative endeavor combining fine-art printmaking techniques, including original drypoints and lithographs printed  
**query:** `"Moses and Monotheism" printmaking printed parchment portfolio` → 12 relevant sentence(s)

  - `artsy.net` (market) — Salvador Dalí, 'Moise et Monotheisme, Moses and Monotheism ', ca.
  - `facebook.com` (reject) — The Tablets of the Law (Les Tables de la Loi) from Moses and Monotheism.
  - `whybuyart.blogspot.com` (unverified) — This is a high grade work on custom material/parchment.
  - `whybuyart.blogspot.com` (unverified) — Influence: "Moses and Monotheism" by Sigmund Freud.

**claim:** Sigmund Freud published *Moses and Monotheism* in 1939 as his final completed book, arguing the provocative thesis that Moses was an Egyptian nobleman  
**query:** `"Moses and Monotheism" published 1939 sigmund monotheism` → 13 relevant sentence(s)

  - `amazon.com` (unverified) — Moses and Monotheism [Freud, Sigmund] on Amazon.com.
  - `amazon.com` (unverified) — Sigmund Freud (1856–1939) stands as one of the most influential figures of ...
  - `en.wikipedia.org` (tier1) — Moses and Monotheism is a 1939 book about the origins of monotheism written by Sigmund Freud, the founder of psychoanalysis.
  - `en.wikipedia.org` (tier1) — It is Freud's final original ...

**claim:** Salvador Dalí considered Freud one of his foremost intellectual heroes and created this illustrated suite in 1974 to visually interpret Freud's founda  
**query:** `"Moses and Monotheism" 1974 salvador considered foremost` → 12 relevant sentence(s)

  - `dokumen.pub` (unverified) — 41 On Salvador, see Gabriel Salvador, Joseph Salvador, sa vie et ses ...
  - `dokumen.pub` (unverified) — Moses and Monotheism,” (Tübingen: Niemeyer, 2006), 203–216; republished in ...
  - `journals.sagepub.com` (unverified) — The author considers Freud's final book, Moses and Monotheism, as a serious work in which Freud proposes his theory of Jewishness, focusing on history ...
  - `theologicalstudies.net` (unverified) — and Moses and Monotheism.

</details>


## credit_line 6.1 — *evaluative*

> **the book itself is an artwork**

`CONFIRMED 4` · `CORRECTED 0` · `DISPUTED 1` · `UNATTESTED 4` · story kind **inert**

### THE STORY

Sigmund Freud finished and published his final book, *Moses and Monotheism*, in 1939, only months before his death. Decades later, Salvador Dalí produced an illustrated edition containing his drawings and engravings alongside Freud's text. While some records date Dalí's edition to 1974, others date the project to 1974–1975. The publishers issued a total edition of 300 copies, printing the work directly onto soft glove sheepskin.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created his illustrations in 1974 for a luxury *livre d'artiste* edition of Sigmund Freud’s final book, *Moses and Monotheism*, published by Éditions Art & Valeur in Paris.
> 
> Dalí chose to illustrate the work because he held a lifelong fascination with Freud's psychoanalytic theories and considered Freud among his greatest heroes.
> 
> The edition of 300 was printed directly onto soft glove sheepskin, a temperamental material known to shrink and warp with changes in humidity.
> 
> The volume was published posthumously decades after Freud's 1939 death, pairing Freud's controversial thesis on the Egyptian origins of Moses with Dalí's Surrealist interpretations.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* CONFIRMED Salvador Dalí illustrated Sigmund Freud's book *Moses and Monotheism* — [collections.museumofthebible.org], [vksart.com]
* DISPUTED The work/illustrations date to 1974 — [vksart.com] dates it to 1974; [artsy.net] and [sothebys.com] date it to 1974–75 (1974/75)
* CONFIRMED *Moses and Monotheism* was Sigmund Freud's final/last published book — [vksart.com], [researchgate.net]
* UNATTESTED The edition was a luxury *livre d'artiste* published by Éditions Art & Valeur in Paris — no retrieved source supports this
* UNATTESTED Dalí chose to illustrate the work because of a lifelong fascination with Freud's psychoanalytic theories and considering Freud among his greatest heroes — no retrieved source supports this
* CONFIRMED The total edition consisted of 300 printed on soft glove sheepskin — [lockportstreetgallery.com]
* UNATTESTED Soft glove sheepskin is a temperamental material known to shrink and warp with changes in humidity — no retrieved source supports this
* CONFIRMED Sigmund Freud died in 1939, shortly after the 1939 publication of *Moses and Monotheism* — [researchgate.net], [collections.museumofthebible.org], [dokumen.pub]
* UNATTESTED Dalí's volume paired Freud's controversial thesis on the Egyptian origins of Moses with Dalí's Surrealist interpretations — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created his illustrations in 1974 for a luxury *livre d'artiste* edition of Sigmund Freud’s final book, *Moses and Monotheism*, publishe  
**query:** `"Moses and Monotheism" 1974 published salvador created` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.
  - `vksart.com` (unverified) — Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.
  - `artsy.net` (market) — Available for sale from Gilden's Art Gallery, Salvador Dalí, Moses and Monotheism (1974/75), Complete Set of Ten Original Hand Signed and Numbered Drypoint…
  - `sothebys.com` (market) — Moses and Monotheism by Salvador Dali, 1974-75.

**claim:** The volume was published posthumously decades after Freud's 1939 death, pairing Freud's controversial thesis on the Egyptian origins of Moses with Dal  
**query:** `"Moses and Monotheism" published 1939 volume posthumously` → 14 relevant sentence(s)

  - `ia802907.us.archive.org` (unverified) — led by him, did in fact take place.
  - `ia802907.us.archive.org` (unverified) — MOSES AND MONOTHEISM.
  - `zoraweb.com` (unverified) — 2l6 MOSES AND MONOTHEISM has not proved so easy to solve.
  - `zoraweb.com` (unverified) — One cannot,however ...

**claim:** The edition of 300 was printed directly onto soft glove sheepskin, a temperamental material known to shrink and warp with changes in humidity.  
**query:** `"Moses and Monotheism" printed edition directly sheepskin` → 13 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — This oversize French edition of Sigmund Freud's 1939 published work, Moses and Monotheism, contains illustrations based on watercolor, pen-and-ink drawings ...
  - `lockportstreetgallery.com` (unverified) — Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by ...
  - `lockportstreetgallery.com` (unverified) — The total edition consists on 300 on soft glove sheepskin.
  - `facebook.com` (reject) — This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism," contains illustrations based on watercolor, pen ...

</details>


## credit_line 7.1 — *evaluative*

> **bridging literary and visual art forms**

`CONFIRMED 3` · `CORRECTED 2` · `DISPUTED 2` · `UNATTESTED 4` · story kind **active** · **tells a disagreement**

### THE STORY

In 1939, Sigmund Freud published his final major work, *Moses and Monotheism*, putting forward the controversial argument that Moses was Egyptian rather than Hebrew. Decades later, publisher Art et Valeur in Paris produced a luxury French edition of the text featuring illustrations by Salvador Dalí based on pen-and-ink and watercolor drawings. Sources date Dalí's suite differently, with some records citing 1974 while individual edition prints are dated 1975. The prints, which include Dalí's depiction of Moses and the Egyptian pharaoh Akhenaten, placed the artist in direct visual dialogue with Freud's disputed psychoanalytic text.

<details><summary>Round 1 (before challenge)</summary>

> Salvador Dalí created this suite of illustrations in 1974 for a French luxury edition of Sigmund Freud's final 1939 book, *Moses and Monotheism*, published by Éditions Art & Valeur in Paris. Dalí drew upon Freud's provocative psychoanalytic thesis asserting that Moses was not Hebrew, but an Egyptian nobleman and follower of Akhenaten who was eventually murdered by his followers. Dalí had idolized Freud's theories on the subconscious since the 1920s and considered the text one of the psychoanalyst's most daring works. To create the edition, Dalí drew with a diamond stylus onto printing plates, combining lithography and drypoint etching directly onto sheets of sheepskin. The portfolio was issued as an unbound loose-leaf livre d'artiste in an edition of 300, encased inside a velvet-lined folio featuring a cast bas-relief metal cover.

</details>

<details><summary>Adjudication — claim by claim</summary>

```
**PART 1 — ADJUDICATE**

* DISPUTED Salvador Dalí created this suite of illustrations in 1974 — salvador-dali.org dates *Moïse et le Monothéisme* to 1974; singulart.com dates it to 1975
* CONFIRMED French edition of Sigmund Freud's 1939 book, *Moses and Monotheism* — collections.museumofthebible.org / cambridge.org / jstor.org
* CONFIRMED Freud's final book — cambridge.org ("Freud's last significant work") / facebook.com ("In 1939, only months before his death")
* CORRECTED Published by Éditions Art & Valeur in Paris -> Published by Art et Valeur, Paris — singulart.com
* CONFIRMED Freud's thesis asserted that Moses was Egyptian / connected to Akhenaten — jstor.org ("Egyptian") / singulart.com ("Moses & Akhenaton")
* UNATTESTED Moses was a follower of Akhenaten who was eventually murdered by his followers — no retrieved source supports this
* UNATTESTED Dalí had idolized Freud's theories on the subconscious since the 1920s and considered the text one of the psychoanalyst's most daring works — no retrieved source supports this
* CORRECTED Dalí drew with a diamond stylus onto printing plates, combining lithography and drypoint etching directly onto sheets of sheepskin -> The edition contains illustrations based on watercolor, pen-and-ink drawings — collections.museumofthebible.org
* DISPUTED Issued in an edition of 300 -> singulart.com indicates an edition numbered out of 250 (e.g., 226/250); other sources do not state the total run
* UNATTESTED The portfolio was issued as an unbound loose-leaf livre d'artiste — no retrieved source supports this
* UNATTESTED Encased inside a velvet-lined folio featuring a cast bas-relief metal cover — no retrieved source supports this

***

**
```

</details>

<details><summary>Challenge queries and the evidence they returned</summary>

**claim:** Salvador Dalí created this suite of illustrations in 1974 for a French luxury edition of Sigmund Freud's final 1939 book, *Moses and Monotheism*, publ  
**query:** `"Moses and Monotheism" 1974 1939 published salvador` → 11 relevant sentence(s)

  - `collections.museumofthebible.org` (unverified) — This oversize French edition of Sigmund Freud's 1939 published work, Moses and Monotheism, contains illustrations based on watercolor, pen-and-ink drawings ...
  - `facebook.com` (reject) — In 1939, only months before his death, Freud sent a copy of Moses and Monotheism from London to his niece Pauline — affectionately called “Poppy ...
  - `jstor.org` (tier2) — (1904) to Moses and Monotheism (1939).
  - `jstor.org` (tier2) — Egyptian, had begged Freud not to publish ...

**claim:** To create the edition, Dalí drew with a diamond stylus onto printing plates, combining lithography and drypoint etching directly onto sheets of sheeps  
**query:** `"Moses and Monotheism" printing plates create edition` → 12 relevant sentence(s)

  - `singulart.com` (unverified) — Moses and Monotheism Moses & Akhenaton ; SIGNED · Hand Signed ; PUBLISHER · Art et Valeur, Paris ; EDITION NUMBER · 226/250 ; MEASUREMENTS · 25.4" x 19.6" ; YEAR · 1975
  - `dokumen.pub` (unverified) — The complete and final version of Moses and Monotheism was at the printer's in Holland.
  - `dokumen.pub` (unverified) — Too old and ill to attend, Freud sent Anna from London to represent ...
  - `salvador-dali.org` (unverified) — In Moïse et le Monothéisme (Moses and Monotheism) from 1974, the artist engages in a dialogue with Sigmund Freud through the text that the great Austrian ...

</details>

