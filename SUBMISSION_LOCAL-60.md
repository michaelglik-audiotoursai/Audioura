##### READY FOR REVIEW

**Branch:** `kiro/local60-cost-metering`
**Date:** 2026-07-31T18:20 UTC

---

## Commit

```
c9415b5 LOCAL-60: Per-operation cost metering — cost_meter, cost_rates, wiring, migration
```

Commit `c9415b5` relative to storied (git rev-list --count storied..HEAD = 1).
SUBSCRIBED_DESIGN.md pulled from origin/storied (not committed — it belongs to storied, not this branch).

---

## Per-file changes

| File | Change |
|------|--------|
| `cost_meter.py` | **NEW** — Single ledger module. `record_operation()` writes to `cost_ledger` table. Enforces cache_hit=True → cost forced to 0 (with warning). `get_operation_cost()` for audit queries. |
| `cost_rates.py` | **NEW** — Centralised rate table. GPT-3.5/4o-mini, Serper, Polly TTS, Google Translate rates. Helper functions: `llm_cost()`, `search_cost()`, `tts_cost()`, `translation_cost()`. `CACHE_HIT_COST_USD = 0.00`. |
| `cost_ceiling_monitor.py` | **EXISTING, unchanged** — Referenced for cross-check validation only. |
| `generate_tour_text.py` | **MODIFIED** — Added `_LAST_GENERATION_COST` global, set on cache hit (cost=0) and on fresh generation (cost=total_cost, breakdown). |
| `generate_tour_text_service.py` | **MODIFIED** — After generation, reads `_LAST_GENERATION_COST` and calls `record_operation()` with correct op_type and cache_hit flag. |
| `tour_orchestrator_service.py` | **MODIFIED** — Translation path: reads `cache_hit` from translation service response, meters `translation_generate` or `translation_cache_hit` with estimated cost or zero. |
| `migration/sql/005_cost_ledger.sql` | **NEW** — DDL for `cost_ledger` table with indexes and comments. |

---

## Evidence: Fresh tour generation (cache_hit=false)

**Venue:** Musee d Art Moderne et d Art Contemporain, Nice, France (MAMAC) — NOT previously cached.
**Job ID:** `f3131458-069f-4459-8390-240c0d577ae7`
**User ID:** `local60-fresh-evidence`

### Container log (verbatim):
```
Total API cost: $0.0803 (40130 tokens)
[COST_METER] FRESH | tour_generate | $0.080260 | user=local60-fresh-evidence | job=f3131458-069f-4459-8390-240c0d577ae7
[LOCAL-60] Cost metered: tour_generate | $0.080260 | cache_hit=False
```

### Corpus mining evidence (story_miner ran):
```
[§3-adapter] Extracting story elements from 5/27 corpus pages for 'Musee d Art Moderne et d Art Contemporain'
  page[0] score=12405 url=https://fr.wikipedia.org/wiki/Musée_d'Art_moderne_et_d'Art_contemporain_de_Nice
  page[1] score=10275 url=https://en.wikipedia.org/wiki/Musée_d'art_moderne_et_d'art_contemporain
  page[2] score=6870 url=https://www.mamac-nice.org/collection/oeuvres-in-situ/
```

### Ledger row (DB query):
```
operation_type | user_id                | our_cost_usd | cache_hit | job_id                               | breakdown
tour_generate  | local60-fresh-evidence | 0.080260     | f         | f3131458-069f-4459-8390-240c0d577ae7 | {"llm": 0.08025999999999998, "tts": 0.0, "search": 0.0}
```

### Cross-check against check_cost_ceiling:
```python
check_cost_ceiling(0.080260, 'museum', True)
# Result: {'exceeded': False, 'cost': 0.08026, 'ceiling': 0.15}
# COST OK: $0.0803 (category=museum)
```

**Cost ceiling compliance:** $0.0803 << $1.30 (Michael's hard ceiling). Under $0.15 soft ceiling.

### Breakdown analysis:
- `llm: $0.08026` — 40,130 tokens × $0.002/1K = $0.08026 ✓
- `tts: $0.00` — TTS (Polly) cost is metered at audio processing stage (tour-processor service), not during text generation
- `search: $0.00` — No Serper API calls during service-level generation; corpus mining uses direct HTTP fetches to museum websites (free)

---

## Evidence: Same tour from cache (cache_hit=true)

**Job ID:** `14d1adc8-053e-4d3e-88fc-6178b1edb555`

### Container log (verbatim):
```
CACHE HIT: Musee d Art Moderne et d Art Contemporain, Nice, France / museum / 10
[COST_METER] CACHE_HIT | tour_cache_hit | $0.000000 | user=local60-fresh-evidence | job=14d1adc8-053e-4d3e-88fc-6178b1edb555
[LOCAL-60] Cost metered: tour_cache_hit | $0.000000 | cache_hit=True
```

### Ledger row:
```
operation_type | user_id                | our_cost_usd | cache_hit | job_id                               | breakdown
tour_cache_hit | local60-fresh-evidence | 0.000000     | t         | 14d1adc8-053e-4d3e-88fc-6178b1edb555 | {"llm": 0.0, "tts": 0.0, "search": 0.0}
```

---

## Evidence: Fresh translation (cache_hit=false)

**Job ID:** `b5fe38cc-004d-4896-bfaf-f81f9fa39e7c` (French translation of MAMAC tour)

### Orchestrator log (verbatim):
```
Translation successful! Translated tour ID: 45 (cache_hit=False)
[COST_METER] FRESH | translation_generate | $0.372000 | user=local60-fresh-evidence | job=b5fe38cc-004d-4896-bfaf-f81f9fa39e7c
```

### Ledger row:
```
operation_type       | user_id                | our_cost_usd | cache_hit | job_id                               | breakdown
translation_generate | local60-fresh-evidence | 0.372000     | f         | b5fe38cc-004d-4896-bfaf-f81f9fa39e7c | {"tts": 0.032, "translate": 0.34}
```

### Breakdown:
- `translate: $0.34` — estimated 17K chars × $0.00002/char (Google Translate)
- `tts: $0.032` — estimated 8K chars × $0.000004/char (Amazon Polly)
- Note: These are estimates based on typical tour length. For exact figures, the translation service would need to report actual char counts. Improvement deferred.

---

## Evidence: Same translation from cache (cache_hit=true)

**Job ID:** `b7c03913-73de-42d1-9ddc-2534826fb042`

### Orchestrator log (verbatim):
```
Translation successful! Translated tour ID: 45 (cache_hit=True)
[COST_METER] CACHE_HIT | translation_cache_hit | $0.000000 | user=local60-fresh-evidence | job=b7c03913-73de-42d1-9ddc-2534826fb042
```

### Ledger row:
```
operation_type        | user_id                | our_cost_usd | cache_hit | job_id                               | breakdown
translation_cache_hit | local60-fresh-evidence | 0.000000     | t         | b7c03913-73de-42d1-9ddc-2534826fb042 | {"tts": 0.0, "translate": 0.0}
```

---

## Full ledger (all rows for user=local60-fresh-evidence):

```
operation_type        | our_cost_usd | cache_hit | job_id   | created_at
tour_generate         | 0.080260     | f         | f3131458 | 2026-07-31 18:15:43 UTC
tour_cache_hit        | 0.000000     | t         | 14d1adc8 | 2026-07-31 18:16:38 UTC
tour_cache_hit        | 0.000000     | t         | 482fc074 | 2026-07-31 18:17:33 UTC  ← orchestrator re-request (EN tour cached)
translation_generate  | 0.372000     | f         | b5fe38cc | 2026-07-31 18:18:20 UTC
tour_cache_hit        | 0.000000     | t         | de4a99d9 | 2026-07-31 18:19:33 UTC  ← 2nd FR request, tour part
translation_cache_hit | 0.000000     | t         | b7c03913 | 2026-07-31 18:20:03 UTC
```

---

## News path

**Status:** Not wired. News services (`news-orchestrator-1:5012`, `news-generator-1:5010`, `news-processor-1:5011`) are running, but `record_operation` is not imported into any news service file. The `news_generate` operation type is defined in `cost_meter.py` and ready for wiring, but no call site exists yet. This is a known gap; wiring requires changes to the news orchestration code (a separate task).

---

## Cloud gateway / entitlements investigation

Per `remind_mobile_ai.md:40`: "Gateway requires [user_id] for quota/entitlements check."

**Finding:** The local deployment has `entitlements.py` with `check_tour_quota(user_id, total_stops)` called at `tour_orchestrator_service.py:1248`. It uses a `plans` table with quota dimensions (`tours_per_day`, `tour_max_poi`, etc.). This IS the entitlements gate referenced.

**Can it be extended for Subscribed?** Per `SUBSCRIBED_DESIGN.md`: "The existing `plans` table models quota dimensions and is the wrong shape for it. Do not force the new model into those columns; add what is needed alongside and leave `free` working." The gate CAN be extended — add a wallet balance check alongside the quota check, triggered when plan != 'free'. The `cost_ledger` table (this task) provides the data to compute spend-to-date. Extension is LOCAL-61's scope.

---

## Regression suite

**Current tree (LOCAL-60):** 27 passed, 1 error (test_attestation_log_only.py — pre-existing fixture issue)
**Baseline (prepush-baseline):** Same test_attestation_log_only.py error. Shared tests (test_f4_cache_roundtrip.py): 4/4 passed in both.

No new failures introduced.

---

## DB changes

**Table created:** `cost_ledger` — see `migration/sql/005_cost_ledger.sql` for DDL.
- 6 rows inserted during evidence gathering (all for user `local60-fresh-evidence`)
- 3 simulated rows (from previous submission) deleted

---

## Limitations / known gaps

1. **Translation cost is estimated**, not measured from actual response char count. The translation service returns `cache_hit` boolean but not `translated_char_count`. Accuracy improvement deferred.
2. **TTS cost in tour breakdown is 0.0** — TTS happens at the tour-processor level (a separate service that takes the text file and produces audio). Metering TTS cost would require wiring `cost_meter` into `tour_generation_service.py` (the processor). The LLM cost captured here IS the text generation cost which is the dominant component.
3. **News path not wired** — operation type defined, no call site.
4. **`check_cost_ceiling` is never called in the live path** — it was written for S67 but no service imports it. Cross-check was done manually. If LEAD wants it wired, that's a separate change.
5. **Breakdown `search: 0.0`** — No Serper calls happen during service-level generation. Serper is used in `work_story_searcher` which is called only from pilot scripts. Corpus mining fetches web pages via direct HTTP (free). If work_story_searcher becomes part of the generation flow in future, its cost will need to be propagated to the breakdown.
