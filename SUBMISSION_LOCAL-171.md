##### READY FOR REVIEW

# LOCAL-171: Make news billing able to run

**Branch:** `kiro/local171-news-billing-wiring`  
**Commit:** `c6bd6e7`  
**Commits ahead of subscribed:** 2  
**Task:** Add missing `projected_costs.py` to `Dockerfile.news-orchestrator`

---

## The problem

The news-orchestrator container cannot execute its billing code. The running
container holds only 3 Python files:

```
/app/build_manifest.py  /app/entitlements.py  /app/news_orchestrator_service.py
```

The Dockerfile (after round 1) had 9 modules COPY'd — but `projected_costs.py`
was missing. That module is imported inside `entitlements._check_ppu_balance()`
at function scope (not top-level), so the container starts cleanly but fails
at runtime when the overdraft floor check fires.

---

## Import closure (ast.walk — descends into function bodies)

Command used:
```python
for node in ast.walk(tree):  # walks ALL nodes including inside functions
    if isinstance(node, ast.ImportFrom): ...
```

### Result: 9 modules required

| Module | In Dockerfile (before) | Status |
|--------|----------------------|--------|
| news_orchestrator_service | ✅ COPY'd | entrypoint |
| news_cache_layer1 | ✅ COPY'd | OK |
| cost_meter | ✅ COPY'd | OK |
| cost_rates | ✅ COPY'd | OK |
| entitlements | ✅ COPY'd | OK |
| payment_provider | ✅ COPY'd | OK |
| pricing | ✅ COPY'd | OK |
| wallet_ledger | ✅ COPY'd | OK |
| **projected_costs** | ❌ **MISSING** | **Added** |

Plus `build_manifest.py` (utility, not in import closure but needed for build step).

### Import chain that was broken:

```
news_orchestrator_service.py (line ~98)
  → from entitlements import check_news_quota

entitlements.py → _check_news_quota_paid → _check_ppu_balance (line ~224)
  → from projected_costs import would_breach_floor, get_projected_cost_cents, OVERDRAFT_FLOOR_CENTS
    ^^^ FUNCTION-LEVEL IMPORT — invisible to top-level-only scan
```

---

## Fix

One line added to `Dockerfile.news-orchestrator`:

```dockerfile
COPY projected_costs.py .
```

---

## Verification: billing path resolves within image module set

Every module in the image was scanned with `ast.walk` and every local import
verified to be present in the image set:

```
OK: cost_meter -> cost_rates
OK: entitlements -> payment_provider
OK: entitlements -> projected_costs
OK: entitlements -> wallet_ledger
OK: news_orchestrator_service -> cost_meter
OK: news_orchestrator_service -> cost_rates
OK: news_orchestrator_service -> entitlements
OK: news_orchestrator_service -> news_cache_layer1
OK: news_orchestrator_service -> pricing
OK: news_orchestrator_service -> wallet_ledger
OK: pricing -> cost_rates

✅ ALL local imports resolve within the image module set.
```

### Host-side import proof (billing path end-to-end):

```
Test 1: from entitlements import check_news_quota              ✅ Resolved
Test 2: from projected_costs import would_breach_floor, ...    ✅ Resolved (OVERDRAFT_FLOOR_CENTS = -200)
Test 3: from wallet_ledger import charge, record_unlimited_cost ✅ Resolved
Test 4: from pricing import compute_user_charge                ✅ Resolved
Test 5: from cost_meter import record_operation                ✅ Resolved
Test 6: End-to-end pricing: $0.008264 × 5 = $0.04 (4¢)       ✅ Correct
Test 7: would_breach_floor(100¢, news_generate) = False        ✅
        would_breach_floor(-195¢, news_generate) = True        ✅ D41 floor enforced
```

---

## Docker container uptimes (unchanged — no rebuild/restart)

```
news-orchestrator-1    Up 4 hours
news-generator-1       Up 4 hours
news-processor-1       Up 4 hours
development-postgres-2-1  Up 4 hours
```

### Running container contents (read-only `docker exec ls`):

```
/app/build_manifest.py
/app/entitlements.py
/app/news_orchestrator_service.py
```

Confirms the stale image — only 3 files. The fix requires a rebuild to take effect.

---

## ⚠️ Deployment is pending LEAD

Per D48: this task proposes the fix. LEAD deploys. The container must be
rebuilt (`docker-compose build news-orchestrator`) to pick up the corrected
Dockerfile with all 10 COPY lines.

---

## Per-file changes

| File | Change |
|------|--------|
| `Dockerfile.news-orchestrator` | Added `COPY projected_costs.py .` |
| `SUBMISSION_LOCAL-171.md` | This file |

---

## Limitations

1. **Container is stale** — the running image has only 3 of the 10 required
   modules. A rebuild is needed for ANY billing code to execute, not just
   `projected_costs`. This is a deployment gap, not a code gap.

2. **Host-side verification only** — imports were verified against the repo
   (where all files exist), but the closure analysis confirms the Dockerfile
   COPY set is complete. The negative (no missing module) was proven by
   exhaustive ast.walk over all 10 modules.

3. **No live billing test** — per constraints, no article was generated. The
   billing code was already proven correct in LOCAL-165.

---

## git status --short (final)

```
(empty — clean working tree)
```
