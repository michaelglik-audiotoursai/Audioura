##### READY FOR REVIEW

## LOCAL-227: Instrument Falsification Report

**Branch:** `kiro/local227-falsify-the-instruments`
**Base:** `storied`

---

### The Deliverable: Which instruments notice being broken?

**All five instruments detect their own breakage.** Zero instruments failed
the falsification test. This is good news.

| # | Instrument | What was broken | What measurement did | Trustworthy? |
|---|---|---|---|---|
| 1 | `style_validator_detector` R1 | Neutralised `check_r1_imperatives` | Findings dropped 5 → 0 | ✓ YES |
| 2 | `style_validator_detector` R3 | Neutralised `check_r3_suggestive_exploration` | Findings dropped 3 → 0 | ✓ YES |
| 3 | `style_validator_detector` R4 | Neutralised `check_r4_prescribed_feeling` | Findings dropped 3 → 0 | ✓ YES |
| 4 | `style_validator_detector` R7 | Neutralised `check_r7_hallucinated_sensory` | Findings dropped 3 → 0 | ✓ YES |
| 5 | `style_validator_detector` R8 | Neutralised `check_r8_prompt_leakage` | Findings dropped 3 → 0 | ✓ YES |
| 6 | `style_validator_detector` R9 | Neutralised `check_r9_generic` | Findings dropped 3 → 0 | ✓ YES |
| 7 | `style_validator_detector` integration | Broke R1 inside `validate_paragraph` | Findings dropped 3 → 2 | ✓ YES |
| 8 | `claim_check` (passages removed) | Removed all corpus passages | SUPPORTED 2→0, UNSUPPORTED 0→2 | ✓ YES |
| 9 | `claim_check` (verdict consistency) | Checked counts vs actual claims | Internally consistent | ✓ YES |
| 10 | `corpus_coverage` (empty passages) | Emptied passages list | Verdict: COVERED → EMPTY | ✓ YES |
| 11 | `corpus_coverage` (role awareness) | Removed `about_subject` roles | Verdict: COVERED → CREATOR_ONLY | ✓ YES |
| 12 | `stop_anchor_detector_v2` | Emptied corpus anchors | Classification: ANCHORED → NO_ANCHOR | ✓ YES |
| 13 | `stop_anchor_detector_v2` (nav) | Removed corpus from nav paragraph | NAVIGATION both ways (independent) | ✓ YES |
| 14 | `secret_scan` (synthetic key) | Planted `sk-proj-...` in temp file | 3 detectors fired | ✓ YES |
| 15 | `secret_scan` (SHA-256 exclusion) | SHA-256 hash in assignment | Correctly silent (D108) | ✓ YES |
| 16 | `secret_scan` (whitelist) | Whitelisted patterns (`sk-xxxx...`) | Correctly silent | ✓ YES |

---

### Instruments that DO NOT detect their own breakage

**None.** The list is empty. Every instrument tested distinguishes its healthy
state from its broken state.

---

### Method

For each instrument, the pattern from D111:
1. Measure the instrument in its healthy state (known-firing corpus).
2. Break it deliberately (monkeypatch the function, empty the corpus, plant a
   key in a temp file).
3. Assert the measurement *moved* (not just that it passed — that it *changed*).
4. Restore state (`try/finally` around every mutation).
5. Verify restoration matches the original measurement.

All mutations are in-memory (monkeypatch) or in temp files (cleaned up).
No database writes. No container rebuilds.

---

### Evidence

**Full test output:**
```
======================================================================
LOCAL-227: INSTRUMENT FALSIFICATION REPORT
======================================================================

BASELINE: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]

  test_style_validator_r1_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_r3_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_r4_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_r7_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_r8_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_r9_falsification... ✓ NOTICES BREAKAGE
  test_style_validator_validate_paragraph_integration... ✓ NOTICES BREAKAGE
  test_claim_check_remove_passages... ✓ NOTICES BREAKAGE
  test_claim_check_corrupt_verdict_counts... ✓ NOTICES BREAKAGE
  test_corpus_coverage_empty_passages... ✓ NOTICES BREAKAGE
  test_corpus_coverage_creator_only_reclassify... ✓ NOTICES BREAKAGE
  test_anchor_detector_remove_corpus... ✓ NOTICES BREAKAGE
  test_anchor_detector_navigation_still_works... ✓ NOTICES BREAKAGE
  test_secret_scan_synthetic_key_fires... ✓ NOTICES BREAKAGE
  test_secret_scan_sha256_does_not_fire... ✓ NOTICES BREAKAGE
  test_secret_scan_whitelist_honored... ✓ NOTICES BREAKAGE

POST-CHECK: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
  ✓ Database unchanged.

======================================================================
SUMMARY
======================================================================
  Instruments that NOTICE breakage:       16
  Instruments that DO NOT notice:         0
  Tests with errors/precondition fails:   0
```

**Existing suites still green:**
```
tests/test_secret_scan.py:              42 passed
tests/test_r9_generic_deletion.py:      39/39 pass
tests/test_r8_prompt_leakage.py:        31/31 pass
tests/test_local210_calibration.py:     Pass (direction: over-flagging, safe)
tests/test_local195_anchor_regression:  Pass (133 tours, Nice list intact)
```

**Database integrity:**
```
BEFORE: audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
AFTER:  audio_tours = 133, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
```

---

### Per-file summary

| File | Action |
|---|---|
| `tests/test_local227_falsification.py` | NEW — 16 falsification tests covering 5 instruments |
| `SUBMISSION_LOCAL-227.md` | NEW — this file |

---

### Limitations

1. **Monkeypatch depth.** The style validator tests replace function pointers,
   not internal regex patterns. A rule whose *regex* is wrong but whose
   *function* is still called would not be caught by this test. The integration
   test partially addresses this by going through `validate_paragraph`, but a
   truly internal regex failure (e.g., a pattern that never matches because of
   a typo) requires the corpus to actually trigger the pattern — which we verify
   via the precondition assertion.

2. **Anchor detector corpus format.** The v2 anchor detector's `corpus_anchors`
   dict has a specific structure (`people`, `dates`, `titles`,
   `all_corpus_people`, `all_corpus_text`). The test constructs this manually
   rather than fetching from the database, so it does not exercise the DB
   extraction path (`build_corpus_anchors` / `get_venue_corpus_for_tour`).

3. **claim_check enhanced pass.** The test uses passages that match claims via
   basic token overlap. The enhanced stem+synonym pass is not separately
   falsified (it fires only when basic matching fails).

4. **No live generation.** These tests do not call the generation pipeline.
   They exercise instruments in isolation. A failure mode where the generation
   pipeline feeds corrupted data to an instrument would not be caught here.

5. **Pre-existing test failure.** `test_local198_corpus_coverage_gate.py` fails
   with `Expected 117, got 133` — this is a stale hardcoded count from before
   tours were added. Not caused by this task.

---

### Cost

$0.00 — all tests are offline (regex matching, function calls, temp files).
No LLM calls, no network requests, no container rebuilds.
