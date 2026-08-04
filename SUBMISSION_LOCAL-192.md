##### READY FOR REVIEW

# SUBMISSION LOCAL-192: Validate-and-Regenerate (Resubmission — 3 Defects Fixed)

**Branch:** `kiro/local192-validate-and-regenerate`
**Base:** `storied`
**Commit:** `7253257`
**Date:** 2026-08-04

---

## Fixes from LEAD Bounce

### Fix 1: Validator moved to repo root (import works inside Docker)

The canonical `style_validator_detector.py` now lives at the repo root, next to
`generate_tour_text.py`. A shim in `tests/` re-exports via `importlib` so existing
test scripts still work from either location.

`generate_tour_text.py` no longer does `sys.path.insert(0, '...tests')` — it imports
the validator as a peer module. Inside Docker, `/app/style_validator_detector.py` is
present (same build context as all other `.py` files at root).

**Proof pending LEAD rebuild:**
```
docker exec audioura-tour-generator-1 python -c "import style_validator_detector"
```

### Fix 2: Short paragraphs no longer dropped on reassembly

Previous code:
```python
_paragraphs = [p.strip() for p in _desc.split('\n\n') if p.strip() and len(p.strip()) > 30]
# ... only _paragraphs go into _new_paragraphs
poi_list[_si]["description"] = '\n\n'.join(_new_paragraphs)
```

Now: ALL non-empty segments are preserved. Only paragraphs >30 chars are validated;
short ones pass through unchanged. No content loss path.

### Fix 3: Retry cost no longer double-counted

Previous code accumulated `_style_retry_tokens` across ALL stops, then added the
**global cumulative** inside the per-stop loop — N stops with retries → stop 1's
tokens counted N times.

Now: per-stop variables `_stop_retry_tokens` / `_stop_retry_cost` reset to 0 for
each stop and only that stop's contribution is added to `total_tokens`/`total_cost`.

---

## A/B Results

MAMAC, same 2 stops (Richard Long ou la sculpture en marchant / She-Bam Pow POP Wizz),
3 runs per arm, 18 content paragraphs per arm. Validator unchanged.

### Per-Rule Rates

| Rule | ARM A (retry off) | ARM B (retry on) | Delta |
|------|-------------------|------------------|-------|
| R1 (imperatives) | 2/18 = 0.11 | 1/18 = 0.06 | −0.056 |
| R3 (suggestive exploration) | 2/18 = 0.11 | 2/18 = 0.11 | 0.000 |
| R4 (prescribed feeling) | 1/18 = 0.06 | 1/18 = 0.06 | 0.000 |
| R7 (hallucinated sensory) | 0/18 = 0.00 | 0/18 = 0.00 | 0.000 |

### Overall Failure Rate

- ARM A (retry off): **33.3%** (6/18 paragraphs with ≥1 error-severity violation)
- ARM B (retry on): **16.7%** (3/18 paragraphs with ≥1 error-severity violation)
- **Delta: −16.7 percentage points**

### Headline: Paired Before/After (Unconfounded)

| Run | Paragraphs retried | Fixed (errors→0) | Failed | Rules fixed |
|-----|-------------------|------------------|--------|-------------|
| B1 | 3 | 3 | 0 | R1+R3, R4, R3 |
| B2 | 1 | 1 | 0 | R3 |
| B3 | 3 | 2 | 1 | R3, R1+R3 (R4 failed) |
| **Total** | **7** | **6** | **1** | |

**Paired success rate: 6/7 = 85.7%**

The one failure was R4_PRESCRIBED_FEELING — "As you immerse yourself" persisted
through retry. This is the same R4 pattern LOCAL-189 found immune to prompt instruction.

---

## Retry Cost

| Metric | Value |
|--------|-------|
| Total retries fired (3 runs) | 7 |
| Total retry tokens | 2,921 |
| Total retry cost | $0.0058 |
| Per-tour retry overhead | ~$0.002 |
| Per-tour base cost (ARM B avg) | $0.0222 |
| **Retry as % of base** | **~9%** |

Total experiment spend: $0.127 (ARM A: $0.060, ARM B: $0.067). Ceiling: $0.40.

---

## How the Retry Prompt Prevents Added Facts

The retry prompt contains:

```
2. DO NOT ADD ANY NEW FACTS, claims, dates, names, or information not already present
   in the paragraph above. Rewrite using ONLY what is already stated. Adding facts
   risks fabrication.
```

The system message reinforces: "You are a copy editor fixing style violations in audio
tour narration. You rewrite only — never add new information."

Temperature is lowered to 0.3 (vs 0.7 for initial generation) to reduce creative drift.

---

## Cache Bypass

Same as LOCAL-189: `DATABASE_URL` removed from env before generation. The S20
`tour_cache` key does not include `DISABLE_STYLE_RETRY`, so without this bypass both
arms return identical cached text. The `stop_corpus` reader falls back to its own
`localhost:5433` connection for grounding material.

---

## Stop Titles (Itinerary Confound Check)

Both arms: Stop 1 = Richard Long ou la sculpture en marchant, Stop 2 = She-Bam Pow POP Wizz
(×3 each). **SAME stops — direct comparison valid.**

---

## Database Safety

- `audio_tours` total rows: **117** (unchanged)
- Nice list [1, 12, 14, 17, 21, 24, 27, 28, 29]: all present, all `is_test=false`
- Test tours: NOT WRITTEN (generate_tour_text writes to file only; all files cleaned up)

---

## `git status --short`

```
(clean)
```

---

## Files Changed

| File | Change |
|------|--------|
| `style_validator_detector.py` | **NEW** — canonical validator at repo root |
| `tests/style_validator_detector.py` | Replaced with re-export shim |
| `generate_tour_text.py` | Fix 1: direct import; Fix 2: keep all segments; Fix 3: per-stop cost |
| `tests/test_local192_style_retry_ab.py` | Updated A/B test script |

---

## Limitations

1. **R4 is partially resistant to retry.** 1 of 7 retries failed, and it was R4. The model
   rewrites "As you immerse yourself…" into another second-person formulation rather than
   converting to declarative. On gpt-3.5-turbo, R4 has a ~50% self-correction rate at best
   (1 of 2 R4 retries succeeded across the runs). This finding is about **gpt-3.5-turbo**
   specifically — the file contains 13 hardcoded `"model": "gpt-3.5-turbo"` calls and no
   env override. LOCAL-194 (model upgrade measurement) should be tested before building
   deterministic rewriting.

2. **n=18 per arm.** Adequate for direction (the -16.7pp delta is 3 paragraphs), not for
   precise magnitude. The paired 6/7 number is more reliable because it's unconfounded by
   generation stochasticity.

3. **Docker proof pending.** The import fix is correct by construction (file at repo root =
   same path as all other modules in the image), but the container hasn't been rebuilt yet.
   LEAD should verify with `docker exec ... python -c "import style_validator_detector"`
   after rebuild.

4. **R7 does not trigger retry** (it is warning-severity per D62). If R7 errors are desired
   in future, the `_ERROR_SEVERITIES` set in Phase 5.1 would need updating.

---

## Commit

```
$ git rev-list --count storied..HEAD
2
$ git log --oneline storied..HEAD
7253257 LOCAL-192: fix 3 defects in validate-and-regenerate, re-run A/B
20c047f LOCAL-192: validate-and-regenerate for style violations (Phase 5.1)
```
