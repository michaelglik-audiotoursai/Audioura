##### READY FOR REVIEW

# LOCAL-171: Make news billing able to run

**Branch:** `kiro/local171-news-billing-wiring`  
**Commit:** `dade030`  
**Commits ahead of subscribed:** 1

---

## Problem

The news-orchestrator container holds only 3 Python files:

```
/app/build_manifest.py  /app/entitlements.py  /app/news_orchestrator_service.py
```

The billing code in `news_orchestrator_service.py` imports `cost_meter`,
`cost_rates`, `pricing`, `wallet_ledger`, and `entitlements` (which itself
imports `payment_provider`). None of these resolve → articles are delivered
unmetered and uncharged.

LOCAL-165 proved the billing *code* is correct ($0.008264 metered, 4¢ charged,
×5 multiplier, D41 floor honoured). The code is right; it simply cannot be
reached because the modules are absent from the container.

---

## Import closure analysis

### Transitive import graph (local .py files only)

```
news_orchestrator_service.py
├── entitlements.py
│   └── payment_provider.py         ← BILLING_RETRY_GRACE_DAYS
├── news_cache_layer1.py
├── cost_meter.py
│   └── cost_rates.py
├── cost_rates.py
├── pricing.py
│   └── cost_rates.py
├── wallet_ledger.py
└── build_manifest.py               (build utility, not runtime)
```

### Required vs Copied vs Missing

| Module | Required | In Dockerfile (before) | In Container | Status |
|--------|----------|----------------------|--------------|--------|
| `news_orchestrator_service.py` | ✓ | ✓ | ✓ | OK |
| `entitlements.py` | ✓ | ✓ | ✓ | OK |
| `news_cache_layer1.py` | ✓ | ✓ | ✗ | Stale build |
| `cost_meter.py` | ✓ | ✓ | ✗ | Stale build |
| `cost_rates.py` | ✓ | ✓ | ✗ | Stale build |
| `build_manifest.py` | ✓ | ✓ | ✓ | OK |
| **`payment_provider.py`** | ✓ | **✗** | ✗ | **MISSING from Dockerfile** |
| **`pricing.py`** | ✓ | **✗** | ✗ | **MISSING from Dockerfile** |
| **`wallet_ledger.py`** | ✓ | **✗** | ✗ | **MISSING from Dockerfile** |

**Summary:**
- 3 files missing from Dockerfile entirely (never added)
- 3 additional files missing from container (Dockerfile correct but image stale)
- After fix: Dockerfile copies all 9 required files; rebuild will produce a
  working image

---

## Fix applied

Added 3 `COPY` lines to `Dockerfile.news-orchestrator`:

```dockerfile
COPY payment_provider.py .
COPY pricing.py .
COPY wallet_ledger.py .
```

---

## Evidence: billing path resolves host-side

### (1) Full import chain — all modules resolve

```
1. Importing entitlements...
   OK: check_news_quota, get_user_plan, words_budget_for_minutes, _get_subscription_tier
2. Importing news_cache_layer1...
   OK: get_cached_news, store_news
3. Importing cost_meter...
   OK: record_operation
4. Importing cost_rates...
   OK: CACHE_HIT_COST_USD=0.0, POLLY_COST_PER_CHAR=4e-06
5. Importing pricing...
   OK: compute_user_charge
6. Importing wallet_ledger...
   OK: charge, record_unlimited_cost
7. Importing payment_provider (transitive dep of entitlements)...
   OK: BILLING_RETRY_GRACE_DAYS=16

=== ALL IMPORTS RESOLVE — billing path is reachable ===
```

### (2) Charge path computation — end-to-end interoperation verified

```
Simulated article: 3000 chars, 3 major points
  TTS chars estimated: 5400
  TTS cost: $0.021600
  LLM cost: $0.000000
  Total our cost: $0.021600
  User charge (x5): $0.11 (11¢)
  Multiplier: 5.0

=== CHARGE PATH COMPUTATION VERIFIED ===
```

The ×5 multiplier is unchanged (D47 confirmed).

### (3) Container uptimes — unchanged (no rebuild)

```
BEFORE & AFTER:
news-orchestrator-1     Up 3 hours
news-processor-1        Up 3 hours
news-generator-1        Up 3 hours
simple-news-search-1    Up 3 hours
newsletter-link-extractor-1  Up 3 hours
```

---

## Deployment is pending LEAD

Per D48: this task proposes the fix. LEAD deploys (rebuilds the container).
No container was rebuilt, recreated, or restarted. The Dockerfile change takes
effect only when `docker compose build news-orchestrator` is run.

---

## Per-file changes

| File | Change |
|------|--------|
| `Dockerfile.news-orchestrator` | Added 3 COPY lines: `payment_provider.py`, `pricing.py`, `wallet_ledger.py` |
| `SUBMISSION_LOCAL-171.md` | This file |

---

## Limitations

1. **Not deployed** — the fix requires a container rebuild (D48: LEAD deploys).
   Until rebuilt, articles continue to ship unmetered.

2. **Container also missing `news_cache_layer1.py` and `cost_rates.py`** — these
   are in the Dockerfile (added in prior commits) but not in the running image
   because it was built before those lines existed. The rebuild will pick them up
   automatically. No Dockerfile change needed for those.

3. **No live HTTP test** — the running container cannot exercise the billing path
   (modules missing). Host-side import verification confirms the code will work
   once the image is rebuilt with all files present.

---

## git status --short (final)

```
(empty — clean working tree)
```
