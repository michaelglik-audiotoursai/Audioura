##### READY FOR REVIEW

## Commit

- Hash: `54280e1`
- Branch: `kiro/local260-prolog-structure-validator`
- Count from storied: 1

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `prolog_structure_validator.py` | NEW | Four-part prolog structure validator — deterministic, zero-cost |
| `tests/test_local260_prolog_structure.py` | NEW | 11 boundary tests including all required rows |
| `tests/test_local260_corpus_scan.py` | NEW | Corpus-wide conformance scanner |
| `generate_tour_text.py` | MODIFIED | Wired validation at post-assembly (after LOCAL-256 gate) |

## Evidence

### All boundary rows with real output

```
======================================================================
LOCAL-260: PROLOG STRUCTURE VALIDATOR — BOUNDARY TESTS
======================================================================

  CONFORMING PROLOG:
    violations: 0 total, 0 errors
    ✓ PASS — zero errors

  ROUND 15 OPENING (reference failure):
    text: "From the secluded allure of Cap d'Antibes to the medieval whispers of Eze Villag..."
    violations: 4 total, 4 errors
      [ERROR] Part 1: PART1_MISSING — Part 1 (Tour name and transportation mode) is not present.
      [ERROR] Part 3: PART3_MISSING — Part 3 (Purpose / intrigue with sourced facts) is not present.
      [ERROR] Part 2: PART2_INSUFFICIENT_SUBSTANCE — Part 2 has only 1 route indicator(s) (endpoints); need at least 2 of: endpoints, distance, terrain, duration.
      [ERROR] Part 4: PART4_VAGUE_PROMISE — Part 4 makes only vague forward references ("more stories await") without naming actual stop content.
    ✓ FAIL (as expected) — validator correctly rejects Round 15

  SWAPPED PARTS (3 before 1):
    violations: 1 total, 1 errors
      [ERROR] Part 3: PARTS_OUT_OF_ORDER — Part 3 appears before Part 2 (sentence 1 vs 2).
    ✓ FAIL (as expected) — ordering violation detected

  VAGUE PART 4 ('More stories await'):
    violations: 1 total, 1 errors
      [ERROR] Part 4: PART4_VAGUE_PROMISE — Part 4 makes only vague forward references ("more stories await") without naming actual stop content.
    ✓ FAIL (as expected) — vague Part 4 detected

  KEYWORD-STUFFED PROLOG (anti-gaming test):
    text: "Cycling tour. Bike. French Riviera. Flat terrain, 30 km distance from Nice to Antibes. History and culture, a rich tapestry of art and heritage. Stories await in the stops."
    violations: 3 total, 2 errors
      [ERROR] Part 3: PART3_MISSING — Part 3 (Purpose / intrigue with sourced facts) is not present.
      [ERROR] Part 4: PART4_MISSING — Part 4 (Forward connection to stops) is not present.
      [WARNING] Part 1: PART1_TOO_THIN — Part 1 sentences are too brief to name the tour subject substantively.
    ✓ FAIL (as expected) — keyword stuffing detected

  EMPTY PROLOG: ✓ PROLOG_MISSING raised

  SPECIFIC PART 4 ('Monet's 1888 series at Antibes, and the ...'):
    Part 4 errors: 0
    ✓ PASS — specific Part 4 accepted

  TRANSPORT DETECTION:
    ✓ Bare 'Bike.' → rejected
    ✓ 'Cycling is fun.' → rejected
    ✓ 'cycling journey through...' → accepted
    ✓ 'biking route along...' → accepted

  ROUTE SUBSTANCE DETECTION:
    'flat and coastal' → ['terrain'] (insufficient)
    '30-km flat terrain from Nice to Antibes' → ['endpoints', 'distance', 'terrain'] (sufficient)
    ✓ Threshold enforced correctly

  SOURCED FACT DETECTION:
    ✓ 'rich tapestry of history' → rejected
    ✓ 'layer of history and culture' → rejected
    ✓ 'built in 1260' → accepted
    ✓ 'Monet painted...1888' → accepted
    ✓ 'siege of the fortress' → accepted

  EXTRACTION FROM TOUR CONTENT:
    prolog: "You are about to embark on a cycling journey. This is a biki..."
    stops: ["Cap d'Antibes", 'Eze Village']
    mode: bike
    ✓ All extraction functions work

======================================================================
RESULTS: 11 passed, 0 failed, 11 total
======================================================================
```

### Corpus-wide conformance

```
  Total tours scanned: 88
  Conforming (0 errors):  0 (0%)
  Non-conforming:         64 (72%)
  No prolog detected:     24

VIOLATION FREQUENCY (errors only):
  PART3_MISSING                    63 tours
  PART4_MISSING                    60 tours
  PART1_MISSING                    52 tours
  PART2_INSUFFICIENT_SUBSTANCE     32 tours
  PART2_MISSING                    16 tours
  PARTS_OUT_OF_ORDER                8 tours

  audio_tours row count: 142 → 142 (unchanged)
```

### Cost report

```
  LLM calls: 0
  Total cost: $0.00
  This check is DETERMINISTIC AND FREE — pure regex/NLP, no model calls.
```

### Pipeline wiring proof

```
  [LOCAL-260] PROLOG STRUCTURE VALIDATION: ✓ all four parts present and conforming
```

(Output when a conforming four-part prolog is validated at post-assembly.)

## Acceptance Criteria Check

| Criterion | Status |
|-----------|--------|
| `validate_prolog_structure` implemented and wired at post-assembly | ✓ |
| All boundary rows run with real output; round 15's opening fails | ✓ (4 errors) |
| Keyword-stuffing test included and failing as intended | ✓ (PART3_MISSING + PART4_MISSING) |
| Corpus-wide conformance count reported | ✓ (0/88 = 0%) |
| Deterministic and free | ✓ (0 LLM calls, $0.00) |
| `git status --short` clean | ✓ |
| No container rebuilt | ✓ |

## Limitations

1. **Prolog extraction from existing tours is heuristic.** The prolog is injected into
   Stop 1's Orientation field, but older tours have varying formats. The extractor
   handles the standard format; non-standard layouts may be classified as NO_PROLOG.

2. **Part 4 stop-name matching requires forward-looking language.** A sentence that
   incidentally mentions a stop name without forward context (e.g., "from Nice to
   Antibes" as route info) is correctly NOT classified as Part 4. This is by design
   (anti-gaming), but means a Part 4 that uses unusual phrasing might be missed.

3. **Part 3 fact detection is conservative.** A sentence needs a year, named-person-
   with-action, or documented-event keyword to qualify. Novel facts expressed in
   unusual prose may not be detected, producing a false PART3_MISSING.

4. **LOCAL-259 has not landed.** The four-part prolog generation is being built in
   parallel (LOCAL-259 owns generation, LOCAL-260 owns validation). The validator
   is built against the specification and verified with synthetic conforming examples.
   When LOCAL-259 lands, the corpus conformance should rise from 0%.

5. **Museum tours and non-English tours.** Many tours (24/88) have no extractable
   prolog — these are museum tours or translated tours where the format differs.
   The validator reports NO_PROLOG rather than false positives.
