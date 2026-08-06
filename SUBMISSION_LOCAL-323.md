##### READY FOR REVIEW

## LOCAL-323: Meter TTS and Attribution

**Commit:** `d69e373` on branch `kiro/local323-meter-tts-and-attribution`

---

### Per-file Summary

| File | Change |
|------|--------|
| `cost_rates.py` | Added engine-aware pricing: `POLLY_STANDARD_COST_PER_1M_CHARS = 4.00`, `POLLY_NEURAL_COST_PER_1M_CHARS = 16.00`. `tts_cost()` now accepts `engine` kwarg. Legacy `POLLY_COST_PER_CHAR` preserved. |
| `cost_meter.py` | Added `tts_generate` and `tts_cache_hit` to `VALID_OPERATION_TYPES`. |
| `polly_tts_service.py` | Metering after successful synthesis: reads optional `user_id`/`job_id` from request, computes cost from chars×engine rate, writes `tts_generate` row via `record_operation`. Non-fatal try block. Extracted `NEURAL_VOICES` frozenset and `engine` variable to avoid repetition. |
| `tour_orchestrator_service.py` | Forwards `user_id` and `job_id` to modernized service `/process` endpoint (2 lines). |
| `tour_generation_modernized.py` | `/process` accepts `user_id`/`job_id`. `generate_modernized_tour_async` forwards them to TTS requests. |
| `spine_generator.py` | `generate_spine()` gains `user_id` kwarg, passes to `record_operation`. |
| `generate_tour_text.py` | Added `_CURRENT_JOB_USER_ID` and `_CURRENT_JOB_ID` module-level vars. Spine calls pass these. |
| `generate_tour_text_service.py` | Sets `_CURRENT_JOB_USER_ID`/`_CURRENT_JOB_ID` before calling `generate_tour_text()`. |
| `tests/test_local60_cost_metering.py` | Added `tts_generate`, `tts_cache_hit` to expected types set. |
| `tests/test_local323_tts_metering.py` | 9 tests: engine-aware pricing, record_operation integration, cache_hit $0, spine param, service attribution checks. |
| `verify_local323.py` | End-to-end verification script (calls live TTS + writes to live DB). |

---

### Rates Used

| Engine | Rate | Source |
|--------|------|--------|
| Standard | $4.00 / 1M characters | https://aws.amazon.com/polly/pricing/ |
| Neural | $16.00 / 1M characters | https://aws.amazon.com/polly/pricing/ |

Read date: 2026-08-06. Neural voices in this codebase: Joanna, Matthew, Amy, Brian (polly_tts_service.py:66).

---

### Verbatim Evidence

#### 1. Neural TTS → ledger row with character count, engine, and cost

```
1. NEURAL TTS: 79 chars, voice=Joanna, engine=neural
  TTS response: 200, audio size: 29564 bytes
  Ledger row: f75f2bcd-1abe-4266-844d-92d35ca30009
  Cost: $0.001264 (79 chars × $0.00001600/char)
```

#### 2. Standard TTS → different unit cost

```
2. STANDARD TTS: 71 chars, voice=Ivy, engine=standard
  TTS response: 200, audio size: 27316 bytes
  Ledger row: 3f2f36fc-07d4-4ff9-b7b0-4b60f7393489
  Cost: $0.000284 (71 chars × $0.00000400/char)
```

Neural ($0.001264 for 79 chars) ≠ Standard ($0.000284 for 71 chars). Ratio: $16/$4 = 4×.

#### 3. Cache hit → $0.00

```
3. TTS CACHE HIT: $0.00
  Ledger row: 908e6921-5d07-41d8-9dc9-57e6226a63f8
  Cost: $0.000000 (cache hit)
```

#### 4. All three rows in DB

```
  operation_type   user_id                                cost  cache_hit breakdown
  tts_generate     verify_local323_d605e844       $  0.001264      False {'chars': 79, 'engine': 'neural', 'voice_id': 'Joanna'}
  tts_generate     verify_local323_d605e844       $  0.000284      False {'chars': 71, 'engine': 'standard', 'voice_id': 'Ivy'}
  tts_cache_hit    verify_local323_d605e844       $  0.000000       True {'chars': 0, 'engine': 'neural', 'voice_id': 'Joanna'}
```

#### 5. Whole-tour total cost (now computable)

```
  Tour job: f1791c9d-b4b1-422c-b89b-7713abee94d2
  User: quota_probe_lead
    tour_generate        $0.060006
    tts_generate (est)   $0.240000  ← NOW TRACKABLE

  TOTAL TOUR COST: $0.300006
  (Previously only $0.060006 was visible — TTS was invisible)
```

The 15,000-char neural TTS estimate ($0.24) is what will appear as actual rows once containers are rebuilt.

#### 6. New unattributed rows: zero

```
  New unattributed rows in last hour (excl spine/test): 0
```

#### 7. cost_ledger row count

```
Before verification: 268
After verification:  274 (added 6 verification rows across 2 runs)
```

Rows added: 6 (all clearly marked with `verify_local323_` user_id prefix).

---

### Unattributed Rows Analysis

| operation_type | count | Root cause | Fix |
|---------------|-------|-----------|-----|
| spine_generate | 62 | `generate_spine()` never accepted `user_id` | Added `user_id` param, wired through module-level context |
| tour_cache_hit | 21 | Before orchestrator rejected empty `user_id` | Already fixed by existing fail-closed check |
| tour_generate | 18 | Same as above | Already fixed |
| **Total** | **101** | | |

**Decision:** Historical rows NOT backfilled. A fabricated attribution is worse than a known gap. Going forward, all three paths produce attributed rows.

---

### Schema Changes

**Additive only.** No new columns. Two new values in `cost_meter.VALID_OPERATION_TYPES`:
- `tts_generate`
- `tts_cache_hit`

---

### What Was NOT Changed

- `COST_TARGET` and `COST_HARD_LIMIT` — unchanged (ceiling policy is a separate task)
- No rows deleted from `cost_ledger`
- No rows modified in `audio_tours`
- No container rebuilt
- The three $12.50 synthetic rows (`test_*_unlim_*`) excluded by user_id prefix in analysis

---

### Limitations

1. **Container rebuild required for production metering.** The code changes to `polly_tts_service.py` and `tour_generation_modernized.py` only take effect after containers are rebuilt. The verification demonstrates the metering logic works by calling `record_operation` from the host.

2. **news_processor_service.py TTS calls** are not yet wired for attribution (no `user_id`/`job_id` forwarded). These will produce `tts_generate` rows with NULL user_id until that service is updated. This is distinguishable from a bug (it's a known gap in an internal service path).

3. **translation_service TTS** calls AWS Polly directly (not via polly_tts_service HTTP endpoint). That path is already covered by the `translation_generate` cost estimate but does not produce a separate `tts_generate` row.

4. **The verify_local323.py rows** (6 total, clearly marked `verify_local323_*`) remain in the ledger per the "do not DELETE from cost_ledger" rule.
