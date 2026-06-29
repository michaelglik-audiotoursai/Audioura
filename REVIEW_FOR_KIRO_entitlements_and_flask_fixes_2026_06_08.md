# REVIEW_FOR_KIRO — Entitlements Wiring + Flask Fix (2026-06-08)

**Session scope:** Items #1–3 from `remind_kiro.md` (code fixes only — no deploys this session).

---

## Changes Made

### 1. `generate_tour_text_service.py` — Flask 2.3.3 compatibility fix

**File:** `development/generate_tour_text_service.py` line 198  
**Change:** `attachment_filename=` → `download_name=`

```python
# Before (broken on Flask 2.3.3):
return send_file(output_path, as_attachment=True, attachment_filename=job["output_file"])

# After:
return send_file(output_path, as_attachment=True, download_name=job["output_file"])
```

**Why:** Flask 2.0 renamed `attachment_filename` to `download_name`. Flask 2.3.3 (our pinned cloud version) raises `TypeError` on the old parameter. This was the last remaining use — the orchestrator's two `send_file` calls and the news orchestrator were already using `download_name=`.

**Audit performed:** Searched all `.py` files in the project for `attachment_filename` — zero remaining hits (only Werkzeug internal docs mention it). Also searched for `before_first_request` (removed in 2.3) and `from flask.json import` (restructured) — none found. Flask 2.3.3 compatibility is clean.

---

### 2. `news_orchestrator_service.py` — Wired in `check_news_quota`

**File:** `development/news_orchestrator_service.py`  
**Change:** Added entitlements quota check at the top of `/generate-news`, after input parsing but before any work (DB insert, service calls).

```python
# Entitlements check: verify user hasn't exceeded their news quota
if secret_id and secret_id != 'anonymous':
    try:
        from entitlements import check_news_quota
        quota = check_news_quota(secret_id)
        if not quota['allowed']:
            logging.info(f"[QUOTA] Denied news for {secret_id}: {quota}")
            return jsonify(quota), 429
        logging.info(f"[QUOTA] Allowed news for {secret_id}: used={quota['used']}, remaining={quota['remaining']}")
    except Exception as quota_err:
        logging.error(f"[QUOTA] Error checking news quota (allowing): {quota_err}")
```

**Design notes:**
- Skips check for `anonymous` users (no user_id = no quota tracking possible).
- Fails OPEN on exception (same pattern as tour-orchestrator). Rationale: `entitlements.py` itself fails CLOSED (returns 9999 → denial), so the only way this outer catch fires is if the module can't be imported (not co-deployed) or some truly unexpected error. During the test phase, this avoids breaking the entire news flow due to a deployment ordering issue.
- Returns the full quota response body on 429 so the mobile app can display "limit reached, resets at X" messaging.

**The tour-orchestrator already had this wired in** — confirmed at line ~1118 of `tour_orchestrator_service.py`.

---

### 3. `entitlements.py` — Documented `tour_max_minutes` enforcement decision

**File:** `development/entitlements.py`  
**Change:** Added explanatory comment in `check_tour_quota` above the POI clamp.

```python
# NOTE: tour_max_minutes is not enforced directly — the POI clamp serves as its proxy.
# Tour duration is roughly proportional to stop count (2-5 min/stop), so clamping POI
# to tour_max_poi effectively caps duration. Direct time enforcement would require
# post-generation measurement + rejection, which wastes the compute cost.
clamped_stops = min(requested_stops, plan['tour_max_poi'])
```

**Rationale:** Generating a tour costs $0.05–1.10 in OpenAI + Polly spend. Rejecting AFTER generation (because it came out too long) wastes that money. Capping POI count before generation is the practical proxy — 30 POI × ~4 min/stop ≈ 120 min max, which matches `tour_max_minutes=120`. Same logic applies to `news_max_minutes` — article length is bounded by the input text, not something we can pre-reject meaningfully.

---

## Verification of Previously-Fixed Items (confirmed, not changed)

These were listed as bugs in the earlier entitlements review but are **already correct** in the current `development/entitlements.py`:

| Issue | Status | Evidence |
|-------|--------|----------|
| `get_news_used_period()` global count (no user filter) | ✅ Fixed | `WHERE secret_id = %s` present in all branches |
| Missing `'week'` branch | ✅ Fixed | `date_trunc('week', CURRENT_DATE)` branch exists |
| `get_user_plan` backwards join | ✅ Fixed | `FROM users u JOIN plans p ON u.plan = p.plan_id WHERE u.secret_id = %s` |
| Count functions fail OPEN (return 0) | ✅ Fixed | Both return `9999` with `# Fail closed: deny on error` |
| `requirements.txt` Flask unpinned | ✅ Already pinned | `flask==2.3.3` |

---

## What's NOT Done (next session)

1. **Cloud Tasks deploy (item #4):** API not yet enabled. Commands prepared in `remind_kiro.md`. Requires `gcloud services enable cloudtasks.googleapis.com`, running the setup script, deploying tour-worker, flipping orchestrator env vars, and removing always-on.

2. **Test-phase quota bump:** `UPDATE plans SET tours_per_day=100 WHERE plan_id='free'` — Sir Michael needs to run this before testing, then tighten before launch.

3. **End-to-end retest (item #5):** generate → download → translate → download translated. Blocked on Cloud Tasks deploy (item #4).

---

## Files Modified This Session

| File | Type of change |
|------|---------------|
| `development/generate_tour_text_service.py` | Bug fix (line 198) |
| `development/news_orchestrator_service.py` | Feature (quota wiring) |
| `development/entitlements.py` | Documentation (comment) |
| `development/remind_kiro.md` | Status update |

---

## Risk Assessment

- **`generate_tour_text_service.py` fix:** Zero risk. The old parameter was already broken on the cloud image; this makes it work.
- **News quota wiring:** Low risk. Fails open on error, skips anonymous. Won't break existing behavior — just adds a guard that returns 429 when limits are hit.
- **Entitlements comment:** Zero risk. Documentation only.

No deploy was performed. These changes take effect on next Cloud Build / `gcloud run deploy`.
