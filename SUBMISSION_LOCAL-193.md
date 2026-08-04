##### READY FOR REVIEW

## LOCAL-193 — Truncate long articles at tier limit

**Commit:** `5987ad9` on branch `kiro/local193-article-truncation`
**Cost:** $0.00 (no API calls, no containers rebuilt — pure logic + tests)

---

## Per-file Summary

| File | Change |
|------|--------|
| `article_truncation.py` (new) | Core truncation module: runtime-config limits, sentence/word boundary logic, tier dispatch, D58-compliant notices |
| `news_processor_service.py` (modified) | Added `secret_id` to DB query; truncates display text before HTML creation; TTS path unchanged |
| `tests/test_local193_article_truncation.py` (new) | 30 unit tests covering all acceptance criteria |

---

## Configuration (runtime-tunable, no code change)

```
NEWS_FREE_CHAR_LIMIT        = 5000   (env var, default)
NEWS_SUBSCRIBED_CHAR_LIMIT  = 15000  (env var, default)
```

Same mechanism as `PRICING_MULTIPLIER` — reads `os.environ.get()` on every call, takes effect immediately.

---

## Candidate Wordings

### Free tier (truncated at 5,000 chars)

**Candidate A (★ shipping):**
> This article has been shortened to 5,000 characters. Subscribe to read longer articles.

**Candidate B (alternate):**
> You're reading a shortened version of this article (5,000 characters). Subscribers can access the full text.

### Subscribed tier (truncated at 15,000 chars)

**Candidate A (★ shipping):**
> This article has been shortened to 15,000 characters.

**Candidate B (alternate):**
> This article exceeds the 15,000-character limit and has been shortened.

---

## Truncation Rules Applied

- **Primary:** Cut at last sentence boundary (`.` `!` `?` followed by whitespace or end) at or before the character budget.
- **Fallback:** If sentence-boundary cut would discard >15% of the allowance, fall back to last word boundary (space).
- **Budget:** `content_budget = limit - len(notice)` so the notice itself never pushes the result over the limit.

On the 30 test articles: sentence-boundary rule fired in 28/30 cases. Word-boundary fallback fired only when articles had no sentence-ending punctuation or the only sentence boundary was within the first 15% of the budget.

---

## TTS Regression Guard (T8)

```
TTS chars (before): 5039
TTS chars (after):  5039
Display chars:      4978
Original chars:     12000
TTS UNCHANGED: ✓
```

The invariant: `clean_text_for_polly()` is called on the ORIGINAL `full_text`, not on the display-truncated text. The processor now has two variables:
- `full_text` → passed to `generate_audio_with_polly()` for audio-99 (unchanged path)
- `display_text` → passed to `create_news_html_with_points()` (truncated for display)

A >5,000-char free article produces identical TTS output before and after this change.

---

## Test Output (verbatim)

```
============================= test session starts ==============================
platform darwin -- Python 3.9.6, pytest-8.4.2, pluggy-1.6.0 -- /Applications/Xcode.app/Contents/Developer/usr/bin/python3
cachedir: .pytest_cache
rootdir: /Users/micha/audioura-worktrees/LOCAL-193
collecting ... collected 30 items

tests/test_local193_article_truncation.py::TestBelowLimit::test_empty_text PASSED [  3%]
tests/test_local193_article_truncation.py::TestBelowLimit::test_free_below_limit PASSED [  6%]
tests/test_local193_article_truncation.py::TestBelowLimit::test_none_text PASSED [ 10%]
tests/test_local193_article_truncation.py::TestBelowLimit::test_subscribed_below_limit PASSED [ 13%]
tests/test_local193_article_truncation.py::TestJustOverLimit::test_free_just_over PASSED [ 16%]
tests/test_local193_article_truncation.py::TestJustOverLimit::test_subscribed_just_over PASSED [ 20%]
tests/test_local193_article_truncation.py::TestFarOverLimit::test_free_far_over PASSED [ 23%]
tests/test_local193_article_truncation.py::TestFarOverLimit::test_subscribed_far_over PASSED [ 26%]
tests/test_local193_article_truncation.py::TestExactlyAtLimit::test_free_exactly_at_limit PASSED [ 30%]
tests/test_local193_article_truncation.py::TestExactlyAtLimit::test_subscribed_exactly_at_limit PASSED [ 33%]
tests/test_local193_article_truncation.py::TestNoSentenceBoundaries::test_no_sentences_free PASSED [ 36%]
tests/test_local193_article_truncation.py::TestNoSentenceBoundaries::test_no_sentences_subscribed PASSED [ 40%]
tests/test_local193_article_truncation.py::TestTierSelection::test_both_truncate_at_different_limits PASSED [ 43%]
tests/test_local193_article_truncation.py::TestTierSelection::test_free_tier_limit PASSED [ 46%]
tests/test_local193_article_truncation.py::TestTierSelection::test_free_truncates_at_5000 PASSED [ 50%]
tests/test_local193_article_truncation.py::TestTierSelection::test_ppu_tier_limit PASSED [ 53%]
tests/test_local193_article_truncation.py::TestTierSelection::test_unlimited_tier_limit PASSED [ 56%]
tests/test_local193_article_truncation.py::TestRuntimeConfig::test_change_free_limit PASSED [ 60%]
tests/test_local193_article_truncation.py::TestRuntimeConfig::test_change_subscribed_limit PASSED [ 63%]
tests/test_local193_article_truncation.py::TestRuntimeConfig::test_config_shown_without_code_change PASSED [ 66%]
tests/test_local193_article_truncation.py::TestTTSUnchanged::test_tts_chars_unchanged   TTS chars (before): 5039
  TTS chars (after):  5039
  Display chars:      4978
  Original chars:     12000
  TTS UNCHANGED: ✓
PASSED [ 70%]
tests/test_local193_article_truncation.py::TestNoticeCompliance::test_free_notice_b_no_cost_no_dollar PASSED [ 73%]
tests/test_local193_article_truncation.py::TestNoticeCompliance::test_free_notice_no_cost_no_dollar PASSED [ 76%]
tests/test_local193_article_truncation.py::TestNoticeCompliance::test_subscribed_notice_b_no_cost_no_dollar PASSED [ 80%]
tests/test_local193_article_truncation.py::TestNoticeCompliance::test_subscribed_notice_no_cost_no_dollar PASSED [ 83%]
tests/test_local193_article_truncation.py::TestNoticeCompliance::test_truncated_output_no_cost_no_dollar PASSED [ 86%]
tests/test_local193_article_truncation.py::TestSentenceBoundaryFallback::test_sentence_too_far_back PASSED [ 90%]
tests/test_local193_article_truncation.py::TestNoticeNotOverLimit::test_many_articles_all_within_limit PASSED [ 93%]
tests/test_local193_article_truncation.py::TestNoticeNotOverLimit::test_result_within_limit_free PASSED [ 96%]
tests/test_local193_article_truncation.py::TestNoticeNotOverLimit::test_result_within_limit_subscribed PASSED [100%]

======================== 30 passed, 1 warning in 0.23s =========================
```

---

## Compliance Grep Results

```
=== Grep for dollar sign in notice strings ===
  '\n\nThis article has been shortened to 5,000 characters. Subscribe to read longer '...
    $=False cost=False token=False
  "\n\nYou're reading a shortened version of this article (5,000 characters). Subscri"...
    $=False cost=False token=False
  '\n\nThis article has been shortened to 15,000 characters.'
    $=False cost=False token=False
  '\n\nThis article exceeds the 15,000-character limit and has been shortened.'
    $=False cost=False token=False

ALL CLEAN
```

---

## git status --short

```
(empty — clean)
```

---

## Limitations (what could NOT be verified without a rebuild)

1. **End-to-end delivery path:** The `truncate_for_user()` call in `news_processor_service.py` resolves the user's subscription tier via DB query (`_get_subscription_tier`). This integration path was verified at the unit-test level (imports work, function signatures match) but could not be run end-to-end without rebuilding the `news-processor-1` container.

2. **Real article from DB:** The TTS regression test uses a synthetic 12,000-char article. A test against an actual stored article (if any >5,000 chars existed in the DB) would require the processor container running and accepting requests.

3. **HTML rendering in mobile app:** The truncation notice appends to the `full_text` displayed in the `index.html` inside the ZIP. Visual confirmation that the notice renders correctly in the Flutter WebView would require a running app + rebuilt processor.

4. **Translation path:** When an article is translated then delivered, the translation service creates a new article_requests row. Truncation fires based on the requesting user's tier at download time (via the processor). The translation service itself is not modified — truncation happens uniformly at the processor regardless of language.

5. **Cache interactions:** If a cached article was generated before truncation was deployed, the first user to download it will get the full text (the cache stores the processor's output ZIP). After rebuild, new articles get truncated. Existing cached ZIPs are not retroactively truncated — this is a known gap that resolves naturally as cache entries expire or new articles are processed.
