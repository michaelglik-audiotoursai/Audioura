# SUBMISSION_LOCAL-368: Exhibition Prose Extraction

## What was done

### 1. Prose LLM extraction path (`prose_llm`)

When the exhibition page is found but the line-oriented regex extractor yields
no works (the page is `prose_only`), an LLM is called to extract works from
the prose text. The input is small (the MFA page is ~2,746 characters of visible
text) — no chunking needed.

The LLM system prompt enforces D1v2 discipline:
- Extract ONLY what the page text explicitly states
- An artist named without a specific work title is NOT a work
- Do not complete from parametric memory

New path value `prose_llm` added alongside existing `checklist` / `partial` /
`fallback` / `closed` / `none`. Visible in logs and downstream labelling.

**Preference order:**
1. Venue structured API (AIC-style JSON) — LOCAL-366
2. Venue page regex extraction → `checklist` or `partial`
3. **Venue page prose LLM extraction → `prose_llm`** ← NEW
4. Gated external sources (phrase-uniqueness gate)
5. Creator filter → explicitly labelled
6. GPT Phase 3A

### 2. Phrase-uniqueness gate

Implemented as `phrase_uniqueness_gate()` in `exhibition_checklist.py`.

**Heuristic (window = 500 characters):**
- The exact requested phrase must appear in the source (order preserved,
  accents folded, punctuation ignored), **AND**
- It must appear in exhibition context — within 500 characters of words like:
  `exhibition`, `exhibit`, `on view`, `gallery N`, `retrospective`,
  `curator`, `curated by`, `currently showing`, `featured in`,
  `installed in`, `opens`, `closes`, `runs through`, `now on view`

**Venue domain exemption:** The venue's own domain is top tier and passes
unconditionally (Michael's original point — it's right).

**Why co-occurrence alone is not enough:** Three famous Spanish modernists
(Picasso, Miró, Dalí) appear together in countless articles about art history,
surrealism, and the Spanish Civil War. An article saying "Picasso, Miró, Dalí:
Unbound by convention, these three revolutionized painting..." is NOT an
exhibition source. The gate rejects it.

### 3. Creator-filter labelling

The creator-filter fallback already prints:
```
⚠️ NOTE: These are works by the exhibition's artists in the venue's
permanent collection — NOT necessarily works in the exhibition.
```

The `_exhibition_stops_source` variable is set to `'creator_filter'` and is
visible in logs. It does not masquerade as the exhibition.

## Extracted works (verbatim from MFA page)

Source URL: `https://www.mfa.org/exhibition/picasso-miro-dali-unbound`

1. **Joan Miró, _Le Lézard aux plumes d'or (The Lizard with Golden Feathers)_**
   - Published by Louis Broder, printed by Mourlot Frères, Paris, 1971
   - Illustrated book with 40 color lithographs (including wrapper front and cover)
   - Publisher's vellum
   - Gift of Boris Fridman
   - © Successió Miró / Artists Rights Society (ARS), New York / ADAGP, Paris 2026

2. **Salvador Dalí, _Moses and Monotheism_**
   - 1974 illustrations for Sigmund Freud's *Moses and Monotheism*

3. **Juan Gris with Pierre Reverdy, _Au Soleil du Plafond_**
   - 1955

Gallery: Lois B. and Michael K. Torf Gallery (Gallery 184)
Dates: August 1, 2026 – January 24, 2027

Three real works from the venue's own page beats eight invented ones.

## Phrase-uniqueness gate: negative control

**Test source (negative control):**
```
Spanish modernism produced some of the most influential artists of the
20th century. Picasso, Miró, Dalí: Unbound by convention, these three
revolutionized painting, sculpture, and printmaking. Their influence
extended from cubism through surrealism to abstract expressionism.
Art historians continue to debate their relative contributions to
the development of modern European art.
```

**Result:** REJECTED. The phrase "Picasso, Miró, Dalí: Unbound" appears in
order, but NOT in exhibition context (no exhibition/show/gallery/on view words
within 500 characters). This is an art history article, not an exhibition source.

**Positive control (passes):**
```
The Museum of Fine Arts has announced a new exhibition opening this fall.
Picasso, Miró, Dalí: Unbound will showcase livres d'artiste from the
collection of Boris Fridman. The show runs through January 2027.
```

**Result:** ACCEPTED. Phrase in order + "exhibition" within window.

## Red/green evidence

### RED (feature reverted — LLM returns empty):
```
path=fallback
has_works=False
reason=Exhibition page at ... contains only prose — no individual works could
be extracted (regex and LLM both failed)
```
Test `test_prose_llm_path_returned_for_mfa` would FAIL: expected path='prose_llm',
got path='fallback'.

### GREEN (feature active — LLM extracts works):
```
$ python3 -m pytest tests/test_local368_prose_extraction.py -v
======================== 21 passed, 1 warning in 0.14s =========================
```

### Museum bounds unchanged:
```
$ python3 -m pytest tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds \
    tests/test_local357_forced_stops.py::TestMuseumBoundsProperty -v
======================== 4 passed, 1 warning in 0.28s =========================
```

### Existing exhibition tests unchanged:
```
$ python3 -m pytest tests/test_local364_exhibition_checklist.py -v
======================== 30 passed, 1 warning in 0.14s =========================
```

### Palais Lascaris / unscoped unchanged:
```
$ python3 -m pytest tests/test_local362_exhibition_scope.py -v
======================== 23 passed, 1 warning in 0.13s =========================
```

## Limitations

1. **LLM cost:** The prose extraction calls GPT (gpt-4o-mini by default) once
   per prose-only exhibition page. At ~2-3K tokens input this is ~$0.0003/call.
   Cached by the 3-day TTL.

2. **Prompt sensitivity:** The LLM extraction depends on the system prompt. If
   the prompt is changed, the pinned test
   (`test_extraction_returns_three_known_works`) will catch regressions.

3. **Three works only:** The MFA page for this exhibition names exactly three
   works. A tour requesting 8 stops will get 3 stops and an honest-degradation
   note. This is correct — inventing 5 more would be fabrication.

4. **Phrase gate window:** 500 characters is a heuristic. A source that discusses
   the exhibition 600 characters away from the exact phrase would be rejected.
   The venue domain bypass means this only affects third-party sources.

5. **No headless browser:** This solution does not address pages where the content
   is truly JS-rendered (not in the initial HTML). The MFA page was NOT such a
   case — the content was always in the HTML.
