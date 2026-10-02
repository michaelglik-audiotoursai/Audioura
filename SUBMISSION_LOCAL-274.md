##### READY FOR REVIEW

## LOCAL-274: Well-formedness check fires and decides

**Commit:** `548f2d5`
**Branch:** `kiro/local274-rewrite-wellformedness`
**Base:** `storied`

---

### Per-file summary

| File | Change |
|---|---|
| `style_validator_detector.py` | Rewrote `_r1_rewrite_wellformed` to implement all four checks (initial capital, mid-sentence capitals, finite verb, repeated clause). Fixed `_as_you_arrive_handler` to produce lowercase "the" after comma. Fixed `_take_in_handler` and `_look_for_handler` to not capitalise interior words when prepending "The". |
| `RIVIERA_2STOP_ROUND28.md` | Generated artifact: 2-stop Riviera cycling tour, all gates on. |
| `run_round28.py` | Generation script for round 28. |

---

### Verbatim evidence — five boundary rows

```
ROW 1:
  IN:  As you arrive at Cap d'Antibes, find yourself amidst the lush greenery of the promontory.
  OUT: From Cap d'Antibes, the lush greenery of the promontory is visible.
  (rewritten=1, deleted=0)

ROW 2:
  IN:  Take a moment to breathe in the salty sea air and listen to the gentle lapping of the waves.
  OUT: Take a moment to breathe in the salty sea air and listen to the gentle lapping of the waves.
  (rewritten=0, deleted=0)  ← fallback to original; wellformedness rejected lowercase start

ROW 3:
  IN:  As you arrive at Cap d'Antibes, take in the breathtaking views of the azure waters.
  OUT: From Cap d'Antibes, you can admire the breathtaking views of the azure waters.
  (rewritten=1, deleted=0)  ← no regression

ROW 4:
  IN:  Start cycling south on the main road, enjoy the sea breeze along the coast.
  OUT: Start cycling south on the main road, enjoy the sea breeze along the coast.
  (rewritten=0, deleted=0)  ← navigation exempt (D164)

ROW 5:
  IN:  Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera.
  OUT: Eze Village is a medieval gem perched high above the French Riviera.
  (rewritten=1, deleted=0)  ← no regression
```

### Wellformedness rejects old broken output

```
"From Cap d'Antibes, The lush greenery of the promontory is visible."  → Well-formed? False (mid-cap "The")
"breathe in the salty sea air and listen to the gentle lapping..."     → Well-formed? False (initial cap)
```

### Corpus-wide fallback rate

```
Corpus: 89 tours, 5567 sentences
R1 hits (imperative, non-nav): 1381 (24.8% of sentences)
  Deterministic rewrites attempted: 234
  Well-formedness FALLBACKS: 35 (15.0% of rewrites)
    Breakdown: initial_cap=20, finite_verb=13, mid_cap=2, repeated_clause=0, reflexive=0
  Fallback fires on 35 of 1381 R1 hits = 2.5% of all R1 hits
  (Below the 50% threshold — rewrite rules are not too narrow)
```

### Prior boundary sets — all pass

```
310 tests passed (0 failed):
  tests/test_local271_r1_damage_and_exhortation.py  — 76 passed (LOCAL-271 four exhortation rows + LOCAL-263 ten + LOCAL-269 eight + LOCAL-249 nine + LOCAL-251 ten + LOCAL-255 eight)
  tests/test_local256_fragment_and_label.py         — 28 passed (LOCAL-256 twenty-eight rows)
  tests/test_local257_fragment_checker.py           — 42 passed
  tests/test_r1_rewrite.py                          — 14 passed (LOCAL-255 eight rows)
  tests/test_local263_unsupported_claim_gate.py     — 48 passed (LOCAL-263 ten rows)
  tests/test_local269_unglossed_reference_gate.py   — 42 passed (LOCAL-269 eight rows)
  tests/test_local253_directions_mode_guard.py      — 14 passed (LOCAL-253 seven rows)
  tests/test_r9_generic_deletion.py                 — 16 passed (LOCAL-249 nine rows)
  tests/test_r10_unfulfilled_promise.py             — 30 passed (LOCAL-251 ten rows)
```

### RIVIERA_2STOP_ROUND28.md generation

```
Cost:       $0.0174 (vs prior $0.0206 / 43s; ceiling $0.60)
Time:       46s
Tokens:     14677
Stops:      Cap d'Antibes, Eze Village
R1:         2 rewritten, 0 deleted, 4 residual
R7:         0 residual
Fragments:  1 (sensor description — pre-existing generation artifact)
Word count: 462
```

Plain text copied to `/Users/micha/Audioura/tours/LOCAL274_riviera_2stop_round28.txt`.

### R1 rewrites performed in this tour

| Before | After | Check |
|---|---|---|
| (imperative in orientation) | Rewritten | wellformedness passed |
| (imperative in orientation) | Rewritten | wellformedness passed |

### D141 cleanup

- Inserted row id=266 with `is_test=true`
- Confirmed via `SELECT is_test FROM audio_tours WHERE id = 266` → `True`
- Deleted after measurements
- audio_tours before: 143, after: 143
- Nice list verified: `[1, 12, 14, 17, 24, 29, 152]` unchanged

---

### Limitations

1. **R1 residual is 4/18 in this tour** — these are imperatives that didn't match any deterministic rule and had no LLM key available. The wellformedness check only applies to attempted rewrites; sentences that return `__LLM_NEEDED__` and have no API key fall through unchanged.

2. **One fragment sentence survives** in the generated tour ("The sensory delights of this stop include...") — this is not an R1 rewrite product but a pre-existing generation artifact where `_has_finite_main_verb` returns True because "include" is detected as a finite verb. The fragment is arguably a complete sentence (subject + verb).

3. **Eze Village paragraph has corpus injection noise** (duplicated phrases like "The area surrounding Èze was first populated around 200 BC as a commune situated..") — this is a pre-existing issue in the generation pipeline's corpus injection phase, outside the scope of the style validator.

4. **The 20 initial_cap fallbacks** in the corpus-wide measurement come from the `_take_a_moment_handler` returning `rest` directly when no content verb is matched (e.g. "breathe in the salty sea air"). The handler could be enhanced to capitalize or restructure, but this is new work beyond the task scope — the safety net catches them correctly.
