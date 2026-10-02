##### READY FOR REVIEW

## LOCAL-327: Ungrounded ADEQUATE ceiling — bounce fix

**Commit:** 87c93bb  
**Branch:** kiro/local327-ungrounded-adequate  
**Files changed:**

| File | Summary |
|------|---------|
| `tour_evaluator.py` | Extract corpus_data/conn BEFORE classification loop; apply `_compute_groundedness_for_stop` before `_classify_stop`; add `conn=` parameter for auto-loading corpus from DB |
| `tour_scoring_service.py` | Pass `_get_connection()` to `evaluate()` so ceiling fires in production path |
| `run_local327_groundedness_audit.py` | Replace broken `get_corpus_passage_counts()` (ILIKE '%venue[:40]%') with `stop_corpus_reader.get_stop_corpus_for_tour()` which handles accent folding and suffix stripping |
| `run_local327_rescore.py` | Rewrite to use evaluate() with/without conn for before/after comparison |
| `tests/test_local327_ungrounded_adequate.py` | Add `TestEvaluatePathCeiling` class (2 new tests) proving ceiling fires through evaluate() |

---

## Root cause of the bounce

### Problem 1: Venue matching was broken

Old predicate in audit:
```python
"SELECT DISTINCT venue_name FROM stop_corpus WHERE venue_name ILIKE %s",
(f'%{venue_name[:40]}%',)
```

For the museum tour, venue extracted from header was:  
`Musée des Arts Asiatiques, Nice - Museum Tour` (truncated to 40 chars: `Musée des Arts Asiatiques, Nice - Museu`)

Stored in DB:  
`Musee des Arts Asiatiques (Asian Art Museum), Nice, France`

ILIKE match fails because: accented `Musée` vs plain `Musee`, `(Asian Art Museum)` infix, ` - Museum Tour` suffix.

**Fix:** Use `stop_corpus_reader.get_stop_corpus_for_tour()` which strips suffixes (" - Museum Tour"), tries multiple candidate forms, does accent-folded matching, and falls back to significant-word search.

**Verification:**
```
Old predicate: ILIKE '%Musée des Arts Asiatiques, Nice - Museu%' → 0 rows
New (stop_corpus_reader): finds 'Musee des Arts Asiatiques (Asian Art Museum), Nice, France' → 8 rows, 41 passages
```

### Problem 2: Ceiling was inert in the default scoring path

`tour_evaluator.py evaluate()` classified stops (line 311-314) BEFORE extracting `corpus_data` (line 333). Since `corpus_lookup_attempted` was never set True before `_classify_stop`, the ceiling could not fire.

**Fix:** Move corpus_data extraction and groundedness computation BEFORE the classification loop. Add `conn=` parameter so `tour_scoring_service.py` can pass a DB connection for auto-loading.

---

## Corrected distribution

```
ADEQUATE-or-better stops:    56
With corpus passages > 0:    46
With corpus passages = 0:    10  ← UNVERIFIED
Fraction unverified:         17.9%
```

(Was reported as 96% — that was entirely a venue-matching artifact.)

The 10 unverified stops:
```
LOCAL262_asian_arts_8stop_restored.txt  L'art en exil - Hàm Nghi   ADEQUATE  3 facts  0.60
LOCAL317_5stop_old_nice_restaurant.txt  Chez Palmyre                ADEQUATE  3 facts  0.60
Musee_Matisse museum tour               Blue Nude IV                ADEQUATE  4 facts  0.44
Chagall 205602                           King David                  ADEQUATE  5 facts  0.50
Chagall 213940                           La Création de l'homme      RICH     6 facts  0.60
Palais Lascaris                          Venus and Cupid             ADEQUATE  3 facts  0.21
Palais Lascaris                          The Penitent Magdalene      ADEQUATE  4 facts  0.36
matisse_nice.txt                         Nature morte aux grenades   ADEQUATE  5 facts  0.33
pilot_chagall_resubmit.txt               The Prophet Elijah          ADEQUATE  4 facts  0.33
pilot_chagall_resubmit.txt               The Song of Songs           ADEQUATE  5 facts  0.29
```

### Threshold

Binary: **at least 1 corpus passage must exist** for a stop to reach ADEQUATE.

Justification from the data:
- All 10 unverified stops have literally **zero** passages
- Grounded ADEQUATE+ stops have 1–7 passages (median 5.5)
- There is no grey zone — the distribution is bimodal (0 vs ≥1)

---

## Before/after scores

| Tour | Before | After | Delta | Stops changed |
|------|--------|-------|-------|---------------|
| Museum 8-stop (Asian Arts) | 78.1 | 71.9 | **-6.2** | La geste de Bouddha:RICH→ADEQUATE; L'art en exil:ADEQUATE→THIN |
| Old Nice Restaurant 317 | 55.0 | 50.0 | **-5.0** | Chez Palmyre:ADEQUATE→THIN |
| Old Nice Restaurant 318 | 65.0 | 60.0 | **-5.0** | La Voglia:RICH→ADEQUATE |
| Palais Lascaris | 18.8 | 12.5 | **-6.2** | Venus and Cupid:ADEQUATE→THIN; Penitent Magdalene:ADEQUATE→THIN |
| Musée Matisse | -3.1 | -6.2 | **-3.1** | Blue Nude IV:ADEQUATE→THIN |
| Chagall (pilot) | 0.0 | -6.2 | **-6.2** | The Prophet Elijah:ADEQUATE→THIN; The Song of Songs:ADEQUATE→THIN |
| Chagall 205602 | 65.6 | 62.5 | **-3.1** | King David:ADEQUATE→THIN |
| Chagall 213940 | 68.8 | 62.5 | **-6.2** | La Création de l'homme:RICH→THIN |

**All scores fell.** No score held steady or rose.

---

## Verification: named stops

### Zero-corpus stop capped (L'art en exil - Hàm Nghi)
- Corpus passages: **0** (confirmed via `get_stop_corpus_for_tour`)
- Facts: 3, density: 0.60 → meets ADEQUATE criteria
- Before: ADEQUATE (no ceiling)
- After: **THIN** (capped — "ADEQUATE capped: no corpus passages — facts unverified")

### Grounded stop unaffected (Masque du vieillard kojô)
- Corpus passages: **3** (matched via accent-folded comparison)
- Facts: 6+, groundedness: 50%
- Before: RICH
- After: **RICH** (unchanged — has corpus, groundedness ≥ 0.40)

### Robe de prêtre taoïste — NOT genuinely zero-corpus
The original task said this stop had "0 corpus passages." LEAD's spot check was correct: it has **4 passages** in stop_corpus. The broken venue matcher was hiding them.

---

## Deliberate break → test red → restore

```
# Broke classify_stop by replacing:
if sa.corpus_lookup_attempted and not sa.corpus_available:
# with:
if False and sa.corpus_lookup_attempted and not sa.corpus_available:

# Result: 6 tests FAILED
FAILED TestZeroCorpusCap::test_adequate_metrics_zero_corpus_capped_to_thin
FAILED TestZeroCorpusCap::test_rich_metrics_zero_corpus_capped_to_adequate
FAILED TestZeroCorpusCap::test_five_facts_zero_corpus_is_thin
FAILED TestScoreImpact::test_score_drops_for_unverified_stop
FAILED TestIntegrationScoreTourFile::test_corpus_data_triggers_ceiling
FAILED TestEvaluatePathCeiling::test_evaluate_with_corpus_data_applies_ceiling
# Restored → 14 passed
```

---

## Test results

```
$ python3 -m pytest tests/test_local327_ungrounded_adequate.py tests/test_local291_groundedness.py -q
.....................................
37 passed in 0.12s
```

---

## Limitations

1. **Ceiling requires DB connection.** When `evaluate()` is called without `conn=` and without `corpus_data=`, no ceiling fires. This is the `corpus_lookup_attempted` guard — by design, absence of a lookup is not absence of corpus (D162). In the production scoring path (`tour_scoring_service.py`), the connection is now provided.

2. **The problem is 18%, not 96%.** The original framing overstated the issue. Ten stops — mostly in Chagall, Palais Lascaris, and single restaurant stops — are genuinely unverified. Most of the corpus is properly connected.

3. **`La geste de Bouddha` drops RICH→ADEQUATE** even though it has 6 corpus passages. This is the LOCAL-291 groundedness floor (groundedness=17% < RICH_MIN_GROUNDEDNESS=0.40), not the LOCAL-327 corpus-availability ceiling. The text claims many facts not present in the 6 passages. This is separate from "no corpus at all."

4. **No container rebuild.** The `tour_scoring_service.py` change will take effect when the container is next restarted, not immediately.
