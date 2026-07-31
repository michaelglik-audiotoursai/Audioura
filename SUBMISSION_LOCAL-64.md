##### READY FOR REVIEW

## LOCAL-64: Enforce Michael's $1.30 Cost Ceiling — Fail-Closed

**Commit:** see `git log --oneline -1` (hash changes with each amend)  
**Branch:** `kiro/local64-enforce-cost-ceiling`  
**Base:** `storied` (at `2f7e2fd`)

---

### Bounce fix: The guard no longer silently disables itself

The first submission placed `enforce_cost_ceiling` inside the LOCAL-60 metering
`try`, whose handler was:

```python
except Exception as _meter_err:
    print(f"[LOCAL-60] Cost metering failed (non-fatal): {_meter_err}")
```

If the ceiling raised for any reason (DB unreachable, bad env, import failure),
the abort branch was skipped and the over-budget tour was delivered. A
swallowed exception around a control is the control not existing.

**Now:**
- Metering has its own `try/except` — metering failure IS non-fatal.
- Ceiling enforcement has a **separate** `try/except` that **fails closed**:
  if `enforce_cost_ceiling` cannot run, delivery is aborted, an ERROR is
  logged naming the exception, and the job is marked `cost_ceiling_check_failed`.
- A tour we cannot price is a tour we must not ship.

### Limitation stated plainly

The ceiling check runs AFTER generation completes. By the time it fires, the
API spend has already happened. It prevents *delivery* of an over-budget tour;
it does not prevent the *cost*.

A feasible follow-up: check accumulated cost between stops during generation
and abort early (in-flight budget check). Not built here — would require
threading cost accumulation through the per-stop loop in `generate_tour_text.py`.

---

### Per-file changes

| File | Change |
|------|--------|
| `cost_ceiling_monitor.py` | Dual-threshold (target $0.15 warn, hard limit $1.30 abort), env-configurable, ledger flagging, /health counters |
| `generate_tour_text_service.py` | **Bounce fix:** ceiling enforcement in its own try block, fails closed. Separate from metering. |
| `tour_orchestrator_service.py` | Added `cost_ceiling` stats to /health endpoint |
| `Dockerfile.orchestrator` | Added COPY for `cost_ceiling_monitor.py`, `cost_meter.py`, `cost_rates.py` |
| `.dockerignore` | Added `!cleanup_newsletter_simple.py` exception |
| `check_dockerignore.py` | Verifies every explicit COPY source survives .dockerignore |
| `migration/sql/006_ceiling_breach.sql` | Adds `ceiling_breach VARCHAR(32)` column to `cost_ledger` |
| `tests/test_local64_cost_ceiling.py` | 31 assertions: threshold tests + **two fail-closed proofs** |

---

### Evidence — Critical acceptance criterion: fail-closed proof

#### Ceiling check raises → tour NOT delivered

```
test_fail_closed_on_ceiling_check_exception:
  enforce_cost_ceiling monkeypatched to raise RuntimeError("Simulated: DB connection refused")
  PASS: delivery aborted when ceiling raises
  PASS: error_type is cost_ceiling_check_failed
  PASS: error message includes exception detail
```

#### Metering succeeds, ceiling explodes → tour still NOT delivered

```
test_fail_closed_metering_ok_ceiling_explodes:
  cost_meter.record_operation succeeds normally
  enforce_cost_ceiling raises ConnectionError("postgres-2: Connection refused")
  PASS: delivery aborted on ceiling failure (metering OK)
  PASS: error_type is ceiling_check_failed
```

This proves the two try blocks are separated: metering success does not
protect a broken ceiling from aborting.

---

### Evidence — Three threshold cases

#### 1. Under target (passes silently) — cost $0.069 < target $0.15

```
[COST_CEILING] COST OK: $0.0690 <= target $0.1500
  PASS: abort is False
  PASS: warn is False
  PASS: breach_level is None
  PASS: message contains COST OK
```

#### 2. Between target and hard limit (WARN) — cost $0.50

```
[COST_CEILING] COST WARNING: $0.5000 exceeds target $0.1500 (hard limit $1.3000, category=walking)
  PASS: abort is False
  PASS: warn is True
  PASS: breach_level is target_exceeded
  PASS: message contains WARNING
```

#### 3. Over hard limit (ABORT) — cost $1.50 > $1.30

```
[COST_CEILING] COST HARD LIMIT EXCEEDED: $1.5000 > $1.3000 — ABORTING tour delivery (category=museum, user=test-user). Michael's standing instruction: stop at $1.30.
  PASS: abort is True
  PASS: breach_level is hard_limit_exceeded
  PASS: message contains ABORT
  PASS: message mentions $1.30
```

#### 4. Forced hard-limit abort with lowered config

```
COST_HARD_LIMIT_USD=0.10
[COST_CEILING] COST HARD LIMIT EXCEEDED: $0.1200 > $0.1000 — ABORTING tour delivery
  PASS: abort with lowered hard limit
  PASS: hard_limit is 0.10
```

---

### Evidence — Ledger flagging

```
  PASS: ledger flagged on target exceeded
  PASS: breach_level param is target_exceeded
```

---

### Evidence — .dockerignore checker

```
Dockerfile.background-article-processor       PASS
Dockerfile.cloudrun                           PASS
Dockerfile.generator                          PASS
Dockerfile.local22                            PASS
Dockerfile.modernized                         PASS
Dockerfile.news-generator                     PASS
Dockerfile.news-orchestrator                  PASS
Dockerfile.news-processor                     PASS
Dockerfile.newsletter-browser                 PASS  (was FAIL before fix)
Dockerfile.newsletter-link-extractor          PASS
Dockerfile.newsletter-processor               PASS
Dockerfile.orchestrator                       PASS
Dockerfile.polly-tts                          PASS
Dockerfile.simple-news-search                 PASS
Dockerfile.testing                            PASS
Dockerfile.tour-id-resolution                 PASS
Dockerfile.tour-processor                     PASS
Dockerfile.tour-worker                        PASS
Dockerfile.treats                             PASS
Dockerfile.voice-nlp                          PASS

Real exclusion found and fixed:
  Dockerfile.newsletter-browser COPY cleanup_newsletter_simple.py
  was excluded by: cleanup_*.py
  Fix: added !cleanup_newsletter_simple.py exception to .dockerignore
```

---

### Evidence — Full test suite

```
LOCAL-60 cost metering:  8/8 PASSED
LOCAL-64 cost ceiling:   31/31 PASSED (includes 2 fail-closed proofs)
.dockerignore checker:   ALL CLEAR (20 PASS, 9 SKIP sub-directory)
```

Measured baseline: $0.0633/tour — under both $0.15 target and $1.30 hard limit.

---

### Design notes

1. **Ceiling in `generate_tour_text_service.py`** — the generator is where
   `_LAST_GENERATION_COST` exists and where the abort can prevent delivery.
   The orchestrator calls the generator over HTTP; it never sees LLM cost
   breakdown.

2. **Both thresholds env-configurable** (`COST_TARGET_USD`, `COST_HARD_LIMIT_USD`)
   — retuneable without redeploy.

3. **Why fail-closed is the right default:** Michael's instruction is
   "stop at $1.30". A control that can be bypassed by infrastructure failure
   is not a control. If the ceiling check cannot run, we do not know whether
   the tour is under $1.30, so we must not ship it. If this causes false
   rejections (e.g., DB flap during a cache-hit tour that cost $0.00), the
   operational fix is to fix the DB, not to deliver unpriced tours.
