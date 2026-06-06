# Claude.AI Review — Entitlements System Implementation

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commit:** `0103f60`  
**Responding to:** `REVIEW_FOR_KIRO_hardening_and_entitlements_2026_06_03.md`

---

## What was implemented

### 1. Schema (`migration/sql/003_entitlements.sql`)

```sql
CREATE TABLE plans (
    plan_id VARCHAR(20) PRIMARY KEY,
    tours_per_day INTEGER DEFAULT 1,
    tour_max_poi INTEGER DEFAULT 30,
    tour_max_minutes INTEGER DEFAULT 120,
    news_per_period INTEGER DEFAULT 10,
    news_period VARCHAR(10) DEFAULT 'day',  -- 'day' or 'month'
    news_max_minutes INTEGER DEFAULT 10,
    downloads_unlimited BOOLEAN DEFAULT TRUE
);

-- Seed:
INSERT INTO plans VALUES ('free', 1, 30, 120, 10, 'day', 10, TRUE);
```

- `users.plan` column added (references `plans.plan_id`, default `'free'`)
- `usage_counters` table for when derived counts get slow
- Applied to local DB ✅

### 2. Module (`entitlements.py`)

Three public functions:

```python
check_tour_quota(user_id, requested_stops=10)
# Returns: {'allowed': True, 'clamped_stops': N, 'remaining': M}
# Or:      {'allowed': False, 'error': 'quota_exceeded', 'limit': 'tours_per_day', 'reset': '...', 'upgrade': True}

check_news_quota(user_id)
# Returns: {'allowed': True, 'remaining': M}
# Or:      {'allowed': False, 'error': 'quota_exceeded', 'limit': 'news_per_period', 'upgrade': True}

get_user_plan(user_id)
# Returns: plan dict with all limits
```

### Design decisions (matching Claude's spec):

| Requirement | Implementation |
|-------------|---------------|
| No hardcoded limits | All numbers in `plans` table rows |
| Change tier = data change | `UPDATE plans SET tours_per_day=5 WHERE plan_id='free'` |
| Add premium tier = SQL INSERT | `INSERT INTO plans VALUES ('premium', 10, 50, ...)` |
| Upgrade a user = SQL UPDATE | `UPDATE users SET plan='premium' WHERE secret_id='...'` |
| Structured 429 response | Includes: error, limit, plan, used, max, reset, upgrade flag |
| Usage derived from existing data | `COUNT(*) FROM tour_requests WHERE started_at::date = TODAY` |
| Per-user keyed on user_id | Uses `secret_id` from request body (already sent by app) |
| Downloads always unlimited | `downloads_unlimited = TRUE` for all plans |

### Not yet wired into services (next step):

The `check_tour_quota` call needs to be added to `tour_orchestrator_service.py` before generation starts, and `check_news_quota` to the news pipeline. The module is ready; wiring is a ~5 line change per service:

```python
from entitlements import check_tour_quota
# Before generation:
quota = check_tour_quota(user_id, total_stops)
if not quota['allowed']:
    return jsonify(quota), 429
total_stops = quota['clamped_stops']  # Plan-enforced maximum
```

---

## Sir Michael's questions answered

### Q1: Cloudflare rate-limit — what are my options?

**Example rule** (in Cloudflare Dashboard → Security → WAF → Rate Limiting Rules):
- **When:** Request URL path contains `/generate-complete-tour` OR `/translate-with-audio`
- **Rate:** 10 requests per 1 minute per IP
- **Action:** Block for 60 seconds
- **Cost:** Free on Cloudflare Pro ($20/month plan), or included in Business/Enterprise. On Free plan you get 1 rate-limiting rule with "block" action.

This is a network-level backstop. The API key + entitlements are the real per-user control.

### Q2: GCP billing budget — changeable later?

Yes. Budgets are fully editable anytime:
- GCP Console → Billing → Budgets & alerts → Create/Edit
- Set $50 now, change to $100/$200 later with one click
- Alert thresholds: e.g., email at 50%, 90%, 100% of budget
- **Optional "programmatic cap":** Use a Cloud Function triggered by the budget alert to automatically stop Cloud SQL or disable the API key if spend exceeds threshold. This is the "internal guardrail" — not just an alert but an automatic shutdown.

### Q3: OpenAI usage — is it exposed?

**Partially.** OpenAI provides:
- **Dashboard:** Manual login at platform.openai.com → Usage
- **API:** `GET https://api.openai.com/v1/usage` — but this is limited and deprecated
- **Usage limits:** You can set a monthly hard cap in OpenAI Dashboard → Organization → Limits → "Monthly budget" — this is the real guardrail
- **Per-request tracking:** The `entitlements.py` module counts generations locally (from `tour_requests`). Since every OpenAI call goes through `tour-generator`, we can track cost per tour by logging token counts (already logged in generator: `"cost: $0.0034 (1688 tokens)"`).

**Recommendation:** Set OpenAI's monthly budget cap ($50-100) as the backstop. Track usage internally via our existing logs/counts. No real-time API needed — the internal counting + the OpenAI hard cap together prevent runaway spend.

---

## Questions for review

1. **Should `check_tour_quota` be wired into the orchestrator NOW** (blocking generation without it), or left as dormant-ready until the mobile app sends `user_id` consistently in generation requests? Currently the orchestrator has `user_id` available from the request body.

2. **The `news_period` for free tier is set to `'day'`** (10 articles/day). Sir Michael needs to confirm this is correct vs 10/month. Easy to change: `UPDATE plans SET news_period='month' WHERE plan_id='free'`.

3. **The `usage_counters` table** exists but isn't populated yet (counts are derived from existing tables). Should I add counter-increment calls now, or wait until derived counts are too slow?
