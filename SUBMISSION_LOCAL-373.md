# SUBMISSION_LOCAL-373.md

## Problem

Live extraction of `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`
returned 1 work; the same fixture returned 3 (in mocked tests). LOCAL-372
validated its nav filter fix against the fixture, but the fixture and live fetch
diverged in ways that matter:

- **Before fix (live/fixture identical on OLD code):** `page_text=6572`,
  `after_filter=5088`, `window=5000` (truncated). All three works were already
  in the window, but at 44% footer noise the LLM was conservative.
- **The concatenated title** `'Picasso, Miró, Dalí: UnboundThrough January 24,
  2027'` appeared on the listing page because `<p[^>]*>` matched `<picture>`
  elements. This was stored as `best_match_title` but NOT passed to the LLM
  prompt (the user-supplied exhibition name is passed instead).

## Root Causes (three)

1. **`<p>` regex matched `<picture>`, `<pre>`, `<path>`**  
   `<p[^>]*>` matches `<picture>` because 'icture' chars are all `[^>]`.  
   Effect: false paragraph content (concatenated titles on listing pages,
   duplicate credit noise on detail pages).

2. **No deduplication in `_fetch_page`**  
   Responsive sites repeat nav menus (155 → 83 unique `<li>` items) and image
   slides repeat the same credit `<p>` and `<img alt>` elements.  
   Effect: 3130 chars of list items → 1670; credit line appeared twice → once.

3. **Footer boundary undetected**  
   Lines like "Getting Here", "Dining", "Collections Search" (2195 chars = 44%
   of window) survived `_NAV_LINE_PATTERNS` because they don't match the
   specific patterns. They're generic site navigation that the pattern-by-pattern
   approach can never fully enumerate.  
   Fix: detect footer boundary (street address or © copyright line) and stop.

## Fix

- `exhibition_checklist.py` — `_fetch_page`:
  - Paragraph regex: `<p(?:\s[^>]*)?>(.+?)</p>` (was `<p[^>]*>(.*?)</p>`)
  - Deduplicate paragraphs, img_alts, and list_items via `set()` tracking
- `exhibition_checklist.py` — `_filter_nav_from_page_text`:
  - Added `_FOOTER_BOUNDARY_PATTERNS` (street address / © / All Rights Reserved)
  - Stop collecting after 500+ chars when boundary detected

## Four Numbers (live vs fixture, now aligned)

|                         | Before fix | After fix |
|-------------------------|-----------|-----------|
| `page_text` (live)      | 6572      | 4207      |
| `after_filter` (live)   | 5088      | 2183      |
| `page_text` (fixture)   | 6572      | 4207      |
| `after_filter` (fixture)| 5088      | 2183      |
| `window` sent to LLM    | 5000 (truncated) | 2183 (no truncation) |
| Live == Fixture?         | ✗ (in OLD code, they matched but both were wrong) | ✓ |

Works in window: Le Lézard @156, Moses @1308, Au Soleil @1462.

## Concatenated Title

`'Picasso, Miró, Dalí: UnboundThrough January 24, 2027'` was produced by the
`<p[^>]*>` regex matching a `<picture>` element on the listing page, spanning
from `<picture>` to the next `</p>` (which was inside a `<p class="info">` tag
containing "TitleThrough Date"). With the fixed regex this no longer occurs —
the listing page now only produces `'Picasso, Miró, Dalí: Unbound'`.

This string was stored as `best_match_title` but the exhibition name passed to
`prose_llm_extract_works` comes from the user's input (via `_exh_name_for_search`),
not from `best_match_title`. So it did not directly skew the LLM extraction, but
it would have affected any downstream logging or display that used
`result.exhibition_title`.

## Tests

- `tests/test_local373_live_extraction_gap.py` — 16 tests
  - `TestParagraphRegexPictureExclusion` (3): verifies `<picture>` not matched
  - `TestFetchPageDeduplication` (3): verifies dedup of paragraphs/alts/items
  - `TestFooterBoundaryDetection` (5): verifies boundary stops at address/©
  - `TestFixtureAndLiveAlignment` (5): integration with real fixture
- **Red on revert:** 8 of 16 fail (dedup + boundary tests)
- **Green on fix:** all 16 pass; 241 existing tests pass

## Acceptance Pending

- [ ] **Live run** — requires `OPENAI_API_KEY` (not available in this env).
      With the window now 2183 chars of clean content (was 5000 with 44% noise),
      the LLM should extract all three works. Run needed to capture stop headings.
- [ ] **Palais Lascaris** — `_fetch_page` returns 38419 chars for the venue;
      no footer boundary triggers (no English street address pattern). Unaffected.
- [ ] **Museum bounds** — no change to extraction logic or grounding; only the
      input text quality improved. Bounds unchanged.
