##### READY FOR REVIEW

# LOCAL-114: Wire Referral — POST /referral/create + POST /referral/redeem Now Reachable

**Branch:** `kiro/local114-wire-referral`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01 (bounce fix applied same day)

---

## Summary

`referral_endpoints.py` defines a `referral_bp` Blueprint with `POST /referral/create`
and `POST /referral/redeem`. The blueprint was fully implemented (S52) but never
registered on any service — the entire referral chain (`referral_endpoints.py` →
`referral_engine.py` → `referral_codes`/`referral_redemptions` tables) has been dead
code since creation.

**Both routes are now wired.** Redemption does NOT grant credit, balance, or any
entitlement. It records an attribution row only. There is no fraud surface.
Three missing abuse controls are documented as findings (proposed as a separate task).

---

## Bounce Fix (2026-08-01)

**Problem:** The guard test had Part 3 assertions that could never pass — they
asserted the existence of self-referral prevention, duplicate-redemption guards,
and rate limiting that do not exist and are not in scope. This made the test
permanently red (exit 1), which is the exact pattern LOCAL-102 cleaned up.

**Fix:** Part 3 now **reports** abuse-control status as informational findings
(with `⚠ [MISSING]` / `✓ [PRESENT]` markers and a summary table) but does NOT
assert on them. Parts 1 and 2 remain hard assertions. The test exits 0 when
wiring is correct, exits 1 only when wiring is actually broken.

---

## The Finding — Chain Confirmed Dark

The `referral_codes` and `referral_redemptions` tables exist in the database but
contained **zero rows** before this task — confirming the feature has never executed
in any environment.

| Table | Rows BEFORE | Rows AFTER |
|-------|-------------|------------|
| `referral_codes` | **0** | 2+ (test data) |
| `referral_redemptions` | **0** | 8+ (test data) |
| `audio_tours` | **88** | **88** (unchanged) |

---

## What Redemption Grants

**Nothing.** `record_referral_redemption()` in `referral_engine.py` does exactly two
things:
1. `UPDATE referral_codes SET redemption_count = redemption_count + 1 WHERE code = %s`
2. `INSERT INTO referral_redemptions (referral_code, new_user_id) VALUES (%s, %s)`

There is no reference to `wallet_ledger`, `credit`, `balance`, `entitlements`,
`cost_meter`, or any value-granting function anywhere in the referral chain.
Redemption is purely an attribution/tracking record.

---

## What Stops Abuse — Or Doesn't

| Control | Present? | Impact (today) |
|---------|----------|----------------|
| **API key required** | ✅ PRESENT | Low — gated at transport level |
| **Self-referral prevention** | ❌ MISSING | Low (grants nothing) but pollutes attribution data |
| **Duplicate redemption prevention** | ❌ MISSING | Low (grants nothing) but inflates `redemption_count` |
| **Rate limiting** | ❌ MISSING | Low (grants nothing) but allows data spam |

**Judgement:** These gaps are acceptable NOW because redemption grants no value.
If a future task adds credit/wallet rewards to redemption, these three controls
become mandatory prerequisites. Proposed as a separate task.

---

## Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | +3 lines: import `referral_bp` + `app.register_blueprint(referral_bp)` |
| `referral_endpoints.py` | 1-line fix: removed `str | None` return type (Python 3.9 compat) |
| `tests/test_local114_referral_wiring_guard.py` | New — 3-part guard test; Parts 1+2 assert wiring, Part 3 reports findings |
| `SUBMISSION_LOCAL-114.md` | New — this file |

---

## Acceptance Evidence

### AC1: Table Row Counts (Chain Was Dark)

```
BEFORE wiring (tables existed, zero rows):
  referral_codes: 0 rows
  referral_redemptions: 0 rows
  audio_tours: 88 rows

AFTER round trips:
  referral_codes: 2 rows
  referral_redemptions: 8 rows
  audio_tours: 88 rows (unchanged)
```

### AC2: Before/After Status for Each Referral Route

| Method | Path | Port 5000 (audioura, NOT touched) | Port 5100 (LOCAL-114 stack) |
|--------|------|-----------------------------------|----------------------------|
| POST | /referral/create | **404** | **200** |
| POST | /referral/redeem | **404** | **200** |

### AC3: What Redemption Grants and Abuse Controls

**Grants:** Nothing. Attribution record only.  
**Abuse controls present:** API key gate only.  
**Abuse controls missing:** Self-referral prevention, duplicate redemption guard, rate limiting.  
**Statement:** Redemption grants no value, so gaps are data-quality issues, not security vulnerabilities.

### AC4: Round Trip

```
POST http://localhost:5100/referral/create
Headers: X-API-Key: test-api-key
Body: {"user_id": "local114_bounce_user"}
→ 200 {"referral_code":"I2IJBE","referral_url":"http://localhost:5000/join/I2IJBE"}

POST http://localhost:5100/referral/redeem
Headers: X-API-Key: test-api-key
Body: {"referral_code": "I2IJBE", "new_user_id": "local114_new_user"}
→ 200 {"redeemed":true,"referrer_user_id":"local114_bounce_user"}
```

### AC5: Guard Test — Exit 0 When Wiring Correct

```
$ python3 tests/test_local114_referral_wiring_guard.py
======================================================================
PART 1: AST Guard — referral_bp registration is live code
======================================================================
  PASS: Service file exists
  PASS: import referral_bp present in source
  PASS: register_blueprint(referral_bp) call present
  PASS: AST confirms register_blueprint(referral_bp) is live code
  PASS: referral_endpoints.py exists
  PASS: referral_bp defined in referral_endpoints.py
  PASS: POST /referral/create route defined
  PASS: POST /referral/redeem route defined
  PASS: referral_engine.py exists

======================================================================
PART 2: Live HTTP Guard — POST /referral/create reachable
======================================================================
  PASS: POST /referral/create is NOT 404
  PASS: POST /referral/create returns 200
  PASS: Response contains referral_code
  PASS: referral_code is 6-char
  PASS: Response contains referral_url
  PASS: POST /referral/redeem is NOT 404
  PASS: POST /referral/redeem returns 200
  PASS: Redeem response has redeemed=true
  PASS: Redeem response has referrer_user_id
  PASS: Missing API key returns 401
  PASS: Unknown referral code returns 404

======================================================================
PART 3: Abuse Surface Audit — referral controls inventory (informational)
         These are findings, not assertions. Missing controls do NOT
         cause test failure — they are reported for future task planning.
======================================================================
  ✓ [PRESENT] No wallet_ledger reference in referral chain
  ✓ [PRESENT] No credit/balance grant in referral chain
  ✓ [PRESENT] No cost_meter reference in referral chain
  ⚠ [MISSING] Self-referral guard (referrer != redeemer) — No check prevents a user from redeeming their own referral code
  ⚠ [MISSING] Duplicate redemption guard — Same user can redeem same code multiple times (no UNIQUE constraint)
  ⚠ [MISSING] Rate limiting on referral endpoints — No rate limiting on referral endpoints

  ┌─────────────────────────────────────────────────────────────────┐
  │ ABUSE CONTROL SUMMARY (for future task planning)               │
  ├─────────────────────────┬──────────┬───────────────────────────┤
  │ Control                 │ Status   │ Impact (today)            │
  ├─────────────────────────┼──────────┼───────────────────────────┤
  │ API key gate            │ PRESENT  │ —                         │
  │ Self-referral guard     │ MISSING  │ Low (grants nothing)      │
  │ Duplicate redemption    │ MISSING  │ Low (inflates counter)    │
  │ Rate limiting           │ MISSING  │ Low (data spam only)      │
  └─────────────────────────┴──────────┴───────────────────────────┘

  Proposed follow-up: Add all three controls BEFORE any value
  (credit/wallet) is ever wired to the redeem path.

======================================================================
Results: 20 PASS, 0 FAIL, 6 findings (informational)
ALL ASSERTIONS PASSED — wiring is correct
  (6 Part 3 findings are informational, not regressions)
======================================================================
Exit: 0
```

### AC6: Guard Test — Exit 1 When Registration Removed

```
$ sed 's/^app.register_blueprint(referral_bp)$/# app.register_blueprint(referral_bp)/' generate_tour_text_service.py > tmp && mv tmp generate_tour_text_service.py
$ python3 tests/test_local114_referral_wiring_guard.py
  ...
  FAIL: AST confirms register_blueprint(referral_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string
  ...
Results: 19 PASS, 1 FAIL, 6 findings (informational)
WIRING BROKEN — Parts 1/2 have failures (actual regressions)
======================================================================
Exit: 1
```

### AC7: Row Count Verification

```
audio_tours: 88 (unchanged)
```

### AC8: Why Both Routes Were Wired

Redemption grants nothing — it records `(code, new_user_id, timestamp)` in
`referral_redemptions` and increments a counter. No wallet interaction, no credit
grant, no entitlement change. The referral chain is a tracking system, not a
value-transfer system.

### AC9: Why Redeem Is Safe Without Abuse Controls Today

Both `create` and `redeem` require `X-API-Key` header (`hmac.compare_digest`).
Without the key, both return 401. Self-referral and duplicate redemption can
produce junk attribution rows but cannot mint value, move money, or unlock
features. The controls are worth adding for data quality but are not a security
gate today.

---

## Proposed Follow-Up Task: Abuse Controls

Before referral redemption ever gains credit/wallet integration:

1. **Self-referral guard** — reject if `referrer_user_id == new_user_id`
2. **Duplicate redemption guard** — `UNIQUE(referral_code, new_user_id)` constraint
3. **Rate limiting** — per-IP or per-user rate limit on both endpoints

These are NOT required today but become mandatory before any value is wired.

---

## Limitations

1. **audioura containers not rebuilt** — per constraint. Port 5000 still returns
   404 for referral routes. The subscribed-generator (port 5100) confirms wiring.

2. **Docker Hub unreachable** — used cached `local-114-subscribed-generator` image
   with local code volume-mounted.

3. **GATEWAY_API_KEY as `test-api-key`** — subscribed stack is dev-only.

4. **Python 3.9 compatibility fix** — removed `str | None` type annotation (3.10+).
