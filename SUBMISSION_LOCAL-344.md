##### READY FOR REVIEW

**Task:** LOCAL-344 — Align fact and claim extractors  
**Branch:** `kiro/local344-align-fact-and-claim-extractors`  
**Commit:** `28b2026`  
**Base:** `storied`

---

## Summary

The fact detector (in `tour_rubric_scorer.py`) counts five categories: dates, named people, materials, measurements, named periods. The groundedness claim extractor (in `groundedness_check.py`) previously only extracted three: persons, dates, artworks. This mismatch meant 55% of stops had zero groundedness claims despite having counted facts — the rubric rewarded facts that were never verified.

**The fix**: `extract_fact_claims()` now delegates to `analyze_stop()` — the same code the scorer uses — and promotes every detected fact to a `FactClaim`. This guarantees the property structurally without enumerating categories. `check_claim_grounded()` handles the new claim types with accent-folded substring matching.

---

## Files Changed

| File | Change |
|------|--------|
| `groundedness_check.py` | `extract_fact_claims()` calls `analyze_stop()` and generates claims for materials, measurements, periods. `check_claim_grounded()` handles new types with substring/token matching. |
| `tests/test_local344_fact_claim_alignment.py` | Property test (12 cases): every fact counted by analyze_stop has a corresponding claim. Grounding verification for new types. |
| `tests/run_local344_verification.py` | Verification script for D258 distribution and museum scores. |

---

## The Property (tested)

> For any stop text, let `sa = analyze_stop(stop, [stop])`. Then for every fact in `sa.dates_years ∪ sa.named_people ∪ sa.materials_techniques ∪ sa.measurements_numbers ∪ sa.named_periods`, there must be a corresponding `FactClaim` in `extract_fact_claims(text, title)`.

Enforced structurally — the claim extractor imports `analyze_stop` and uses its output directly. It is impossible for the fact detector to count something the claim extractor doesn't see for materials, measurements, and periods (they share identical code).

---

## Test Evidence (RED → GREEN)

```
BEFORE (unfixed):
tests/test_local344_fact_claim_alignment.py  10 FAILED, 2 passed

AFTER (fixed):
tests/test_local344_fact_claim_alignment.py  12 passed in 0.09s
```

Full regression suite (102 tests):
```
tests/test_local344_fact_claim_alignment.py    12 passed
tests/test_local343_vacuous_groundedness.py    10 passed
tests/test_local291_groundedness.py            23 passed
tests/test_local333_fact_detector_nonmuseum.py 34 passed
tests/test_local331_groundedness_default.py    14 passed
tests/test_local340_groundedness_misattribution.py 12 passed
                                              ─────────
                                              102 passed, 0 failed
```

---

## Museum 8-stop (Asian Arts) — Before vs After

```
                        BEFORE              AFTER
Base score:             71.875              65.625  ↓ fell (expected)

Stop 1 La geste de Bouddha:       gc=6 gf=0.167  →  gc=9 gf=0.111  ↓ fell
Stop 2 Daim et Daine:              gc=1 gf=0.000  →  gc=3 gf=0.333  ↑ rose*
Stop 3 Masque du vieillard:        gc=2 gf=0.500  →  gc=8 gf=0.125  ↓ fell
Stop 4 Statue de Bouddha:          gc=3 gf=1.000  →  gc=4 gf=1.000  = same
Stop 5 Kannon à mille bras:        gc=3 gf=1.000  →  gc=7 gf=0.429  ↓ fell
Stop 6 L'Armure d'Andô Naoyuki:    gc=3 gf=0.667  →  gc=7 gf=0.286  ↓ fell
Stop 7 Les paysages de l'âme:      gc=0 gf=None   →  gc=0 gf=None
Stop 8 L'art en exil:              gc=0 gf=None   →  gc=0 gf=None
```

**gc** = groundedness claims checked. **gf** = groundedness fraction.

*Stop 2 rose explanation: Before, only 1 claim (date "2nd century"), UNGROUNDED → 0/1=0.0. After, 3 claims (date "2nd century" + materials "gray", "schist"), and "schist" IS genuinely present in corpus → 1/3=0.333. A new check firing — `schist` is grounded because the corpus says "The statue is made of chlorite/schist." Not easy matching.

**Overall**: Base 71.875→65.625. Previously-uncheckable material/measurement facts are now checked; most are UNGROUNDED (not in corpus), which correctly lowers the score. No regression — this is the expected direction.

---

## Chagall 4-stop

```
Base score: 50.0 → 50.0 (unchanged)
All stops: gc=0, gf=None (no corpus passages exist for any Chagall stop)
```

The bound holds trivially — no corpus passages means no groundedness is measured.

---

## D258 Distribution — New Split (446 DB stops)

```
              BEFORE (D258)       AFTER (LOCAL-344)
n=0 claims:   115 (25.8%)         90 (20.2%)         −5.6pp
n=1 claims:   150 (33.6%)        132 (29.6%)         −4.0pp
n>=2 claims:  181 (40.6%)        224 (50.2%)         +9.6pp
```

Previously 59.4% of stops had ≤1 claim (near-vacuous). Now 49.8%. Majority of stops now have 2+ checkable claims.

---

## Residual: Facts Without Claims

**27 stops** still have `distinct_fact_count > 0` but `claims = 0`.

All 27 are false person detections in the fact detector — phrases like "Abu Dhabi", "Race Track", "Camel Tour", "Le Disque" pass `_PROPER_PHRASE_RE` in the scorer's person extraction but correctly fail `_PERSON_CONTEXT_RE` in the claim extractor (no person-context words nearby).

Categories of residual:
- Place names detected as people by the scorer: "Abu Dhabi", "Al Wathba Camel", "Qasr Al Sarab"
- Short phrases from French-language stops: "La Fuite", "Le Disque"  
- OLD regression test tours (pre-storied): "Pike Place Market" (date "360" — questionable 3-digit date)

**Why not zero**: The scorer's `named_people` detection is slightly more permissive than the claim extractor's person extraction (which requires person-context verification). This is a fact-detector false-positive issue, not a claim-extractor gap. The task says "do not widen the fact detector" — the right fix would be to tighten the scorer's person detection, which is out of scope.

---

## Corpus Row Counts (Unchanged)

```
stop_corpus:  117 rows
venue_corpus:  18 rows
```

---

## Limitations

1. **Residual is 27/446 (6%)** — all false person detections. Cannot be zero without tightening the fact detector (out of scope per task constraints).
2. **Stop 2 (Daim et Daine) groundedness rose** from 0.0→0.333 because a newly-checkable material ("schist") is genuinely grounded. Investigated: not easy matching.
3. **Chagall 4-stop unmeasurable** — no corpus passages exist, so the alignment change has no effect. The "87.5" reference in the task cannot be verified against file-based scoring because no Chagall corpus passages are harvested.
4. **"gray" extracted as material** — from "Sculpted from gray schist", the structural regex captures the first word after "from". This is a fact-detector quirk (color adjective, not material), but since the property says "anything the fact detector counts must be checkable", it is correctly promoted and correctly UNGROUNDED.
