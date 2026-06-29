# REVIEW_FOR_KIRO — Open Quota Items: Verification Results (2026-06-10)

**Context:** Executing Claude's punch-list from `claude_review_open_quota_remediation_for_kiro_2026_06_10.md`. Part A (code fixes) was completed in v18. Part B (verification) follows.

---

## Part A — Code Fixes (all completed in v18)

| Item | Status | Implementation |
|------|--------|----------------|
| A1: Double-counting | ✅ Fixed | `source` column; counter filters `source='orchestrator'` |
| A2: Failed tours consume quota | ✅ Fixed | Rollback DELETE on generation failure |
| A3: `tour_id` collisions | ✅ Fixed | `job_id` (UUID) generated first, used as `tour_id` |

Deployed: `tour-orchestrator-00016-bkv` on `audioura:v18`.

---

## Part B — Verification Results

### B5: Plan values in prod ✅

```
plan_id    tours/day  news/period  period   news_max_min
---------- ---------- ------------ -------- ------------
free       1          10           week     10
paid       10         50           week     30
tester     100        100          week     30
```

Test devices confirmed on `tester` plan:
- `USER-281301397` (Android) → tester
- `USER-974226925` (iPhone) → tester

### T1 (News anonymous → 401) ✅

```
POST /generate-news {"article_text":"hello"} + API key, no secret_id → 401
```

### Tour anonymous → 401 ✅

```
POST /generate-complete-tour {"location":"test","tour_type":"walking","user_id":""} + API key → 401
```

### Tour allow-path (B3 equivalent) ✅

```
POST /generate-complete-tour {"location":"test park Boston","tour_type":"walking","total_stops":1,"user_id":"USER-281301397"} + API key
→ 200 {"job_id":"aafb6575-1890-4490-b7fa-d9791c7e6da0","language":"en","status":"queued"}
```

Quota gate passed, generation started. Confirms the fix doesn't over-deny.

### T2 (News over-quota → 429) ✅ (from earlier session)

Seeded 1 usage row for `ITEST-NEWS-QUOTA` (limit=1), second request → 429 with full quota response.

---

## Remaining B items (deferred — require special setup)

| Item | Status | Reason |
|------|--------|--------|
| B1: News DB-down → 503 | ⬜ Deferred | Requires deploying a throwaway revision with broken DB_HOST |
| B2: News truncation (T5) | ⬜ Deferred | Heavy (costs OpenAI + Polly); run locally pre-launch |
| B4: Tour quota integration test | ⬜ Deferred | Should mirror news test; write after all fixes stable |

These are pre-launch checklist items, not blockers for the current code review.

---

## Definition of Done Status

- [x] One `tour_requests` row per tour (no double-count) — `source` column implemented
- [x] Tester plan values: 100 tours/day confirmed in DB
- [x] Failed tour rolls back usage row (code verified)
- [x] `tour_id == job_id` (UUID, unique, correlated)
- [x] News T1 (anonymous → 401): PASS
- [x] News T2 (over-quota → 429): PASS
- [x] Tour anonymous → 401: PASS
- [x] Tour allow-path → 200 (queued): PASS
- [x] Real plan values confirmed (B5): PASS
- [ ] T4 (DB-down → 503): deferred (operator-assisted)
- [ ] T5 (truncation): deferred (heavy, run locally)
- [ ] B4 (tour integration test script): deferred (write when stable)
