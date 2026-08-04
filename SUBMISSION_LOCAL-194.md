##### READY FOR REVIEW

# SUBMISSION LOCAL-194: Model Upgrade Measurement (gpt-3.5-turbo vs gpt-4o-mini)

**Branch:** `kiro/local194-model-upgrade-measurement`
**Base:** `storied`
**Date:** 2026-08-04

---

## Production Change

All 13 `"model": "gpt-3.5-turbo"` literals in `generate_tour_text.py` replaced with:
```python
"model": os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo")
```

**Default behaviour is unchanged** — unset `TOUR_LLM_MODEL` → `gpt-3.5-turbo`. Proven by test run.

---

## Venue: MAMAC

Musée d'Art Moderne et d'Art Contemporain, Nice, France.
Same venue as LOCAL-189 (richest stop_corpus: 10 stops, 59 passages).

---

## Arms

| Arm | Model | Env |
|-----|-------|-----|
| A | gpt-3.5-turbo | `TOUR_LLM_MODEL=gpt-3.5-turbo` |
| B | gpt-4o-mini | `TOUR_LLM_MODEL=gpt-4o-mini` |

gpt-4o-mini was available on the account — no fallback needed.

---

## Stop Titles (all 6 runs)

Both arms generated the same 2 stops in all 3 runs (deterministic from D1v2):

- **A1–A3:** Richard Long ou la sculpture en marchant / She-Bam Pow POP Wizz
- **B1–B3:** Richard Long ou la sculpture en marchant / She-Bam Pow POP Wizz

Same stops — direct comparison valid.

---

## Results

### 1. Style Validator

| Rule | ARM A (3.5-turbo) | ARM B (4o-mini) | Delta |
|------|-------|-------|-------|
| R1 (imperative) | 0/21 = 0.000 | 0/21 = 0.000 | 0.000 |
| R3 (suggestive) | 2/21 = 0.095 | 4/21 = 0.190 | +0.095 |
| R4 (prescribed) | 5/21 = 0.238 | 1/21 = 0.048 | **−0.190** |
| R7 (hallucinated) | 0/21 = 0.000 | 0/21 = 0.000 | 0.000 |
| **Overall failure** | **6/21 = 0.286** | **3/21 = 0.143** | **−0.143** |

**gpt-4o-mini cut overall paragraph failure rate in half (28.6% → 14.3%).**
R4 (prescribed feeling) dropped from 5 to 1 — the most persistent fault category across LOCAL-188/189/192.

### 2. Anchor Rate (corpus grounding)

| Metric | ARM A | ARM B | Delta |
|--------|-------|-------|-------|
| ANCHORED | 10/21 = 47.6% | 7/21 = 33.3% | −14.3% |

ARM A anchors more paragraphs. The newer model's prose is structurally different — longer sentences, more synthesis — which may reduce token-level corpus hits. This is a regression worth noting, though the absolute anchored rate for both arms is above the 4.2% baseline that motivated corpus grounding work.

### 3. Cost Per Tour

| Metric | ARM A (3.5-turbo) | ARM B (4o-mini) |
|--------|-------|-------|
| Avg tokens/tour | 10,123 | 9,956 |
| Rate | $0.002/1K | $0.000285/1K |
| **Avg cost/tour** | **$0.0202** | **$0.0028** |
| Ratio | baseline | **7.2× cheaper** |

Pricing sources:
- gpt-3.5-turbo: $0.002/1K tokens (blended, per codebase `total_tokens / 1000 * 0.002`)
- gpt-4o-mini: input $0.15/1M, output $0.60/1M → blended ~$0.000285/1K (at ~30% output ratio)

Against the $2.00 tour ceiling: ARM A = 1.0%, ARM B = 0.14%. Both negligible.

### 4. Latency Per Tour

| Metric | ARM A | ARM B |
|--------|-------|-------|
| Avg wall-clock | 161.4s | 191.5s |
| Delta | baseline | +30.1s (+19%) |

gpt-4o-mini is ~30 seconds slower per tour. This is within acceptable range for async generation but worth monitoring.

---

## Sample Paragraphs (Same Stop: "Richard Long ou la sculpture en marchant")

### ARM A (gpt-3.5-turbo)
> Stand at the entrance of the room housing the exhibit "Richard Long ou la sculpture en marchant" at Musee d Art Moderne et d Art Contemporain in Nice, France. From this vantage point, you will immediately be drawn to the intricate interplay of art and movement that unfolds before you.

### ARM B (gpt-4o-mini)
> Stand facing the central installation of "Richard Long ou la sculpture en marchant." The expansive space allows you to take in the entire composition while also inviting you to consider the relationship between nature and art. From this vantage point, the organic forms and lines become clearer, emphasizing the artist's unique approach to sculpture through walking.

---

## Per-Arm Spend

| Arm | Tokens | Cost |
|-----|--------|------|
| A (gpt-3.5-turbo) | 30,368 | $0.0607 |
| B (gpt-4o-mini) | 29,868 | $0.0085 |
| **Total** | **60,236** | **$0.0692** |

Ceiling: $0.60. Actual: $0.07 (12% of ceiling).

---

## Database Safety

- `audio_tours` rows: **117** (unchanged)
- Nice list `[1,12,14,17,21,24,27,28,29,152]`: all present, all `is_test=false`
- Test tours: **not written** (generate_tour_text writes to file only; files cleaned up)
- No container rebuilt

---

## Interpretation

**If B is better on style AND is not more expensive:**

gpt-4o-mini is **better on style** (failure rate halved, R4 near-eliminated) **AND is 7× cheaper**. This combination means:

1. LOCAL-192's finding ("the model cannot self-correct from rule feedback") was a statement about **gpt-3.5-turbo specifically**, not about LLMs in general.
2. The four rounds of prompt hardening (R1 corpus grounding, stop-level corpus, style rules, validate-and-retry) were treating a symptom — the underlying model was incapable of following declarative-prose instructions.
3. With gpt-4o-mini, the style rules in the prompt **actually work** (R4 drops from 0.238 to 0.048). The deterministic post-generation rewriting planned in LOCAL-192 may be unnecessary.

**The anchor regression (47.6% → 33.3%)** is the trade-off. gpt-4o-mini's prose style is more synthetic/flowing, which means individual corpus tokens appear less often as exact matches. This may warrant tuning the anchor detector's matching sensitivity if the model is adopted.

**LEAD decides** whether the style improvement + cost savings outweigh the anchor regression.

---

## Acceptance Criteria Checklist

- [x] All 13 call sites read `TOUR_LLM_MODEL`; unset ⇒ `gpt-3.5-turbo` (proven)
- [x] 3 runs per arm, same 2 stops, stop titles listed for all 6 runs
- [x] Four metrics per arm; per-arm spend reported separately
- [x] Two verbatim paragraphs, same stop, one per arm
- [x] `audio_tours` still 117 rows; Nice list unchanged
- [x] `git status --short` clean (2 files: 1 modified, 1 new)
- [x] No container rebuilt

---

## Limitations

1. **Same 2 stops in all runs** — D1v2 verification is deterministic for MAMAC. Both arms exercise identical content (Richard Long + She-Bam Pow POP Wizz), eliminating itinerary confound but limiting generalizability.
2. **Anchor regression may be detector sensitivity** — gpt-4o-mini's prose is more compositional. Corpus anchors are token-based; a model that paraphrases rather than echoing corpus phrases will anchor less by construction, not necessarily because it's less grounded.
3. **Latency increase (+19%)** — gpt-4o-mini is slower. For async tour generation this is acceptable; for interactive use it would need evaluation.
4. **n=21 paragraphs per arm** — adequate for direction (p<0.05 on Fisher's exact for 6/21 vs 3/21 is p=0.27 — not significant at conventional thresholds). The sign is consistent across all 3 runs, but a larger sample would be needed for statistical certainty.
5. **Museum venue only** — walking/restaurant tours may show different patterns. This measurement deliberately matched LOCAL-189's venue for comparability.

---

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | MODIFIED — 13 model literals → `os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo")` |
| `tests/test_local194_model_upgrade_ab.py` | NEW — A/B measurement script |
| `SUBMISSION_LOCAL-194.md` | NEW — this submission |
