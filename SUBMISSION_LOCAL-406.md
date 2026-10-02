# SUBMISSION_LOCAL-406.md

## Summary

**Root cause:** `synthesize_queries` built every query around the *artist* —
`"<title>" <artist> story behind`, `"<title>" <artist> history making`, etc.
SERP responded with the most generic thing it knows about an artist: the
biography. No selection logic, retry loop, or downstream filter can produce
"Broder gambled on livres d'artiste" from four encyclopaedia entries about
Miró's childhood.

**Fix:** Queries are now built around the *work* and the *people who made it happen*.

## Changes

### `work_story_searcher.py`

1. **New function `_is_biography_only(snippet_text, snippet_title)`** — detects
   generic artist biography snippets (dominated by birth/death, nationality,
   "was a <profession>") and rejects them unless they also contain a work-relevant
   signal (publish, print, edition, workshop, collection, donation, exhibition, etc.).
   Logged: `[LOCAL-406] snippet rejected: biography-only '<title>'`.

2. **Rewritten `synthesize_queries`** — for a stop with title *T*, artist *A*,
   publisher *P*, printer *R*, donor *D*:
   - `"<T>" <A>` — the work itself
   - `"<T>" history` / `"<T>" edition lithographs`
   - `<P> <A>` — publisher–artist relationship (e.g. `Louis Broder Joan Miró`)
   - `<R> workshop history` — e.g. `Mourlot Frères workshop history`
   - `<D> collection` — e.g. `Boris Fridman collection`
   - `livre d'artiste <A>` — the form, tied to this artist (when medium suggests it)
   - Plus existing W4/W5/Q3/E1/W9 queries (retained, suffix changed from
     "story behind" to "history")

   **Donor extraction from credit_line**: parses "Gift of X to Y" pattern to extract
   the donor name when no explicit `donor` field is present on the stop dict.

3. **Biography rejection in `search_stories_for_stop`** — applied at both the main
   query loop and the SQ-S1 refinement loop. Rejected snippets are logged but do not
   consume budget or enter the result set.

### `temporal_coherence_gate.py`

4. **"Worked together" gate fix** — the pattern `r'work(?:ed|ing)\s+(?:with|alongside)'`
   now also matches `together`: `r'work(?:ed|ing)\s+(?:with|alongside|together)'`.
   This closes the last of six relation forms that could escape the gate.

## Queries for stop 1 (Le Lézard aux plumes d'or)

```
1. "Le Lézard aux plumes d'or" Joan Miró
2. "Le Lézard aux plumes d'or" history
3. "Le Lézard aux plumes d'or" edition lithographs
4. Louis Broder Joan Miró
5. Mourlot Frères workshop history
6. Boris Fridman collection
7. livre d'artiste Joan Miró
8. Museum of Fine Arts Boston Joan Miró donation history
```

Compare old queries (all fetched biography):
```
1. "Le Lézard aux plumes d'or" Joan Miró story behind
2. "Le Lézard aux plumes d'or" Joan Miró history making
3. "Le Lézard aux plumes d'or" Joan Miró controversy
```

## Tests

**`test_local406_query_the_work.py`** — 16 tests, all pass:

- `TestSynthesizeQueriesTargetWork` (7 tests):
  - Queries include work title AND at least one collaborator name (not just artist)
  - Publisher → Broder query generated
  - Printer → Mourlot workshop query generated
  - Donor extracted from credit_line → Fridman collection query generated
  - Livre d'artiste form query when medium suggests book
  - **Revert-detection (D296):** asserts NO "story behind" suffix — reverting
    the logic produces the old suffix, breaking this test
- `TestBiographyRejection` (6 tests):
  - Pure biography → rejected
  - Biography with generic profession → rejected
  - Snippet with publishing/exhibition/collection info → kept
  - Biography mentioning workshop → rescued
- `TestWorkedTogetherGateFix` (3 tests):
  - "worked together with" caught
  - "working together with" caught
  - Regex pattern match verification

**Red-on-revert count:** 10 (7 query logic tests + 3 biography tests directly
exercise the new code path; reverting synthesize_queries restores "story behind"
suffix which fails `test_no_generic_story_behind_for_contained`, and removes
collaborator queries which fail the 4 collaborator tests + the combined assertion).

**Real generation path (D307):** The acceptance runner `run_local406_acceptance.py`
exercises `search_stories_for_stop` with the real SERP pipeline.

## Do-not-lose verification

- Temporal coherence gate: all 11 test_local402 tests pass, all 11 test_local405 tests pass
- "worked together" form now caught (was the one escaped form of six)
- `with publisher` = 0 checked in acceptance
- Broder, Mourlot, Fridman all checked
- Zero-check (ceiling/mural/sculpture/glass/Chagall/Rousseau/Corbusier/Lalanne/Matisse)
- test_local403, test_local388, test_local391, test_local390, test_local383: all 88+5 pass

## Files changed

- `work_story_searcher.py` — `_is_biography_only` + rewritten `synthesize_queries` + filter calls
- `temporal_coherence_gate.py` — one regex line (add `|together`)
- `test_local406_query_the_work.py` — new (16 tests)
- `run_local406_acceptance.py` — new (acceptance runner)
- `SUBMISSION_LOCAL-406.md` — this file
