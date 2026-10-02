# Raw results — matrix-built queries, both engines

**30 Serper queries + 3 Gemini grounded = 33 retrievals · ~$0.042 · 36s**

Queries come from `work_story_searcher.synthesize_queries` — the real mechanism, LOCAL-406 + LOCAL-423, built from eleven matrix fields. Gemini gets D366's framing directly: *"What story can be told to visitors of {exhibition} about {work}?"* with the whole matrix attached.

Sentence marks: **R** relevant · w weak (anaphoric, own snippet establishes subject) · **X** irrelevant. `kind` is `material_kind`, shown before → after the relevance gate.


---

# Le Lézard aux plumes d’or (The Lizard with Golden Feathers)


## Query 1 — `"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" Joan Miró story visitors Picasso, Miró, Dalí: Unbound`

8 results · kind **active → active** · R10 w0 X2

**1. Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**4. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...

  - **R** Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**6. Joan Miró. Cover front from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**7. Le Lézard aux plumes d'or – Poster Museum**  
`postermuseum.com` · tier `reject`  
> Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers). Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...

  - **R** Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...  
    <sub>names joan miro, joan, miro</sub>

**8. Global Cultural Bulletin: August 2026**  
`cabanamagazine.substack.com` · tier `unverified`  
> Picasso, Miró, Dalí: Unbound. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot ...

  - **R** Picasso, Miró, Dalí: Unbound.  
    <sub>names miro</sub>
  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot ...  
    <sub>names golden feathers, louis broder, the lizard</sub>


## Query 2 — `"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" Gift of Boris Fridman history story`

1 results · kind **active → active** · R1 w0 X0

**1. Global Cultural Bulletin: August 2026**  
`cabanamagazine.substack.com` · tier `unverified`  
> Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris ...

  - **R** Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris ...  
    <sub>names golden feathers, louis broder, the lizard</sub>


## Query 3 — `"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" Joan Miró`

8 results · kind **inert → inert** · R9 w1 X3

**1. 557135 The Lizard with Golden Feathers Joan Miró - Colección BBVA**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no. 515**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no. 515 ; Joan Miró (1893 - 1983) · Etching ...

  - **R** Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** 515 ; Joan Miró (1893 - 1983) · Etching ...  
    <sub>names joan miro, joan, miro</sub>

**3. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with Golden ... - MoMA**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**4. Joan Miró - Le lézard aux plumes d'or - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, 197167**  
`artsy.net` · tier `market`  
> Available for sale from Masterworks Fine Art, Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 (197167), Color Lithograph., 14 …

  - **R** Available for sale from Masterworks Fine Art, Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 (197167), Color Lithograph., 14 …  
    <sub>names golden feathers, the lizard, le lezard</sub>

**6. Joan Miró, Le Lézard aux plumes d'or (The Lizard with Golden Feathers ...**  
`masterworksfineart.com` · tier `unverified`  
> Title: Plate III from Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ; Reference: C. 148, M. 793 ; Medium: Color Lithograph on wove paper.

  - **R** Title: Plate III from Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 ; Reference: C.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** 793 ; Medium: Color Lithograph on wove paper.  
    <sub>about someone else (Medium), not this stop</sub>

**7. Joan Miró - Le Lezard aux Plumes d'Or (The Lizard with Golden ...**  
`facebook.com` · tier `reject`  
> Joan Miró - Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers). 1971. Paris: Louis Broder. .. 15 color lithographs, loose as issued in publisher's ...

  - **R** Joan Miró - Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - w 15 color lithographs, loose as issued in publisher's ...  
    <sub>no entity of its own; snippet names golden feathers</sub>

**8. Joan Miró. Plate (folio 29 verso) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 29 verso) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 29 verso) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>


## Query 4 — `"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" history`

8 results · kind **inert → inert** · R9 w0 X2

**1. Le Lézard aux plumes d'or (The Lizard with Golden Feathers)**  
`moma.org` · tier `tier1`  
> Le Lézard aux plumes d'or (The Lizard with. Golden Feathers). These works are part of an illustrated book. 40 works online. Joan Miró.

  - **R** Le Lézard aux plumes d'or (The Lizard with.  
    <sub>names the lizard, le lezard, plumes</sub>
  - **X** These works are part of an illustrated book.  
    <sub>about someone else (These), not this stop</sub>

**2. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...

  - **R** Original hand-signed Joan Miró Le Lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 Lithograph from the edition of 100 in pencil in the image ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Plate folio 30 from Le Lezard aux plumes dor The Lizard with ...**  
`artnet.com` · tier `market`  
> Joan Miró · Plate (folio 30) from Le Lezard aux plumes d'or (The Lizard with Golden Feathers), 1971 · 36 x 50 cm. (14.2 x 19.7 in.).

  - **R** Joan Miró · Plate (folio 30) from Le Lezard aux plumes d'or (The Lizard with Golden Feathers), 1971 · 36 x 50 cm.  
    <sub>names golden feathers, the lizard, le lezard</sub>

**4. Sold at Auction: Joan Miró, Joan Miró, Le lézard aux plumes d'or ...**  
`invaluable.com` · tier `market`  
> Joan Miró (Spanish, 1893 - 1983) Le lézard aux plumes d'or (The lizard with golden feathers), 1971 colour lithograph on paper 34.5 x 98.5 cm

  - **R** Joan Miró (Spanish, 1893 - 1983) Le lézard aux plumes d'or (The lizard with golden feathers), 1971 colour lithograph on paper 34.5 x 98.5 cm  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. Joan Miró. Le Lézard aux plumes d'or ( The Lizard with ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Illustrated book with forty lithographs (including wrapper front and cover).

  - **R** Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Illustrated book with forty lithographs (including wrapper front and cover).  
    <sub>about someone else (Illustrated), not this stop</sub>

**6. Last Chance alert! Some incredible works in our American ...**  
`instagram.com` · tier `reject`  
> ... Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers),” 1967, lithograph. Allentown Art Museum: Gift of Paul K. Kania, 2017. (2017.14 ...

  - **R** Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers),” 1967, lithograph.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** Allentown Art Museum: Gift of Paul K.  
    <sub>names gift</sub>

**7. Behind the Artist: Joan Miró**  
`parkwestgallery.com` · tier `unverified`  
> A fine example of Miró's literary-inspired art is his series “Le Lézard aux Plumes d'Or” (The Lizard with Golden Feathers). The series of ...

  - **R** A fine example of Miró's literary-inspired art is his series “Le Lézard aux Plumes d'Or” (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>

**8. Joan Miró Lithograph, Le lezard aux plumes d'or ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró (1893 - 1983) · Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 · Maeght 515 · Color Lithograph · 13 1/4 in x 19 in (33.6 cm x 48.3 cm).

  - **R** Joan Miró (1893 - 1983) · Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 · Maeght 515 · Color Lithograph · 13 1/4 in x 19 in (33.6 cm x 48.3 cm).  
    <sub>names golden feathers, the lizard, le lezard</sub>


## Query 5 — `"Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" edition lithographs`

8 results · kind **inert → inert** · R9 w2 X2

**1. Joan Miró - Le lezard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró (1893 - 1983) · Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 · Cramer 148 · Color Lithograph · 13 1/4 in x 19 3/16 in (33.7 cm x 48.8 ...

  - **R** Joan Miró (1893 - 1983) · Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967 · Cramer 148 · Color Lithograph · 13 1/4 in x 19 3/16 in (33.7 cm x 48.8 ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. Joan Miró. Plate (folio 11) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 11) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 11) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**3. Le lezard aux plumes d'or (The Lizard with Golden Fe ...**  
`artsy.net` · tier `market`  
> Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, 197167. Color Lithograph. 14 × 19 69/100 in | 35.6 × 50 cm. Edition of 170. Part of a

  - **R** Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, 197167.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - w 14 × 19 69/100 in | 35.6 × 50 cm.  
    <sub>no entity of its own; snippet names golden feathers</sub>

**4. Joan Miró | Le Lézard aux plumes d'or (1971, Lithographs)**  
`composition.gallery` · tier `unverified`  
> Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...

  - **R** Joan Miró's Le Lézard aux plumes d'or (The Lizard with Golden Feathers) from 1971 is a limited edition illustrated book that features 15 lithographs in vibrant ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> It consists of fifteen lithographs, accompanied by a poem by Miró ... Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered ...

  - **R** It consists of fifteen lithographs, accompanied by a poem by Miró ...  
    <sub>names miro</sub>
  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**6. Joan Miró - Le Lezard aux Plumes d'Or ( ...**  
`facebook.com` · tier `reject`  
> Joan Miró - Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers). 1971. Paris: Louis Broder. .. 15 color lithographs, loose as issued in publisher's ...

  - **R** Joan Miró - Le Lezard aux Plumes d'Or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - w 15 color lithographs, loose as issued in publisher's ...  
    <sub>no entity of its own; snippet names golden feathers</sub>

**7. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**8. Joan Miró. Cover front from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>


## Query 6 — `Louis Broder Joan Miró`

8 results · kind **inert → inert** · R13 w1 X3

**1. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> In 1956, Broder began a partnership with Joan Miró alongside Atelier Mourlot, a world-famous French lithographic studio. In 1920 when Miro was ...

  - **R** In 1956, Broder began a partnership with Joan Miró alongside Atelier Mourlot, a world-famous French lithographic studio.  
    <sub>names joan miro, mourlot, broder</sub>
  - **R** In 1920 when Miro was ...  
    <sub>names miro</sub>

**2. Louis Broder Archives**  
`parkwestgallery.com` · tier `unverified`  
> Joan Miró's “Broder Collection” is a series of color lithographs that, until 2004, had been inaccessible for over 30 years. The Broder Collection's vivid colors ...

  - **R** Joan Miró's “Broder Collection” is a series of color lithographs that, until 2004, had been inaccessible for over 30 years.  
    <sub>names joan miro, broder, joan</sub>
  - **R** The Broder Collection's vivid colors ...  
    <sub>names broder</sub>

**3. Louis Broder, [Paris], 1971 – People - Toledo Museum of Art**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Louis Broder, [Paris], 1971. Joan Miró (1) lithographs: Artist/Maker Nationality Spanish. Original prints: 15 lithographs in colors. Joan Miró Original prints: ...

  - **R** Louis Broder, [Paris], 1971.  
    <sub>names louis broder, broder, louis</sub>
  - **R** Joan Miró (1) lithographs: Artist/Maker Nationality Spanish.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Original prints: 15 lithographs in colors.  
    <sub>about someone else (Original), not this stop</sub>
  - **R** Joan Miró Original prints: ...  
    <sub>names joan miro, joan, miro</sub>

**4. JOAN MIRO , René Char, Nous Avons, Paris, Louis Broder ...**  
`christies.com` · tier `market`  
> JOAN MIRO René Char, Nous Avons, Paris, Louis Broder, 1959 (D. 247-52; C. 53) the complete set of one unsigned woodcut, and five unsigned etchings with ...

  - **R** JOAN MIRO René Char, Nous Avons, Paris, Louis Broder, 1959 (D.  
    <sub>names louis broder, joan miro, broder</sub>
  - w 53) the complete set of one unsigned woodcut, and five unsigned etchings with ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**5. Louis Broder**  
`nga.gov` · tier `tier1`  
> Joan Miró, Louis Broder, Crommelynck and Dutrou · 1957 · color etching and aquatint on wove paper mounted to cardboard · Accession ID 2010.73.1. 1 of 3. Site ...

  - **R** Joan Miró, Louis Broder, Crommelynck and Dutrou · 1957 · color etching and aquatint on wove paper mounted to cardboard · Accession ID 2010.73.1.  
    <sub>names louis broder, joan miro, broder</sub>

**6. Joan Miró, Le Lézard aux Plumes d'or, Louis Broder éditeur**  
`books.google.com` · tier `unverified`  
> Bibliographic information ; Publisher, Berggruen, 1971 ; Original from, the University of California ; Digitized, Mar 18, 2009 ; Length, 24 pages.

  - **X** Bibliographic information ; Publisher, Berggruen, 1971 ; Original from, the University of California ; Digitized, Mar 18, 2009 ; Length, 24 pages.  
    <sub>about someone else (Bibliographic), not this stop</sub>

**7. Louis BRODER's album A : A legendary portfolio**  
`wdartgallery-modern.com` · tier `unverified`  
> A is an album taken from the tribute book to Paul Eluard "a poem in each book" published in 1956. Joan Miro, Album A hand-signed by the artist (for sale on the ...

  - **X** A is an album taken from the tribute book to Paul Eluard "a poem in each book" published in 1956.  
    <sub>about someone else (Paul Eluard), not this stop</sub>
  - **R** Joan Miro, Album A hand-signed by the artist (for sale on the ...  
    <sub>names joan miro, joan, miro</sub>

**8. [Louis BRODER]. - Lot 55**  
`pba-auctions.com` · tier `unverified`  
> Joan Miró, Pablo Picasso, Paris, Louis Broder, 1968. Unique edition of 115 copies of an album of ten original prints, - Joan MIRÓ. Pour Louis Broder, Joan Miró ...

  - **R** Joan Miró, Pablo Picasso, Paris, Louis Broder, 1968.  
    <sub>names louis broder, joan miro, broder</sub>
  - **R** Unique edition of 115 copies of an album of ten original prints, - Joan MIRÓ.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Pour Louis Broder, Joan Miró ...  
    <sub>names louis broder, joan miro, broder</sub>


## Query 7 — `Mourlot workshop history`

8 results · kind **active → active** · R9 w1 X2

**1. Mourlot Studios**  
`en.wikipedia.org` · tier `tier1`  
> Mourlot Studios was a commercial print shop founded in 1852 by the Mourlot family and located in Paris, France. It was also known as Imprimerie Mourlot, ...

  - **R** Mourlot Studios was a commercial print shop founded in 1852 by the Mourlot family and located in Paris, France.  
    <sub>names mourlot</sub>
  - **R** It was also known as Imprimerie Mourlot, ...  
    <sub>names mourlot</sub>

**2. About Mourlot Editions - The Prinkmakers of Picasso**  
`mourloteditions.com` · tier `unverified`  
> The first painters to create lithographs at the Mourlot Frères studio were Vlaminck and Utrillo, and for many years they would be the only ones. Further, he ...

  - **R** The first painters to create lithographs at the Mourlot Frères studio were Vlaminck and Utrillo, and for many years they would be the only ones.  
    <sub>names mourlot</sub>

**3. L'Atelier Mourlot: Masters of twentieth-century lithography**  
`kingandmcgaw.com` · tier `unverified`  
> Founded in Paris in 1852 by Francois Mourlot, l'Atelier Mourlot began as a producer of fine wallpaper. In 1914, his son Jules expanded the business to produce ...

  - **R** Founded in Paris in 1852 by Francois Mourlot, l'Atelier Mourlot began as a producer of fine wallpaper.  
    <sub>names mourlot</sub>
  - **X** In 1914, his son Jules expanded the business to produce ...  
    <sub>about someone else (Jules), not this stop</sub>

**4. Mourlot Editions | Fine Art Lithographs & Prints Since 1852**  
`mourloteditions.com` · tier `unverified`  
> Since 1852, Mourlot Editions has been synonymous with printmaking and lithography. We now offer our extensive inventory of fine art lithographs, prints, posters ...

  - **R** Since 1852, Mourlot Editions has been synonymous with printmaking and lithography.  
    <sub>names mourlot</sub>
  - w We now offer our extensive inventory of fine art lithographs, prints, posters ...  
    <sub>no entity of its own; snippet names mourlot</sub>

**5. Atelier Mourlot Biography**  
`masterworksfineart.com` · tier `unverified`  
> Atelier Mourlot's involvement in the art world began in the early 20th century when Fernand Mourlot purchased a printing press from an old lithographic workshop ...

  - **R** Atelier Mourlot's involvement in the art world began in the early 20th century when Fernand Mourlot purchased a printing press from an old lithographic workshop ...  
    <sub>names mourlot</sub>

**6. Ink, Stone, and Genius: The Secret Life of Atelier Mourlot**  
`printed-editions.com` · tier `unverified`  
> Inside Atelier Mourlot: the Paris print shop where Picasso and Chagall made lithography a fine art — and quietly rewrote art history.

  - **R** Inside Atelier Mourlot: the Paris print shop where Picasso and Chagall made lithography a fine art — and quietly rewrote art history.  
    <sub>names mourlot</sub>

**7. The Chemistry of Colour: Inside the Mourlot Frères Studio ...**  
`canonandrare.com` · tier `unverified`  
> Under the ambitious direction of Fernand Mourlot, this former 19th century commercial printing shop was converted into an epicentre of fine art ...

  - **R** Under the ambitious direction of Fernand Mourlot, this former 19th century commercial printing shop was converted into an epicentre of fine art ...  
    <sub>names mourlot</sub>

**8. Fernand Mourlot 1895–1988 - PrintChronicle.com**  
`printchronicle.com` · tier `unverified`  
> Mourlot's workshop was able to retain the monumental force of Rouault's imagery without losing its finer tonal details. Fernand Léger and Alexander Calder.

  - **R** Mourlot's workshop was able to retain the monumental force of Rouault's imagery without losing its finer tonal details.  
    <sub>names mourlot</sub>
  - **X** Fernand Léger and Alexander Calder.  
    <sub>about someone else (Fernand Léger), not this stop</sub>


## Query 8 — `Boris Fridman collection`

8 results · kind **inert → inert** · R8 w4 X3

**1. Boris Fridman: a Russian collector's pursuit of printed art**  
`artfocusnow.com` · tier `unverified`  
> Fridman's collection includes works by Pablo Picasso, Henri Matisse, Joan Miro and many others. As the collector points out, “they were not ...

  - **R** Fridman's collection includes works by Pablo Picasso, Henri Matisse, Joan Miro and many others.  
    <sub>names joan miro, fridman, joan</sub>
  - w As the collector points out, “they were not ...  
    <sub>no entity of its own; snippet names joan miro</sub>

**2. Boris Fridman - Managing Partner at Windsail Partners**  
`linkedin.com` · tier `reject`  
> I am a former CEO and entrepreneur turned investment banker. provides strategic M&A and capital advisory to companies in digital media, advertising, and ...

  - **X** I am a former CEO and entrepreneur turned investment banker.  
    <sub>names nothing belonging to this stop</sub>
  - **X** provides strategic M&A and capital advisory to companies in digital media, advertising, and ...  
    <sub>names nothing belonging to this stop</sub>

**3. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> The collections of artists' books amassed by Boris Friedman and George Gens are probably the fullest of their kind in Russia. showcased more than 30 books by ...

  - **R** The collections of artists' books amassed by Boris Friedman and George Gens are probably the fullest of their kind in Russia.  
    <sub>names boris</sub>
  - w showcased more than 30 books by ...  
    <sub>no entity of its own; snippet names boris</sub>

**4. Meet Dr. Boris Fridman - Absolute Smile**  
`myabsolutesmile.com` · tier `unverified`  
> His knowledge included areas of cosmetic dentistry, periodontal surgery, implant and laser dentistry, endodontics, and orthodontics.

  - **X** His knowledge included areas of cosmetic dentistry, periodontal surgery, implant and laser dentistry, endodontics, and orthodontics.  
    <sub>names nothing belonging to this stop</sub>

**5. Boris Friedman**  
`instagram.com` · tier `reject`  
> 1.3K+ followers · 2.4K+ following · 166 posts · @boris.friedman: “Travels | Photos | Music | Dreams”

  - **R** 1.3K+ followers · 2.4K+ following · 166 posts · @boris.friedman: “Travels | Photos | Music | Dreams”  
    <sub>names boris</sub>

**6. livre d'artiste, artist's book, exhibition catalogue**  
`cosmoscow.com` · tier `unverified`  
> Boris Fridman, collector of Livre. Boris Friedman's lecture “Collecting Livre d'Artiste Editions (What, How, Why?)” Livre d'artiste editions ...

  - **R** Boris Fridman, collector of Livre.  
    <sub>names boris fridman, fridman, boris</sub>
  - **R** Boris Friedman's lecture “Collecting Livre d'Artiste Editions (What, How, Why?)” Livre d'artiste editions ...  
    <sub>names boris</sub>

**7. Boris Fridman Obituary - Roswell, GA**  
`dignitymemorial.com` · tier `unverified`  
> Boris Fridman, age 32, of Roswell, Georgia passed away on Wednesday, April 19, 2023. A graveside service for Boris will be held Friday, April 21, 2023

  - **R** Boris Fridman, age 32, of Roswell, Georgia passed away on Wednesday, April 19, 2023.  
    <sub>names boris fridman, fridman, boris</sub>
  - **R** A graveside service for Boris will be held Friday, April 21, 2023  
    <sub>names boris</sub>

**8. The Collection Of Boris Fridman: Museum's Exhibitions**  
`arthive.com` · tier `unverified`  
> The Collection Of Boris Fridman: Museum's Exhibitions. The museum has not announced any exhibitions yet. For museums and galleries To collectors

  - **R** The Collection Of Boris Fridman: Museum's Exhibitions.  
    <sub>names boris fridman, fridman, boris</sub>
  - w The museum has not announced any exhibitions yet.  
    <sub>no entity of its own; snippet names boris fridman</sub>
  - w For museums and galleries To collectors  
    <sub>no entity of its own; snippet names boris fridman</sub>


## Query 9 — `Boris Fridman "Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" donation why`

0 results · kind **none → none** · R0 w0 X0

_(no results)_

## Query 10 — `Joan Miró "Le Lézard aux plumes d’or (The Lizard with Golden Feathers)" why created motivation`

8 results · kind **inert → inert** · R9 w1 X4

**1. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. Joan Miró. Cover front from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty lithographs ...

  - **R** Cover front from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty lithographs ...  
    <sub>about someone else (Lithograph), not this stop</sub>

**3. Joan Miró - Le Lézard aux plumes d'or (The Lizard with ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism. Bursting with vibrant ...

  - **R** Joan Miró Le lézard aux plumes d'or (The Lizard with Golden Feathers), 1971 is a dazzling example of the artist's poetic surrealism.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Bursting with vibrant ...  
    <sub>about someone else (Bursting), not this stop</sub>

**4. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró. These ...

  - **R** “Le Lézard aux Plumes d'or” (The Lizard with Golden Feathers) is a series of symbolic images based on poetic texts written by Miró.  
    <sub>names golden feathers, the lizard, le lezard</sub>

**5. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is ... created in 1971 as a vibrant fusion of poetry, printmaking, and sculptural

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is ...  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - w created in 1971 as a vibrant fusion of poetry, printmaking, and sculptural  
    <sub>no entity of its own; snippet names golden feathers</sub>

**6. Le Lézard aux plumes d'or – Poster Museum**  
`postermuseum.com` · tier `reject`  
> Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers). Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...

  - **R** Title: Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** Joan Miró (1893-1983) found notoriety through his Surrealist work mixed with occasional ...  
    <sub>names joan miro, joan, miro</sub>

**7. Joan Miró: Le Lézard aux Plumes d'Or - OUMA**  
`museum.oglethorpe.edu` · tier `tier1`  
> Joan Miró (1893-1983) Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) M. 446, 1967 Color lithograph on Japon paper 14” x 19 ½”

  - **R** Joan Miró (1893-1983) Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) M.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** 446, 1967 Color lithograph on Japon paper 14” x 19 ½”  
    <sub>about someone else (Color), not this stop</sub>

**8. Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or ...**  
`moma.org` · tier `tier1`  
> Joan Miró. Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers). 1971. Lithograph from an illustrated book with forty ...

  - **R** Plate (folio 20) from Le Lézard aux plumes d'or (The Lizard with Golden Feathers).  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **X** Lithograph from an illustrated book with forty ...  
    <sub>about someone else (Lithograph), not this stop</sub>


## Query 11 — `Louis Broder Mourlot collaboration`

8 results · kind **active → active** · R8 w1 X0

**1. Joan Miró's Broder Collection: How One Artist ...**  
`parkwestgallery.com` · tier `unverified`  
> In 1956, Broder began a partnership with Joan Miró alongside Atelier Mourlot, a world-famous French lithographic studio.

  - **R** In 1956, Broder began a partnership with Joan Miró alongside Atelier Mourlot, a world-famous French lithographic studio.  
    <sub>names joan miro, mourlot, broder</sub>

**2. Louis Broder, [Paris], 1971 – People - Toledo Museum of Art**  
`emuseum.toledomuseum.org` · tier `unverified`  
> Louis Broder, [Paris], 1971 · Books · lithographs: Mourlot, Paris (Jean Célestin, director); text: Fequet et Baudier, Paris; box: Jean Duval, Paris · Clear All ...

  - **R** Louis Broder, [Paris], 1971 · Books · lithographs: Mourlot, Paris (Jean Célestin, director); text: Fequet et Baudier, Paris; box: Jean Duval, Paris · Clear All ...  
    <sub>names louis broder, mourlot, broder</sub>

**3. Louis Broder**  
`nga.gov` · tier `tier1`  
> Explore selected works ; Untitled · Hans Bellmer, Louis Broder · 1967 · engraving in black on Rives wove paper ; Si je mourais là-bas (If I Died Over There), Page 47.

  - **R** Explore selected works ; Untitled · Hans Bellmer, Louis Broder · 1967 · engraving in black on Rives wove paper ; Si je mourais là-bas (If I Died Over There), Page 47.  
    <sub>names louis broder, broder, louis</sub>

**4. Louis Broder Auction Results: Historical Sales Records**  
`mutualart.com` · tier `market`  
> Get a complete overview of Broder's career: artworks for sale, auction results, market analytics, exhibitions, and articles from leading publications.

  - **R** Get a complete overview of Broder's career: artworks for sale, auction results, market analytics, exhibitions, and articles from leading publications.  
    <sub>names broder</sub>

**5. (#60) Joán Miró**  
`sothebys.com` · tier `market`  
> The prints are in good condition, the full sheets with fresh colors. Mourlot 527 and 528 with pale time-stain at the extreme sheet edges. Broder inventory ...

  - w The prints are in good condition, the full sheets with fresh colors.  
    <sub>no entity of its own; snippet names mourlot</sub>
  - **R** Mourlot 527 and 528 with pale time-stain at the extreme sheet edges.  
    <sub>names mourlot</sub>

**6. Preserved in Galerie Mourlot's Parisian archive until now, we're ...**  
`instagram.com` · tier `reject`  
> A stunning color lithograph on wove paper with the Miró watermark, published by Louis Broder and printed by the legendary Mourlot atelier in Paris.⁣ ⁣

  - **R** A stunning color lithograph on wove paper with the Miró watermark, published by Louis Broder and printed by the legendary Mourlot atelier in Paris.⁣ ⁣  
    <sub>names louis broder, mourlot, broder</sub>

**7. Louis BRODER's album A : A legendary portfolio**  
`wdartgallery-modern.com` · tier `unverified`  
> A is an album taken from the tribute book to Paul Eluard "a poem in each book" published in 1956 under the direction of the publisher Louis BRODER.

  - **R** A is an album taken from the tribute book to Paul Eluard "a poem in each book" published in 1956 under the direction of the publisher Louis BRODER.  
    <sub>names louis broder, broder, louis</sub>

**8. MASTERS & APPRENTICES | THE LAKEVIEW COLLECTION ...**  
`issuu.com` · tier `unverified`  
> Colour lithograph on Japan paper, 65.72 x 50.8cm Joan Miro collaborated with Louis Broder, an art publisher based in Paris, and created 4 suites of lithographs ...

  - **R** Colour lithograph on Japan paper, 65.72 x 50.8cm Joan Miro collaborated with Louis Broder, an art publisher based in Paris, and created 4 suites of lithographs ...  
    <sub>names louis broder, joan miro, broder</sub>


## Query 12 — `livre d'artiste Joan Miró`

8 results · kind **inert → inert** · R10 w1 X1

**1. Joan Miro - Tous les Peintres et monographies - Livre, BD - Fnac**  
`fnac.com` · tier `unverified`  
> La Fnac vous propose 70 références Tous les Peintres et monographies : Joan Miro avec la livraison chez vous en 1 jour ou en magasin avec -5% de réduction.

  - **R** La Fnac vous propose 70 références Tous les Peintres et monographies : Joan Miro avec la livraison chez vous en 1 jour ou en magasin avec -5% de réduction.  
    <sub>names joan miro, joan, miro</sub>

**2. Livre illustré Recent Paintings par MIRO Joan - Le Coin des Arts**  
`lecoindesarts.com` · tier `unverified`  
> Le catalogue comprend de nombreuses reproductions d'œuvres, dont six en couleurs, le tout imprimé à l'atelier Mourlot, l'un des meilleurs pour la lithographie.

  - **R** Le catalogue comprend de nombreuses reproductions d'œuvres, dont six en couleurs, le tout imprimé à l'atelier Mourlot, l'un des meilleurs pour la lithographie.  
    <sub>names mourlot</sub>

**3. Livre Joan Miró, les oeuvres de sa vie - Dosde**  
`dosde.com` · tier `unverified`  
> Ce livre rassemble les oeuvres les plus importantes de Joan Miró et aborde les étapes de création du peintre, considéré comme l'un des représentants majeurs ...

  - **R** Ce livre rassemble les oeuvres les plus importantes de Joan Miró et aborde les étapes de création du peintre, considéré comme l'un des représentants majeurs ...  
    <sub>names joan miro, joan, miro</sub>

**4. Joan Miró : Livres - Amazon.fr**  
`amazon.fr` · tier `unverified`  
> French Edition (20 livres) Joan Miro, artista silencioso/ silent artist Relié 5,95 €5,95€ … 35 € d'achat de livres expédiés par

  - **R** French Edition (20 livres) Joan Miro, artista silencioso/ silent artist Relié 5,95 €5,95€ … 35 € d'achat de livres expédiés par  
    <sub>names joan miro, joan, miro</sub>

**5. Joan Miro : La couleur des rêves - Sandrine Andrews - Babelio**  
`babelio.com` · tier `unverified`  
> Joan Miró a créé un monde fantaisiste, où se mêlent peinture et poésie. Ses tableaux, pleins de vie, sont peuplés de signes colorés et de formes fantastiques,

  - **R** Joan Miró a créé un monde fantaisiste, où se mêlent peinture et poésie.  
    <sub>names joan miro, joan, miro</sub>
  - w Ses tableaux, pleins de vie, sont peuplés de signes colorés et de formes fantastiques,  
    <sub>no entity of its own; snippet names joan miro</sub>

**6. Joan Miró - artiste - Galerie Lelong**  
`galerie-lelong.com` · tier `unverified`  
> Livres ; livre Ecrits et entretiens Joan Miró. Joan Miró : Ecrits et entretiens ; livre Femmes, oiseaux et monstres Joan Miró. Joan Miró : Femmes, oiseaux et ...

  - **R** Livres ; livre Ecrits et entretiens Joan Miró.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Joan Miró : Ecrits et entretiens ; livre Femmes, oiseaux et monstres Joan Miró.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Joan Miró : Femmes, oiseaux et ...  
    <sub>names joan miro, joan, miro</sub>

**7. A masterpiece of artistic collaboration. 'Parler seul. Poème' (1950) by Joan ...**  
`facebook.com` · tier `reject`  
> ... ⁠ 'Parler seul. Poème' (1950) by Joan Miró and Tristan Tzara is one of the most celebrated livres d'artistes of...

  - **R** Poème' (1950) by Joan Miró and Tristan Tzara is one of the most celebrated livres d'artistes of...  
    <sub>names joan miro, joan, miro</sub>

**8. Jiyoung Shim - Les livres illustrés de Joan Miró chez Maeght éditeur : de ...**  
`revue-textimage.com` · tier `unverified`  
> Parler seul est un ouvrage majeur de la démarche artistique de Miró dans le domaine du livre. D'une part, c'est la collaboration sa plus réussie avec Tzara, qui ...

  - **R** Parler seul est un ouvrage majeur de la démarche artistique de Miró dans le domaine du livre.  
    <sub>names miro</sub>
  - **X** D'une part, c'est la collaboration sa plus réussie avec Tzara, qui ...  
    <sub>about someone else (D'une), not this stop</sub>


## Query 13 — `"Le Lézard aux plumes d’or" Joan Miró`

8 results · kind **inert → inert** · R10 w1 X4

**1. Joan Miró - Le lézard aux plumes d'or**  
`choicecontemporary.com` · tier `unverified`  
> Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...

  - **R** Joan Miró's Le lézard aux plumes d'or (The Lizard with Golden Feathers) is one of the artist's most celebrated illustrated portfolios, created in 1971 as a ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**2. 557135 The Lizard with Golden Feathers Joan Miró**  
`coleccionbbva.com` · tier `unverified`  
> Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...

  - **R** Le Lézard aux Plumes d'Or (The Lizard with Golden Feathers) is considered one of the main pieces made by Miró that year for its extraordinary combination of two ...  
    <sub>names golden feathers, the lizard, le lezard</sub>

**3. Le Lézard aux Plumes d'Or (1971) by Joan Miró - For Sale**  
`artsy.net` · tier `market`  
> Joan Miró. ,. Le Lézard aux Plumes d'Or, 1971 · High auction record. US$53.5m, Christie's, 2026 · Blue-chip. Represented by internationally recognized galleries.

  - **R** Le Lézard aux Plumes d'Or, 1971 · High auction record.  
    <sub>names le lezard, plumes, lezard</sub>
  - **X** US$53.5m, Christie's, 2026 · Blue-chip.  
    <sub>about someone else (Christie's), not this stop</sub>
  - **X** Represented by internationally recognized galleries.  
    <sub>about someone else (Represented), not this stop</sub>

**4. Le Lézard aux plumes d'or (The Lizard with Golden Feathers)**  
`moma.org` · tier `tier1`  
> Le Lézard aux plumes d'or (The Lizard with. Golden Feathers). These works are part of an illustrated book. 40 works online. Joan Miró.

  - **R** Le Lézard aux plumes d'or (The Lizard with.  
    <sub>names the lizard, le lezard, plumes</sub>
  - **X** These works are part of an illustrated book.  
    <sub>about someone else (These), not this stop</sub>

**5. Joan Miró, Le lezard aux plumes d'or (The Lizard ...**  
`masterworksfineart.com` · tier `unverified`  
> Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no. 515 ; Joan Miró (1893 - 1983) · Etching ...

  - **R** Joan Miró, Le lezard aux plumes d'or (The Lizard with Golden Feathers), 1967, no.  
    <sub>names golden feathers, the lizard, le lezard</sub>
  - **R** 515 ; Joan Miró (1893 - 1983) · Etching ...  
    <sub>names joan miro, joan, miro</sub>

**6. 177: JOAN MIRÓ, Untitled (from Le lezard aux plumes d'or ...**  
`ragoarts.com` · tier `unverified`  
> Lot 177: Joan Miró 1893–1983. Untitled (from Le lezard aux plumes d'or series). 1971, lithograph in colors on Kochi Japan.

  - **R** Lot 177: Joan Miró 1893–1983.  
    <sub>names joan miro, joan, miro</sub>
  - **R** Untitled (from Le lezard aux plumes d'or series).  
    <sub>names le lezard, plumes, lezard</sub>
  - **X** 1971, lithograph in colors on Kochi Japan.  
    <sub>about someone else (Kochi Japan), not this stop</sub>

**7. Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris ...**  
`christies.com` · tier `market`  
> JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M. 789-828; C. books 148) the complete set of fifteen lithographs in colors, ...

  - **R** JOAN MIRO Joan Miró, Le Lézard aux Plumes d'Or, Louis Broder, Paris, 1971 (M.  
    <sub>names louis broder, le lezard, joan miro</sub>
  - w books 148) the complete set of fifteen lithographs in colors, ...  
    <sub>no entity of its own; snippet names louis broder</sub>

**8. Joan Miró - Le Lezard aux Plumes d'Or**  
`nationalgalleries.org` · tier `unverified`  
> This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.

  - **R** This is from a series of 15 colour lithographs based on Joan Miró's poem and surrealist fantasy, Le Lézard aux Plumes d'or.  
    <sub>names le lezard, joan miro, plumes</sub>


## Query 14 — `Museum of Fine Arts, Boston Joan Miró donation history`

8 results · kind **active → active** · R7 w1 X6

**1. Picasso, Miró, Dalí: Unbound**  
`mfa.org` · tier `tier1`  
> Lead support is provided by the Jean S. and Frederic A. Sharf Exhibition Fund. Major support is provided by the Lia and William Poorvu Fund and ...

  - **X** Lead support is provided by the Jean S.  
    <sub>about someone else (Lead), not this stop</sub>
  - **X** Sharf Exhibition Fund.  
    <sub>about someone else (Sharf Exhibition Fund), not this stop</sub>
  - **X** Major support is provided by the Lia and William Poorvu Fund and ...  
    <sub>about someone else (Major), not this stop</sub>

**2. Museum of Fine Arts, Boston**  
`facebook.com` · tier `reject`  
> At the turn of the 20th century, they revolutionized the book as an art form and attracted many famous practitioners—Pablo Picasso, Joan Miró, ...

  - **R** At the turn of the 20th century, they revolutionized the book as an art form and attracted many famous practitioners—Pablo Picasso, Joan Miró, ...  
    <sub>names joan miro, joan, miro</sub>

**3. First-Ever Salvador Dalí Exhibition at the Museum ...**  
`mfa.org` · tier `tier1`  
> On a trip to Paris in 1929, Dalí connected with the Surrealist group through another Catalan artist, Joan Miró. is 100 years old. from the ...

  - **R** On a trip to Paris in 1929, Dalí connected with the Surrealist group through another Catalan artist, Joan Miró.  
    <sub>names joan miro, joan, miro</sub>

**4. JARED'S PICKS FOR 8/22-23 1) Picasso, Miró, Dalí: ...**  
`instagram.com` · tier `reject`  
> Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs. Photograph © Museum of Fine Arts, Boston Poemes

  - **R** Joan Miró (Spanish, 1893–1983) 1971 Illustrated book with forty color lithographs.  
    <sub>names joan miro, joan, miro</sub>
  - **X** Photograph © Museum of Fine Arts, Boston Poemes  
    <sub>about someone else (Photograph), not this stop</sub>

**5. Museum of Fine Arts Boston | Boston's Art Museum**  
`mfa.org` · tier `tier1`  
> Give to the MFA Planned Giving. Picasso, Miró, Dalí: Museum purchase with funds by exchange from the Gift of Laurence K. and Lorna J. Marshall.

  - **X** Give to the MFA Planned Giving.  
    <sub>about someone else (Give), not this stop</sub>
  - **R** Picasso, Miró, Dalí: Museum purchase with funds by exchange from the Gift of Laurence K.  
    <sub>names miro, gift</sub>

**6. Picasso, Miró and Dalí reinvent the book as a work of art at ...**  
`bonart.cat` · tier `unverified`  
> The exhibition brings together some of the most outstanding contributions of Pablo Picasso, Joan Miró, and Salvador Dalí to this genre, which ...

  - **R** The exhibition brings together some of the most outstanding contributions of Pablo Picasso, Joan Miró, and Salvador Dalí to this genre, which ...  
    <sub>names joan miro, joan, miro</sub>

**7. Joan Miro | Icon of 20th Century Modernism**  
`dtrmodern.com` · tier `unverified`  
> Fundació Joan Miró in Barcelona, founded with a substantial donation of works from his family.

  - **R** Fundació Joan Miró in Barcelona, founded with a substantial donation of works from his family.  
    <sub>names joan miro, joan, miro</sub>

**8. ✨ JARED'S PICKS FOR 8/22-23✨ 1) Picasso, Miró, Dalí: ...**  
`facebook.com` · tier `reject`  
> We started the Museum of Fine Arts for very interesting new show. It's called Picasso Miro Dali Unbound. The show is about artists books but we ...

  - **X** We started the Museum of Fine Arts for very interesting new show.  
    <sub>about someone else (Museum), not this stop</sub>
  - **R** It's called Picasso Miro Dali Unbound.  
    <sub>names miro</sub>
  - w The show is about artists books but we ...  
    <sub>no entity of its own; snippet names miro</sub>


## GEMINI (grounded) — full matrix, D366 framing

kind **eventful → eventful** · R5 w0 X0

> Joan Miró created *Le Lézard aux plumes d’or* as a visual companion to his own surrealist poetry, which he hand-wrote across the project's pages.
> 
> The book was originally conceived and printed in 1967, but Miró and publisher Louis Broder noticed that a manufacturing defect in the paper altered the colors.
> 
> Because of the defective paper, Miró and Broder decided to reject and completely destroy the original 1967 print run.
> 
> Since the original lithographic stones had already been effaced after the initial run, Miró was forced to redraw the entire series from scratch. 
> 
> The finalized edition was printed by Mourlot Frères and released in 1971, delaying the project's completion by four years.

  - **R** Joan Miró created *Le Lézard aux plumes d’or* as a visual companion to his own surrealist poetry, which he hand-wrote across the project's pages.  
    <sub>names le lezard aux plumes d’or, le lezard, joan miro</sub>
  - **R** The book was originally conceived and printed in 1967, but Miró and publisher Louis Broder noticed that a manufacturing defect in the paper altered the colors.  
    <sub>names louis broder, broder, louis</sub>
  - **R** Because of the defective paper, Miró and Broder decided to reject and completely destroy the original 1967 print run.  
    <sub>names broder, miro</sub>
  - **R** Since the original lithographic stones had already been effaced after the initial run, Miró was forced to redraw the entire series from scratch.  
    <sub>names miro</sub>
  - **R** The finalized edition was printed by Mourlot Frères and released in 1971, delaying the project's completion by four years.  
    <sub>names mourlot</sub>


---

# Au Soleil du Plafond


## Query 1 — `"Au Soleil du Plafond" Juan Gris story visitors Picasso, Miró, Dalí: Unbound`

8 results · kind **eventful → eventful** · R12 w0 X9

**1. Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston**  
`thehistoryofart.org` · tier `unverified`  
> Juan Gris and the French poet Pierre Reverdy's Au Soleil du Plafond from 1955 show another, where artist and writer work in closer harmony from the outset.

  - **R** Juan Gris and the French poet Pierre Reverdy's Au Soleil du Plafond from 1955 show another, where artist and writer work in closer harmony from the outset.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**2. ✨ JARED’S PICKS FOR 8/22-23✨ 1) Picasso, Miró, Dalí ...**  
`instagram.com` · tier `reject`  
> Au Soleil du Plafond: hard shell box. Juan Gris (Spanish (worked in France), 1887–1927) 1955. Illustrated book with twelve lithographs * Gift of ...

  - **R** Au Soleil du Plafond: hard shell box.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris (Spanish (worked in France), 1887–1927) 1955.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Illustrated book with twelve lithographs * Gift of ...  
    <sub>about someone else (Illustrated), not this stop</sub>

**3. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> Picasso, Miró, Dali: Unbound, through January 24, 2027. Donna Ferrato: 'Living ... Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).

  - **X** Picasso, Miró, Dali: Unbound, through January 24, 2027.  
    <sub>about someone else (Picasso), not this stop</sub>
  - **X** Donna Ferrato: 'Living ...  
    <sub>about someone else (Donna Ferrato), not this stop</sub>
  - **R** Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**4. Gris and Reverdy's Au soleil du plafond**  
`araderbooks.com` · tier `unverified`  
> Au soleil du plafond was José Victoriano González-Pérez (pseud. Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...

  - **R** Au soleil du plafond was José Victoriano González-Pérez (pseud.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...  
    <sub>names juan gris, juan, gris</sub>

**5. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> Picasso, Miró, Dali: Unbound. Museum of Fine Arts, Boston. location_onBack Bay ... Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).

  - **X** Picasso, Miró, Dali: Unbound.  
    <sub>about someone else (Picasso), not this stop</sub>
  - **X** Museum of Fine Arts, Boston.  
    <sub>about someone else (Museum), not this stop</sub>
  - **X** location_onBack Bay ...  
    <sub>about someone else (Back Bay), not this stop</sub>
  - **R** Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond (1955).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**6. GBH News | Accountability, or political coverup? GBH News ...**  
`instagram.com` · tier `reject`  
> 1) Picasso, Miró, Dalí: Unbound at the @mfaboston 2) DTF St ... Au Soleil du Plafond: hard shell box. Juan Gris (Spanish (worked in ...

  - **X** 1) Picasso, Miró, Dalí: Unbound at the @mfaboston 2) DTF St ...  
    <sub>about someone else (Picasso), not this stop</sub>
  - **R** Au Soleil du Plafond: hard shell box.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris (Spanish (worked in ...  
    <sub>names juan gris, juan, gris</sub>

**7. GBH News | There have been multiple sightings of great white ...**  
`instagram.com` · tier `reject`  
> 1) Picasso, Miró, Dalí: Unbound at the @mfaboston 2) DTF St ... Au Soleil du Plafond: hard shell box. Juan Gris (Spanish (worked in ...

  - **X** 1) Picasso, Miró, Dalí: Unbound at the @mfaboston 2) DTF St ...  
    <sub>about someone else (Picasso), not this stop</sub>
  - **R** Au Soleil du Plafond: hard shell box.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris (Spanish (worked in ...  
    <sub>names juan gris, juan, gris</sub>

**8. Coming Attractions: July 19 Through August 3 - What Will ...**  
`artsfuse.org` · tier `unverified`  
> The MFA's exhibition Picasso, Miró, Dalí: Unbound, which opens on ... Au Soleil du Plafond (1955), the product of a close collaboration ...

  - **X** The MFA's exhibition Picasso, Miró, Dalí: Unbound, which opens on ...  
    <sub>about someone else (The MFA's), not this stop</sub>
  - **R** Au Soleil du Plafond (1955), the product of a close collaboration ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>


## Query 2 — `"Au Soleil du Plafond" Juan Gris`

8 results · kind **eventful → eventful** · R13 w0 X3

**1. Designed by Juan Gris - Au Soleil du Plafond**  
`metmuseum.org` · tier `tier1`  
> Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)

  - **R** Au Soleil du Plafond; Designer: Designed by Juan Gris (Spanish, Madrid 1887–1927 Boulogne-sur-Seine); Author: Written by Pierre Reverdy (French, 1889–1960)  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**2. AFTER JUAN GRIS (1887-1927), Au Soleil du Plafond**  
`onlineonly.christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...

  - **R** AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**3. Gris and Reverdy's Au soleil du plafond**  
`araderbooks.com` · tier `unverified`  
> Au soleil du plafond was José Victoriano González-Pérez (pseud. Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...

  - **R** Au soleil du plafond was José Victoriano González-Pérez (pseud.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris, 1887–1927) final body of work, as he died of kidney failure at only 40 years old in ...  
    <sub>names juan gris, juan, gris</sub>

**4. Juan Gris, 'Pierre Reverdy. Au soleil du plafond Paris ...**  
`artsy.net` · tier `market`  
> Juan Gris. ,. Pierre Reverdy. Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery. Zürich ; High auction record. £34.8m, Christie's, 2014.

  - **R** Au soleil du plafond Paris, Tériade Éditeur, 1955 ; Lechbinska Gallery.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>
  - **X** Zürich ; High auction record.  
    <sub>about someone else (Zürich), not this stop</sub>
  - **X** £34.8m, Christie's, 2014.  
    <sub>about someone else (Christie's), not this stop</sub>

**5. Au Soleil du Plafond - First Edition - Signed - Pierre Reverdy**  
`baumanrarebooks.com` · tier `unverified`  
> Au Soleil du Plafond rare book for sale. This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.

  - **R** Au Soleil du Plafond rare book for sale.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** This First Edition, Signed by Pierre REVERDY, Juan GRIS is available at Bauman Rare Books.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>

**6. Au soleil du plafond - Juan GRIS (Jose Victoriano ...**  
`musee-lam.fr` · tier `unverified`  
> ... Juan GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY. 1955. Au soleil du plafond ... Juan Gris, Paris, Tériade (Verve), 1955 Lithographie sur ...

  - **R** Juan GRIS (Jose Victoriano GONZALES PEREZ, dit) ou Pierre REVERDY.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** Au soleil du plafond ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris, Paris, Tériade (Verve), 1955 Lithographie sur ...  
    <sub>names juan gris, teriade, verve</sub>

**7. Au soleil du plafond**  
`artvee.com` · tier `unverified`  
> View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.

  - **R** View Au soleil du plafond by Juan Gris and other public domain artworks on Artvee.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**8. 263 - Au Soleil du Plafond - GRIS, Juan (b.1887-1927)**  
`portal.sds.ox.ac.uk` · tier `tier1`  
> Book ID. 263 ; Title Of Work. Au Soleil du Plafond ; Artist Name. GRIS, Juan (b.1887-1927) ; OLIS Call number ?? ; Provenance: Old Printed Catalogue ...

  - **R** Au Soleil du Plafond ; Artist Name.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** GRIS, Juan (b.1887-1927) ; OLIS Call number ??  
    <sub>names juan, gris</sub>
  - **X** ; Provenance: Old Printed Catalogue ...  
    <sub>about someone else (Provenance), not this stop</sub>


## Query 3 — `"Au Soleil du Plafond" history`

8 results · kind **eventful → eventful** · R10 w1 X4

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

**3. AFTER JUAN GRIS (1887-1927), Au Soleil du Plafond | Christie's**  
`onlineonly.christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...

  - **R** AFTER JUAN GRIS (1887-1927) Au Soleil du Plafond the complete deluxe portfolio comprising 11 lithographs in colors on Arches wove paper, with the additional ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**4. Au soleil du plafond by Gris, Juan; Pierre Reverdy: Very Good ...**  
`abebooks.com` · tier `market`  
> Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.

  - **R** Title: Au soleil du plafond ; Publisher: Tériade Éditeur, Paris ; Publication Date: 1955 ; Binding: Hardcover ; Edition: First edition.  
    <sub>names au soleil du plafond, au soleil, teriade</sub>

**5. 263 - Au Soleil du Plafond - GRIS, Juan (b.1887-1927)**  
`portal.sds.ox.ac.uk` · tier `tier1`  
> Book ID. 263 ; Title Of Work. Au Soleil du Plafond ; Artist Name. GRIS, Juan (b.1887-1927) ; OLIS Call number ?? ; Provenance: Old Printed Catalogue ...

  - **R** Au Soleil du Plafond ; Artist Name.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** GRIS, Juan (b.1887-1927) ; OLIS Call number ??  
    <sub>names juan, gris</sub>
  - **X** ; Provenance: Old Printed Catalogue ...  
    <sub>about someone else (Provenance), not this stop</sub>

**6. Juan Gris: Au soleil du plafond | Buy prints | engravings | lithography ...**  
`galerialaaurora.com` · tier `unverified`  
> History · La Aurora in the press · what's graphic ... History · La Aurora in the press · Events · Whatsapp ... Juan Gris: Au soleil du plafond. Juan Gris , buy ...

  - **X** History · La Aurora in the press · what's graphic ...  
    <sub>about someone else (History), not this stop</sub>
  - **X** History · La Aurora in the press · Events · Whatsapp ...  
    <sub>about someone else (History), not this stop</sub>
  - **R** Juan Gris: Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**7. Exposición Juan Gris : au soleil du plafond - Facebook**  
`facebook.com` · tier `reject`  
> Exposición Juan Gris : au soleil du plafond · Public · Hosted by Galería La Aurora · Thursday 7 September 2023 at 12:00 CEST · Plaza de la Aurora, 30001 Murcia ( ...

  - **R** Exposición Juan Gris : au soleil du plafond · Public · Hosted by Galería La Aurora · Thursday 7 September 2023 at 12:00 CEST · Plaza de la Aurora, 30001 Murcia ( ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**8. Reproduction Au soleil du plafond – Juan Gris | Artem Legrand**  
`artemlegrand.com` · tier `unverified`  
> Reproduction of the painting Au soleil du plafond - Juan Gris ; Free shipping on orders over €45. At your home within 3 to 8 business days ; Money-back guarantee.

  - **R** Reproduction of the painting Au soleil du plafond - Juan Gris ; Free shipping on orders over €45.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - **X** At your home within 3 to 8 business days ; Money-back guarantee.  
    <sub>about someone else (Money-back), not this stop</sub>


## Query 4 — `Pierre Reverdy Juan Gris`

8 results · kind **active → active** · R9 w1 X2

**1. Still Life with a Poem - Wikipedia**  
`en.wikipedia.org` · tier `tier1`  
> Pierre Reverdy, one of the greatest modern French poets, was born in 1889 and died in 1960. Like Gris, his work is well known and instantly recognizable.

  - **R** Pierre Reverdy, one of the greatest modern French poets, was born in 1889 and died in 1960.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Like Gris, his work is well known and instantly recognizable.  
    <sub>names gris</sub>

**2. Juan Gris - The Fruit Bowl - The Metropolitan Museum of Art**  
`metmuseum.org` · tier `tier1`  
> Gris collaborated with his friend, the poet Pierre Reverdy, on a commissioned book, but the project stalled during World War I and remained unfinished...

  - **R** Gris collaborated with his friend, the poet Pierre Reverdy, on a commissioned book, but the project stalled during World War I and remained unfinished...  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**3. Still Life with a Poem - Pasadena - Norton Simon Museum**  
`nortonsimon.org` · tier `unverified`  
> a poem written by the artist's friend Pierre Reverdy, for whose collection of abstract prose poems Gris painted a set of watercolor illustrations.

  - **R** a poem written by the artist's friend Pierre Reverdy, for whose collection of abstract prose poems Gris painted a set of watercolor illustrations.  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**4. The Cubist Poetry of Pierre Reverdy - Bureau of Public Secrets**  
`bopsecrets.org` · tier `unverified`  
> Juan Gris was Pierre Reverdy's favorite illustrator, as he in turn was the painter's favorite poet. being the most Cubist of the Cubists.

  - **R** Juan Gris was Pierre Reverdy's favorite illustrator, as he in turn was the painter's favorite poet.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **X** being the most Cubist of the Cubists.  
    <sub>about someone else (Cubist), not this stop</sub>

**5. Pierre Reverdy, Au Soleil du Plafond, Tériade Editeur, Paris, 1955**  
`christies.com` · tier `market`  
> AFTER JUAN GRIS (1887-1927) complete set of 11 lithographs in colors, 1916-17, on Arches, these lithographs were produced in 1955 after gouaches 1916-17.

  - **R** AFTER JUAN GRIS (1887-1927) complete set of 11 lithographs in colors, 1916-17, on Arches, these lithographs were produced in 1955 after gouaches 1916-17.  
    <sub>names juan gris, juan, gris</sub>

**6. Pierre Reverdy. Au soleil du plafond Paris, Tériade … (1955) by Juan Gris**  
`artsy.net` · tier `market`  
> Pioneering Cubist painter Juan Gris approached his canvases with a rigorous, mathematical attention to composition; he rendered discrete forms with precision ...

  - **R** Pioneering Cubist painter Juan Gris approached his canvases with a rigorous, mathematical attention to composition; he rendered discrete forms with precision ...  
    <sub>names juan gris, juan, gris</sub>

**7. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> The poet Pierre Reverdy is reputed to have said, “From 1910 to 1914 I learned the cubist lesson.” I've yet to find out what lesson he felt he ...

  - **R** The poet Pierre Reverdy is reputed to have said, “From 1910 to 1914 I learned the cubist lesson.” I've yet to find out what lesson he felt he ...  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**8. Juan Gris, Portrait de Pierre Reverdy, 1918 - Fondation Maeght**  
`fondation-maeght.com` · tier `unverified`  
> Juan Gris, Portrait de Pierre Reverdy, 1918 - Fondation. The Fondation is open everyday from 10:00 a.m.–6:00 p.m. Tel: +33 (0)4 93 32 81 63

  - **R** Juan Gris, Portrait de Pierre Reverdy, 1918 - Fondation.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **X** The Fondation is open everyday from 10:00 a.m.–6:00 p.m.  
    <sub>about someone else (The Fondation), not this stop</sub>
  - w Tel: +33 (0)4 93 32 81 63  
    <sub>no entity of its own; snippet names pierre reverdy</sub>


## Query 5 — `Pierre Reverdy Juan Gris relationship why collaborated`

8 results · kind **inert → inert** · R11 w2 X1

**1. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> ... Gris painting pointed the way. I knew of Reverdy from O'Hara and Ashbery, but I had no idea of Reverdy's collaboration with Gris. So, once ...

  - **R** Gris painting pointed the way.  
    <sub>names gris</sub>
  - **R** I knew of Reverdy from O'Hara and Ashbery, but I had no idea of Reverdy's collaboration with Gris.  
    <sub>names reverdy, gris</sub>

**2. The Cubist Poetry of Pierre Reverdy**  
`bopsecrets.org` · tier `unverified`  
> Juan Gris was Pierre Reverdy's favorite illustrator, as he in turn was the painter's favorite poet. No one today would deny that they share the distinction of ...

  - **R** Juan Gris was Pierre Reverdy's favorite illustrator, as he in turn was the painter's favorite poet.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - w No one today would deny that they share the distinction of ...  
    <sub>no entity of its own; snippet names pierre reverdy</sub>

**3. Still Life with a Poem**  
`en.wikipedia.org` · tier `tier1`  
> His collaborative work with still-life paintings ended in 1927, due to the death of his peer, Gris. Like Gris, Reverdy worked closely with Pablo Picasso and ...

  - **R** His collaborative work with still-life paintings ended in 1927, due to the death of his peer, Gris.  
    <sub>names gris</sub>
  - **R** Like Gris, Reverdy worked closely with Pablo Picasso and ...  
    <sub>names reverdy, gris</sub>

**4. Juan Gris, notes of biography, gallery Champetier**  
`mchampetier.com` · tier `unverified`  
> Juan Gris sculpts, makes collages, illustrates works of poets (Pierre Reverdy, Tristan Tzara, etc.). In 1912, Juan Gris participates in the Salon des ...

  - **R** Juan Gris sculpts, makes collages, illustrates works of poets (Pierre Reverdy, Tristan Tzara, etc.).  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** In 1912, Juan Gris participates in the Salon des ...  
    <sub>names juan gris, juan, gris</sub>

**5. Juan Gris - The Fruit Bowl**  
`metmuseum.org` · tier `tier1`  
> Gris collaborated with his friend, the poet Pierre Reverdy, on a commissioned book, but the project stalled during World War I and remained unfinished...

  - **R** Gris collaborated with his friend, the poet Pierre Reverdy, on a commissioned book, but the project stalled during World War I and remained unfinished...  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**6. Juan Gris, Portrait de Pierre Reverdy, 1918**  
`fondation-maeght.com` · tier `unverified`  
> Juan Gris, Portrait de Pierre Reverdy, 1918 ... The Fondation is open everyday from 10:00 a.m.–6:00 p.m. (10:00 a.m.–7:00 p.m july - august).

  - **R** Juan Gris, Portrait de Pierre Reverdy, 1918 ...  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **X** The Fondation is open everyday from 10:00 a.m.–6:00 p.m.  
    <sub>about someone else (The Fondation), not this stop</sub>
  - w (10:00 a.m.–7:00 p.m july - august).  
    <sub>no entity of its own; snippet names pierre reverdy</sub>

**7. The “Cubist” Poetry of Pierre Reverdy**  
`jstor.org` · tier `tier2`  
> by E Howe · 2014 · Cited by 4 — Most evaluations of the connections between Reverdy's poetry and Cubism either dwell exclusively on the notion of geometrical shapes and typographical.

  - **R** by E Howe · 2014 · Cited by 4 — Most evaluations of the connections between Reverdy's poetry and Cubism either dwell exclusively on the notion of geometrical shapes and typographical.  
    <sub>names reverdy</sub>

**8. Au soleil du plafond – Works – eMuseum - Toledo Museum**  
`emuseum.toledomuseum.org` · tier `unverified`  
> The project began in 1916 as a collaboration between Juan Gris and poet Pierre Reverdy: Gris would supply 20 images; Reverdy 20 prose poems.

  - **R** The project began in 1916 as a collaboration between Juan Gris and poet Pierre Reverdy: Gris would supply 20 images; Reverdy 20 prose poems.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>


## Query 6 — `Juan Gris "Au Soleil du Plafond" why created motivation`

8 results · kind **inert → inert** · R12 w5 X4

**1. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>

**2. (PDF) The cubism of Juan Gris. Vol II. Portraits. Pierrots & Harlequins ...**  
`academia.edu` · tier `tier1`  
> ... Au soleil du plafond. The idea for this collaboration between 29 Miguel Orozco Juan Gris. Vol II. Portraits. Pierrots, Drawings, Books, etc Gris and Reverly ...

  - **R** Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** The idea for this collaboration between 29 Miguel Orozco Juan Gris.  
    <sub>names juan gris, juan, gris</sub>
  - **R** Pierrots, Drawings, Books, etc Gris and Reverly ...  
    <sub>names gris</sub>

**3. Juan Gris - Canvas Prints & Wall Art - iCanvas**  
`icanvas.com` · tier `unverified`  
> Motivational Art All Subjects ... The Guitar, illustration for the poem 'Au soleil du plafond', by Pierre Reverdy Juan Gris.

  - **X** Motivational Art All Subjects ...  
    <sub>about someone else (Motivational Art All Subjects), not this stop</sub>
  - **R** The Guitar, illustration for the poem 'Au soleil du plafond', by Pierre Reverdy Juan Gris.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**4. [PDF] Untitled - Borges Center**  
`borges.pitt.edu` · tier `tier1`  
> Juan Gris. Paris: Gallimard, 1946. Reverdy, Pierre. Au Soleil du plafond et autres poèmes. ... created from language ordered in a certain way ... motivation behind ...

  - **X** Paris: Gallimard, 1946.  
    <sub>about someone else (Paris), not this stop</sub>
  - **R** Au Soleil du plafond et autres poèmes.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w created from language ordered in a certain way ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - w motivation behind ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**5. The cubism of Juan Gris. Vol I. Still lifes, landscapes - Academia.edu**  
`academia.edu` · tier `tier1`  
> ... Juan Gris, Au soleil du plafond, Paris, 1955, repr. plate 8 among a serie of ... His foresight as a patron made his collection a target for the rising ...

  - **R** Juan Gris, Au soleil du plafond, Paris, 1955, repr.  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>
  - w plate 8 among a serie of ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - w His foresight as a patron made his collection a target for the rising ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**6. (PDF) Textual Spaces: The Poetry of Pierre Reverdy - ResearchGate**  
`researchgate.net` · tier `unverified`  
> This 'ideelle Motivation' is recognised ... anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.

  - **X** This 'ideelle Motivation' is recognised ...  
    <sub>about someone else (Motivation'), not this stop</sub>
  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>

**7. LES RECUEILS ILLUSTRÉS DE PIERRE REVERDY - jstor**  
`jstor.org` · tier `tier2`  
> Au soleil du plafond, 11 lithographies en couleurs d'apres des oeuvres de Juan Gris, texte de Pierre Reverdy manuscrit lithographie, [Paris], Teriade, 1955 ...

  - **R** Au soleil du plafond, 11 lithographies en couleurs d'apres des oeuvres de Juan Gris, texte de Pierre Reverdy manuscrit lithographie, [Paris], Teriade, 1955 ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**8. Juan Gris (Art Ebook) | PDF | Aesthetics | Paintings - Scribd**  
`scribd.com` · tier `unverified`  
> Reverdy, Pierre: Au soleil du plafond. Paris. Teriade, 1956. in .in English translation in ''The Transatlantic Review", New York, I. Jul) I924,pages 182-486 ...

  - **R** Reverdy, Pierre: Au soleil du plafond.  
    <sub>names au soleil du plafond, au soleil, reverdy</sub>
  - **X** in .in English translation in ''The Transatlantic Review", New York, I.  
    <sub>about someone else (English), not this stop</sub>
  - w Jul) I924,pages 182-486 ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>


## Query 7 — `"Au Soleil du Plafond" Pierre Reverdy why chose subject`

8 results · kind **active → active** · R12 w3 X2

**1. A Cubist Glimpse | Prufrock's Dilemma - WordPress.com**  
`prufrocksdilemma.wordpress.com` · tier `unverified`  
> Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...

  - **R** Each of the poems in his collection Au Soleil du plafond refers to a still life by Juan Gris, one of which, Compotier (The Fruit Bowl), is ...  
    <sub>names au soleil du plafond, au soleil, juan gris</sub>

**2. Livre d'Artiste | The Tretyakov Gallery Magazine**  
`tretyakovgallerymagazine.com` · tier `unverified`  
> A double-page spread from the book Pierre Reverdy. Au Soleil du plafond Paris, 1955. A colour lithograph by Juan Gris. 42 x 64 cm.

  - **R** A double-page spread from the book Pierre Reverdy.  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond Paris, 1955.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** A colour lithograph by Juan Gris.  
    <sub>names juan gris, juan, gris</sub>

**3. (PDF) Textual Spaces: The Poetry of Pierre Reverdy - ResearchGate**  
`researchgate.net` · tier `unverified`  
> anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the. destructive wind: Le vent noir qui tordait les ...

  - **R** anxiety in 'La Lampe' (Au soleil du plafond) about the possible extinction of the lamp by the.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w destructive wind: Le vent noir qui tordait les ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**4. Transforming the Horizon: Reverdy's World War I - jstor**  
`jstor.org` · tier `tier2`  
> Asp Au soleil du plafond et autres po?mes (Paris ... He chose to retreat during the I920S in a ... Pierre Reverdy a choisi de s'abstenir de publier ...

  - **R** Asp Au soleil du plafond et autres po?mes (Paris ...  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - w He chose to retreat during the I920S in a ...  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>
  - **R** Pierre Reverdy a choisi de s'abstenir de publier ...  
    <sub>names pierre reverdy, reverdy, pierre</sub>

**5. Dan Bellm - Yetzirah | a hearth for Jewish poetry**  
`yetzirahpoets.org` · tier `unverified`  
> Sun on the Ceiling / Au soleil du plafond, Pierre Reverdy (San Francisco Center for the Book, 2011). Author Site. Author Site. Links to Sample Works. Voetica ...

  - **R** Sun on the Ceiling / Au soleil du plafond, Pierre Reverdy (San Francisco Center for the Book, 2011).  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>
  - **X** Links to Sample Works.  
    <sub>about someone else (Links), not this stop</sub>

**6. [PDF] Untitled - Borges Center**  
`borges.pitt.edu` · tier `tier1`  
> Reverdy, Pierre. Au Soleil du plafond et autres poèmes. ... Dostoevsky chose to use a first-person narrator who identifies himself ... subject of recrimina-.

  - **R** Au Soleil du plafond et autres poèmes.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **X** Dostoevsky chose to use a first-person narrator who identifies himself ...  
    <sub>about someone else (Dostoevsky), not this stop</sub>
  - w subject of recrimina-.  
    <sub>no entity of its own; snippet names au soleil du plafond</sub>

**7. Juan Gris • Buy exclusive fine art prints online - MeisterDrucke**  
`meisterdrucke.us` · tier `unverified`  
> ... The Guitar, illustration for the poem “Au soleil du plafond” by Pierre Reverdy (1889-1960), 1955. Juan Gris. Choose picture ...

  - **R** The Guitar, illustration for the poem “Au soleil du plafond” by Pierre Reverdy (1889-1960), 1955.  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**8. [PDF] Objects Observed - The Poetry of Things in Twentieth - dokumen.pub**  
`dokumen.pub` · tier `unverified`  
> Pierre Reverdy (1889–1960) is one of the twentieth-century French po ... Au Soleil du plafond, see Rothwell, “Cubism and the Avant-garde Prose. Poem ...

  - **R** Pierre Reverdy (1889–1960) is one of the twentieth-century French po ...  
    <sub>names pierre reverdy, reverdy, pierre</sub>
  - **R** Au Soleil du plafond, see Rothwell, “Cubism and the Avant-garde Prose.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>


## Query 8 — `Museum of Fine Arts, Boston Juan Gris donation history`

8 results · kind **inert → inert** · R6 w1 X10

**1. Essential Cubists: Braque, Gris, Léger, and Picasso**  
`mfa.org` · tier `tier1`  
> Juan Gris, Fernand Léger, and Pablo Picasso started an artistic revolution. traces the four artists' interactions between 1908 through 1926. Sponsors Presented ...

  - **R** Juan Gris, Fernand Léger, and Pablo Picasso started an artistic revolution.  
    <sub>names juan gris, juan, gris</sub>
  - w traces the four artists' interactions between 1908 through 1926.  
    <sub>no entity of its own; snippet names juan gris</sub>
  - **X** Sponsors Presented ...  
    <sub>about someone else (Sponsors Presented), not this stop</sub>

**2. JARED'S PICKS FOR 8/22-23   1) Picasso, Miró, Dalí: Unbound at the ...**  
`instagram.com` · tier `reject`  
> * Courtesy Museum of Fine Arts, Boston Au Soleil du Plafond: hard shell box. Juan Gris (Spanish (worked in France), 1887–1927) 1955. Illustrated ...

  - **R** * Courtesy Museum of Fine Arts, Boston Au Soleil du Plafond: hard shell box.  
    <sub>names au soleil du plafond, au soleil, plafond</sub>
  - **R** Juan Gris (Spanish (worked in France), 1887–1927) 1955.  
    <sub>names juan gris, juan, gris</sub>

**3. Advance Exhibition Schedule | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> Please contact Public Relations to verify titles and dates before publication: pr@mfa.org. Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond ( ...

  - **X** Please contact Public Relations to verify titles and dates before publication: pr@mfa.org.  
    <sub>about someone else (Please), not this stop</sub>
  - **R** Juan Gris and French poet Pierre Reverdy's Au Soleil du Plafond ( ...  
    <sub>names au soleil du plafond, pierre reverdy, au soleil</sub>

**4. Inside John Singer Sargent's studio Threadbare carpets, flying ...**  
`facebook.com` · tier `reject`  
> ... the work's eventual donation to the Museum of Fine Arts, Boston. ... art history John Singer Sargent The Metropolitan Museum of Art. 03 ...

  - **X** the work's eventual donation to the Museum of Fine Arts, Boston.  
    <sub>about someone else (Museum), not this stop</sub>
  - **X** art history John Singer Sargent The Metropolitan Museum of Art.  
    <sub>about someone else (John Singer Sargent The Metropolitan Museum), not this stop</sub>

**5. Pieces from private collections offer a look at pioneers of Cubism**  
`fosters.com` · tier `unverified`  
> Museum of Fine Arts, Boston. Juan Gris, are the focus of this concise survey of rarely-seen works of art. Great Benefactors of the MFA. is $15 ...

  - **X** Museum of Fine Arts, Boston.  
    <sub>about someone else (Museum), not this stop</sub>
  - **R** Juan Gris, are the focus of this concise survey of rarely-seen works of art.  
    <sub>names juan gris, juan, gris</sub>
  - **X** Great Benefactors of the MFA.  
    <sub>about someone else (Great Benefactors), not this stop</sub>

**6. numbered 41, ca. 1816–20 Black ink and wash 10 3/8 x 6 3/4 inches ...**  
`facebook.com` · tier `reject`  
> The Baltimore Museum of Art: The John Dorsey and Robert W. Armacost ... Museum of Fine Arts, Boston. William Sturgis Bigelow Collection ...

  - **X** The Baltimore Museum of Art: The John Dorsey and Robert W.  
    <sub>about someone else (The Baltimore Museum), not this stop</sub>
  - **X** Museum of Fine Arts, Boston.  
    <sub>about someone else (Museum), not this stop</sub>
  - **X** William Sturgis Bigelow Collection ...  
    <sub>about someone else (William Sturgis Bigelow Collection), not this stop</sub>

**7. Facets of Cubism | Museum of Fine Arts Boston**  
`mfa.org` · tier `tier1`  
> “Facets of Cubism” is a family affair: several major private collectors are lending rarely seen masterpieces to honor Irving Rabb and his late wife, Dolly, ...

  - **X** “Facets of Cubism” is a family affair: several major private collectors are lending rarely seen masterpieces to honor Irving Rabb and his late wife, Dolly, ...  
    <sub>about someone else (Facets), not this stop</sub>

**8. Acquisitions of the Month: January 2024 - Apollo Magazine**  
`apollo-magazine.com` · tier `tier2`  
> Museum of Fine Arts, Boston National Gallery of Art, A Parrot for Juan Gris (1953–54), which references the Spanish painter's 1915 work … is perhaps the most ...

  - **R** Museum of Fine Arts, Boston National Gallery of Art, A Parrot for Juan Gris (1953–54), which references the Spanish painter's 1915 work … is perhaps the most ...  
    <sub>names juan gris, juan, gris</sub>


## GEMINI (grounded) — full matrix, D366 framing

kind **eventful → eventful** · R5 w0 X0

> The project was originally planned around 1916–1917 by the art dealer Léonce Rosenberg as a collaboration between Juan Gris and poet Pierre Reverdy.
> 
> The original plan called for Gris to create a corresponding illustration for each of Reverdy's twenty poems.
> 
> The initial effort was left incomplete because Gris died in 1927 at age 40, having completed only eleven of the intended illustrations.
> 
> Nearly thirty years after Gris's death, the publisher Tériade revived and reconceived the unfinished project in collaboration with Reverdy.
> 
> The book was finally published posthumously in 1955 as a tribute to Gris by Reverdy and Tériade.

  - **R** The project was originally planned around 1916–1917 by the art dealer Léonce Rosenberg as a collaboration between Juan Gris and poet Pierre Reverdy.  
    <sub>names pierre reverdy, juan gris, reverdy</sub>
  - **R** The original plan called for Gris to create a corresponding illustration for each of Reverdy's twenty poems.  
    <sub>names reverdy, gris</sub>
  - **R** The initial effort was left incomplete because Gris died in 1927 at age 40, having completed only eleven of the intended illustrations.  
    <sub>names gris</sub>
  - **R** Nearly thirty years after Gris's death, the publisher Tériade revived and reconceived the unfinished project in collaboration with Reverdy.  
    <sub>names reverdy, teriade, gris</sub>
  - **R** The book was finally published posthumously in 1955 as a tribute to Gris by Reverdy and Tériade.  
    <sub>names reverdy, teriade, gris</sub>


---

# Moses and Monotheism


## Query 1 — `"Moses and Monotheism" Salvador Dalí story visitors Picasso, Miró, Dalí: Unbound`

8 results · kind **inert → inert** · R15 w0 X4

**1. Picasso, Miró, Dalí: Unbound | Museum of Fine Arts Boston**  
`thehistoryofart.org` · tier `unverified`  
> Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism show one model, where an artist interprets a foundational text. Juan Gris and the French ...

  - **R** Dalí's 1974 illustrations for Sigmund Freud's Moses and Monotheism show one model, where an artist interprets a foundational text.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** Juan Gris and the French ...  
    <sub>about someone else (Juan Gris), not this stop</sub>

**2. Salvador Dalí Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> Picasso, Miró, Dali: Unbound ... Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...

  - **R** Picasso, Miró, Dali: Unbound ...  
    <sub>names dali</sub>
  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**3. Advance Exhibition Schedule**  
`mfa.org` · tier `tier1`  
> Picasso, Miró, Dali: Unbound ... Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...

  - **R** Picasso, Miró, Dali: Unbound ...  
    <sub>names dali</sub>
  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**4. Dalí's Religious Models: the Iconography of Martyrdom and ...**  
`academia.edu` · tier `tier1`  
> Miró, Arp, Ernst and Picasso had been useful models while Dalí's ... Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...

  - **R** Miró, Arp, Ernst and Picasso had been useful models while Dalí's ...  
    <sub>names dali</sub>
  - **R** Moses and Monotheism: three essays' [1934-8], in volumes XIV and XIII ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**5. Photos by Zlata Tarasovna🌸 (@zllatochkaa_) · June 6, 2026**  
`instagram.com` · tier `reject`  
> ... Salvador Dalí among them-but they were also deeply collaborative ventures. ... Moses and Monotheism; others partnered with . DE CARLOS CERO 100% ...

  - **R** Salvador Dalí among them-but they were also deeply collaborative ventures.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** Moses and Monotheism; others partnered with .  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** DE CARLOS CERO 100% ...  
    <sub>about someone else (CARLOS CERO), not this stop</sub>

**6. Reel by Diana | Cape Town (@panda_est_banbuk) · July 8 ...**  
`instagram.com` · tier `reject`  
> ... Salvador Dalí among them-but they were also deeply collaborative ventures. ... Moses and Monotheism; others partnered with . DE CARLOS CERO 100% ...

  - **R** Salvador Dalí among them-but they were also deeply collaborative ventures.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** Moses and Monotheism; others partnered with .  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** DE CARLOS CERO 100% ...  
    <sub>about someone else (CARLOS CERO), not this stop</sub>

**7. Joan Miró Exhibitions: Current, Upcoming & Past Shows**  
`mutualart.com` · tier `market`  
> Picasso, Miró, Dali: Unbound ... Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...

  - **R** Picasso, Miró, Dali: Unbound ...  
    <sub>names dali</sub>
  - **R** Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud's Moses and Monotheism ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**8. Photos by ꜱᴀʀᴀ ᴍɪʟᴇʀ (@miilersara) · October 22, 2025**  
`instagram.com` · tier `reject`  
> ... Salvador Dalí among them-but they were also deeply collaborative ventures. ... Moses and Monotheism; others partnered with . DE CARLOS CERO 100% ...

  - **R** Salvador Dalí among them-but they were also deeply collaborative ventures.  
    <sub>names salvador dali, salvador, dali</sub>
  - **R** Moses and Monotheism; others partnered with .  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** DE CARLOS CERO 100% ...  
    <sub>about someone else (CARLOS CERO), not this stop</sub>


## Query 2 — `"Moses and Monotheism" Salvador Dalí`

8 results · kind **inert → inert** · R12 w0 X6

**1. Illustrations and printed text of Sigmund Freud's Moses and ...**  
`collections.museumofthebible.org` · tier `unverified`  
> Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.

  - **R** Illustrations and printed text of Sigmund Freud's Moses and Monotheism (Moïse et le Monothéisme) by Salvador Dalí, with additional drawings by the artist.  
    <sub>names moses and monotheism, salvador dali, sigmund freud</sub>

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

**8. Moses and Monotheism Bronze Bas Relief - Choice Contemporary**  
`choicecontemporary.com` · tier `unverified`  
> Moses and Monotheism Bronze Bas Relief. Salvador Dali. Regular price $3,980.00 USD. Moses and Monotheism Salvador Dali

  - **R** Moses and Monotheism Bronze Bas Relief.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Regular price $3,980.00 USD.  
    <sub>about someone else (Regular), not this stop</sub>
  - **R** Moses and Monotheism Salvador Dali  
    <sub>names moses and monotheism, salvador dali, monotheism</sub>


## Query 3 — `"Moses and Monotheism" history`

8 results · kind **inert → inert** · R10 w0 X0

**1. Moses and Monotheism - Wikipedia**  
`en.wikipedia.org` · tier `tier1`  
> Moses and Monotheism is a 1939 book about the origins of monotheism written by Sigmund Freud, the founder of psychoanalysis. It is Freud's final original ...

  - **R** Moses and Monotheism is a 1939 book about the origins of monotheism written by Sigmund Freud, the founder of psychoanalysis.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **R** It is Freud's final original ...  
    <sub>names freud</sub>

**2. How is 'Moses and Monotheism' by Sigmund Freud viewed by ... - Reddit**  
`reddit.com` · tier `reject`  
> Sigmund Freud's book Moses and Monotheism (German: Der Mann Moses und die monotheistische Religion) from 1939 makes the claim that Judaism comes ...

  - **R** Sigmund Freud's book Moses and Monotheism (German: Der Mann Moses und die monotheistische Religion) from 1939 makes the claim that Judaism comes ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**3. Full article: Sigmund Freud's Moses and Monotheism: A treatment of ...**  
`tandfonline.com` · tier `unverified`  
> The second part of this article explores Freud's Moses and Monotheism as a psychoanalytic attempt to address the historical roots of anti- ...

  - **R** The second part of this article explores Freud's Moses and Monotheism as a psychoanalytic attempt to address the historical roots of anti- ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**4. Moses and Monotheism Summary | SuperSummary**  
`supersummary.com` · tier `unverified`  
> Divided into three parts, Moses and Monotheism begins by setting up Freud's central conceit, which was that Moses was not actually a Jewish man but rather an ...

  - **R** Divided into three parts, Moses and Monotheism begins by setting up Freud's central conceit, which was that Moses was not actually a Jewish man but rather an ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**5. Moses And Monotheism : Freud,Sigmund. - Internet Archive**  
`archive.org` · tier `unverified`  
> Moses And Monotheism ; Publication date: 1939 ; Topics: RELIGION. THEOLOGY, Prehistoric and primitive religions ; Publisher: By The Hogarth Press.

  - **R** Moses And Monotheism ; Publication date: 1939 ; Topics: RELIGION.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** THEOLOGY, Prehistoric and primitive religions ; Publisher: By The Hogarth Press.  
    <sub>names hogarth</sub>

**6. What are thoughts on Freud's Moses and Monotheism? - Facebook**  
`facebook.com` · tier `reject`  
> In Moses and Monotheism, Freud speculates that Moses was not Jewish, but actually born into Ancient Egyptian nobility and was perhaps a follower ...

  - **R** In Moses and Monotheism, Freud speculates that Moses was not Jewish, but actually born into Ancient Egyptian nobility and was perhaps a follower ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**7. Moses, Murder, and the Jewish Psyche**  
`jewishreviewofbooks.com` · tier `unverified`  
> As Yerushalmi's account makes clear, Freud in Moses and Monotheism sets forth three exceptionally controversial historical claims: Moses was an ...

  - **R** As Yerushalmi's account makes clear, Freud in Moses and Monotheism sets forth three exceptionally controversial historical claims: Moses was an ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**8. Out of Your Mind — Reading Freud's Moses and Monotheism - Medium**  
`medium.com` · tier `reject`  
> “[Moses and Monotheism] started out from the question as to what has really created the particular character of the Jew, and came to the ...

  - **R** “[Moses and Monotheism] started out from the question as to what has really created the particular character of the Jew, and came to the ...  
    <sub>names moses and monotheism, monotheism, moses</sub>


## Query 4 — `Sigmund Freud Salvador Dalí`

8 results · kind **eventful → eventful** · R13 w1 X0

**1. When Dalí met Freud - Freud Museum London**  
`freud.org.uk` · tier `unverified`  
> Salvador Dalí's first and only encounter with Sigmund Freud was fittingly bizarre. The pair met on 19 July 1938 at Freud's home in London, as a ...

  - **R** Salvador Dalí's first and only encounter with Sigmund Freud was fittingly bizarre.  
    <sub>names salvador dali, sigmund freud, salvador</sub>
  - **R** The pair met on 19 July 1938 at Freud's home in London, as a ...  
    <sub>names freud</sub>

**2. Sigmund Freud - Salvador Dalí Museum**  
`thedali.org` · tier `unverified`  
> Salvador Dalí's connection with Sigmund Freud is well-documented, beginning with his reading of Interpretation of Dreams, which Dalí regarded as one of the “ ...

  - **R** Salvador Dalí's connection with Sigmund Freud is well-documented, beginning with his reading of Interpretation of Dreams, which Dalí regarded as one of the “ ...  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**3. Freud, Dalí and the Metamorphosis of Narcissus - Freud Museum London**  
`freud.org.uk` · tier `unverified`  
> Salvador Dalí was a passionate admirer of Sigmund Freud and finally met him in London on July 19th 1938. This year 2018 marks the 80th anniversary of this event ...

  - **R** Salvador Dalí was a passionate admirer of Sigmund Freud and finally met him in London on July 19th 1938.  
    <sub>names salvador dali, sigmund freud, salvador</sub>
  - w This year 2018 marks the 80th anniversary of this event ...  
    <sub>no entity of its own; snippet names salvador dali</sub>

**4. When Salvador Dali Met Sigmund Freud, and Changed Freud's Mind ...**  
`openculture.com` · tier `unverified`  
> Salvador Dalí, who considered himself a devoted follower of Freud. took place in July of 1938, at Freud's home in London. Freud was 81, Dali 34.

  - **R** Salvador Dalí, who considered himself a devoted follower of Freud.  
    <sub>names salvador dali, salvador, freud</sub>
  - **R** took place in July of 1938, at Freud's home in London.  
    <sub>names freud</sub>
  - **R** Freud was 81, Dali 34.  
    <sub>names freud, dali</sub>

**5. Dalí – Freud | Belvedere Museum Vienna**  
`belvedere.at` · tier `unverified`  
> In London in 1938 Salvador Dalí finally met Sigmund Freud, who had recently fled Vienna – the first and only meeting between the artist and his ...

  - **R** In London in 1938 Salvador Dalí finally met Sigmund Freud, who had recently fled Vienna – the first and only meeting between the artist and his ...  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**6. Sketch of Sigmund Freud by Salvador Dali - Google Arts & Culture**  
`artsandculture.google.com` · tier `unverified`  
> Dali visited Freud in London in 1938 and made a study for a number of pen sketches of Freud. Dali's written account of the meeting refers to Freud's stare

  - **R** Dali visited Freud in London in 1938 and made a study for a number of pen sketches of Freud.  
    <sub>names freud, dali</sub>
  - **R** Dali's written account of the meeting refers to Freud's stare  
    <sub>names freud, dali</sub>

**7. What Happened When Salvador Dali Met Sigmund Freud? - TheCollector**  
`thecollector.com` · tier `unverified`  
> Salvador Dali had long been an admirer of Sigmund Freud, and the pair finally met in July 1938.

  - **R** Salvador Dali had long been an admirer of Sigmund Freud, and the pair finally met in July 1938.  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**8. Sigmund Freud and Salvador Dalí: Personal Moments - jstor**  
`jstor.org` · tier `tier2`  
> On 19 July 1938, Sigmund Freud and Salvador Dali. founder of psychoanalysis, Dali embellished his one-sided relationship with Freud with intense feelings and ...

  - **R** On 19 July 1938, Sigmund Freud and Salvador Dali.  
    <sub>names salvador dali, sigmund freud, salvador</sub>
  - **R** founder of psychoanalysis, Dali embellished his one-sided relationship with Freud with intense feelings and ...  
    <sub>names freud, dali</sub>


## Query 5 — `Sigmund Freud Salvador Dalí relationship why collaborated`

8 results · kind **active → inert** · R9 w0 X1

**1. When Dalí met Freud**  
`freud.org.uk` · tier `unverified`  
> The surrealist icon met with the father of psychoanalysis on 19 July 1938. · Salvador Dalí's first and only encounter with Sigmund Freud was ...

  - **X** The surrealist icon met with the father of psychoanalysis on 19 July 1938.  
    <sub>about someone else (July), not this stop</sub>
  - **R** · Salvador Dalí's first and only encounter with Sigmund Freud was ...  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**2. Sigmund Freud**  
`thedali.org` · tier `unverified`  
> Salvador Dalí's connection with Sigmund Freud is well-documented, beginning with his reading of Interpretation of Dreams, which Dalí regarded as one of the ...

  - **R** Salvador Dalí's connection with Sigmund Freud is well-documented, beginning with his reading of Interpretation of Dreams, which Dalí regarded as one of the ...  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**3. Salvador Dali influences Sigmund Freud on surrealism**  
`facebook.com` · tier `reject`  
> His interest in the enigma of the mind brought him into contact with Sigmund Freud. The meetings occurred in 1938, when Freud was ailing in his ...

  - **R** His interest in the enigma of the mind brought him into contact with Sigmund Freud.  
    <sub>names sigmund freud, sigmund, freud</sub>
  - **R** The meetings occurred in 1938, when Freud was ailing in his ...  
    <sub>names freud</sub>

**4. Salvador Dali Meets Sigmund Freud: Paranoia, Narcissism ...**  
`escipub.com` · tier `unverified`  
> For Dalí the meeting served as a way to break with Surrealism and led to a revised philosophy ...

  - **R** For Dalí the meeting served as a way to break with Surrealism and led to a revised philosophy ...  
    <sub>names dali</sub>

**5. TIL that Salvador Dalí and Sigmund Freud met in 1938. ...**  
`reddit.com` · tier `reject`  
> Dalí started sketching Freud and Freud whispered to his friends: “That boy looks like a fanatic.” The remark, repeated to Dalí, delighted him.

  - **R** Dalí started sketching Freud and Freud whispered to his friends: “That boy looks like a fanatic.” The remark, repeated to Dalí, delighted him.  
    <sub>names freud, dali</sub>

**6. The Freudian Universe of Dalí**  
`museothyssen.org` · tier `unverified`  
> The relationship between the work of Salvador Dalí and the writings of Sigmund Freud is one of the key issues that articulate the artist's visual aesthetic.

  - **R** The relationship between the work of Salvador Dalí and the writings of Sigmund Freud is one of the key issues that articulate the artist's visual aesthetic.  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**7. Salvador Dali and Sigmund Freud Meet in Lisa Monde's ...**  
`iloveny.com` · tier `unverified`  
> Salvador Dali worshiped the famous psychoanalyst – Doctor Sigmund Freud, ardently wished to meet him and discuss his own complexes as well as ...

  - **R** Salvador Dali worshiped the famous psychoanalyst – Doctor Sigmund Freud, ardently wished to meet him and discuss his own complexes as well as ...  
    <sub>names salvador dali, sigmund freud, salvador</sub>

**8. That time Salvador Dali met Sigmund Freud - Dangerous Minds**  
`dangerousminds.net` · tier `unverified`  
> Because of their interest in dreams and the unconscious, it may have seemed obvious that Dali and Freud would have made natural friends, but ...

  - **R** Because of their interest in dreams and the unconscious, it may have seemed obvious that Dali and Freud would have made natural friends, but ...  
    <sub>names freud, dali</sub>


## Query 6 — `Salvador Dalí "Moses and Monotheism" why created motivation`

8 results · kind **inert → inert** · R12 w0 X2

**1. Freud had a lifelong fascination for the figure of Moses ...**  
`facebook.com` · tier `reject`  
> In his work "Moses and Monotheism," he used his ideas of the Oedipal Complex to create a larger portrait of western religion. Mosaic monotheism, ...

  - **R** In his work "Moses and Monotheism," he used his ideas of the Oedipal Complex to create a larger portrait of western religion.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Mosaic monotheism, ...  
    <sub>names monotheism</sub>

**2. Beware the Boa Constructor! Freud, Modern Art and the ...**  
`88invisiblemirrors.blog` · tier `unverified`  
> ... Moses and Monotheism (1939), the story of psychoanalysis can be read as an epic, autobiographical story of his attempt to create a method ...

  - **R** Moses and Monotheism (1939), the story of psychoanalysis can be read as an epic, autobiographical story of his attempt to create a method ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**3. Freud's Mexican Readers | Psychoanalysis and History**  
`euppublishing.com` · tier `unverified`  
> ... Moses and Monotheism made upon him. 'Freud's study of Judaic monotheism', he told Fell, inspired him to write an account 'of the world of ...

  - **R** Moses and Monotheism made upon him.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** 'Freud's study of Judaic monotheism', he told Fell, inspired him to write an account 'of the world of ...  
    <sub>names monotheism, freud</sub>

**4. From 15 August the exhibition “Conquest of the Irrational. Books ...**  
`instagram.com` · tier `reject`  
> ... Dali's late oeuvre is represented above all by striking large-format publications: Freud's Moses and Monotheism, The Twelve Tribes of Israel, Francisco de ...

  - **R** Dali's late oeuvre is represented above all by striking large-format publications: Freud's Moses and Monotheism, The Twelve Tribes of Israel, Francisco de ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**5. “The Audacity Cannot Be Avoided” (Chapter 3)**  
`cambridge.org` · tier `unverified`  
> And this is why everything in Moses and Monotheism turns on the new concept of “historical truth,” that “kernel of truth” built on the back of his renewed ...

  - **R** And this is why everything in Moses and Monotheism turns on the new concept of “historical truth,” that “kernel of truth” built on the back of his renewed ...  
    <sub>names moses and monotheism, monotheism, moses</sub>

**6. Max Horkheimer: Lectures Towards a Psychology of Anti ...**  
`jamescrane.substack.com` · tier `unverified`  
> Tear of Blood, Moses and Monotheism. 1975. “Civilization itself cannot be cleared of the responsibility of having engendered its opposite: ...

  - **R** Tear of Blood, Moses and Monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** “Civilization itself cannot be cleared of the responsibility of having engendered its opposite: ...  
    <sub>about someone else (Civilization), not this stop</sub>

**7. tools-public/tools/voice/voice-of-sigmund-freud.md at master**  
`github.com` · tier `unverified`  
> Moses and Monotheism was the last major work, and it was the most reckless. I argued that Moses was not a Hebrew but an Egyptian nobleman, that he imposed ...

  - **R** Moses and Monotheism was the last major work, and it was the most reckless.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** I argued that Moses was not a Hebrew but an Egyptian nobleman, that he imposed ...  
    <sub>names moses</sub>

**8. 400 QUOTES BY SIGMUND FREUD [PAGE - 18]**  
`azquotes.com` · tier `unverified`  
> Dark. SIGMUND FREUD (1939). “MOSES AND MONOTHEISM”. 8 Copy. Another technique for fending off suffering is the employment of the displacements of libido which ...

  - **R** SIGMUND FREUD (1939).  
    <sub>names sigmund freud, sigmund, freud</sub>
  - **R** “MOSES AND MONOTHEISM”.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **X** Another technique for fending off suffering is the employment of the displacements of libido which ...  
    <sub>about someone else (Another), not this stop</sub>


## Query 7 — `"Moses and Monotheism" Sigmund Freud why chose subject`

8 results · kind **inert → inert** · R10 w0 X1

**1. Full article: Sigmund Freud's Moses and Monotheism: A treatment of ...**  
`tandfonline.com` · tier `unverified`  
> The second part of this article explores Freud's Moses and Monotheism as a psychoanalytic attempt to address the historical roots of anti- ...

  - **R** The second part of this article explores Freud's Moses and Monotheism as a psychoanalytic attempt to address the historical roots of anti- ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**2. Moses and Monotheism by Sigmund Freud (1938) | Books & Boots**  
`astrofella.wordpress.com` · tier `unverified`  
> 'Moses and Monotheism' was Freud's last published work, written when he was wracked by painful cancer of the jaw, and anxiety about the Nazis ...

  - **R** 'Moses and Monotheism' was Freud's last published work, written when he was wracked by painful cancer of the jaw, and anxiety about the Nazis ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**3. What are thoughts on Freud's Moses and Monotheism? - Facebook**  
`facebook.com` · tier `reject`  
> “Moses and monotheism. Freud (1939) says: “I found that I could not erase traces of the origin story of a work, which was unusual in any case.

  - **R** “Moses and monotheism.  
    <sub>names moses and monotheism, monotheism, moses</sub>
  - **R** Freud (1939) says: “I found that I could not erase traces of the origin story of a work, which was unusual in any case.  
    <sub>names freud</sub>

**4. “Moses and Monotheism” as History. Reading Freud through de Certau ...**  
`quest-cdecjournal.it` · tier `unverified`  
> Freud's Moses and Monotheism belongs without any doubt to this kind of undying works. BACK. [1] Sigmund Freud, Moses and Monotheism, trans. Katherine Jones ...

  - **R** Freud's Moses and Monotheism belongs without any doubt to this kind of undying works.  
    <sub>names moses and monotheism, monotheism, freud</sub>
  - **R** [1] Sigmund Freud, Moses and Monotheism, trans.  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**5. Was Freud the first to say that Judaism borrowed from Atenism?**  
`history.stackexchange.com` · tier `unverified`  
> In Moses and Monotheism, Sigmund Freud went further than Breasted's Dawn of Conscience to argue that Moses was an Egyptian who derived his ...

  - **R** In Moses and Monotheism, Sigmund Freud went further than Breasted's Dawn of Conscience to argue that Moses was an Egyptian who derived his ...  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>

**6. Freud's father religion: refinding Moses and Monotheism in 2023**  
`pmc.ncbi.nlm.nih.gov` · tier `tier1`  
> Preparing a talk on Freud's Judaism in the early fall of 2023, I – strange at it may sound – wanted to steer away from Moses and Monotheism, ...

  - **R** Preparing a talk on Freud's Judaism in the early fall of 2023, I – strange at it may sound – wanted to steer away from Moses and Monotheism, ...  
    <sub>names moses and monotheism, monotheism, freud</sub>

**7. Was Moses a monotheist? What about Akhenaten? Was Freud for ... - Quora**  
`quora.com` · tier `reject`  
> Sigmund Freud put forth the theory that Akhenaten was the Pharaoh of the Exodus in his book "Moses and Monotheism". What are the arguments ...

  - **R** Sigmund Freud put forth the theory that Akhenaten was the Pharaoh of the Exodus in his book "Moses and Monotheism".  
    <sub>names moses and monotheism, sigmund freud, monotheism</sub>
  - **X** What are the arguments ...  
    <sub>about someone else (What), not this stop</sub>

**8. Moses, Murder, and the Jewish Psyche**  
`jewishreviewofbooks.com` · tier `unverified`  
> That Freud wrote Moses and Monotheism near the end of his life, after the Nazi rise to power, and as he himself began to reread the Bible his ...

  - **R** That Freud wrote Moses and Monotheism near the end of his life, after the Nazi rise to power, and as he himself began to reread the Bible his ...  
    <sub>names moses and monotheism, monotheism, freud</sub>


## Query 8 — `Museum of Fine Arts, Boston Salvador Dalí donation history`

8 results · kind **inert → inert** · R7 w0 X4

**1. First-Ever Salvador Dalí Exhibition at the Museum ...**  
`mfa.org` · tier `tier1`  
> Dalí: Disruption and Devotion is generously supported by the William Randolph Hearst Foundations. Additional support from the Alexander

  - **R** Dalí: Disruption and Devotion is generously supported by the William Randolph Hearst Foundations.  
    <sub>names dali</sub>
  - **X** Additional support from the Alexander  
    <sub>about someone else (Additional), not this stop</sub>

**2. Dalí: Disruption and Devotion**  
`mfa.org` · tier `tier1`  
> “Dalí: Disruption and Devotion” juxtaposes nearly 30 paintings and prints on loan from the Salvador Dalí Museum in St. Petersburg, Florida, with European ...

  - **R** “Dalí: Disruption and Devotion” juxtaposes nearly 30 paintings and prints on loan from the Salvador Dalí Museum in St.  
    <sub>names salvador dali, salvador, dali</sub>
  - **X** Petersburg, Florida, with European ...  
    <sub>about someone else (Petersburg), not this stop</sub>

**3. Dalí In Context**  
`mfa.org` · tier `tier1`  
> Explore the exhibition “Dalí: Disruption and Devotion” through the lens of history, film, photography, and the artists that came before and after the ...

  - **R** Explore the exhibition “Dalí: Disruption and Devotion” through the lens of history, film, photography, and the artists that came before and after the ...  
    <sub>names dali</sub>

**4. Dalí: Outlandish and Reverential**  
`mfa.org` · tier `tier1`  
> Give to the MFA Planned Giving. In this four-minute video hear from exhibition curator Frederick Ilchman, discusses the work of Salvador Dalí. ...

  - **X** Give to the MFA Planned Giving.  
    <sub>about someone else (Give), not this stop</sub>
  - **R** In this four-minute video hear from exhibition curator Frederick Ilchman, discusses the work of Salvador Dalí.  
    <sub>names salvador dali, salvador, dali</sub>

**5. Salvador Dali exhibit at Boston Museum of Fine Arts**  
`facebook.com` · tier `reject`  
> Hello Dali - These are a few of the special exhibit of Salvador Dali and realism that we saw last night at the Boston Museum of Fine Arts. Friday night ...

  - **R** Hello Dali - These are a few of the special exhibit of Salvador Dali and realism that we saw last night at the Boston Museum of Fine Arts.  
    <sub>names salvador dali, salvador, dali</sub>

**6. 'Dalí: Disruption + Devotion,' a New Exhibition at The ...**  
`thedali.org` · tier `unverified`  
> Co-organized with the Museum of Fine Arts, Boston, through a collection of rarely lent works, the exhibition opens November 7, 2026, and remains ...

  - **X** Co-organized with the Museum of Fine Arts, Boston, through a collection of rarely lent works, the exhibition opens November 7, 2026, and remains ...  
    <sub>about someone else (Co-organized), not this stop</sub>

**7. Where's Waldo? Or in this case, Where's Dalí?  Today, we're ...**  
`facebook.com` · tier `reject`  
> Today, we're looking at all the thoughtful references and details in Salvador Dalí's massive painting, "The Ecumenical Council" with Julia ...

  - **R** Today, we're looking at all the thoughtful references and details in Salvador Dalí's massive painting, "The Ecumenical Council" with Julia ...  
    <sub>names salvador dali, salvador, dali</sub>

**8. 'Dalí: Disruption and Devotion' Review: Getting to Know ...**  
`thecrimson.com` · tier `unverified`  
> The Museum of Fine Arts, Boston challenges this narrative with its current exhibition, “Dalí: Disruption and Devotion.” This collection puts ...

  - **R** The Museum of Fine Arts, Boston challenges this narrative with its current exhibition, “Dalí: Disruption and Devotion.” This collection puts ...  
    <sub>names dali</sub>


## GEMINI (grounded) — full matrix, D366 framing

kind **eventful → eventful** · R3 w1 X1

> * Salvador Dalí created this portfolio of illustrations between 1970 and 1974 to interpret Sigmund Freud's final 1939 book, *Moses and Monotheism*.
> * The project was undertaken in collaboration with French publisher Ariane Lancell and issued by Éditions Art & Valeur in Paris.
> * Unlike typical *livre d'artiste* projects initiated as living dialogues between authors and artists, Dalí illustrated the foundational text decades after Freud's death.
> * Dalí had long idolized Freud—having famously met him only once in London in 1938—and created the suite as part of a series engaging Jewish and psychoanalytic themes.
> * The finished edition was presented as an extravagant portfolio encased in a box featuring a silver-plated brass bas-relief.

  - **R** * Salvador Dalí created this portfolio of illustrations between 1970 and 1974 to interpret Sigmund Freud's final 1939 book, *Moses and Monotheism*.  
    <sub>names moses and monotheism, salvador dali, sigmund freud</sub>
  - **X** * The project was undertaken in collaboration with French publisher Ariane Lancell and issued by Éditions Art & Valeur in Paris.  
    <sub>about someone else (French), not this stop</sub>
  - **R** * Unlike typical *livre d'artiste* projects initiated as living dialogues between authors and artists, Dalí illustrated the foundational text decades after Freud's death.  
    <sub>names freud, dali</sub>
  - **R** * Dalí had long idolized Freud—having famously met him only once in London in 1938—and created the suite as part of a series engaging Jewish and psychoanalytic themes.  
    <sub>names freud, dali</sub>
  - w * The finished edition was presented as an extravagant portfolio encased in a box featuring a silver-plated brass bas-relief.  
    <sub>no entity of its own; snippet names moses and monotheism</sub>

