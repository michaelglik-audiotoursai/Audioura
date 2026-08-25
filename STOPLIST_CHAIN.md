# The stop list chain — one call, captured on the wire

Generated 2026-08-25 16:13 · model `gpt-4o-mini` · temperature `0.0` · HTTP 200

This is the call whose result becomes the tour's stop list. Nothing here is
reconstructed — `requests.post` was wrapped inside `exhibition_checklist`.

---

## LINK 1 — the user-requested string

```
Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA
```

Resolved by production to `http://www.mfa.org/exhibition/picasso-miro-dali-unbound`
(page fetched: 6869 chars raw)

---

## LINK 2 — the prompt sent to OpenAI

Request parameters actually on the wire: `model=gpt-4o-mini`, `temperature=0.0`, `max_tokens=1500`, `seed=**ABSENT**`

### system message (880 chars)

```
You are an exhibition checklist extractor. Given the visible text from a museum exhibition page, extract every artwork/work mentioned with its metadata. Return ONLY a JSON array. Each element has these fields (omit any not stated on the page):
- "title": the work's title (string, required)
- "artist": the artist who created the work (string)
- "date": date or year of creation (string)
- "medium": materials or technique (string)
- "publisher": publisher name if stated (string)
- "credit_line": provenance/gift/bequest (string)

Rules:
- Extract ONLY what the page text explicitly states. Do NOT complete from your own knowledge.
- An artist named without a specific work title is NOT a work — skip it.
- Titles in italics (marked with * or _) are work titles.
- Do not invent titles, dates, or media not present in the text.
- Return [] if no specific works are identifiable.

```

### user message (2899 chars)

```
Exhibition: Picasso, Miró, Dalí: Unbound

Page text:
Picasso, Miró, Dalí: Unbound
Related Events
Livres d’Artiste: Picasso, Miró, Dalí
$5 Third Thursday
Virtual Member Lecture: Picasso, Miró, Dalí
Extras
Step Inside the Exhibition
Sponsors
Abstract black-line drawing with bursts of red, yellow, green, and blue.
detail of two-page spread with gibberish handwritten text, with the center burned out
A Sound Bites concert, as seen from above, taking place in the Linde Family Wing for Contemporary Art
Joan Miró, Le Lézard aux plumes d’or (The Lizard with Golden Feathers), published by Louis Broder, printed by Mourlot Frères, Paris, 1971
Joan Miró, Le Lézard aux plumes d’or (The Lizard with Golden Feathers) (detail), published by Louis Broder, printed by Mourlot Frères, Paris, 1971. Illustrated book with 40 color lithographs (including wrapper front and cover); publisher’s vellum. Gift of Boris Fridman. © Successió Miró / Artists Rights Society (ARS), New York / ADAGP, Paris 2026.
Bold, experimental, extravagant, and unbound, both literally and in the creative minds that produced them, livres d’artiste had no precedent. At the turn of the 20th century, they revolutionized the book as an art form. Livres d’artiste attracted many famous practitioners—Pablo Picasso, Joan Miró, and Salvador Dalí among them—but they were also deeply collaborative ventures. Authors, publishers, designers, and printmakers played essential roles in bringing them to life.
This exhibition introduces the imaginative world of this form through a group of extraordinary works by Spanish artists. Visitors can explore how images, words, and typography intersect, often in intricate ways that defy expectations. Some artists interpreted foundational texts, as Dalí did in his 1974 illustrations for Sigmund Freud’s Moses and Monotheism; others partnered with writers to devise images and words in harmony at the outset, as in Juan Gris and French poet Pierre Reverdy’s Au Soleil du Plafond (1955). Rarely on view, and resisting easy categorization, these livres d’artiste invite visitors into a world of artistic ambition in which creativity and the power of collaboration led to some of the most singular and compelling achievements of publishing in the 20th century.
Wednesday, September 16–Wednesday, October 7, 2026
Thursday, October 15, 20265:00 pm–10:00 pm
Wednesday, December 9, 20266:30 pm–7:30 pm
A post shared by Museum of Fine Arts, Boston (@mfaboston)
Lead support is provided by the Jean S. and Frederic A. Sharf Exhibition Fund.
Major support is provided by the Lia and William Poorvu Fund and an anonymous funder.
Additional support comes from Peter and Catherine Creighton, Erinn and Jason Rhodes, the Dr. Lawrence and Roberta Cohn Fund for Exhibitions, the Ellen and Robert Jaffe Fund, and an anonymous funder.

Extract all artworks/works mentioned with their metadata. Return ONLY a JSON array.
```

---

## LINK 3 — the raw return from OpenAI

tokens: prompt=889, completion=123 · finish_reason=`stop` · system_fingerprint=`fp_f282d56213`

### message content, verbatim

```
```json
[
    {
        "title": "Le Lézard aux plumes d’or (The Lizard with Golden Feathers)",
        "artist": "Joan Miró",
        "date": "1971",
        "medium": "Illustrated book with 40 color lithographs (including wrapper front and cover); publisher’s vellum",
        "publisher": "Louis Broder",
        "credit_line": "Gift of Boris Fridman. © Successió Miró / Artists Rights Society (ARS), New York / ADAGP, Paris 2026."
    }
]
```
```

---

## What the pipeline then made of it

`prose_llm_extract_works` returned **1 work(s)** after its own validation:

1. `Le Lézard aux plumes d’or (The Lizard with Golden Feathers)` — artist='Joan Miró' date='1971'

Each surviving entry becomes one stop in the tour.
