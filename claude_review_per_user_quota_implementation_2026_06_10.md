# CLAUDE REVIEW — Kiro's Per-User Quota Implementation

**Date:** 2026-06-10 · **Lane:** Cloud services (entitlements / tour-orchestrator) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_per_user_quota_2026_06_10.md` (Kiro) against the deployed code.
**Spec under test:** `claude_review_per_user_quota_2026_06_10.md`.

## Verdict: CHANGES REQUESTED (core mechanism approved; two HIGH issues block sign-off)

The plan/tier architecture is implemented correctly and matches the spec: `plans` table, three tiers,
`users.plan`, the `COALESCE` override, the empty-id guard, and SQL-only tiering all check out. **But the
"anonymous/empty `secret_id` cannot bypass quota" acceptance item is marked done and is not actually
satisfied**, and the new tour quota check is **fail-OPEN on error**. Both must be fixed before this can be
trusted as a launch cost guardrail.

---

## Claim-by-claim verification

| Kiro's claim | Status | Evidence |
|---|---|---|
| `get_user_plan` empty/anonymous guard returns free (1/day), no DB hit | ✅ Verified | `entitlements.py:42–54` |
| `COALESCE(u.tours_per_day_override, p.tours_per_day)` query | ✅ Verified | `entitlements.py:59–68` |
| Unknown user → falls back to `free` plan | ✅ Verified | `entitlements.py:71–74` |
| DB-unavailable fallback returns `tours_per_day=1` | ✅ Verified | `entitlements.py:93–103` |
| Orchestrator changed from `if user_id:` skip → always-check | ✅ Verified (intent) | `tour_orchestrator_service.py:1108–1118` |
| `plans` schema + 3 tiers (free=1, tester=100, paid=10) | ✅ Plausible | matches `db-job/run.py`; not independently queried |
| Test devices set to `tester` | ✅ Plausible | `db-job/run.py:77–89` |
| **Anonymous/empty `secret_id` cannot bypass quota (capped 1/day)** | ❌ **NOT satisfied** | see Finding 2 |
| Per-user override via `tours_per_day_override` (NULL = plan default) | ✅ Verified | `entitlements.py:61` |
| "new/unknown user blocked on 2nd tour (429)" | ⬜ Unverified (Kiro left unchecked) | will fail given Findings 1–2 |

---

## Findings

### Finding 1 — HIGH: Tour quota check is FAIL-OPEN on exception
`tour_orchestrator_service.py:1119–1120`:
```python
except Exception as quota_err:
    print(f"[QUOTA] Error checking quota (allowing): {quota_err}")
```
On **any** exception in `check_tour_quota`, the code logs "(allowing)" and falls through — the tour proceeds
with no limit. This is the same fail-OPEN class we just removed from the news path (`news_orchestrator_service.py`
now denies with 401/503). The tour path must match. A transient DB error or any bug in the quota path =
unlimited tours = the exact cost exposure this project exists to close.

**Fix — fail CLOSED:**
```python
_quota_user = user_id if user_id else 'anonymous'
try:
    from entitlements import check_tour_quota
    quota = check_tour_quota(_quota_user, total_stops)
except Exception as quota_err:
    print(f"[QUOTA] Quota check failed — denying (fail-closed): {quota_err}")
    return jsonify({"allowed": False, "error": "quota_check_failed",
                    "message": "Could not verify your tour quota. Please try again."}), 503
if not quota['allowed']:
    return jsonify(quota), 429
total_stops = quota['clamped_stops']
```

### Finding 2 — HIGH: Quota counting is decoupled from enforcement → anonymous cap does not work
The counter `get_tours_used_today(user_id)` reads `tour_requests` (`entitlements.py:110–113`):
```sql
SELECT COUNT(*) FROM tour_requests WHERE secret_id = %s AND started_at::date = CURRENT_DATE
```
But **the tour-orchestrator never writes `tour_requests`.** Those rows are inserted by a *separate* user-tracking
service from the **app-supplied** `secret_id` (`user_api_with_cors.py:100`, `user-tracking/app.py:79`). The
orchestrator/worker only write `job_status`. Consequences:

1. **Anonymous never counts.** For an anonymous request the orchestrator checks the bucket `secret_id='anonymous'`,
   but the tracking service writes rows under the app's real/device id (or writes nothing for anonymous). So
   `COUNT(... WHERE secret_id='anonymous')` stays at 0 and **every anonymous request is allowed** → the "cannot
   bypass" claim is false.
2. **Any client that doesn't report is uncounted.** Because usage is recorded by a different service driven by the
   client, a client that simply skips the tracking call is never counted → unlimited tours. (Compounded by the
   X-API-Key being extractable from the APK — noted in the launch digest.)
3. **Race window.** Even for honest clients, the quota check counts *existing* rows while the row for the current
   tour is written elsewhere, possibly after generation starts — several tours can slip through before any land.

**Fix:** make enforcement and accounting share one source of truth. Have the **orchestrator (or worker) write a
usage row itself**, keyed on the same `_quota_user` it checked, at the moment it admits the tour — rather than
relying on the app/tracking service. Simplest: an `INSERT INTO tour_requests (secret_id, tour_id, status, started_at)`
(or a dedicated `tour_usage` table) inside the orchestrator right after the quota passes, using `_quota_user`.
Then the counter and the check agree, anonymous included.

### Finding 3 — MEDIUM: Anonymous is a single shared global bucket + inconsistent with news path
Even once counting works, `_quota_user='anonymous'` puts **all** anonymous users in one `secret_id='anonymous'`
counter — the first anonymous tour each day would lock out every other anonymous user globally. Also, the spec
recommended *rejecting* missing-id requests, and the **news path now does exactly that** (401, `auth_required`),
but the tour path *allows* anonymous. Pick one policy and apply it to both. Recommended: require a stable
`secret_id` for tour generation (reject with 401 when absent), matching news; if anonymous tours must be allowed,
key the bucket on a per-device id, not the literal string.

### Finding 4 — LOW: The decisive end-to-end test was not run
Kiro left "new/unknown user blocked on 2nd tour (429)" unchecked. Given Findings 1–2 this test would currently
**fail** (the second tour would be allowed because the counter never increments from the orchestrator's view).
This test is the real proof of the feature and must pass after the fixes.

---

## What's correct and good (credit where due)
- `get_user_plan` empty-id guard, `COALESCE` override, unknown-user → free, and DB-down → 1/day are all correct
  and exactly per spec. The plan-lookup layer fails closed properly.
- Tier and override changes are pure SQL with no redeploy — the operational goal is met.
- Routing anonymous *into* the check (instead of skipping) is the right intent; it just isn't backed by a
  working counter yet.
- Schema matches the spec; tester/paid tiers present.

---

## Required before sign-off
1. **Finding 1:** make the tour quota exception path fail CLOSED (503), not "(allowing)".
2. **Finding 2:** record usage in the same service/transaction that enforces it, keyed on `_quota_user`, so the
   counter actually reflects admitted tours (fixes the anonymous bypass).
3. **Finding 3:** choose one anonymous policy (recommend: reject missing id, matching the news path) and apply
   consistently.
4. **Re-run** the integration tests, especially: new user blocked on 2nd tour (429); anonymous blocked after 1;
   DB-down returns 503 (not 200); tester gets 100/day.

## Cross-references
- News-path fail-closed + `news_max_minutes`: `claude_review_news_quota_failclosed_news_minutes_2026_06_10.md`
  (the news orchestrator already shows the fail-closed guard applied — good; mirror that exception handling here).
- Original spec: `claude_review_per_user_quota_2026_06_10.md`.

## Scope notes
Services-only review. No mobile changes assessed. If the team adopts "reject anonymous" for tours, the app must
surface 401 gracefully — a Mobile-AQ item, out of scope for this doc.
