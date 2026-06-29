# CLAUDE REVIEW — Kiro's News-Quota Integration Test Results

**Date:** 2026-06-10 · **Lane:** Cloud services (test verification) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_integration_test_results_2026_06_10.md` (Kiro).
**Tests under review:** `test_news_quota_integration.py` + `db-job/run.py` (T2 harness).

## Verdict: PARTIAL PASS — T1 & T2 genuinely verified; NOT yet enough for launch sign-off

The two executed tests are real and correctly automated — I confirmed the T2 harness against the code. But the
campaign proves only the **deny** behavior. The single most important regression (DB-down → 503), the entire
`news_max_minutes` truncation path, and *any* successful allow-path remain unverified. Two of the three "skipped"
risk ratings are too low.

---

## What I independently confirmed
- **T2 harness is faithful (`db-job/run.py`):** creates `itest` plan with `news_per_period=1`, assigns
  `ITEST-NEWS-QUOTA`, clears prior usage, seeds exactly one usage row, verifies the count with the same
  `date_trunc('week', …)` query entitlements uses, calls `/generate-news`, asserts 429, then **deletes the rows,
  user, and plan**. So "no test data persists" is accurate. (`db-job/run.py:29–78`)
- **T2 response body is consistent with the real code:** the reported
  `{"error":"quota_exceeded","limit":"news_per_period","max":1,"used":1,"news_max_minutes":10,…,"plan":"itest"}`
  matches `entitlements.check_news_quota`'s denied dict (`entitlements.py:205–216`), including the `news_max_minutes`
  field — so Change 2 (field exposure) and the 429 gate are genuinely proven.
- **T1 (401)** is a pure HTTP assertion against the live gateway and is credible.

Conclusion: T1 and T2 are **legitimate passes**, well-isolated, and reproducible. Good.

---

## Assessment of the skipped tests (my severity vs Kiro's)

| Test | Kiro's rating | My rating | Why |
|---|---|---|---|
| T4 — DB down → 503 | Medium, deferred | **HIGH / mandatory** | This is *the* regression the change exists to fix (was 200, must be 503). "Code inspection confirms" is not behavioral proof — fail-closed bugs live precisely in the un-exercised error path (an uncaught exception type, a hung connection that never raises, a downstream 500 instead of the orchestrator's 503). **And it costs nothing** (no OpenAI/Polly): point a test revision's `DB_HOST` at a dead value, fire one request, assert 503, restore. There is no good reason to defer this one. |
| T5 — truncation | Low | **MEDIUM** | The pure function `truncate_to_word_budget` is unit-verified (I ran it), but that does NOT prove the wiring: orchestrator deriving the budget from the quota, passing `max_narration_words`, and the generator truncating *before storage*. That's three integration points, plus the still-unconfirmed `NARRATION_COLUMN` / what the processor actually sends to TTS. It's the whole `news_max_minutes` half of the spec — run it once before relying on the minutes cap. |
| T3 — under quota passes | Low | **MEDIUM** | Every observed response in this campaign is a *denial* (401/429). There is zero end-to-end evidence that a legitimate under-quota request returns **200**. A bug that over-denies (e.g., a missing key throwing → 503 for everyone) would pass T1+T2 and break all real usage. Kiro's "self-evidencing once real users hit it" only holds *post-launch* — pre-launch there's no signal. Confirm at least one allow-path (cheaply: local Docker, or one tiny article). |

The "costs money" framing for T3/T5 is overstated: the full suite runs in **local Docker** (`--local
--run-generate --test-truncation`) with short inputs, so these are runnable cheaply once — not blocked, just not yet done.

---

## Minor notes
- T2 exercised a synthetic `itest` plan, not the real `free` plan (correct for isolation). Worth a one-line
  `SELECT plan_id, news_per_period, news_period, news_max_minutes FROM plans WHERE plan_id='free';` against prod
  to confirm the real launch values are present (10/week/10min).
- Re-run instructions are clear and the harness tears down cleanly — good operational hygiene.

---

## Required before treating the news-quota work as launch-verified
1. **Run T4 (DB-down → 503)** — mandatory, cheap, non-generative. The core regression proof.
2. **Run T5 once** — confirm a long article is actually stored truncated to the budget (and resolve the
   `NARRATION_COLUMN` / TTS-target question from `claude_review_news_quota_failclosed_implementation_2026_06_10.md`).
3. **Confirm one allow-path (T3)** — at least one 200 through the new code (local Docker is fine).
4. Spot-check real `free` plan values exist in prod.

Until 1–3 are done, the news path is **deny-verified but not allow/enforce-verified** — fine to keep moving, but
not yet a green check for launch.

## Cross-references
- Implementation review: `claude_review_news_quota_failclosed_implementation_2026_06_10.md`.
- Test script + case definitions: `test_news_quota_integration.py`.
- Note for parity: the tour-quota path still has the open double-counting fix
  (`claude_review_quota_failclosed_usage_recording_implementation_2026_06_10.md`) and will need its own
  equivalent test run.
