# SUBMISSION_LOCAL-378.md

## Status: Unproven, handing to LEAD

The fixes are structurally sound and all 38 unit tests pass. However, a live
generation run has not been completed in this session — the acceptance criteria
require a full `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`
generation with 8 stops, which requires API keys and the full service stack.

## Summary of Changes

### Defect 1 — Bare surname removal (prose_entity_grounding_gate.py)

**Problem:** The LOCAL-376 gate used `_PERSON_PATTERN` which only matches
multi-word capitalised names. It caught `Xavier Lalanne` once but missed the
dominant bare surname form `Lalanne's` (4 occurrences sailed through).

**Fix:** Once a person is judged ungrounded, `remove_person_from_text()` removes
ALL forms: full name, bare surname (`\bLalanne\b`), and possessive
(`\bLalanne's\b`) using whole-word regex matching. The surname is extracted from
the last capitalised word of the rejected full name.

### Defect 2 — 'The Treat Page' false positive (prose_entity_grounding_gate.py)

**Problem:** Any capitalised multi-word phrase was classified as a person.

**Fix:** `_looks_like_person_name()` heuristic:
- Rejects strings starting with non-name openers (The, This, That, etc.)
- Rejects strings in `_KNOWN_NON_PERSON_STRINGS` set (includes "The Treat Page")
- Requires at least one word that is NOT in a common-noun vocabulary
- Each significant word must start with a capital letter

### Defect 3 — Dangling fragments (prose_entity_grounding_gate.py)

**Problem:** Dropping a sentence mid-construction left a dangling participle or
conjunction fragment.

**Fix:** After initial sentence removal, a second pass runs `_is_fragment()` on
remaining sentences. Fragments (lowercase-starting, short conjunction-openers,
very short without punctuation) are also dropped.

### Defect 4 — Part A never reaches the prose (generate_tour_text.py)

**Problem:** `match_credit_line('Le Lézard aux plumes d\'or (The Lizard with
Golden Feathers)', works)` failed because the parenthetical translation inflated
the word count, diluting overlap below the 60% threshold (actual: 33%).

**Diagnosis confirmed:** The `[LOCAL-378]` diagnostic log was added. It prints
`stop='<title>' matched_work=<True/False> medium='<value>'
provenance_block_chars=<n>` for each stop.

**Fix:**
1. `_strip_parenthetical_translation()` — removes trailing `(...)` before
   comparison. Applied to both poi_name AND work titles for symmetric matching.
2. `match_work_for_stop()` — new function, same matching logic as
   `match_credit_line` but returns the full work dict (with medium, publisher,
   credit_line).
3. **MEDIUM CONSTRAINT** injected into the description prompt when the matched
   work has a `medium` field. The model can no longer hallucinate "sculpture"
   when the work is an illustrated book.

### Defect 5 — Gate scope limitation (documented, no code change)

The prose entity grounding gate is guarded by:
```python
if (tour_category == 'museum' and _exhibition_checklist_result
        and getattr(_exhibition_checklist_result, 'page_text', '')):
```

Unscoped museum tours (Palais Lascaris, etc.) remain ungated. This is
intentional — widening would require a different grounding corpus (the general
venue page) which is not yet available. Stated here so it is not mistaken for
coverage.

## Files Changed

| File | Change |
|------|--------|
| `prose_entity_grounding_gate.py` | NEW — gate module (Defects 1, 2, 3) |
| `generate_tour_text.py` | `_strip_parenthetical_translation()`, `match_work_for_stop()`, MEDIUM CONSTRAINT injection, gate wiring at PHASE 5.158 (Defect 4) |
| `tests/test_local378_prose_entity_grounding.py` | NEW — 38 tests |

## Tests (D294)

**Expected red-on-revert count: 26**

- Neutering `prose_entity_grounding_gate.py` body → **23 tests fail**
- Neutering `_strip_parenthetical_translation` body → **3 additional tests fail**

### Green run (all 38 pass):
```
tests/test_local378_prose_entity_grounding.py   38 passed in 0.22s
```

### Revert run (neutered `prose_entity_grounding_gate.py`):
```
23 failed, 15 passed in 0.17s
```

### Revert run (neutered `_strip_parenthetical_translation`):
```
3 failed, 5 passed in 0.29s
```

The revert breaks the **logic, not the symbol** (D296): function signatures and
imports remain intact; only the function body is neutered to `return` without
performing its logic.

## Acceptance Criteria — Not Yet Verified

The following require a live generation run (LEAD to execute):

- [ ] `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested
- [ ] `Rousseau`, `Corbusier`, `Lalanne`, `Matisse` → 0 each in delivered text
- [ ] Stop 1 names Miró; stop 2 names Dalí and Freud; stop 3 names Gris and Reverdy
- [ ] `book` or `illustrated book` appears (medium stated, not implied)
- [ ] `sculpture`, `painting`, `mural`, `ceiling`, `canopy`, `stand beneath`,
      `look up`, `Position yourself directly under` → 0
- [ ] `The Treat Page` present if closing includes it
- [ ] No dangling fragment where a sentence was dropped
- [ ] Palais Lascaris, Nice, France (4 stops) → still 4/4 real instruments
- [ ] `score_tour_file(f, 4)` = 81.2, `score_tour_file(f, 8)` = 75.0

## Env for LEAD run

```bash
DISABLE_TOUR_CACHE=1
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
STORIED_MODE=true
```
