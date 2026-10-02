# Raw results — every query, both engines, nothing summarised

**37 Serper queries + 37 Gemini (grounded) calls = 74 retrievals · ~$0.185 · 212s**

Verdict marks on each sentence come from the D505 relevance gate: **R** relevant (names one of the stop's own entities) · **w** weak (anaphoric, its own snippet establishes the subject) · **X** irrelevant (names nothing of ours, or names somebody else).

`kind` is `material_kind` — the same eventful/active/inert instrument step 3d uses — shown **before → after** the relevance gate.


---

# Le Lézard aux plumes d’or (The Lizard with Golden Feathers)


## Seed 2.1 — evaluative

**Seed phrase:** `revolutionized the book as an art form with its deep collaboration`  
**Question asked:** What did This exhibition in Gallery 184 actually DO that would justify "revolutionized the book as an art form with its deep collaboration"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" commissioned` — *the phrase is ours; hunt the event (commissioned) behind it*

### SERPER — 8 results · kind **inert → inert** · R10 w0 X5

**1. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or series)**  
`ragoarts.com` · tier `unverified`  
> Joan ... In 1958, Miró was commissioned to make two significant murals ...

  - **R** In 1958, Miró was commissioned to make two significant murals ...  
    <sub>names miro</sub>

**2. Joan Miró , Plate XII, from Le Lezard aux Plumes d'Or (M. 525) | Christie's**  
`christies.com` · tier `market`  
> Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M. 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...

  - **R** Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...  
    <sub>names miro</sub>

**3. Joan Miró Lithographs & Etchings - Masterworks Fine Art**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Lithograph, Le Lezard Aux Plumes d'Or (The Lizard with Golden Joan Miró Lithograph ... commissioned mural Personnage ...

  - **R** Joan Miró Lithograph, Le Lezard Aux Plumes d'Or (The Lizard with Golden Joan Miró Lithograph ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** commissioned mural Personnage ...  
    <sub>about someone else (Personnage), not this stop</sub>

**4. Museum of Fine Arts, Boston - Facebook**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

**5. Joan Miró Artwork - Christopher Clark Fine Art**  
`clarkfineart.com` · tier `unverified`  
> In 1933, he was commissioned to do three etchings for the poems of Georges Hugnet. ... Joan Miró lithograph "Le Lézard aux Plumes d'Or". Le Lézard aux Plumes d'Or.

  - **X** In 1933, he was commissioned to do three etchings for the poems of Georges Hugnet.  
    <sub>about someone else (Georges Hugnet), not this stop</sub>
  - **R** Joan Miró lithograph "Le Lézard aux Plumes d'Or".  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Le Lézard aux Plumes d'Or.  
    <sub>names le lezard, lezard, plumes</sub>

**6. Learn more about the playful imagination of Joan Miró in “Le Lézard ...**  
`instagram.com` · tier `reject`  
> Learn more about the playful imagination of Joan Miró in “Le Lézard aux Plumes d'Or” with OUMA's Assistant Collections Manager and Registrar, Courtney Christy!

  - **R** Learn more about the playful imagination of Joan Miró in “Le Lézard aux Plumes d'Or” with OUMA's Assistant Collections Manager and Registrar, Courtney Christy!  
    <sub>names le lezard, joan miro, plumes</sub>

**7. Notice anything differnet about Joan Miró's Personnages Oiseaux? Join ...**  
`facebook.com` · tier `reject`  
> A museum registrar at Oglethorpe University presents a detailed analysis of the surrealistic artwork "Le Lézard aux Plumes d'Or" by artist Joan ...

  - **R** A museum registrar at Oglethorpe University presents a detailed analysis of the surrealistic artwork "Le Lézard aux Plumes d'Or" by artist Joan ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Buy Picture "Le lézard aux plumes d'or" (1971) by Joan Miró ...**  
`kunsthaus-artes.de` · tier `unverified`  
> Detailed description. Picture "Le lézard aux plumes d'or" (1971). Colour lithograph, 1971. Edition: 40 copies on Japanese paper, numbered and signed.

  - **X** Detailed description.  
    <sub>about someone else (Detailed), not this stop</sub>
  - **R** Picture "Le lézard aux plumes d'or" (1971).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Colour lithograph, 1971.  
    <sub>about someone else (Colour), not this stop</sub>
  - **X** Edition: 40 copies on Japanese paper, numbered and signed.  
    <sub>about someone else (Edition), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> The exhibition *Picasso, Miró, Dalí:

  - **R** The exhibition *Picasso, Miró, Dalí:  
    <sub>names miro</sub>


## Seed 2.2 — evaluative

**Seed phrase:** `focusing on the livre d'artiste`  
**Question asked:** What did This exhibition in Gallery 184 actually DO that would justify "focusing on the livre d'artiste"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" dispute` — *the phrase is ours; hunt the event (dispute) behind it*

### SERPER — 8 results · kind **active → inert** · R9 w3 X4

**1. Lot 34 - 'Le Lezard aux Plumes D'or (1971)' by Joan Miro | Morgan O ...**  
`morganodriscoll.com` · tier `unverified`  
> Le Lezard aux Plumes D'or (1971) ; Hammer Price: €3,400 ; Lot Number: 34 ; Artist: Joan Miro (1893-1983) Spanish ; Title: Le Lezard aux Plumes D'or (1971).

  - **R** Le Lezard aux Plumes D'or (1971) ; Hammer Price: €3,400 ; Lot Number: 34 ; Artist: Joan Miro (1893-1983) Spanish ; Title: Le Lezard aux Plumes D'or (1971).  
    <sub>names le lezard, joan miro, plumes</sub>

**2. Lot - JOAN MIRÓ Le Lézard aux Plumes d'Or.**  
`swanngalleries.com` · tier `unverified`  
> JOAN MIRÓ Le Lézard aux Plumes d'Or. ; Sold: $5,166.00. Estimate: $5,000 - $8,000. (Sold Price includes Buyer's Premium) ; Estimate: $5,000 - $8,000 ; Condition: ...

  - **R** JOAN MIRÓ Le Lézard aux Plumes d'Or.  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** Estimate: $5,000 - $8,000.  
    <sub>about someone else (Estimate), not this stop</sub>
  - **X** (Sold Price includes Buyer's Premium) ; Estimate: $5,000 - $8,000 ; Condition: ...  
    <sub>about someone else (Sold Price), not this stop</sub>

**3. Museum of Fine Arts, Boston - Facebook**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

**4. Sold at Auction: Joan Miró, Joan Miro (Spanish, 1893-1983) "Le ...**  
`invaluable.com` · tier `market`  
> Joan Miró. Lot 34: Joan Miro (Spanish, 1893-1983) "Le lézard aux Plumes d'Or" Lithograph ... Joan Miró ... dispute. In the event of a dispute after the sale ...

  - **R** Lot 34: Joan Miro (Spanish, 1893-1983) "Le lézard aux Plumes d'Or" Lithograph ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - w In the event of a dispute after the sale ...  
    <sub>no entity of its own; snippet names le lezard</sub>

**5. Joan Miró Artwork - Christopher Clark Fine Art**  
`clarkfineart.com` · tier `unverified`  
> In this work, one sees a man raising his fist as the inscription reads: In the present conflict ... Joan Miró lithograph "Le Lézard aux Plumes d'Or". Le Lézard ...

  - w In this work, one sees a man raising his fist as the inscription reads: In the present conflict ...  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **R** Joan Miró lithograph "Le Lézard aux Plumes d'Or".  
    <sub>names le lezard, joan miro, plumes</sub>

**6. Joan Miró (1893-1983), Untitled, from "Le Lezard aux Plumes d'Or," 1967**  
`johnmoran.com` · tier `unverified`  
> Untitled, from "Le Lezard aux Plumes d'Or," 1967. Lithograph in colors on ... Any dispute, claim, or controversy arising out of or relating to these ...

  - **R** Untitled, from "Le Lezard aux Plumes d'Or," 1967.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Lithograph in colors on ...  
    <sub>about someone else (Lithograph), not this stop</sub>
  - w Any dispute, claim, or controversy arising out of or relating to these ...  
    <sub>no entity of its own; snippet names le lezard</sub>

**7. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names le lezard, joan miro, plumes</sub>

**8. Joan Miro (1893-1983) - Lot 148 - Yann Le Mouel**  
`yannlemouel.com` · tier `unverified`  
> Joan Miro (1893-1983) - Lot 148. Result · Joan ... Joan Miro (1893-1983) Le Lézard aux plumes d'or ... In the event of a dispute, the Auctioneer has the ...

  - **R** Joan Miro (1893-1983) - Lot 148.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Joan Miro (1893-1983) Le Lézard aux plumes d'or ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** In the event of a dispute, the Auctioneer has the ...  
    <sub>about someone else (Auctioneer), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X1

> The exhibition in Gallery 184 (the Lois B. and Michael K. Torf Gallery), titled *Picasso, Miró, Dalí: Unbound*, was explicitly dedicated to examining the *livre d'artiste* as an art form produced by 20th-century Spanish artists [Museum of Fine Arts Boston, "Picasso, Miró, Dalí: Unbound"]

  - **X** The exhibition in Gallery 184 (the Lois B.  
    <sub>about someone else (Gallery), not this stop</sub>
  - **R** Torf Gallery), titled *Picasso, Miró, Dalí: Unbound*, was explicitly dedicated to examining the *livre d'artiste* as an art form produced by 20th-century Spanish artists [Museum of Fine Arts Boston, "Picasso, Miró, Dalí: Unbound"]  
    <sub>names miro</sub>


## Seed 4.1 — evaluative

**Seed phrase:** `showcasing how artists express these concepts through their unrivaled creativity`  
**Question asked:** What did These actually DO that would justify "showcasing how artists express these concepts through their unrivaled creativity"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" delayed` — *the phrase is ours; hunt the event (delayed) behind it*

### SERPER — 8 results · kind **inert → inert** · R9 w1 X2

**1. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...

  - **R** Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...  
    <sub>names le lezard, joan miro, plumes</sub>

**2. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...

  - **R** Today, Le lézard aux plumes d'or is prized for its innovation, rarity, and the way it encapsulates Miró's late-career creativity—joyful, poetic, and defiantly ...  
    <sub>names le lezard, lezard, plumes</sub>

**3. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**4. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53. Mourlot 831. This version was pulled before lettering, (before the text was ...

  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53.  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>
  - w This version was pulled before lettering, (before the text was ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**5. Joan Miró (1893-1983); Le Lézard aux Plumes d'Or**  
`bonhams.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk. 148), 1971. The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...

  - **R** Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **R** The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...  
    <sub>names miro</sub>

**6. Le Lézard aux Plumes d'Or by Joan Miró, 1971 | Lithographs**  
`artsper.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or, Plate X is a beautiful color lithograph on Japanese paper, realized in 1971 by the Spanish Surrealist artist Joan Miró (Montroing, ...

  - **R** Le Lézard aux Plumes d'Or, Plate X is a beautiful color lithograph on Japanese paper, realized in 1971 by the Spanish Surrealist artist Joan Miró (Montroing, ...  
    <sub>names le lezard, joan miro, plumes</sub>

**7. Museum of Fine Arts, Boston**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

**8. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These words ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI (grounded) — kind **inert → inert** · R3 w0 X0

> Joan Miró wrote the original poetic text and created the accompanying suite of color lithographs for the publication. 
> 
> Miró handwrote the text across twenty-six pages to integrate his script directly with the printed imagery. 
> 
> The lithographs were printed at the Mourlot workshop and published in Paris by Louis Broder in 

  - **R** Joan Miró wrote the original poetic text and created the accompanying suite of color lithographs for the publication.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Miró handwrote the text across twenty-six pages to integrate his script directly with the printed imagery.  
    <sub>names miro</sub>
  - **R** The lithographs were printed at the Mourlot workshop and published in Paris by Louis Broder in  
    <sub>names louis broder, mourlot, broder</sub>


## Seed 5.1 — anchored

**Seed phrase:** `Broder's pivotal decision`  
**Question asked:** Is this true, and what is the event behind it: "Broder's pivotal decision"?  
**Query built:** `Broder "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R10 w1 X2

**1. Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M.  
    <sub>names louis broder, le lezard, joan miro</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**2. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Printed by Mourlot, Paris; published by Louis Broder, Paris. Catalogue Raisonné & COA: Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers) ...

  - **R** Printed by Mourlot, Paris; published by Louis Broder, Paris.  
    <sub>names louis broder, mourlot, broder</sub>
  - **R** Catalogue Raisonné & COA: Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers) ...  
    <sub>names le lezard, joan miro, plumes</sub>

**3. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris ...**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, le lezard, joan miro</sub>

**4. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**5. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These words ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names le lezard, lezard, plumes</sub>

**6. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Joan Miró. (Barcelona ... Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers), a portfolio published by Louis Broder and printed in Paris by Mourlot.

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers), a portfolio published by Louis Broder and printed in Paris by Mourlot.  
    <sub>names louis broder, le lezard, mourlot</sub>

**7. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names le lezard, joan miro, plumes</sub>

**8. Joan Miró. Wrapper front from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Wrapper front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Wrapper front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> In 1967, publisher Louis Broder and Joan Miró discovered that a manufacturing defect in the paper had

  - **R** In 1967, publisher Louis Broder and Joan Miró discovered that a manufacturing defect in the paper had  
    <sub>names louis broder, joan miro, broder</sub>


## Seed 5.2 — evaluative

**Seed phrase:** `allowing the artist to blend visual and textual narratives seamlessly`  
**Question asked:** What did At Le Lézard aux actually DO that would justify "allowing the artist to blend visual and textual narratives seamlessly"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" commissioned` — *the phrase is ours; hunt the event (commissioned) behind it*

### SERPER — 8 results · kind **active → inert** · R11 w2 X7

**1. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**2. Plate XII, from Le Lezard aux Plumes d'Or (M. 525)**  
`christies.com` · tier `market`  
> Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M. 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...

  - **R** Joan Miró Plate XII, from Le Lezard aux Plumes d'Or (M.  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** 525) lithograph in colours, 1967, on wove paper watermark Miró, from the set of 18, signed in pencil ...  
    <sub>names miro</sub>

**3. Joan Miró Lithographs & Etchings**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Lithograph, Le Lezard Aux Plumes d'Or (The Lizard with Golden Joan Miró Lithograph ... commissioned mural Personnage ...

  - **R** Joan Miró Lithograph, Le Lezard Aux Plumes d'Or (The Lizard with Golden Joan Miró Lithograph ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** commissioned mural Personnage ...  
    <sub>about someone else (Personnage), not this stop</sub>

**4. Museum of Fine Arts, Boston**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

**5. Joan Miro Artwork**  
`clarkfineart.com` · tier `unverified`  
> In 1933, he was commissioned to do three etchings for the poems of Georges Hugnet. ... Joan Miró lithograph "Le Lézard aux Plumes d'Or". Le Lézard aux Plumes d'Or.

  - **X** In 1933, he was commissioned to do three etchings for the poems of Georges Hugnet.  
    <sub>about someone else (Georges Hugnet), not this stop</sub>
  - **R** Joan Miró lithograph "Le Lézard aux Plumes d'Or".  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Le Lézard aux Plumes d'Or.  
    <sub>names le lezard, lezard, plumes</sub>

**6. Learn more about the playful imagination of Joan Miró in “Le ...**  
`instagram.com` · tier `reject`  
> Learn more about the playful imagination of Joan Miró in “Le Lézard aux Plumes d'Or” with OUMA's Assistant Collections Manager and Registrar, Courtney Christy!

  - **R** Learn more about the playful imagination of Joan Miró in “Le Lézard aux Plumes d'Or” with OUMA's Assistant Collections Manager and Registrar, Courtney Christy!  
    <sub>names le lezard, joan miro, plumes</sub>

**7. Notice anything differnet about Joan Miró's Personnages ...**  
`facebook.com` · tier `reject`  
> ... Le Lézard aux Plumes d'Or" by artist Joan Miró. The video explains ... commissioned by the Guggenheim Foundation. The video explains ...

  - **R** Le Lézard aux Plumes d'Or" by artist Joan Miró.  
    <sub>names le lezard, joan miro, plumes</sub>
  - w The video explains ...  
    <sub>no entity of its own; snippet names le lezard</sub>
  - **X** commissioned by the Guggenheim Foundation.  
    <sub>about someone else (Guggenheim Foundation), not this stop</sub>
  - w The video explains ...  
    <sub>no entity of its own; snippet names le lezard</sub>

**8. Buy Picture "Le lézard aux plumes d'or" (1971) by Joan Miró**  
`kunsthaus-artes.de` · tier `unverified`  
> Detailed description. Picture "Le lézard aux plumes d'or" (1971). Colour lithograph, 1971. Edition: 40 copies on Japanese paper, numbered and signed.

  - **X** Detailed description.  
    <sub>about someone else (Detailed), not this stop</sub>
  - **R** Picture "Le lézard aux plumes d'or" (1971).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Colour lithograph, 1971.  
    <sub>about someone else (Colour), not this stop</sub>
  - **X** Edition: 40 copies on Japanese paper, numbered and signed.  
    <sub>about someone else (Edition), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Joan Miró authored both the poetic text and the accompanying illustrations for *Le Lézard aux plumes d’or*

  - **R** Joan Miró authored both the poetic text and the accompanying illustrations for *Le Lézard aux plumes d’or*  
    <sub>names le lezard aux plumes d’or, le lezard, joan miro</sub>


## Seed 6.1 — anchored

**Seed phrase:** `Freud's exploration of`  
**Question asked:** Is this true, and what is the event behind it: "Freud's exploration of"?  
**Query built:** `Freud "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **inert → inert** · R10 w1 X6

**1. JARED'S PICKS FOR 8/22-23   1) Picasso, Miró, Dalí: Unbound at the ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and cover); ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and cover); ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names le lezard, joan miro, plumes</sub>

**3. Joan Miró Artwork - Christopher Clark Fine Art**  
`clarkfineart.com` · tier `unverified`  
> Freud's conclusions about the subconscious and dream states were fundamental to this thought process. ... Joan Miró lithograph "Le Lézard aux Plumes d'Or". Le ...

  - **X** Freud's conclusions about the subconscious and dream states were fundamental to this thought process.  
    <sub>about someone else (Freud's), not this stop</sub>
  - **R** Joan Miró lithograph "Le Lézard aux Plumes d'Or".  
    <sub>names le lezard, joan miro, plumes</sub>

**4. "Picasso, Miró, Dalí: Unbound" at the Museum of Fine Arts Boston - Air Mail**  
`airmail.news` · tier `unverified`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ... Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism is an example ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism is an example ...  
    <sub>about someone else (Dalí's), not this stop</sub>

**5. Currently showing at our Las Vegas gallery, the works of Joan Miró ...**  
`facebook.com` · tier `reject`  
> ... (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on ... Freudian explorations of the unconscious into 20th- century art.

  - **R** (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on ...  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Freudian explorations of the unconscious into 20th- century art.  
    <sub>about someone else (Freudian), not this stop</sub>

**6. Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Abstract black-line drawing with bursts of red, yellow, green, and blue. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ...

  - **X** Abstract black-line drawing with bursts of red, yellow, green, and blue.  
    <sub>about someone else (Abstract), not this stop</sub>
  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ...  
    <sub>names le lezard, joan miro, plumes</sub>

**7. Le lézard aux plumes d'or, Paris, Louis Broder, 1971 by Joan Miro ...**  
`art.salon` · tier `unverified`  
> The work Le lézard aux plumes d'or, Paris, Louis Broder, 1971 by Joan Miró was auctioned at Christies in New York in April 2015. The result of USD 15,000.00 ...

  - **R** The work Le lézard aux plumes d'or, Paris, Louis Broder, 1971 by Joan Miró was auctioned at Christies in New York in April 2015.  
    <sub>names louis broder, le lezard, joan miro</sub>
  - w The result of USD 15,000.00 ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**8. The Essences of the Earth H.C (1968) by Joan Miró - For Sale | Artsy**  
`artsy.net` · tier `market`  
> ... Freud's psychoanalytic theories. Celebrated for ... Joan Miró, 'Le Lézard aux Plumes d'Or (one plate)' ... Joan Miró, 'Joan Miro A L'encre', 1972 · Joan ...

  - **X** Freud's psychoanalytic theories.  
    <sub>about someone else (Freud's), not this stop</sub>
  - **R** Joan Miró, 'Le Lézard aux Plumes d'Or (one plate)' ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Joan Miró, 'Joan Miro A L'encre', 1972 · Joan ...  
    <sub>names joan miro, joan, miro</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 8.1 — anchored

**Seed phrase:** `drawing you into the surreal world that Joan Miró has crafted`  
**Question asked:** Is this true, and what is the event behind it: "drawing you into the surreal world that Joan Miró has crafted"?  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or"` — *verify the named claim*

### SERPER — 8 results · kind **inert → inert** · R11 w0 X4

**1. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names le lezard, joan miro, plumes</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names le lezard, lezard, plumes</sub>

**3. Le Lézard aux Plumes d'Or (1971) by Joan Miró - For Sale | Artsy**  
`artsy.net` · tier `market`  
> Joan Miró. ,. Le Lézard aux Plumes d'Or, 1971 · High auction record. US$53.5m, Christie's, 2026 · Blue-chip. Represented by internationally recognized galleries.

  - **R** Le Lézard aux Plumes d'Or, 1971 · High auction record.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** US$53.5m, Christie's, 2026 · Blue-chip.  
    <sub>about someone else (Christie's), not this stop</sub>
  - **X** Represented by internationally recognized galleries.  
    <sub>about someone else (Represented), not this stop</sub>

**4. Le Lézard aux plumes d'or (The Lizard with Golden Feathers) | MoMA**  
`moma.org` · tier `tier1`  
> Le Lézard aux plumes d'or (The Lizard with. Golden Feathers). These works are part of an illustrated book. 40 works online. Joan Miró.

  - **R** Le Lézard aux plumes d'or (The Lizard with.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** These works are part of an illustrated book.  
    <sub>about someone else (These), not this stop</sub>

**5. Joan Miró (1893-1983); Le Lézard aux Plumes d'Or - Bonhams**  
`bonhams.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk. 148), 1971. The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...

  - **R** Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **R** The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...  
    <sub>names miro</sub>

**6. Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no. 515**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no. 515. No image available. Artist: Joan Miró (1893 - 1983). Medium: Etching ...

  - **R** Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no.  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Artist: Joan Miró (1893 - 1983).  
    <sub>names joan miro, joan, miro</sub>

**7. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or series)**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**8. Joan Miró - Le Lezard aux Plumes d'Or - National Galleries of Scotland**  
`nationalgalleries.org` · tier `unverified`  
> This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.

  - **R** This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 10.1 — anchored

**Seed phrase:** `Louis Broder, a figure renowned for his commitment to the art of the book`  
**Question asked:** Is this true, and what is the event behind it: "Louis Broder, a figure renowned for his commitment to the art of the book"?  
**Query built:** `Louis Broder "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **inert → inert** · R10 w1 X3

**1. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...

  - **R** Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...  
    <sub>names le lezard, joan miro, plumes</sub>

**2. Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M.  
    <sub>names louis broder, le lezard, joan miro</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**3. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names le lezard, lezard, plumes</sub>

**4. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or series)**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**5. Joan Miró. Cover front from Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**6. Joan Miró's Broder Collection: How One Artist Revolutionized Lithography**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These words ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names le lezard, lezard, plumes</sub>

**7. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971 - Artsy**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, le lezard, joan miro</sub>

**8. Le Lezards aux Plumes by Joan Miro, 1971 - Mourlot Editions**  
`mourloteditions.com` · tier `unverified`  
> Joan Miró · Henry Moore · Ira Moskowitz · Alphonse Mucha · Roger Mühl · Edvard ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53 ...

  - **R** Joan Miró · Henry Moore · Ira Moskowitz · Alphonse Mucha · Roger Mühl · Edvard ...  
    <sub>names joan miro, joan, miro</sub>
  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53 ...  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R2 w0 X0

> Louis Broder was a Paris-based publisher who specialized in publishing limited-edition illustrated books (*livres d'artiste*) with prominent modern artists, including Joan Miró [Joan Miró's Broder Collection, Atelier Mourlot / Joan Miró: Lithographe III, Maeght Éditeur]. In 1967, Miró created an initial series of color lithographs to illustrate his own text for *Le Lé

  - **R** Louis Broder was a Paris-based publisher who specialized in publishing limited-edition illustrated books (*livres d'artiste*) with prominent modern artists, including Joan Miró [Joan Miró's Broder Collection, Atelier Mourlot / Joan Miró: Lithographe III, Maeght Éditeur].  
    <sub>names louis broder, joan miro, mourlot</sub>
  - **R** In 1967, Miró created an initial series of color lithographs to illustrate his own text for *Le Lé  
    <sub>names miro</sub>


## Seed 10.2 — evaluative

**Seed phrase:** `the exhibition highlights`  
**Question asked:** What did Published by actually DO that would justify "the exhibition highlights"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" history` — *the phrase is ours; hunt the event (history) behind it*

### SERPER — 8 results · kind **inert → inert** · R8 w1 X5

**1. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Historical Description. Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.

  - **X** Historical Description.  
    <sub>about someone else (Historical Description), not this stop</sub>
  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names le lezard, joan miro, plumes</sub>

**2. Le Lezards aux Plumes by Joan Miro, 1971**  
`mourloteditions.com` · tier `unverified`  
> ... Le lézard aux plumes d'or", Louis Broder publisher. Corredor-Matheos N° 53. Mourlot 831. This version was pulled before lettering, (before the text was ...

  - **R** Le lézard aux plumes d'or", Louis Broder publisher.  
    <sub>names louis broder, le lezard, broder</sub>
  - **X** Corredor-Matheos N° 53.  
    <sub>about someone else (Corredor-Matheos), not this stop</sub>
  - w This version was pulled before lettering, (before the text was ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**3. Le lézard aux plumes d'or (1971) by Joan Miró**  
`artsy.net` · tier `market`  
> Joan Miró. ,. Le lézard aux plumes d'or, 1971 · High auction record. US$53.5m, Christie's, 2026 · Blue-chip. Represented by internationally recognized galleries.

  - **R** Le lézard aux plumes d'or, 1971 · High auction record.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** US$53.5m, Christie's, 2026 · Blue-chip.  
    <sub>about someone else (Christie's), not this stop</sub>
  - **X** Represented by internationally recognized galleries.  
    <sub>about someone else (Represented), not this stop</sub>

**4. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**5. JOAN MIRÓ (1893-1983), Cover, from: Le Lézard aux ...**  
`onlineonly.christies.com` · tier `market`  
> JOAN MIRÓ (1893-1983) Cover, from: Le Lézard aux plumes d'or lithograph in colours, on Japan Kochi paper, 1971, signed in pencil, numbered 'E.A. 2/10' (the ...

  - **R** JOAN MIRÓ (1893-1983) Cover, from: Le Lézard aux plumes d'or lithograph in colours, on Japan Kochi paper, 1971, signed in pencil, numbered 'E.A.  
    <sub>names le lezard, joan miro, plumes</sub>

**6. Joan Miró - Le Lezard aux Plumes d'Or**  
`nationalgalleries.org` · tier `unverified`  
> This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.

  - **R** This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.  
    <sub>names le lezard, joan miro, plumes</sub>

**7. (Le Lézard aux Plumes d'Or, M.794), 1971 by Joan Miró**  
`martinlawrence.com` · tier `unverified`  
> 052 - Untitled (Le Lézard aux Plumes d'Or, M.794), 1971 ; Medium: hand-signed lithograph on Kochi Japan paper ; Signature: signed 'Miró' lower right and annotated ...

  - **R** 052 - Untitled (Le Lézard aux Plumes d'Or, M.794), 1971 ; Medium: hand-signed lithograph on Kochi Japan paper ; Signature: signed 'Miró' lower right and annotated ...  
    <sub>names le lezard, lezard, plumes</sub>

**8. Le lézard aux plumes d'or, 1969–1969 - Joan Miró**  
`artnet.com` · tier `market`  
> Le lézard aux plumes d'or, 1969–1969 · Joan Miró · Le lézard aux plumes d'or, 1969–1969 · 41.2 x 56.5 cm. (16.2 x 22.2 in.).

  - **R** Le lézard aux plumes d'or, 1969–1969 · Joan Miró · Le lézard aux plumes d'or, 1969–1969 · 41.2 x 56.5 cm.  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> * *Le Lézard aux plumes d'or* was published in Paris in 19

  - **R** * *Le Lézard aux plumes d'or* was published in Paris in 19  
    <sub>names le lezard, lezard, plumes</sub>


## Seed 11.1 — anchored

**Seed phrase:** `Broder's decision to engage Miró was pivotal`  
**Question asked:** Is this true, and what is the event behind it: "Broder's decision to engage Miró was pivotal"?  
**Query built:** `Broder "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R10 w1 X2

**1. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Printed by Mourlot, Paris; published by Louis Broder, Paris. Catalogue Raisonné & COA: Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers) ...

  - **R** Printed by Mourlot, Paris; published by Louis Broder, Paris.  
    <sub>names louis broder, mourlot, broder</sub>
  - **R** Catalogue Raisonné & COA: Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers) ...  
    <sub>names le lezard, joan miro, plumes</sub>

**2. Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M.  
    <sub>names louis broder, le lezard, joan miro</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**3. Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971 - Artsy**  
`artsy.net` · tier `market`  
> From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …

  - **R** From Christie's, Joan Miró, Joan Miro, Le Lézard aux plumes d'or, Louis Broder, Paris, 1971, The complete set of 15 lithographs in colors, on Rives paper, …  
    <sub>names louis broder, le lezard, joan miro</sub>

**4. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or series)**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**5. Joan Miró's Broder Collection: How One Artist Revolutionized Lithography**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These words ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names le lezard, lezard, plumes</sub>

**6. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Joan Miró. (Barcelona ... Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers), a portfolio published by Louis Broder and printed in Paris by Mourlot.

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers), a portfolio published by Louis Broder and printed in Paris by Mourlot.  
    <sub>names louis broder, le lezard, mourlot</sub>

**7. Joan Miró. Wrapper front from Le Lézard aux plumes d'or ( The Lizard ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Wrapper front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Wrapper front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**8. Le Lézard aux plumes d'or (book) - Joan Miró - Composition Gallery**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 11.2 — evaluative

**Seed phrase:** `blending visual and textual narratives seamlessly`  
**Question asked:** What did Broder's decision to engage Miró actually DO that would justify "blending visual and textual narratives seamlessly"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" abandoned` — *the phrase is ours; hunt the event (abandoned) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R8 w1 X5

**1. Joan Miró - Le Lezard aux Plumes d'Or - National Galleries of Scotland**  
`nationalgalleries.org` · tier `unverified`  
> This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or ... In Paris he abandoned this ...

  - **R** This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** In Paris he abandoned this ...  
    <sub>about someone else (Paris), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names le lezard, lezard, plumes</sub>

**3. Joan Miró , Plate XII, from Le Lezard aux Plumes d'Or (M. 525) | Christie's**  
`christies.com` · tier `market`  
> Plate XII, from Le Lezard aux Plumes d'Or (M. 525) ... Mid-way through printing the project was abandoned by the artist and his publisher ...

  - **R** Plate XII, from Le Lezard aux Plumes d'Or (M.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Mid-way through printing the project was abandoned by the artist and his publisher ...  
    <sub>about someone else (Mid-way), not this stop</sub>

**4. Joan Miró (1893-1983), Untitled, from "Le Lezard aux Plumes d'Or," 1967**  
`johnmoran.com` · tier `unverified`  
> Untitled, from "Le Lezard aux Plumes d'Or," 1967. Lithograph in colors on ... abandoned ("Abandoned Property") and title to it will pass to Moran. Moran ...

  - **R** Untitled, from "Le Lezard aux Plumes d'Or," 1967.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Lithograph in colors on ...  
    <sub>about someone else (Lithograph), not this stop</sub>
  - **X** abandoned ("Abandoned Property") and title to it will pass to Moran.  
    <sub>about someone else (Abandoned Property), not this stop</sub>

**5. Sold at Auction: Joan Miró, Joan Miro "Le Lezard Aux plumes d'Or"**  
`invaluable.com` · tier `market`  
> Bid now on Invaluable: Joan Miro "Le Lezard Aux plumes d'Or" from Helmuth ... abandoned unless prior arrangements have been made. See below. - Refusal ...

  - **R** Bid now on Invaluable: Joan Miro "Le Lezard Aux plumes d'Or" from Helmuth ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - w abandoned unless prior arrangements have been made.  
    <sub>no entity of its own; snippet names le lezard</sub>

**6. Miró, Joan Le Lézard aux plumes d'or. 1967. Set... - Lot 104**  
`gazette-drouot.com` · tier `unverified`  
> An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or. I. Draft 1967: 14 lithographs (361 x 503 mm). Some ...

  - **R** An important record of Miró's work on the lost (and different) first edition of Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Draft 1967: 14 lithographs (361 x 503 mm).  
    <sub>about someone else (Draft), not this stop</sub>

**7. Joan Miró (Spanish, 1893-1983) Le Lezard aux plumes d ... - Bonhams**  
`bonhams.com` · tier `unverified`  
> In 1963, Joan Miro and his publisher Louis Broder embarked on the first edition of "Le Lezard aux plumes d'or", a series of 18 colour lithographs to accompany a ...

  - **R** In 1963, Joan Miro and his publisher Louis Broder embarked on the first edition of "Le Lezard aux plumes d'or", a series of 18 colour lithographs to accompany a ...  
    <sub>names louis broder, le lezard, joan miro</sub>

**8. Museum of Fine Arts, Boston - Facebook**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **active → active** · R1 w0 X0

> Publisher Louis Broder published *Le Lézard aux plumes d’or* as a project where

  - **R** Publisher Louis Broder published *Le Lézard aux plumes d’or* as a project where  
    <sub>names le lezard aux plumes d’or, louis broder, le lezard</sub>


## Seed 12.1 — anchored

**Seed phrase:** `Boris Fridman, a supporter of the art community`  
**Question asked:** Is this true, and what is the event behind it: "Boris Fridman, a supporter of the art community"?  
**Query built:** `Boris Fridman "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R12 w1 X5

**1. JARED'S PICKS FOR 8/22-23 1) Picasso, Miró, Dalí: ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and cover); ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and cover); ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. ✨ JARED'S PICKS FOR 8/22-23✨ 1) Picasso, Miró, Dalí: ...**  
`facebook.com` · tier `reject`  
> Le Lézard aux plumes d'or Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs (including wrapper front and ...

  - **R** Le Lézard aux plumes d'or Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs (including wrapper front and ...  
    <sub>names le lezard, joan miro, plumes</sub>

**3. Fall Signature Night: Picasso, Miró, Dalí**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names louis broder, le lezard, joan miro</sub>

**4. Thank you to Julie and Jeff Kinney! Tune in at 2pm to hear ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**5. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971). Here, the artist's colour lithographs alternate with pages filled with text. Written by Miro ...

  - **R** Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Here, the artist's colour lithographs alternate with pages filled with text.  
    <sub>about someone else (Here), not this stop</sub>

**6. Virtual Member Lecture: Picasso, Miró, Dalí**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ... Gift of Boris Fridman. © Successió Miró / Artists Rights Society (ARS), New ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Gift of Boris Fridman.  
    <sub>names gift of boris fridman, boris fridman, fridman</sub>
  - **R** © Successió Miró / Artists Rights Society (ARS), New ...  
    <sub>names miro</sub>

**7. paper title**  
`atlantis-press.com` · tier `unverified`  
> Feathers” (“Le Lézard aux plumes d'or”). Miró wrote the. 1. The true name by Yvan Goll (1891-1950) is Isaac Lang. poetic surreal text ...

  - **R** Feathers” (“Le Lézard aux plumes d'or”).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** The true name by Yvan Goll (1891-1950) is Isaac Lang.  
    <sub>about someone else (Yvan Goll), not this stop</sub>
  - w poetic surreal text ...  
    <sub>no entity of its own; snippet names le lezard</sub>

**8. Unbound at the Museum of Fine Arts, Boston 2) DTF St. ...**  
`facebook.com` · tier `reject`  
> If you ever miss us on the radio, you can find us on Spotify, Apple Podcasts, or the GBH website! Le Lézard aux plumes d'or Joan Miró ...

  - **X** If you ever miss us on the radio, you can find us on Spotify, Apple Podcasts, or the GBH website!  
    <sub>about someone else (Spotify), not this stop</sub>
  - **R** Le Lézard aux plumes d'or Joan Miró ...  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Boris Fridman is an art collector and curator specializing in 20th-century *livres d'artiste* (artists' books) [Art Focus Now, 2019]. 
> 
> The copy of

  - **R** Boris Fridman is an art collector and curator specializing in 20th-century *livres d'artiste* (artists' books) [Art Focus Now, 2019].  
    <sub>names boris fridman, fridman, boris</sub>


## Seed 12.2 — anchored

**Seed phrase:** `Boston's holdings`  
**Question asked:** Is this true, and what is the event behind it: "Boston's holdings"?  
**Query built:** `Boston "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R10 w1 X4

**1. Joan Miró (1893-1983); Le Lézard aux Plumes d'Or - Bonhams**  
`bonhams.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk. 148), 1971. The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...

  - **R** Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **R** The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...  
    <sub>names miro</sub>

**2. Museum of Fine Arts, Boston - Facebook**  
`facebook.com` · tier `reject`  
> ... Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...

  - **R** Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (detail, 1971), illustrated book with forty color lithographs (including wrapper ...  
    <sub>names le lezard, joan miro, plumes</sub>

**3. JARED'S PICKS FOR 8/22-23   1) Picasso, Miró, Dalí: Unbound at the ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and cover); ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and cover); ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**4. Fall Signature Night: Picasso, Miró, Dalí | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names louis broder, le lezard, joan miro</sub>

**5. Le lézard aux plumes d'or 1 - Gallerease**  
`static.gallerease.com` · tier `unverified`  
> Interested in buying Le lézard aux plumes d'or 1? This exclusive work along with other unique curated artworks can only be found here!

  - **R** Interested in buying Le lézard aux plumes d'or 1?  
    <sub>names le lezard, lezard, plumes</sub>
  - w This exclusive work along with other unique curated artworks can only be found here!  
    <sub>no entity of its own; snippet names le lezard</sub>

**6. "Picasso, Miró, Dalí: Unbound" at the Museum of Fine Arts Boston - Air Mail**  
`airmail.news` · tier `unverified`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ... Boston is now presenting a focused selection that includes Juan Gris ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **X** Boston is now presenting a focused selection that includes Juan Gris ...  
    <sub>about someone else (Boston), not this stop</sub>

**7. Miró's luminous lithography In the late 1940s, Joan Miró published ...**  
`instagram.com` · tier `reject`  
> : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front ...

  - **R** : Joan Miró (Spanish, 1893–1983), "Le Lézard aux plumes d'or" (1971), illustrated book with forty color lithographs (including wrapper front ...  
    <sub>names le lezard, joan miro, plumes</sub>

**8. Auction Results & Gallery Prices - Joan Miró - Mutual Art**  
`mutualart.com` · tier `market`  
> Artworks for Sale ; Le Lézard aux plumes d'or, 1969. Ask for Availability and Price ; Le Chien Aboyant À La Lune, 1956. Ask for Availability and Price ; litografie ...

  - **R** Artworks for Sale ; Le Lézard aux plumes d'or, 1969.  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Ask for Availability and Price ; Le Chien Aboyant À La Lune, 1956.  
    <sub>about someone else (Availability), not this stop</sub>
  - **X** Ask for Availability and Price ; litografie ...  
    <sub>about someone else (Availability), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R2 w0 X0

> The Museum of Fine Arts, Boston holds Joan Miró's 1971 illustrated book *Le Lézard aux plumes d’or (The Lizard with Golden Feathers)* as a gift from Boris Fridman. The work is featured in the museum's exhibition *Picasso, Miró, Dalí: Unbound*.

  - **R** The Museum of Fine Arts, Boston holds Joan Miró's 1971 illustrated book *Le Lézard aux plumes d’or (The Lizard with Golden Feathers)* as a gift from Boris Fridman.  
    <sub>names le lezard aux plumes d’or, boris fridman, joan miro</sub>
  - **R** The work is featured in the museum's exhibition *Picasso, Miró, Dalí: Unbound*.  
    <sub>names miro</sub>


## Seed 13.1 — anchored

**Seed phrase:** `Fridman's contribution ensures`  
**Question asked:** Is this true, and what is the event behind it: "Fridman's contribution ensures"?  
**Query built:** `Fridman "Le Lézard aux plumes d’or" Joan Miró` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R12 w0 X3

**1. JARED'S PICKS FOR 8/22-23   1) Picasso, Miró, Dalí: Unbound at the ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and cover); ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and cover); ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**2. Fall Signature Night: Picasso, Miró, Dalí | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971.  
    <sub>names louis broder, le lezard, joan miro</sub>

**3. JARED'S PICKS FOR 8/22-23   1) Picasso, Miró, Dalí: Unbound at the ...**  
`facebook.com` · tier `reject`  
> Le Lézard aux plumes d'or Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs (including wrapper front and ...

  - **R** Le Lézard aux plumes d'or Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs (including wrapper front and ...  
    <sub>names le lezard, joan miro, plumes</sub>

**4. Framed Joan Miró 'Le Lézard aux Plumes d'Or' Art Print | eBay**  
`ebay.com` · tier `unverified`  
> This is a framed art print of Joan Miró's 'Le Lézard aux Plumes d'Or,' featuring Miró's signature abstract style with bold colors and whimsical forms.

  - **R** This is a framed art print of Joan Miró's 'Le Lézard aux Plumes d'Or,' featuring Miró's signature abstract style with bold colors and whimsical forms.  
    <sub>names le lezard, joan miro, plumes</sub>

**5. Thank you to Julie and Jeff Kinney! Tune in at 2pm to hear all about ...**  
`instagram.com` · tier `reject`  
> Le Lézard aux plumes d'or. Joan Miró (Spanish, 1893–1983) 1971. Illustrated book with forty color lithographs (including wrapper front and ...

  - **R** Le Lézard aux plumes d'or.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Joan Miró (Spanish, 1893–1983) 1971.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Illustrated book with forty color lithographs (including wrapper front and ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**6. Virtual Member Lecture: Picasso, Miró, Dalí**  
`mfa.org` · tier `tier1`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ... Gift of Boris Fridman. © Successió Miró / Artists Rights Society (ARS), New ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) ...  
    <sub>names le lezard, joan miro, plumes</sub>
  - **R** Gift of Boris Fridman.  
    <sub>names gift of boris fridman, boris fridman, fridman</sub>
  - **R** © Successió Miró / Artists Rights Society (ARS), New ...  
    <sub>names miro</sub>

**7. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971). Here, the artist's colour lithographs alternate with pages filled with text. Written by Miro ...

  - **R** Another such example is Miro's "Le Lezard aux Plumes d'Or" (1971).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Here, the artist's colour lithographs alternate with pages filled with text.  
    <sub>about someone else (Here), not this stop</sub>

**8. Public Auction Sale: Collect: Prints & Multiples - Chicago, IL - AuctionZip**  
`auctionzip.com` · tier `unverified`  
> Joan Miró (Spanish, 1893-1983) Le Lézard aux plumes d'or: one plate, 1971 lithograph in colors on Japan Nacre signed and numbered E.A. 10/10 in ...

  - **R** Joan Miró (Spanish, 1893-1983) Le Lézard aux plumes d'or: one plate, 1971 lithograph in colors on Japan Nacre signed and numbered E.A.  
    <sub>names le lezard, joan miro, plumes</sub>

### GEMINI (grounded) — kind **active → active** · R1 w0 X0

> Joan Miró’s illustrated book *Le Lézard aux plumes d’or* (1

  - **R** Joan Miró’s illustrated book *Le Lézard aux plumes d’or* (1  
    <sub>names le lezard aux plumes d’or, le lezard, joan miro</sub>


## Seed 13.2 — evaluative

**Seed phrase:** `visitors can appreciate the intricate dance between lithography`  
**Question asked:** What did Fridman's contribution actually DO that would justify "visitors can appreciate the intricate dance between lithography"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" destroyed` — *the phrase is ours; hunt the event (destroyed) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R11 w1 X1

**1. Le Lézard aux plumes d'or, 1st version, plate XV**  
`galeriearenthon.com` · tier `unverified`  
> First version of the fifteenth plate realized for his album "Le Lézard aux plumes d'or". Condition : Very good condition.

  - **R** First version of the fifteenth plate realized for his album "Le Lézard aux plumes d'or".  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** Condition : Very good condition.  
    <sub>about someone else (Condition), not this stop</sub>

**2. Le Lézard aux Plumes d'Or by Joan Miró, 1971 | Lithographs**  
`artsper.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or, Plate X is a beautiful color lithograph on Japanese paper, realized in 1971 by the Spanish Surrealist artist Joan Miró (Montroing, ...

  - **R** Le Lézard aux Plumes d'Or, Plate X is a beautiful color lithograph on Japanese paper, realized in 1971 by the Spanish Surrealist artist Joan Miró (Montroing, ...  
    <sub>names le lezard, joan miro, plumes</sub>

**3. Le lézard aux plumes d'or I (1967) by Joan Miró - For Sale**  
`artsy.net` · tier `market`  
> In 1967 Miró executed a series of lithographs to illustrate his poem "Le lézard aux plumes d'or". For technical reasons, Miró decided to destroy the lithographs ...

  - **R** In 1967 Miró executed a series of lithographs to illustrate his poem "Le lézard aux plumes d'or".  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** For technical reasons, Miró decided to destroy the lithographs ...  
    <sub>names miro</sub>

**4. Composition pour 'Le lézard aux plumes d'or'**  
`christies.com` · tier `market`  
> Joan Miró (1893-1983) Composition pour 'Le lézard aux plumes d'or' signed and dated 'Miró III/64' (lower left) oil and wax crayon on paper 14 x 19 7/8 in.

  - **R** Joan Miró (1893-1983) Composition pour 'Le lézard aux plumes d'or' signed and dated 'Miró III/64' (lower left) oil and wax crayon on paper 14 x 19 7/8 in.  
    <sub>names le lezard, joan miro, plumes</sub>

**5. Martin Lawrence Galleries**  
`facebook.com` · tier `reject`  
> ... (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on ... The works must be conceived with fire in the soul but executed with clinical ...

  - **R** (Le Lézard aux Plumes d'Or, M.794), 1971 hand-signed lithograph on ...  
    <sub>names le lezard, lezard, plumes</sub>
  - w The works must be conceived with fire in the soul but executed with clinical ...  
    <sub>no entity of its own; snippet names le lezard</sub>

**6. Le lézard aux plumes d'or II - Joan Miró**  
`singulart.com` · tier `unverified`  
> In 1967 Miró executed a series of lithographs to illustrate his poem "Le lézard aux plumes d'or". Edition of 20. For technical reasons, Miró decided to destroy ...

  - **R** In 1967 Miró executed a series of lithographs to illustrate his poem "Le lézard aux plumes d'or".  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** For technical reasons, Miró decided to destroy ...  
    <sub>names miro</sub>

**7. UNTITLED from Le Lezard aux Plumes d'Or, 1971**  
`artsy.net` · tier `market`  
> One of fifteen color lithographs illustrating the text Le Lezard aux Plumes d'Or, a series of the artist's own poems. Published by Louis Broder, Paris; printed ...

  - **R** One of fifteen color lithographs illustrating the text Le Lezard aux Plumes d'Or, a series of the artist's own poems.  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** Published by Louis Broder, Paris; printed ...  
    <sub>names louis broder, broder, louis</sub>

**8. Miró Joan | La destruction du miroir | Compare similar artworks**  
`mutualart.com` · tier `market`  
> La destruction du miroir · Le lézard aux plumes d'or , 1971 · Le Lezarde aux lumes d'or · Le courtisan grotesque , 1974 · Le Lézard aux Plumes d'Or. , 1971 · Le ...

  - **R** La destruction du miroir · Le lézard aux plumes d'or , 1971 · Le Lezarde aux lumes d'or · Le courtisan grotesque , 1974 · Le Lézard aux Plumes d'Or.  
    <sub>names le lezard, lezard, plumes</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Boris Fridman's contribution was donating the copy of Joan Miró's *Le Lézard aux plumes

  - **R** Boris Fridman's contribution was donating the copy of Joan Miró's *Le Lézard aux plumes  
    <sub>names boris fridman, le lezard, joan miro</sub>


## Seed 13.3 — evaluative

**Seed phrase:** `offering a unique tactile experience and inviting viewers to ponder the narrative beyond the page`  
**Question asked:** What did Fridman's contribution actually DO that would justify "offering a unique tactile experience and inviting viewers to ponder the narrative beyond the page"? If nothing, cut the phrase.  
**Query built:** `Joan Miró "Le Lézard aux plumes d’or" refused` — *the phrase is ours; hunt the event (refused) behind it*

### SERPER — 8 results · kind **active → active** · R11 w1 X1

**1. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or series)**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, lezard, plumes</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names le lezard, lezard, plumes</sub>

**3. Joan Miró (1893-1983); Le Lézard aux Plumes d'Or - Bonhams**  
`bonhams.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk. 148), 1971. The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...

  - **R** Le Lézard aux Plumes d'Or (Mourlot 789-828, Cramer bk.  
    <sub>names le lezard, mourlot, lezard</sub>
  - **R** The complete set of 15 lithographs in colors on Rives paper with Miró watermark, ...  
    <sub>names miro</sub>

**4. Le lézard aux plumes d'or, 1969–1969 - Joan Miró - Artnet**  
`artnet.com` · tier `market`  
> Joan Miró · Le lézard aux plumes d'or, 1969–1969 · 41.2 x 56.5 cm. (16.2 x 22.2 in.).

  - **R** Joan Miró · Le lézard aux plumes d'or, 1969–1969 · 41.2 x 56.5 cm.  
    <sub>names le lezard, joan miro, plumes</sub>

**5. Joan Miró's Broder Collection: How One Artist Revolutionized Lithography**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These words ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names le lezard, lezard, plumes</sub>

**6. Le Lézard aux Plumes d'Or by Joan Mirò at wallector.comwallector.com**  
`wallector.com` · tier `unverified`  
> "Le Lézard aux Plumes d'Or" is an original hand-signed and numbered lithograph realized by Joan Miró in 1971. This is an edition of 80 prints.

  - **R** "Le Lézard aux Plumes d'Or" is an original hand-signed and numbered lithograph realized by Joan Miró in 1971.  
    <sub>names le lezard, joan miro, plumes</sub>
  - w This is an edition of 80 prints.  
    <sub>no entity of its own; snippet names le lezard</sub>

**7. Le Lezard Aux Plumes D'Or, 1967 by Joan Miro - DENIS BLOCH FINE ART**  
`denisbloch.com` · tier `unverified`  
> Le Lezard Aux Plumes D'Or (M.458), 1967 by Joan Miro is a colored lithograph print signed in the lower right and numbered in the lower left in an edition of ...

  - **R** Le Lezard Aux Plumes D'Or (M.458), 1967 by Joan Miro is a colored lithograph print signed in the lower right and numbered in the lower left in an edition of ...  
    <sub>names le lezard, joan miro, plumes</sub>

**8. Museum of Fine Arts, Boston - Facebook**  
`facebook.com` · tier `reject`  
> ... Le Lézard aux plumes d'or" (detail, 1971), illustrated book with ... ~ Joan Miró rejected the constraints of traditional painting ...

  - **R** Le Lézard aux plumes d'or" (detail, 1971), illustrated book with ...  
    <sub>names le lezard, lezard, plumes</sub>
  - **R** ~ Joan Miró rejected the constraints of traditional painting ...  
    <sub>names joan miro, joan, miro</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Boris Fridman's contribution to *Le Lézard aux plumes d’or* at the

  - **R** Boris Fridman's contribution to *Le Lézard aux plumes d’or* at the  
    <sub>names le lezard aux plumes d’or, boris fridman, le lezard</sub>


---

# Au Soleil du Plafond


## Seed 2.1 — anchored

**Seed phrase:** `Pierre Reverdy, the French poet linked to Surrealism`  
**Question asked:** Is this true, and what is the event behind it: "Pierre Reverdy, the French poet linked to Surrealism"?  
**Query built:** `Pierre Reverdy "Au Soleil du Plafond" Juan Gris` — *verify the named claim*

### SERPER — 8 results · kind **eventful → eventful** · R11 w0 X2

**1. Gris and Reverdy's Au soleil du plafond | AraderBooks**  
`araderbooks.com` · tier `unverified`  
> Au soleil du plafond was José Victoriano González-Pérez (pseud. Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...

  - **R** Au soleil du plafond was José Victoriano González-Pérez (pseud.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...  
    <sub>names juan gris, juan, gris</sub>

**2. Designed by Juan Gris - Au Soleil du Plafond**  
`metmuseum.org` · tier `tier1`  
> Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)

  - **R** Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**3. Pierre Reverdy. Au soleil du plafond Paris, Tériade … (1955) by Juan Gris**  
`artsy.net` · tier `market`  
> Juan Gris. ,. Pierre Reverdy. Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery. Zürich ; High auction record. £34.8m, Christie's, 2014.

  - **R** Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Zürich ; High auction record.  
    <sub>about someone else (Zürich), not this stop</sub>
  - **X** £34.8m, Christie's, 2014.  
    <sub>about someone else (Christie's), not this stop</sub>

**4. Au Soleil du Plafond - Pierre Reverdy - Bauman Rare Books**  
`baumanrarebooks.com` · tier `unverified`  
> Au Soleil du Plafond rare book for sale. This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.

  - **R** Au Soleil du Plafond rare book for sale.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>

**5. Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955**  
`christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955 the complete set of 11 lithographs in colors, 1916-17, ...

  - **R** AFTER JUAN GRIS (1887-1927) Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955 the complete set of 11 lithographs in colors, 1916-17, ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**6. Au soleil du plafond portfolio of 11 wcolophon and text by Pierre ...**  
`artnet.com` · tier `market`  
> Juan Gris · Au soleil du plafond (portfolio of 11 w/colophon and text by Pierre Reverdy) · 43 x 33 cm. (16.9 x 13 in.).

  - **R** Juan Gris · Au soleil du plafond (portfolio of 11 w/colophon and text by Pierre Reverdy) · 43 x 33 cm.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**7. Juan Gris, La Pipe (Kahnweiler 1969), Au Soleil du Plafond, Limited ...**  
`in.pinterest.com` · tier `unverified`  
> Set of 11 Works by Juan Gris: Pierre Reverdy, Au Soleil du Plafond,. More to explore. Etsy. Juan Gris, La Pipe (Kahnweiler 1969), Au Soleil du Plafond, Limited ...

  - **R** Set of 11 Works by Juan Gris: Pierre Reverdy, Au Soleil du Plafond,.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **R** Juan Gris, La Pipe (Kahnweiler 1969), Au Soleil du Plafond, Limited ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**8. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> The statement is true, as Pierre Reverdy was a French poet closely associated with avant-garde movements including Cub

  - **R** The statement is true, as Pierre Reverdy was a French poet closely associated with avant-garde movements including Cub  
    <sub>names pierre reverdy, reverdy, pierre</sub>


## Seed 2.2 — evaluative

**Seed phrase:** `revolutionized the concept of the book as art`  
**Question asked:** What did Juan Gris and Pierre Reverdy actually DO that would justify "revolutionized the concept of the book as art"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" delayed` — *the phrase is ours; hunt the event (delayed) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R14 w0 X4

**1. Juan Gris Sold at Auction Prices**  
`invaluable.com` · tier `market`  
> ... AU SOLEIL DU PLAFOND 22 litografie di Gris. Edizione DeLuxe. Juan Gris e Pierre Reverdy. Parigi, Teriade 1955. cm 43x33. Portfolio con 11+11 litografie ...

  - **R** AU SOLEIL DU PLAFOND 22 litografie di Gris.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris e Pierre Reverdy.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Parigi, Teriade 1955.  
    <sub>names teriade</sub>
  - **X** Portfolio con 11+11 litografie ...  
    <sub>about someone else (Portfolio), not this stop</sub>

**2. Au soleil du plafond**  
`artvee.com` · tier `unverified`  
> View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee. ... Late 1913 or early 1914 they lived together at the Bateau-Lavoir ...

  - **R** View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Late 1913 or early 1914 they lived together at the Bateau-Lavoir ...  
    <sub>about someone else (Late), not this stop</sub>

**3. JUAN GRIS (1887-1927), Le moulin à café**  
`christies.com` · tier `market`  
> It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond. Other gouaches include Compotier, now part of the Leonard A. Lauder ...

  - **R** It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Other gouaches include Compotier, now part of the Leonard A.  
    <sub>about someone else (Other), not this stop</sub>

**4. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>

**5. After Juan Gris**  
`mutualart.com` · tier `market`  
> Recent Lots by Juan Gris. 12 Arbeiten. In: Au Soleil du Plafond - Juan Gris. -23%. below mid-estimate. Jeschke ...

  - **R** Recent Lots by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** In: Au Soleil du Plafond - Juan Gris.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**6. Compotier – henripeyrefi**  
`henripeyrefi.ws.gc.cuny.edu` · tier `tier1`  
> It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond. In this book ...

  - **R** It was only many years later in 1955 that Reverdy published a scaled-back version of their original plans: Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**7. Mary Ann Caws on Pierre Reverdy**  
`poetrysociety.org` · tier `unverified`  
> In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...

  - **R** In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**8. Pot de Fleurs. From au Soleil du Plafond. First edition. (Soft ...**  
`abebooks.com` · tier `market`  
> Pot de Fleurs. From au Soleil du Plafond. First edition. Publisher: Paris: Tériade Editeur. Publication Date: 1955; Binding: Soft cover; Condition ...

  - **R** From au Soleil du Plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Publisher: Paris: Tériade Editeur.  
    <sub>names teriade</sub>
  - **X** Publication Date: 1955; Binding: Soft cover; Condition ...  
    <sub>about someone else (Publication Date), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Juan Gris and Pierre Reverdy conceived the project around 1916

  - **R** Juan Gris and Pierre Reverdy conceived the project around 1916  
    <sub>names pierre reverdy, juan gris, reverdy</sub>


## Seed 2.3 — evaluative

**Seed phrase:** `exemplifying the collaborative spirit that defines the MFA's exhibition`  
**Question asked:** What did Juan Gris and Pierre Reverdy actually DO that would justify "exemplifying the collaborative spirit that defines the MFA's exhibition"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" history` — *the phrase is ours; hunt the event (history) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R11 w1 X3

**1. Designed by Juan Gris - Au Soleil du Plafond**  
`metmuseum.org` · tier `tier1`  
> Au Soleil du Plafond ... This book was originally planned by L. Rosenberg ca. 1916-1917. Gris died in 1927, having finished only half of the intended ...

  - **R** Au Soleil du Plafond ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w This book was originally planned by L.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** Gris died in 1927, having finished only half of the intended ...  
    <sub>names gris</sub>

**2. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...

  - **R** Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. AFTER JUAN GRIS (1887-1927), Au Soleil du Plafond**  
`onlineonly.christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...

  - **R** AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**4. 263 - Au Soleil du Plafond - GRIS, Juan (b.1887-1927)**  
`portal.sds.ox.ac.uk` · tier `tier1`  
> Book ID. 263 ; Title Of Work. Au Soleil du Plafond ; Artist Name. GRIS, Juan (b.1887-1927) ; OLIS Call number ?? ; Provenance: Old Printed Catalogue ...

  - **R** Au Soleil du Plafond ; Artist Name.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** GRIS, Juan (b.1887-1927) ; OLIS Call number ??  
    <sub>names juan, gris</sub>
  - **X** ; Provenance: Old Printed Catalogue ...  
    <sub>about someone else (Provenance), not this stop</sub>

**5. Au soleil du plafond by Gris, Juan; Pierre Reverdy**  
`abebooks.com` · tier `market`  
> Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.

  - **R** Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>

**6. Exposición Juan Gris : au soleil du plafond**  
`facebook.com` · tier `reject`  
> Exposición Juan Gris : au soleil du plafond · Public · Hosted by Galería La Aurora · Thursday 7 September 2023 at 12:00 CEST · Plaza de la Aurora, 30001 Murcia ( ...

  - **R** Exposición Juan Gris : au soleil du plafond · Public · Hosted by Galería La Aurora · Thursday 7 September 2023 at 12:00 CEST · Plaza de la Aurora, 30001 Murcia ( ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. Juan Gris: Au soleil du plafond | Buy prints | engravings**  
`galerialaaurora.com` · tier `unverified`  
> Juan Gris , buy and sale of illustrated books ... History · La Aurora in the press · what's graphic ... Juan GrisJuan Gris: Au soleil du plafond 24Book.

  - **R** Juan Gris , buy and sale of illustrated books ...  
    <sub>names juan gris, juan, gris</sub>
  - **X** History · La Aurora in the press · what's graphic ...  
    <sub>about someone else (History), not this stop</sub>
  - **R** Juan GrisJuan Gris: Au soleil du plafond 24Book.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**8. Reproduction of the painting Au soleil du plafond - Juan Gris**  
`artemlegrand.com` · tier `unverified`  
> Reproduction of the painting Au soleil du plafond - Juan Gris ; Free shipping on orders over €45. At your home within 3 to 8 business days ; Money-back guarantee.

  - **R** Reproduction of the painting Au soleil du plafond - Juan Gris ; Free shipping on orders over €45.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** At your home within 3 to 8 business days ; Money-back guarantee.  
    <sub>about someone else (Money-back), not this stop</sub>

### GEMINI (grounded) — kind **active → active** · R3 w0 X1

> Around 1916–1917, Juan Gris and Pierre Reverdy planned an artist's book in which Gris was to create illustrations corresponding directly to twenty of Reverdy's poems. 
> 
> The Museum of Fine Arts, Boston notes that the artist and writer partnered at the project's inception to devise the images and words together in harmony. 
> 
> Gris completed eleven artworks for the planned collaboration before his death in 1927. 
> 
> Reverdy later worked with publisher Tériade to publish the project as a *livre d'artiste* in 1955, combining his texts with color lithographs based on Gris's completed designs.

  - **R** Around 1916–1917, Juan Gris and Pierre Reverdy planned an artist's book in which Gris was to create illustrations corresponding directly to twenty of Reverdy's poems.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **X** The Museum of Fine Arts, Boston notes that the artist and writer partnered at the project's inception to devise the images and words together in harmony.  
    <sub>about someone else (The Museum), not this stop</sub>
  - **R** Gris completed eleven artworks for the planned collaboration before his death in 1927.  
    <sub>names gris</sub>
  - **R** Reverdy later worked with publisher Tériade to publish the project as a *livre d'artiste* in 1955, combining his texts with color lithographs based on Gris's completed designs.  
    <sub>names teriade, reverdy, gris</sub>


## Seed 3.1 — evaluative

**Seed phrase:** `Gris's innovative vision`  
**Question asked:** What did Gris actually DO that would justify "innovative vision"? If nothing, cut the phrase.  
**Query built:** `Gris "Au Soleil du Plafond" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **eventful → inert** · R11 w2 X6

**1. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> ... Gris, Au soleil du plafond (In the Ceiling Sun). Text by Pierre Reverdy ... When the artist died the following year, the lithographs and text remained unfinished.

  - **R** Gris, Au soleil du plafond (In the Ceiling Sun).  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Text by Pierre Reverdy ...  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **X** When the artist died the following year, the lithographs and text remained unfinished.  
    <sub>about someone else (When), not this stop</sub>

**2. Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after) For ...**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. GRIS (JUAN) REVERDY (PAUL) Au soleil du plafond ... - Bonhams**  
`bonhams.com` · tier `unverified`  
> GRIS (JUAN). REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955. Fine Books, Manuscripts ...

  - **R** REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Fine Books, Manuscripts ...  
    <sub>about someone else (Fine Books), not this stop</sub>

**4. Juan Gris — Artworks, Sold Prices & Market Data - Appraisily**  
`appraisily.com` · tier `unverified`  
> Juan Gris shows deep auction liquidity with 368 tracked lots. Median realized sale is around $15,444. Category concentration is still broad or sparse. Last 12 ...

  - **R** Juan Gris shows deep auction liquidity with 368 tracked lots.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Median realized sale is around $15,444.  
    <sub>about someone else (Median), not this stop</sub>
  - **X** Category concentration is still broad or sparse.  
    <sub>about someone else (Category), not this stop</sub>

**5. Transforming the Horizon: Reverdy's World War I - jstor**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris: Flammarion, 1980). C?p Cette ?motion appel?e po?sie (Paris: Flammarion, 1974). Nord-Sud Nord-Sud, Self ...

  - **R** Asp Au soleil du plafond et autres po?mes (Paris: Flammarion, 1980).  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **X** C?p Cette ?motion appel?e po?sie (Paris: Flammarion, 1974).  
    <sub>about someone else (Cette), not this stop</sub>
  - **X** Nord-Sud Nord-Sud, Self ...  
    <sub>about someone else (Nord-Sud Nord-Sud), not this stop</sub>

**6. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ... incomplete circle from left to right. Gris transitioned from the Nature ...

  - **R** Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w incomplete circle from left to right.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** Gris transitioned from the Nature ...  
    <sub>names gris</sub>

**7. Pierre reverdy hi-res stock photography and images - Alamy**  
`alamy.com` · tier `unverified`  
> Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916. RM 3F4EGGY ... unfinished at the time of Gris's death. A reduced version, with color ...

  - **R** Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** unfinished at the time of Gris's death.  
    <sub>names gris</sub>
  - w A reduced version, with color ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**8. Living Still Life | John Golding | The New York Review of Books**  
`nybooks.com` · tier `unverified`  
> ... Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later). These small ...

  - **R** Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Juan Gris partnered directly with poet Pierre Reverdy to develop lithographs and

  - **R** Juan Gris partnered directly with poet Pierre Reverdy to develop lithographs and  
    <sub>names pierre reverdy, juan gris, reverdy</sub>


## Seed 3.2 — evaluative

**Seed phrase:** `Reverdy's poetic prowess`  
**Question asked:** What did Reverdy actually DO that would justify "poetic prowess"? If nothing, cut the phrase.  
**Query built:** `Reverdy "Au Soleil du Plafond" refused` — *the phrase is ours; hunt the event (refused) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R12 w2 X2

**1. Mary Ann Caws on Pierre Reverdy - Poetry Society of America**  
`poetrysociety.org` · tier `unverified`  
> In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond ... refused to publish anything during ...

  - **R** In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - w refused to publish anything during ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**2. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>

**3. Transforming the Horizon: Reverdy's World War I - jstor**  
`jstor.org` · tier `tier2`  
> works by Reverdy will appear in the text using the following abbreviations: Asp Au soleil du plafond et autres po?mes (Paris: Flammarion, 1980). C?p Cette ...

  - **R** works by Reverdy will appear in the text using the following abbreviations: Asp Au soleil du plafond et autres po?mes (Paris: Flammarion, 1980).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**4. Pierre Reverdy - Reverdy, Pierre; Caws, Mary Ann; Ashbery, John ...**  
`obergassbuecher.ch` · tier `unverified`  
> E-Book , EPUB / DRM Adobe (E-Book), Reverdy, Pierre, 184 Seiten. ... During the Nazi occupation, he joined the Resistance, refused ... Au soleil du plafond. La ...

  - **R** E-Book , EPUB / DRM Adobe (E-Book), Reverdy, Pierre, 184 Seiten.  
    <sub>names reverdy, pierre</sub>
  - **X** During the Nazi occupation, he joined the Resistance, refused ...  
    <sub>about someone else (During), not this stop</sub>
  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**5. (PDF) Textual Spaces: The Poetry of Pierre Reverdy - ResearchGate**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**6. International Postwar Gris, Juan 12 works. In: *Au S... - 87825153 ...**  
`interencheres.com` · tier `unverified`  
> - The portfolio *Au Soleil du Plafond* stems from a collaboration between Juan Gris and the poet Pierre Reverdy, which was conceived as early as 1925 but ...

  - **R** - The portfolio *Au Soleil du Plafond* stems from a collaboration between Juan Gris and the poet Pierre Reverdy, which was conceived as early as 1925 but ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**7. [PDF] Untitled - Borges Center**  
`borges.pitt.edu` · tier `tier1`  
> “Reverdy et l' art plastique,” Mercure de France 344 (1962): 42–43. Juan Gris. Paris: Gallimard, 1946. Reverdy, Pierre. Au Soleil du plafond et autres poèmes.

  - **R** “Reverdy et l' art plastique,” Mercure de France 344 (1962): 42–43.  
    <sub>names reverdy</sub>
  - **X** Paris: Gallimard, 1946.  
    <sub>about someone else (Paris), not this stop</sub>
  - **R** Au Soleil du plafond et autres poèmes.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**8. Constat du discontinu, pratique de la discontinuité dans l'œuvre poétique ...**  
`persee.fr` · tier `unverified`  
> Pierre Reverdy, La Meule de soleil, 1915-1920, dans Au soleil du plafond et autres poèmes, Paris, Flammarion, 1 980, p. 99. ↵. 5 ...

  - **R** Pierre Reverdy, La Meule de soleil, 1915-1920, dans Au soleil du plafond et autres poèmes, Paris, Flammarion, 1 980, p.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Pierre Reverdy authored the poems for *Au Soleil du Plafond* around 1916

  - **R** Pierre Reverdy authored the poems for *Au Soleil du Plafond* around 1916  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>


## Seed 3.3 — evaluative

**Seed phrase:** `resulting in a unique interlacing of images and words`  
**Question asked:** What did The project actually DO that would justify "resulting in a unique interlacing of images and words"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **inert → inert** · R12 w1 X3

**1. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...

  - **R** Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**2. Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after) For ...**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. Juan Gris — Artworks, Sold Prices & Market Data - Appraisily**  
`appraisily.com` · tier `unverified`  
> Juan Gris shows deep auction liquidity with 368 tracked lots. Median realized sale is around $15,444. Category concentration is still broad or sparse. Last 12 ...

  - **R** Juan Gris shows deep auction liquidity with 368 tracked lots.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Median realized sale is around $15,444.  
    <sub>about someone else (Median), not this stop</sub>
  - **X** Category concentration is still broad or sparse.  
    <sub>about someone else (Category), not this stop</sub>

**4. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris and Reverly ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** Pierrots, Drawings, Books, etc Gris and Reverly ...  
    <sub>names gris</sub>

**5. GRIS (JUAN) REVERDY (PAUL) Au soleil du plafond ... - Bonhams**  
`bonhams.com` · tier `unverified`  
> GRIS (JUAN). REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955. Fine Books, Manuscripts ...

  - **R** REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Fine Books, Manuscripts ...  
    <sub>about someone else (Fine Books), not this stop</sub>

**6. Pierre reverdy hi-res stock photography and images - Alamy**  
`alamy.com` · tier `unverified`  
> Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916. RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...

  - **R** Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. Living Still Life | John Golding | The New York Review of Books**  
`nybooks.com` · tier `unverified`  
> ... Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later). These small ...

  - **R** Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**8. Transforming the Horizon: Reverdy's World War I - jstor**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris ... be seen as the frontispiece to Douglas Cooper's Juan Gris: Catalogue raisonn? ... leaves the tableau unfinished ...

  - **R** Asp Au soleil du plafond et autres po?mes (Paris ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** be seen as the frontispiece to Douglas Cooper's Juan Gris: Catalogue raisonn?  
    <sub>names juan gris, juan, gris</sub>
  - w leaves the tableau unfinished ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Juan Gris and poet Pierre Reverdy collaborated directly starting around 1916 to create matching visual

  - **R** Juan Gris and poet Pierre Reverdy collaborated directly starting around 1916 to create matching visual  
    <sub>names pierre reverdy, juan gris, reverdy</sub>


## Seed 4.1 — evaluative

**Seed phrase:** `Gris's ability to transform visual art`  
**Question asked:** What did Gris actually DO that would justify "ability to transform visual art"? If nothing, cut the phrase.  
**Query built:** `Gris "Au Soleil du Plafond" destroyed` — *the phrase is ours; hunt the event (destroyed) behind it*

### SERPER — 8 results · kind **eventful → inert** · R11 w0 X8

**1. Juan Gris, Au solei du plafond La pipe, 1955, Lithograph**  
`centraldoaposentado.com` · tier `unverified`  
> Juan Gris ... Juan Gris, The Pipe, from Au Soleil du Plafond, 1955 (after display ... Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine.

  - **R** Juan Gris, The Pipe, from Au Soleil du Plafond, 1955 (after display ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine.  
    <sub>about someone else (Dora Szampanier), not this stop</sub>

**2. Juan Gris, Au solei du plafond Guitare, 1955, Lithograph**  
`browswithlea.com` · tier `unverified`  
> Juan Gris, Au solei du ... Juan Gris | Au Soleil du plafond (1955) | MutualArt display picture 1 ... Related Searches. Dora Szampanier, Etching of destroyed ...

  - **R** Juan Gris, Au solei du ...  
    <sub>names juan gris, juan, gris</sub>
  - **R** Juan Gris | Au Soleil du plafond (1955) | MutualArt display picture 1 ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Dora Szampanier, Etching of destroyed ...  
    <sub>about someone else (Dora Szampanier), not this stop</sub>

**3. Au soleil du plafond**  
`artvee.com` · tier `unverified`  
> View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.

  - **R** View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**4. Juan Gris Prices - 259 Auction Price Results**  
`liveauctioneers.com` · tier `market`  
> ... for Ege Axminster after Juan Gris. See Sold Price. Hill Auction Gallery Sunrise, FL. Juan Gris, Pot de fleurs (Kahnweiler 1969), Au Soleil du Plafond,. 2026.

  - **R** for Ege Axminster after Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Hill Auction Gallery Sunrise, FL.  
    <sub>about someone else (Hill Auction Gallery Sunrise), not this stop</sub>
  - **R** Juan Gris, Pot de fleurs (Kahnweiler 1969), Au Soleil du Plafond,.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**5. Juan Gris Sold at Auction Prices**  
`invaluable.com` · tier `market`  
> ... Damaged. SOLD AS IS. Price Reflects Condition. Notes: Published by ... After Juan Gris, Spanish 1887-1927- "Au Soleil du Plafond",1955; lithographs ...

  - **X** Price Reflects Condition.  
    <sub>about someone else (Price Reflects Condition), not this stop</sub>
  - **X** Notes: Published by ...  
    <sub>about someone else (Notes), not this stop</sub>
  - **R** After Juan Gris, Spanish 1887-1927- "Au Soleil du Plafond",1955; lithographs ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**6. Juan Gris, Compotier (kahnweiler 1969), Au Soleil Du ...**  
`etsy.com` · tier `unverified`  
> Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph. RHFineArtCo · 4 out of 5 stars (16). Sale Price NZ$3,994.67 NZ ...

  - **R** Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** RHFineArtCo · 4 out of 5 stars (16).  
    <sub>about someone else (RHFineArtCo), not this stop</sub>
  - **X** Sale Price NZ$3,994.67 NZ ...  
    <sub>about someone else (Sale Price NZ), not this stop</sub>

**7. 19TH - 20TH CENTURIES ART: SPAIN BARCELONA ...**  
`facebook.com` · tier `reject`  
> ... Gris did for the book by Pierre Reverdy (1889-1960) "Au soleil du plafond, Paris, Tériade, 1955. Published nearly thirty years after the death of Juan Gris ...

  - **R** Gris did for the book by Pierre Reverdy (1889-1960) "Au soleil du plafond, Paris, Tériade, 1955.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **R** Published nearly thirty years after the death of Juan Gris ...  
    <sub>names juan gris, juan, gris</sub>

**8. Reproduction In the Ceiling Sun – Juan Gris**  
`artemlegrand.com` · tier `unverified`  
> Reproduction of the painting Au soleil du plafond - Juan Gris ; Responsible company. Made to order, sustainable and sourced materials (FSC wood) ; Premium posters.

  - **R** Reproduction of the painting Au soleil du plafond - Juan Gris ; Responsible company.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Made to order, sustainable and sourced materials (FSC wood) ; Premium posters.  
    <sub>about someone else (Made), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R2 w0 X0

> Juan Gris helped develop Synthetic Cubism by formulating a deductive method that generated recognizable objects from abstract geometric grids rather than breaking down observed forms [Encyclopaedia Britannica].
> 
> Starting in 1912, Gris transformed the materials

  - **R** Juan Gris helped develop Synthetic Cubism by formulating a deductive method that generated recognizable objects from abstract geometric grids rather than breaking down observed forms [Encyclopaedia Britannica].  
    <sub>names juan gris, juan, gris</sub>
  - **R** Starting in 1912, Gris transformed the materials  
    <sub>names gris</sub>


## Seed 4.2 — evaluative

**Seed phrase:** `Reverdy's capacity to infuse words with structural beauty`  
**Question asked:** What did Reverdy actually DO that would justify "capacity to infuse words with structural beauty"? If nothing, cut the phrase.  
**Query built:** `Reverdy "Au Soleil du Plafond" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **inert → inert** · R10 w3 X4

**1. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...

  - **R** Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**2. GRIS (JUAN) REVERDY (PAUL) Au soleil du plafond ... - Bonhams**  
`bonhams.com` · tier `unverified`  
> GRIS (JUAN). REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955. Fine Books, Manuscripts ...

  - **R** REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Fine Books, Manuscripts ...  
    <sub>about someone else (Fine Books), not this stop</sub>

**3. Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after) For ...**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**4. Transforming the Horizon: Reverdy's World War I - jstor**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris ... clearly that Reverdy has a double way of looking: he argues that Reverdy's ... leaves the tableau unfinished.

  - **R** Asp Au soleil du plafond et autres po?mes (Paris ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** clearly that Reverdy has a double way of looking: he argues that Reverdy's ...  
    <sub>names reverdy</sub>
  - w leaves the tableau unfinished.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**5. Pierre reverdy hi-res stock photography and images - Alamy**  
`alamy.com` · tier `unverified`  
> ... Au soleil du plafond), 1916, post-Cubist color lithograph still life ... unfinished at the time of Gris's death. A reduced version, with color ...

  - **R** Au soleil du plafond), 1916, post-Cubist color lithograph still life ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** unfinished at the time of Gris's death.  
    <sub>names gris</sub>
  - w A reduced version, with color ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**6. Living Still Life | John Golding | The New York Review of Books**  
`nybooks.com` · tier `unverified`  
> ... Reverdy's Au Soleil du plafond (not published until much later). ... Oh how I wish I could convey the ease and the charm of the unfinished.

  - **R** Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - w Oh how I wish I could convey the ease and the charm of the unfinished.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**7. Revue des Revues - ProQuest**  
`search.proquest.com` · tier `unverified`  
> ... Reverdy's Au Soleil du plafond. - No 4. - A.H.T. LEVI: The Reception of ... unfinished work. His idca of Europe, more similar to a religion than to a ...

  - **R** Reverdy's Au Soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **X** LEVI: The Reception of ...  
    <sub>about someone else (LEVI), not this stop</sub>
  - **X** His idca of Europe, more similar to a religion than to a ...  
    <sub>about someone else (Europe), not this stop</sub>

**8. Pierre Reverdy's Image Theory Explained | PDF | Mind - Scribd**  
`scribd.com` · tier `unverified`  
> Other essays may be allusive but remain quite incomplete in any assessment of image theory. ... M Au Soleil du Plafond, Paris: Tenade, 1955, pp. 23-4. M Pierre ...

  - **X** Other essays may be allusive but remain quite incomplete in any assessment of image theory.  
    <sub>about someone else (Other), not this stop</sub>
  - **R** M Au Soleil du Plafond, Paris: Tenade, 1955, pp.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 6.1 — evaluative

**Seed phrase:** `rarely emerge from the archives`  
**Question asked:** What did Their actually DO that would justify "rarely emerge from the archives"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" destroyed` — *the phrase is ours; hunt the event (destroyed) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R11 w1 X7

**1. Au soleil du plafond - Artvee**  
`artvee.com` · tier `unverified`  
> View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.

  - **R** View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**2. Juan Gris Prices - 259 Auction Price Results - LiveAuctioneers**  
`liveauctioneers.com` · tier `market`  
> ... Rug for Ege Axminster after Juan Gris. See Sold Price. Hill Auction Gallery Sunrise, FL. Juan Gris, Pot de fleurs (Kahnweiler 1969), Au Soleil du Plafond,. 2026.

  - **R** Rug for Ege Axminster after Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Hill Auction Gallery Sunrise, FL.  
    <sub>about someone else (Hill Auction Gallery Sunrise), not this stop</sub>
  - **R** Juan Gris, Pot de fleurs (Kahnweiler 1969), Au Soleil du Plafond,.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. Juan Gris, Au solei du plafond La pipe, 1955, Lithograph**  
`centraldoaposentado.com` · tier `unverified`  
> Juan Gris ... Juan Gris, The Pipe, from Au Soleil du Plafond, 1955 (after display ... Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine.

  - **R** Juan Gris, The Pipe, from Au Soleil du Plafond, 1955 (after display ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Dora Szampanier, Etching of destroyed synagogue - Drohobisz, Ukraine.  
    <sub>about someone else (Dora Szampanier), not this stop</sub>

**4. Juan Gris, Au solei du plafond Guitare, 1955, Lithograph**  
`browswithlea.com` · tier `unverified`  
> Juan Gris | Au Soleil du plafond (1955) | MutualArt display picture 1. Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after display. Juan Gris, Violin ...

  - **R** Juan Gris | Au Soleil du plafond (1955) | MutualArt display picture 1.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after display.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** Juan Gris, Violin ...  
    <sub>names juan gris, juan, gris</sub>

**5. Juan Gris Sold at Auction Prices - Invaluable.com**  
`invaluable.com` · tier `market`  
> ... Damaged. SOLD AS IS. Price Reflects Condition. Notes: Published by ... After Juan Gris, Spanish 1887-1927- "Au Soleil du Plafond",1955; lithographs ...

  - **X** Price Reflects Condition.  
    <sub>about someone else (Price Reflects Condition), not this stop</sub>
  - **X** Notes: Published by ...  
    <sub>about someone else (Notes), not this stop</sub>
  - **R** After Juan Gris, Spanish 1887-1927- "Au Soleil du Plafond",1955; lithographs ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**6. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ... He usually destroyed these drawings after the painting had been completed ...

  - **R** Au soleil du plafond lithographs 240 Other Lithographs 251 Posters 259 ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w He usually destroyed these drawings after the painting had been completed ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**7. Reproduction In the Ceiling Sun – Juan Gris | Artem Legrand**  
`artemlegrand.com` · tier `unverified`  
> Reproduction of the painting Au soleil du plafond - Juan Gris ; Responsible company. Made to order, sustainable and sourced materials (FSC wood) ; Premium posters.

  - **R** Reproduction of the painting Au soleil du plafond - Juan Gris ; Responsible company.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** Made to order, sustainable and sourced materials (FSC wood) ; Premium posters.  
    <sub>about someone else (Made), not this stop</sub>

**8. Juan Gris, Compotier (kahnweiler 1969), Au Soleil Du Plafond ... - Etsy**  
`etsy.com` · tier `unverified`  
> Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph. RHFineArtCo · 4 out of 5 stars (16). Sale Price NZ$3,994.67 NZ ...

  - **R** Juan Gris, Compotier (Kahnweiler 1969), Au Soleil du Plafond, Limited Edition Lithograph.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** RHFineArtCo · 4 out of 5 stars (16).  
    <sub>about someone else (RHFineArtCo), not this stop</sub>
  - **X** Sale Price NZ$3,994.67 NZ ...  
    <sub>about someone else (Sale Price NZ), not this stop</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 6.2 — evaluative

**Seed phrase:** `offering a glimpse into the transformative collaborations of early-20th-century artists`  
**Question asked:** What did Their actually DO that would justify "offering a glimpse into the transformative collaborations of early-20th-century artists"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" refused` — *the phrase is ours; hunt the event (refused) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R14 w3 X0

**1. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>

**2. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris and Reverly ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** Pierrots, Drawings, Books, etc Gris and Reverly ...  
    <sub>names gris</sub>

**3. Sold at Auction: Juan Gris, Juan Gris "Au Soleil du Plafond" ...**  
`invaluable.com` · tier `market`  
> Bid now on Invaluable: Juan Gris "Au Soleil du Plafond" Portfolio, 1955 from Auctions at Showplace on June 05, 2025, 11:00 AM EST.

  - **R** Bid now on Invaluable: Juan Gris "Au Soleil du Plafond" Portfolio, 1955 from Auctions at Showplace on June 05, 2025, 11:00 AM EST.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**4. Juan Gris - lots in our price database - LotSearch**  
`lotsearch.net` · tier `unverified`  
> JUAN GRIS (1887 – 1927) & PIERRE REVERDY (1889 – 1960). Au Soleil du plafond, Tériade, Paris, 4 février 1955. 11 lithographies en couleur à pleine page de ...

  - **R** JUAN GRIS (1887 – 1927) & PIERRE REVERDY (1889 – 1960).  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Au Soleil du plafond, Tériade, Paris, 4 février 1955.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - w 11 lithographies en couleur à pleine page de ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**5. The Gallery Collection: Curated Fine Art 2026-06-17 Auction**  
`liveauctioneers.com` · tier `market`  
> ... Juan Gris, Loupire (Kahnweiler 1969), Au Soleil du Plafond ... refuse any sale due to unforeseen ... refused sale for which payment has already been ...

  - **R** Juan Gris, Loupire (Kahnweiler 1969), Au Soleil du Plafond ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - w refuse any sale due to unforeseen ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - w refused sale for which payment has already been ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**6. Mary Ann Caws on Pierre Reverdy**  
`poetrysociety.org` · tier `unverified`  
> In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...

  - **R** In particular, Reverdy's close collaboration with Juan Gris lay at the origin of the poems of Au Soleil du plafond (Sun on the Ceiling), published in 1955, but ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. cubism, art hidden by geometric figures - Olmedo JEsus**  
`artsandculture.google.com` · tier `unverified`  
> The exception, which involves the inclusion of colorful gouaches are made to illustrate the album Au soleil du plafond, Pierre Reverdy, Juan Gris finally ...

  - **R** The exception, which involves the inclusion of colorful gouaches are made to illustrate the album Au soleil du plafond, Pierre Reverdy, Juan Gris finally ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**8. Juan Gris, cubiste au carré**  
`barnebys.fr` · tier `unverified`  
> ... (Au soleil du plafond). Durant la Première Guerre Mondiale, Gris et Picasso ne sont pas mobilisés, l'Espagne étant neutre. Chacun se retire ...

  - **R** (Au soleil du plafond).  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Durant la Première Guerre Mondiale, Gris et Picasso ne sont pas mobilisés, l'Espagne étant neutre.  
    <sub>names gris</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Juan Gris partnered directly with poet Pierre Reverdy beginning around 191

  - **R** Juan Gris partnered directly with poet Pierre Reverdy beginning around 191  
    <sub>names pierre reverdy, juan gris, reverdy</sub>


## Seed 7.1 — evaluative

**Seed phrase:** `highlights how visual artists`  
**Question asked:** What did this actually DO that would justify "highlights how visual artists"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **inert → inert** · R12 w1 X3

**1. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...

  - **R** Au soleil du plafond ; Artist Juan Gris (Spanish, 1887-1927) ; Publisher Éditions Verve, Paris, 1955 (Tériade) ; Printer Mourlot Frères, Paris ; Author Pierre ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**2. Juan Gris, The Book, from Au Soleil du Plafond, 1955 (after)**  
`1stdibs.com` · tier `market`  
> This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...

  - **R** This exquisite lithograph after Juan Gris (1887–1927), titled Le Livre (The Book), from the folio Au Soleil du Plafond (In the Sunlight of the Ceiling), ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. Juan Gris — Artworks, Sold Prices & Market Data**  
`appraisily.com` · tier `unverified`  
> Juan Gris shows deep auction liquidity with 368 tracked lots. Median realized sale is around $15,444. Category concentration is still broad or sparse. Last 12 ...

  - **R** Juan Gris shows deep auction liquidity with 368 tracked lots.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Median realized sale is around $15,444.  
    <sub>about someone else (Median), not this stop</sub>
  - **X** Category concentration is still broad or sparse.  
    <sub>about someone else (Category), not this stop</sub>

**4. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris and Reverly ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** Pierrots, Drawings, Books, etc Gris and Reverly ...  
    <sub>names gris</sub>

**5. GRIS (JUAN) REVERDY (PAUL) Au soleil du plafond, NUMBER ...**  
`bonhams.com` · tier `unverified`  
> GRIS (JUAN). REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955. Fine Books, Manuscripts ...

  - **R** REVERDY (PAUL) Au soleil du plafond, NUMBER 142 OF 220 COPIES, SIGNED BY REVERDY on the colophon, Paris, Tériade, 1955.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Fine Books, Manuscripts ...  
    <sub>about someone else (Fine Books), not this stop</sub>

**6. Pierre reverdy Stock Photos and Images**  
`alamy.com` · tier `unverified`  
> Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916. RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...

  - **R** Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. Living Still Life | John Golding**  
`nybooks.com` · tier `unverified`  
> ... Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later). These small ...

  - **R** Gris produced the most beautiful of his book illustrations for Reverdy's Au Soleil du plafond (not published until much later).  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**8. Transforming the Horizon: Reverdy's World War I**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris ... be seen as the frontispiece to Douglas Cooper's Juan Gris: Catalogue raisonn? ... leaves the tableau unfinished ...

  - **R** Asp Au soleil du plafond et autres po?mes (Paris ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** be seen as the frontispiece to Douglas Cooper's Juan Gris: Catalogue raisonn?  
    <sub>names juan gris, juan, gris</sub>
  - w leaves the tableau unfinished ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> For *Au Soleil du Plafond*, visual artist Juan Gris partnered directly

  - **R** For *Au Soleil du Plafond*, visual artist Juan Gris partnered directly  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>


## Seed 8.1 — evaluative

**Seed phrase:** `inviting reflection on art as a shared divine expression`  
**Question asked:** What did The confluence of art and text here actually DO that would justify "inviting reflection on art as a shared divine expression"? If nothing, cut the phrase.  
**Query built:** `Juan Gris "Au Soleil du Plafond" commissioned` — *the phrase is ours; hunt the event (commissioned) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R12 w2 X2

**1. Juan Gris Art Value Price Guide - Invaluable.com**  
`invaluable.com` · tier `market`  
> Juan Gris (1887 - 1927) PIERRE REVERDY (1889 - 1960) AU SOLEIL DU PLAFOND 22 litografie di Gris. Ed. Est: €6,000 - €7,000. View sold prices. Juan Gris (1887 ...

  - **R** Juan Gris (1887 - 1927) PIERRE REVERDY (1889 - 1960) AU SOLEIL DU PLAFOND 22 litografie di Gris.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - w Est: €6,000 - €7,000.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**2. JUAN GRIS (1887-1927), Le moulin à café - Christie's**  
`christies.com` · tier `market`  
> It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond. Other gouaches include Compotier, now part of the Leonard A. Lauder ...

  - **R** It was not until 1955 when the book was published by Tériade, entitled Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Other gouaches include Compotier, now part of the Leonard A.  
    <sub>about someone else (Other), not this stop</sub>

**3. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris and Reverly ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** Pierrots, Drawings, Books, etc Gris and Reverly ...  
    <sub>names gris</sub>

**4. Purchase a reproduction of Coffee Grinder, Cup and Glass on a ...**  
`wahooart.com` · tier `unverified`  
> Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely decorative; they were integral to the artwork's ...

  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely decorative; they were integral to the artwork's ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**5. Purchase Collectible Image - Juan Gris**  
`artsdot.com` · tier `unverified`  
> Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely decorative; they were integral to the artwork's ...

  - **R** Reverdy's poems, intended to accompany Gris's chromolithographs in Au soleil du plafond, weren't merely decorative; they were integral to the artwork's ...  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>

**6. Pierre reverdy hi-res stock photography and images - Alamy**  
`alamy.com` · tier `unverified`  
> Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916. RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...

  - **R** Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **R** RM 3F4EGGY–Juan Gris – The Violin (Le Violon / Au soleil du plafond), 1916, post-Cubist ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. The cubism of Juan Gris. Vol I. Still lifes, landscapes - Academia.edu**  
`academia.edu` · tier `tier1`  
> ... Juan Gris, Au soleil du plafond, Paris, 1955, repr. plate 8 among a serie of 10 other gouaches p.105-107. Exhibitions: - Saidenberg Gallery, New York, Juan Gris ...

  - **R** Juan Gris, Au soleil du plafond, Paris, 1955, repr.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - w plate 8 among a serie of 10 other gouaches p.105-107.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** Exhibitions: - Saidenberg Gallery, New York, Juan Gris ...  
    <sub>names juan gris, juan, gris</sub>

**8. At Cateau-Cambrésis, an enhanced Matisse museum - Gazette Drouot**  
`gazette-drouot.com` · tier `unverified`  
> Architects Emmanuelle and Laurent Beaudoin were commissioned to ... Juan Gris for Pierre Reverdy's Au soleil du plafond. In the near ...

  - **X** Architects Emmanuelle and Laurent Beaudoin were commissioned to ...  
    <sub>about someone else (Architects Emmanuelle), not this stop</sub>
  - **R** Juan Gris for Pierre Reverdy's Au soleil du plafond.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Cut the phrase. 
> 
> In *Au Soleil du Plafond*, Juan Gris partnered with poet

  - **R** In *Au Soleil du Plafond*, Juan Gris partnered with poet  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>


---

# Moses and Monotheism


## Seed 1.1 — anchored

**Seed phrase:** `Dalí's vivid illustrations`  
**Question asked:** Is this true, and what is the event behind it: "Dalí's vivid illustrations"?  
**Query built:** `Dalí "Moses and Monotheism" Salvador Dalí` — *verify the named claim*

### SERPER — 8 results · kind **inert → inert** · R12 w0 X6

**1. Illustrations and printed text of Sigmund Freud's Moses and ...**  
`collections.museumofthebible.org` · tier `unverified`  
> Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.

  - **R** Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**2. Moise et Monotheisme, Moses and Monotheism, ca. 1975 - Artsy**  
`artsy.net` · tier `market`  
> Salvador Dalí. ,. Moise et Monotheisme, Moses and Monotheism, ca. 1975 ; High auction record. £13.5m, Sotheby's, 2011 ; Blue-chip. Represented by internationally ...

  - **R** Moise et Monotheisme, Moses and Monotheism, ca.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** 1975 ; High auction record.  
    <sub>about someone else (High), not this stop</sub>
  - **X** £13.5m, Sotheby's, 2011 ; Blue-chip.  
    <sub>about someone else (Sotheby's), not this stop</sub>
  - **X** Represented by internationally ...  
    <sub>about someone else (Represented), not this stop</sub>

**3. Moses and Monotheism by Salvador Dali - David Barnett Gallery**  
`davidbarnettgallery.com` · tier `unverified`  
> Moses and Monotheism. Bronze Bas-relief Sculpture with Silver Patina, signed lower right. 27.25 x 20.75 ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Bronze Bas-relief Sculpture with Silver Patina, signed lower right.  
    <sub>about someone else (Bronze Bas-relief Sculpture), not this stop</sub>

**4. Dream of Moses - Moses and Monotheism - Dali Paris**  
`daliparis.com` · tier `unverified`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on ...  
    <sub>names freud</sub>

**5. Salvador Dali Moise et Monotheisme, Moses and Monotheism**  
`lockportstreetgallery.com` · tier `unverified`  
> Salvador Dali Moise et Monotheisme, book also known as Moses and Monotheism contains text plus artwork. For the book Moise et Monotheisme there are 10 full ...

  - **R** Salvador Dali Moise et Monotheisme, book also known as Moses and Monotheism contains text plus artwork.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** For the book Moise et Monotheisme there are 10 full ...  
    <sub>names monotheism</sub>

**6. Moses and Monotheism by Salvador Dalí on artnet**  
`artnet.com` · tier `market`  
> View Moses and Monotheism by Salvador Dalí on artnet. Browse upcoming and past auction lots by Salvador Dalí.

  - **R** View Moses and Monotheism by Salvador Dalí on artnet.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** Browse upcoming and past auction lots by Salvador Dalí.  
    <sub>names salvador dali, salvador, dali</sub>

**7. Salvador Dali Moses And Monotheism Sculpture Bas Relief Silver Patina ...**  
`ebay.com` · tier `unverified`  
> Salvador Dali Moses And Monotheism Sculpture Bas Relief Silver Patina 21x27”. M. mygallery500 (332). 100% positive. Message. $4,600.00or Best Offer.

  - **R** Salvador Dali Moses And Monotheism Sculpture Bas Relief Silver Patina 21x27”.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **X** $4,600.00or Best Offer.  
    <sub>about someone else (Best Offer), not this stop</sub>

**8. Salvador Dali Moses Monotheism Etching/Lithograph Signed Limited**  
`kcmgalleries.com` · tier `unverified`  
> Description: Salvador Dali. Moses' Nightmare (Cauchemar de Moise) from Moses and Monotheism. Etching over lithography on soft glove sheepskin. Year: 1975.

  - **R** Description: Salvador Dali.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** Moses' Nightmare (Cauchemar de Moise) from Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Etching over lithography on soft glove sheepskin.  
    <sub>about someone else (Etching), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Yes, Salvador Dalí created a portfolio of prints illustrating Sigmund Freud's 19

  - **R** Yes, Salvador Dalí created a portfolio of prints illustrating Sigmund Freud's 19  
    <sub>names sigmund freud, salvador dali, salvador</sub>


## Seed 2.1 — anchored

**Seed phrase:** `breathe life into Freud’s narrative become evident`  
**Question asked:** Is this true, and what is the event behind it: "breathe life into Freud’s narrative become evident"?  
**Query built:** `Freud’s "Moses and Monotheism" Salvador Dalí` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R12 w0 X1

**1. Illustrations and printed text of Sigmund Freud's Moses and ...**  
`collections.museumofthebible.org` · tier `unverified`  
> Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.

  - **R** Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**2. Dream of Moses - Moses and Monotheism - Dali Paris**  
`daliparis.com` · tier `unverified`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on ...  
    <sub>names freud</sub>

**3. Salvador Dali Moise et Monotheisme, Moses and Monotheism**  
`lockportstreetgallery.com` · tier `unverified`  
> Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport Street Gallery.

  - **R** Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport Street Gallery.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**4. Moses and Monotheism - Dream of Moses by Salvador Dalí on artnet**  
`artnet.com` · tier `market`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on psychoanalytic ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on psychoanalytic ...  
    <sub>names freud</sub>

**5. Sigmund Freud - Salvador Dalí Museum**  
`thedali.org` · tier `unverified`  
> Freud, Sigmund. Moses and Monotheism. Vintage Books, 1967. This volume reflects Freud's commentaries on various aspects of religion, specifically his ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** This volume reflects Freud's commentaries on various aspects of religion, specifically his ...  
    <sub>names freud</sub>

**6. Moses and Monotheism - VKS ART**  
`vksart.com` · tier `unverified`  
> Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.

  - **R** Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**7. Museum - This oversize French edition of Sigmund Freud's 1939 ...**  
`facebook.com` · tier `reject`  
> This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism ... Salvador Dalí. #ArtifactoftheDay The pages ...

  - **R** This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** #ArtifactoftheDay The pages ...  
    <sub>about someone else (ArtifactoftheDay The), not this stop</sub>

**8. Moses and Monotheism - Moses and Akhenaton (1975) by Salvador Dalí**  
`artsy.net` · tier `market`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on psychoanalytic ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on psychoanalytic ...  
    <sub>names freud</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 3.1 — evaluative

**Seed phrase:** `infusing it with his characteristic surrealism`  
**Question asked:** What did Salvador Dalí actually DO that would justify "infusing it with his characteristic surrealism"? If nothing, cut the phrase.  
**Query built:** `Salvador Dalí "Moses and Monotheism" refused` — *the phrase is ours; hunt the event (refused) behind it*

### SERPER — 8 results · kind **active → inert** · R11 w1 X7

**1. Sold at Auction: Salvador Dalí, Salvador Dali Moses and ...**  
`invaluable.com` · tier `market`  
> Est · $6,000 USD - $8,000 USD ; Description. After Salvador Dali. "Moses and Monotheism." Bas Relief sculpture with silver patina. Dimensions: 28 x 21 inches.

  - **X** Est · $6,000 USD - $8,000 USD ; Description.  
    <sub>about someone else (Description), not this stop</sub>
  - **R** "Moses and Monotheism." Bas Relief sculpture with silver patina.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Dimensions: 28 x 21 inches.  
    <sub>about someone else (Dimensions), not this stop</sub>

**2. Freud had a lifelong fascination for the figure of Moses, from ... - Facebook**  
`facebook.com` · tier `reject`  
> In 1939, Sigmund Freud finished his last book, "Moses and Monotheism", shortly before his death. It caused outrage and drew much criticism the ...

  - **R** In 1939, Sigmund Freud finished his last book, "Moses and Monotheism", shortly before his death.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - w It caused outrage and drew much criticism the ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**3. Salvador Dali Moses and Monotheism sculpture Silver Patina**  
`kcmgalleries.com` · tier `unverified`  
> Description: After Salvador Dali. "Moses and Monotheism." Bas Relief sculpture with silver patina. Dimensions: 28 x 21 inches.

  - **R** Description: After Salvador Dali.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** "Moses and Monotheism." Bas Relief sculpture with silver patina.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Dimensions: 28 x 21 inches.  
    <sub>about someone else (Dimensions), not this stop</sub>

**4. DALI (Salvador). Moses and Monotheism. Embossed silver ...**  
`interencheres.com` · tier `unverified`  
> DALI (Salvador). Moses and Monotheism. Embossed silver-plated copper bas-relief (540x680mm), signed in the plate with black ink highlighting, ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Embossed silver-plated copper bas-relief (540x680mm), signed in the plate with black ink highlighting, ...  
    <sub>about someone else (Embossed), not this stop</sub>

**5. Sigmund and Monotheism: God, Jokes, and Eloquent Silence ... - jstor**  
`jstor.org` · tier `tier2`  
> , his commitment stretching from Psychopathy of Everyday Life. (1904) to Moses and Monotheism (1939). ... Salvador Dali had tried unsuccessfully to visit Freud in ...

  - **X** , his commitment stretching from Psychopathy of Everyday Life.  
    <sub>about someone else (Psychopathy), not this stop</sub>
  - **R** (1904) to Moses and Monotheism (1939).  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Salvador Dali had tried unsuccessfully to visit Freud in ...  
    <sub>names salvador dali, salvador, freud</sub>

**6. Lot - After Salvador Dali (Spanish, 1904-1989), Moses and ...**  
`andrewjonesauctions.com` · tier `unverified`  
> After Salvador Dali (Spanish, 1904-1989), Moses and Monotheism, gold gilt patinated copper bas relief, 27 x 21in. (71 x 53cm) · Sold: · Additional ...

  - **R** After Salvador Dali (Spanish, 1904-1989), Moses and Monotheism, gold gilt patinated copper bas relief, 27 x 21in.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **X** (71 x 53cm) · Sold: · Additional ...  
    <sub>about someone else (Sold), not this stop</sub>

**7. Dalí: Transgressing a mythical icon of art history - Fundació Gala**  
`salvador-dali.org` · tier `unverified`  
> ... Moses and monotheism, two key elements for understanding Dalí's contribution to surrealism. Exhibiting the Venus de Milo with Drawers in the 21st century.

  - **R** Moses and monotheism, two key elements for understanding Dalí's contribution to surrealism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Exhibiting the Venus de Milo with Drawers in the 21st century.  
    <sub>about someone else (Exhibiting), not this stop</sub>

**8. About Salvador Dalí - Moderna Museet**  
`modernamuseet.se` · tier `unverified`  
> ... Dalí (The Unspeakable Confessions of Salvador Dalí), 1973. 1974. Provides the introduction and illustrations to Sigmund Freud's book Moses and Monotheism. The ...

  - **R** Dalí (The Unspeakable Confessions of Salvador Dalí), 1973.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** Provides the introduction and illustrations to Sigmund Freud's book Moses and Monotheism.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1

> For the 1974 *livre d'

  - **X** For the 1974 *livre d'  
    <sub>names nothing belonging to this stop</sub>


## Seed 4.1 — anchored

**Seed phrase:** `Freud's exploration of`  
**Question asked:** Is this true, and what is the event behind it: "Freud's exploration of"?  
**Query built:** `Freud "Moses and Monotheism" Salvador Dalí` — *verify the named claim*

### SERPER — 8 results · kind **active → active** · R11 w0 X2

**1. Illustrations and printed text of Sigmund Freud's Moses and ...**  
`collections.museumofthebible.org` · tier `unverified`  
> Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.

  - **R** Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**2. Dream of Moses - Moses and Monotheism**  
`daliparis.com` · tier `unverified`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on ...  
    <sub>names freud</sub>

**3. Salvador Dali Moise et Monotheisme, Moses and ...**  
`lockportstreetgallery.com` · tier `unverified`  
> Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport Street Gallery.

  - **R** Salvador Dali Moise et Monotheisme, Moses and Monotheism illustrated book by Sigmund Freud is available at the Lockport Street Gallery.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**4. Moses and Monotheism**  
`vksart.com` · tier `unverified`  
> Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.

  - **R** Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**5. Moses and Monotheism - Transfer of traditions, 1975**  
`artnet.com` · tier `market`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on psychoanalytic theory ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on psychoanalytic theory ...  
    <sub>names freud</sub>

**6. Sigmund Freud**  
`thedali.org` · tier `unverified`  
> Freud, Sigmund. Moses and Monotheism. Vintage Books, 1967. This volume reflects Freud's commentaries on various aspects of religion, specifically his ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** This volume reflects Freud's commentaries on various aspects of religion, specifically his ...  
    <sub>names freud</sub>

**7. Museum - This oversize French edition of Sigmund Freud's ...**  
`facebook.com` · tier `reject`  
> This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism ... Salvador Dalí. #ArtifactoftheDay The pages ...

  - **R** This oversize French edition of Sigmund Freud's 1939 published work, "Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** #ArtifactoftheDay The pages ...  
    <sub>about someone else (ArtifactoftheDay The), not this stop</sub>

**8. Salvador DALI and Sigmund FREUD Moses and Monotheism Art...**  
`gazette-drouot.com` · tier `unverified`  
> Salvador DALI and Sigmund FREUD Moses and Monotheism Art and Value. Paris, 1974. Large folio in sheets, two plexiglass folders with burgundy suede spine, ...

  - **R** Salvador DALI and Sigmund FREUD Moses and Monotheism Art and Value.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>
  - **X** Large folio in sheets, two plexiglass folders with burgundy suede spine, ...  
    <sub>about someone else (Large), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Yes, Salvador Dalí created illustrations for Sigmund Freud's 1939 text *Moses

  - **R** Yes, Salvador Dalí created illustrations for Sigmund Freud's 1939 text *Moses  
    <sub>names sigmund freud, salvador dali, salvador</sub>


## Seed 4.2 — evaluative

**Seed phrase:** `visualizing the psychological and spiritual transition from polytheistic beliefs`  
**Question asked:** What did His imagery actually DO that would justify "visualizing the psychological and spiritual transition from polytheistic beliefs"? If nothing, cut the phrase.  
**Query built:** `Salvador Dalí "Moses and Monotheism" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R11 w3 X0

**1. Everyday Life in Exile - Sigmund Freud Museum**  
`freud-museum.at` · tier `unverified`  
> Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished. He receives guests including ...

  - **R** Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - w He receives guests including ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**2. Lucian Freud Self Portrait (Unfinished), c. 1956 oil on canvas ...**  
`facebook.com` · tier `reject`  
> But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...

  - **R** But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**3. Sigmund Freud | British Psychoanalytical Society**  
`psychoanalysis.org.uk` · tier `unverified`  
> In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis. He was visited by Salvador Dalí – a ...

  - **R** In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** He was visited by Salvador Dalí – a ...  
    <sub>names salvador dali, salvador, dali</sub>

**4. “The Audacity Cannot Be Avoided” (Chapter 3) - The Late Sigmund Freud**  
`cambridge.org` · tier `unverified`  
> Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial. It is the culmination of his thinking about religion and ...

  - **R** Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w It is the culmination of his thinking about religion and ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**5. Peter Arenskov Turned, Bas Relief Sculpture Auction**  
`liveauctioneers.com` · tier `market`  
> ... Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism. 1975. 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...

  - **R** Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...  
    <sub>names salvador dali, salvador, moses</sub>

**6. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows - MutualArt**  
`mutualart.com` · tier `market`  
> Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ... It is an attitude, an unfinished ...

  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - w It is an attitude, an unfinished ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**7. I can't believe I almost didnt buy this from the antique shop. Outside ...**  
`instagram.com` · tier `reject`  
> Dalí was only 27 years old when he created this legendary piece. ... The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975). ... • ...

  - **R** Dalí was only 27 years old when he created this legendary piece.  
    <sub>names dali</sub>
  - **R** The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975).  
    <sub>names moses and monotheism, monotheism, freud</sub>

**8. Freud and the World Wars | Psychology Today**  
`psychologytoday.com` · tier `unverified`  
> He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoanalysis, which came out ...

  - **R** He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoanalysis, which came out ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 5.1 — evaluative

**Seed phrase:** `delves into the complexities of religious origins`  
**Question asked:** What did this actually DO that would justify "delves into the complexities of religious origins"? If nothing, cut the phrase.  
**Query built:** `Salvador Dalí "Moses and Monotheism" destroyed` — *the phrase is ours; hunt the event (destroyed) behind it*

### SERPER — 8 results · kind **inert → inert** · R11 w2 X2

**1. Moses and Monotheism - VKS ART**  
`vksart.com` · tier `unverified`  
> Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.

  - **R** Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**2. Salvador Dali Moses And Monotheism (Platinum Patina) Bas Relif Signed**  
`facebook.com` · tier `reject`  
> Salvador Dali Moses And Monotheism (Platinum Patina) Bas Relif Signed 5️⃣k obo (request private message if interested)

  - **R** Salvador Dali Moses And Monotheism (Platinum Patina) Bas Relif Signed 5️⃣k obo (request private message if interested)  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>

**3. Dali 1904-1989 Moses Monotheism Bronze Bas Relief Auction**  
`liveauctioneers.com` · tier `market`  
> ... Moses and Monotheism. 1975 · US$2,950. Related Searches. Artwork Salvador DaliDaliDali PaintingsOriginal DaliSalvador Dali ArtSalvador Dali EaSalvador Dali ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Artwork Salvador DaliDaliDali PaintingsOriginal DaliSalvador Dali ArtSalvador Dali EaSalvador Dali ...  
    <sub>names salvador dali, salvador, dali</sub>

**4. After Salvador Dali, Moses And Monotheism, Bronze Bas Relief ...**  
`mutualart.com` · tier `market`  
> A bronze plaque depicting a man with a bow and arrow. After Salvador Dali, Moses And Monotheism, Bronze Bas Relief Sculpture, Center Art Gallery. bas ...

  - w A bronze plaque depicting a man with a bow and arrow.  
    <sub>no entity of its own; snippet names moses and monotheism</sub>
  - **R** After Salvador Dali, Moses And Monotheism, Bronze Bas Relief Sculpture, Center Art Gallery.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>

**5. Sigmund and Monotheism: God, Jokes, and Eloquent Silence ... - jstor**  
`jstor.org` · tier `tier2`  
> , his commitment stretching from Psychopathy of Everyday Life. (1904) to Moses and Monotheism (1939). ... ” says Dali in his broken English ... Salvador Dali had ...

  - **X** , his commitment stretching from Psychopathy of Everyday Life.  
    <sub>about someone else (Psychopathy), not this stop</sub>
  - **R** (1904) to Moses and Monotheism (1939).  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** ” says Dali in his broken English ...  
    <sub>names dali</sub>
  - **R** Salvador Dali had ...  
    <sub>names salvador dali, salvador, dali</sub>

**6. Salvador Dalí Moses and Monotheism, 1979 - 1stDibs**  
`1stdibs.com` · tier `market`  
> This artwork titled, "Moses and Monotheism" 1979, is a copper embossed bas relief by artist Salvador Dali, 1904-1989. It is hand signed in felt pen at the ...

  - **R** This artwork titled, "Moses and Monotheism" 1979, is a copper embossed bas relief by artist Salvador Dali, 1904-1989.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - w It is hand signed in felt pen at the ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**7. Lot - After Salvador Dali (Spanish, 1904-1989), Moses and ...**  
`andrewjonesauctions.com` · tier `unverified`  
> Description: After Salvador Dali (Spanish, 1904-1989) Moses and Monotheism gold gilt patinated copper bas relief

  - **R** Description: After Salvador Dali (Spanish, 1904-1989) Moses and Monotheism gold gilt patinated copper bas relief  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>

**8. Lot - Salvador Dali "Moses and Monotheism" Ltd. Ed. Signed Bas ...**  
`bradfordsauction.com` · tier `unverified`  
> Description: Salvador Dali (1904-1989) "Moses And Monotheism" Bas Relief with Gold Patina. Hand signed in marker lower right, ...

  - **R** Description: Salvador Dali (1904-1989) "Moses And Monotheism" Bas Relief with Gold Patina.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **X** Hand signed in marker lower right, ...  
    <sub>about someone else (Hand), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R2 w0 X0

> Dalí produced a 1974 *livre d'artiste* portfolio that illustrates Sigmund Freud’s 1939 treatise *Moses and Monotheism* [Museum of Fine Arts Boston, "Picasso, Miró, Dalí: Unbound"]. 
> 
> Freud's text presents the psychoanalytic hypothesis that Moses was an Egyptian noble who introduced the monotheistic religion of Pharaoh Akhenaten to the Hebrew people [Sigmund Freud, *Moses and Monotheism*, 1939]. 

  - **R** Dalí produced a 1974 *livre d'artiste* portfolio that illustrates Sigmund Freud’s 1939 treatise *Moses and Monotheism* [Museum of Fine Arts Boston, "Picasso, Miró, Dalí: Unbound"].  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** Freud's text presents the psychoanalytic hypothesis that Moses was an Egyptian noble who introduced the monotheistic religion of Pharaoh Akhenaten to the Hebrew people [Sigmund Freud, *Moses and Monotheism*, 1939].  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>


## Seed 5.2 — anchored

**Seed phrase:** `setting the stage for Dalí's evocative interpretations`  
**Question asked:** Is this true, and what is the event behind it: "setting the stage for Dalí's evocative interpretations"?  
**Query built:** `Dalí's "Moses and Monotheism" Salvador Dalí` — *verify the named claim*

### SERPER — 8 results · kind **inert → inert** · R13 w0 X4

**1. Dream of Moses - Moses and Monotheism**  
`daliparis.com` · tier `unverified`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on ...  
    <sub>names freud</sub>

**2. Moise et Monotheisme, Moses and Monotheism, ca. 1975**  
`artsy.net` · tier `market`  
> Salvador Dalí. ,. Moise et Monotheisme, Moses and Monotheism, ca. 1975 ; High auction record. £13.5m, Sotheby's, 2011 ; Blue-chip. Represented by internationally ...

  - **R** Moise et Monotheisme, Moses and Monotheism, ca.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** 1975 ; High auction record.  
    <sub>about someone else (High), not this stop</sub>
  - **X** £13.5m, Sotheby's, 2011 ; Blue-chip.  
    <sub>about someone else (Sotheby's), not this stop</sub>
  - **X** Represented by internationally ...  
    <sub>about someone else (Represented), not this stop</sub>

**3. Moses and Monotheism by Salvador Dali**  
`davidbarnettgallery.com` · tier `unverified`  
> Moses and Monotheism. Bronze Bas-relief Sculpture with Silver Patina, signed lower right. 27.25 x 20.75 ...

  - **R** Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Bronze Bas-relief Sculpture with Silver Patina, signed lower right.  
    <sub>about someone else (Bronze Bas-relief Sculpture), not this stop</sub>

**4. Illustrations and printed text of Sigmund Freud's Moses ...**  
`collections.museumofthebible.org` · tier `unverified`  
> Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.

  - **R** Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.  
    <sub>names moses and monotheism, sigmund freud, salvador dali</sub>

**5. Salvador Dali Moise et Monotheisme, Moses and ...**  
`lockportstreetgallery.com` · tier `unverified`  
> Salvador Dali Moise et Monotheisme, book also known as Moses and Monotheism contains text plus artwork. For the book Moise et Monotheisme there are 10 full ...

  - **R** Salvador Dali Moise et Monotheisme, book also known as Moses and Monotheism contains text plus artwork.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** For the book Moise et Monotheisme there are 10 full ...  
    <sub>names monotheism</sub>

**6. DALI Moses and Monotheism The Tear of Blood Hand Sig ...**  
`ebay.com` · tier `unverified`  
> DALI Moses and Monotheism The Tear of Blood Hand Sig/Num Etching Surreal ART ; Artist. Salvador Dalí ; Edition Size. EA XXIII/XXV ; ARTIST: Salvador Dali ; TITLE: ...

  - **R** DALI Moses and Monotheism The Tear of Blood Hand Sig/Num Etching Surreal ART ; Artist.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Salvador Dalí ; Edition Size.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** EA XXIII/XXV ; ARTIST: Salvador Dali ; TITLE: ...  
    <sub>names salvador dali, salvador, dali</sub>

**7. Moses and Monotheism - Salvador Dalí**  
`artnet.com` · tier `market`  
> Moses and Monotheism is a book written in 1939 by Sigmund Freud. The book consists of three essays and is an extension of Freud's work on psychoanalytic ...

  - **R** Moses and Monotheism is a book written in 1939 by Sigmund Freud.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** The book consists of three essays and is an extension of Freud's work on psychoanalytic ...  
    <sub>names freud</sub>

**8. Moses and Monotheism**  
`vksart.com` · tier `unverified`  
> Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.

  - **R** Dali's edition of Sigmund Freud's last publication, Moses and Monotheism, was published in 1974 and consists of Freud's text, accompanied by ten engravings.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1 · **declared NO RELIABLE INFORMATION**

> NO RELIABLE INFORMATION

  - **X** NO RELIABLE INFORMATION  
    <sub>about someone else (RELIABLE INFORMATION), not this stop</sub>


## Seed 6.1 — evaluative

**Seed phrase:** `the book itself is an artwork`  
**Question asked:** What did The work actually DO that would justify "the book itself is an artwork"? If nothing, cut the phrase.  
**Query built:** `Salvador Dalí "Moses and Monotheism" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **eventful → eventful** · R11 w2 X0

**1. Everyday Life in Exile**  
`freud-museum.at` · tier `unverified`  
> Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished. He receives guests including ...

  - **R** Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - w He receives guests including ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**2. Lucian Freud Self Portrait (Unfinished), c. 1956 oil on ...**  
`facebook.com` · tier `reject`  
> But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...

  - **R** But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**3. Sigmund Freud**  
`psychoanalysis.org.uk` · tier `unverified`  
> In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis. He was visited by Salvador Dalí – a ...

  - **R** In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** He was visited by Salvador Dalí – a ...  
    <sub>names salvador dali, salvador, dali</sub>

**4. “The Audacity Cannot Be Avoided” (Chapter 3)**  
`cambridge.org` · tier `unverified`  
> And a “Jewish medical biographer” even claimed, upon reading Moses and Monotheism, to have ripped up his unpublished manuscript on Freud's life. In early 1936, ...

  - **R** And a “Jewish medical biographer” even claimed, upon reading Moses and Monotheism, to have ripped up his unpublished manuscript on Freud's life.  
    <sub>names moses and monotheism, monotheism, freud</sub>

**5. Peter Arenskov Turned, Bas Relief Sculpture Auction**  
`liveauctioneers.com` · tier `market`  
> ... Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism. 1975. 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...

  - **R** Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...  
    <sub>names salvador dali, salvador, moses</sub>

**6. I can't believe I almost didnt buy this from the antique shop. ...**  
`instagram.com` · tier `reject`  
> Dalí was only 27 years old when he created this legendary piece. ... The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975). ... • ...

  - **R** Dalí was only 27 years old when he created this legendary piece.  
    <sub>names dali</sub>
  - **R** The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975).  
    <sub>names moses and monotheism, monotheism, freud</sub>

**7. Freud and the World Wars**  
`psychologytoday.com` · tier `unverified`  
> He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoanalysis, which came out ...

  - **R** He completed his long-unfinished book Moses and Monotheism, and a synopsis of his lifetime's work, An Outline of Psychoanalysis, which came out ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**8. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ... It is an attitude, an unfinished ...

  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - w It is an attitude, an unfinished ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

### GEMINI (grounded) — kind **inert → none** · R0 w0 X1

> The 1974 publication was produced as an unbound *livre d'artiste* portfolio containing loose sheets of

  - **X** The 1974 publication was produced as an unbound *livre d'artiste* portfolio containing loose sheets of  
    <sub>names nothing belonging to this stop</sub>


## Seed 7.1 — evaluative

**Seed phrase:** `bridging literary and visual art forms`  
**Question asked:** What did Dalí and Freud actually DO that would justify "bridging literary and visual art forms"? If nothing, cut the phrase.  
**Query built:** `Salvador Dalí "Moses and Monotheism" unfinished` — *the phrase is ours; hunt the event (unfinished) behind it*

### SERPER — 8 results · kind **inert → inert** · R10 w3 X1

**1. Everyday Life in Exile - Sigmund Freud Museum**  
`freud-museum.at` · tier `unverified`  
> Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished. He receives guests including ...

  - **R** Here, he finishes his work Moses and Monotheism, while his final work— An Outline of Psychoanalysis —remains unfinished.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - w He receives guests including ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**2. Lucian Freud Self Portrait (Unfinished), c. 1956 oil on canvas ...**  
`facebook.com` · tier `reject`  
> But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...

  - **R** But in 'Moses and Monotheism' we find – amid much fascinating and bizarre speculation – both an enthusiastic defence of monotheism and a ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**3. “The Audacity Cannot Be Avoided” (Chapter 3) - The Late Sigmund Freud**  
`cambridge.org` · tier `unverified`  
> Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial. It is the culmination of his thinking about religion and ...

  - **R** Moses and Monotheism of 1939 is Freud's last significant work and one of his most controversial.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - w It is the culmination of his thinking about religion and ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**4. Sigmund Freud | British Psychoanalytical Society**  
`psychoanalysis.org.uk` · tier `unverified`  
> In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis. He was visited by Salvador Dalí – a ...

  - **R** In London Freud worked on his final books, Moses and Monotheism, and the incomplete Outline of Psychoanalysis.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** He was visited by Salvador Dalí – a ...  
    <sub>names salvador dali, salvador, dali</sub>

**5. Aliyah, The Rebirth of Israel, Salvador Dali - Scribd**  
`scribd.com` · tier `unverified`  
> ... Moses and Monotheism* (1975), and others, some of which, like the "Menorah" and "Western Wall" sculptures (1982) appeared very late in his lifetime. Most of ...

  - **R** Moses and Monotheism* (1975), and others, some of which, like the "Menorah" and "Western Wall" sculptures (1982) appeared very late in his lifetime.  
    <sub>names moses and monotheism, monotheism, moses</sub>

**6. Peter Arenskov Turned, Bas Relief Sculpture Auction**  
`liveauctioneers.com` · tier `market`  
> ... Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism. 1975. 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...

  - **R** Salvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses and Monotheism.  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>
  - **R** 7 days LeftSalvador Dali (Spanish 1904-1989) Bas Relief Sculpture Moses ...  
    <sub>names salvador dali, salvador, moses</sub>

**7. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows - MutualArt**  
`mutualart.com` · tier `market`  
> Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ... It is an attitude, an unfinished ...

  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - w It is an attitude, an unfinished ...  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

**8. I can't believe I almost didnt buy this from the antique shop. Outside ...**  
`instagram.com` · tier `reject`  
> The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975). The Victoria Memorial Etchings : The two works at the Victoria Memorial ...

  - **R** The Philosophical: Goethe's Faust (1969) and Freud's Moses and Monotheism (1975).  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **X** The Victoria Memorial Etchings : The two works at the Victoria Memorial ...  
    <sub>about someone else (The Victoria Memorial Etchings), not this stop</sub>

### GEMINI (grounded) — kind **inert → inert** · R1 w0 X0

> Sigmund Freud wrote and published the text *Moses and Monotheism* in 1939

  - **R** Sigmund Freud wrote and published the text *Moses and Monotheism* in 1939  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

