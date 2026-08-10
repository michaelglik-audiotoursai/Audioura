# SUBMISSION_LOCAL-372.md

## Summary

LOCAL-372 fixes three problems that prevented the MFA "Picasso, Miró, Dalí: Unbound"
exhibition from generating a tour after LOCAL-370's retrieval fixes opened this path.

---

## Problem 1: Theme-word filter matched substrings

**Root cause:** `tw in _work_lower` is plain containment. Short theme words mined at
runtime (e.g. `'or'`) matched inside `"d'or"`, dropping the only verified work.

**Fix:** Replaced with `theme_word_match()` (lifted to module scope) which uses
whitespace/punctuation boundaries that respect apostrophe-joined words (d'or, l'art).

**Diagnostic:** Every DROP now logs the matching theme word:
```
  [D1v2] DROPPED 'The Golden Age' — theme/book word 'golden', not a work title
```

**Scope-aware exemption:** When the exhibition is about books/prints/illustrated
volumes (detected via keywords in the requirements string — `unbound`, `livre`,
`book`, `print`, `lithograph`, etc.), theme-word drops are suppressed entirely:
```
  [D1v2] EXEMPT 'Le Lézard...' — theme word 'or' matched but exhibition is book/print-scoped (LOCAL-372)
```

The MFA exhibition triggers this via `"Unbound"` in its name.

**Matched theme word from the failure:**  
The original DROP was caused by a short theme word (likely `'or'` or similar ≤3-char
word mined from canonical titles) matching inside the French `"d'or"`. The runtime
`theme_words` set is ephemeral (mined per-request), so the exact word cannot be
recovered from the cached record — but with the new diagnostic logging, every future
drop will be fully explained.

---

## Problem 2: prose_llm_extract_works saw only 1 work (should be 3)

**Root cause:** `_fetch_page` assembles text from headings + figcaptions + img_alts +
paragraphs + list_items. The fixture has **155 list items**, mostly navigation garbage
(`"Log In"`, `"View Cart"`, `"Get Tickets"`, etc.). These pushed real exhibition
content past the 5000-char truncation window in `prose_llm_extract_works`.

**Fix:** Added `_filter_nav_from_page_text()` which strips lines matching known
navigation patterns before truncation. Result on fixture:

| Metric | Before | After |
|--------|--------|-------|
| `len(page_text)` (raw) | 6572 chars | 6572 chars |
| After nav filter | — | 5088 chars |
| `text_for_llm` (to LLM) | 5000 chars (truncated, ends in nav) | 5000 chars (ends in real content) |

All 3 works are now within the 5000-char window:
- `Joan Miró, Le Lézard aux plumes d'or` — position ~385
- `Dalí...Moses and Monotheism` — position ~1883  
- `Juan Gris...Au Soleil du Plafond` — position ~2048

---

## Problem 3: Exhibition-sourced stops bypass D1v2

**Decision:** Exhibition-extracted works (from `checklist`, `partial`, or `prose_llm`
paths) are already grounded by the venue's own exhibition page. Verifying them against
SPARQL/Wikidata would reject exhibition-specific works not in the permanent collection
catalogue. This is exactly wrong for temporary exhibitions.

**Implementation:** When `_deterministic_fill_used` and `_exhibition_stops_source` is
one of `('checklist', 'partial', 'prose_llm')`, the D1v2 block is skipped entirely:
```
  [D1/LOCAL-372] SKIP D1v2 — stops sourced from exhibition prose_llm
                  (already grounded by venue page, 3 works)
```

**Behavior for 1-work exhibitions:** A tour is generated with however many honest
stops were found. `clean fail` is reserved for finding nothing. This matches D275
("three honest stops beat eight invented ones, and one honest stop beats a clean fail").

---

## Red/Green Evidence

### theme_word_match (word boundary)

**RED (old behavior — substring containment):**
```python
# Old: 'or' in "le lézard aux plumes d'or..." → True (WRONG)
old_theme_word_check("le lézard aux plumes d'or (the lizard with golden feathers)", {'or'})
# Returns: 'or'
```

**GREEN (new behavior — word boundary):**
```python
# New: theme_word_match respects apostrophe-joined words
theme_word_match("le lézard aux plumes d'or (the lizard with golden feathers)", {'or'})
# Returns: '' (no match — 'or' is part of "d'or", not a standalone word)
```

### _is_book_exhibition_scope

**RED:** Function returns False for non-book exhibitions:
```python
_is_book_exhibition_scope({'requirements': 'Impressionism and the Sea'})
# Returns: False
```

**GREEN:** Function returns True for the MFA exhibition:
```python
_is_book_exhibition_scope({'requirements': 'Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA'})
# Returns: True (matches keyword 'unbound')
```

### _filter_nav_from_page_text

**RED:** Without filter, truncation at 5000 chars ends in navigation:
```
...Corporate Membership\nGifts of Art\nGifts of Securities\nDonor-Advised Funds\nGet Tickets\nJoin Today\nLog In...
```

**GREEN:** With filter, truncation at 5000 chars ends in actual content, all 3 works visible.

---

## Live Run Evidence

⚠️ **OPENAI_API_KEY not available in this environment.** Live generation requires
the API key for the prose_llm extraction step and the tour text generation step.

The fixture-based verification confirms:
1. All 3 works' content is within the LLM's input window after nav filtering
2. The theme-word filter no longer drops `Le Lézard aux plumes d'or`
3. Exhibition-sourced stops bypass D1v2 verification

A live run with `OPENAI_API_KEY` set will produce a tour with stops from the MFA's
exhibition page. The stop headings will be the titles extracted by the LLM from the
page content (expected: Le Lézard aux plumes d'or, Moses and Monotheism illustrations,
Au Soleil du Plafond).

---

## Test Results

```
tests/test_local372_book_word_drop.py — 25 passed
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds — 2 passed
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty — 2 passed
```

Museum bounds (75.0/81.2) unchanged — the exhibition-scope bypass only activates
when stops come from the exhibition checklist, not for venue-wide tours.

---

## Files Changed

- `generate_tour_text.py`: 
  - `theme_word_match()` — word-boundary theme-word check (module scope)
  - `_is_book_exhibition_scope()` — book/print exhibition detection (module scope)
  - `_verify_works_v2()` — added `exhibition_scope` parameter, uses new helpers
  - D1v2 caller — passes `exhibition_scope`, skips verification for exhibition-sourced stops
  - Loud warning when all candidates are dropped

- `exhibition_checklist.py`:
  - `_filter_nav_from_page_text()` — strips navigation lines (module scope)
  - `prose_llm_extract_works()` — uses nav filter before truncation, logs page_text length

- `tests/test_local372_book_word_drop.py`: 25 tests for the three lifted helpers
