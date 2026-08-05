##### READY FOR REVIEW

**Commit:** `4488d55`
**Branch:** `kiro/local265-prolog-extractor-current-layout`
**Base:** `storied` (merge-base `d325996`)

---

## Per-File Summary

| File | Change |
|------|--------|
| `prolog_structure_validator.py` | Rewrote `extract_prolog_from_tour_content` with three-strategy layout detection; added `_extract_tour_level_span`, `_is_sentence_tour_level`, `_is_directive_sentence`, `_is_stop_orientation_sentence`; tightened `_is_tour_level_description`; updated `detect_duplicate_tour_descriptions` |
| `tests/test_local265_prolog_extractor.py` | New test file with 7 boundary rows covering all three layouts |

---

## Verbatim Evidence

### Seven Boundary Rows (all with real output)

```
======================================================================
LOCAL-265: PROLOG EXTRACTOR — ALL THREE LAYOUTS + BOUNDARY ROWS
======================================================================

  ROW 1 — Round 16 (prolog after Orientation):
    extracted: "You are about to embark on a cycling journey through the French Riviera. This route will take you fr..."
    words: 113
    ✓ PASS

  ROW 2 — Round 17M (prolog inside Orientation):
    extracted: "You are about to embark on a cycling journey through the French Riviera. In 2012, Cap Ferrat was nam..."
    words: 99
    ✓ PASS

  ROW 3 — No tour-level description:
    extracted: (empty)
    ✓ PASS — correctly returns empty

  ROW 4 — Round 16 validation:
    violations: 0 total, 0 errors
    ✓ PASS — 0 errors

  ROW 5 — Round 15 opening (must FAIL):
    text: "From the secluded allure of Cap d'Antibes to the medieval whispers of Eze Villag..."
    violations: 4 total, 4 errors
      [error] Part 1: PART1_MISSING
      [error] Part 3: PART3_MISSING
      [error] Part 2: PART2_INSUFFICIENT_SUBSTANCE
      [error] Part 4: PART4_VAGUE_PROMISE
    ✓ FAIL (as expected)

  ROW 6 — Keyword-stuffed decoy (must FAIL):
    text: "Cycling tour. Bike. French Riviera. Flat terrain, 30 km distance from Nice to An..."
    violations: 4 total, 2 errors
      [error] Part 3: PART3_MISSING
      [error] Part 4: PART4_MISSING
      [warning] Part 1: PART1_TOO_THIN
      [warning] Part 1: PART1_DOES_NOT_NAME_TOUR
    ✓ FAIL (as expected)

  ROW 7 — Duplicate tour descriptions (must produce DUPLICATE):
    violations: 1
      [error] DUPLICATE_TOUR_DESCRIPTION
    ✓ DUPLICATE_TOUR_DESCRIPTION detected

======================================================================
RESULTS: 7 passed, 0 failed, 7 total
======================================================================
```

### Original LOCAL-260 Tests (backward compatibility)

```
======================================================================
RESULTS: 15 passed, 0 failed, 15 total
======================================================================
```

### Corpus-Wide Conformance Scan

```
  audio_tours row count BEFORE: 142
  Tours with content: 88

  Total tours scanned: 88
  Conforming (0 errors):  0 (0%)
  Non-conforming:         63 (71%)
  No prolog detected:     25

  audio_tours row count AFTER: 142
  ✓ Row count unchanged (142 == 142)

  LLM calls: 0
  Total cost: $0.00
```

### Git Status

```
$ git status --short
(empty — clean)

$ git rev-list --count storied..HEAD
1
```

---

## Limitations

1. **Corpus shows 0% conformance.** This is expected — the four-part prolog specification (LOCAL-259) was only enforced starting with round 16. All older tours in the DB were generated without it. The extractor is correct; the corpus simply predates the requirement.

2. **Round 17M prolog passes extraction but has Part 1/Part 2 validator findings.** The round 17M prolog ("In 2012, Cap Ferrat was named...") is thinner than round 16's prolog on route substance (no distance/terrain) and doesn't use the "cycling tour of" naming pattern. These are legitimate content-quality observations from the validator, not extraction errors.

3. **`_is_stop_orientation_sentence` uses keyword heuristics.** A very unusual stop orientation sentence without any sensory/positional vocabulary could potentially be included in the prolog span. In practice the directive sentence ("Start biking...") always appears first and catches the boundary.

4. **The `tours/` directory is gitignored.** Fixture files (`LOCAL259_riviera_2stop_round16.txt`, `LOCAL264b_riviera_2stop_round17M.txt`) exist on disk for manual testing but are not tracked. The test file embeds the data inline.

5. **No container rebuilt.** The fix is pure Python logic in `prolog_structure_validator.py` — no Docker/service changes.
