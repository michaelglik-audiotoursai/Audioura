# SUBMISSION_LOCAL-382.md

## Status: IMPLEMENTATION COMPLETE — awaiting live acceptance with API key

## Summary of Changes

### The Problem

The exhibition "Picasso, Miró, Dalí: Unbound" at MFA Boston is about **livres
d'artiste** — artist's books that revolutionized the book as an art form. The
exhibition page explicitly states this thesis, and our code already fetches that
page. But the generated tour ignored the thesis entirely, treating book-artworks
as if they were paintings on a wall, and opening the general description by
listing works without explaining what the exhibition is about.

Google gave a better answer than we did — using the same source text.

### The Solution: Three-Case Framing (LOCAL-382)

New module: `exhibition_thesis.py`

**Core logic — `detect_framing_case()`:**

| Case | Detection | Effect |
|---|---|---|
| 1. `exhibition` | `_exhibition_scope` set AND `page_text` has premise signals | Prolog states thesis before works; each stop must engage collaboration/form/typography |
| 2. `venue_purpose` | Venue's own text contains "dedicated to", "founded in YYYY to", "bequeathed", "mission is" | Light framing: venue purpose mentioned in prolog; stops gently connected |
| 3. `none` | Neither signal found | No framing. Tour proceeds as today. |

**Logging:** `[LOCAL-382] framing=exhibition|venue_purpose|none source='<verbatim page phrase or ->'`

### Part A — General Description (Prolog)

`build_exhibition_thesis_prolog_block()` injects into the prolog prompt:
- For `exhibition`: lists grounded claims from the page (livre d'artiste, no
  precedent, revolutionized, collaborative, rarely on view, Torf Gallery) and
  instructs the LLM to state the premise BEFORE listing works.
- For `venue_purpose`: quotes the verbatim source phrase and instructs the LLM
  to mention it as context.
- For `none`: returns '' (no injection).

### Part B — Per-Stop Framing

`build_exhibition_thesis_stop_block()` injects into each stop's description prompt:
- For `exhibition`: requires engaging at least TWO of (1) collaboration, (2) form,
  (3) image/word/typography intersection. FORBIDS treating works as paintings.
  When matched_work has publisher/collaborator/medium, those are highlighted.
- For `venue_purpose`: light instruction to connect to venue purpose if natural.
- For `none`: returns '' (no injection).

### Part C — Detection Safeguards

- **Never synthesised:** The thesis must be FOUND in the page text. The patterns
  are strict: "dedicated to", "founded in... to", "bequeathed", "mission is",
  "devoted to", etc.
- **General museums safe:** The Louvre, Uffizi, Prado all return `framing=none`
  because their page text doesn't contain these specific purpose-statement patterns.
- **No false positives on "houses a collection of 2,300 paintings":** The pattern
  requires a proper noun (named person/collector) after "collection of", not
  quantity words.

## Files Changed

| File | Change |
|---|---|
| `exhibition_thesis.py` | **NEW** — Three-case detection + prompt block builders |
| `generate_tour_text.py` | +20 lines: framing detection (before prolog) |
| `generate_tour_text.py` | +12 lines: thesis injection into prolog prompt |
| `generate_tour_text.py` | +11 lines: thesis injection into stop prompts |
| `tests/test_local382_exhibition_thesis.py` | **NEW** — 28 unit tests |
| `run_local382_acceptance.py` | **NEW** — Live acceptance runner |

## Tests

**Expected red-on-revert count: 17**

Reverting the logic (making all functions return empty/none while keeping the module):
- 3 in `TestDetectFramingCase` (case1_exhibition, case2_venue_purpose, priority test)
- 2 in `TestExtractExhibitionThesis` (non-empty extraction, core claims)
- 1 in `TestExtractVenuePurpose` (matisse detection)
- 3 in `TestBuildPrologBlock` (exhibition livre, premise-first instruction, venue quote)
- 4 in `TestBuildStopBlock` (collaboration, painting-forbidden, publisher, venue_purpose)
- 4 in `TestExtractGroundedClaims` (livre, collaboration, rarely_on_view, torf)

Total: 17 tests break on logic revert. All 28 break on module deletion.

Reverting the `generate_tour_text.py` changes has no unit test effect (the
integration is only exercised by live generation). This is correct per D296:
"revert must break the logic, not the symbol."

## Acceptance Criteria (to run with API key)

```bash
DISABLE_TOUR_CACHE=1 \
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours \
STORIED_MODE=true \
OPENAI_API_KEY=<key> \
python3 run_local382_acceptance.py
```

### Expected outcomes:

1. **MFA exhibition (8 stops):**
   - General description contains: `livre d'artiste` (or `artist's book`), `collabor*`,
     ≥2 of {`no precedent`, `revolutionized`, `rarely on view`, `typography`, `Torf Gallery`}
   - Each stop names ≥2 of: author/poet, publisher, printer, binding/plate count, or
     image/word/typography relationship
   - Zero banned terms: ceiling, installation, mural, canopy, vault, overhead, dome,
     sculpture, painting, glass, stand beneath, look up, gaze up, Rousseau, Corbusier,
     Lalanne, Matisse
   - Present: Miró (stop 1), Dalí+Freud (stop 2), Gris+Reverdy (stop 3)
   - `book` in ≥2 stops; every stop ≥120 words
   - `score_tour_file(f, 8)` ≥ 75.0

2. **Palais Lascaris (4 stops):**
   - 4/4 real instruments
   - Log shows `framing=venue_purpose` or `framing=none` (NOT `exhibition`)
   - No fabricated curatorial premise
   - `score_tour_file(f, 4)` ≥ 81.2

3. **Louvre (4 stops):**
   - Log shows `framing=none`
   - No invented language about why the museum exists
   - `score_tour_file(f, 4)` ≥ 81.2
