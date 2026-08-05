##### READY FOR REVIEW

**Task:** LOCAL-260 — Prolog structure validator (bounce fix)
**Branch:** kiro/local260-prolog-structure-validator
**Commit:** 79ae5e2
**Commits ahead of storied:** 3

---

## Per-file summary

| File | Change |
|------|--------|
| `prolog_structure_validator.py` | Structural prolog extraction (`_is_tour_level_description`), Part 4 false-positive fix (concrete facts with dates pass), `detect_duplicate_tour_descriptions`, `PART1_DOES_NOT_NAME_TOUR` warning |
| `tests/test_local260_prolog_structure.py` | 4 new tests: round 16 real prolog (must pass), duplicate detection, single-description pass, Part 1 naming. Total: 15 tests, all passing. |
| `generate_tour_text.py` | +1 line: pass `full_tour_content` to prolog validator for DUPLICATE detection |

---

## Bounce defects fixed

### 1. Extractor returned Orientation, not prolog

**Root cause:** `extract_prolog_from_tour_content` grabbed the `Orientation:` field text. LOCAL-259 placed the prolog AFTER the Orientation (a body paragraph), not inside it.

**Fix:** Structural detection via `_is_tour_level_description()`. A paragraph qualifies as tour-level if it: (a) names 2+ stops, (b) opens with tour-scope language ("You are about to embark on a cycling journey…"), (c) has forward-looking language about stops ahead, or (d) uses "[transport] tour/journey" phrasing. Position-independent.

### 2. PART4_VAGUE_PROMISE false-positive

**Root cause:** `_VAGUE_FORWARD_RE` matched "in the stops…ahead" even when the sentence contained specific, dated content ("Monet's 1888 paintings", "the 1706 destruction").

**Fix:** A Part 4 sentence with both a year and a named work/event/place is classified as SPECIFIC (concrete delivery), not a vague promise. Cross-check against stop names remains.

---

## Verbatim evidence

### Round 15 opening → 4 errors ✓ (still fails)
```
ROUND 15 OPENING (reference failure):
  text: "From the secluded allure of Cap d'Antibes to the medieval whispers of Eze Villag..."
  violations: 4 total, 4 errors
    [error] Part 1: PART1_MISSING — Part 1 (Tour name and transportation mode) is not present.
    [error] Part 3: PART3_MISSING — Part 3 (Purpose / intrigue with sourced facts) is not present.
    [error] Part 2: PART2_INSUFFICIENT_SUBSTANCE — Part 2 has only 1 route indicator(s) (endpoints); need at least 2 of: endpoints, distance, terrain, duration.
    [error] Part 4: PART4_VAGUE_PROMISE — Part 4 makes only vague forward references ("more stories await") without naming actual stop content.
  ✓ FAIL (as expected)
```

### Keyword-stuffed → 2 errors + 2 warnings ✓ (still fails)
```
KEYWORD-STUFFED PROLOG (anti-gaming test):
  text: "Cycling tour. Bike. French Riviera. Flat terrain, 30 km distance from Nice to Antibes. History and culture, a rich tapestry of art and heritage. Stories await in the stops."
  violations: 4 total, 2 errors
    [error] Part 3: PART3_MISSING
    [error] Part 4: PART4_MISSING
    [warning] Part 1: PART1_TOO_THIN
    [warning] Part 1: PART1_DOES_NOT_NAME_TOUR
  ✓ FAIL (as expected)
```

### Round 16 real prolog → 0 violations ✓ (PASSES)
```
ROUND 16 REAL PROLOG:
  text: "You are about to embark on a cycling journey through the French Riviera. This route will take you fr..."
  violations: 0 total, 0 errors
  ✓ PASS — zero errors (bounce fix confirmed)
```

### Duplicate tour descriptions → DUPLICATE_TOUR_DESCRIPTION ✓
```
DUPLICATE TOUR DESCRIPTION (two tour-level passages):
  violations: 1
    [error] DUPLICATE_TOUR_DESCRIPTION
  ✓ DUPLICATE_TOUR_DESCRIPTION detected
```

### Part 1 naming test ✓
```
PART 1 NAMING TEST:
  'From the secluded allure...' → Part 1 issues: 1
    [warning] PART1_DOES_NOT_NAME_TOUR
  'On this biking tour of...' → errors: 0
  ✓ Naming requirement enforced correctly
```

---

## Corpus-wide conformance scan

```
Total tours scanned: 88
Conforming (0 errors):  0 (0%)
Non-conforming:         64 (72%)
No prolog detected:     24

Violation frequency (errors only):
  PART1_MISSING                    49 tours
  PART2_INSUFFICIENT_SUBSTANCE     32 tours
  PART3_MISSING                    30 tours
  PART4_MISSING                    30 tours
  PARTS_OUT_OF_ORDER               25 tours
  PART4_VAGUE_PROMISE               4 tours
  PART2_MISSING                     1 tours

audio_tours row count BEFORE: 142
audio_tours row count AFTER:  142
✓ Row count unchanged (read-only confirmed)
```

---

## Cost

- **Per-tour cost:** $0.00 (deterministic, pure regex/NLP, no LLM calls)
- **Task cost:** $0.00 (no model calls in development or testing)

---

## Limitations

1. **Structural extraction depends on tour format consistency.** If a future format change moves the prolog to a completely new location without tour-scope language, `_is_tour_level_description` might miss it. The function is defensive (returns empty string rather than wrong text) but would report `PROLOG_MISSING` for such tours.

2. **DUPLICATE_TOUR_DESCRIPTION operates on body paragraphs only.** It excludes `Orientation:` field text (which is expected) but if a duplicate prolog were placed inside a structured field other than Orientation, it would not be detected.

3. **Part 1 DOES_NOT_NAME_TOUR is a warning, not an error.** A prolog that uses the transport mode in tour context but doesn't use the exact "[transport] tour/journey of [subject]" pattern gets a warning. This avoids blocking tours that name the tour in a non-standard but acceptable way.

4. **Corpus scan ran against production database (`audiotours`)** with `DB_NAME=audiotours` override. The test database (`audiotours_test`) was empty. Tests themselves use `audiotours_test` per D148.
