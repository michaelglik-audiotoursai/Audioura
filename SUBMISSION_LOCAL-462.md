# SUBMISSION_LOCAL-462.md — Request_to_AI and Structure_AI_output

**Branch:** LOCAL-462-request-and-structure  
**Base:** storied (29cbff9)  
**Date:** 2026-08-13

## Files

- `request_and_structure.py` — implementation of both routines
- `test_local462_request_and_structure.py` — 16 acceptance tests (all faked, no network)

## Design Decisions

### Routine 1 — `request_to_ai`

1. **Sentence assembly**: Each part of Michael's template is a conditional segment.
   ABSENT slots produce empty strings, which are simply not appended. There is no
   post-hoc cleanup of "and None" — dangling connectors never enter the string.

2. **Deduplication**: `english_title` is only appended if it differs from
   `canonical_title` (string equality check).

3. **Unverified terms**: Every slot with `status == 'CLAIMED'` has its value
   collected into `unverified_terms`. This is D427/D435: The Hogarth Press is
   CLAIMED and FALSE, but it still goes in the question because we are asking,
   not asserting.

### Routine 2 — `structure_ai_output`

1. **Sentence counting**: Uses `story_opportunity_scan.split_sentences` for
   consistency with the handle-measurement pipeline.

2. **Summarization (>5 sentences)**: Sends exactly the prompt Michael specified:
   `"Summarize the following into 3 sentences: " + answer`.

3. **Substitution (<3 sentences)**: Gets the full ordered candidate list from
   `_credit_line_candidates` (FLAT → MENTIONED → DANGLING, never DEVELOPED),
   advances a cursor past the current credit_line, and feeds the next one into a
   rebuilt matrix → rebuilt request → re-ask cycle.

4. **`ask` injection**: The callable signature is `(prompt: str) -> str`. Tests
   supply a lambda/closure. No API key, no network, ever.

5. **Exhaustion**: When retries or candidates are exhausted, returns
   `status='INSUFFICIENT'` with the full chain. Does not raise.

### Credit-Line Candidate List

`_credit_line_candidates` replicates the same filtering logic as
`interrogation_matrix._pick_credit_line` but returns ALL qualifying handles in
order rather than just the first. This is the "ordered list and a cursor into it"
the task requires. The first element is always the same handle `_pick_credit_line`
would choose.

## Acceptance Evidence

### 1. MFA stop 2 request shape

```
What story can be told to visitors of Picasso, Miro, Dali: Unbound + Museum of Fine Arts, Boston : regarding Moses and Monotheism about Sigmund Freud in connection with Salvador Dalí and The Hogarth Press?
  unverified: ['Salvador Dalí', 'The Hogarth Press']
  omitted:    ['printed_by']
```

✓ Exhibition as medium, museum as venue, Moses and Monotheism present.  
✓ The Hogarth Press listed in `unverified_terms`.

### 2. All nine requests (walking tour reads grammatically with printed_by ABSENT)

```
TOUR_MFA_20260812_2030.txt (museum_exhibition)
Stop 1: What story can be told to visitors of Picasso, Miro, Dali: Unbound + Museum of Fine Arts, Boston : regarding Le Lézard aux plumes d'or or The Lizard with Golden Feathers about book in connection with Joan Miró and Louis Broder and Mourlot Frères?
Stop 2: What story can be told to visitors of Picasso, Miro, Dali: Unbound + Museum of Fine Arts, Boston : regarding Moses and Monotheism about Sigmund Freud in connection with Salvador Dalí and The Hogarth Press?
Stop 3: What story can be told to visitors of Picasso, Miro, Dali: Unbound + MFA, Boston, MA : regarding Au Soleil du Plafond about Pierre Reverdy in connection with Juan Gris and Tériade?

fruitlands_museum_tour.txt (museum)
Stop 1: What story can be told to visitors : regarding The Hudson River from Fort Putnam by Thomas Cole, 1846 about Hudson River School in connection with Thomas Cole?
Stop 2: What story can be told to visitors : regarding The Brothers by John Appleton Brown, 1883 in connection with John Appleton Brown?
Stop 3: What story can be told to visitors : regarding The Print Room" featuring works by Currier & Ives about James Merritt Ives in connection with Nathaniel Currier?

Beacon_Hill__Boston_walking_tour_20260714_135649.txt (walking)
Stop 1: What story can be told to visitors of Beacon Hill, Boston : regarding Massachusetts State House about Golden Dome in connection with Charles Bulfinch?
Stop 2: What story can be told to visitors of Beacon Hill, Boston : regarding Cheers Beacon Hill about Show Location in connection with Van Bergen?
Stop 3: What story can be told to visitors of Beacon Hill, Boston : regarding Louisburg Square about Elegant Townhouses in connection with Charles Bulfinch?
```

✓ All walking-tour requests read as grammatical English with `printed_by` and `publisher` ABSENT.
✓ No "and None", no "and —", no dangling "and".

### 3. Fake-based structure tests

**Summarize path** (`test_structure_summarize_when_too_long`):
- Fake returns 8 sentences → routine issues `"Summarize the following into 3 sentences: ..."` → returns 3 sentences.

**Retry path** (`test_structure_retry_when_too_short`):
- Fake initially returns 1 sentence → routine substitutes credit_line from `Sigmund Freud` to the next candidate, rebuilds request, asks again → chain shows `['Sigmund Freud', 'illustrations']`.

Both proven with fakes, no network.

### 4. Retry exhaustion

`test_structure_exhaustion_returns_insufficient`: After max_retries with perpetually-short
answers, returns `{'status': 'INSUFFICIENT', ...}` and does not raise.

## Test Output — Neutralized (FAILING)

```
12 failed, 4 passed in 0.33s

FAILED test_mfa_stop2_request_contains_exhibition_as_medium
FAILED test_mfa_stop2_request_contains_museum_as_venue
FAILED test_mfa_stop2_request_contains_moses_and_monotheism
FAILED test_mfa_stop2_hogarth_press_in_unverified
FAILED test_mfa_stop2_no_english_title_duplication
FAILED test_all_nine_requests_are_grammatical
FAILED test_structure_summarize_when_too_long
FAILED test_structure_retry_when_too_short
FAILED test_structure_retry_chain_shows_substitution
FAILED test_structure_exhaustion_returns_insufficient
FAILED test_structure_exhaustion_no_candidates_returns_insufficient
FAILED test_structure_accepts_3_to_5_sentences
```

## Test Output — Restored (PASSING)

```
16 passed in 0.46s

PASSED test_mfa_stop2_request_contains_exhibition_as_medium
PASSED test_mfa_stop2_request_contains_museum_as_venue
PASSED test_mfa_stop2_request_contains_moses_and_monotheism
PASSED test_mfa_stop2_hogarth_press_in_unverified
PASSED test_mfa_stop2_no_english_title_duplication
PASSED test_beacon_hill_stop1_no_dangling_and
PASSED test_beacon_hill_printed_by_absent
PASSED test_all_nine_requests_are_grammatical
PASSED test_structure_summarize_when_too_long
PASSED test_structure_retry_when_too_short
PASSED test_structure_retry_chain_shows_substitution
PASSED test_structure_exhaustion_returns_insufficient
PASSED test_structure_exhaustion_no_candidates_returns_insufficient
PASSED test_structure_accepts_3_to_5_sentences
PASSED test_request_is_deterministic
PASSED test_credit_line_candidates_ordered
```

## Regression

LOCAL-461 test suite: 21 passed, 0 failed (no regressions).
