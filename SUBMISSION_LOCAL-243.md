##### READY FOR REVIEW

## LOCAL-243: R10 In-Pipeline Verification (Round 3, Final)

**Commit:** `ec98723`
**Branch:** `kiro/local243-round3-final`
**Base:** `storied`

---

## Per-File Summary

| File | Change |
|---|---|
| `RIVIERA_2STOP_ROUND3.md` | Overwritten with LOCAL-243 regeneration — R10 confirmed running in-pipeline (PHASE 5.155) |
| `run_local243_riviera_round3.py` | Generation script: fresh LLM call, cache bypassed, all gates active, R10 NOT re-applied in post-processing |

---

## Evidence

### PHASE 5.155 — CONFIRMED RUNNING IN-PIPELINE

```
[LOCAL-235] PHASE 5.155: R10 unfulfilled-promise deletion...
[LOCAL-235] R10 summary: 0 sentences deleted, 0 paragraphs emptied, 0 stops affected
```

R10 imported successfully through the fixed shim (`tests/style_validator_detector.py` now forwards all names dynamically). The `apply_r10_to_description` function resolved and executed. It found 0 sentences to delete because the LLM did not produce R10-triggering text in the stop descriptions this run.

### Generation parameters

```
STORIED_MODE=true
TOUR_LLM_MODEL=(unset → gpt-3.5-turbo)
ENABLE_STOP_EXISTENCE_GATE=1
DATABASE_URL removed (cache bypass)
DISABLE_STYLE_RETRY=(unset → ON)
DISABLE_R10_DELETION=(unset → ON)
DISABLE_R9_DELETION=(unset → ON)
DISABLE_CONTRADICTED_BLOCK=(unset → ON)
DISABLE_SUBJECT_ROUTINE=(unset → ON)
```

### Model and cost

```
Model: gpt-3.5-turbo (default)
Tokens: 9,080
Cost: $0.0073 (generation $0.0073 + subject $0.0000)
Ceiling: $0.20
Generation time: 38.7s
Cache hit: False
```

### Four-way word count comparison

```
Run                            Words   R10 position
------------------------------ ------  --------------------
Round 2                          819   (no R10)
LOCAL-240 re-applied             191   (R10 on old text)
LOCAL-241 end-to-end             393   (R10 post-processing)
LOCAL-243 (this run)             505   (R10 in-pipeline)
```

### Key finding: R10 position does not matter when R10 finds nothing

LOCAL-241 had 5 R10 post-processing deletions (~90 words removed). LOCAL-243 had 0 R10 deletions (LLM didn't produce R10-triggering text in stop descriptions). The +112 word difference is LLM generation variance, not an R10 positioning effect. R10's position in the pipeline is moot when it finds nothing to delete.

### Style validator still flags prolog/epilog

```
P2 (prolog): R10_UNFULFILLED_PROMISE — added in PHASE 6, after R10 ran
P6 (epilog): R9_GENERIC — added in PHASE 6, after R9 ran
```

These are assembly-stage artifacts. PHASE 5.155 (R10) and PHASE 5.15 (R9) operate on stop descriptions before PHASE 6 adds prolog/transitions/epilog. This is a structural gap in the pipeline: assembly-generated text bypasses all style gates.

### Database invariants

```
audio_tours: 142 → 143 (+1, tour 199)
Tour 199: is_test=True, lat=NULL, lng=NULL
Nice list: [1, 12, 14, 17, 24, 29, 152] — UNCHANGED ✓
```

### Stops selected and verified

```
Cap d'Antibes: VERIFIED (stop_corpus_geographic)
Col de Vence:  VERIFIED (stop_corpus_geographic)
```

---

## Limitations

1. **R10 deleted 0 sentences.** This means we cannot compare "R10 in-pipeline produced X deletions vs R10 post-processing produced Y deletions" — there's no deletion to compare. The LLM simply generated cleaner text this run. A definitive comparison would require a run where the LLM produces R10-triggering text and we can observe whether in-pipeline R10 changes downstream paragraph generation.

2. **Prolog/epilog bypass style gates.** Paragraphs 2 and 6 (prolog, epilog) trigger R10/R9 respectively but were added AFTER those gates ran. This is a structural gap — not a regression, since it existed before LOCAL-243.

3. **LLM variance.** gpt-3.5-turbo is non-deterministic. The same prompt produced 183+60=243 words of stop descriptions (vs LOCAL-241's different word distribution). Direct comparison between runs is always confounded by this variance.

4. **Subject routine found 0 promises.** Unlike LOCAL-241 (which found and expanded 1 promise), this run's text contained no unfulfilled-promise patterns detectable by the subject routine. This is also LLM variance.

5. **No container rebuilt (D48 compliant).** All work done via Python scripts against the running services.

---

## git status --short

```
(clean after commit)
```
