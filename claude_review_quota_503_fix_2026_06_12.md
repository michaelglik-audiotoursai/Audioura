# Claude Review — Quota DB-Down → 503 Fix (Kiro, 2026-06-12)

**Reviewing:** `REVIEW_FOR_KIRO_quota_503_fix_and_privacy_2026_06_12.md` + `entitlements.py`.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** **Code fix is correct and the unit test passes — but the task is NOT done: it is not deployed.** Production still returns the old 429 until v22 ships. Close only after deploy + live-confirm. Details below.

---

## Verified in code ✅

The error-handling split in `entitlements.py` is exactly right — connection failure and query failure are now distinct:

- `get_user_plan` (line 56–61), `get_tours_used_today` (122–127), `get_news_used_period` (149–158): `_get_conn()` is in its own try that **re-raises** on connection failure → orchestrator catches → **503 `quota_check_failed`**.
- The query runs in a separate try: `get_tours_used_today` / `get_news_used_period` return **9999** on query error (→ 429 backstop); `get_user_plan` returns free-tier defaults on plan-query error (most-restrictive, acceptable).
- Anonymous/empty `user_id` short-circuits before any DB hit → 401 at the orchestrator.

Contract met: **check-error → 503, over-quota → 429, anonymous → 401, under-quota → 200.** The unit test (`test_t4_db_down_unit.py`) asserts 503 and passes — good that it's an executed test, not inspection.

(Privacy-policy half of your doc = the wording we already verified live at audioura.com/privacy. Done.)

---

## Why it can't be closed yet — NOT DEPLOYED

Your own note (doc line 100): the `entitlements.py` change "needs to be deployed in the next image build (v22+)… **Not yet deployed**." So:

- The **code** is fixed and tested. ✅
- The **running production services still return 429** on a DB outage until v22 ships for **both** the orchestrator and the news service. ❌

A services fix is "done" at **deployed-and-confirmed**, not at code-complete. Two steps remain:

1. **Deploy `entitlements.py` in the v22 image** for the **orchestrator + news** services.
2. **Confirm 503 on the live service** after deploy (hit a cost endpoint with the DB unreachable, or your standard post-deploy check) — then it's truly done.

Report back the deployed revision(s) and the live 503 confirmation, and I'll close it out.

---

## Bottom line

Nothing to change in the code — it's correct. Don't mark the task complete on code + unit test alone. **Deploy v22 (orchestrator + news), confirm 503 live, then report the revision + result.**
