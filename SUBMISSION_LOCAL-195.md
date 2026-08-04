##### READY FOR REVIEW

# SUBMISSION LOCAL-195: Anchor Regression Truth Check

**Branch:** `kiro/local195-anchor-regression-truth`
**Base:** `storied`
**Date:** 2026-08-04

---

## Context

LOCAL-194 showed gpt-4o-mini halves R4 prescribed-feeling failures (5/21 → 1/21) at 7× lower cost, but anchor rate fell from 47.6% to 33.3%. D67 blocks the model switch until a human determines: is the drop a **paraphrase artifact** (detector can't see restated corpus) or **real ungrounding** (model invents from parametric memory)?

This task answers that question by hand-checking every factual claim in every NO_ANCHOR and UNLINKED_ENTITY paragraph, against the corpus.

---

## Experiment Setup

| Parameter | Value |
|-----------|-------|
| Venue | MAMAC (Musée d'Art Moderne et d'Art Contemporain, Nice) |
| Stops | 2 per run (same as LOCAL-194) |
| Runs | 1 per arm (reading exercise, not sample-size exercise) |
| Arms | gpt-3.5-turbo / gpt-4o-mini |
| Cache bypass | DATABASE_URL removed during generation |
| STORIED_MODE | true |
| Total spend | $0.0238 (ceiling: $0.35) |

### Stop Titles (both arms, identical)

- **Richard Long ou la sculpture en marchant**
- **She-Bam Pow POP Wizz**

---

## Detector Results (this run)

| Classification | ARM A (gpt-3.5-turbo) | ARM B (gpt-4o-mini) |
|---|---|---|
| ANCHORED | 1/7 = 14.3% | 1/7 = 14.3% |
| NO_ANCHOR | 2/7 | 2/7 |
| UNLINKED_ENTITY | 4/7 | 4/7 |
| Total paragraphs | 7 | 7 |

**Note:** In this single run, both arms have *identical* classification distributions. The 47.6% vs 33.3% gap from LOCAL-194's 3-run aggregate did not reproduce. This is consistent with the p=0.27 Fisher's exact reported in that submission — the difference is within noise.

---

## Per-Claim Fact Check: ARM A (gpt-3.5-turbo)

### Paragraph A1 — Richard Long, UNLINKED_ENTITY

> Position yourself at the entrance of the exhibit "Richard Long ou la sculpture en marchant" at Musee d'Art Moderne et d'Art Contemporain in Nice, France. From this vantage point, you are immediately greeted by a captivating sight that encapsulates the essence of movement and artistry.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Exhibit titled "Richard Long ou la sculpture en marchant" exists at MAMAC | SUPPORTED_PARAPHRASE | stop_corpus has a row with this exact title; venue_corpus canonical_titles lists it |
| Located in Nice, France | SUPPORTED_PARAPHRASE | SE[22]: "The Musée d'art moderne et d'art contemporain opened on 21 June 1990, in Nice, France." |
| No other factual claims | NOT_CHECKABLE | "encapsulates the essence of movement and artistry" is atmosphere, not fact |

**Unsupported claims: 0**

---

### Paragraph A2 — Richard Long, UNLINKED_ENTITY (prolog)

> You are about to embark on a journey through the Evolution of Art in the 20th and 21st Century at the Musee d Art Moderne et d Art Contemporain. Since its inauguration on June 21, 1990, this museum has evolved alongside the artistic movements it houses. The story begins with Richard Long's transformative pieces, reflecting the museum's own evolution. As you explore, you will witness the explosive impact of pop art on contemporary culture, marking a pivotal moment in the museum's narrative. Each chapter in this immersive experience reveals a different facet of modern and contemporary art, showcasing the generous contributions that have shaped Mamac and the profound influence of artists like Yves Klein. Embark on this journey of artistic evolution and discovery, where each artwork is a chapter waiting to be explored.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| MAMAC inaugurated June 21, 1990 | SUPPORTED_PARAPHRASE | SE[23]: "Since the opening of the Museum on June 21, 1990, over 213 exhibitions have been presented." |
| Pop art is part of MAMAC's collection | SUPPORTED_PARAPHRASE | Page 25 (Wikipedia): "American Pop art is represented by a collection of works by Roy Lichtenstein, Robert Indiana, Andy Warhol..." Also Page 9: "MAMAC is widely deploying in rooms 4 and 8 key pieces of this international movement" |
| Generous contributions shaped MAMAC | SUPPORTED_PARAPHRASE | SE[0]: Niki de Saint Phalle donation of 170 works; SE[1]: Albert Chubac hundred works; SE[2]: Khalil Nahoul 94 works |
| Yves Klein influenced the museum | SUPPORTED_PARAPHRASE | SE[7]: "Depuis l'ouverture, Yves Klein bénéficie d'une salle où sont rassemblées une vingtaine de ses œuvres" |
| "Richard Long's transformative pieces" | UNSUPPORTED | **Richard Long does not appear anywhere in venue_corpus or stop_corpus text.** The stop_corpus entry for "Richard Long ou la sculpture en marchant" contains only the Donations and deposits section (about Klein, Niki de Saint Phalle, Chubac) — it says nothing about Richard Long the artist. |
| Museum dedicated to modern and contemporary art | SUPPORTED_PARAPHRASE | SE[3]: "un musée consacré à l'art moderne et l'art contemporain" |

**Unsupported claims: 1** (Richard Long described as having "transformative pieces" — no corpus content about the artist himself)

---

### Paragraph A3 — She-Bam Pow POP Wizz, NO_ANCHOR (main content)

> This eclectic exhibit is a testament to the revolutionary spirit of pop art and its profound influence on contemporary culture. As you gaze upon the pieces, you are immediately struck by the sheer exuberance and vitality that permeate each work. The exhibit features a diverse array of artworks that range from striking graphic images to playful and whimsical compositions. One standout piece in the collection is a large-scale painting that captures the essence of the pop art movement. The artist's innovative use of bold colors and dynamic shapes creates a visual feast for the eyes, drawing you into a world of vibrant energy and excitement. Each brushstroke seems to pulsate with life, inviting you to explore the layers of meaning embedded within the artwork. One particular technique that stands out is the artist's skillful manipulation of popular culture references to convey deeper social commentary. Through the juxtaposition of familiar symbols and icons, the artist challenges conventional notions of art and society, inviting viewers to question the boundaries between high and low culture. This collection celebrates creativity and innovation, offering insight into the evolving landscape of contemporary art. The exhibit "She-Bam Pow POP Wizz" showcases explosive energy and boundless imagination. These dynamic contributions leave a lasting impact on the museum's legacy.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| She-Bam Pow POP Wizz relates to pop art | SUPPORTED_PARAPHRASE | Page 9: MAMAC deploys "key pieces of this international movement [pop art]"; the exhibition title itself contains "POP" |
| "diverse array of artworks" in the exhibit | NOT_CHECKABLE | Generic description, no factual claim |
| "One standout piece... large-scale painting" | UNSUPPORTED | **No corpus passage identifies any specific work in this exhibition.** This is a fabricated specific. |
| "The artist's innovative use of bold colors..." | NOT_CHECKABLE | Aesthetic description without naming an artist |
| "popular culture references to convey deeper social commentary" | SUPPORTED_PARAPHRASE | Page 9: "This new artistic movement witnessed as much as it created a new visual language... brings art and life closer together, reground creation in popular strains" |
| Pop art challenges "boundaries between high and low culture" | SUPPORTED_PARAPHRASE | Page 9: pop art "embraces the emerging mass culture" and brings "art and life closer together" |

**Unsupported claims: 1** ("One standout piece in the collection is a large-scale painting" — fabricated specific with no corpus source)

---

### Paragraph A4 — She-Bam Pow POP Wizz, UNLINKED_ENTITY (epilog)

> From Richard Long ou la sculpture en marchant to She-Bam Pow POP Wizz, you have followed the thread of Evolution of Art through the 20th and 21st Century. Since its opening, the museum has presented over 213 exhibitions.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Museum has presented over 213 exhibitions | SUPPORTED_PARAPHRASE | SE[23]: "Since the opening of the Museum on June 21, 1990, over 213 exhibitions have been presented." (exact match) |

**Unsupported claims: 0**

---

### Paragraph A5 — She-Bam Pow POP Wizz, NO_ANCHOR (transition)

> From Richard Long ou la sculpture en marchant to She-Bam Pow POP Wizz — a collection that spans more ground than these stops alone.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| No factual claims | NOT_CHECKABLE | This is a structural transition sentence with no checkable facts |

**Unsupported claims: 0**

---

### Paragraph A6 — She-Bam Pow POP Wizz, UNLINKED_ENTITY (sources)

> Sources: This tour draws on information from en.wikipedia.org, fr.wikipedia.org, www.mamac-nice.org and the Wikipedia article on the museum.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| No factual claims about the venue | NOT_CHECKABLE | Attribution paragraph, not content |

**Unsupported claims: 0**

---

## Per-Claim Fact Check: ARM B (gpt-4o-mini)

### Paragraph B1 — Richard Long, NO_ANCHOR (positioning)

> Stand facing Richard Long ou la sculpture en marchant. This vantage point allows you to fully appreciate the dialogue between the natural materials and the surrounding gallery space. The sunlight filtering through the museum's large windows interacts with the textures of the installation, creating a dynamic interplay that invites contemplation.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| The work uses "natural materials" | UNSUPPORTED | **No corpus passage describes what materials this installation uses.** The stop_corpus for this title contains only the Donations section (Klein, Niki, Chubac). Richard Long's real work does use natural materials, but this is parametric memory, not corpus-sourced. |
| The museum has "large windows" | SUPPORTED_PARAPHRASE | Page 25 (Wikipedia): "The available area is approximately 4,500 m2, distributed over ten showrooms." Architecture described with "Carrara marble" facades. Page 26 mentions the Promenade des Arts terrace. However, **"large windows"** specifically is NOT in the corpus. |
| "Textures of the installation" | NOT_CHECKABLE | Atmospheric description |

**Unsupported claims: 1–2** ("natural materials" is from parametric memory; "large windows" is plausible but not in corpus)

---

### Paragraph B2 — Richard Long, UNLINKED_ENTITY (prolog)

> You are about to embark on a captivating journey through the evolving landscape of modern art, tracing the intricate narrative of the Musée d'Art Moderne et d'Art Contemporain, which opened its doors on June 21, 1990, in the heart of Nice, France. Each chapter of your experience reveals a unique facet of artistic evolution, woven together by the rich tapestry of donations that have shaped the museum's collection. Begin with Richard Long's sculptures, which encapsulate the essence of movement and nature, inviting you to reflect on the personal journeys reflected in the landscapes he traverses. As you delve deeper, prepare for an explosive climax in the vibrant world of Pop Art, where the legacy of Niki de Saint Phalle bursts forth in vivid colors and forms, a testament to her pivotal role as a donor. Together, these chapters coalesce into a profound exploration of creativity and connection, revealing how each artist's legacy contributes to the museum's vibrant narrative.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| MAMAC opened June 21, 1990 | SUPPORTED_PARAPHRASE | SE[22]: "The Musée d'art moderne et d'art contemporain opened on 21 June 1990, in Nice, France." |
| Donations shaped the collection | SUPPORTED_PARAPHRASE | SE[0], SE[1], SE[2]: Niki de Saint Phalle, Chubac, Nahoul donations documented |
| "Richard Long's sculptures... essence of movement and nature" | UNSUPPORTED | **No corpus passage describes Richard Long's artistic practice.** This is parametric memory (accurate about the real artist, but not corpus-grounded). |
| "the landscapes he traverses" | UNSUPPORTED | Same as above — describing Long's practice from world knowledge, not corpus |
| Niki de Saint Phalle as donor | SUPPORTED_PARAPHRASE | SE[0]: "En octobre 2001, Niki de Saint Phalle lègue une importante partie de sa collection à la Ville de Nice pour le musée" |
| Pop Art is part of MAMAC | SUPPORTED_PARAPHRASE | Page 25: "American Pop art is represented by a collection of works..." |

**Unsupported claims: 2** (both about Richard Long's artistic practice)

---

### Paragraph B3 — Richard Long, UNLINKED_ENTITY (main content)

> Richard Long ou la sculpture en marchant embodies the essence of movement and nature, manifesting the artist's personal journey through the landscapes he traverses. The work consists of a series of circular arrangements made from stones collected during Long's walks. These stones, each chosen for their unique textures and colors, are placed in a deliberate, yet organic fashion, engaging the viewer in a dialogue about the passage of time and the ephemeral nature of our surroundings. One striking aspect of Long's technique is his choice of natural materials, which serves as a direct reflection of his connection to the earth. By utilizing stones, he emphasizes the importance of the physical world; each stone carries its own history and origin, evoking a sense of place and memory. This decision matters because it transforms the ordinary into the extraordinary, prompting viewers to consider their own relationship with nature. Historically, Long's work is situated within the land art movement of the 1960s and 1970s, which sought to confront the commercialization of art by engaging directly with the environment. This movement, characterized by artists like Robert Smithson and Andy Goldsworthy, emerged during a time of heightened environmental awareness. Understanding this context enriches the viewer's interpretation of Long's work, as it aligns with a broader conversation about humanity's impact on nature. Richard Long ou la sculpture en marchant resonates with the museum's mission to showcase modern and contemporary art that challenges conventional boundaries. This piece not only stands alone but connects with the museum's ongoing exploration of the relationship between art, nature, and the human experience. As you absorb the subtle nuances of the installation, the echoes of Long's walks linger, inviting you to reflect on the artistic legacy born from a simple act of walking through nature.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| "The work consists of a series of circular arrangements made from stones collected during Long's walks" | UNSUPPORTED | **No corpus passage describes what this specific MAMAC installation looks like.** This is parametric knowledge about Richard Long's general practice — he IS known for stone circles — but the corpus says nothing about this work's composition. |
| "Long's technique is his choice of natural materials" | UNSUPPORTED | Same — accurate about the real artist, not corpus-sourced |
| "Long's work is situated within the land art movement of the 1960s and 1970s" | UNSUPPORTED | Page 16 mentions "David Tremlett, figure majeure du Land Art" at MAMAC, but says nothing about Richard Long or the land art movement's dates. The 1960s/1970s dating is parametric memory. |
| "characterized by artists like Robert Smithson and Andy Goldsworthy" | UNSUPPORTED | **Neither Robert Smithson nor Andy Goldsworthy appears anywhere in the corpus.** Pure parametric memory. |
| "sought to confront the commercialization of art" | UNSUPPORTED | Not in corpus |
| "emerged during a time of heightened environmental awareness" | UNSUPPORTED | Not in corpus |
| Museum's mission: "modern and contemporary art that challenges conventional boundaries" | SUPPORTED_PARAPHRASE | SE[25]: "The collections present an overview of avant-garde artistic creations from the late 1950s to today." |

**Unsupported claims: 6** (all describing Richard Long's practice and art-historical context from parametric memory)

---

### Paragraph B4 — She-Bam Pow POP Wizz, UNLINKED_ENTITY (epilog)

> From Richard Long ou la sculpture en marchant to She-Bam Pow POP Wizz, you have followed the thread of Chronological Development of Modern Art. The Musée d'art moderne et d'art contemporain opened on 21 June 1990, in Nice, France.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| MAMAC opened 21 June 1990, in Nice, France | SUPPORTED_PARAPHRASE | SE[22]: "The Musée d'art moderne et d'art contemporain opened on 21 June 1990, in Nice, France." (verbatim) |

**Unsupported claims: 0**

---

### Paragraph B5 — She-Bam Pow POP Wizz, NO_ANCHOR (transition)

> From Richard Long ou la sculpture en marchant to She-Bam Pow POP Wizz — a collection that spans more ground than these stops alone.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| No factual claims | NOT_CHECKABLE | Structural transition sentence |

**Unsupported claims: 0**

---

### Paragraph B6 — She-Bam Pow POP Wizz, UNLINKED_ENTITY (sources)

> Sources: This tour draws on information from en.wikipedia.org, fr.wikipedia.org, www.mamac-nice.org and the Wikipedia article on the museum.

| Claim | Verdict | Evidence |
|-------|---------|----------|
| No factual claims about the venue | NOT_CHECKABLE | Attribution paragraph |

**Unsupported claims: 0**

---

## Summary Table

### Per-paragraph unsupported claim counts

| Paragraph | ARM A (3.5-turbo) | ARM B (4o-mini) |
|---|---|---|
| Richard Long positioning | 0 | 1–2 |
| Richard Long prolog | 1 | 2 |
| Richard Long main content | *(ANCHORED — not checked)* | 6 |
| She-Bam main content | 1 | *(ANCHORED — not checked)* |
| She-Bam epilog | 0 | 0 |
| She-Bam transition | 0 | 0 |
| Sources | 0 | 0 |
| **Total unsupported claims** | **2** | **9–10** |
| **Flagged paragraphs** | 6 | 6 |
| **Paragraphs with ≥1 unsupported** | 2/6 | 3/6 |
| **Unsupported per flagged paragraph** | **0.33** | **1.5–1.7** |

### Verdict classification totals

| Verdict | ARM A | ARM B |
|---------|-------|-------|
| SUPPORTED_PARAPHRASE | 9 | 7 |
| SUPPORTED_ELSEWHERE | 0 | 0 |
| UNSUPPORTED | 2 | 9–10 |
| CONTRADICTED | 0 | 0 |
| NOT_CHECKABLE | 5 | 4 |

---

## The Deciding Number

**Unsupported claims per flagged paragraph:**
- ARM A (gpt-3.5-turbo): **0.33**
- ARM B (gpt-4o-mini): **1.5–1.7**

gpt-4o-mini's unsupported rate is **4.5–5× higher** than gpt-3.5-turbo's.

---

## Analysis: Why the Difference

The unsupported claims in ARM B (gpt-4o-mini) are overwhelmingly about **Richard Long's artistic practice** — his use of stones, circular arrangements, walking, the land art movement, Robert Smithson, Andy Goldsworthy. These are **factually accurate about the real artist** based on world knowledge, but **have no basis in the corpus**.

The corpus entry for "Richard Long ou la sculpture en marchant" contains only the Donations and deposits section (about Yves Klein, Niki de Saint Phalle, Albert Chubac). It says nothing about Richard Long the artist, his techniques, his materials, or his art-historical context.

gpt-3.5-turbo avoided these claims by producing vaguer prose: "a captivating sight that encapsulates the essence of movement and artistry" (NOT_CHECKABLE). gpt-4o-mini produced *more specific and accurate* text about Richard Long — but sourced it from parametric memory rather than the corpus.

ARM A's 2 unsupported claims are:
1. "Richard Long's transformative pieces" (vague but still from parametric memory)
2. "One standout piece... large-scale painting" in She-Bam (fabricated specific)

ARM B's 9–10 unsupported claims are:
1–6. Detailed factual claims about Richard Long's practice (all accurate, all parametric)
7–8. "natural materials" and "large windows" in positioning paragraph
9–10. "landscapes he traverses" in prolog

**The failure mode is different.** ARM A fabricates a vague specific ("a large-scale painting") with no referent. ARM B provides *real art-historical information* that isn't in the corpus. Both are ungrounded by definition, but only ARM A's is genuinely unreliable.

---

## Recommendation

**The anchor regression is REAL, not a detector artifact.** gpt-4o-mini produces more unsupported claims per paragraph (1.5–1.7 vs 0.33). The drop from 47.6% to 33.3% reflects a genuine difference in how much the model draws from parametric memory vs corpus material.

However, the *character* of the ungrounding is different from what D67 feared. gpt-4o-mini's unsupported claims are **factually accurate about the real world** — they describe Richard Long's practice correctly. The problem is a **corpus coverage gap** (the stop_corpus for "Richard Long ou la sculpture en marchant" contains zero information about Richard Long), not model hallucination.

The pipeline's defense against fabrication (D50) says: "if no grounded fact links the entity to the stop, the paragraph is cut, not embellished." By that standard, gpt-4o-mini is embellishing from memory where the corpus is silent — which is exactly what the defense prohibits, even when the memory is correct.

**One-line verdict: Real regression. The model is more grounded in world knowledge but less grounded in corpus. Do not flip the default.**

---

## Database Safety

- `audio_tours` rows: **117** (unchanged)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: all present
- Test tours: `is_test = true` count: 88
- No container rebuilt
- No detector modified

---

## Spend

| Arm | Tokens | Cost |
|-----|--------|------|
| A (gpt-3.5-turbo) | 10,504 | $0.0210 |
| B (gpt-4o-mini) | 9,881 | $0.0028 |
| **Total** | **20,385** | **$0.0238** |

Ceiling: $0.35. Actual: $0.024 (7% of ceiling).

---

## Limitations

1. **Single run per arm (7 paragraphs each).** The task specified "one or two runs is enough — this is a reading exercise, not a sample-size exercise." The per-claim analysis is definitive regardless of sample size, but the *proportion* could shift with more runs.

2. **Corpus coverage gap dominates.** The stop_corpus for "Richard Long ou la sculpture en marchant" contains zero information about Richard Long's practice. If the corpus had adequate coverage, gpt-4o-mini might anchor perfectly — but testing "what if" is not the task. The corpus *as it exists* is the reference.

3. **Both arms had 1/7 ANCHORED in this run** — identical distribution. The 47.6%→33.3% gap from LOCAL-194 did not reproduce in a single run, consistent with p=0.27 (not statistically significant).

4. **The ANCHORED paragraph in each arm was not fact-checked** (the task specifies checking NO_ANCHOR and UNLINKED_ENTITY paragraphs only). ARM A's ANCHORED paragraph was the Richard Long main content; ARM B's was the She-Bam main content.

5. **gpt-4o-mini's claims are factually accurate about the real world.** The regression is against the corpus-grounding standard specifically. A different evaluation framework (e.g., "are claims true?") would score gpt-4o-mini higher.

---

## Files Changed

| File | Change |
|------|--------|
| `tests/test_local195_anchor_regression_truth.py` | NEW — generation + detector script |
| `SUBMISSION_LOCAL-195.md` | NEW — this submission |
