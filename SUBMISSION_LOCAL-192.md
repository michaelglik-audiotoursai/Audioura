##### READY FOR REVIEW

# SUBMISSION LOCAL-192: Validate-and-regenerate for style violations

**Branch:** `kiro/local192-validate-and-regenerate`
**Base:** `storied`
**Date:** 2026-08-04

---

## What was done

Added a post-generation style validation + per-paragraph retry step (Phase 5.1)
to `generate_tour_text.py`. After all stop descriptions are generated in parallel
(Phase 5), the deterministic style validator runs on each paragraph. Any paragraph
with an **error-severity** violation (R1–R4) gets a single retry: the model is told
exactly which rule it broke, the offending sentence is quoted, and it rewrites just
that paragraph.

Key design choices:
- **One retry per paragraph max.** If the retry also fails, the better of the two is kept.
- **R7 is warning-only** (D62) → does not trigger retry.
- **Behind `DISABLE_STYLE_RETRY=1`** flag for controlled A/B measurement.
- **Fabrication guard (D50):** The retry prompt explicitly says "rewrite using ONLY
  what is already in the paragraph; do not add facts." Temperature is lowered to 0.3
  for rewrites.
- **Cache bypass (D63):** Same approach as LOCAL-189 — `DATABASE_URL` removed so
  S20 tour cache doesn't mask the difference between arms.
- **STORIED_MODE=true** so stops are multi-paragraph (measurable).

---

## How the retry prompt prevents added facts

The retry prompt contains:
```
2. DO NOT ADD ANY NEW FACTS, claims, dates, names, or information not already
   present in the paragraph above. Rewrite using ONLY what is already stated.
   Adding facts risks fabrication.
```

The system message is: "You are a copy editor fixing style violations in audio tour
narration. You rewrite only — never add new information."

Temperature is 0.3 (vs 0.7 for generation) to reduce creativity/invention.

---

## How the cache was bypassed

Same method as LOCAL-189: `DATABASE_URL` is popped from `os.environ` before calling
`generate_tour_text()`. The S20 cache layer checks `os.environ.get("DATABASE_URL")`
and prints "DATABASE_URL not set — cache skipped" when absent. The stop_corpus reader
has its own fallback to `localhost:5433` so grounding material still flows.

---

## Results

### Paragraph Counts

|                          | ARM A (retry OFF) | ARM B (retry ON) |
|--------------------------|-------------------|------------------|
| Total paragraphs         | 18                | 18               |
| Navigation (exempt)      | 0                 | 0                |
| Content paragraphs       | 18                | 18               |
| Clean (no violations)    | 13                | 12               |

### Per-Rule Rates (violations per content paragraph)

| Rule | ARM A | ARM B | Delta |
|------|-------|-------|-------|
| R1 (imperatives)           | 0/18 = 0.00 | 1/18 = 0.06 | +0.056 |
| R3 (suggestive exploration)| 4/18 = 0.22 | 2/18 = 0.11 | −0.111 |
| R4 (prescribed feeling)   | 2/18 = 0.11 | 3/18 = 0.17 | +0.056 |
| R7 (hallucinated sensory) | 0/18 = 0.00 | 0/18 = 0.00 | +0.000 |

### Overall Failure Rate

- ARM A: 27.8% (5/18 paragraphs with ≥1 violation)
- ARM B: 33.3% (6/18 paragraphs with ≥1 violation)
- **Error-severity violations: ARM A = 6, ARM B = 6 (Δ = 0)**
- **Delta: +5.6 percentage points (retry did not reduce post-assembly rates)**

---

## Retry Mechanics — What Actually Happened

The retry DID fire and DID fix violations at the `description` level:

| Run | Paragraphs Retried | Fixed/Improved | Failed |
|-----|-------------------|----------------|--------|
| B1  | 3                 | 2              | 1      |
| B2  | 3                 | 2              | 1      |
| B3  | 2                 | 1              | 1      |
| **Total** | **8**       | **5**          | **3**  |

5 of 8 retried paragraphs passed validation after retry (62.5% success rate).
3 paragraphs could not be fixed in one retry.

**Why the post-assembly measurement doesn't show improvement:**
The validator runs on the `description` field in Phase 5.1, but the test measures
the fully-assembled tour text (after Phase 6 adds the prolog, transitions, and
epilog to Stop 1). Phase 6 injects ~130 words of prolog into Stop 1 that was never
validated. Additionally, generation is stochastic — ARM B's 3 runs happened to
produce different base text than ARM A's 3 runs.

---

## Retry Cost

| | Tokens | Cost |
|--|--------|------|
| B1 retries (3 paragraphs) | 1,235 | $0.0025 |
| B2 retries (3 paragraphs) | 1,259 | $0.0025 |
| B3 retries (2 paragraphs) | 804   | $0.0016 |
| **Total retry overhead**   | **3,298** | **$0.0066** |

- Base generation per tour (2 stops): ~$0.020
- Retry adds: ~$0.002 per tour (~10.9% overhead on the description call)
- Per-retry cost: ~$0.0008 (400 tokens average)

---

## Stop Titles (Itinerary Confound Check)

Both arms generated the same 2 stops in all 3 runs:
- Stop 1: Richard Long ou la sculpture en marchant (×3 per arm)
- Stop 2: She-Bam Pow POP Wizz (×3 per arm)

**SAME stops — direct comparison valid.**

---

## Sample Violations (ARM B with retry)

```
[R1_IMPERATIVE] Stop 1: "As you approach the exhibit, you'll be captivated..."
[R4_PRESCRIBED_FEELING] Stop 2: "She-Bam Pow POP Wizz showcases a visual symphony..."
[R3_SUGGESTIVE_EXPLORATION] Stop 1: "You are about to embark on a journey through..."
[R4_PRESCRIBED_FEELING] Stop 2: "She-Bam Pow POP Wizz captivates with its larger-than-life..."
[R3_SUGGESTIVE_EXPLORATION] Stop 1: "You are about to embark on a mesmerizing journey..."
[R4_PRESCRIBED_FEELING] Stop 2: "In front of you, She-Bam Pow POP Wizz stands..."
```

R4 remains the persistent offender. "Captivates" / "you'll be captivated" continue
to appear even after explicit prohibition + retry.

---

## Actual Spend

| Component | Cost |
|-----------|------|
| ARM A (3 runs × generation + spine + theme) | $0.147 |
| ARM B (3 runs × generation + spine + theme + retries) | $0.155 |
| Intent analysis + Phase 3B (6 calls) | $0.012 |
| **Total** | **$0.329** |

Ceiling: $0.40. Actual: $0.329 (82% of ceiling).

---

## Database Safety

- audio_tours total rows: **117** (unchanged)
- Nice list [1,12,14,17,21,24,27,28,29]: all present, all is_test=false
- Test tours: NOT WRITTEN (generate_tour_text writes to file only; all generated
  files cleaned up)

---

## The Failure Worth Reporting

**The model cannot reliably self-correct from rule feedback on R4.**

5 of 8 retried paragraphs passed validation — meaning the retry works for R3
(remove "as you explore" constructions) but fails persistently on R4 (prescribed
feeling). The model rewrites "you feel the weight" as "you'll be captivated" or
"the piece commands your attention" — different words, same rule violation.

The next design for R4 is **deterministic rewriting for the mechanical cases**:
regex-replace "you feel X" → "X is [adjective]", strip "as you stand before" →
"Before [object]". For constructions that can't be mechanically fixed (implicit
prescribed feeling through word choice like "captivates"), **removal** is the
fallback. This is not an LLM task.

---

## Limitations

1. **18 paragraphs per arm** — adequate for direction, not for precise magnitude.
   Same sample size limitation as LOCAL-189.
2. **Prolog contamination:** The Phase 6 prolog (~130 words) injected into Stop 1
   is not validated by Phase 5.1. It may contain violations that inflate the
   post-assembly rate.
3. **Stochastic generation:** Different base text between arms means some violations
   in ARM B were never in ARM A's baseline and vice versa. The retry success rate
   (62.5%) is the more meaningful metric than the arm-vs-arm delta.
4. **One retry only.** A second retry might fix the 3 failures, but the task spec
   says "never loop" and D63's design intent is to prove the concept, not to stack
   retries.

---

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | MODIFIED — added Phase 5.1 style validation + per-paragraph retry (LOCAL-192) |
| `tests/test_local192_style_retry_ab.py` | NEW — A/B test script |
| `SUBMISSION_LOCAL-192.md` | NEW — this submission |

---

## Commit

```
git rev-list --count storied..HEAD >= 1
```
