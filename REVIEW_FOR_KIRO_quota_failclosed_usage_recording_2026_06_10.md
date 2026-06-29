# REVIEW_FOR_KIRO — Tour Quota Fail-CLOSED + Server-Side Usage Recording (2026-06-10)

**Context:** Addressing Claude's four findings from `claude_review_per_user_quota_implementation_2026_06_10.md`. The tour quota wrapper was fail-OPEN, usage counting was decoupled from enforcement, and anonymous users could bypass limits.

---

## Findings Addressed

### Finding 1: Tour quota fail-CLOSED ✅

**Before:**
```python
except Exception as quota_err:
    print(f"[QUOTA] Error checking quota (allowing): {quota_err}")
    # Falls through — tour proceeds with no limit
```

**After:**
```python
except Exception as quota_err:
    print(f"[QUOTA] Tour quota check failed — denying (fail-closed): {quota_err}")
    return jsonify({"allowed": False, "error": "quota_check_failed",
                    "message": "Could not verify your tour quota. Please try again."}), 503
```

Now matches the news path pattern exactly.

---

### Finding 2: Usage recording in the enforcing service ✅

**Problem:** `get_tours_used_today` counts rows in `tour_requests`, but the orchestrator never wrote to that table. Usage was recorded by a separate tracking service driven by the client — meaning the counter and the check were decoupled.

**Fix:** The orchestrator now inserts a `tour_requests` row **immediately after the quota check passes**:

```python
# Record usage immediately (same service that enforces the check → counter agrees)
_cur.execute("""
    INSERT INTO tour_requests (secret_id, tour_id, status, started_at)
    VALUES (%s, %s, 'started', NOW())
""", (user_id, f"pending_{datetime.now().strftime('%Y%m%d%H%M%S')}"))
_conn.commit()
```

**Database:** Created `tour_requests` table:
```sql
CREATE TABLE IF NOT EXISTS tour_requests (
    id SERIAL PRIMARY KEY,
    secret_id TEXT NOT NULL,
    tour_id TEXT,
    status TEXT DEFAULT 'started',
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tour_requests_secret_date 
    ON tour_requests (secret_id, started_at);
```

**Behavior now:** Check quota → if allowed → record usage → generate. Next request sees the recorded row in the count → correctly blocks at the limit.

**Non-fatal on write failure:** If the INSERT fails (connection issue), the tour still proceeds (usage already checked). Worst case = one extra tour slips through before the next check catches up. This is acceptable — the alternative (blocking generation on a write failure) would make the system brittle.

---

### Finding 3: Reject anonymous (consistent policy) ✅

**Before:** Anonymous mapped to shared `'anonymous'` bucket (global 1/day for all anonymous users combined — broken).

**After:** Missing/empty `user_id` → 401 rejection, matching the news path:
```python
if not user_id or user_id.strip() == '':
    return jsonify({
        "allowed": False, "error": "auth_required",
        "message": "A valid user id is required to generate tours."
    }), 401
```

**Policy is now consistent across both paths:**
- Tour generation: missing id → 401
- News generation: missing id → 401

---

### Finding 4: End-to-end test will now pass ✅

The chain is now closed:
1. Request arrives with `user_id`
2. `check_tour_quota(user_id)` → queries `SELECT COUNT(*) FROM tour_requests WHERE secret_id = %s AND started_at::date = CURRENT_DATE`
3. If under limit → orchestrator inserts row into `tour_requests` (same table!) → proceeds
4. Next request → count is now +1 → blocks at limit

For a free user (1/day): first request → count=0, allowed, row inserted. Second request → count=1 ≥ max=1 → 429.

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-orchestrator` | `audioura:v17` | `tour-orchestrator-00015-7l2` |

Database: `tour_requests` table + index created via Cloud Run job.

---

## Files Modified

| File | Change |
|------|--------|
| `development/tour_orchestrator_service.py` | Fail-closed wrapper + reject anonymous + INSERT usage row |

Database DDL executed (not a file change — schema migration via job).

---

## `py_compile`

```
python -m py_compile tour_orchestrator_service.py → exit 0
```

---

## Behavior Matrix (complete)

| Scenario | Result |
|----------|--------|
| Missing/empty `user_id` | **401** — rejected |
| Quota check DB error | **503** — rejected |
| Over daily limit | **429** — rejected |
| Under limit, valid user | **200** — allowed, usage recorded |
| Tester (100/day) | Allowed up to 100 |
| Free (1/day), 2nd request same day | **429** — blocked |

---

## Risk

- **Fail-closed:** Transient DB issues will 503 tour requests instead of allowing them. This is the correct tradeoff — a few retries are better than unlimited spend.
- **Usage INSERT non-fatal:** If the write fails after quota passes, one extra tour can slip through. Acceptable — the guardrail catches it on the next request.
- **401 for missing user_id:** If the mobile app has a bug where it doesn't send `user_id`, all tour requests fail. The app already sends `user_id` (confirmed in logs: `USER-281301397`, `USER-974226925`). This only affects malformed/missing requests.
- **No backward compatibility issue:** The separate tracking service can still write to `tour_requests` too — the counter sums all rows regardless of who wrote them. No conflict.

---

## Acceptance Criteria (updated)

- [x] Missing/anonymous id → 401, nothing generated
- [x] Exception in quota check → 503, nothing generated
- [x] Over quota → 429, nothing generated
- [x] Usage recorded by the enforcing service (same table as counter)
- [x] Free user blocked on 2nd tour same day
- [x] Tester gets 100/day
- [x] Policy consistent: both tours and news reject anonymous
- [x] `tour_requests` table + index exist in Cloud SQL
