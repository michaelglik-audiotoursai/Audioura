# For Kiro Amazon-Q — Security Hardening Review + Entitlements Architecture (Services)

**Date:** 2026-06-03
**Scope:** Services/GCloud only.

Two parts: (1) sign-off on the security hardening (commit `e871eae`), and (2) forward-looking guidance so the **free/paid tier limits are data-driven, not hardcoded** — Sir Michael's explicit requirement.

---

## Part 1 — Security hardening: ✅ approved (verified in code)
- **Fail-closed API key:** `main.py` now logs a startup `[WARNING]` when `GATEWAY_API_KEY` is unset (line 28-29) and `require_api_key()` returns **503** when no key is configured (line 34-36). Protection can no longer silently vanish. ✅
- **Constant-time compare:** `hmac.compare_digest(client_key, API_KEY)` (line 38). ✅
- Applied to all four cost endpoints (generate, tour-status, translate, process_newsletter). ✅
- **IAM lock empirically verified:** map-delivery / orchestrator / polly-tts return 403 directly. ✅

Nothing to change. This closes the production-security residuals.

---

## Part 2 — Build entitlements as DATA, not hardcoded limits

Sir Michael's product model: a **free tier** (1 generated tour/day ≤ 30 POI and ≤ 2 hours; 10 news articles ≤ 10 min each; unlimited downloads of already-generated tours) and **paid tiers later** (subscription, after App-Store/Play billing exists). His one firm requirement: **do not hardcode any limit** — paid tiers must be a config change, not a code change.

### The design
**1. A `plans` table (or config) — limits live here, never in code.**
```
plans(plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
      news_per_period, news_period, news_max_minutes, downloads_unlimited, ...)
-- seed:
free    : 1,  30, 120, 10, 'day'|'month'(see note), 10, true
premium : (TBD higher numbers)
```
Storing these as **rows** means changing the free tier or adding `premium` is an `UPDATE`/`INSERT`, with zero redeploy.

**2. A `plan` column on the users table**, default `'free'`. Everyone is `free` today; the column is the seam for later.

**3. Usage counting.** You likely don't need a new table at first — derive "used today/this period" from existing data:
- tours today = `COUNT(*) FROM tour_requests WHERE secret_id=:user AND started_at::date = CURRENT_DATE`
- news this period = `COUNT(*) FROM news_audios/article_requests WHERE user=:user AND created_at >= :period_start`
Add a lightweight `usage_counters(user_id, period_key, kind, count)` only if these counts get slow.

**4. Enforce server-side, in the service that does the costly work — keyed on `user_id`, not the API key.**
- **tour-orchestrator `/generate-complete-tour`:** before generating, load `plan = plan_of(user_id)` → `limits = plans[plan]`. Check tours-today < `tours_per_day`; clamp/reject `total_stops` > `tour_max_poi` and requested length > `tour_max_minutes`.
- **news-orchestrator / newsletter-processor:** check news-this-period < `news_per_period`; cap article audio to `news_max_minutes`.
- **map-delivery `/download-tour`:** no gating — downloads stay unlimited for all.

Return a **structured** quota response the app can act on, e.g.:
```json
{"error":"quota_exceeded","limit":"tours_per_day","plan":"free","reset":"2026-06-04T00:00Z","upgrade":true}
```
(HTTP 429.) That lets the mobile app later show "You've used today's free tour — upgrade for more" without any further services change.

### Why this satisfies "don't hardcode"
The enforcement code is generic: `if used >= limits[kind]: reject`. The *numbers* live in `plans`; a user's tier lives in `users.plan`. When subscriptions ship, an App-Store/Play **IAP webhook** simply sets `users.plan='premium'` and the same code grants the premium row's limits — no enforcement change.

### Identity note (important)
The gateway `X-API-Key` is a **shared, app-level** secret — it answers "is this our app?", not "who is this user?". Entitlements must key on the **per-user `user_id`** (`USER-xxx` / `secret_id`) the app already sends in tour/news requests. Confirm `/generate-complete-tour` and the news endpoints receive `user_id` in the body so the orchestrator can look up the plan. (They already insert `secret_id` into `tour_requests`, so it's available.)

### Two things to fix/avoid now so nothing is baked in
- **Existing hardcoded `total_stops` 1–50 validation** (in `generate_tour_text_service.py`) is exactly the kind of constant to make plan-driven: keep a hard ceiling (sanity max, e.g. 50) but apply the **plan's** `tour_max_poi` (30 for free) as the enforced cap. Don't bury the free number in code.
- **Build the plan check now, defaulting everyone to `free`** — even though there's no paid tier yet and no billing. The system runs dormant-but-ready; flipping a user to paid later is a data change.
- **Track usage from day one** (even before billing) so Sir Michael has real consumption data to price the subscription.

### One product clarification to get from Sir Michael (it drives cost a lot)
"10 News Articles" has **no period stated**. 10/**day** vs 10/**month** is a ~30× cost difference. Make `news_period` a plan column (`'day'`/`'month'`) and ask him which — but either way it's a config value, not a constant.

---

## Bottom line for Kiro
Security hardening: approved, verified, done. For the business model: **implement entitlements as a `plans` table + `users.plan` + per-user server-side checks in orchestrator/news**, returning structured 429s, defaulting everyone to `free`. That makes today's free limits (1 tour/day/30 POI/2 hr; 10 news/10 min) enforceable now and fully flexible for paid tiers later — no hardcoded numbers, no redeploy to change a plan. The rate-limit / billing / OpenAI-cap items are Sir Michael's console actions (answered to him separately) and are anti-abuse backstops, **not** a substitute for this per-user entitlement layer.
