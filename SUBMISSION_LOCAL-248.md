##### READY FOR REVIEW

## LOCAL-248: Merge storied into subscribed

**Branch:** `kiro/local248-merge-storied-into-subscribed`
**Commit:** `77c7034` (merge of storied @ `5078ac2` into subscribed @ `ccc1c54`)
**Base:** `subscribed`

---

### Conflict Resolution — Per-File Summary

#### Files taken wholesale from storied (3):
- **DECISIONS.md** — storied's authoritative D1-D143 record.
- **ANSWERS.md** — storied's version.
- **tests/style_validator_detector.py** — storied's dynamic export shim (D135).

#### Real merges (4):

| File | Storied contributed | Subscribed contributed |
|------|--------------------|-----------------------|
| **generate_tour_text.py** | Model-aware `_tour_llm_cost()` wrapper (LOCAL-194/197: costs at actual model rate, not hardcoded gpt-3.5-turbo), corpus coverage gate (LOCAL-198/209/203: EMPTY/VENUE_ONLY/CREATOR_ONLY verdicts), prolog gating (LOCAL-244: R9+R10+subject routine on prolog), orientation gating (LOCAL-246: R9+R10 on orientation paragraphs) | The `_llm_cost` from `cost_rates` is still called *through* `_tour_llm_cost`, so billing metering is preserved. Subscribed's cost_rates module remains the pricing authority. |
| **tour_orchestrator_service.py** | `link_stop_metrics_to_tour()` function (LOCAL-128: backfills tour_id on stop_metrics rows), stop_metrics linkage call after `store_audio_tour` | Wallet API blueprint registration (LOCAL-68/154), compensating service_credit on storage failure (LOCAL-156), D47 charge-retained-on-reuse logic (LOCAL-172), translation wallet charging (LOCAL-169/D45: PPU charge + unlimited cost recording) |
| **cost_meter.py** | Explanatory comment above `news_cache_hit` entry (documenting D58 separation between storied/subscribed metering) | All Wallet-facing code, `VALID_OPERATION_TYPES` set, DB-backed ledger writes — unchanged |
| **tests/test_local197_real_model_pricing.py** | `pytest` import and `_subscribed_only = pytest.mark.skipif(...)` guard decorating `test_wallet_ledger_unchanged` and `test_projected_costs_unchanged` — makes the file runnable on both branches | The wallet/projected_costs test bodies themselves (unchanged) |

---

### Verification Evidence

#### 1. Storied's style gates fire

```
$ python3 -c "from style_validator_detector import validate_paragraph; print(validate_paragraph(\"Standing at the Cap d'Antibes Coastal Path, you are enveloped in the beauty of the French Riviera.\"))"

{'is_navigation': False, 'findings': [{'rule_id': 'R4_PRESCRIBED_FEELING', 'severity': 'error', 'sentence': "Standing at the Cap d'Antibes Coastal Path, you are enveloped in the beauty of the French Riviera.", 'suggestion': 'Rewrite as objective description. Remove "you" + feeling verb; describe what IS, not what the listener should feel.'}], 'rules_violated': {'R4_PRESCRIBED_FEELING'}}
```

```
$ python3 -c "from style_validator_detector import check_r10_unfulfilled_promise; print(check_r10_unfulfilled_promise(['The coastline holds stories that deepen the allure of the French Riviera.', 'The path is popular.'], index=0))"

{'rule_id': 'R10_UNFULFILLED_PROMISE', 'severity': 'error', 'sentence': 'The coastline holds stories that deepen the allure of the French Riviera.', 'suggestion': 'This sentence names a subject (story, tale, history, legacy) without delivering a concrete, on-topic payload (date, name, fact) in itself or the next 2 sentences. Either follow up with specifics or delete the sentence.', 'lookahead': 2}
```

#### 2. R10 reachable via tests shim

```
$ python3 -c "from tests.style_validator_detector import check_r10_unfulfilled_promise; print(check_r10_unfulfilled_promise)"

<function check_r10_unfulfilled_promise at 0x109f21700>
```

#### 3. Subscribed billing dry run (LOCAL-225)

```
$ python3 -m pytest tests/billing_dry_run/ -v

14 passed in 0.71s

Tests:
  test_cache_hit_charging PASSED
  test_get_user_plan_free PASSED
  test_get_user_plan_ppu PASSED
  test_get_subscription_tier_active PASSED
  test_get_tours_used_today PASSED
  test_get_news_used_period PASSED
  test_check_tour_quota_ppu_integration PASSED
  test_check_tour_quota_ppu_overdraft_breach PASSED
  test_full_lifecycle PASSED
  test_sanity_ceiling_rejects_inflated_cost PASSED
  test_free_tier_truncation PASSED
  test_subscribed_tier_truncation PASSED
  test_under_limit_not_truncated PASSED
  test_unlimited_tier_uses_subscribed_limit PASSED
```

#### 4. Subscribed service-layer dry run (LOCAL-226)

```
$ python3 -m pytest tests/service_layer_dry_run/ -v

34 passed, 1 warning in 0.63s

Tests include: wallet routes (GET/POST), entitlements gate, cache-hit charge,
truncation e2e, falsification guard, tier change — all passed.
```

#### 5. Subscribed-only files still present

```
$ git diff --stat storied HEAD -- wallet_api.py wallet_ledger.py voice_control_service.py user-tracking/

 user-tracking/app_fixed_final.py | 363 +++++++++++++++++++++
 user-tracking/app_with_routes.py |  31 ++
 user-tracking/routes.py          |  31 ++
 voice_control_service.py         |  97 ++++++
 wallet_api.py                    | 501 ++++++++++++++++++++++++++++
 wallet_ledger.py                 | 687 +++++++++++++++++++++++++++++++++++++++
 6 files changed, 1710 insertions(+)
```

---

### Acceptance Criteria Checklist

| Criterion | Status |
|-----------|--------|
| `git rev-list --count HEAD..storied` = 0 | ✓ (0) |
| All 7 conflicts resolved per rules | ✓ |
| Four real-merge files documented | ✓ (table above) |
| 5 verification rows with real output | ✓ (all 5 passed) |
| Subscribed-only files present | ✓ |
| `git status --short` clean | ✓ |
| No container rebuilt | ✓ |
| Nothing pushed | ✓ |

---

### Limitations

None. All five verifications ran and passed. Database was available on localhost:5433.
