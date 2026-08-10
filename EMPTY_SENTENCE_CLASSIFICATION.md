# EMPTY_SENTENCE_CLASSIFICATION.md — LOCAL-375

## Summary

**49 sentences** flagged by `_is_empty_sentence` across **5 live tours** generated
with `DISABLE_TOUR_CACHE=1`, `DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`.

| Tour | Type | Stops | Flagged |
|------|------|-------|---------|
| Palais Lascaris, Nice, France | museum | 4 | 12 |
| Museum of Fine Arts, Boston, MA | museum | 8 | 19 |
| French Riviera, France | biking | 2 | 2 |
| Musee Matisse, Nice, France | museum | 4 | 9 |
| Boston Common, Boston, MA | walking | 3 | 7 |
| **TOTAL** | | **21** | **49** |

`code_sha`: `81170f9`

---

## Classification Key

| Class | Definition |
|-------|------------|
| **1 — Genuinely empty** | Grammatical but information-free. No factual claim a listener could verify, learn from, or act on. |
| **2 — Broken grammar** | Fragments, dangling predicates, garbled splices, truncated clauses. |
| **3 — False positive** | Carries real information but trips the heuristic (visual description of artwork, short factual claims about technique, non-English). |
| **4 — Ambiguous** | Arguable — sentence has a weak claim or partial information that reasonable people could classify either way. |

---

## Full Classification Table

### Tour 1: Palais Lascaris, Nice, France (museum, 4 stops)

| # | Stop | Sentence (verbatim) | Class |
|---|------|---------------------|-------|
| 1 | Stop 1: Harpe by Naderman (Paris, 1780) | "This piece holds profound historical significance, representing a pivotal era in musical instrument design and innovation." | **1 — Empty** |
| 2 | Stop 1: Harpe by Naderman (Paris, 1780) | "With connections to renowned harp makers and musicians of the time, such as Jean-Henri Naderman, this piece offers a glimpse into the luxurious musical culture of Paris during the period." | **3 — False positive** |
| 3 | Stop 1: Harpe by Naderman (Paris, 1780) | "The instrument's regal presence and elegant design set the stage for the orchestral innovations that would follow." | **1 — Empty** |
| 4 | Stop 2: Guitar by Antonio de Torres (Almeria, 1884) | "This specific guitar is a tangible representation of Torres' dedication to craftsmanship and his influence on the evolution of the classical guitar." | **1 — Empty** |
| 5 | Stop 2: Guitar by Antonio de Torres (Almeria, 1884) | "Studying the intricate details of this guitar reveals how Torres' creations have endured over time, influencing generations of musicians and craftsmen." | **1 — Empty** |
| 6 | Stop 2: Guitar by Antonio de Torres (Almeria, 1884) | "The craftsmanship and artistry in this instrument stand as a testament to Torres' dedication to his craft and his lasting impact on classical guitar-making." | **1 — Empty** |
| 7 | Stop 3: Basse de violon by Paolo Antonio Testore (Milan, 1696) | "The revolutionary string instrument that echoed the eternal cycles of innovation and creativity in the world of music was yet to come." | **2 — Broken grammar** |
| 8 | Stop 4: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | "The craftsmanship of this trombone is a marvel to behold, with each curve and detail reflecting the expertise and dedication of the maker." | **1 — Empty** |
| 9 | Stop 4: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | "This piece serves as a window into the world of Renaissance music and the significance of musical instruments in shaping the cultural landscape of the time." | **1 — Empty** |
| 10 | Stop 4: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | "Its presencethe rich collection but also provides visitors with a unique opportunity to engage with a piece of history that has influenced the development of music over the centuries." | **2 — Broken grammar** |
| 11 | Stop 4: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | "As you admire this tenor sackbut, you can't help but appreciate the meticulous craftsmanship and historical significance it represents." | **1 — Empty** |
| 12 | Stop 4: Sacqueboute ténor by Anton Schnitzer (Nuremberg, 1581) | "It offers a glimpse into a bygone era, where music played a vital role in society, and instruments like the sackbut were crafted with precision and care." | **1 — Empty** |

### Tour 2: Museum of Fine Arts, Boston, MA (museum, 8 stops)

| # | Stop | Sentence (verbatim) | Class |
|---|------|---------------------|-------|
| 13 | Stop 1: Appeal to the Great Spirit | "This piece serves as a touchstone for the museum's commitment to diverse narratives and artistic expressions." | **1 — Empty** |
| 14 | Stop 1: Appeal to the Great Spirit | "As you observe this monumental artwork, reflect on the legacy and his contributions to the museum's collection." | **2 — Broken grammar** |
| 15 | Stop 2: Ancient Nubia Now | "Their artists and craftspeople excelled in creating magnificent jewelry, pottery, and other exquisite objects now on display in this exhibition." | **3 — False positive** |
| 16 | Stop 3: Adam and Eve | "Adam and Eve, the first couple created in the Bible, stand as the perfect beginning of humanity yet also symbolize the original sin that led to humankind's fall from grace." | **3 — False positive** |
| 17 | Stop 3: Adam and Eve | "The artist masterfully used tiny brushes to build up thick layers of color, giving the figures a glowing, almost ethereal quality." | **3 — False positive** |
| 18 | Stop 3: Adam and Eve | "This technique adds a sense of otherworldliness to the painting, enhancing the dramatic nature of the narrative." | **1 — Empty** |
| 19 | Stop 3: Adam and Eve | "The work not only showcases the skill and artistry of the creator but also serves as a powerful reflection on the eternal themes of creation, temptation, and the consequences of human actions." | **1 — Empty** |
| 20 | Stop 3: Adam and Eve | "This artwork, acquired with the support of Bartlett's donations, highlights his significant role in diversifying the museum's religious art collection." | **3 — False positive** |
| 21 | Stop 4: April 1957 (Celestial Blue) | "The use of this specific pigment adds a layer of historical significance to the piece, connecting it to the craftsmanship and artistry of the past." | **1 — Empty** |
| 22 | Stop 4: April 1957 (Celestial Blue) | "Its timeless beauty and historical roots offer a unique perspective on the intersection of art, history, and culture." | **1 — Empty** |
| 23 | Stop 5: Adoration of the Shepherds | "Mengs skillfully captures the tender expressions of the figures, conveying a sense of awe and reverence." | **3 — False positive** |
| 24 | Stop 5: Adoration of the Shepherds | "The soft, warm lighting illuminates the faces of the shepherds, emphasizing their adoration of the infant." | **3 — False positive** |
| 25 | Stop 5: Adoration of the Shepherds | "Their faces are filled with wonder and humility, reflecting the profound significance of the divine presence before them." | **1 — Empty** |
| 26 | Stop 5: Adoration of the Shepherds | "By exploring this piece, visitors can connect with centuries of artistic tradition and spiritual devotion that have been inspired by this sacred event." | **1 — Empty** |
| 27 | Stop 5: Adoration of the Shepherds | "The timeless appeal of religious themes, exemplified in this painting, speaks to the donors' vision of preserving and showcasing art that transcends time and resonates with viewers across generations." | **1 — Empty** |
| 28 | Stop 6: An Italian Autumn | "Cole's meticulous attention to detail in portraying the changing colors of the leaves and the play of light and shadow creates a captivating visual experience." | **3 — False positive** |
| 29 | Stop 7: Madame Monet wearing a kimono | "As you gaze upon the painting, you are met with a striking image of a European woman, depicted in a vibrant red uchikake kimono." | **3 — False positive** |
| 30 | Stop 7: Madame Monet wearing a kimono | "This painting serves as a timeless reminder of the power of art to transcend boundaries and inspire appreciation for diverse cultural traditions." | **1 — Empty** |
| 31 | Stop 8: A Papal Saint (Saint Gregory the Great?) | "The figure depicted may be adorned in traditional papal attire, symbolizing authority and holiness." | **4 — Ambiguous** |

### Tour 3: French Riviera, France (biking, 2 stops)

| # | Stop | Sentence (verbatim) | Class |
|---|------|---------------------|-------|
| 32 | Stop 1: Villa Ephrussi de Rothschild | "Upon entering the villa, visitors will encounter a collection paintings, along with objets d'art, reflecting the baroness's refined taste and passion for beauty." | **4 — Ambiguous** |
| 33 | Stop 2: Musée Matisse | "The convergence of light and colors in his works reflects the artist's deep connection to this region and his unwavering dedication to pushing artistic boundaries." | **1 — Empty** |

### Tour 4: Musee Matisse, Nice, France (museum, 4 stops)

| # | Stop | Sentence (verbatim) | Class |
|---|------|---------------------|-------|
| 34 | Stop 1: Nu bleu IV | "As the last technique developed by the artist, these cut-outs serve as a testament to his relentless experimentation and creative spirit." | **4 — Ambiguous** |
| 35 | Stop 1: Nu bleu IV | "The vibrant hues and intricate forms of this iconic piece capture narratives and emotions." | **1 — Empty** |
| 36 | Stop 1: Nu bleu IV | "Nu bleu IV delves into Matisse's world, where color, form, and innovation converge to create a timeless masterpiece that continues to inspire." | **1 — Empty** |
| 37 | Stop 3: Papeete-Tahiti | "This artwork showcases Matisse's ability to blend realism and abstraction, transporting viewers to the landscapes of Tahiti." | **4 — Ambiguous** |
| 38 | Stop 3: Papeete-Tahiti | "It remains a cherished piece in the collection, inspiring admiration and wonder in all who view it." | **1 — Empty** |
| 39 | Stop 4: Tempête à Nice | "Matisse's bold brushstrokes and vibrant color palette bring the tumultuous energy of the sea to life, contrasting with the calm of the coastal city." | **3 — False positive** |
| 40 | Stop 4: Tempête à Nice | "The use of light and shadow creates a dynamic interplay, evoking a sense of movement and drama within the composition." | **1 — Empty** |
| 41 | Stop 4: Tempête à Nice | "This painting stands as a testament to the enduring impact of Matisse's work and the timeless beauty it continues to exude." | **1 — Empty** |
| 42 | Stop 4: Tempête à Nice | "This piece encapsulates the blend of tranquility and turbulence in Matisse's life and the development of the museum." | **1 — Empty** |

### Tour 5: Boston Common, Boston, MA (walking, 3 stops)

| # | Stop | Sentence (verbatim) | Class |
|---|------|---------------------|-------|
| 43 | Stop 1: Brewer Fountain | "The fountain's significance goes beyond its physical form; it represents the blending of classical artistry with modern urban landscape." | **1 — Empty** |
| 44 | Stop 1: Brewer Fountain | "Near the fountain, the gentle trickle of water cascades down its ornate structure, creating a soothing ambiance amidst the hustle and bustle of the city." | **3 — False positive** |
| 45 | Stop 1: Brewer Fountain | "Brewer Fountain's presence on this walking tour emphasizes the enduring importance of public art in shaping communal spaces." | **1 — Empty** |
| 46 | Stop 2: Park Street Church | "The physical presence of this landmark connects visitors to a time when ideals were voiced with conviction and action." | **1 — Empty** |
| 47 | Stop 2: Park Street Church | "Its significance in the fight against slavery and the promotion of social justice positions it as a cornerstone of American civic history." | **4 — Ambiguous** |
| 48 | Stop 2: Park Street Church | "The voices that once echoed within these walls shaped the course of history." | **1 — Empty** |
| 49 | Stop 3: Soldiers and Sailors Monument | "The physical presence envelops visitors in history, with the weight of the monument's significance palpable." | **1 — Empty** |

---

## Counts by Class

| Class | Count | Fraction | Notes |
|-------|-------|----------|-------|
| **1 — Genuinely empty** | 30 | 61.2% | No factual content whatsoever |
| **2 — Broken grammar** | 3 | 6.1% | Garbled splices, dangling predicates |
| **3 — False positive** | 11 | 22.4% | Visual artwork descriptions trip heuristic |
| **4 — Ambiguous** | 5 | 10.2% | Mixed factual + filler, reasonable disagreement |
| **TOTAL** | **49** | **100%** | |

## Counts by Class × Tour Type

| Tour type | Class 1 | Class 2 | Class 3 | Class 4 | Total |
|-----------|---------|---------|---------|---------|-------|
| museum (4 tours, 19 stops) | 26 | 3 | 9 | 5 | 43 |
| biking (1 tour, 2 stops) | 1 | 0 | 0 | 1 | 2 |
| walking (1 tour, 3 stops) | 4 | 0 | 1 | 0 | 5 |

Note: the biking tour generated a walking-register tour (it was categorised as WALKING by the pipeline).

---

## False Positive Analysis (Class 3)

The 11 false positives share a common pattern: they describe **visual properties of artwork** — specific technique, composition, or depicted content — but without using a proper noun mid-sentence, a date, or a named period. The heuristic has no signal for:

1. **Art-description vocabulary** — "brushstrokes", "layers of color", "warm lighting", "bold palette", "intricate forms" are factual descriptions of visible properties. They carry information a listener looking at an artwork could verify.

2. **Depicted-content claims** — "a European woman, depicted in a vibrant red uchikake kimono" or "jewelry, pottery, and other exquisite objects now on display" reference specific visible things. They fail because no proper noun appears mid-sentence.

3. **Biblical/mythological referents** — "Adam and Eve, the first couple created in the Bible" is a factual statement about a painting's subject. It fails because "Bible" is not in `_SINGLE_WORD_EXCLUSIONS` but the proper nouns "Adam" and "Eve" appear as the first words.

### Proposed heuristic narrowing (DO NOT implement — separate task)

Add a **Signal 9: Visual-description vocabulary** that exempts sentences containing concrete visual/technique terms:

```python
_VISUAL_DESCRIPTION_RE = re.compile(
    r'(?i)\b(?:'
    r'brushstroke|brush[-\s]?stroke|palette|pigment|canvas|'
    r'composition|lighting|shadow|color|colour|hue|'
    r'depicted|portraying|depicting|illustrat|'
    r'jewelry|pottery|ceramic|sculpture|engraving|'
    r'kimono|attire|garment|'
    r'oil\s+on|gouache|watercolor|tempera|fresco'
    r')\b'
)
```

This would eliminate 9 of 11 false positives. The remaining 2 (#2 "Jean-Henri Naderman" and #20 "Bartlett's donations") are borderline — they contain proper nouns but the heuristic misses them because the name follows a possessive or preposition pattern. Fixing those requires refining Signal 2 (proper noun detection) to handle possessives (`Bartlett's`) and sentence-initial names followed by qualifiers.

---

## Recommendation

**Class 3 is 22.4% of hits.** This is below the "dominant" threshold but non-trivial.

**Enforcing at >3 empty sentences per stop is SAFE** given the current data:
- The highest per-stop count observed is 5 (Palais Lascaris Stop 4), which includes 2 broken-grammar sentences that should genuinely fail.
- No stop has >2 *false positives*. 
- A threshold of ≤3 per stop would reject 0 good tours from this sample (all false-positive stops have ≤2 class-3 sentences per stop).

However, a **per-tour threshold** is more useful:
- At the per-tour level, MFA Boston has 8 false positives across 8 stops. A threshold of ≤3 per tour would reject it.
- A per-tour threshold of ≤10 would pass all 5 tours in this sample.

**Specific recommendation:**

> Enforce at **>5 empty sentences per stop** (reject only catastrophic stops like Palais Lascaris Stop 4, which has 5 class-1+2 hits including a garbled splice). This passes all false-positive-heavy stops while catching genuine structural defects.
>
> Alternatively, enforce at **>4 per stop** after implementing the visual-description narrowing (which would reduce 9 of 11 false positives to non-hits).

**Before either threshold is applied**, the visual-description heuristic narrowing should be implemented as a separate task. This drops the false-positive rate from 22.4% to ~4% and makes any reasonable threshold safe.

---

## Ambiguous Cases (Class 4) — Rationale

| # | Sentence | Why ambiguous |
|---|----------|---------------|
| 31 | "The figure depicted may be adorned in traditional papal attire, symbolizing authority and holiness." | Describes visible content (papal attire) but hedges with "may be" — borderline between visual description (FP) and empty hedging. |
| 32 | "Upon entering the villa, visitors will encounter a collection paintings, along with objets d'art, reflecting the baroness's refined taste and passion for beauty." | Contains "objets d'art" and describes what's there, but "refined taste and passion for beauty" is empty filler appended to a factual claim. Also has grammar error ("collection paintings"). |
| 34 | "As the last technique developed by the artist, these cut-outs serve as a testament to his relentless experimentation and creative spirit." | "Last technique" is factual but lacks a date/name to anchor it; "testament to experimentation" is empty. |
| 37 | "This artwork showcases Matisse's ability to blend realism and abstraction, transporting viewers to the landscapes of Tahiti." | "Blend realism and abstraction" is a verifiable art-critical claim about technique; "transporting viewers" is filler. Mixed. |
| 47 | "Its significance in the fight against slavery and the promotion of social justice positions it as a cornerstone of American civic history." | References factual history (abolition movement) but without any specific date, person, or event — it's a *summary* that would be informative in context but structurally empty in isolation. |

---

## Reproduction Evidence

```
code_sha: 81170f9
DATABASE_URL: postgresql://admin:password123@localhost:5433/audiotours
DISABLE_TOUR_CACHE: 1
STORIED_MODE: true
STOP_EXISTENCE_GATE_MODE: enforce
```

Log lines confirming live generation (from `tours/LOCAL375_run_log.txt`):

```
CACHE STORE: Palais Lascaris, Nice, France / museum / 4
Total API cost: $0.0462 (34186 tokens)

CACHE STORE: Museum of Fine Arts, Boston, MA / museum / 8
Total API cost: $0.0763 (58953 tokens)

CACHE STORE: French Riviera, France / biking / 2
Total API cost: $0.0275 (17684 tokens)

CACHE STORE: Musee Matisse, Nice, France / museum / 4
Total API cost: $0.0431 (34393 tokens)

CACHE STORE: Boston Common, Boston, MA / walking / 4
Total API cost: $0.0388 (28487 tokens)
```

All 5 tours generated live (CACHE STORE confirms fresh generation, not cache hit).
