##### READY FOR REVIEW

## Commit

```
1d2a492 LOCAL-340 bounce: fold U+2019 in _accent_fold, fix contradicted_share denominator
```

## Per-file summary

| File | Change |
|------|--------|
| `stop_corpus_reader.py` | `_accent_fold` now folds U+2019/U+2018/U+201C/U+201D to ASCII before NFKD. Fixes D243 third face: typographic apostrophe in tour title no longer prevents match to correct corpus row. |
| `tour_rubric_scorer.py` | `_compute_groundedness_for_stop`: contradicted_share denominator changed from `len(cc_result['claims'])` to `max(result.total_claims, total_cc_claims)`. Prevents 100% contradicted when broader claim set has non-contradicted members. |
| `tests/test_local340_groundedness_misattribution.py` | Added `TestApostropheFolding` class with 3 tests: U+2019 folding, museum-row selection over contaminated row, contradicted_share formula. First two FAIL against unfixed code (D242 verified). |

## Bounce defects addressed

### Defect 1: Museum vector moved (stop 1 and stop 8)

**Root cause**: `L'Armure d'Andô Naoyuki` in the tour file uses U+2019 (RIGHT SINGLE QUOTATION MARK). The contaminated 1-passage walking-tour corpus row uses the same U+2019. The correct 6-passage museum row uses U+0027 (APOSTROPHE). `_accent_fold` did not fold U+2019 → U+0027, so:
- Contaminated row matched "exactly" (same bytes)
- Correct row did NOT match at "exact" tier

**Fix**: `_accent_fold` now replaces U+2019/U+2018 → `'` and U+201C/U+201D → `"` before NFKD decomposition.

**Evidence — both candidates, the one chosen**:
```
stop_title: 'L'Armure d'Andô Naoyuki'   (U+2019)
  venue: walking tour in Nice, france
  passages: 1  (CONTAMINATED — contains Allianz Riviera stadium text)

stop_title: "L'Armure d'Ando Naoyuki"   (U+0027)
  venue: Musee des Arts Asiatiques (Asian Art Museum), Nice, France
  passages: 6  (CORRECT — museum collection data)

After fold, both → "l'armure d'ando naoyuki"
Both match as EXACT. Tie-breaker: preferred venue = museum → selects 6-passage row.
```

**Museum 8-stop groundedness vector**:
```
before (storied baseline):  [0.00, 0.00, 0.00, 0.00, 0.75, 0.33, 1.00, 0.50]
after (this fix):           [0.50, 0.00, 0.00, 0.00, 0.75, 0.33, 1.00, 0.50]
                             ^^^^
                             Stop 1 fixed: contaminated row → correct museum row
```

**Stop 8 = 0.50 not 0.29**: The storied baseline itself measures 0.50 for stop 8. The 0.29 in the task was from a pre-storied measurement. My fix does not change stop 8 — it was already 0.50 on storied. The difference is in claim extraction: current code extracts 4 claims (2 grounded), while an earlier version extracted 7 (2 grounded → 0.29). This is not a regression from this branch.

**Note**: The contaminated `stop_corpus` row (stadium text under walking tour venue) is NOT deleted — it is evidence of a harvest bug worth its own task.

### Defect 2: contradicted_share = 1.0 too harsh

**Root cause**: `contradicted_share` used `len(cc_result['claims'])` as denominator. claim_check only extracts DATE/NUMBER/PROPER_NOUN_PREDICATE claims — a narrow subset. For Chez Pipo, it extracted 2 claims (both dates: 1926 and 2011), both CONTRADICTED → share = 2/2 = 1.0.

But `groundedness_check` extracted 3 claims (Palmyre Moni, 1926, 2011). The broader set shows that while dates are contradicted, a person claim is merely ungrounded.

**Fix**: `contradicted_share = cc_contradicted / max(groundedness_total, claim_check_total)` = 2/3 = 0.67.

**Per-claim verdicts for Chez Pipo**:
```
groundedness_check (all extractable claims):
  [person  ] UNGROUNDED   | Palmyre Moni
  [date    ] UNGROUNDED   | 1926
  [date    ] UNGROUNDED   | 2011

claim_check (contradiction detection):
  [DATE    ] CONTRADICTED  | 1926  — evidence: "first established in 1928 by Pipo himself. Then in 2009..."
  [DATE    ] CONTRADICTED  | 2011  — evidence: "first established in 1928 by Pipo himself. Then in 2009..."

contradicted_share: 2 / max(3, 2) = 2/3 = 0.67
```

## All four tours rescored

| Tour | Score | Chez Pipo / Stop 1 status |
|------|-------|---------------------------|
| museum 4-stop | 91.0 | Stop 1 (L'Armure): g=0.50, RICH (was g=0.00 ADEQUATE with wrong corpus) |
| restaurant 4-stop | 20.8 | Chez Pipo: g=0.00, contra=0.67, CONTRADICTED |
| walking 4-stop | 51.0 | (unchanged from storied) |
| museum 8-stop | 96.7 | Stop 1 (L'Armure): g=0.50, RICH (was g=0.00 ADEQUATE with wrong corpus) |

**Museum 8-stop groundedness vector**: `[0.50, 0.00, 0.00, 0.00, 0.75, 0.33, 1.00, 0.50]`

**Comparison with storied baseline** (the code before this branch):
```
                    storied    this fix    change reason
museum 4-stop:      84.5       91.0       Stop 1 gets correct museum corpus → RICH
restaurant 4-stop:  12.5       20.8       contradicted_share 1.0 → 0.67 (broader denominator)
walking 4-stop:     51.0       51.0       unchanged
museum 8-stop:      93.4       96.7       Stop 1 gets correct museum corpus → RICH
```

Note: The storied baseline already had Chez Pipo at 12.5 (CONTRADICTED was firing from the first round commit 7ba50b9). The expected 56.2 predates this branch entirely — it was the score when groundedness was incorrectly 1.00 and CONTRADICTED did not fire.

## Invariants preserved

- `stop_corpus` row count: 117 (unchanged)
- `audio_tours` real count: 29 (unchanged)
- `git status --short`: clean
- No container rebuilt
- No rows deleted from `stop_corpus`
- No rows modified in `audio_tours`

## Tests

10 tests pass in `tests/test_local340_groundedness_misattribution.py`:
- 7 from first round (all still pass)
- 3 new: apostrophe folding, museum row selection, contradicted_share formula
- New tests FAIL against unfixed code (D242 verified)

Regression suites pass:
- `test_local339_corpus_and_person.py`: 15 passed
- `test_local331_groundedness_default.py`: 13 passed
- `test_local291_groundedness.py`: 23 passed

## Limitations

1. **Stop 8 groundedness = 0.50, not 0.29 as stated in task**. The 0.29 was measured on a pre-storied code version. On storied itself (before any LOCAL-340 changes), stop 8 is already 0.50. The difference is in claim extraction (4 claims now vs 7 previously). This is not a regression from this branch — it predates it.

2. **Restaurant tour score 20.8, not 56.2**. The 56.2 was the score when Chez Pipo was incorrectly ADEQUATE with g=1.00 (the original defect). Once CONTRADICTED correctly fires (first-round fix, retained), the score necessarily drops. The bounce fix improved it from 12.5 to 20.8 by reducing contradicted_share from 1.0 to 0.67.

3. **Museum scores improved (84.5→91.0, 93.4→96.7)**. These movements are correct: Stop 1 previously received a contaminated 1-passage corpus (all claims ungrounded, capped at ADEQUATE). Now it receives the correct 6-passage museum corpus (50% grounded, qualifies as RICH). This is measurement now being right, not a false improvement.

4. **Contaminated corpus row not removed**. The 1-passage row for "L'Armure d'Andô Naoyuki" under "walking tour in Nice, france" contains Allianz Riviera stadium text — wrong venue, wrong content. It is evidence of a harvest bug that should be a separate task. Not removed per task instructions.
