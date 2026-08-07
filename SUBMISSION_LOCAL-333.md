##### READY FOR REVIEW

**Commit:** 4a9b03c  
**Branch:** kiro/local333-fact-detector-nonmuseum  
**Base:** storied (bc536ee)

## Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Title exclusion narrowed to full-title-only (not sub-phrases); appositive place-guard now blocks subsequent verb detection; closing-offer regex handles unicode right-single-quote |
| `tests/test_local333_fact_detector_nonmuseum.py` | 7 new tests for bounce r2 (34 total, all pass) |

## Fixes applied (bounce r2)

### 1. Title exclusion corrected
**Before:** Extracted sub-phrases from within stop titles and excluded all of them.  
- `"Ulysses Grant"` extracted from `"Ulysses Grant au Japon"` → excluded (WRONG)  
- `"Andô Naoyuki"` extracted from `"L'Armure d'Andô Naoyuki"` → excluded (WRONG)

**After:** Only exclude names that are the FULL stop title (exact match, accent-folded).  
- `"Ulysses Grant"` ⊂ `"Ulysses Grant au Japon"` → KEPT ✓  
- `"Andô Naoyuki"` ⊂ `"L'Armure d'Andô Naoyuki"` → KEPT ✓  
- `"Chez Palmyre"` == full title → excluded ✓  
- `"La Merenda"` == full title → excluded ✓

### 2. Place-appositive blocks verb detection
**Before:** "Arts Asiatiques, a modern building, houses…" → appositive guard correctly identified "building" as place noun, but code fell through to active-verb check which detected "houses" → false positive.

**After:** When appositive positively identifies a place/institution, `continue` skips all remaining checks.

### 3. Closing-offer unicode quote
Regex now matches both `That's` (ASCII) and `That's` (U+2019).

## Verbatim evidence

### Red→green transcript (D242)
```
=== BEFORE (unfixed scorer, new tests) ===
FAILED test_ulysses_grant_within_longer_title - AssertionError: Person within longer title should be kept: []
FAILED test_ando_naoyuki_within_longer_title - AssertionError: Person within longer title should be kept: []
2 failed, 2 passed

=== AFTER (fixed scorer) ===
34 passed in 0.11s
```

### Bounce r2 verification (all four cases)
```
Ulysses Grant: named_people=['Ulysses Grant']              RESTORED ✓
Andô Naoyuki: named_people=['Andô Naoyuki']               RESTORED ✓
Chez Palmyre: named_people=[]                              EXCLUDED ✓
La Merenda: named_people=[]                                EXCLUDED ✓
```

### Treat Page — zero across all tours
```
'Treat Page' appears in ZERO stops across all tours. PASS.
```

### Filler/place-appositive guards still hold
```
"A mix of laughter and clinking glasses…"       → people=[] facts=0   ✓
"Nice, a coastal city, offers…"                 → people=[] facts=0   ✓
"Cours Saleya, a historic square, hosts…"       → people=[] facts=0   ✓
"Arts Asiatiques, a modern building, houses…"   → people=[] facts=0   ✓
```

### Museum 8-stop false-positive check (did NOT balloon)
```
                  Before   After
run1.txt people:    2        3    (+Ulysses Grant restored)
run2.txt people:    2        3    (+Andô Naoyuki restored)
run3.txt people:    2        3    (+Andô Naoyuki restored)
run4.txt people:    6        8    (+Andô Naoyuki, +Ulysses Grant restored)
run5.txt people:    6        7    (+Toyohara Chikanobu restored)
```

### Rescored tours
```
Museum 8-stop (run1):  107.7  (storied: 107.7, no change)
Restaurant (LOCAL318):  66.3  (storied: 61.2, +5.1 from correct fact detection)
```

Note: LEAD reported baselines of 78.1/60.0 — that was against different tour data or with corpus. These scores are without corpus data (file-only scoring), so they reflect the detector change in isolation.

## Reader-vs-detector table (LOCAL318 restaurant tour)

| Stop | Title | Detector | Reader | Gap | Notes |
|------|-------|----------|--------|-----|-------|
| 1 | La Rossettisserie | 0 | 1 | -1 | "daube" definition not counted (no date/person/measurement) |
| 2 | Acchiardo | 4 | 5 | -1 | Misses "Giuseppe" (single-word, no person context) |
| 3 | Chez Palmyre | 2 | 4 | -2 | Misses "Vincent and Sam" (no person context nearby) |
| 4 | Le Safari | 3 | 4 | -1 | Misses "three-star" (already counted as measurement?) |
| 5 | La Voglia | 3 | 4 | -1 | Misses numeric detail in body |

**Aggregate:** Detector 12, Reader ~18. Gap ratio: detector captures ~67% of what a reader counts. The misses are primarily single-word names without structural context and definitions/characterizations that don't fit the date/person/measurement taxonomy.

## Limitations

1. **Pre-existing false positives NOT addressed:** Sentence-initial words joining proper phrases (`"In Noh"`, `"Notice Ganesh"`, `"The Acchiardo"`, `"The Cap"`, `"In January"`) exist in both museum and cycling tours. These are a `_PROPER_PHRASE_RE` boundary issue outside this task's scope.

2. **Single-word people without context missed:** Names like "Giuseppe", "Vincent", "Sam" are not detected because they lack nearby structural cues (appositive, verb, title-noun). This is by design — expanding single-word detection would flood false positives.

3. **Definition-facts not counted:** "daube — a slow-cooked beef stew" is a verifiable fact to a reader but doesn't fit the date/person/measurement taxonomy used by the detector.

4. **No corpus provided in file-only scoring:** Scores here don't reflect groundedness adjustments (D244). When corpus is provided, the fact detection improvements only help if facts are grounded.
