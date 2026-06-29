# CLAUDE REVIEW — Kiro's News Quota Fail-CLOSED + `news_max_minutes` Implementation

**Date:** 2026-06-10 · **Lane:** Cloud services (news-orchestrator / news-generator / entitlements) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_news_quota_failclosed_2026_06_10.md` (Kiro) against deployed code.
**Spec under test:** `claude_review_news_quota_failclosed_news_minutes_2026_06_10.md`.

## Verdict: APPROVED (minor, non-blocking hardening notes below)

This implementation is correct and complete against the spec. The fail-closed posture is exactly right, and —
notably — it avoids the decoupled-counting flaw found in the tour-quota work: the news orchestrator records the
usage row in the **same service and with the same `secret_id`** it quota-checks, so the counter and the
enforcement agree. This is the reference pattern the tour path should adopt.

---

## Claim-by-claim verification

| Kiro's claim | Status | Evidence |
|---|---|---|
| Missing/anonymous `secret_id` → 401, nothing generated | ✅ Verified | `news_orchestrator_service.py:55–60` (returns before insert/generate) |
| Exception in quota check → 503, nothing generated | ✅ Verified | `:62–70` |
| Over quota → 429, nothing generated | ✅ Verified | `:72–74` |
| `check_news_quota` returns `news_max_minutes` (both paths) | ✅ Verified | `entitlements.py:214` (denied), `:224` (allowed) |
| `words_budget_for_minutes(10) == 1500` @150 wpm | ✅ Verified (executed) | returns 1500; `0`/`None` → `None` |
| `truncate_to_word_budget` cuts at sentence boundary | ✅ Verified (executed) | ends on `.`; no-punct → hard clip at budget; under-budget unchanged |
| Orchestrator derives budget + passes to generator | ✅ Verified | `:77–79`, `:124–126` (`max_narration_words`) |
| Generator reads param + truncates before storage | ✅ Verified | `news_generator_service.py:571`, `:580–587` |
| `NEWS_WPM` env-configurable, no redeploy | ✅ Verified | `entitlements.py:231` |
| `py_compile` clean | ✅ Trusted (files parse; logic executed) | — |
| Integration tests | ⬜ Pending (Kiro's open box) | run before final sign-off |

I executed the two helper functions with boundary inputs: budget math, sentence-boundary truncation, the
no-punctuation hard-clip path, and the under-budget no-op all behave as specified.

---

## What's done well
- **Order is safe:** all three deny paths (401/503/429) return *before* the `article_requests` insert and before
  any generator/processor call — denied requests create no row, consume no quota, and generate no audio.
- **Counting is coupled to enforcement:** the orchestrator itself inserts `article_requests` with the same
  `secret_id` it checked (`:97–102`). So `get_news_used_period` actually reflects admitted requests — no
  app/tracking dependency, no anonymous-bypass hole. (Contrast: `claude_review_per_user_quota_implementation_2026_06_10.md`.)
- **Anonymous rejected (401), fail-closed on error (503):** matches the spec and is the correct, consistent policy.
- **Enforcement at generation time:** truncating in the generator before storage avoids paying TTS for audio that
  would be discarded.

---

## Minor notes (non-blocking; hardening / confirm)

1. **Confirm the truncation target equals what TTS narrates.** The cap is applied to
   `processed_text = "Summary: {summary}\n\nFull Article: {cleaned_text}"` (`news_generator_service.py:577`).
   The minutes→words proxy is only accurate if the news-processor sends *that same string* to TTS. If the
   processor narrates only the summary, the cap rarely bites (safe/conservative); if it narrates the whole thing,
   the cap is correct. Worth a one-line confirmation of the processor's TTS input.

2. **Failed generations still consume quota.** The `article_requests` row is inserted with status `'started'`
   before the generator/processor run. If generation later fails, the row persists and counts toward
   `news_per_period`. Consider not counting non-completed rows (or rolling back on failure) so transient errors
   don't burn a user's weekly allowance. Low severity.

3. **Check-then-insert race.** No lock between the quota count and the insert; two near-simultaneous requests
   could both pass. Negligible for a weekly news limit, but note it if news ever moves to a tight daily cap.

4. **Belt-and-suspenders processor cap not added.** The spec suggested *also* truncating in `news_processor`
   immediately before TTS as a fallback. Only the generator path was implemented. Acceptable since the generator
   is the single narration-assembly point — but if any future path reaches TTS without going through
   `/process-article`, the cap would be missed. Optional hardening.

5. **Pathological truncation cut (inherited from my spec's algorithm).** `rfind` selects the last sentence end
   ≤ budget, so for normal prose the loss is a few words. Only degenerate input (a single early period, then a
   long punctuation-free run) would over-trim. Real articles won't hit this; flagging only for completeness. An
   optional guard: keep the hard word-clip if the sentence backoff would discard more than, say, 20% of the budget.

---

## Recommended before launch sign-off
Run the spec's integration tests (Kiro's last open item), specifically:
- New/over-quota user: set `news_per_period=2`, expect 200, 200, **429**.
- **DB-down → 503** (not 200) with an unreachable `DB_HOST`; restore and confirm 200.
- **Anonymous → 401**, and verify **no** `article_requests` row was created.
- **Long article capped:** free user (budget 1500), submit ~6000 words → stored narration ≤ ~1500 words, truncation logged; submit ~300 words → unchanged.

## Cross-references
- Spec: `claude_review_news_quota_failclosed_news_minutes_2026_06_10.md`.
- Tour-quota review (the decoupled-counting + fail-open issues this implementation correctly avoids):
  `claude_review_per_user_quota_implementation_2026_06_10.md`.

## Scope
Services-only review. Mobile handling of the new 401/503 responses (the app currently handles 429) is a
Mobile-AQ item and out of scope here.
