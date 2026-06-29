# REVIEW_FOR_KIRO — Quota 503 Fix + Privacy Policy Update (2026-06-12)

**Context:** Two items: (1) Fix the quota check so DB connection errors return 503 (not 429 "quota exceeded"). (2) Amend the privacy policy per owner decisions.

---

## 1. Quota DB-Down → 503 Fix

### Problem

The entitlements module caught ALL exceptions (including DB connection errors) and returned `9999` → quota exceeded → 429. The contract says: check-error → 503, over-quota → 429. A user seeing "quota exceeded" when the DB is down is misleading and non-actionable.

### Fix

Split error handling in `get_user_plan`, `get_tours_used_today`, and `get_news_used_period`:

- **DB connection failure** (`_get_conn()` raises) → exception propagates → orchestrator catches → **503** `quota_check_failed`
- **Query error** (connected but query fails) → returns 9999 → **429** (last-resort backstop, rare)

```python
def get_news_used_period(user_id, period='week'):
    try:
        conn = _get_conn()      # ← raises on connection failure → 503
    except Exception as e:
        raise                   # propagate to orchestrator

    try:
        # ... query logic ...
        return count
    except Exception as e:
        return 9999             # last-resort backstop for query errors → 429
```

Same pattern applied to all three functions.

### Test Result

```
T4 DB-Down Test:
  Status: 503
  Body: {'allowed': False, 'error': 'quota_check_failed',
         'message': 'Could not verify your news quota. Please try again.'}
  ✅ T4 PASS: DB down → 503

T4b Anonymous with DB down:
  Status: 401
  ✅ PASS: Anonymous → 401 (identity check precedes DB)
```

### Status Code Contract (final)

| Scenario | Status | Error field |
|----------|--------|-------------|
| Missing/anonymous user | 401 | `auth_required` |
| DB connection down | 503 | `quota_check_failed` |
| Over quota (DB works) | 429 | `quota_exceeded` |
| Under quota | 200 | (proceeds to generation) |

---

## 2. Privacy Policy Amendments

Per `OWNER_DECISIONS_privacy_and_profile_portability_2026_06_11.md`, three spots updated in `PRIVACY_POLICY.html`:

### Section 1 (table row "Tour content you generate"):
Added: "Generated tours are added to Audioura's shared, public library and may be available to other users. This content is not linked to your identity."

### Section 4 (Data retention):
Added: "Tour content you generate is added to our shared public library and may be retained, in anonymized form not linked to you, even after you delete your data — because other users may rely on those tours and their translations."

### Section 6 (Your rights):
- Changed "delete all your data" → "delete all your personal data"
- Explicitly lists what's deleted: account, usage history, credentials, device-linked records, downloaded tours
- Added: "Generated tours already added to the shared public library are retained in anonymized form, no longer linked to you."
- Fixed label: "Settings → Delete My Data" → "About → Delete My Account" (matches app UI)

### Rationale
Tours are shared/public content (no `secret_id` column in `audio_tours`). After account deletion, no link between the user and the retained content exists — genuinely anonymized. The policy now accurately describes this behavior.

---

## Files Modified

| File | Change |
|------|--------|
| `development/entitlements.py` | DB connection errors raise (→503); query errors return 9999 (→429 backstop) |
| `development/PRIVACY_POLICY.html` | Three sections amended per owner decision |
| `development/test_t4_db_down_unit.py` | Updated to assert 503 |

---

## `py_compile`

`entitlements.py`: exit 0 (clean).

---

## Deployment Note

The `entitlements.py` change needs to be deployed in the next image build (v22+) for the orchestrator and news services. Not yet deployed — marking for next build.
