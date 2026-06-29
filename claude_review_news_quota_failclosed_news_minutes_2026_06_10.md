# REVIEW / SPEC FOR KIRO (Amazon-Q) — Enforce `news_max_minutes` + Make News-Quota Fail-CLOSED

**Date:** 2026-06-10 · **Lane:** Cloud services (news + entitlements) — services only, no mobile changes.
**Author:** Claude (independent reviewer) · **Owner to implement:** Kiro.

## Summary of the task
Two defects in the news path, both launch-gating:

1. **Fail-OPEN quota wrapper.** In `news_orchestrator_service.py::generate_news`, the quota check (a) is
   skipped entirely for `anonymous`/empty users, and (b) on any exception it **logs "(allowing)" and lets the
   request through**. Both let users exceed quota. Must become **fail-CLOSED** (deny on error / missing id).
2. **`news_max_minutes` is never enforced.** `entitlements.get_user_plan` returns `news_max_minutes`
   (free = 10), but nothing caps the generated news audio length. A user can request an arbitrarily long
   article and get unlimited audio minutes.

---

## Current code (verified 2026-06-10)

`news_orchestrator_service.py`, `/generate-news` (lines ~54–64):

```python
# Entitlements check: verify user hasn't exceeded their news quota
if secret_id and secret_id != 'anonymous':          # (b) FAIL-OPEN: anonymous/empty skips the check
    try:
        from entitlements import check_news_quota
        quota = check_news_quota(secret_id)
        if not quota['allowed']:
            logging.info(f"[QUOTA] Denied news for {secret_id}: {quota}")
            return jsonify(quota), 429
        logging.info(f"[QUOTA] Allowed news for {secret_id}: used={quota['used']}, remaining={quota['remaining']}")
    except Exception as quota_err:
        logging.error(f"[QUOTA] Error checking news quota (allowing): {quota_err}")  # (a) FAIL-OPEN
```

Downstream flow: `/generate-news` → stores `article_text` → calls news-generator `/process-article/<id>`
(produces narration text from the article) → calls news-processor `/process-audio/<id>` (TTS → audio).
The narration produced by the generator is what determines audio length.

`entitlements.check_news_quota` already fails closed internally (`get_news_used_period` returns 9999 → deny on
DB error). The problem is the **wrapper** in the orchestrator swallowing errors and the anonymous skip.

---

## Required changes

### Change 1 — News-quota wrapper must fail CLOSED

Replace the block above with logic that denies on both missing-id and exception paths:

```python
# Entitlements check: verify user hasn't exceeded their news quota. FAIL-CLOSED.
if not secret_id or secret_id == 'anonymous':
    logging.warning("[QUOTA] Missing/anonymous secret_id — denying news (fail-closed)")
    return jsonify({
        "allowed": False, "error": "auth_required",
        "message": "A valid user id is required to generate news."
    }), 401

try:
    from entitlements import check_news_quota
    quota = check_news_quota(secret_id)
except Exception as quota_err:
    logging.error(f"[QUOTA] News quota check failed — denying (fail-closed): {quota_err}")
    return jsonify({
        "allowed": False, "error": "quota_check_failed",
        "message": "Could not verify your news quota. Please try again."
    }), 503

if not quota['allowed']:
    logging.info(f"[QUOTA] Denied news for {secret_id}: {quota}")
    return jsonify(quota), 429
logging.info(f"[QUOTA] Allowed news for {secret_id}: used={quota['used']}, remaining={quota['remaining']}")
```

Behavior after this change:
- Missing / `anonymous` id → **401** (deny).
- Exception while checking → **503** (deny).
- Over quota → **429** (deny, unchanged).
- Under quota → proceed.

### Change 2 — Expose `news_max_minutes` from the entitlement check

In `entitlements.py`, add `news_max_minutes` to **both** return dicts of `check_news_quota` so the orchestrator
doesn't need a second DB call:

```python
# in check_news_quota, both the allowed and denied returns:
'news_max_minutes': plan['news_max_minutes'],
```

### Change 3 — Enforce `news_max_minutes` (cap the narration length)

Audio duration ≈ words ÷ speaking-rate. Cap the **narration word count** to a budget derived from the user's
`news_max_minutes`. Enforce at generation time so we never pay TTS for audio we'd discard.

Add a shared constant + helper (put in `entitlements.py` or a small `news_limits.py`):

```python
import os
NEWS_WORDS_PER_MINUTE = int(os.getenv('NEWS_WPM', '150'))  # Polly ~150 wpm; tune via env, no redeploy

def words_budget_for_minutes(max_minutes):
    if not max_minutes or max_minutes <= 0:
        return None  # no cap
    return int(max_minutes * NEWS_WORDS_PER_MINUTE)

def truncate_to_word_budget(text, word_budget):
    """Return (text, was_truncated). Cuts at the last sentence end at/under budget."""
    if not word_budget:
        return text, False
    words = text.split()
    if len(words) <= word_budget:
        return text, False
    clipped = ' '.join(words[:word_budget])
    cut = max(clipped.rfind('.'), clipped.rfind('!'), clipped.rfind('?'))
    if cut > 0:
        clipped = clipped[:cut + 1]
    return clipped, True
```

**Primary enforcement (recommended):** pass the budget from the orchestrator into the generator so it limits its
output. In `generate_news`, after the quota check:

```python
max_words = words_budget_for_minutes(quota['news_max_minutes'])
generator_response = requests.post(
    f'{NEWS_GENERATOR_URL}/process-article/{article_id}',
    json={'max_major_points': major_points_count, 'max_narration_words': max_words},
    headers={'Content-Type': 'application/json'}, timeout=30
)
```
In `news_generator_service.py::/process-article`, after the narration text is assembled and before it is stored,
apply `truncate_to_word_budget(narration, max_narration_words)` and log when truncation occurs.

**Belt-and-suspenders (recommended in addition):** in `news_processor_service.py`, immediately before the TTS
call, re-apply `truncate_to_word_budget` using the budget for that article's user, so the cap holds even if a
narration path bypasses the generator limit.

> Notes: enforce on the **English** narration word count for v1 (translations derive from it). `NEWS_WPM` is an
> env var so the minutes→words mapping can be tuned without redeploy. Do not hard-fail an article for being
> long — **truncate** to the cap (better UX than rejecting after the user picked the article).

---

## Tests to verify compliance

Provide these as automated tests where possible plus the manual checks. **All must pass.**

### A. Unit tests — fail-closed wrapper (mock `check_news_quota`)
1. `test_news_missing_secret_id_denied` — POST `/generate-news` with `secret_id` omitted → **401**, body `error=auth_required`, and the generator/processor are **never called**.
2. `test_news_anonymous_denied` — `secret_id='anonymous'` → **401**, downstream never called.
3. `test_news_quota_exception_denied` — patch `check_news_quota` to raise → **503**, `error=quota_check_failed`, downstream never called.
4. `test_news_over_quota_denied` — `check_news_quota` returns `allowed=False` → **429**, downstream never called.
5. `test_news_under_quota_allowed` — `allowed=True` → proceeds to generation (downstream called once).

> Test 3 is the core regression: before the fix it returns 200 and processes; after the fix it must return 503.

### B. Unit tests — `news_max_minutes` enforcement
6. `test_words_budget` — `words_budget_for_minutes(10)==1500` (with `NEWS_WPM=150`); `words_budget_for_minutes(0) is None`.
7. `test_truncate_under_budget_unchanged` — text with fewer words than budget returns unchanged, `was_truncated=False`.
8. `test_truncate_over_budget_clips_at_sentence` — text far over budget → returns ≤ budget words, ends with `.`/`!`/`?`, `was_truncated=True`.
9. `test_check_news_quota_exposes_minutes` — `check_news_quota(user)` dict contains `news_max_minutes` on both allowed and denied paths.

### C. Integration tests (real services, test DB)
10. **Quota exhaustion is enforced:** set a test user to `news_per_period=2`. Three `/generate-news` calls → first two **200/success**, third **429**. (Confirms wrapper denies and counting works.)
11. **DB-down fails closed:** point entitlements at an unreachable DB (bad `DB_HOST`) → `/generate-news` returns **503** (not 200). Restore DB; request succeeds.
12. **Long article is capped:** with `news_max_minutes=10` and `NEWS_WPM=150` (budget 1500 words), submit a 6,000-word article. Inspect the stored narration / generated audio: narration ≤ ~1500 words; log shows truncation. Submit a 300-word article → unchanged, no truncation.
13. **Anonymous cannot generate:** `/generate-news` with no `secret_id` → **401**; verify no row added to `article_requests` and no audio produced.

### D. Manual verification (curl + SQL, copy-paste)
```bash
# Missing id -> 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$GW/generate-news" \
  -H 'Content-Type: application/json' -d '{"article_text":"hello world"}'      # expect 401

# Over quota (after setting news_per_period=1 for the user and using once) -> 429
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$GW/generate-news" \
  -H 'Content-Type: application/json' \
  -d '{"article_text":"...","secret_id":"<test_id>"}'                          # expect 429 on 2nd call
```
```sql
-- Confirm the cap is in the plan and counting works
SELECT plan_id, news_per_period, news_period, news_max_minutes FROM plans WHERE plan_id='free';  -- 10/week/10min
SELECT COUNT(*) FROM article_requests WHERE secret_id='<test_id>'
  AND created_at >= date_trunc('week', CURRENT_DATE);
```

### Acceptance criteria (definition of done)
- [ ] Tests A1–A5, B6–B9 pass.
- [ ] Integration 10–13 pass against a test DB.
- [ ] On any quota-check error, `/generate-news` returns **503** and does **not** generate (was 200 before).
- [ ] Missing/anonymous id returns **401** and generates nothing.
- [ ] News audio for a `news_max_minutes=10` user never exceeds ~10 minutes of narration regardless of input length; truncation is logged.
- [ ] `NEWS_WPM` is configurable via env (no redeploy to tune).

## Rollback
- Revert the `generate_news` wrapper block and the `check_news_quota` return-dict addition.
- Remove `max_narration_words` handling in generator/processor and the `news_limits` helper.
(No schema change is required; `news_max_minutes` already exists in `plans`.)

## Out of scope
- Mobile changes. The app already handles 429; it should also surface 401/503 gracefully, but that is a Mobile-AQ item, not part of this services task.
- Per-user quota tiering — covered separately in `claude_review_per_user_quota_2026_06_10.md`.
- Measuring actual generated-audio duration post-TTS (future refinement); the word-budget proxy is sufficient for v1, mirroring how tours proxy minutes via the POI clamp.
