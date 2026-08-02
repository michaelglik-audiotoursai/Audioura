##### READY FOR REVIEW

# LOCAL-115: Referral Abuse Controls — Self-Referral, Duplicate, Rate Limit

**Branch:** `kiro/local115-referral-abuse-controls`
**Agent:** Mac Mini Kiro
**Date:** 2026-08-01
**Commit:** `b4cc7d1`

---

## Summary

LOCAL-114 wired `POST /referral/create` and `POST /referral/redeem`. Its own
audit identified three missing abuse controls and rated them low-impact because
redemption grants nothing today. This task closes all three gaps while the
stakes are zero — before anyone wires wallet credit to the redeem path.

Redemption still grants **nothing**. No wallet, credit, balance, or entitlement
logic was added or touched.

---

## Per-File Changes

| File | Change |
|------|--------|
| `referral_endpoints.py` | +self-referral guard (403), +rate limiter (429), +duplicate handling (409) |
| `referral_engine.py` | `record_referral_redemption` returns `"duplicate"` on `UniqueViolation` instead of raising |
| `migration/sql/009_referral_abuse_controls.sql` | `ALTER TABLE referral_redemptions ADD CONSTRAINT uq_referral_redemptions_code_user UNIQUE (referral_code, new_user_id)` |
| `tests/test_local115_referral_abuse_controls_guard.py` | New — 24-assertion guard test (3 parts: AST, live HTTP, DB constraint) |
| `tests/test_local114_referral_wiring_guard.py` | Updated to use unique IDs per run (avoids UNIQUE constraint collision) |
| `docker-compose-local115.yml` | Test compose: cached image + volume mounts for LOCAL-115 files |

---

## Acceptance Evidence

### AC1: Self-referral attempt rejected

```
POST http://localhost:5100/referral/redeem
Headers: X-API-Key: test-api-key
Body: {"referral_code": "F08PP7", "new_user_id": "local115_alice"}
→ 403 {"error": "self_referral", "message": "You cannot redeem your own referral code."}
```

Alice created code F08PP7 and tried to redeem it herself — rejected with 403.

### AC2: Duplicate redemption — graceful 409 (not 500)

```
First redeem (bob):
POST http://localhost:5100/referral/redeem
Body: {"referral_code": "F08PP7", "new_user_id": "local115_bob"}
→ 200 {"redeemed": true, "referrer_user_id": "local115_alice"}

Second redeem (bob, same code):
POST http://localhost:5100/referral/redeem
Body: {"referral_code": "F08PP7", "new_user_id": "local115_bob"}
→ 409 {"error": "already_redeemed", "message": "You have already redeemed this referral code."}
```

UNIQUE constraint fires, engine returns `"duplicate"`, endpoint returns clean 409.

### AC3: Rate limit fires

```
Requests #1–#10 → 200 (within window)
Request #11 → 429 {"error": "rate_limit_exceeded", "message": "Too many requests. Please try again later.", "retry_after_seconds": 60}
```

In-process sliding window: 10 requests per 60 seconds per user. Fires on both `/referral/create` and `/referral/redeem`.

### AC4: Legitimate referral still works end-to-end

```
POST /referral/create {"user_id": "local115_alice"}
→ 200 {"referral_code": "F08PP7", "referral_url": "http://localhost:5000/join/F08PP7"}

POST /referral/redeem {"referral_code": "F08PP7", "new_user_id": "local115_bob"}
→ 200 {"redeemed": true, "referrer_user_id": "local115_alice"}

Attribution row confirmed in referral_redemptions:
  ('F08PP7', 'local115_bob', '2026-08-01 22:43:18.408246')
```

### AC5: Row counts before and after

| Table | BEFORE (baseline) | AFTER (test runs) |
|-------|-------------------|-------------------|
| `referral_codes` | 3 | 15 (test data from guard runs) |
| `referral_redemptions` | 3 | 10 (test data from guard runs) |
| `audio_tours` | **88** | **88** (unchanged) |

### AC6: Guard test exits 0 when controls work

```
$ python3 tests/test_local115_referral_abuse_controls_guard.py
PART 1: AST Guard — abuse controls present in referral_endpoints.py
  PASS: referral_endpoints.py exists
  PASS: referral_engine.py exists
  PASS: Self-referral guard present (new_user_id == referrer_user_id check)
  PASS: Self-referral returns 403 with error code 'self_referral'
  PASS: Rate limiter function called in endpoints
  PASS: Rate limit returns 429 with error code 'rate_limit_exceeded'
  PASS: Duplicate redemption returns 409
  PASS: Duplicate response has 'already_redeemed' error code
  PASS: Engine catches UniqueViolation and returns 'duplicate'

PART 2: Live HTTP Guard — abuse controls respond correctly
  PASS: Setup: create referral returns 200
  PASS: Setup: referral_code returned
  PASS: Legitimate redeem returns 200
  PASS: Redeem has redeemed=true
  PASS: Redeem returns correct referrer_user_id
  PASS: Self-referral returns 403
  PASS: Self-referral error is 'self_referral'
  PASS: Duplicate redeem returns 409 (not 500)
  PASS: Duplicate error is 'already_redeemed'
  PASS: Rate limit fires within 12 requests (limit=10)
  PASS: Rate limit error is 'rate_limit_exceeded'
  PASS: Rate limit includes retry_after_seconds

PART 3: Database Guard — UNIQUE constraint on referral_redemptions
  PASS: UNIQUE constraint 'uq_referral_redemptions_code_user' exists
  PASS: Constraint covers (referral_code, new_user_id)
  PASS: audio_tours row count unchanged (88)

Results: 24 PASS, 0 FAIL
ALL ASSERTIONS PASSED — referral abuse controls are working
Exit: 0
```

### AC7: Guard test exits 1 when a control is removed

```
(Self-referral guard disabled by replacing comparison with `if False:`)

PART 1: AST Guard — abuse controls present in referral_endpoints.py
  FAIL: Self-referral guard present (new_user_id == referrer_user_id check) — No self-referral comparison found in source

Results: 23 PASS, 1 FAIL
ABUSE CONTROLS BROKEN — one or more controls missing or non-functional
Exit: 1
```

### AC8: Backfill safety — duplicate check before constraint

```
Before applying UNIQUE constraint:
  SELECT referral_code, new_user_id, COUNT(*)
  FROM referral_redemptions
  GROUP BY referral_code, new_user_id
  HAVING COUNT(*) > 1;

Result: 1 duplicate pair found ('FZ6MV0', 'guard_new_user', 7)
Source: LOCAL-114 guard test residue (test data, not real users)
Action: Deduped (kept earliest row, deleted 6 extras)
Post-dedup: 0 duplicates — constraint applied successfully
```

### AC9: LOCAL-114 test still passes

```
$ python3 tests/test_local114_referral_wiring_guard.py
Results: 20 PASS, 0 FAIL, 6 findings (informational)
ALL ASSERTIONS PASSED — wiring is correct
Exit: 0
```

---

## Design Decisions

### Self-referral identity

"Same user" = same `user_id` / `secret_id` string. This is the only stable
identity in the `users` table. A device reinstall generates a new `secret_id`,
so the same physical person could bypass this check by reinstalling. The guard
catches the trivial case (same string) — airtight prevention would require
email/phone verification which doesn't exist in this system.

### Rate limiting approach

In-process sliding window (Python `dict` + `threading.Lock`). Configurable via
environment variables `REFERRAL_RATE_LIMIT_MAX` (default 10) and
`REFERRAL_RATE_LIMIT_WINDOW` (default 60s). Resets on container restart.

No Redis added — task explicitly said "simple and in-process."

### Duplicate handling architecture

Two layers of defense:
1. **Database UNIQUE constraint** — authoritative, survives any code bug
2. **Application-level handling** — catches `psycopg2.errors.UniqueViolation`,
   returns `"duplicate"` to the endpoint, which responds with a clean 409

The constraint is the real guard. The application layer exists to produce a
descriptive error message instead of a raw 500.

---

## Limitations

1. **Self-referral is identity-string-only.** A device reinstall produces a new
   `secret_id`, allowing the same person to bypass the check. No stronger
   identity (email, phone) exists in this system today.
2. **Rate limiter is in-process.** Resets on container restart. Multiple
   replicas would each have independent counters (no shared state). Acceptable
   for current single-container deployment.
3. **Rate limiter uses wall clock.** Under heavy load with clock skew this is
   imprecise. Acceptable for the current use case.
4. **Docker Hub unreachable.** Used cached `local-114-subscribed-generator`
   image with volume mounts to overlay updated files.
5. **audioura containers untouched** — per constraint. Production routes remain
   at port 5000 with original (pre-LOCAL-115) code.
6. **Test data left in tables.** Guard test runs accumulate rows in
   `referral_codes` and `referral_redemptions`. These are clearly prefixed
   (`guard115_*`, `local115_*`) and do not affect production behavior.
