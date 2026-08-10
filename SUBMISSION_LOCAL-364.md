# SUBMISSION_LOCAL-364.md — Exhibition Checklist Retrieval

## Per-file Summary

| File | Purpose |
|------|---------|
| `exhibition_checklist.py` (new, 410 lines) | Exhibition page discovery, fuzzy title matching, work extraction, date parsing, closed-show detection. Self-contained module with no LLM dependency — proven offline against real HTML. |
| `generate_tour_text.py` (+200 lines modified) | Restructured the `_exhibition_scope` block: checklist retrieval runs FIRST; LOCAL-362 creator filter is now the labelled FALLBACK. Closed-show early return. Honest-degradation note injected into prolog prompt. |
| `tests/test_local364_exhibition_checklist.py` (new, 30 tests) | TTL choice, fuzzy matching, date parsing, extraction from 3 page shapes, closed detection, honest degradation labelling, unscoped bypass. |

## Verification Table

| request | path taken | stops | source of stops |
|---|---|---|---|
| `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA` | **fallback** (prose-only page — MFA uses JS-rendered content) | Works by Picasso/Miró/Dalí from MFA's SPARQL permanent collection | `https://www.mfa.org/exhibition/picasso-miro-dali-unbound` found but static HTML contains no structured checklist. Fallback labelled in prolog. |
| A venue+exhibition where the site publishes no checklist: **Met Breuer "Unfinished" (closed 2016)** | **closed** | NONE — tour refused | "Exhibition closed" message returned. A tour of a dismounted exhibition is worse than no tour. |
| `Museum of Fine Arts, Boston` | **unscoped bypass** — `_exhibition_scope=None`, deterministic fill as before | Venue-wide documented works | Same path as before LOCAL-364 (no scope detected → existing D1v2 verification) |
| `Palais Lascaris, Nice, France` | **unscoped bypass** — `_exhibition_scope=None` | Venue-wide documented works | Benchmark unchanged (no scope → existing path, museum score bounds hold) |

## Exhibition Page Crawl — Proven Offline (no API key needed)

```
$ python3 -c "from exhibition_checklist import find_exhibition_checklist; ..."

[LOCAL-364] Searching for exhibition 'Picasso, Miró, Dalí: Unbound exhibition' on https://www.mfa.org
[LOCAL-364] Found exhibition listing: https://www.mfa.org/exhibitions (11864 chars)
[LOCAL-364] Matched exhibition: 'Picasso, Miró, Dalí: Unbound' (score: 0.80)
[LOCAL-364] Exhibition URL: https://www.mfa.org/exhibition/picasso-miro-dali-unbound
[LOCAL-364] No closing date found — assuming exhibition is current
[LOCAL-364] Exhibition page is prose-only — no checklist extractable
Path: fallback
Reason: Exhibition page at https://www.mfa.org/exhibition/picasso-miro-dali-unbound
        contains only prose — no individual works could be extracted
Shape: prose_only
```

The MFA page IS found (score 0.80 match), but MFA's exhibition detail pages are
JS-rendered — the static HTML contains no structured work list. This fires the
honest-degradation path correctly: fallback to creator filter with the reason stated.

## Page Shapes Handled

1. **structured_checklist**: Lines matching "Title, Artist, Year" or "Artist, Title, Year"
   (disambiguated by heuristic: title-indicator words vs person-name pattern).
   Example: `Guernica Study, Pablo Picasso, 1937`

2. **highlights_only**: Links pointing to `/collections/object/` or `/art/object/`
   with proper-noun link text that is not a navigation label.

3. **prose_only**: Exhibition page exists but contains only descriptive paragraphs.
   Returns empty checklist, triggers fallback with honest reason.

## Cache TTL Decision

Exhibition data uses a **3-day TTL** (`EXHIBITION_CACHE_TTL_DAYS = 3`).

Rationale: The venue_cache uses 30 days because permanent collections change rarely.
Exhibitions rotate every few weeks/months. A stale exhibition checklist is actively
harmful — it would tour works that are no longer on display. 3 days is:
- Short enough to catch exhibitions closing mid-run
- Long enough to avoid re-crawling the venue site on every request
- Implemented as a module constant (easily configurable via env var if needed)

## Limitations

1. **JS-rendered pages**: The MFA, Met, Tate, and many large museums render exhibition
   detail content dynamically. Static HTML crawling cannot extract their checklists.
   This is honestly handled: the page is found (title match works), but extraction
   returns empty, triggering the labelled fallback.

2. **LLM half unproven**: The prolog honest-degradation note injection (lines added to
   the prolog prompt when `_exhibition_stops_source == 'creator_filter'`) cannot be
   proven without an `OPENAI_API_KEY` run. Handing to LEAD for that half.

3. **Date parsing**: Handles US/European/ISO formats and common patterns like "Through
   March 9, 2025". Does not handle relative dates ("closes next month") or languages
   other than English for date text.

## Test Results

```
tests/test_local364_exhibition_checklist.py      30 passed
tests/test_local362_exhibition_scope.py          23 passed
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds  2 passed
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty 2 passed
─────────────────────────────────────────────────────────────
Total                                            57 passed, 0 failed
```
