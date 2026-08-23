# Raw results — 37 credit_lines × 2 engines = 74 retrievals

**37 Serper + 37 Gemini grounded · ~$0.259 · 142s**

Each credit_line becomes ONE question, in two encodings (D507):

- **Serper** — compiled keywords: quoted work + named agents + `why` + year. No framing words; the question sent verbatim to Serper returns nothing.
- **Gemini** — the question verbatim: *"What story can be told to visitors of {exhibition} about {work}, {credit_line}?"* with the matrix attached.

Sentence marks: **R** relevant · w weak · **X** irrelevant (D505 gate). `kind` from `material_kind`, before → after gating.


---

# Le Lézard aux plumes d’or (The Lizard with Golden Feathers)


## credit_line 2.1 — *evaluative* / relative

> **revolutionized the book as an art form with its deep collaboration**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 revolutionized collaboration`

8 results · kind **active → active** · R10 w0 X6

**1. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's ... Broder's collaboration with Miró resulted in the publication of the ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Broder's collaboration with Miró resulted in the publication of the ...  
    <sub>names broder, miro</sub>

**2. Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**3. Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9)**  
`choicecontemporary.com` · tier `unverified`  
> Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9). Joan Miró. Regular price $7,480.00 USD. Lithograph in colors on B.F.K. Rives paper, watermarked.

  - **R** Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Regular price $7,480.00 USD.  
    <sub>about someone else (Regular), not this stop</sub>
  - **X** Lithograph in colors on B.F.K.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - **X** Rives paper, watermarked.  
    <sub>about someone else (Rives), not this stop</sub>

**4. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. Virtual Member Lecture: Picasso, Miró, Dalí**  
`mfa.org` · tier `tier1`  
> ... Broder, printed by Mourlot Frères, Paris, 1971. Illustrated book with ... Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers. Credit.

  - **R** Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names mourlot, broder</sub>
  - **X** Illustrated book with ...  
    <sub>about someone else (Illustrated), not this stop</sub>
  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers.  
    <sub>names golden feathers, the lizard, joan miro</sub>

**6. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**7. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, joan miro, le lezard</sub>

**8. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, revolutionized the book as an art form with its deep collaboration?`

kind **eventful → active** · R4 w0 X1

> Joan Miró initially completed the lithographs for this collaborative project between 1963 and 1967 for a planned 1967 release. 
> 
> After the initial printing was finished, Miró and publisher Louis Broder discovered a defect in the chosen paper that degraded and altered the lithographic ink colors. 
> 
> Because the original zinc printing plates had already been discarded, the entire existing run had to be abandoned. 
> 
> Miró was forced to redraw a completely new set of lithographs from scratch, delaying the book's final publication until 1971. 
> 
> Unlike many *livres d’artiste* where an artist illustrates another author's work, Miró authored both the poetry and the accompanying handwritten script alongside his visual imagery.

  - **R** Joan Miró initially completed the lithographs for this collaborative project between 1963 and 1967 for a planned 1967 release.  
    <sub>names joan miro, miro, joan</sub>
  - **R** After the initial printing was finished, Miró and publisher Louis Broder discovered a defect in the chosen paper that degraded and altered the lithographic ink colors.  
    <sub>names louis broder, broder, louis</sub>
  - **X** Because the original zinc printing plates had already been discarded, the entire existing run had to be abandoned.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Miró was forced to redraw a completely new set of lithographs from scratch, delaying the book's final publication until 1971.  
    <sub>names miro</sub>
  - **R** Unlike many *livres d’artiste* where an artist illustrates another author's work, Miró authored both the poetry and the accompanying handwritten script alongside his visual imagery.  
    <sub>names miro</sub>


## credit_line 2.2 — *evaluative* / participial

> **focusing on the livre d'artiste**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 focusing livre`

8 results · kind **active → inert** · R10 w1 X5

**1. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**2. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**3. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**4. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**5. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...  
    <sub>names joan miro, broder, miro</sub>

**6. Joan Miró, 'Le Lézard aux Plumes d'Or (Mourlot 828)', 1971**  
`artsy.net` · tier `market`  
> Le Lézard aux Plumes d'Or (Mourlot 828), 1971. Lithograph printed in colours. 14 × 39 2/5 in | 35.5 × 100 cm. Forum Auctions: Prints & Editions (September 2021).

  - **R** Le Lézard aux Plumes d'Or (Mourlot 828), 1971.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **X** Lithograph printed in colours.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w 14 × 39 2/5 in | 35.5 × 100 cm.  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **X** Forum Auctions: Prints & Editions (September 2021).  
    <sub>about someone else (Forum Auctions), not this stop</sub>

**7. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, focusing on the livre d'artiste?`

kind **inert → inert** · R3 w1 X0

> Joan Miró authored both the surrealist poetic text and the lithographic illustrations for the project. 
> 
> The book was originally prepared between 1963 and 1967, but Miró and publisher Louis Broder discovered that a chemical flaw in the paper had altered the lithographs' ink colors. 
> 
> Because the original printing plates were destroyed or discarded after the botched run, Miró had to entirely redraw a new set of lithographs. 
> 
> The corrected definitive edition was finally published four years late in 1971.

  - **R** Joan Miró authored both the surrealist poetic text and the lithographic illustrations for the project.  
    <sub>names joan miro, miro, joan</sub>
  - **R** The book was originally prepared between 1963 and 1967, but Miró and publisher Louis Broder discovered that a chemical flaw in the paper had altered the lithographs' ink colors.  
    <sub>names louis broder, broder, louis</sub>
  - **R** Because the original printing plates were destroyed or discarded after the botched run, Miró had to entirely redraw a new set of lithographs.  
    <sub>names miro</sub>
  - w The corrected definitive edition was finally published four years late in 1971.  
    <sub>no entity of its own; snippet names louis broder</sub>


## credit_line 4.1 — *evaluative* / participial

> **showcasing how artists express these concepts through their unrivaled creativity**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 showcasing express`

8 results · kind **active → inert** · R10 w1 X4

**1. Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**4. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**5. Le Lézard aux Plumes d'Or (Mourlot 828) (1971) by Joan Miró | Artsy**  
`artsy.net` · tier `market`  
> Le Lézard aux Plumes d'Or (Mourlot 828), 1971. Lithograph printed in colours ... express the inner workings of the human psyche. Miró used color and ...

  - **R** Le Lézard aux Plumes d'Or (Mourlot 828), 1971.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **X** Lithograph printed in colours ...  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w express the inner workings of the human psyche.  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **R** Miró used color and ...  
    <sub>names miro</sub>

**6. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**7. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Miró Joan | 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris ...**  
`mutualart.com` · tier `market`  
> 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.

  - **R** 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.  
    <sub>names louis broder, le lezard, broder</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, showcasing how artists express these concepts through their unrivaled creativity?`

kind **eventful → inert** · R2 w1 X1

> Joan Miró composed both the surrealist poem and the accompanying imagery for the project. 
> 
> The book was originally prepared for publication in 1967, but mid-way through production, the inks chemically reacted with a defective batch of specially commissioned paper. 
> 
> Because the printer had already erased the original lithographic stones before the defect was discovered, the entire initial edition had to be abandoned. 
> 
> Miró then had to completely redraw a new set of lithographic plates, delaying the final publication with publisher Louis Broder until 1971.

  - **R** Joan Miró composed both the surrealist poem and the accompanying imagery for the project.  
    <sub>names joan miro, miro, joan</sub>
  - w The book was originally prepared for publication in 1967, but mid-way through production, the inks chemically reacted with a defective batch of specially commissioned paper.  
    <sub>no entity of its own; snippet names louis broder</sub>
  - **X** Because the printer had already erased the original lithographic stones before the defect was discovered, the entire initial edition had to be abandoned.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Miró then had to completely redraw a new set of lithographic plates, delaying the final publication with publisher Louis Broder until 1971.  
    <sub>names louis broder, broder, louis</sub>


## credit_line 5.1 — *anchored* / possessive

> **Broder's pivotal decision**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 pivotal decision`

8 results · kind **inert → inert** · R9 w2 X6

**1. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9)**  
`choicecontemporary.com` · tier `unverified`  
> Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9). Joan Miró. Regular price $7,480.00 USD. Lithograph in colors on B.F.K. Rives paper, watermarked.

  - **R** Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Regular price $7,480.00 USD.  
    <sub>about someone else (Regular), not this stop</sub>
  - **X** Lithograph in colors on B.F.K.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - **X** Rives paper, watermarked.  
    <sub>about someone else (Rives), not this stop</sub>

**5. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971. The complete set of 15 lithographs in colors, on Rives paper. 15 1/5 × 20 1/5 × ...

  - **R** Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - **X** The complete set of 15 lithographs in colors, on Rives paper.  
    <sub>about someone else (Rives), not this stop</sub>
  - w 15 1/5 × 20 1/5 × ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**6. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**7. Miró Joan | 15 WORKS: Le Lézard aux Plumes d'Or, Louis ...**  
`mutualart.com` · tier `market`  
> 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.

  - **R** 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.  
    <sub>names louis broder, le lezard, broder</sub>

**8. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ... For over 170 years, the name Mourlot has been associated with important graphic ...

  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>
  - **R** For over 170 years, the name Mourlot has been associated with important graphic ...  
    <sub>names mourlot</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Broder's pivotal decision?`

kind **eventful → eventful** · R5 w0 X0

> Joan Miró originally created a full set of eighteen color lithographs between 1963 and 1967 to illustrate his own surrealist poem for the publisher Louis Broder.
> 
> After the initial printing was finished, Broder and Miró discovered a manufacturing defect in the paper that chemically reacted with and degraded the ink colors.
> 
> Broder made the costly decision to reject and destroy the entire defective print run rather than release a substandard edition.
> 
> Because the original lithographic stones had already been erased in the Mourlot workshop, none of the initial compositions could simply be reprinted.
> 
> Consequently, Miró was forced to start completely from scratch, designing entirely new lithographic compositions that were ultimately published four years later in 1971.

  - **R** Joan Miró originally created a full set of eighteen color lithographs between 1963 and 1967 to illustrate his own surrealist poem for the publisher Louis Broder.  
    <sub>names louis broder, joan miro, broder</sub>
  - **R** After the initial printing was finished, Broder and Miró discovered a manufacturing defect in the paper that chemically reacted with and degraded the ink colors.  
    <sub>names broder, miro</sub>
  - **R** Broder made the costly decision to reject and destroy the entire defective print run rather than release a substandard edition.  
    <sub>names broder</sub>
  - **R** Because the original lithographic stones had already been erased in the Mourlot workshop, none of the initial compositions could simply be reprinted.  
    <sub>names mourlot</sub>
  - **R** Consequently, Miró was forced to start completely from scratch, designing entirely new lithographic compositions that were ultimately published four years later in 1971.  
    <sub>names miro</sub>


## credit_line 5.2 — *evaluative* / participial

> **allowing the artist to blend visual and textual narratives seamlessly**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 allowing artist`

8 results · kind **inert → inert** · R10 w1 X3

**1. Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'Or II” (1971, M.821). From Joan Miró's “Broder Collection.” In addition to lithography, Miró's talents spanned many ...

  - **R** “Le Lezard aux Plumes d'Or II” (1971, M.821).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” In addition to lithography, Miró's talents spanned many ...  
    <sub>names joan miro, broder, miro</sub>

**5. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**6. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, joan miro, le lezard</sub>

**7. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**8. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, allowing the artist to blend visual and textual narratives seamlessly?`

kind **eventful → eventful** · R4 w0 X1

> Joan Miró originally wrote the surreal poem himself and completed a first full run of eighteen lithographic plates with publisher Louis Broder in 1967. 
> 
> During that first printing attempt, a chemical defect in the specially commissioned paper caused the ink colors to alter and react unfavorably. 
> 
> Because the original lithographic stones and plates had already been erased before the defect came to light, Miró and Broder were forced to abandon the entire initial edition. 
> 
> Miró had to redraw and recreate a completely new set of compositions from scratch on different papers to successfully publish the project in 1971. 
> 
> To merge the textual and visual narratives, Miró lithographically reproduced his own handwritten script alongside the imagery across dozens of pages rather than using standard typeset text.

  - **R** Joan Miró originally wrote the surreal poem himself and completed a first full run of eighteen lithographic plates with publisher Louis Broder in 1967.  
    <sub>names louis broder, joan miro, broder</sub>
  - **X** During that first printing attempt, a chemical defect in the specially commissioned paper caused the ink colors to alter and react unfavorably.  
    <sub>about someone else (During), not this stop</sub>
  - **R** Because the original lithographic stones and plates had already been erased before the defect came to light, Miró and Broder were forced to abandon the entire initial edition.  
    <sub>names broder, miro</sub>
  - **R** Miró had to redraw and recreate a completely new set of compositions from scratch on different papers to successfully publish the project in 1971.  
    <sub>names miro</sub>
  - **R** To merge the textual and visual narratives, Miró lithographically reproduced his own handwritten script alongside the imagery across dozens of pages rather than using standard typeset text.  
    <sub>names miro</sub>


## credit_line 6.1 — *anchored* / possessive

> **Freud's exploration of**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 exploration`

3 results · kind **active → active** · R3 w0 X0

**1. Fall Signature Night: Picasso, Miró, Dalí**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names golden feathers, louis broder, the lizard</sub>

**2. Global Cultural Bulletin: August 2026**  
`cabanamagazine.substack.com` · tier `unverified`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, ...  
    <sub>names golden feathers, louis broder, the lizard</sub>

**3. Picasso, Miró, Dalí: Unbound**  
`mfa.org` · tier `tier1`  
> ... Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971 ...

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971 ...  
    <sub>names golden feathers, louis broder, the lizard</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Freud's exploration of?`

kind **inert → none** · R0 w0 X1 · NO RELIABLE INFORMATION

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## credit_line 8.1 — *anchored* / participial

> **drawing you into the surreal world that Joan Miró has crafted**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 drawing surreal`

8 results · kind **active → inert** · R9 w2 X4

**1. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789 ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Le Lézard aux plumes d'or - Philip Williams Posters**  
`postermuseum.com` · tier `reject`  
> Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers). Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...

  - **R** Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...  
    <sub>names joan miro, miro, joan</sub>

**5. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Admire Joan Miró's 1971 'Le Lézard aux plumes d'or,' featuring 15 vibrant lithographs. Secure this surreal masterpiece at Composition.Gallery!

  - **R** Admire Joan Miró's 1971 'Le Lézard aux plumes d'or,' featuring 15 vibrant lithographs.  
    <sub>names joan miro, le lezard, plumes</sub>
  - **X** Secure this surreal masterpiece at Composition.Gallery!  
    <sub>about someone else (Secure), not this stop</sub>

**6. Le Lézard aux Plumes d'Or (Mourlot 828) (1971) by Joan Miró | Artsy**  
`artsy.net` · tier `market`  
> Le Lézard aux Plumes d'Or (Mourlot 828), 1971. Lithograph printed in colours ... drawing that attempted to express the inner workings of the human psyche.

  - **R** Le Lézard aux Plumes d'Or (Mourlot 828), 1971.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **X** Lithograph printed in colours ...  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w drawing that attempted to express the inner workings of the human psyche.  
    <sub>no entity of its own; snippet names le lezard</sub>

**7. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, drawing you into the surreal world that Joan Miró has crafted?`

kind **eventful → active** · R4 w0 X1

> * Joan Miró authored both the surrealist poem and the visual compositions for *Le Lézard aux plumes d’or*.
> * He originally completed a full suite of lithographs for the project with publisher Louis Broder in 1967.
> * After production began, Miró and Broder discovered that a manufacturing defect in the specially commissioned paper caused the colored inks to deteriorate and alter.
> * Because the original lithographic stones had already been effaced, the damaged print run was rejected and largely destroyed.
> * Miró was forced to redraw entirely new plates and rewrite the text to publish the edition on new paper in 1971.

  - **R** * Joan Miró authored both the surrealist poem and the visual compositions for *Le Lézard aux plumes d’or*.  
    <sub>names le lezard aux plumes d’or, joan miro, le lezard</sub>
  - **R** * He originally completed a full suite of lithographs for the project with publisher Louis Broder in 1967.  
    <sub>names louis broder, broder, louis</sub>
  - **R** * After production began, Miró and Broder discovered that a manufacturing defect in the specially commissioned paper caused the colored inks to deteriorate and alter.  
    <sub>names broder, miro</sub>
  - **X** * Because the original lithographic stones had already been effaced, the damaged print run was rejected and largely destroyed.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** * Miró was forced to redraw entirely new plates and rewrite the text to publish the edition on new paper in 1971.  
    <sub>names miro</sub>


## credit_line 10.1 — *anchored* / appositive

> **Louis Broder, a figure renowned for his commitment to the art of the book**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 figure renowned`

8 results · kind **inert → inert** · R10 w0 X3

**1. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**3. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**4. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...  
    <sub>names joan miro, broder, miro</sub>

**5. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**6. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**7. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, joan miro, le lezard</sub>

**8. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Louis Broder, a figure renowned for his commitment to the art of the book?`

kind **eventful → eventful** · R5 w0 X0

> * Joan Miró paired his lithographs with his own poetry, revising verses originally written in the 1930s to create a unified work.
> * An initial version of the book with eighteen lithographs was printed in 1967 under publisher Louis Broder.
> * Broder and Miró discovered a paper manufacturing defect that caused chemical reactions and altered the ink colors.
> * Because of this flaw, Broder and Miró made the decision to abandon the 1967 run and destroy the printed sheets.
> * Because the original printing stones had already been erased, Miró had to recreate an entirely new suite of lithographs from scratch, delaying publication until 1971.

  - **R** * Joan Miró paired his lithographs with his own poetry, revising verses originally written in the 1930s to create a unified work.  
    <sub>names joan miro, miro, joan</sub>
  - **R** * An initial version of the book with eighteen lithographs was printed in 1967 under publisher Louis Broder.  
    <sub>names louis broder, broder, louis</sub>
  - **R** * Broder and Miró discovered a paper manufacturing defect that caused chemical reactions and altered the ink colors.  
    <sub>names broder, miro</sub>
  - **R** * Because of this flaw, Broder and Miró made the decision to abandon the 1967 run and destroy the printed sheets.  
    <sub>names broder, miro</sub>
  - **R** * Because the original printing stones had already been erased, Miró had to recreate an entirely new suite of lithographs from scratch, delaying publication until 1971.  
    <sub>names miro</sub>


## credit_line 10.2 — *evaluative* / relative

> **the exhibition highlights**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 exhibition highlights`

8 results · kind **active → active** · R9 w1 X2

**1. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789 ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Fall Signature Night: Picasso, Miró, Dalí | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names golden feathers, louis broder, the lizard</sub>

**5. Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions**  
`mourloteditions.com` · tier `unverified`  
> Original lithographic poster printed by Mourlot for an exhibition by ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Original lithographic poster printed by Mourlot for an exhibition by ...  
    <sub>names mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**6. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971 - Artsy**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, joan miro, le lezard</sub>

**7. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Global Cultural Bulletin: August 2026 - Cabana | Substack**  
`cabanamagazine.substack.com` · tier `unverified`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, ...  
    <sub>names golden feathers, louis broder, the lizard</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, the exhibition highlights?`

kind **eventful → eventful** · R3 w1 X1

> Joan Miró originally conceived and worked on *Le Lézard aux plumes d’or* to be published in 1967. 
> 
> Midway through the initial print run, Miró and publisher Louis Broder abandoned the entire first edition because the inks chemically reacted with and stained the specially commissioned paper. 
> 
> Because the original lithographic stones and plates had already been effaced when the paper defect was discovered, the entire project had to be restarted from scratch. 
> 
> Miró personally authored and calligraphed the accompanying Surrealist poem directly across the pages. 
> 
> The completed project took years of re-creation before finally being issued in 1971.

  - **R** Joan Miró originally conceived and worked on *Le Lézard aux plumes d’or* to be published in 1967.  
    <sub>names le lezard aux plumes d’or, joan miro, le lezard</sub>
  - **R** Midway through the initial print run, Miró and publisher Louis Broder abandoned the entire first edition because the inks chemically reacted with and stained the specially commissioned paper.  
    <sub>names louis broder, broder, louis</sub>
  - **X** Because the original lithographic stones and plates had already been effaced when the paper defect was discovered, the entire project had to be restarted from scratch.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Miró personally authored and calligraphed the accompanying Surrealist poem directly across the pages.  
    <sub>names miro</sub>
  - w The completed project took years of re-creation before finally being issued in 1971.  
    <sub>no entity of its own; snippet names le lezard aux plumes d’or</sub>


## credit_line 11.1 — *anchored* / capacity

> **Broder's decision to engage Miró was pivotal**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 decision engage`

8 results · kind **inert → inert** · R9 w2 X5

**1. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789 ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Joan Miró's Broder Collection: How One Artist Revolutionized Lithography**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...  
    <sub>names joan miro, broder, miro</sub>

**5. Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9)**  
`choicecontemporary.com` · tier `unverified`  
> Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9). Joan Miró. Regular price $7,480.00 USD. Lithograph in colors on B.F.K. Rives paper, watermarked.

  - **R** Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Regular price $7,480.00 USD.  
    <sub>about someone else (Regular), not this stop</sub>
  - **X** Lithograph in colors on B.F.K.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - **X** Rives paper, watermarked.  
    <sub>about someone else (Rives), not this stop</sub>

**6. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971 - Artsy**  
`artsy.net` · tier `market`  
> Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971. The complete set of 15 lithographs in colors, on Rives paper. 15 1/5 × 20 1/5 × ...

  - **R** Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - **X** The complete set of 15 lithographs in colors, on Rives paper.  
    <sub>about someone else (Rives), not this stop</sub>
  - w 15 1/5 × 20 1/5 × ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**7. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**8. Le lézard aux plumes d'or - Fundació Miró Mallorca**  
`miromallorca.com` · tier `unverified`  
> Author: Joan Miró; Title: Le lézard aux plumes d'or; Year: 1971; Technique: Litography; Dimensions: 39 x 106 cm; Classification: Graphic work ...

  - **R** Author: Joan Miró; Title: Le lézard aux plumes d'or; Year: 1971; Technique: Litography; Dimensions: 39 x 106 cm; Classification: Graphic work ...  
    <sub>names joan miro, le lezard, plumes</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Broder's decision to engage Miró was pivotal?`

kind **eventful → eventful** · R4 w1 X1

> Publisher Louis Broder originally commissioned Joan Miró to illustrate his own Surrealist poem under this title in 1967. 
> 
> After the entire initial print run was completed, Broder and Miró discovered manufacturing defects in the paper that had degraded the colors. 
> 
> Because of these flaws, they made the costly choice to scrap the project and destroy the printed sheets. 
> 
> The original stones had already been planed down or destroyed, making an identical reprint impossible. 
> 
> Broder chose to recommit to the ambitious project, requiring Miró to draft entirely new compositions for the eventual 1971 publication. 
> 
> This project ultimately marked the final collaboration between Broder and Miró before the publisher's death.

  - **R** Publisher Louis Broder originally commissioned Joan Miró to illustrate his own Surrealist poem under this title in 1967.  
    <sub>names louis broder, joan miro, broder</sub>
  - **R** After the entire initial print run was completed, Broder and Miró discovered manufacturing defects in the paper that had degraded the colors.  
    <sub>names broder, miro</sub>
  - **X** Because of these flaws, they made the costly choice to scrap the project and destroy the printed sheets.  
    <sub>about someone else (Because), not this stop</sub>
  - w The original stones had already been planed down or destroyed, making an identical reprint impossible.  
    <sub>no entity of its own; snippet names louis broder</sub>
  - **R** Broder chose to recommit to the ambitious project, requiring Miró to draft entirely new compositions for the eventual 1971 publication.  
    <sub>names broder, miro</sub>
  - **R** This project ultimately marked the final collaboration between Broder and Miró before the publisher's death.  
    <sub>names broder, miro</sub>


## credit_line 11.2 — *evaluative* / participial

> **blending visual and textual narratives seamlessly**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 blending visual`

8 results · kind **inert → inert** · R10 w0 X4

**1. Joan Miró. Plate (folio 12) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 12) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 12) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**2. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**3. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**4. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**5. Miró Joan | 15 WORKS: Le Lézard aux Plumes d'Or, Louis ...**  
`mutualart.com` · tier `market`  
> 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.

  - **R** 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.  
    <sub>names louis broder, le lezard, broder</sub>

**6. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**7. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**8. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, blending visual and textual narratives seamlessly?`

kind **inert → inert** · R4 w0 X3

> Joan Miró created *Le Lézard aux plumes d’or* based on a surrealist poem he wrote himself, integrating his own handwritten text with the imagery [PerQueryResult(index="1.2.2", source="Behind the Artist: Joan Miró - Park West Gallery"), PerQueryResult(index="1.2.5", source="Livre d'Artiste | The Tretyakov Gallery Magazine")]. 
> 
> Publisher Louis Broder initiated the project in the 1960s to explore the seamless dialogue between poetry and fine art [PerQueryResult(index="1.2.2", source="Behind the Artist: Joan Miró - Park West Gallery"), PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or. 1967. Set... - Lot 104 - Gazette Drouot")]. 
> 
> After the initial suite was fully printed in 1967, an unexpected flaw in the paper stock chemically altered and compromised the ink colors [PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or. 1967. Set... - Lot 104 - Gazette Drouot")]. 
> 
> Because the original printing plates had already been destroyed, Miró was forced to redraw the entire series from scratch, delaying the final publication until 1971 [PerQueryResult(index="1.2.1", source="Joan Miró - Le Lezard aux Plumes d'Or - National Galleries of Scotland"), PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or. 1967. Set... - Lot 104 - Gazette Drouot")].

  - **R** Joan Miró created *Le Lézard aux plumes d’or* based on a surrealist poem he wrote himself, integrating his own handwritten text with the imagery [PerQueryResult(index="1.2.2", source="Behind the Artist: Joan Miró - Park West Gallery"), PerQueryResult(index="1.2.5", source="Livre d'Artiste | The Tretyakov Gallery Magazine")].  
    <sub>names le lezard aux plumes d’or, joan miro, le lezard</sub>
  - **R** Publisher Louis Broder initiated the project in the 1960s to explore the seamless dialogue between poetry and fine art [PerQueryResult(index="1.2.2", source="Behind the Artist: Joan Miró - Park West Gallery"), PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - **X** - Lot 104 - Gazette Drouot")].  
    <sub>about someone else (Gazette Drouot), not this stop</sub>
  - **R** After the initial suite was fully printed in 1967, an unexpected flaw in the paper stock chemically altered and compromised the ink colors [PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or.  
    <sub>names le lezard, plumes, lezard</sub>
  - **X** - Lot 104 - Gazette Drouot")].  
    <sub>about someone else (Gazette Drouot), not this stop</sub>
  - **R** Because the original printing plates had already been destroyed, Miró was forced to redraw the entire series from scratch, delaying the final publication until 1971 [PerQueryResult(index="1.2.1", source="Joan Miró - Le Lezard aux Plumes d'Or - National Galleries of Scotland"), PerQueryResult(index="2.2.1", source="Miró, Joan Le Lézard aux plumes d'or.  
    <sub>names joan miro, le lezard, plumes</sub>
  - **X** - Lot 104 - Gazette Drouot")].  
    <sub>about someone else (Gazette Drouot), not this stop</sub>


## credit_line 12.1 — *anchored* / appositive

> **Boris Fridman, a supporter of the art community**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 supporter community`

8 results · kind **active → inert** · R10 w1 X8

**1. Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...  
    <sub>names joan miro, broder, miro</sub>

**4. Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9)**  
`choicecontemporary.com` · tier `unverified`  
> Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9). Joan Miró. Regular price $7,480.00 USD. Lithograph in colors on B.F.K. Rives paper, watermarked.

  - **R** Le lézard aux plumes d'or, 1971, Plate (Folios 8 verso and 9).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Regular price $7,480.00 USD.  
    <sub>about someone else (Regular), not this stop</sub>
  - **X** Lithograph in colors on B.F.K.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - **X** Rives paper, watermarked.  
    <sub>about someone else (Rives), not this stop</sub>

**5. Le lézard aux plumes d'or**  
`miromallorca.com` · tier `unverified`  
> Author: Joan Miró; Title: Le lézard aux plumes d'or; Year: 1971; Technique: Litography; Dimensions: 39 x 106 cm; Classification: Graphic work ...

  - **R** Author: Joan Miró; Title: Le lézard aux plumes d'or; Year: 1971; Technique: Litography; Dimensions: 39 x 106 cm; Classification: Graphic work ...  
    <sub>names joan miro, le lezard, plumes</sub>

**6. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**7. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**8. Joan Miró, 'Le Lézard aux Plumes d'Or (Mourlot 828)', 1971**  
`artsy.net` · tier `market`  
> Le Lézard aux Plumes d'Or (Mourlot 828), 1971. Lithograph printed in colours. 14 × 39 2/5 in | 35.5 × 100 cm. Forum Auctions: Prints & Editions (September 2021).

  - **R** Le Lézard aux Plumes d'Or (Mourlot 828), 1971.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **X** Lithograph printed in colours.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w 14 × 39 2/5 in | 35.5 × 100 cm.  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **X** Forum Auctions: Prints & Editions (September 2021).  
    <sub>about someone else (Forum Auctions), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Boris Fridman, a supporter of the art community?`

kind **eventful → eventful** · R4 w0 X0

> Miró created the illustrated book to accompany his own surrealist poetic text originally written in the late 1930s. 
> 
> Miró and publisher Louis Broder initially completed a first edition of lithographs in the 1960s, but they rejected and ordered the printed run destroyed after discovering a manufacturing defect in the paper that altered the colors. 
> 
> Because the original printing plates had already been erased, Miró was forced to redraw an entirely new set of compositions to complete the publication in 1971. 
> 
> The featured 1971 copy entered the collection of the Museum of Fine Arts, Boston as a gift from Boris Fridman, a prominent collector and promoter of *livres d'artistes*.

  - **R** Miró created the illustrated book to accompany his own surrealist poetic text originally written in the late 1930s.  
    <sub>names miro</sub>
  - **R** Miró and publisher Louis Broder initially completed a first edition of lithographs in the 1960s, but they rejected and ordered the printed run destroyed after discovering a manufacturing defect in the paper that altered the colors.  
    <sub>names louis broder, broder, louis</sub>
  - **R** Because the original printing plates had already been erased, Miró was forced to redraw an entirely new set of compositions to complete the publication in 1971.  
    <sub>names miro</sub>
  - **R** The featured 1971 copy entered the collection of the Museum of Fine Arts, Boston as a gift from Boris Fridman, a prominent collector and promoter of *livres d'artistes*.  
    <sub>names boris fridman, fridman, boris</sub>


## credit_line 12.2 — *anchored* / possessive

> **Boston's holdings**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 holdings`

2 results · kind **active → active** · R3 w0 X0

**1. Picasso, Miró, Dalí: Unbound**  
`mfa.org` · tier `tier1`  
> ... Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971 ...

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971 ...  
    <sub>names golden feathers, louis broder, the lizard</sub>

**2. 1850s Edo Era Abstract Japanese Katagami Stencil Art**  
`taurocertificadosmedicos.es` · tier `unverified`  
> Le Lézard aux Plumes d'Or - Original Lithograph by Joan Mirò - 1971 1971. US ... 1962 Orlando Pelayo Original Lithograph 2 Mourlot Freres. US$ 66-110. Min ...

  - **R** Le Lézard aux Plumes d'Or - Original Lithograph by Joan Mirò - 1971 1971.  
    <sub>names joan miro, le lezard, plumes</sub>
  - **R** 1962 Orlando Pelayo Original Lithograph 2 Mourlot Freres.  
    <sub>names mourlot</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Boston's holdings?`

kind **eventful → eventful** · R5 w0 X1

> Joan Miró created the book to illustrate his own poetic text, originally published in 1945 as *Jeux poétiques*. 
> 
> Miró and publisher Louis Broder originally printed a complete 18-plate edition in 1967. 
> 
> After printing, the collaborators discovered that chemical flaws in the manufactured paper were reacting with and degrading the colors. 
> 
> Because the original printing plates had already been erased, Broder and Miró chose to destroy the entire initial press run. 
> 
> Miró had to create a brand-new set of compositions from scratch, delaying publication until 1971. 
> 
> The featured copy was donated to the Museum of Fine Arts, Boston, by the prominent collector Boris Fridman.

  - **R** Joan Miró created the book to illustrate his own poetic text, originally published in 1945 as *Jeux poétiques*.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Miró and publisher Louis Broder originally printed a complete 18-plate edition in 1967.  
    <sub>names louis broder, broder, louis</sub>
  - **X** After printing, the collaborators discovered that chemical flaws in the manufactured paper were reacting with and degrading the colors.  
    <sub>about someone else (After), not this stop</sub>
  - **R** Because the original printing plates had already been erased, Broder and Miró chose to destroy the entire initial press run.  
    <sub>names broder, miro</sub>
  - **R** Miró had to create a brand-new set of compositions from scratch, delaying publication until 1971.  
    <sub>names miro</sub>
  - **R** The featured copy was donated to the Museum of Fine Arts, Boston, by the prominent collector Boris Fridman.  
    <sub>names boris fridman, fridman, boris</sub>


## credit_line 13.1 — *anchored* / possessive

> **Fridman's contribution ensures**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 contribution ensures`

8 results · kind **inert → inert** · R10 w2 X4

**1. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...

  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** From Joan Miró's “Broder Collection.” While Miró certainly drew inspiration from Surrealism, he ...  
    <sub>names joan miro, broder, miro</sub>

**5. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**6. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971. The complete set of 15 lithographs in colors, on Rives paper. 15 1/5 × 20 1/5 × ...

  - **R** Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - **X** The complete set of 15 lithographs in colors, on Rives paper.  
    <sub>about someone else (Rives), not this stop</sub>
  - w 15 1/5 × 20 1/5 × ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**7. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**8. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, Fridman's contribution ensures?`

kind **eventful → eventful** · R5 w0 X0

> Joan Miró wrote the surrealist poem underlying the book between 1936 and 1939, initially publishing the text in the magazine *Cahiers d'Art* in 1945. 
> 
> Miró originally created a full set of eighteen color lithographs for the project in 1967 with publisher Louis Broder. 
> 
> Due to a paper defect that altered the colors and damaged the printing surfaces, Miró and Broder abandoned the original run and destroyed most of the completed 1967 prints. 
> 
> Because the original plates and stones could not be reused, Miró had to completely redraw new compositions to bring the book to completion in 1971. 
> 
> The completed 1971 livre d'artiste entered the collection of the Museum of Fine Arts, Boston as a gift from collector Boris Fridman.

  - **R** Joan Miró wrote the surrealist poem underlying the book between 1936 and 1939, initially publishing the text in the magazine *Cahiers d'Art* in 1945.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Miró originally created a full set of eighteen color lithographs for the project in 1967 with publisher Louis Broder.  
    <sub>names louis broder, broder, louis</sub>
  - **R** Due to a paper defect that altered the colors and damaged the printing surfaces, Miró and Broder abandoned the original run and destroyed most of the completed 1967 prints.  
    <sub>names broder, miro</sub>
  - **R** Because the original plates and stones could not be reused, Miró had to completely redraw new compositions to bring the book to completion in 1971.  
    <sub>names miro</sub>
  - **R** The completed 1971 livre d'artiste entered the collection of the Museum of Fine Arts, Boston as a gift from collector Boris Fridman.  
    <sub>names boris fridman, fridman, boris</sub>


## credit_line 13.2 — *evaluative* / relative

> **visitors can appreciate the intricate dance between lithography**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 visitors appreciate`

8 results · kind **inert → inert** · R10 w2 X4

**1. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miro, Le lézard aux plumes d'or, Paris, Louis Broder, 1971 (M.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**4. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions - Fine_Art - Poster ...  
    <sub>names joan miro, le lezard, mourlot</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

**5. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971. The complete set of 15 lithographs in colors, on Rives paper. 15 1/5 × 20 1/5 × ...

  - **R** Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971.  
    <sub>names louis broder, joan miro, le lezard</sub>
  - **X** The complete set of 15 lithographs in colors, on Rives paper.  
    <sub>about someone else (Rives), not this stop</sub>
  - w 15 1/5 × 20 1/5 × ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**6. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**7. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**8. Miró Joan | 15 WORKS: Le Lézard aux Plumes d'Or, Louis ...**  
`mutualart.com` · tier `market`  
> 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.

  - **R** 15 WORKS: Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 · 6 Plates, from Le Lézard aux Plumes d'Or 6 , 1971 · 70 WORKS: Tristan Tzara, Parler Seul, A.  
    <sub>names louis broder, le lezard, broder</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, visitors can appreciate the intricate dance between lithography?`

kind **eventful → inert** · R4 w1 X1

> Joan Miró wrote the surrealist poem underlying this illustrated book between 1936 and 1939.
> 
> Publisher Louis Broder originally initiated the printing project with Miró in the 1960s to publish the portfolio in 1967.
> 
> After completing an initial run of 18 lithographs at Atelier Mourlot in 1967, Miró and Broder discovered a paper manufacturing defect that altered and distorted the inks' colors.
> 
> Because of this defect, the artist and publisher rejected the original print run and ordered the copies destroyed.
> 
> Since the original lithographic plates and stones had already been effaced, Miró had to recreate an entirely new series of lithographs from scratch.
> 
> This forced re-creation delayed the final publication of the book until 1971.

  - **R** Joan Miró wrote the surrealist poem underlying this illustrated book between 1936 and 1939.  
    <sub>names joan miro, miro, joan</sub>
  - **R** Publisher Louis Broder originally initiated the printing project with Miró in the 1960s to publish the portfolio in 1967.  
    <sub>names louis broder, broder, louis</sub>
  - **R** After completing an initial run of 18 lithographs at Atelier Mourlot in 1967, Miró and Broder discovered a paper manufacturing defect that altered and distorted the inks' colors.  
    <sub>names mourlot, broder, miro</sub>
  - **X** Because of this defect, the artist and publisher rejected the original print run and ordered the copies destroyed.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Since the original lithographic plates and stones had already been effaced, Miró had to recreate an entirely new series of lithographs from scratch.  
    <sub>names miro</sub>
  - w This forced re-creation delayed the final publication of the book until 1971.  
    <sub>no entity of its own; snippet names louis broder</sub>


## credit_line 13.3 — *evaluative* / participial

> **offering a unique tactile experience and inviting viewers to ponder the narrative beyond the page**

### SERPER — `"Le Lézard aux plumes d’or" Mourlot Broder Fridman why 1971 offering unique`

8 results · kind **active → inert** · R9 w2 X5

**1. Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions**  
`mourloteditions.com` · tier `unverified`  
> ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53. Mourlot 831. This version was pulled before lettering, (before the text was ...

  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53.  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>
  - w This version was pulled before lettering, (before the text was ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**4. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, joan miro</sub>

**5. Joan Miró's Broder Collection: How One Artist Revolutionized Lithography**  
`parkwestgallery.com` · tier `unverified`  
> The Broder Collection's vivid colors and obscure shapes align with Miró's unique ... “Le Lezard aux Plumes d'or II” (1971, M.828). From Joan ...

  - **R** The Broder Collection's vivid colors and obscure shapes align with Miró's unique ...  
    <sub>names broder, miro</sub>
  - **R** “Le Lezard aux Plumes d'or II” (1971, M.828).  
    <sub>names le lezard, lezard, plumes</sub>

**6. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant color ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, joan miro</sub>
  - **X** Bursting with vibrant color ...  
    <sub>about someone else (Bursting), not this stop</sub>

**7. Le Lézard aux Plumes d'Or (Mourlot 828) (1971) by Joan Miró | Artsy**  
`artsy.net` · tier `market`  
> Le Lézard aux Plumes d'Or (Mourlot 828), 1971. Lithograph printed in colours. 14 × 39 2/5 in | 35.5 × 100 cm. Forum Auctions: Prints & Editions (September 2021).

  - **R** Le Lézard aux Plumes d'Or (Mourlot 828), 1971.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **X** Lithograph printed in colours.  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w 14 × 39 2/5 in | 35.5 × 100 cm.  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **X** Forum Auctions: Prints & Editions (September 2021).  
    <sub>about someone else (Forum Auctions), not this stop</sub>

**8. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Le Lézard aux plumes d’or, offering a unique tactile experience and inviting viewers to ponder the narrative beyond the page?`

kind **inert → inert** · R3 w0 X1

> Joan Miró not only created the lithographs for *Le Lézard aux plumes d’or* but also authored the accompanying surrealist fantasy poem handwritten across the pages.
> 
> Originally intended for publication in 1967, the entire first print run was destroyed after a defect was discovered in the paper stock.
> 
> Because the original lithographic stones had already been effaced, Miró had to redraw every single composition from scratch to produce the final 1971 edition.
> 
> Miró turned intensely to printmaking and this project during a period of severe depression and pessimism surrounding Spain's political climate.

  - **R** Joan Miró not only created the lithographs for *Le Lézard aux plumes d’or* but also authored the accompanying surrealist fantasy poem handwritten across the pages.  
    <sub>names le lezard aux plumes d’or, joan miro, le lezard</sub>
  - **X** Originally intended for publication in 1967, the entire first print run was destroyed after a defect was discovered in the paper stock.  
    <sub>about someone else (Originally), not this stop</sub>
  - **R** Because the original lithographic stones had already been effaced, Miró had to redraw every single composition from scratch to produce the final 1971 edition.  
    <sub>names miro</sub>
  - **R** Miró turned intensely to printmaking and this project during a period of severe depression and pessimism surrounding Spain's political climate.  
    <sub>names miro</sub>


---

# Au Soleil du Plafond


## credit_line 2.1 — *anchored* / appositive

> **Pierre Reverdy, the French poet linked to Surrealism**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why linked`

8 results · kind **eventful → eventful** · R12 w0 X1

**1. Designed by Juan Gris - Au Soleil du Plafond**  
`metmuseum.org` · tier `tier1`  
> The project was taken up by Ténade some thirty years later, with the collaboration of the author (Reverdy). ... Au Soleil du Plafond; Designer: Designed by Juan ...

  - **R** The project was taken up by Ténade some thirty years later, with the collaboration of the author (Reverdy).  
    <sub>names reverdy</sub>
  - **R** Au Soleil du Plafond; Designer: Designed by Juan ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**2. AFTER JUAN GRIS (1887-1927), Au Soleil du Plafond**  
`onlineonly.christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...

  - **R** AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**3. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**4. Juan Gris, Compotier (kahnweiler 1969), Au Soleil Du ...**  
`etsy.com` · tier `unverified`  
> Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph. RHFineArtCo. 4 out of 5 stars. Returns & exchanges accepted.

  - **R** Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>
  - **X** Returns & exchanges accepted.  
    <sub>about someone else (Returns), not this stop</sub>

**5. Mary Ann Caws on Pierre Reverdy**  
`poetrysociety.org` · tier `unverified`  
> ... Gris is largely responsible for that label. In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond ...

  - **R** Gris is largely responsible for that label.  
    <sub>names gris</sub>
  - **R** In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**6. Gris, Juan | Benezit Dictionary of Artists**  
`oxfordartonline.com` · tier `unverified`  
> He provided illustrations for various published works including: in 1915, Pierre Reverdy's Au soleil du plafond (Tériade, Paris), Poèmes en Prose published by P ...

  - **R** He provided illustrations for various published works including: in 1915, Pierre Reverdy's Au soleil du plafond (Tériade, Paris), Poèmes en Prose published by P ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**7. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, gris, juan</sub>

**8. Compotier – henripeyrefi**  
`henripeyrefi.ws.gc.cuny.edu` · tier `tier1`  
> It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond. In this book ...

  - **R** It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, Pierre Reverdy, the French poet linked to Surrealism?`

kind **eventful → eventful** · R5 w0 X0

> The project was originally initiated around 1916–1917 by the art dealer and publisher Léonce Rosenberg as a direct collaboration pairing twenty poems by Pierre Reverdy with plates by Juan Gris. 
> 
> Production came to a sudden halt when Gris died of kidney failure in 1927 at age forty, leaving behind only eleven completed gouache illustrations. 
> 
> Publisher Tériade resurrected the stalled project nearly three decades later with Reverdy to publish the work posthumously. 
> 
> Reverdy reshaped the revived edition into a memorial tribute to his late friend, publishing the poems in a facsimile of his own handwriting alongside Gris's prints. 
> 
> The completed livre d’artiste was finally issued in 1955 after master lithographer Fernand Mourlot translated Gris's original gouaches into color lithographs.

  - **R** The project was originally initiated around 1916–1917 by the art dealer and publisher Léonce Rosenberg as a direct collaboration pairing twenty poems by Pierre Reverdy with plates by Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Production came to a sudden halt when Gris died of kidney failure in 1927 at age forty, leaving behind only eleven completed gouache illustrations.  
    <sub>names gris</sub>
  - **R** Publisher Tériade resurrected the stalled project nearly three decades later with Reverdy to publish the work posthumously.  
    <sub>names reverdy, teriade</sub>
  - **R** Reverdy reshaped the revived edition into a memorial tribute to his late friend, publishing the poems in a facsimile of his own handwriting alongside Gris's prints.  
    <sub>names reverdy, gris</sub>
  - **R** The completed livre d’artiste was finally issued in 1955 after master lithographer Fernand Mourlot translated Gris's original gouaches into color lithographs.  
    <sub>names gris</sub>


## credit_line 2.2 — *evaluative* / relative

> **revolutionized the concept of the book as art**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why revolutionized concept`

8 results · kind **inert → inert** · R11 w2 X1

**1. Living Still Life | John Golding**  
`nybooks.com` · tier `unverified`  
> ... Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later). These small ...

  - **R** Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**2. Coffee Grinder, Cup and Glass on a Table - Juan Gris**  
`artsdot.com` · tier `unverified`  
> ... Reverdy that truly ignited his artistic revolution. Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...

  - **R** Reverdy that truly ignited his artistic revolution.  
    <sub>names reverdy</sub>
  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**3. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Pierrots, Drawings, Books, etc Gris ...  
    <sub>names gris</sub>

**4. LES RECUEILS ILLUSTRÉS DE PIERRE REVERDY**  
`jstor.org` · tier `tier2`  
> by S Linarès · 2007 · Cited by 2 — Au soleil du plafond, 11 lithographies en couleurs d'apres des oeuvres de Juan Gris, texte de Pierre Reverdy manuscrit lithographie, [Paris], Teriade, 1955.

  - **R** by S Linarès · 2007 · Cited by 2 — Au soleil du plafond, 11 lithographies en couleurs d'apres des oeuvres de Juan Gris, texte de Pierre Reverdy manuscrit lithographie, [Paris], Teriade, 1955.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>

**5. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> At the turn of the 20th century, they revolutionized the book as an art form. ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on ...

  - w At the turn of the 20th century, they revolutionized the book as an art form.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**6. Objects Observed: The Poetry of Things in Twentieth ...**  
`dokumen.pub` · tier `unverified`  
> If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear. Let us look, ...

  - **R** If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**7. Coming Attractions: July 19 Through August 3 - What Will ...**  
`artsfuse.org` · tier `unverified`  
> ... Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy. Here, both text and ...

  - **R** Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>
  - **X** Here, both text and ...  
    <sub>about someone else (Here), not this stop</sub>

**8. 'Bibliotheque Litteraire Jacques Doucet, Paris, France' ...**  
`bridgemanimages.com` · tier `unverified`  
> ... Au soleil du plafond', by Pierre Reverdy (1889-1960) 1955 (colour litho) · Gris, Juan (1887-1927). CHT203701. Quick Preview. Add to the current lightbox. Remove ...

  - **R** Au soleil du plafond', by Pierre Reverdy (1889-1960) 1955 (colour litho) · Gris, Juan (1887-1927).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - w Add to the current lightbox.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, revolutionized the concept of the book as art?`

kind **eventful → eventful** · R4 w0 X0

> The project was originally commissioned around 1916–1917 by the art dealer Léonce Rosenberg as a collaborative work between poet Pierre Reverdy and painter Juan Gris.
> 
> The original plan stalled when Gris died prematurely of kidney failure in 1927 at age 40, having completed only 11 of the planned 20 gouache illustrations.
> 
> Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation to honor his late friend.
> 
> The volume was finally brought to completion and published in 1955 with Reverdy's handwritten poems and Gris's gouaches rendered as lithographs by the Mourlot Frères workshop.

  - **R** The project was originally commissioned around 1916–1917 by the art dealer Léonce Rosenberg as a collaborative work between poet Pierre Reverdy and painter Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The original plan stalled when Gris died prematurely of kidney failure in 1927 at age 40, having completed only 11 of the planned 20 gouache illustrations.  
    <sub>names gris</sub>
  - **R** Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation to honor his late friend.  
    <sub>names reverdy, teriade</sub>
  - **R** The volume was finally brought to completion and published in 1955 with Reverdy's handwritten poems and Gris's gouaches rendered as lithographs by the Mourlot Frères workshop.  
    <sub>names reverdy, gris</sub>


## credit_line 2.3 — *evaluative* / participial

> **exemplifying the collaborative spirit that defines the MFA's exhibition**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why exemplifying collaborative spirit defines`

8 results · kind **inert → inert** · R13 w1 X2

**1. (PDF) Textual Spaces: The Poetry of Pierre Reverdy - ResearchGate**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**2. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Pierrots, Drawings, Books, etc Gris ...  
    <sub>names gris</sub>

**3. Coming Attractions: July 19 Through August 3 - What Will Light Your Fire**  
`artsfuse.org` · tier `unverified`  
> ... Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy. Here, both text and ...

  - **R** Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>
  - **X** Here, both text and ...  
    <sub>about someone else (Here), not this stop</sub>

**4. [PDF] Objects Observed - The Poetry of Things in Twentieth - dokumen.pub**  
`dokumen.pub` · tier `unverified`  
> Au Soleil du plafond was originally to have been a collaborative effort, featuring still lifes by the major Cubist artist Juan Gris accompanying prose poems ...

  - **R** Au Soleil du plafond was originally to have been a collaborative effort, featuring still lifes by the major Cubist artist Juan Gris accompanying prose poems ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**5. Juan Gris, The Soup Tureen, from Au Soleil du Plafond, 1955 (after)**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled La Soupiere (The Soup Tureen), from the folio Au Soleil du Plafond (In the Sunlight of the ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled La Soupiere (The Soup Tureen), from the folio Au Soleil du Plafond (In the Sunlight of the ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**6. Pablo Picasso Exhibitions: Current, Upcoming & Past Shows - Mutual Art**  
`mutualart.com` · tier `market`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

**7. Deux Pôles de L'image Littéraire Au XXe Siècle - La Poésie Plastique ...**  
`scribd.com` · tier `unverified`  
> ... Au soleil du plafond. Jennifer Pap voque la gense de ce projet, dans un article trs document, Entre quatre murs: Reverdy, Cubism, and the space of the still ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Jennifer Pap voque la gense de ce projet, dans un article trs document, Entre quatre murs: Reverdy, Cubism, and the space of the still ...  
    <sub>names reverdy</sub>

**8. The cubism of Juan Gris. Vol I. Still lifes, landscapes - Academia.edu**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco The cubism of Juan Gris. Vol I. Still lifes, landscapes Gris and ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco The cubism of Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Still lifes, landscapes Gris and ...  
    <sub>names gris</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, exemplifying the collaborative spirit that defines the MFA's exhibition?`

kind **active → active** · R9 w0 X1

> Art dealer Léonce Rosenberg originally conceived the project around 1915 to display Pierre Reverdy's handwritten poems alongside gouaches by Juan Gris [PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol. 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu"), PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].
> 
> Rosenberg intended the work to appear on large wall panels, but the original project fell apart and was abandoned [PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].
> 
> Gris died in 1927 before the collaboration could ever be realized in print [PerQueryResult(index="1.1.6", source_title="Coming Attractions: July 19 Through August 3 - What Will Light Your Fire - The Arts Fuse"), PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol. 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu")].
> 
> Reverdy eventually reclaimed his texts and brought them to publisher Tériade to resurrect the project as a *livre d'artiste* [PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].
> 
> Because of Gris's early death, only eleven of Reverdy's twenty poems were accompanied by color lithographs after the painter's original gouaches [PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol. 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu"), PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].
> 
> The book was finally published in 1955, four decades after its inception [PerQueryResult(index="1.1.1", source_title="Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston"), PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol. 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu")].

  - **R** Art dealer Léonce Rosenberg originally conceived the project around 1915 to display Pierre Reverdy's handwritten poems alongside gouaches by Juan Gris [PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu"), PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].  
    <sub>names juan gris, gris, juan</sub>
  - **R** Rosenberg intended the work to appear on large wall panels, but the original project fell apart and was abandoned [PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].  
    <sub>names juan gris, gris, juan</sub>
  - **R** Gris died in 1927 before the collaboration could ever be realized in print [PerQueryResult(index="1.1.6", source_title="Coming Attractions: July 19 Through August 3 - What Will Light Your Fire - The Arts Fuse"), PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol.  
    <sub>names gris</sub>
  - **R** 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu")].  
    <sub>names juan gris, gris, juan</sub>
  - **R** Reverdy eventually reclaimed his texts and brought them to publisher Tériade to resurrect the project as a *livre d'artiste* [PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].  
    <sub>names juan gris, reverdy, teriade</sub>
  - **R** Because of Gris's early death, only eleven of Reverdy's twenty poems were accompanied by color lithographs after the painter's original gouaches [PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol.  
    <sub>names reverdy, gris</sub>
  - **R** 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu"), PerQueryResult(index="1.2.5", source_title="Juan Gris Art Value Price Guide - Invaluable.com")].  
    <sub>names juan gris, gris, juan</sub>
  - **X** The book was finally published in 1955, four decades after its inception [PerQueryResult(index="1.1.1", source_title="Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston"), PerQueryResult(index="1.2.4", source_title="The Orozco Collection Vol.  
    <sub>about someone else (PerQueryResult), not this stop</sub>
  - **R** 3 Juan Gris, Antoni Clavé, Manuel Ortiz de Zárate, Francisco Bores, Ortega, Redondela - Academia.edu")].  
    <sub>names juan gris, gris, juan</sub>


## credit_line 3.1 — *evaluative* / possessive

> **Gris's innovative vision**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why innovative vision`

8 results · kind **inert → inert** · R12 w1 X2

**1. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**2. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, gris, juan</sub>

**3. Juan Gris Sold at Auction Prices**  
`invaluable.com` · tier `market`  
> Juan Gris (1887 - 1927) PIERRE REVERDY (1889 - 1960) AU SOLEIL DU PLAFOND 22 litografie di Gris. Ed. Est: €6,000 - €7,000. View sold prices. Juan Gris (1887 ...

  - **R** Juan Gris (1887 - 1927) PIERRE REVERDY (1889 - 1960) AU SOLEIL DU PLAFOND 22 litografie di Gris.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>
  - w Est: €6,000 - €7,000.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**4. Pierre reverdy Stock Photos and Images**  
`alamy.com` · tier `unverified`  
> Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916. RM 3F4EGGY ... Gris collaborated with his friend, the poet Pierre Reverdy, on a ...

  - **R** Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>
  - **R** Gris collaborated with his friend, the poet Pierre Reverdy, on a ...  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**5. Picasso, Miró and Dalí reinvent the book as a work of art at ...**  
`bonart.cat` · tier `unverified`  
> The exhibition also includes lesser-known collaborations, such as Au Soleil du Plafond , conceived by Juan Gris with the French poet Pierre ...

  - **R** The exhibition also includes lesser-known collaborations, such as Au Soleil du Plafond , conceived by Juan Gris with the French poet Pierre ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**6. Juan Gris, Le Livre (kahnweiler 1969), Au Soleil Du ...**  
`etsy.com` · tier `unverified`  
> Juan Gris, Le Livre (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph. RHFineArtCo. 4 out of 5 stars. Returns & exchanges accepted.

  - **R** Juan Gris, Le Livre (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>
  - **X** Returns & exchanges accepted.  
    <sub>about someone else (Returns), not this stop</sub>

**7. Picasso, Miró, Dalí: Unbound**  
`mfa.org` · tier `tier1`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste ...  
    <sub>about someone else (Rarely), not this stop</sub>

**8. Living Still Life | John Golding**  
`nybooks.com` · tier `unverified`  
> Reverdy was two years younger than Gris and came to see Cubism through Gris's eyes ... Reverdy's Au Soleil du plafond (not published until much ...

  - **R** Reverdy was two years younger than Gris and came to see Cubism through Gris's eyes ...  
    <sub>names reverdy, gris</sub>
  - **R** Reverdy's Au Soleil du plafond (not published until much ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, Gris's innovative vision?`

kind **eventful → eventful** · R5 w0 X0

> * The project was originally conceived in 1916–1917 as a collaboration between Juan Gris and poet Pierre Reverdy, planned for publication by art dealer Léonce Rosenberg.
> * The original plan called for twenty gouache illustrations by Gris to match Reverdy's twenty poems.
> * Production halted when Gris died prematurely in 1927, having completed only eleven of the intended illustrations.
> * Publisher Tériade revived the abandoned project nearly three decades later with Reverdy to release it as a memorial tribute to Gris.
> * Reverdy had to completely redesign the format of the book to accommodate the missing illustrations before its eventual publication in 1955.

  - **R** * The project was originally conceived in 1916–1917 as a collaboration between Juan Gris and poet Pierre Reverdy, planned for publication by art dealer Léonce Rosenberg.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** * The original plan called for twenty gouache illustrations by Gris to match Reverdy's twenty poems.  
    <sub>names reverdy, gris</sub>
  - **R** * Production halted when Gris died prematurely in 1927, having completed only eleven of the intended illustrations.  
    <sub>names gris</sub>
  - **R** * Publisher Tériade revived the abandoned project nearly three decades later with Reverdy to release it as a memorial tribute to Gris.  
    <sub>names reverdy, teriade, gris</sub>
  - **R** * Reverdy had to completely redesign the format of the book to accommodate the missing illustrations before its eventual publication in 1955.  
    <sub>names reverdy</sub>


## credit_line 3.2 — *evaluative* / possessive

> **Reverdy's poetic prowess**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why poetic prowess`

4 results · kind **inert → inert** · R5 w0 X2

**1. Objects Observed - The Poetry of Things in Twentieth**  
`dokumen.pub` · tier `unverified`  
> If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear. Let us ...

  - **R** If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**2. (PDF) The cubism of Juan Gris. Vol I. Still lifes, landscapes**  
`academia.edu` · tier `tier1`  
> ... Reverdy's volume of poems, "Au Soleil du Plafond". Reverdy had been Gris' neighbour at 13, Place Ravignan in Montmartre before the War, he was then a young poet ...

  - **R** Reverdy's volume of poems, "Au Soleil du Plafond".  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** Reverdy had been Gris' neighbour at 13, Place Ravignan in Montmartre before the War, he was then a young poet ...  
    <sub>names reverdy, gris</sub>

**3. Efficacité/Efficacy**  
`brill.com` · tier `unverified`  
> morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La. Liberté des mers, 1960), en reproduction de manuscrit. Quant à Cocteau, il.

  - **R** morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>
  - **X** Liberté des mers, 1960), en reproduction de manuscrit.  
    <sub>about someone else (Liberté), not this stop</sub>

**4. Transnational Railway Cultures: Trains in Music, Literature ...**  
`dokumen.pub` · tier `unverified`  
> “Cubism and the Avant-Garde Prose-Poem: Figural Space in Pierre Reverdy's 'Au soleil du plafond.' ” French Studies 43, no 2: 302–19. Schivelbusch, Wolfgang ...

  - **R** “Cubism and the Avant-Garde Prose-Poem: Figural Space in Pierre Reverdy's 'Au soleil du plafond.' ” French Studies 43, no 2: 302–19.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Schivelbusch, Wolfgang ...  
    <sub>about someone else (Schivelbusch), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, Reverdy's poetic prowess?`

kind **eventful → eventful** · R4 w0 X1

> Art dealer Léonce Rosenberg originally conceived the project around 1916 or 1917 as a set of large rigid panels featuring Pierre Reverdy's handwritten poems paired with gouaches by Juan Gris. 
> 
> The publication stalled and Gris died prematurely in 1927 at age forty, leaving only eleven of the twenty planned illustrations completed. 
> 
> Following Rosenberg's death, Reverdy reclaimed his manuscripts and brought the unfinished project to art publisher Tériade. 
> 
> Because ten illustrations were missing, the creators had to fundamentally change the book's intended format. 
> 
> Tériade and printer Fernand Mourlot finally published the work in 1955, more than thirty years after its initial conception, as a tribute to Gris.

  - **R** Art dealer Léonce Rosenberg originally conceived the project around 1916 or 1917 as a set of large rigid panels featuring Pierre Reverdy's handwritten poems paired with gouaches by Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The publication stalled and Gris died prematurely in 1927 at age forty, leaving only eleven of the twenty planned illustrations completed.  
    <sub>names gris</sub>
  - **R** Following Rosenberg's death, Reverdy reclaimed his manuscripts and brought the unfinished project to art publisher Tériade.  
    <sub>names reverdy, teriade</sub>
  - **X** Because ten illustrations were missing, the creators had to fundamentally change the book's intended format.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Tériade and printer Fernand Mourlot finally published the work in 1955, more than thirty years after its initial conception, as a tribute to Gris.  
    <sub>names teriade, gris</sub>


## credit_line 3.3 — *evaluative* / participial

> **resulting in a unique interlacing of images and words**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why resulting unique interlacing images`

8 results · kind **eventful → eventful** · R14 w1 X2

**1. Designed by Juan Gris - Au Soleil du Plafond**  
`metmuseum.org` · tier `tier1`  
> Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)

  - **R** Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>

**2. Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, ...**  
`christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955 the complete set of 11 lithographs in colors, 1916-17, ...

  - **R** AFTER JUAN GRIS (1887-1927) Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955 the complete set of 11 lithographs in colors, 1916-17, ...  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>

**3. A double-page spread from the book Pierre Reverdy. Au ...**  
`tretyakovgallerymagazine.ru` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond. Miscellaneous. Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm. Magazine ...

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, gris, juan</sub>

**4. Gris and Reverdy's Au soleil du plafond**  
`araderbooks.com` · tier `unverified`  
> Au soleil du plafond was José Victoriano González-Pérez (pseud. Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...

  - **R** Au soleil du plafond was José Victoriano González-Pérez (pseud.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...  
    <sub>names juan gris, gris, juan</sub>

**5. Juan Gris, 'Pierre Reverdy. Au soleil du plafond Paris ...**  
`artsy.net` · tier `market`  
> Juan Gris. ,. Pierre Reverdy. Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery. Zürich ; High auction record. £34.8m, Christie's, 2014.

  - **R** Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **X** Zürich ; High auction record.  
    <sub>about someone else (Zürich), not this stop</sub>
  - **X** £34.8m, Christie's, 2014.  
    <sub>about someone else (Christie's), not this stop</sub>

**6. Au Soleil du Plafond - First Edition - Signed - Pierre Reverdy**  
`baumanrarebooks.com` · tier `unverified`  
> Au Soleil du Plafond rare book for sale. This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.

  - **R** Au Soleil du Plafond rare book for sale.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>

**7. Au soleil du plafond - Juan GRIS (Jose Victoriano ...**  
`musee-lam.fr` · tier `unverified`  
> ... GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY. Au soleil du plafond. 1955. Juan GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY. Au ...

  - **R** GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>

**8. (PDF) Textual Spaces: The Poetry of Pierre Reverdy**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, resulting in a unique interlacing of images and words?`

kind **eventful → eventful** · R4 w0 X1

> Art dealer Léonce Rosenberg originally planned the project around 1916–1917 as a collaboration where Juan Gris would produce twenty illustrations corresponding to twenty poems by Pierre Reverdy. 
> 
> Work on the book halted when Gris died prematurely in 1927 after completing only eleven gouaches. 
> 
> Nearly thirty years later, publisher Tériade revived the abandoned project in collaboration with Reverdy. 
> 
> Because almost half of the illustrations were missing, the creators had to fundamentally redesign the layout and presentation of the volume. 
> 
> Publisher Tériade finally released the completed work in 1955 through Éditions de la Revue Verve with lithographs printed by Mourlot Frères as a posthumous tribute to Gris.

  - **R** Art dealer Léonce Rosenberg originally planned the project around 1916–1917 as a collaboration where Juan Gris would produce twenty illustrations corresponding to twenty poems by Pierre Reverdy.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Work on the book halted when Gris died prematurely in 1927 after completing only eleven gouaches.  
    <sub>names gris</sub>
  - **R** Nearly thirty years later, publisher Tériade revived the abandoned project in collaboration with Reverdy.  
    <sub>names reverdy, teriade</sub>
  - **X** Because almost half of the illustrations were missing, the creators had to fundamentally redesign the layout and presentation of the volume.  
    <sub>about someone else (Because), not this stop</sub>
  - **R** Publisher Tériade finally released the completed work in 1955 through Éditions de la Revue Verve with lithographs printed by Mourlot Frères as a posthumous tribute to Gris.  
    <sub>names teriade, verve, gris</sub>


## credit_line 4.1 — *evaluative* / capacity

> **Gris's ability to transform visual art**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why ability transform visual`

8 results · kind **inert → inert** · R12 w1 X1

**1. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**2. Living Still Life | John Golding**  
`nybooks.com` · tier `unverified`  
> ... Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later). These small ...

  - **R** Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**3. Cubist Painting of Picasso, Braque, Gris and Léger**  
`thepersonalreview.blogspot.com` · tier `unverified`  
> ... Au Soleil du plafond using color lithographs of Gris' original works ... Viewers who actually read the Reverdy poem that accompanies Gris's ...

  - **R** Au Soleil du plafond using color lithographs of Gris' original works ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Viewers who actually read the Reverdy poem that accompanies Gris's ...  
    <sub>names reverdy, gris</sub>

**4. Coffee Grinder, Cup and Glass on a Table - Juan Gris**  
`artsdot.com` · tier `unverified`  
> ... Reverdy that truly ignited his artistic revolution. Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...

  - **R** Reverdy that truly ignited his artistic revolution.  
    <sub>names reverdy</sub>
  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**5. (PDF) Textual Spaces: The Poetry of Pierre Reverdy**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**6. Juan Gris, Guitar, from Au Soleil du Plafond, 1955 (after)**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled Guitare (Guitar), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled Guitare (Guitar), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**7. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Pierrots, Drawings, Books, etc Gris ...  
    <sub>names gris</sub>

**8. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, Gris's ability to transform visual art?`

kind **eventful → eventful** · R4 w0 X0

> The project was originally planned around 1916–1917 by the art dealer and publisher Léonce Rosenberg as a collaborative volume pairing twenty poems by Pierre Reverdy with plates by Juan Gris.
> 
> Production halted when Gris died prematurely of kidney failure in 1927, having completed only eleven of the intended illustrations.
> 
> Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation.
> 
> The book was finally published in 1955 by Tériade, printed by Mourlot Frères, with Reverdy dedicating the work as a posthumous tribute to Gris.

  - **R** The project was originally planned around 1916–1917 by the art dealer and publisher Léonce Rosenberg as a collaborative volume pairing twenty poems by Pierre Reverdy with plates by Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Production halted when Gris died prematurely of kidney failure in 1927, having completed only eleven of the intended illustrations.  
    <sub>names gris</sub>
  - **R** Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation.  
    <sub>names reverdy, teriade</sub>
  - **R** The book was finally published in 1955 by Tériade, printed by Mourlot Frères, with Reverdy dedicating the work as a posthumous tribute to Gris.  
    <sub>names reverdy, teriade, gris</sub>


## credit_line 4.2 — *evaluative* / capacity

> **Reverdy's capacity to infuse words with structural beauty**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why capacity infuse words structural`

7 results · kind **inert → inert** · R12 w0 X2

**1. Coffee Grinder, Cup and Glass on a Table — Juan Gris**  
`wahooart.com` · tier `unverified`  
> Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond ... This piece is a testament to Gris's ability to ... structural ...

  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** This piece is a testament to Gris's ability to ...  
    <sub>names gris</sub>

**2. Objects Observed: The Poetry of Things in Twentieth ...**  
`dokumen.pub` · tier `unverified`  
> If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear. Let us look, ...

  - **R** If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**3. (PDF) The cubism of Juan Gris. Vol I. Still lifes, landscapes**  
`academia.edu` · tier `tier1`  
> Reverdy, Au Soleil du Plafond, Paris, 1955 J. Thrall Soby, Juan Gris, Museum of Modern Art, New York, 1958 (illustrated p. 56) G. Tinterow, Juan Gris ...

  - **R** Reverdy, Au Soleil du Plafond, Paris, 1955 J.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** Thrall Soby, Juan Gris, Museum of Modern Art, New York, 1958 (illustrated p.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Tinterow, Juan Gris ...  
    <sub>names juan gris, gris, juan</sub>

**4. Efficacité/Efficacy**  
`brill.com` · tier `unverified`  
> morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La. Liberté des mers, 1960), en reproduction de manuscrit. Quant à Cocteau, il.

  - **R** morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>
  - **X** Liberté des mers, 1960), en reproduction de manuscrit.  
    <sub>about someone else (Liberté), not this stop</sub>

**5. Transnational Railway Cultures: Trains in Music, Literature ...**  
`dokumen.pub` · tier `unverified`  
> Both Nord-Sud and SIC advertised Reverdy's collection of poetry, reaffirming the link between the three works. ... Reverdy's 'Au soleil du plafond.' ” French ...

  - **R** Both Nord-Sud and SIC advertised Reverdy's collection of poetry, reaffirming the link between the three works.  
    <sub>names reverdy</sub>
  - **R** Reverdy's 'Au soleil du plafond.' ” French ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**6. Juan Gris, María Blanchard y los cubismos.pdf**  
`academia.edu` · tier `tier1`  
> ... Au Soleil du Plafond de Reverdy. Pero 22. Sobre las relaciones de Juan Gris con la luego, con inmediata posteridad a estas fechas, ni Gris ni Lipchitz ...

  - **R** Au Soleil du Plafond de Reverdy.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** Sobre las relaciones de Juan Gris con la luego, con inmediata posteridad a estas fechas, ni Gris ni Lipchitz ...  
    <sub>names juan gris, gris, juan</sub>

**7. The Yale Anthology of Twentieth-Century French Poetry**  
`epdf.pub` · tier `unverified`  
> ... Au soleil du plafond, 1955; La Liberté des mers, 1959; Sable mouvant, 1966. In the Fields or on the Hill No Historical ﬁgure And there the sun was coming ...

  - **R** Au soleil du plafond, 1955; La Liberté des mers, 1959; Sable mouvant, 1966.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **X** In the Fields or on the Hill No Historical ﬁgure And there the sun was coming ...  
    <sub>about someone else (Fields), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, Reverdy's capacity to infuse words with structural beauty?`

kind **eventful → eventful** · R6 w0 X0

> Art dealer Léonce Rosenberg originally planned the collaborative project between Pierre Reverdy and Juan Gris around 1916–1917. 
> 
> The initial intention was for Gris to provide a plate for each of Reverdy's twenty poems. 
> 
> Work came to a halt when Gris died prematurely in 1927 at age forty, having completed only eleven gouaches for the illustrations. 
> 
> Nearly thirty years later, the art publisher Tériade revived the abandoned project in collaboration with Reverdy. 
> 
> Fernand Mourlot’s atelier printed the volume in 1955, reproducing Gris’s gouaches as color lithographs alongside lithographs of Reverdy’s handwritten text. 
> 
> Reverdy included an introductory tribute to bring the delayed work to completion as a memorial to his late friend.

  - **R** Art dealer Léonce Rosenberg originally planned the collaborative project between Pierre Reverdy and Juan Gris around 1916–1917.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The initial intention was for Gris to provide a plate for each of Reverdy's twenty poems.  
    <sub>names reverdy, gris</sub>
  - **R** Work came to a halt when Gris died prematurely in 1927 at age forty, having completed only eleven gouaches for the illustrations.  
    <sub>names gris</sub>
  - **R** Nearly thirty years later, the art publisher Tériade revived the abandoned project in collaboration with Reverdy.  
    <sub>names reverdy, teriade</sub>
  - **R** Fernand Mourlot’s atelier printed the volume in 1955, reproducing Gris’s gouaches as color lithographs alongside lithographs of Reverdy’s handwritten text.  
    <sub>names reverdy, gris</sub>
  - **R** Reverdy included an introductory tribute to bring the delayed work to completion as a memorial to his late friend.  
    <sub>names reverdy</sub>


## credit_line 6.1 — *evaluative* / relative

> **rarely emerge from the archives**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why rarely emerge archives`

8 results · kind **inert → inert** · R10 w0 X4

**1. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**2. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Pierre Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc ...

  - **R** Pierre Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **X** Pierrots, Drawings, Books, etc ...  
    <sub>about someone else (Pierrots), not this stop</sub>

**3. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on ... Archives.” By documenting injustices, repression, and state violence ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Archives.” By documenting injustices, repression, and state violence ...  
    <sub>about someone else (Archives), not this stop</sub>

**4. Pierre Reverdy Chapter Summary**  
`bookey.app` · tier `unverified`  
> His collection, "Au Soleil du plafond," showcases this artistic partnership and includes poems inspired by Gris's still lifes. Reverdy himself ...

  - **R** His collection, "Au Soleil du plafond," showcases this artistic partnership and includes poems inspired by Gris's still lifes.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**5. Letter from Paris**  
`newyorker.com` · tier `tier2`  
> The volume has just been published, under the title “Au Soleil du Plafond ... According to Reverdy, in 1917 Gris and he conceived the idea of this doubly ...

  - **R** The volume has just been published, under the title “Au Soleil du Plafond ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** According to Reverdy, in 1917 Gris and he conceived the idea of this doubly ...  
    <sub>names reverdy, gris</sub>

**6. Objects Observed: The Poetry of Things in Twentieth ...**  
`dokumen.pub` · tier `unverified`  
> The complexity of Reverdy's engagement with the still life emerges again in the short collection of prose poems Au Soleil du plafond (At the Ceiling's Sun) ...

  - **R** The complexity of Reverdy's engagement with the still life emerges again in the short collection of prose poems Au Soleil du plafond (At the Ceiling's Sun) ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**7. Coming Attractions: July 19 Through August 3 - What Will ...**  
`artsfuse.org` · tier `unverified`  
> ... Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy. Here, both text and ...

  - **R** Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>
  - **X** Here, both text and ...  
    <sub>about someone else (Here), not this stop</sub>

**8. Joan Miró Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, rarely emerge from the archives?`

kind **eventful → eventful** · R5 w0 X1

> Art dealer Léonce Rosenberg originally planned the project around 1916–1917 with Juan Gris and Pierre Reverdy.
> 
> The initial plan called for illustrating each of Reverdy's twenty poems, but production was halted when Gris died of kidney failure in 1927 after finishing only eleven illustrations.
> 
> The project was revived roughly thirty years later by the art publisher Tériade, who reconceived the publication alongside Reverdy as a posthumous tribute to Gris.
> 
> Reverdy had originally written the accompanying texts decades earlier solely for personal resolution before they were finally paired with Gris's lithographs in the 1955 edition.
> 
> Master printer Fernand Mourlot produced the lithographs in Paris from Gris's original 1916–1917 gouaches.
> 
> The work at the Museum of Fine Arts, Boston was gifted to the museum by collectors Boris and Galina Fridman.

  - **R** Art dealer Léonce Rosenberg originally planned the project around 1916–1917 with Juan Gris and Pierre Reverdy.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The initial plan called for illustrating each of Reverdy's twenty poems, but production was halted when Gris died of kidney failure in 1927 after finishing only eleven illustrations.  
    <sub>names reverdy, gris</sub>
  - **R** The project was revived roughly thirty years later by the art publisher Tériade, who reconceived the publication alongside Reverdy as a posthumous tribute to Gris.  
    <sub>names reverdy, teriade, gris</sub>
  - **R** Reverdy had originally written the accompanying texts decades earlier solely for personal resolution before they were finally paired with Gris's lithographs in the 1955 edition.  
    <sub>names reverdy, gris</sub>
  - **R** Master printer Fernand Mourlot produced the lithographs in Paris from Gris's original 1916–1917 gouaches.  
    <sub>names gris</sub>
  - **X** The work at the Museum of Fine Arts, Boston was gifted to the museum by collectors Boris and Galina Fridman.  
    <sub>about someone else (Museum), not this stop</sub>


## credit_line 6.2 — *evaluative* / participial

> **offering a glimpse into the transformative collaborations of early-20th-century artists**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why offering glimpse transformative collaborations`

8 results · kind **inert → inert** · R11 w3 X2

**1. Transforming the Horizon: Reverdy's World War I**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris ... Poulet's comment offers a visual model with which to understand Reverdy's ... be seen as the frontispiece to ...

  - **R** Asp Au soleil du plafond et autres po?mes (Paris ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Poulet's comment offers a visual model with which to understand Reverdy's ...  
    <sub>names reverdy</sub>
  - w be seen as the frontispiece to ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**2. (PDF) Textual Spaces: The Poetry of Pierre Reverdy**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**3. Coming Attractions: July 19 Through August 3 - What Will ...**  
`artsfuse.org` · tier `unverified`  
> A glimpse of Kasandra ... Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy.

  - **X** A glimpse of Kasandra ...  
    <sub>about someone else (Kasandra), not this stop</sub>
  - **R** Au Soleil du Plafond (1955), the product of a close collaboration between Juan Gris and the poet Pierre Reverdy.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>

**4. (PDF) The cubism of Juan Gris. Vol I. Still lifes, landscapes**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco The cubism of Juan Gris. Vol I. Still lifes, landscapes Gris and ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco The cubism of Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Still lifes, landscapes Gris and ...  
    <sub>names gris</sub>

**5. Objects Observed: The Poetry of Things in Twentieth ...**  
`dokumen.pub` · tier `unverified`  
> If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear. Let us look, ...

  - **R** If we turn now to some prose poems from Au Soleil du plafond, the links between Reverdy's Cubist poetics and the paintings of Gris will be clear.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**6. Joan Miró Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

**7. # Un village, un homme : Pierre Reverdy à Solesmes ...**  
`facebook.com` · tier `reject`  
> Pierre Reverdy ( 1869-1960) Sable Mouvant Au soleil du plafond La liberté des mers (Poesie/Gallimard) 2003 Grâce au soutien du couturier-mécène Jacques ...

  - **R** Pierre Reverdy ( 1869-1960) Sable Mouvant Au soleil du plafond La liberté des mers (Poesie/Gallimard) 2003 Grâce au soutien du couturier-mécène Jacques ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**8. Pablo Picasso Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on ... Their generous bequest offers a rare glimpse into the vision of two ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - w Their generous bequest offers a rare glimpse into the vision of two ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, offering a glimpse into the transformative collaborations of early-20th-century artists?`

kind **eventful → eventful** · R4 w0 X0

> The livre d'artiste was originally commissioned around 1916 by art dealer Léonce Rosenberg to feature 20 poems by Pierre Reverdy alongside 20 corresponding gouache illustrations by Juan Gris.
> 
> The project was abruptly halted when Gris died in 1927 at age 40, having completed only 11 of the intended artworks.
> 
> Nearly thirty years later, publisher Tériade revived the abandoned collaboration alongside Reverdy.
> 
> Reverdy reconceived the book to finally bring their dialogue to print, dedicating the posthumous 1955 release as a tribute to his deceased friend.

  - **R** The livre d'artiste was originally commissioned around 1916 by art dealer Léonce Rosenberg to feature 20 poems by Pierre Reverdy alongside 20 corresponding gouache illustrations by Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The project was abruptly halted when Gris died in 1927 at age 40, having completed only 11 of the intended artworks.  
    <sub>names gris</sub>
  - **R** Nearly thirty years later, publisher Tériade revived the abandoned collaboration alongside Reverdy.  
    <sub>names reverdy, teriade</sub>
  - **R** Reverdy reconceived the book to finally bring their dialogue to print, dedicating the posthumous 1955 release as a tribute to his deceased friend.  
    <sub>names reverdy</sub>


## credit_line 7.1 — *evaluative* / relative

> **highlights how visual artists**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why highlights visual`

8 results · kind **inert → inert** · R15 w1 X1

**1. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, gris, juan</sub>

**2. Coffee Grinder, Cup and Glass on a Table — Juan Gris**  
`wahooart.com` · tier `unverified`  
> ... Reverdy that truly ignited his artistic revolution. Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...

  - **R** Reverdy that truly ignited his artistic revolution.  
    <sub>names reverdy</sub>
  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**3. Juan Gris, Le Livre (kahnweiler 1969), Au Soleil Du ...**  
`etsy.com` · tier `unverified`  
> May include: A cubist style abstract still life painting featuring a book, a glass ... May include: A vintage book cover with the title "Au soleil du plafond".

  - w May include: A cubist style abstract still life painting featuring a book, a glass ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** May include: A vintage book cover with the title "Au soleil du plafond".  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**4. Coffee Grinder, Cup and Glass on a Table - Juan Gris**  
`artsdot.com` · tier `unverified`  
> ... Reverdy that truly ignited his artistic revolution. Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...

  - **R** Reverdy that truly ignited his artistic revolution.  
    <sub>names reverdy</sub>
  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**5. Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston**  
`thehistoryofart.org` · tier `unverified`  
> Juan Gris and the French poet Pierre Reverdy's Au Soleil du Plafond from 1955 show another, where artist and writer work in closer harmony from the outset.

  - **R** Juan Gris and the French poet Pierre Reverdy's Au Soleil du Plafond from 1955 show another, where artist and writer work in closer harmony from the outset.  
    <sub>names au soleil du plafond, pierre reverdy, juan gris</sub>

**6. (PDF) Textual Spaces: The Poetry of Pierre Reverdy**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the ... visual puns as evidence of Reverdy's desire to ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** visual puns as evidence of Reverdy's desire to ...  
    <sub>names reverdy</sub>

**7. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Reverdy, Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris ...

  - **R** Reverdy, Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, gris, juan</sub>
  - **R** Pierrots, Drawings, Books, etc Gris ...  
    <sub>names gris</sub>

**8. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, highlights how visual artists?`

kind **active → active** · R5 w1 X0

> The project was originally planned around 1916–1917 by the art dealer Léonce Rosenberg to pair twenty poems by Pierre Reverdy with twenty accompanying illustrations by Juan Gris.
> 
> Gris was only able to complete eleven gouache designs before his early death in 1927 at the age of forty brought the collaboration to a halt.
> 
> Nearly thirty years later, publisher Tériade revived the stalled project in collaboration with Reverdy.
> 
> The missing illustrations forced the creators to fundamentally redesign the layout from its original intended format.
> 
> Master printer Fernand Mourlot translated Gris's surviving gouaches into lithographs for the final publication in 1955.
> 
> Reverdy authorized and signed the posthumous edition as a tribute to his deceased friend.

  - **R** The project was originally planned around 1916–1917 by the art dealer Léonce Rosenberg to pair twenty poems by Pierre Reverdy with twenty accompanying illustrations by Juan Gris.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Gris was only able to complete eleven gouache designs before his early death in 1927 at the age of forty brought the collaboration to a halt.  
    <sub>names gris</sub>
  - **R** Nearly thirty years later, publisher Tériade revived the stalled project in collaboration with Reverdy.  
    <sub>names reverdy, teriade</sub>
  - w The missing illustrations forced the creators to fundamentally redesign the layout from its original intended format.  
    <sub>no entity of its own; snippet names pierre reverdy</sub>
  - **R** Master printer Fernand Mourlot translated Gris's surviving gouaches into lithographs for the final publication in 1955.  
    <sub>names gris</sub>
  - **R** Reverdy authorized and signed the posthumous edition as a tribute to his deceased friend.  
    <sub>names reverdy</sub>


## credit_line 8.1 — *evaluative* / participial

> **inviting reflection on art as a shared divine expression**

### SERPER — `"Au Soleil du Plafond" Reverdy Gris why inviting reflection shared divine`

8 results · kind **active → active** · R12 w2 X3

**1. (PDF) Textual Spaces: The Poetry of Pierre Reverdy**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**2. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

**3. Objects Observed - The Poetry of Things in Twentieth**  
`dokumen.pub` · tier `unverified`  
> The complexity of Reverdy's engagement with the still life emerges again in the short collection of prose poems Au Soleil du plafond (At the. Ceiling's Sun) ...

  - **R** The complexity of Reverdy's engagement with the still life emerges again in the short collection of prose poems Au Soleil du plafond (At the.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**4. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> ... Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...

  - **R** Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Rarely on view, and resisting easy categorization, these livres d'artiste invite visitors ...  
    <sub>about someone else (Rarely), not this stop</sub>

**5. LE CORBUSIER Y EL POEMA DEL ÁNGULO RECTO**  
`upcommons.upc.edu` · tier `tier1`  
> by JM Rovira · Cited by 2 — ... Au Soleil du Plafond (illustrated by Gris). However, among the twenty-six livres de peintres Tériade published, such examples are rare.” Ver: ANTHO-. NIOZ ...

  - **X** by JM Rovira · Cited by 2 — ...  
    <sub>about someone else (Rovira), not this stop</sub>
  - **R** Au Soleil du Plafond (illustrated by Gris).  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** However, among the twenty-six livres de peintres Tériade published, such examples are rare.” Ver: ANTHO-.  
    <sub>names teriade</sub>

**6. (Word & Image Interactions 7) v. Ronique Plesch, Jan ...**  
`scribd.com` · tier `unverified`  
> morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La Liberté des mers, 1960), en reproduction de manuscrit. Quant à Cocteau, il

  - **R** morts, 1948), Juan Gris (Au soleil du plafond, 1955) et Georges Braque (La Liberté des mers, 1960), en reproduction de manuscrit.  
    <sub>names au soleil du plafond, juan gris, au soleil</sub>

**7. Salon International du Livre Rare et de l'Objet d'Art 2018**  
`calameo.com` · tier `unverified`  
> 06 80 47 25 69 hutinemmanuel@gmail.com REVERDY (Pierre). Au soleil du plafond. Paris, Tériade, 1955. In folio, en feuilles, couverture rempliée, chemise et ...

  - **R** 06 80 47 25 69 hutinemmanuel@gmail.com REVERDY (Pierre).  
    <sub>names reverdy, pierre</sub>
  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Paris, Tériade, 1955.  
    <sub>names teriade</sub>
  - w In folio, en feuilles, couverture rempliée, chemise et ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**8. Approche de l'adjectif gradable par sa polarité et son ...**  
`academia.edu` · tier `tier1`  
> Tout le monde est parti Pierre Reverdy, Au soleil du plafond et autres ... ] J'ai voulu des gris fer, des gris demi-deuil, des gris aluminium… […] Je n ...

  - **R** Tout le monde est parti Pierre Reverdy, Au soleil du plafond et autres ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **R** ] J'ai voulu des gris fer, des gris demi-deuil, des gris aluminium… […] Je n ...  
    <sub>names gris</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Au Soleil du Plafond, inviting reflection on art as a shared divine expression?`

kind **eventful → eventful** · R6 w0 X0

> The book was originally planned around 1916–1917 by art dealer and publisher Léonce Rosenberg as a joint venture between Juan Gris and poet Pierre Reverdy. 
> 
> The original plan called for Gris to create illustrations for twenty poems written by Reverdy. 
> 
> Production was halted when Gris died prematurely in 1927 at age forty, leaving behind only eleven completed gouaches. 
> 
> Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation. 
> 
> The completed work was published posthumously in 1955 as a tribute to Gris, featuring lithographs printed by Fernand Mourlot alongside Reverdy's handwritten texts. 
> 
> In his preface, Reverdy wrote that completing the work allowed him to reunite with his deceased friend through art that "defies the grave."

  - **R** The book was originally planned around 1916–1917 by art dealer and publisher Léonce Rosenberg as a joint venture between Juan Gris and poet Pierre Reverdy.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The original plan called for Gris to create illustrations for twenty poems written by Reverdy.  
    <sub>names reverdy, gris</sub>
  - **R** Production was halted when Gris died prematurely in 1927 at age forty, leaving behind only eleven completed gouaches.  
    <sub>names gris</sub>
  - **R** Publisher Tériade revived the abandoned project nearly three decades later with Reverdy's participation.  
    <sub>names reverdy, teriade</sub>
  - **R** The completed work was published posthumously in 1955 as a tribute to Gris, featuring lithographs printed by Fernand Mourlot alongside Reverdy's handwritten texts.  
    <sub>names reverdy, gris</sub>
  - **R** In his preface, Reverdy wrote that completing the work allowed him to reunite with his deceased friend through art that "defies the grave."  
    <sub>names reverdy</sub>


---

# Moses and Monotheism


## credit_line 1.1 — *anchored* / possessive

> **Dalí's vivid illustrations**

### SERPER — `"Moses and Monotheism" Freud Dalí why vivid illustrations`

8 results · kind **inert → inert** · R14 w2 X1

**1. Freud had a lifelong fascination for the figure of Moses ...**  
`facebook.com` · tier `reject`  
> One of the many Jewish that impacted the world through knowledge was Sigmund Freud. I read his book, " Moses and Monotheism ". He believed Moses ...

  - **R** One of the many Jewish that impacted the world through knowledge was Sigmund Freud.  
    <sub>names sigmund freud, sigmund, freud</sub>
  - **R** I read his book, " Moses and Monotheism ".  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** He believed Moses ...  
    <sub>names moses</sub>

**2. New London Exhibition 'Freud's Antiquity' Unveils ...**  
`uh.edu` · tier `tier1`  
> ... Moses and Monotheism.” “Freud created the 'archaeological metaphor' to show how the mind resembles an archaeological site which the analyst ...

  - **R** Moses and Monotheism.” “Freud created the 'archaeological metaphor' to show how the mind resembles an archaeological site which the analyst ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**3. Salvador Dalí Moses and Monotheism, 1979**  
`1stdibs.com` · tier `market`  
> This artwork titled, "Moses and Monotheism" 1979, is a copper embossed bas relief by artist Salvador Dali, 1904-1989. It is hand signed in felt pen at the ...

  - **R** This artwork titled, "Moses and Monotheism" 1979, is a copper embossed bas relief by artist Salvador Dali, 1904-1989.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - w It is hand signed in felt pen at the ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**4. Freuds Last Session**  
`exhibits.wilson.edu` · tier `tier1`  
> cancer, and wrote his most provocative book, Moses and Monotheism . 9de6d6e4c5. Taking us on a journey through the `site-responsive' artworks, exhibitions ...

  - **R** cancer, and wrote his most provocative book, Moses and Monotheism .  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Taking us on a journey through the `site-responsive' artworks, exhibitions ...  
    <sub>about someone else (Taking), not this stop</sub>

**5. FINE ARTS EXHIBITION: Salvador Dalí – Recettes d' ...**  
`gml.si` · tier `unverified`  
> Texts from Freud's Moses and Monotheism (1939) accompany the artwork. The selection of its content came from Dalí's universal interest in Freud ...

  - **R** Texts from Freud's Moses and Monotheism (1939) accompany the artwork.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** The selection of its content came from Dalí's universal interest in Freud ...  
    <sub>names freud, dali</sub>

**6. Dalí's Religious Models: the Iconography of Martyrdom and ...**  
`academia.edu` · tier `tier1`  
> Dalí was reading Freud, but not yet painting him. We should also give some ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** Dalí was reading Freud, but not yet painting him.  
    <sub>names freud, dali</sub>
  - w We should also give some ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**7. DALÍ A HISTORY OF PAINTING 6 July to 8 September 2019**  
`grimaldiforum.com` · tier `unverified`  
> He writes the preface to and illustrates Sigmund Freud's book, Moses and Monotheism. On. 28 September, the Dalí Theatre-Museum is inaugurated. 1977. The ...

  - **R** He writes the preface to and illustrates Sigmund Freud's book, Moses and Monotheism.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** 28 September, the Dalí Theatre-Museum is inaugurated.  
    <sub>names dali</sub>

**8. Final Analysis**  
`chicagoreader.com` · tier `unverified`  
> ... Moses and Monotheism, that the Hebrew lawgiver was actually an ... David Gropman's set re-creates Freud's study in vivid detail, from ...

  - **R** Moses and Monotheism, that the Hebrew lawgiver was actually an ...  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** David Gropman's set re-creates Freud's study in vivid detail, from ...  
    <sub>names freud</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, Dalí's vivid illustrations?`

kind **active → active** · R3 w1 X1

> * Salvador Dalí idolized Sigmund Freud as an intellectual father figure, having met him in London in 1938 just before Freud’s death.
> * Dalí created this portfolio in 1974 to illustrate the French edition of Freud’s controversial final 1939 book, which argued that Moses was an Egyptian noble rather than Hebrew.
> * The Paris publisher Art et Valeur issued the work in a limited edition of 300 copies.
> * Dalí drew the illustrations with a diamond stylus directly onto massive gold printing plates, printing the images on soft lambskin and sheepskin.
> * The publisher faced material challenges because the sheepskin reacts to humidity by shrinking and curling, making the loose sheets prone to slipping out from beneath frame matting.

  - **R** * Salvador Dalí idolized Sigmund Freud as an intellectual father figure, having met him in London in 1938 just before Freud’s death.  
    <sub>names sigmund freud, salvador dali, salvador</sub>
  - **R** * Dalí created this portfolio in 1974 to illustrate the French edition of Freud’s controversial final 1939 book, which argued that Moses was an Egyptian noble rather than Hebrew.  
    <sub>names moses, freud, dali</sub>
  - **X** * The Paris publisher Art et Valeur issued the work in a limited edition of 300 copies.  
    <sub>about someone else (The Paris), not this stop</sub>
  - **R** * Dalí drew the illustrations with a diamond stylus directly onto massive gold printing plates, printing the images on soft lambskin and sheepskin.  
    <sub>names dali</sub>
  - w * The publisher faced material challenges because the sheepskin reacts to humidity by shrinking and curling, making the loose sheets prone to slipping out from beneath frame matting.  
    <sub>no entity of its own; snippet names sigmund freud</sub>


## credit_line 2.1 — *anchored* / relative

> **breathe life into Freud’s narrative become evident**

### SERPER — `"Moses and Monotheism" Freud Dalí why breathe narrative become evident`

8 results · kind **active → active** · R15 w2 X0

**1. What is Freud's psychoanalytic theory on the survival of Jewish ...**  
`facebook.com` · tier `reject`  
> In his work "Moses and Monotheism," he used his ideas of the Oedipal Complex to create a larger portrait of western religion. Mosaic monotheism, ...

  - **R** In his work "Moses and Monotheism," he used his ideas of the Oedipal Complex to create a larger portrait of western religion.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Mosaic monotheism, ...  
    <sub>names monotheism</sub>

**2. Freud at Shalem | A discussion space for students of "Introduction to ...**  
`freudatshalem.wordpress.com` · tier `unverified`  
> ... Moses and Monotheism, or in his letter to his fiancé in which he says he is neither European nor Austrian but rather a Jew). In the space between Freud's ...

  - **R** Moses and Monotheism, or in his letter to his fiancé in which he says he is neither European nor Austrian but rather a Jew).  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** In the space between Freud's ...  
    <sub>names freud</sub>

**3. (PDF) Dalí's Religious Models: the Iconography of Martyrdom and its ...**  
`academia.edu` · tier `tier1`  
> It was around that time that Dalí became aware of Freud's essay 'The Uncanny ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** It was around that time that Dalí became aware of Freud's essay 'The Uncanny ...  
    <sub>names freud, dali</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**4. [EPUB] The Escape of Sigmund Freud - dokumen.pub**  
`dokumen.pub` · tier `unverified`  
> There Freud was right and well ahead of specialist scholars. Freud published Moses and Monotheism in Amsterdam. It was, as he expected, very controversial ...

  - **R** There Freud was right and well ahead of specialist scholars.  
    <sub>names freud</sub>
  - **R** Freud published Moses and Monotheism in Amsterdam.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w It was, as he expected, very controversial ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**5. (PDF) Freud's Foes: Psychoanalysis, Science and Resistance**  
`researchgate.net` · tier `unverified`  
> Freud, The Future of an Illusion, p. 160. 116. Freud, The Future of an Illusion, p. 175. 117. Freud, “Moses and Monotheism,” SE, 23:66. 118. See Paul ...

  - **R** Freud, The Future of an Illusion, p.  
    <sub>names freud</sub>
  - **R** Freud, The Future of an Illusion, p.  
    <sub>names freud</sub>
  - **R** Freud, “Moses and Monotheism,” SE, 23:66.  
    <sub>names moses and monotheism, monotheism, freud</sub>

**6. Kindred by Chance: Spontaneous Art and Neoliberal Order - eScholarship**  
`escholarship.org` · tier `unverified`  
> ... Freud's last book, Moses and Monotheism (1939), which traces the origin of ... narrative would seem a fitting intellectual afterimage of the death of ...

  - **R** Freud's last book, Moses and Monotheism (1939), which traces the origin of ...  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w narrative would seem a fitting intellectual afterimage of the death of ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**7. Sigmund Freud is pictured on the menu of his favourite coffee house ...**  
`instagram.com` · tier `reject`  
> It was here that Sigmund Freud started work on his book 'Moses and Monotheism' (1939) and this was his last summer residence before exile in ...

  - **R** It was here that Sigmund Freud started work on his book 'Moses and Monotheism' (1939) and this was his last summer residence before exile in ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**8. Dynamic Theories of Personality, Classical, Post-Modern, and Person ...**  
`link.springer.com` · tier `unverified`  
> Freud, S. (1937). Moses and Monotheism. In F. Sigmund (Ed.), The standard edition of the complete psychological works of Sigmund Freud. London: Hogarth ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Sigmund (Ed.), The standard edition of the complete psychological works of Sigmund Freud.  
    <sub>names sigmund freud, sigmund, freud</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, breathe life into Freud’s narrative become evident?`

kind **active → active** · R3 w2 X0

> Salvador Dalí created this suite of illustrations in 1974 to reinterpret Sigmund Freud's controversial 1939 final book.
> 
> Dalí undertook the project as a direct engagement with Freudian psychoanalytic theory, which had profoundly influenced his surrealist method throughout his career.
> 
> Rather than a direct real-time collaboration with Freud, who died in 1939, the portfolio was conceived decades later as an artist's book (*livre d'artiste*) exploring Freud's thesis that Moses was an Egyptian noble.
> 
> The work was produced in a loose-leaf format printed on sheepskin and silk using pressed etchings and lithography.
> 
> The portfolio was originally issued in two large acrylic folios housed inside a velvet-lined case featuring a bas-relief metal front cover.

  - **R** Salvador Dalí created this suite of illustrations in 1974 to reinterpret Sigmund Freud's controversial 1939 final book.  
    <sub>names sigmund freud, salvador dali, salvador</sub>
  - **R** Dalí undertook the project as a direct engagement with Freudian psychoanalytic theory, which had profoundly influenced his surrealist method throughout his career.  
    <sub>names freud, dali</sub>
  - **R** Rather than a direct real-time collaboration with Freud, who died in 1939, the portfolio was conceived decades later as an artist's book (*livre d'artiste*) exploring Freud's thesis that Moses was an Egyptian noble.  
    <sub>names moses, freud</sub>
  - w The work was produced in a loose-leaf format printed on sheepskin and silk using pressed etchings and lithography.  
    <sub>no entity of its own; snippet names sigmund freud</sub>
  - w The portfolio was originally issued in two large acrylic folios housed inside a velvet-lined case featuring a bas-relief metal front cover.  
    <sub>no entity of its own; snippet names sigmund freud</sub>


## credit_line 3.1 — *evaluative* / participial

> **infusing it with his characteristic surrealism**

### SERPER — `"Moses and Monotheism" Freud Dalí why infusing characteristic`

8 results · kind **active → active** · R12 w1 X4

**1. //...Frida Kahlo...// (Mexican, 1907-1954) Moses, 1945. Oil on ...**  
`facebook.com` · tier `reject`  
> Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.

  - **R** Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**2. Sigmund Freud was an avid collector of figurines - Facebook**  
`facebook.com` · tier `reject`  
> This point is not incidental because for Freud, in Moses and Monotheism ... Freud inspired us with his personality, character and ideas, and his ...

  - **R** This point is not incidental because for Freud, in Moses and Monotheism ...  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** Freud inspired us with his personality, character and ideas, and his ...  
    <sub>names freud</sub>

**3. (PDF) Dalí's Religious Models: the Iconography of Martyrdom and its ...**  
`academia.edu` · tier `tier1`  
> Dalí welcomed Freud's scientific theories of the forces at work within a ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** Dalí welcomed Freud's scientific theories of the forces at work within a ...  
    <sub>names freud, dali</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**4. Frankenstein, Spellbound, and World War Z: Evolving concepts of the ...**  
`doi.apa.org` · tier `unverified`  
> Freud, S. (1964). Moses and monotheism: Three essays. In J. Strachey (Ed. & Trans.), The standard edition of the complete psychological works of Sigmund Freud ( ...

  - **R** Moses and monotheism: Three essays.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** & Trans.), The standard edition of the complete psychological works of Sigmund Freud ( ...  
    <sub>names sigmund freud, sigmund, freud</sub>

**5. Shabbat Reading List - Jewish Currents**  
`jewishcurrents.org` · tier `unverified`  
> ... Freud's own final completed work, Moses and Monotheism (1939). In this puzzling and provocative text, Said explains, the founder of psychoanalysis indulges ...

  - **R** Freud's own final completed work, Moses and Monotheism (1939).  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **X** In this puzzling and provocative text, Said explains, the founder of psychoanalysis indulges ...  
    <sub>about someone else (Said), not this stop</sub>

**6. Kindred by Chance: Spontaneous Art and Neoliberal Order - eScholarship**  
`escholarship.org` · tier `unverified`  
> ... Freud's last book, Moses and Monotheism (1939), which traces the origin of ... characteristic is the vertical “[d]evelopment of forms and the formation ...

  - **R** Freud's last book, Moses and Monotheism (1939), which traces the origin of ...  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w characteristic is the vertical “[d]evelopment of forms and the formation ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**7. AFTERLIFE - Cambridge University Press & Assessment**  
`cambridge.org` · tier `unverified`  
> Freud, S. (1964). Moses and Monotheism, trans. K. Jones, in The Standard. Edition of the Complete Psychological Works of Sigmund Freud, Vol. XXIII (1937–1939) ...

  - **R** Moses and Monotheism, trans.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Jones, in The Standard.  
    <sub>about someone else (Jones), not this stop</sub>
  - **R** Edition of the Complete Psychological Works of Sigmund Freud, Vol.  
    <sub>names sigmund freud, sigmund, freud</sub>
  - **X** XXIII (1937–1939) ...  
    <sub>about someone else (XXIII), not this stop</sub>

**8. [PDF] Idol fantasies: toward an ethics of image-making in Wilde, Conrad ...**  
`open.bu.edu` · tier `tier1`  
> 104 Sigmund Freud, Moses and Monotheism, trans. Katherine Jones, with the assistance of James Strachey and Wilfred Trotter (New York: Vintage, 1939), 144 ...

  - **R** 104 Sigmund Freud, Moses and Monotheism, trans.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** Katherine Jones, with the assistance of James Strachey and Wilfred Trotter (New York: Vintage, 1939), 144 ...  
    <sub>about someone else (Katherine Jones), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, infusing it with his characteristic surrealism?`

kind **active → active** · R3 w0 X1

> Salvador Dalí created his illustrations for *Moses and Monotheism* in 1974 as a visual interpretation of Sigmund Freud's final 1939 book. 
> 
> The project served as a late artistic tribute to Freud, whom Dalí had deeply idolized and met in London in 1938. 
> 
> The portfolio was commissioned and published in Paris in 1975 by Éditions Art et Valeur in a limited edition of 250 copies. 
> 
> Dalí chose unusual, tactile materials for the edition, executing the mixed-media lithographs and etchings on sheepskin.

  - **R** Salvador Dalí created his illustrations for *Moses and Monotheism* in 1974 as a visual interpretation of Sigmund Freud's final 1939 book.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>
  - **R** The project served as a late artistic tribute to Freud, whom Dalí had deeply idolized and met in London in 1938.  
    <sub>names freud, dali</sub>
  - **X** The portfolio was commissioned and published in Paris in 1975 by Éditions Art et Valeur in a limited edition of 250 copies.  
    <sub>about someone else (Paris), not this stop</sub>
  - **R** Dalí chose unusual, tactile materials for the edition, executing the mixed-media lithographs and etchings on sheepskin.  
    <sub>names dali</sub>


## credit_line 4.1 — *anchored* / possessive

> **Freud's exploration of**

### SERPER — `"Moses and Monotheism" Freud Dalí why exploration`

8 results · kind **inert → inert** · R13 w0 X1

**1. Illustrations and printed text of Sigmund Freud's Moses and ...**  
`collections.museumofthebible.org` · tier `unverified`  
> This oversize French edition of Sigmund Freud's 1939 published work, Moses and Monotheism, contains illustrations based on watercolor, pen-and-ink drawings, ...

  - **R** This oversize French edition of Sigmund Freud's 1939 published work, Moses and Monotheism, contains illustrations based on watercolor, pen-and-ink drawings, ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**2. Sigmund Freud - Salvador Dalí Museum**  
`thedali.org` · tier `unverified`  
> Freud, Sigmund. Moses and Monotheism. Vintage Books, 1967. This volume reflects Freud's commentaries on various aspects of religion, specifically his ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** This volume reflects Freud's commentaries on various aspects of religion, specifically his ...  
    <sub>names freud</sub>

**3. Freud had a lifelong fascination for the figure of Moses, from ... - Facebook**  
`facebook.com` · tier `reject`  
> One of the many Jewish that impacted the world through knowledge was Sigmund Freud. I read his book, " Moses and Monotheism ". He believed Moses ...

  - **R** One of the many Jewish that impacted the world through knowledge was Sigmund Freud.  
    <sub>names sigmund freud, sigmund, freud</sub>
  - **R** I read his book, " Moses and Monotheism ".  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** He believed Moses ...  
    <sub>names moses</sub>

**4. Moses and Monotheism - VKS ART**  
`vksart.com` · tier `unverified`  
> In Moses and Monotheism Freud applies his psychoanalytic theory not to a person but to an event in history. He contradicts the biblical story of Moses, ...

  - **R** In Moses and Monotheism Freud applies his psychoanalytic theory not to a person but to an event in history.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** He contradicts the biblical story of Moses, ...  
    <sub>names moses</sub>

**5. Salvador Dali Meets Sigmund Freud: Paranoia, Narcissism, Snails**  
`escipub.com` · tier `unverified`  
> Moses and monotheism: three essays. Standard Edition, 1939[1934-38]; 23 ... ...

  - **R** Moses and monotheism: three essays.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Standard Edition, 1939[1934-38]; 23 ...  
    <sub>about someone else (Standard Edition), not this stop</sub>

**6. Beware the Boa Constructor! Freud, Modern Art and the Riddle of ...**  
`88invisiblemirrors.blog` · tier `unverified`  
> If taken sequentially from his earliest work On Aphasia (1891) to Moses and Monotheism (1939), the story of psychoanalysis can be read as an ...

  - **R** If taken sequentially from his earliest work On Aphasia (1891) to Moses and Monotheism (1939), the story of psychoanalysis can be read as an ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**7. Did you catch our incredible exhibition 'Freud, Dali and the ...**  
`instagram.com` · tier `reject`  
> ... Moses and Monotheism'. Our latest afternoon session explores Freud's fascination with Moses through the years, included with your Museum admission. 24 ...

  - **R** Moses and Monotheism'.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Our latest afternoon session explores Freud's fascination with Moses through the years, included with your Museum admission.  
    <sub>names moses, freud</sub>

**8. Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism; others ...

  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism; others ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, Freud's exploration of?`

kind **inert → inert** · R3 w0 X2

> Salvador Dalí revered Sigmund Freud's final 1939 book, writing in his diary that Freud had performed his most difficult and bitter task by arguing that Moses was Egyptian.
> 
> The luxury *livre d'artiste* edition was published in Paris by Art et Valeur in the mid-1970s with a limited print run.
> 
> Dalí created the ten portfolio illustrations by engraving directly onto massive gold plates with a diamond stylus before printing them onto lambskin and sheepskin.
> 
> Printers and conservators found sheepskin uniquely challenging because its sensitivity to humidity causes it to shrink, warp, and slip out of standard framing mats.
> 
> The resulting suite was issued unbound in loose-leaf sheets, protected inside Plexiglas folders and a custom velvet-lined box adorned with a sculpted bas-relief cover of Moses.

  - **R** Salvador Dalí revered Sigmund Freud's final 1939 book, writing in his diary that Freud had performed his most difficult and bitter task by arguing that Moses was Egyptian.  
    <sub>names sigmund freud, salvador dali, salvador</sub>
  - **X** The luxury *livre d'artiste* edition was published in Paris by Art et Valeur in the mid-1970s with a limited print run.  
    <sub>about someone else (Paris), not this stop</sub>
  - **R** Dalí created the ten portfolio illustrations by engraving directly onto massive gold plates with a diamond stylus before printing them onto lambskin and sheepskin.  
    <sub>names dali</sub>
  - **X** Printers and conservators found sheepskin uniquely challenging because its sensitivity to humidity causes it to shrink, warp, and slip out of standard framing mats.  
    <sub>about someone else (Printers), not this stop</sub>
  - **R** The resulting suite was issued unbound in loose-leaf sheets, protected inside Plexiglas folders and a custom velvet-lined box adorned with a sculpted bas-relief cover of Moses.  
    <sub>names moses</sub>


## credit_line 4.2 — *evaluative* / participial

> **visualizing the psychological and spiritual transition from polytheistic beliefs**

### SERPER — `"Moses and Monotheism" Freud Dalí why visualizing psychological spiritual transition`

8 results · kind **active → active** · R11 w2 X2

**1. Beethoven and Psychoanalysis** # ***(Freud · Jung · Lacan) - Facebook**  
`facebook.com` · tier `reject`  
> ... Moses and Monotheism" (1939), reflecting his relentless intellectual spirit. His extensive writings forged connections across psychology ...

  - **R** Moses and Monotheism" (1939), reflecting his relentless intellectual spirit.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - w His extensive writings forged connections across psychology ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**2. “The Audacity Cannot Be Avoided” (Chapter 3) - The Late Sigmund Freud**  
`cambridge.org` · tier `unverified`  
> Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial. It is the culmination of his thinking about religion and ...

  - **R** Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w It is the culmination of his thinking about religion and ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**3. (PDF) Dalí's Religious Models: the Iconography of Martyrdom and its ...**  
`academia.edu` · tier `tier1`  
> Freud was beginning to shape Dalí's thoughts on the psychological condition ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** Freud was beginning to shape Dalí's thoughts on the psychological condition ...  
    <sub>names freud, dali</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**4. [PDF] © 2019 Charles Emerson Riggs ALL RIGHTS RESERVED - RUcore**  
`rucore.libraries.rutgers.edu` · tier `tier1`  
> between Christian theology and Freudian theory – to show the latter's psychological ... Moses and Monotheism, translated by Kathrine Jones. New York: Vintage, ...

  - **R** between Christian theology and Freudian theory – to show the latter's psychological ...  
    <sub>names freud</sub>
  - **R** Moses and Monotheism, translated by Kathrine Jones.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** New York: Vintage, ...  
    <sub>about someone else (New York), not this stop</sub>

**5. [PDF] Hannah Höch's radical imagination - UCL Discovery**  
`discovery.ucl.ac.uk` · tier `tier1`  
> The Standard Edition of the Complete Psychological Works of Sigmund. Freud, Volume XXIII (1937-1939): Moses and Monotheism, An Outline of Psycho-Analysis and ...

  - **R** The Standard Edition of the Complete Psychological Works of Sigmund.  
    <sub>names sigmund</sub>
  - **R** Freud, Volume XXIII (1937-1939): Moses and Monotheism, An Outline of Psycho-Analysis and ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**6. Freud's Mexico - Into The Wilds of Psychoanalysis (DR - Soc) PDF**  
`scribd.com` · tier `unverified`  
> The Labyrinth of Solitude is an original adaptation of Moses and Monotheism. to the Mexican context—an effort to use psychoanalytic concepts to theorize

  - **R** The Labyrinth of Solitude is an original adaptation of Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** to the Mexican context—an effort to use psychoanalytic concepts to theorize  
    <sub>about someone else (Mexican), not this stop</sub>

**7. Kindred by Chance: Spontaneous Art and Neoliberal Order - eScholarship**  
`escholarship.org` · tier `unverified`  
> ... Freud later returned in The Future of an Illusion (1927), Civilization and Its Discontents (1930), and Moses and Monotheism (1939)—built around Freud's ...

  - **R** Freud later returned in The Future of an Illusion (1927), Civilization and Its Discontents (1930), and Moses and Monotheism (1939)—built around Freud's ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**8. The Psychological Fictions of J. G. Ballard 9781472542854 ...**  
`dokumen.pub` · tier `unverified`  
> Reading Freud's Moses and Monotheism , Caruth suggests that 'By replacing factual history with the curious dynamics of trauma, Freud would seem to have ...

  - **R** Reading Freud's Moses and Monotheism , Caruth suggests that 'By replacing factual history with the curious dynamics of trauma, Freud would seem to have ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, visualizing the psychological and spiritual transition from polytheistic beliefs?`

kind **inert → inert** · R4 w0 X0

> Salvador Dalí revered Sigmund Freud’s final book, *Moses and Monotheism*, considering Freud’s argument that Moses was an Egyptian prince rather than Jewish to be one of the thinker's most profound and bitter intellectual feats.
> 
> Published in 1974 by Éditions Art & Valeur in Paris, the deluxe portfolio was created thirty-five years after Freud’s death.
> 
> Dalí personally drew the designs using a diamond stylus directly onto solid gold printing plates.
> 
> The resulting suite of ten etchings and lithographs was printed directly on sheepskin and bound in a burgundy suede portfolio featuring a sculpted metal bas-relief cover inspired by Michelangelo’s *Moses*.

  - **R** Salvador Dalí revered Sigmund Freud’s final book, *Moses and Monotheism*, considering Freud’s argument that Moses was an Egyptian prince rather than Jewish to be one of the thinker's most profound and bitter intellectual feats.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>
  - **R** Published in 1974 by Éditions Art & Valeur in Paris, the deluxe portfolio was created thirty-five years after Freud’s death.  
    <sub>names freud</sub>
  - **R** Dalí personally drew the designs using a diamond stylus directly onto solid gold printing plates.  
    <sub>names dali</sub>
  - **R** The resulting suite of ten etchings and lithographs was printed directly on sheepskin and bound in a burgundy suede portfolio featuring a sculpted metal bas-relief cover inspired by Michelangelo’s *Moses*.  
    <sub>names moses</sub>


## credit_line 5.1 — *evaluative* / relative

> **delves into the complexities of religious origins**

### SERPER — `"Moses and Monotheism" Freud Dalí why delves complexities religious origins`

8 results · kind **active → active** · R11 w0 X4

**1. 'Between Oedipus and the Sphinx: Freud and Egypt ...**  
`facebook.com` · tier `reject`  
> Akhenaten features prominently in one of Sigmund Freud's last books, Moses and Monotheism, published in 1939 while he was living in exile in ...

  - **R** Akhenaten features prominently in one of Sigmund Freud's last books, Moses and Monotheism, published in 1939 while he was living in exile in ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**2. Dalí's Religious Models: the Iconography of Martyrdom and ...**  
`academia.edu` · tier `tier1`  
> ... Dalí was in ill health (Puignau, 163-4) 4 Freud's 'The Moses of Michelangelo' [1914], supplemented by 'Moses and Monotheism: three essays' [1934-8], in ...

  - **R** Dalí was in ill health (Puignau, 163-4) 4 Freud's 'The Moses of Michelangelo' [1914], supplemented by 'Moses and Monotheism: three essays' [1934-8], in ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**3. //...Frida Kahlo...// (Mexican, 1907-1954) Moses, 1945. Oil ...**  
`facebook.com` · tier `reject`  
> Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.

  - **R** Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**4. Max Horkheimer: Lectures Towards a Psychology of Anti ...**  
`jamescrane.substack.com` · tier `unverified`  
> Salvador Dalí. Tear of Blood, Moses and Monotheism. 1975. “Civilization itself cannot be cleared of the responsibility of having engendered ...

  - **R** Tear of Blood, Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** “Civilization itself cannot be cleared of the responsibility of having engendered ...  
    <sub>about someone else (Civilization), not this stop</sub>

**5. (PDF) Person of Issue: Sigmund Freud (1856-1939)**  
`researchgate.net` · tier `unverified`  
> 1939 Moses and Monotheism. Case histories. 1905 Fragment of an Analysis of a Case of Hysteria (the Dora case history). 1909 Analysis of a ...

  - **R** 1939 Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** 1905 Fragment of an Analysis of a Case of Hysteria (the Dora case history).  
    <sub>about someone else (Fragment), not this stop</sub>
  - **X** 1909 Analysis of a ...  
    <sub>about someone else (Analysis), not this stop</sub>

**6. The Death of Sigmund Freud**  
`cdn.bookey.app` · tier `unverified`  
> 1.Freud's reflections on anti-Semitism include influences from Mark Twain's essay. 2.Freud chose not to publish 'Moses and Monotheism' due to warnings about ...

  - **R** 1.Freud's reflections on anti-Semitism include influences from Mark Twain's essay.  
    <sub>names freud</sub>
  - **R** 2.Freud chose not to publish 'Moses and Monotheism' due to warnings about ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**7. ❌Sold❌ Price: ₹299 📚 Psychopathology of Everyday Life ...**  
`instagram.com` · tier `reject`  
> ... Freudian Psychology introduces Freud's theories on ... The Origins of Religion TOTEM AND TABOO, MOSES AND MONOTHEISM AND OTHER WORKS 200 RS ...

  - **R** Freudian Psychology introduces Freud's theories on ...  
    <sub>names freud</sub>
  - **R** The Origins of Religion TOTEM AND TABOO, MOSES AND MONOTHEISM AND OTHER WORKS 200 RS ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**8. © 2019 Charles Emerson Riggs ALL RIGHTS RESERVED**  
`rucore.libraries.rutgers.edu` · tier `tier1`  
> approaches and to adopt Freud's critique of religious moralism as their own. ... Moses and Monotheism, trans. Kathrine Jones (New York: Vintage, 1939); ...

  - **R** approaches and to adopt Freud's critique of religious moralism as their own.  
    <sub>names freud</sub>
  - **R** Moses and Monotheism, trans.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Kathrine Jones (New York: Vintage, 1939); ...  
    <sub>about someone else (Kathrine Jones), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, delves into the complexities of religious origins?`

kind **active → active** · R5 w0 X0

> Salvador Dalí created this portfolio in 1974 to illustrate Sigmund Freud's final 1939 book, which controversially argued that Moses was an Egyptian nobleman rather than Hebrew and had imported monotheism from Pharaoh Akhenaten. 
> 
> Dalí was a lifelong admirer of Freud's psychoanalytic theories and described Freud's thesis on Moses as both heroic and deeply tragic. 
> 
> To produce the deluxe portfolio, Dalí engraved drawings with a diamond stylus directly onto gold printing plates and printed them onto lambskin. 
> 
> The resulting limited edition of 250 copies was published in Paris by Éditions Art & Valeur and housed in a burgundy suede case with a metal bas-relief depicting Moses. 
> 
> The work exhibited in *Picasso, Miró, Dalí: Unbound* is drawn from the collection of Boris and Galina Fridman.

  - **R** Salvador Dalí created this portfolio in 1974 to illustrate Sigmund Freud's final 1939 book, which controversially argued that Moses was an Egyptian nobleman rather than Hebrew and had imported monotheism from Pharaoh Akhenaten.  
    <sub>names sigmund freud, salvador dali, monotheism</sub>
  - **R** Dalí was a lifelong admirer of Freud's psychoanalytic theories and described Freud's thesis on Moses as both heroic and deeply tragic.  
    <sub>names moses, freud, dali</sub>
  - **R** To produce the deluxe portfolio, Dalí engraved drawings with a diamond stylus directly onto gold printing plates and printed them onto lambskin.  
    <sub>names dali</sub>
  - **R** The resulting limited edition of 250 copies was published in Paris by Éditions Art & Valeur and housed in a burgundy suede case with a metal bas-relief depicting Moses.  
    <sub>names moses</sub>
  - **R** The work exhibited in *Picasso, Miró, Dalí: Unbound* is drawn from the collection of Boris and Galina Fridman.  
    <sub>names dali</sub>


## credit_line 5.2 — *anchored* / participial

> **setting the stage for Dalí's evocative interpretations**

### SERPER — `"Moses and Monotheism" Freud Dalí why setting stage evocative interpretations`

8 results · kind **inert → inert** · R14 w1 X0

**1. //...Frida Kahlo...// (Mexican, 1907-1954) Moses, 1945. Oil ...**  
`facebook.com` · tier `reject`  
> Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.

  - **R** Her work Moses, painted as a reaction to Sigmund Freud's book Moses and Monotheism, exemplifies many of these social and political attitudes.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**2. Dalí's Religious Models: the Iconography of Martyrdom and ...**  
`academia.edu` · tier `tier1`  
> ... stage set for a drama of approximately Freudian inspiration. In any case, its ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** stage set for a drama of approximately Freudian inspiration.  
    <sub>names freud</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**3. Frankenstein, Spellbound, and World War Z**  
`doi.apa.org` · tier `unverified`  
> Freud, S. (1964). Moses and monotheism: Three essays. In J. Strachey (Ed. & Trans.), The standard edition of the complete psychological works of Sigmund Freud ( ...

  - **R** Moses and monotheism: Three essays.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** & Trans.), The standard edition of the complete psychological works of Sigmund Freud ( ...  
    <sub>names sigmund freud, sigmund, freud</sub>

**4. Sigmund Freud's extensive collection of antiquities features ...**  
`facebook.com` · tier `reject`  
> This point is not incidental because for Freud, in Moses and Monotheism, monotheism seems to represent a triumph of the mind, or what Freud ...

  - **R** This point is not incidental because for Freud, in Moses and Monotheism, monotheism seems to represent a triumph of the mind, or what Freud ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**5. Inside the Freud Museums: History, Memory and Site ...**  
`dokumen.pub` · tier `unverified`  
> ... Freud and Art, pp. 153–72. The interpretations of Freud's Moses and Monotheism are diverse and at times contradictory. The ones I found most useful for my ...

  - **R** The interpretations of Freud's Moses and Monotheism are diverse and at times contradictory.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w The ones I found most useful for my ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**6. (PDF) Freud's British Family: Reclaiming Lost Lives in ...**  
`researchgate.net` · tier `unverified`  
> 1939 book Moses and Monotheism. Jacob Freud was born in Tysmenitz ... Controversies in the English publication of Freud's The Interpretation of ...

  - **R** 1939 book Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Jacob Freud was born in Tysmenitz ...  
    <sub>names freud</sub>
  - **R** Controversies in the English publication of Freud's The Interpretation of ...  
    <sub>names freud</sub>

**7. Decade of the Drawing**  
`galleryand.studio` · tier `unverified`  
> prints that Dali executed for “Don. Quixote” and “Moses and Monotheism,” two other important livres d'artistes that demonstrate his ...

  - **R** prints that Dali executed for “Don.  
    <sub>names dali</sub>
  - **R** Quixote” and “Moses and Monotheism,” two other important livres d'artistes that demonstrate his ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**8. Coming Attractions: July 19 Through August 3 - What Will ...**  
`artsfuse.org` · tier `unverified`  
> The exhibition includes artists' interpretations of classic texts, such as the illustrations Dalí ... Moses and Monotheism, originally published ...

  - **R** The exhibition includes artists' interpretations of classic texts, such as the illustrations Dalí ...  
    <sub>names dali</sub>
  - **R** Moses and Monotheism, originally published ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, setting the stage for Dalí's evocative interpretations?`

kind **active → active** · R5 w1 X0

> Salvador Dalí created his illustration portfolio to accompany the French edition of Sigmund Freud’s final book, *Moses and Monotheism*, published in 1939. 
> 
> Freud’s controversial thesis hypothesized that Moses was not born Hebrew, but was an Egyptian nobleman who followed the monotheistic pharaoh Akhenaten. 
> 
> Dalí long idolized Freud, explicitly writing in his 1957 diary that he placed Freud "among the heroes" for writing his tragic and difficult thesis on Moses. 
> 
> Published in Paris by Art et Valeur in the mid-1970s, Dalí drew the portfolio's designs with a diamond stylus onto printing plates to produce limited-edition etchings over lithographs. 
> 
> The publisher printed the artwork directly onto glove sheepskin rather than paper, a material choice known to shrink and warp when exposed to ambient humidity. 
> 
> The completed project was housed loose-leaf in custom Plexiglas folders within a large case featuring a bas-relief relief cover based on Michelangelo's sculpture of Moses.

  - **R** Salvador Dalí created his illustration portfolio to accompany the French edition of Sigmund Freud’s final book, *Moses and Monotheism*, published in 1939.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>
  - **R** Freud’s controversial thesis hypothesized that Moses was not born Hebrew, but was an Egyptian nobleman who followed the monotheistic pharaoh Akhenaten.  
    <sub>names moses, freud</sub>
  - **R** Dalí long idolized Freud, explicitly writing in his 1957 diary that he placed Freud "among the heroes" for writing his tragic and difficult thesis on Moses.  
    <sub>names moses, freud, dali</sub>
  - **R** Published in Paris by Art et Valeur in the mid-1970s, Dalí drew the portfolio's designs with a diamond stylus onto printing plates to produce limited-edition etchings over lithographs.  
    <sub>names dali</sub>
  - w The publisher printed the artwork directly onto glove sheepskin rather than paper, a material choice known to shrink and warp when exposed to ambient humidity.  
    <sub>no entity of its own; snippet names moses and monotheism</sub>
  - **R** The completed project was housed loose-leaf in custom Plexiglas folders within a large case featuring a bas-relief relief cover based on Michelangelo's sculpture of Moses.  
    <sub>names moses</sub>


## credit_line 6.1 — *evaluative* / relative

> **the book itself is an artwork**

### SERPER — `"Moses and Monotheism" Freud Dalí why itself artwork`

8 results · kind **inert → inert** · R12 w1 X2

**1. Sigmund Freud**  
`thedali.org` · tier `unverified`  
> Freud, Sigmund. Moses and Monotheism. Vintage Books, 1967. This volume reflects Freud's commentaries on various aspects of religion, specifically his ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** This volume reflects Freud's commentaries on various aspects of religion, specifically his ...  
    <sub>names freud</sub>

**2. Freud had a lifelong fascination for the figure of Moses ...**  
`facebook.com` · tier `reject`  
> ”― Sigmund Freud, MOSES AND MONOTHEISM ABOUT MOSES AND MONOTHEISM This volume contains Freud's speculations on various aspects of religion ...

  - **R** ”― Sigmund Freud, MOSES AND MONOTHEISM ABOUT MOSES AND MONOTHEISM This volume contains Freud's speculations on various aspects of religion ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**3. Beware the Boa Constructor! Freud, Modern Art and the ...**  
`88invisiblemirrors.blog` · tier `unverified`  
> Freud's appreciation of Dali's mastery of the medium of painting ... Sigmund Freud Moses and Monotheism (1939). Sigmund Freud An Outline ...

  - **R** Freud's appreciation of Dali's mastery of the medium of painting ...  
    <sub>names freud, dali</sub>
  - **R** Sigmund Freud Moses and Monotheism (1939).  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** Sigmund Freud An Outline ...  
    <sub>names sigmund freud, sigmund, freud</sub>

**4. FREUD and EGYPT**  
`miekezilverberg.com` · tier `unverified`  
> Akhenaten features prominently in one of Sigmund Freud's last books, Moses and Monotheism ... The exhibition is best taken as a supplement to a ...

  - **R** Akhenaten features prominently in one of Sigmund Freud's last books, Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - w The exhibition is best taken as a supplement to a ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**5. A meeting of the minds**  
`cltampa.com` · tier `unverified`  
> Yehuda is incensed with Freud after having read a draft of Moses and Monotheism, and Dalí, in London to pay homage to Freud, is intrigued with the naked girl ...

  - **R** Yehuda is incensed with Freud after having read a draft of Moses and Monotheism, and Dalí, in London to pay homage to Freud, is intrigued with the naked girl ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**6. New London Exhibition 'Freud's Antiquity' Unveils ...**  
`uh.edu` · tier `tier1`  
> ... Moses and Monotheism.” “Freud created the 'archaeological metaphor' to show how the mind resembles an archaeological site which the analyst ...

  - **R** Moses and Monotheism.” “Freud created the 'archaeological metaphor' to show how the mind resembles an archaeological site which the analyst ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**7. "Picasso, Miró, Dalí: Unbound" at the Museum of Fine Arts ...**  
`airmail.news` · tier `unverified`  
> Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism is an example of an artist illustrating a foundational text. Resistant to easy ...

  - **R** Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism is an example of an artist illustrating a foundational text.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** Resistant to easy ...  
    <sub>about someone else (Resistant), not this stop</sub>

**8. Frida Kahlo, Surrealism, and the Gradivian Myth**  
`ahnp.ub.uni-heidelberg.de` · tier `unverified`  
> Breton was an admirer of Freud's works, especially The Interpretation of ... Freud's Moses and Monotheism, ed. Ruth Ginsburg and Ilana Pardes, Tübingen ...

  - **R** Breton was an admirer of Freud's works, especially The Interpretation of ...  
    <sub>names freud</sub>
  - **R** Freud's Moses and Monotheism, ed.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **X** Ruth Ginsburg and Ilana Pardes, Tübingen ...  
    <sub>about someone else (Ruth Ginsburg), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, the book itself is an artwork?`

kind **active → inert** · R4 w0 X1

> Salvador Dalí created this livre d'artiste portfolio in 1974 to illustrate the final, controversial 1939 book written by his intellectual hero Sigmund Freud.
> 
> Dalí's interest in illustrating Freud's text stemmed in part from personal associations with his authoritarian father, who twisted his hair into a horn reminiscent of traditional depictions of Moses.
> 
> The project was commissioned and issued by the Parisian publisher Éditions Art et Valeur in an edition limited to 250 numbered copies.
> 
> Dalí drew the compositions directly onto gold-plated printing plates using a diamond-tipped stylus before running them as colour etchings over lithographs onto lambskin parchment.
> 
> The complete artwork was issued not as a bound book, but as loose sheets housed inside Plexiglas folders and a suede-covered case cast with a bas-relief portrait of Moses.

  - **R** Salvador Dalí created this livre d'artiste portfolio in 1974 to illustrate the final, controversial 1939 book written by his intellectual hero Sigmund Freud.  
    <sub>names sigmund freud, salvador dali, salvador</sub>
  - **R** Dalí's interest in illustrating Freud's text stemmed in part from personal associations with his authoritarian father, who twisted his hair into a horn reminiscent of traditional depictions of Moses.  
    <sub>names moses, freud, dali</sub>
  - **X** The project was commissioned and issued by the Parisian publisher Éditions Art et Valeur in an edition limited to 250 numbered copies.  
    <sub>about someone else (Parisian), not this stop</sub>
  - **R** Dalí drew the compositions directly onto gold-plated printing plates using a diamond-tipped stylus before running them as colour etchings over lithographs onto lambskin parchment.  
    <sub>names dali</sub>
  - **R** The complete artwork was issued not as a bound book, but as loose sheets housed inside Plexiglas folders and a suede-covered case cast with a bas-relief portrait of Moses.  
    <sub>names moses</sub>


## credit_line 7.1 — *evaluative* / participial

> **bridging literary and visual art forms**

### SERPER — `"Moses and Monotheism" Freud Dalí why bridging literary visual forms`

8 results · kind **inert → inert** · R12 w1 X3

**1. Beware the Boa Constructor! Freud, Modern Art and the Riddle of ...**  
`88invisiblemirrors.blog` · tier `unverified`  
> If taken sequentially from his earliest work On Aphasia (1891) to Moses and Monotheism (1939), the story of psychoanalysis can be read as an ...

  - **R** If taken sequentially from his earliest work On Aphasia (1891) to Moses and Monotheism (1939), the story of psychoanalysis can be read as an ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**2. Sigmund Freud's extensive collection of antiquities features several horse ...**  
`facebook.com` · tier `reject`  
> Returning to Moses twenty years later in his weird and wonderful book Moses and Monotheism, Freud gives final form to the possible virtues ...

  - **R** Returning to Moses twenty years later in his weird and wonderful book Moses and Monotheism, Freud gives final form to the possible virtues ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**3. Wading into Battle: Frida Kahlo, Surrealism, and the Gradivian Myth**  
`ahnp.ub.uni-heidelberg.de` · tier `unverified`  
> ... visual and literary. [29] The female foot as marker of eroticism and ... Freud's Moses and Monotheism, ed. Ruth Ginsburg and Ilana Pardes, Tübingen ...

  - w [29] The female foot as marker of eroticism and ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>
  - **R** Freud's Moses and Monotheism, ed.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **X** Ruth Ginsburg and Ilana Pardes, Tübingen ...  
    <sub>about someone else (Ruth Ginsburg), not this stop</sub>

**4. Freud Museum London on Instagram: "April's 4pm Session promises to be ...**  
`instagram.com` · tier `reject`  
> ... book, 'Moses and Monotheism'. Our latest afternoon session explores Freud's fascination with Moses through the years, included with your ...

  - **R** book, 'Moses and Monotheism'.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Our latest afternoon session explores Freud's fascination with Moses through the years, included with your ...  
    <sub>names moses, freud</sub>

**5. (PDF) Dalí's Religious Models: the Iconography of Martyrdom and its ...**  
`academia.edu` · tier `tier1`  
> ... visual lexicon for the themes through which Freud was guiding him. Lorca ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** visual lexicon for the themes through which Freud was guiding him.  
    <sub>names freud</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**6. Sigmund Freud - Wikipedia**  
`en.wikipedia.org` · tier `tier1`  
> ... book form. In contrast Allan Hobson believes that Freud, by ... 62–69, and Chaney, 'Moses and Monotheism, by Sigmund Freud', 'The Canon ...

  - **R** In contrast Allan Hobson believes that Freud, by ...  
    <sub>names freud</sub>
  - **R** 62–69, and Chaney, 'Moses and Monotheism, by Sigmund Freud', 'The Canon ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**7. Sigmund Freud's influence on modern literature and art - Facebook**  
`facebook.com` · tier `reject`  
> ... Freud had a profound impact on visual art. Here we examine the many ... Moses and Monotheism (1939); An Outline of Psychoanalysis (1940).

  - **R** Freud had a profound impact on visual art.  
    <sub>names freud</sub>
  - **X** Here we examine the many ...  
    <sub>about someone else (Here), not this stop</sub>
  - **R** Moses and Monotheism (1939); An Outline of Psychoanalysis (1940).  
    <sub>names moses and monotheism, monotheism, moses</sub>

**8. Inside the Freud Museums: History, Memory and Site-Responsive Art ...**  
`dokumen.pub` · tier `unverified`  
> In his book Moses and Monotheism Freud compares the history of the Jews with trauma. Again he puts forward the idea that there is a form of forgetting and ...

  - **R** In his book Moses and Monotheism Freud compares the history of the Jews with trauma.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **X** Again he puts forward the idea that there is a form of forgetting and ...  
    <sub>about someone else (Again), not this stop</sub>

### GEMINI — `What story can be told to visitors of Picasso, Miró, Dalí: Unbound about Moses and Monotheism, bridging literary and visual art forms?`

kind **active → active** · R4 w0 X1

> * Dalí held a lifelong fascination with Sigmund Freud’s psychoanalytic theories, describing Freud's 1939 text *Moses and Monotheism* in his 1957 journal as the author's "best and most tragic" work.
> * Published in 1974 by Editions Art & Valeur in Paris, the project was conceived as an artist's book (*livre d'artiste*) uniting Freud's historical-psychoanalytic text with ten original prints by Dalí.
> * To produce the suite, Dalí etched the illustrations directly onto large gold printing plates using a diamond stylus.
> * Rather than conventional paper, the illustrations were printed onto sheets of soft lambskin suede, an unusual support prone to warping and shrinkage in shifting humidity.
> * The entire edition was limited to 300 copies, all packaged in heavy portfolio cases featuring a relief of Moses based on Michelangelo's sculpture set within an Eye of Horus to reinforce Freud's thesis that Moses was Egyptian.

  - **R** * Dalí held a lifelong fascination with Sigmund Freud’s psychoanalytic theories, describing Freud's 1939 text *Moses and Monotheism* in his 1957 journal as the author's "best and most tragic" work.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** * Published in 1974 by Editions Art & Valeur in Paris, the project was conceived as an artist's book (*livre d'artiste*) uniting Freud's historical-psychoanalytic text with ten original prints by Dalí.  
    <sub>names freud, dali</sub>
  - **R** * To produce the suite, Dalí etched the illustrations directly onto large gold printing plates using a diamond stylus.  
    <sub>names dali</sub>
  - **X** * Rather than conventional paper, the illustrations were printed onto sheets of soft lambskin suede, an unusual support prone to warping and shrinkage in shifting humidity.  
    <sub>about someone else (Rather), not this stop</sub>
  - **R** * The entire edition was limited to 300 copies, all packaged in heavy portfolio cases featuring a relief of Moses based on Michelangelo's sculpture set within an Eye of Horus to reinforce Freud's thesis that Moses was Egyptian.  
    <sub>names moses, freud</sub>

