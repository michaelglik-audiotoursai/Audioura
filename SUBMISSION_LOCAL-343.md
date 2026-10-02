##### READY FOR REVIEW

## Commit

```
d91b61e  LOCAL-343: Fix vacuous groundedness — zero claims yields None, not 1.0
```

`git rev-list --count storied..HEAD` = 1

## Per-file summary

| File | Change |
|------|--------|
| `groundedness_check.py` | `measure_stop_groundedness`: when `total_claims == 0`, returns `groundedness_fraction=None` (was `1.0`). Same fix at aggregate level in `measure_tour_groundedness`. `GroundednessResult.groundedness_fraction` typed `Optional[float]`. |
| `tour_rubric_scorer.py` | `StopAnalysis` gains `groundedness_claims_checked: int = 0` field. `_compute_groundedness_for_stop` populates it from `result.total_claims`. `classify_stop` evidence string now includes `(n=X)` when measured. |
| `tour_evaluator.py` | `per_stop` dict includes `"groundedness_n"` field for sample-size visibility. |
| `tests/test_local343_vacuous_groundedness.py` | 10 tests covering zero-claims→None, sample size visibility, aggregate None, and non-regression for stops with claims. |

## Defect and fix

**Root cause (line 387 of `groundedness_check.py`):**
```python
fraction = grounded / total if total > 0 else 1.0
```

When a stop has corpus passages but the text contains no extractable fact-claims (no dates, no named people, no artwork titles), `total == 0` and the function returns `1.0`. This reports "everything we checked held" when nothing was checked.

**Fix:**
```python
fraction = grounded / total if total > 0 else None
```

`None` = unmeasured, consistent with D244's treatment of the no-corpus case. The stop has corpus but nothing checkable — it cannot claim to be verified.

## Scope item 2: Small denominator decision

A 1-claim stop scoring `1.0 (n=1)` is reported honestly. No smoothing prior, no Laplace correction. The evidence string now reads `groundedness 100% (n=1)` so a reader can judge weight. Inventing a prior would hide the problem instead of exposing it — the same instinct that produced the default 1.0.

## Scope item 3: Claim-count distribution

```
Tours scorable (parseable + corpus): 85
Tours with ≥1 zero-claim stop:       38  (45% of tours)
Total stops with corpus:              261

Claim count distribution:
  n= 0:   67 stops (25.7%) ← VACUOUS (was 1.0, now None)
  n= 1:   88 stops (33.7%)
  n= 2:   44 stops (16.9%)
  n= 3:   24 stops ( 9.2%)
  n= 4:   17 stops ( 6.5%)
  n= 5:   17 stops ( 6.5%)
  n= 6:    2 stops ( 0.8%)
  n= 7:    1 stops ( 0.4%)
  n=10:    1 stops ( 0.4%)

Impact:
  Stops that WERE 1.0 (now None): 67
  Stops scored on 1 claim only:   88
  Stops with n≥2 (solid):         106
```

**59% of our groundedness reporting** is near-vacuous (n=0 or n=1). The claim extractor finds dates, named people, and artwork titles — restaurant stops and walking stops rarely contain these, so their "perfect groundedness" was a measurement artifact.

## Verification: Museum scores unmoved

```
=== MUSEUM 8-STOP (id=21, scored n=8) ===
Score: 95.5
Groundedness: [0.6, 0.5, 0.5, 0.0, 0.5, 0.667, 1.0, 0.5]
Claims (n):   [5, 2, 2, 1, 2, 3, 1, 2]
All n > 0: True (fix cannot affect this tour)
```

All 8 stops have `total_claims > 0`. The fix only touches the `total == 0` branch. Museum scores are structurally immune to this change.

## Verification: Before/after

### Restaurant tour (id=17, n=5)
```
Score: 70.0 (UNCHANGED)
  Le Safari                  g=None  n=0  was=1.00 (VACUOUS)
  La Rossettisserie          g=1.00  n=2  unchanged
  Le Tire Bouchon            g=None  n=0  was=1.00 (VACUOUS)
  Le Bistro du Port          g=None  n=0  was=1.00 (VACUOUS)
  Le Vieux Four              g=0.00  n=1  unchanged
```
3 stops were vacuously 1.0, now correctly None. Score unchanged (all THIN on density — groundedness doesn't affect THIN classification).

### Walking tour (id=12, Nice, n=4)
```
Score: 193.25
  Promenade des Anglais             g=None  n=0  was=1.00 (VACUOUS)
  Castle Hill (Colline du Château)  g=None  n=0  was=1.00 (VACUOUS)
  Albert 1st Gardens                g=None  n=0  was=1.00 (VACUOUS)
  Nice Opera House                  g=1.00  n=2  unchanged
  Place Masséna                     g=0.50  n=2  unchanged
  Cours Saleya Market               g=1.00  n=1  unchanged
  Old Town (Vieux Nice)             g=None  n=0  was=1.00 (VACUOUS)
  Russian Orthodox Cathedral        g=0.00  n=1  unchanged
  Marc Chagall National Museum      g=None  n=0  was=1.00 (VACUOUS)
  Museum of Modern and Contemp.     g=None  n=0  was=1.00 (VACUOUS)
```
6 of 10 stops were vacuously 1.0. Now None.

### File: LOCAL262 Asian Arts 8-stop (from tours/)
```
Score: 88.9375
  Stops 7,8 (Les paysages de l'âme, L'art en exil): g=None n=0  was=1.00 (VACUOUS)
  Stops 1-6: g=[0.167, 0.0, 0.5, 1.0, 1.0, 0.667]  n=[6, 1, 2, 3, 3, 3]  unchanged
```

## Verification: Nothing rises

All previously-1.0 stops moved to None (lower or unmeasured). No stop's reported groundedness increased. Scores either stayed the same or stayed meaningfully proportional (no numeric score changed for the tours tested, because groundedness only affects RICH ceiling, and the affected stops are THIN).

## Break test transcript

```
=== DELIBERATE BREAK: simulate old behavior ===
total_claims=0, groundedness_fraction=1.0
✗ FAIL (as expected): Expected None, got 1.0
  Old code returns 1.0 for zero claims — the vacuous groundedness bug.

=== RESTORED: fixed production code ===
total_claims=0, groundedness_fraction=None
✓ PASS: zero claims correctly returns None (unmeasured)
```

## Test run

```
tests/test_local343_vacuous_groundedness.py — 10 passed
tests/test_local331_groundedness_default.py — 13 passed
tests/test_local291_groundedness.py         — 23 passed
tests/test_local327_ungrounded_adequate.py  — all passed
tests/test_local340_groundedness_misattribution.py — all passed
tests/test_local309_verified_unavailable.py — all passed
tests/test_local305_missing_stop_fairness.py — all passed
Total: 106 passed, 3 errors (pre-existing: missing gitignored tour file)
```

## Limitations

1. **Tour files `LOCAL336_walking_4stop.txt`, `LOCAL343_restaurant_4stop.txt`, `LOCAL342_walking_4stop.txt`** do not exist in the worktree (gitignored). Verification used equivalent tours from the database (id=12 walking, id=17 restaurant) and the existing `LOCAL262_asian_arts_8stop_restored.txt` file.

2. **Museum score values differ from task spec** (95.5 vs 75.0). The 75.0 comes from LEAD's measurement pass using different corpus data (as LOCAL-331 submission documents). The invariant holds: all stops in the museum tour have `total_claims > 0`, so the zero-claims fix structurally cannot affect them.

3. **The claim extractor is narrow** (dates, people, artworks). Restaurant and walking stops rarely contain these → 59% of "grounded" stops were never actually checked. Broadening the extractor is a separate concern (would change museum scores too).

4. **`OPENAI_API_KEY` not in environment** — cannot regenerate tours to produce the named files. This is a measurement/reporting fix, not a generation change.
