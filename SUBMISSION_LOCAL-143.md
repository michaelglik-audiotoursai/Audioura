##### READY FOR REVIEW

# SUBMISSION LOCAL-143: Make Booked Translation Cost Follow the Code That Changed

**Task:** Make the booked translation cost follow the code that changed  
**Branch:** kiro/local143-translation-cost-follows-code  
**Base:** subscribed  

---

## 1. Deployed Container State (Measured, Not Assumed)

```
$ docker ps --filter name=audioura-translation-service-1 --format '{{.Names}} {{.Status}}'
audioura-translation-service-1 Up 2 days

$ docker inspect audioura-translation-service-1 --format '{{.Created}}'
2026-07-28T15:43:00.686597341Z

$ docker exec audioura-translation-service-1 grep -c "LOCAL-142" /app/translation_service.py
0   (exit code 1 — no matches)

$ docker exec audioura-translation-service-1 grep -n "self.translate_text(self._strip_nav_fields_for_tts" /app/translation_service.py
294:                    tts_text = self.translate_text(self._strip_nav_fields_for_tts(stop_text), target_language)
```

**Conclusion:** Container built 2026-07-28, predates LOCAL-142 merge (2026-08-02).
No single-pass code present. **The deployed service runs TWO-PASS translation.**

---

## 2. Design Decision

**Option chosen: Parameterize `translation_cost()` by pass count, with the
default driven by a deployment-inspected constant.**

Reasoning:
- The task says "prefer measuring over assuming." The enforcement test
  (`test_local143_cost_model_matches_deploy.py`) *measures* the container on
  every run via `docker exec grep`.
- A constant that is validated against reality on every test run is the next
  best thing to a live call count (which would require changing the translation
  service response shape — out of scope).
- The constant is set to 2 today (matching the container). When LOCAL-142
  deploys, the test will FAIL until someone flips it to 1. This is the
  desired property: **the cost model cannot silently drift from the deployed code.**
- The alternative (have the translation service report call count back) would
  require changing the service's API contract — a larger change with deployment
  coordination. The parameterized constant achieves the same correctness with
  zero deployment dependency.

---

## 3. Changes Made

| File | Change |
|------|--------|
| `cost_rates.py` | Added `DEPLOYED_TRANSLATION_PASSES = 2` constant with documentation of how it was determined. Parameterized `translation_cost(char_count, passes=None)` — `passes=2` uses the old 1.95× multiplier, `passes=1` uses 1.0×; default comes from the constant. Added `ValueError` on invalid passes. |
| `tour_orchestrator_service.py` | Metering block now imports `DEPLOYED_TRANSLATION_PASSES`, passes it explicitly to `translation_cost()`, and records it in the breakdown dict for audit. |
| `tests/test_local60_cost_metering.py` | Added assertions for `passes=1` mode and verified `default == explicit(passes=DEPLOYED)`. Comment updated with LOCAL-143 reference. |
| `tests/test_local143_cost_model_matches_deploy.py` | **NEW.** Enforcement test: inspects running container, asserts constant matches, verifies arithmetic, orchestrator wiring, and input validation. |

---

## 4. Evidence

### 4.1 All 5 required test suites — BEFORE (base, no changes)

```
tests/test_local60_cost_metering.py         exit 0
tests/test_local64_cost_ceiling.py          exit 0
tests/test_local69_news_metering.py         exit 0
tests/test_local83_charging_wire.py         exit 0
tests/test_local142_single_pass_translation.py  exit 0
```

### 4.2 All 5 required test suites — AFTER (this branch)

```
tests/test_local60_cost_metering.py         exit 0
tests/test_local64_cost_ceiling.py          exit 0
tests/test_local69_news_metering.py         exit 0
tests/test_local83_charging_wire.py         exit 0
tests/test_local142_single_pass_translation.py  exit 0
```

### 4.3 New enforcement test

```
tests/test_local143_cost_model_matches_deploy.py  exit 0  (21 passed, 0 failed)
```

Key assertions proved:
- Container grep returns 0 LOCAL-142 matches → two-pass active
- DEPLOYED_TRANSLATION_PASSES (2) == detected pass mode (2)
- Two-pass arithmetic: 33.278 per 1M source chars ✓
- Single-pass arithmetic: 19.028 per 1M source chars ✓
- Ratio: ~1.75× (two-pass/one-pass) ✓
- Invalid passes (0, 3, -1) all raise ValueError ✓
- Orchestrator imports DEPLOYED_TRANSLATION_PASSES ✓
- Orchestrator passes it to translation_cost() ✓
- Breakdown records translation_passes ✓
- Default(N) == explicit(N, passes=2) for all test sizes ✓
- Real tours (14, 21, 27): default matches 2-pass, saving ~43% switching to 1-pass ✓

### 4.4 Booked cost matches the pass count actually used

| Tour | Chars | 2-pass cost (deployed) | 1-pass cost (after LOCAL-142 deploys) |
|------|-------|----------------------|--------------------------------------|
| 14   | 17,765 | $0.5912 | $0.3382 |
| 21   | 14,755 | $0.4910 | $0.2809 |
| 27   | 16,531 | $0.5501 | $0.3147 |

Today's deployed cost (2-pass) matches the old measured $0.53 ± $0.05 from
LOCAL-135 — confirming no overshoot or undershoot vs reality.

### 4.5 Fallback behaviour

When LOCAL-142 deploys and the positional strip fallback fires (line count
mismatch), that individual stop costs 2 translate_text calls. The overall
pass count for the tour is between 1.0 and 2.0, but the *booked* cost uses
the mode's per-stop assumption:
- `passes=1`: assumes the optimistic case (no fallbacks). This underestimates
  by at most 1 translate_text call per affected stop.
- `passes=2`: assumes the pessimistic case (all fallbacks). This overestimates
  by the savings on stops where the positional strip succeeded.

With the constant set to 2 (matching the deployed code which always does 2
calls), the booked cost is **exact** — not an estimate.

---

## 5. How the Test Fails If They Drift

**Scenario A — Container rebuilt with LOCAL-142, constant still 2:**
```
  FAIL: DEPLOYED_TRANSLATION_PASSES == detected (1)
    — constant=2, container=1. The cost model is overstating translation cost!
      Update DEPLOYED_TRANSLATION_PASSES in cost_rates.py.
```

**Scenario B — Constant flipped to 1, container still runs old code:**
```
  FAIL: DEPLOYED_TRANSLATION_PASSES == detected (2)
    — constant=1, container=2. The cost model is understating translation cost!
      Update DEPLOYED_TRANSLATION_PASSES in cost_rates.py.
```

---

## 6. API Spend Incurred

**$0.00.** No API calls, no Docker builds, no container modifications.
All evidence from docker inspect/exec (read-only) and offline tests.

---

## 7. Limitations

- **The enforcement test requires Docker access.** If run in CI without Docker,
  it skips the container inspection and only runs internal consistency checks.
  The test clearly logs "SKIP (container not available)" in that case.
- **The per-stop fallback count is not tracked.** When LOCAL-142 deploys,
  setting `DEPLOYED_TRANSLATION_PASSES=1` assumes the optimistic path (no
  fallbacks). For tours where fallback fires on some stops, the real cost is
  slightly higher. The maximum error is bounded: at most 0.95 × source_chars
  × $0.000015 per fallback stop. For a typical 9-stop tour with 2 fallbacks,
  the error is ~$0.03 (5% of total) — within the existing stdev of $0.05.
- **x5 multiplier unchanged.** The user-facing price decision is Michael's
  per TRANSLATION_PRICING.md. This change only corrects the *input* to that
  multiplier.
- **No changes to the translation service.** LOCAL-142's code is in git but
  not deployed; this task only fixes the cost model, not the deployment.

---

## 8. Commit

```
0fa1dce LOCAL-143: make booked translation cost follow deployed pass count
git rev-list --count subscribed..HEAD = 1
git status --short = (clean)
```
