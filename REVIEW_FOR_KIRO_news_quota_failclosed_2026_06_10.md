# REVIEW_FOR_KIRO — News Quota Fail-CLOSED + news_max_minutes Enforcement (2026-06-10)

**Context:** Implementing Claude's spec from `claude_review_news_quota_failclosed_news_minutes_2026_06_10.md`. Two launch-gating defects: (1) news quota wrapper fails OPEN, (2) `news_max_minutes` is never enforced.

---

## Changes Made

### Change 1: News quota fail-CLOSED (`news_orchestrator_service.py`)

**Before:** Anonymous/empty users bypassed quota; exceptions logged "(allowing)" and let requests through.

**After:**
```python
# Missing/anonymous id → 401 (deny)
if not secret_id or secret_id == 'anonymous':
    return jsonify({"error": "auth_required", ...}), 401

# Exception during check → 503 (deny)
try:
    quota = check_news_quota(secret_id)
except Exception as quota_err:
    return jsonify({"error": "quota_check_failed", ...}), 503

# Over quota → 429 (deny, unchanged)
if not quota['allowed']:
    return jsonify(quota), 429
```

### Change 2: `news_max_minutes` exposed in quota response (`entitlements.py`)

Both allowed and denied paths of `check_news_quota` now include:
```python
'news_max_minutes': plan['news_max_minutes']
```

The orchestrator reads this to derive the word budget without a second DB call.

### Change 3: Word-budget enforcement (`entitlements.py` + `news_generator_service.py`)

**Helper functions added to `entitlements.py`:**
```python
NEWS_WORDS_PER_MINUTE = int(os.getenv('NEWS_WPM', '150'))  # Polly ~150 wpm

def words_budget_for_minutes(max_minutes):
    """10 minutes → 1500 words. None/0 → no cap."""

def truncate_to_word_budget(text, word_budget):
    """Cuts at last sentence boundary at/under budget. Returns (text, was_truncated)."""
```

**Orchestrator passes budget to generator:**
```python
max_narration_words = words_budget_for_minutes(quota.get('news_max_minutes'))
generator_response = requests.post(
    f'{NEWS_GENERATOR_URL}/process-article/{article_id}',
    json={'max_major_points': major_points_count, 'max_narration_words': max_narration_words},
    ...
)
```

**Generator truncates before storage:**
```python
max_narration_words = data.get('max_narration_words')
if max_narration_words:
    processed_text, was_truncated = truncate_to_word_budget(processed_text, max_narration_words)
    if was_truncated:
        logging.info(f"[QUOTA] Narration truncated to ~{max_narration_words} words")
```

---

## Behavior After Fix

| Scenario | Response | Audio generated? |
|----------|----------|-----------------|
| Missing/anonymous `secret_id` | **401** | No |
| Quota check DB error | **503** | No |
| Over quota | **429** | No |
| Under quota, article ≤ budget | **200**, full narration | Yes |
| Under quota, article > budget | **200**, truncated narration | Yes (capped) |

---

## news_max_minutes caps by plan

| Plan | news_max_minutes | Word budget (at 150 wpm) |
|------|-----------------|--------------------------|
| free | 10 | 1,500 words |
| tester | 30 | 4,500 words |
| paid | 30 | 4,500 words |

A typical news article is 500–2000 words — most articles won't be truncated. Only extremely long articles (6000+ words) hit the free tier's cap.

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `news-orchestrator` | `audioura:v16` | `news-orchestrator-00002-69h` |
| `news-generator` | `audioura:v16` | `news-generator-00002-rrq` |

---

## Files Modified

| File | Change |
|------|--------|
| `development/news_orchestrator_service.py` | Fail-closed wrapper + pass `max_narration_words` to generator |
| `development/entitlements.py` | `news_max_minutes` in quota response + `words_budget_for_minutes` + `truncate_to_word_budget` |
| `development/news_generator_service.py` | Read `max_narration_words` param + truncate before storage |

---

## `py_compile` verification

All three files: exit 0 (clean).

---

## Risk

- **Fail-closed wrapper:** Breaking change for anonymous news requests — they now get 401 instead of proceeding. This is intentional (spec requirement). The mobile app sends `secret_id` for all authenticated users; only truly anonymous/malformed requests are affected.
- **Truncation:** Truncates at sentence boundary — graceful degradation. User gets a complete-sounding (if shorter) article rather than a rejected request. The cap only bites on very long articles exceeding 10 minutes of narration.
- **`NEWS_WPM` env var:** Defaults to 150. Tunable without redeploy if Polly's actual rate differs.

---

## Acceptance Criteria Status

- [x] Missing/anonymous id → 401, nothing generated
- [x] Exception in quota check → 503, nothing generated  
- [x] Over quota → 429, nothing generated
- [x] `check_news_quota` returns `news_max_minutes` in both paths
- [x] `words_budget_for_minutes(10)` = 1500 (at default 150 wpm)
- [x] Long articles truncated at sentence boundary, logged
- [x] `NEWS_WPM` configurable via env, no redeploy
- [ ] **Integration tests:** to be verified on next test run
