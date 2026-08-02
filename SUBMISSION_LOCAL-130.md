##### READY FOR REVIEW

# LOCAL-130: Fix the referral abuse guard — exercises behaviour, not source

**Branch:** `kiro/local130-fix-abuse-guard`  
**Commit:** `77a816642cde81d1c49622e45aaeb9c8f2c478d7`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

The guard was permanently red (hardcoded row count 88 vs actual 94) and blind
to disabled controls (substring/AST checks pass when a call exists even behind
`if False:`). Both defects are fixed:

1. **Hardcoded row count → before/after invariant.** Never asserts an absolute
   value; records count at start, asserts unchanged at end.
2. **Source-level inspection → behavioural HTTP tests.** Spins up a host-side
   Flask instance with the real `referral_endpoints.py` and `referral_engine.py`,
   pointed at the live Postgres DB. Exercises each control via actual HTTP
   requests and asserts the correct rejection status code.

The AST checks are retained as a fast first-line defence but are no longer the
only evidence. A disabled limiter (`if False and _check_rate_limit(...)`) will
now fail on the HTTP assertion even if the AST still finds a `Call` node.

---

## Changes

| File | Lines | What |
|------|-------|------|
| `tests/test_local115_referral_abuse_controls_guard.py` | +233 −141 | Full rewrite: behavioural tests, dynamic row counts |

---

## Evidence

### Guard exits 0 with all three controls in place

```
PART 1: AST Guard — abuse control code structurally present
  PASS: referral_endpoints.py exists
  PASS: referral_engine.py exists
  PASS: Self-referral: equality check in AST
  PASS: Rate limiter: _check_rate_limit() called in ≥2 routes
  PASS: Duplicate redemption: 409 + 'already_redeemed' in redeem_referral
  PASS: Engine: catches UniqueViolation → 'duplicate'

PART 2: Behavioural Guard — exercise controls via live HTTP
  PASS: Setup: create referral returns 200
  PASS: Self-referral returns 403
  PASS: Self-referral error is 'self_referral'
  PASS: First redeem returns 200
  PASS: Duplicate redeem returns 409 (not 500)
  PASS: Duplicate error is 'already_redeemed'
  PASS: Rate limit fires within 8 requests (limit=5)
  PASS: Rate limit error is 'rate_limit_exceeded'
  PASS: Rate limit includes retry_after_seconds
  PASS: Legitimate redeem returns 200
  PASS: Legitimate redeem has redeemed=true

PART 3: Database Guard — UNIQUE constraint + row-count invariant
  PASS: UNIQUE constraint 'uq_referral_redemptions_code_user' exists
  PASS: Constraint covers (referral_code, new_user_id)
  INFO: audio_tours row count = 94
  INFO: stop_metrics row count = 1002
  PASS: audio_tours row count unchanged across test
  PASS: stop_metrics row count unchanged across test

Results: 21 PASS, 0 FAIL, 0 SKIP
ALL ASSERTIONS PASSED — referral abuse controls are working
EXIT=0
```

### Break/Restore Cycle 1: Self-referral prevention

**BREAK** — `if new_user_id == referrer_user_id:` → `if False:`
```
  FAIL: Self-referral: equality check in AST — No live AST comparison of new_user_id == referrer_user_id found
  FAIL: Self-referral returns 403 — Got 200: {"redeemed":true,"referrer_user_id":"guard_self_1785688650482"}
Results: 18 PASS, 2 FAIL, 0 SKIP
EXIT=1
```

**RESTORE** — reverted:
```
Results: 21 PASS, 0 FAIL, 0 SKIP
ALL ASSERTIONS PASSED — referral abuse controls are working
EXIT=0
```

### Break/Restore Cycle 2: Duplicate redemption

**BREAK** — `return "duplicate"` → `return "ok_fake"` in referral_engine.py
```
  FAIL: Engine: catches UniqueViolation → 'duplicate' — Expected except handler with UniqueViolation returning 'duplicate'
  FAIL: Duplicate redeem returns 409 (not 500) — Got 200: {"redeemed":true,"referrer_user_id":"guard_dup_creator_1785688658432"}
Results: 18 PASS, 2 FAIL, 0 SKIP
EXIT=1
```

**RESTORE** — reverted:
```
Results: 21 PASS, 0 FAIL, 0 SKIP
EXIT=0
```

### Break/Restore Cycle 3: Rate limiting

**BREAK** — `if not _check_rate_limit(rate_key):` → `if False and not _check_rate_limit(rate_key):`
```
  FAIL: Rate limit fires within 8 requests (limit=5) — All requests returned 200 — rate limiting not active
Results: 18 PASS, 1 FAIL, 0 SKIP
EXIT=1
```

**RESTORE** — reverted:
```
Results: 21 PASS, 0 FAIL, 0 SKIP
ALL ASSERTIONS PASSED — referral abuse controls are working
EXIT=0
```

### No hardcoded row counts

```
$ grep -n "== 88\|== 94\|== 1002" tests/test_local115_referral_abuse_controls_guard.py
(no output — NONE FOUND)
```

### No substring identifier checks

```
$ grep -n '"_check_rate_limit" in' tests/test_local115_referral_abuse_controls_guard.py
(no output — NONE FOUND)
```

### Row counts

```
audio_tours row count = 94
stop_metrics row count = 1002
```

### git status --short

```
(clean — no output)
```

---

## Approach: Host-side Flask instead of Docker

Docker builds are hung (constraint: no Docker builds). The test starts a
temporary Flask process on a random free port with:
- `referral_endpoints.py` loaded directly (the file under test)
- `referral_engine.py` as its dependency
- Connected to the existing Postgres on localhost:5433
- Rate limit set to 5 (lower than prod's 10) for faster test cycles

The launcher script is ephemeral — created at test start, deleted at end,
never committed. The test is self-contained: `python3 tests/test_local115_referral_abuse_controls_guard.py`.

---

## Limitations

1. **No container-level verification.** The Docker service on port 5100 is
   unreachable (no matching containers, Docker builds hung). The test uses
   a host-side Flask instance with the same code. If the containerized
   service diverges from the source files (e.g., stale image), this test
   would not catch that — but since Docker builds are blocked, the container
   cannot be rebuilt anyway.

2. **Rate limit window interaction.** The test uses unique user IDs per run
   (timestamped) to avoid cross-run rate limit state. If run twice within
   60s with the same timestamp (impossible in practice due to ms precision),
   the second run could see stale rate limit entries from the first.

3. **Referral redemption table accumulates test data.** Each run creates 3-4
   referral codes and 2 redemptions. These are isolated by unique timestamped
   user IDs and do not affect other tests or production data.
