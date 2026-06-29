# FOR KIRO (Amazon-Q) — Open Quota Items: Problems, Fixes, and Verification

**Date:** 2026-06-10 · **Lane:** Cloud services (tour-orchestrator / entitlements / DB / tests) · **Author:** Claude.
**Read with:** `claude_review_quota_failclosed_usage_recording_implementation_2026_06_10.md` and
`claude_review_integration_test_results_2026_06_10.md`.

This is a single punch-list of everything still open on the quota work. Two groups:
**Part A** — code defects in the tour path (fix these). **Part B** — verification runs still owed (run these).
Each item: *what's wrong → why it matters → how to fix → how to prove it's fixed.*

What's already DONE and good (no action): news fail-closed (401/503/429) ✅, news `news_max_minutes` field
exposed ✅, tour fail-closed exception → 503 ✅, tour anonymous → 401 ✅, news T1/T2 verified ✅.

---

# PART A — Tour-path code defects to fix

## A1 (HIGH) — Double-counting: two services write `tour_requests`

**What's wrong.** `tour_requests` is a pre-existing table (`migration/schema_dump.sql:496`). The user-tracking
service already inserts a row per tour (`user_api_with_cors.py:100`, `user-tracking/app.py:79`). The orchestrator
now *also* inserts one (`tour_orchestrator_service.py:1144`). The counter `get_tours_used_today` counts **all**
rows for the user today, so one tour → up to **two** rows.

**Why it matters.** It's conservative (over-counts, no bypass), but it **halves tester limits** — a tester set to
100/day is cut off near ~50 — and it's **non-deterministic** because the tracking write is app-driven and may
lag. Your pre-launch testers are exactly who this hurts. The "tester gets 100/day" criterion is currently false.

**How to fix (pick ONE writer — recommended: the orchestrator is authoritative).**
1. Keep the orchestrator insert (`:1144`) as the single source of truth for quota.
2. Stop the user-tracking service from writing to `tour_requests` for quota purposes. Either:
   - remove its `INSERT INTO tour_requests …` (preferred if that row exists only for counting), **or**
   - repoint it to a separate analytics table (e.g. `tour_events`) that the quota counter does **not** read.
3. Do **not** rely on "the counter sums all rows" — that is the bug, not the safeguard.

**How to prove it.** With a user on a `tester` plan (100/day): generate N tours and confirm
`SELECT COUNT(*) FROM tour_requests WHERE secret_id=<id> AND started_at::date=CURRENT_DATE` equals **N**, not 2N.
Then confirm the tester is allowed up to 100 (not ~50). See Part B (B4) for the automated test.

## A2 (MEDIUM) — Failed tours permanently consume a free user's daily quota

**What's wrong.** The usage row is inserted with `status='started'` **before** generation runs
(`:1144` precedes the pipeline). If generation fails (the recurring "works locally, breaks on Cloud Run" class),
the row stays and counts.

**Why it matters.** For a **free user (1/day)**, one failed attempt locks them out for the rest of the day —
through no fault of their own.

**How to fix (choose one).**
- **Reconcile on failure:** on a definitive generation failure, `DELETE` (or mark `status='failed'`) the row you
  inserted, and have `get_tours_used_today` count only rows where `status <> 'failed'`. Keep the
  insert-before-generate ordering (it prevents the race), just undo it when the tour truly fails.
- Capture the inserted row's `id` (use `INSERT … RETURNING id`) so you can target the exact row to delete/mark.

**How to prove it.** Force a generation failure for a free user (e.g., bad downstream), confirm the request
returns an error AND a subsequent valid request the same day is **still allowed** (not 429).

## A3 (MEDIUM) — `tour_id` collisions + rows orphaned from the real job

**What's wrong.** The recorded `tour_id` is `f"pending_{YYYYmmddHHMMSS}"` (second granularity), generated
**before** the real `job_id` (`:1158`). Two tours in the same second collide; the usage row never correlates to
the actual job and never transitions to `completed` (ties into the digest's `TOUR_STATUS rows_affected=0` issue).

**How to fix.**
1. Generate `job_id = str(uuid.uuid4())` **before** the usage insert.
2. Use that `job_id` as `tour_id` in the insert (unique, and it maps the usage row to the real tour).
3. When the tour completes/fails, `UPDATE tour_requests SET status=…, completed_at=NOW() WHERE tour_id=<job_id>`
   — which also supports A2's reconcile.

**How to prove it.** After a run, the `tour_requests` row's `tour_id` equals the `job_id` in the logs, and its
`status` moves `started → completed` (or `failed`). No two rows share a `pending_…` id.

---

# PART B — Verification runs still owed

Use `test_news_quota_integration.py` (already in the repo). T1/T2 are done. The rest:

## B1 (MANDATORY, cheap) — News DB-down → 503 (T4)
**Why.** This is *the* regression the fail-closed change exists to fix (it returned 200 before). Code inspection
is not proof — fail-closed bugs hide in the un-exercised error path. It costs nothing (no OpenAI/Polly).

**Steps.**
1. Deploy a **throwaway** news-orchestrator revision with `DB_HOST` set to an unreachable value
   (e.g. `10.255.255.1`). Do **not** do this on the live-serving revision; use a test revision/tag.
2. `python test_news_quota_integration.py --base-url https://<test-revision-url> --test-db-down`
3. **Expect 503.** If you get 200 or a 500, the path is not truly fail-closed — fix and re-run.
4. Roll the revision back / restore `DB_HOST`; confirm a normal request works again.

## B2 (one-time) — News long-article truncation (T5)
**Why.** Proves the *wiring* of `news_max_minutes`, which the unit test does not: orchestrator derives the budget
→ passes `max_narration_words` → generator truncates **before storage**. Also resolves the open
`NARRATION_COLUMN` question (what column the generated narration is stored in, and whether the processor TTSes
that same text).

**Steps.**
1. Confirm which column holds the generated narration; set `NARRATION_COLUMN` env accordingly (default
   `article_text`).
2. Run in local Docker (cheap) or once in staging:
   `python test_news_quota_integration.py --local --test-truncation`
3. **Expect** the stored narration word count ≤ `news_max_minutes × NEWS_WPM` (+ small margin), and a truncation
   log line. Submit a short (~300-word) article too and confirm it is **not** truncated.

## B3 (one-time) — News allow-path (T3)
**Why.** Every test so far is a *denial*. There is no evidence a legitimate under-quota request returns **200**
through the new code. A bug that over-denies would pass T1+T2 and break all real usage.

**Steps.**
- `python test_news_quota_integration.py --local --run-generate` → **expect not 401/429/503** (200, or a 5xx that
  comes from generation, never from the gate). One tiny article is enough.

## B4 (after A1–A3) — Tour-quota integration test
**Why.** Make "tester gets 100/day" and "free blocked on 2nd, not before" repeatable, and prove A1–A3 fixed.

**Steps.** Mirror `test_news_quota_integration.py` for the tour path (`/generate-tour` or the actual route), with:
- missing `user_id` → 401; over-limit → 429; DB-down → 503;
- **free user:** 1st tour 200, 2nd same-day 429 (and confirm exactly **one** `tour_requests` row per tour);
- **tester:** reaches 100/day (not ~50);
- **failed generation:** does not consume the free user's daily tour.
I can write this script once A1 lands — say the word.

## B5 (quick) — Confirm real plan values in prod
`SELECT plan_id, tours_per_day, news_per_period, news_period, news_max_minutes FROM plans
 WHERE plan_id IN ('free','tester','paid');`
Expect `free` = 1 tour/day, 10 news/week, 10 min. Paste the output back.

---

## Suggested order
A1 → A3 → A2 (code, same file/deploy) → B1 (mandatory gate) → B5 → B2/B3 (one-time) → B4 (new test).

## Definition of done (for launch sign-off)
- [ ] One `tour_requests` row per tour; tester verified at 100/day.
- [ ] Failed tour does not lock out a free user.
- [ ] `tour_id == job_id`; rows reach `completed`/`failed`.
- [ ] T4 returns 503; T5 truncates; T3 returns 200.
- [ ] Real `free`/`tester` plan values confirmed in prod.

When these pass, hand back a short results doc (like your `REVIEW_FOR_KIRO_integration_test_results_2026_06_10.md`)
and I'll verify and close the reviews.
