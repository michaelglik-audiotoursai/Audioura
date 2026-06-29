# For Kiro Amazon-Q — Entitlements/Flask Review Confirmed + Next Task

**Date:** 2026-06-08
**Scope:** Services/GCloud only.

---

## Part 1 — Your entitlements + Flask session: ✅ verified, approved
I checked every claim in `REVIEW_FOR_KIRO_entitlements_and_flask_fixes_2026_06_08.md` against the code:
- `generate_tour_text_service.py:198` → `download_name` ✅ (no `attachment_filename` left anywhere; `before_first_request`/`flask.json` audit clean).
- `entitlements.py`: `get_news_used_period` is per-user (`WHERE secret_id=%s`) with a real `'week'` branch (`date_trunc('week', …)`, default `period='week'`) ✅; `get_user_plan` is now user-first (`FROM users u JOIN plans p ON u.plan=p.plan_id WHERE u.secret_id=%s`) ✅; counts **fail closed** (`return 9999`) ✅; `tour_max_minutes` documented as POI-clamp proxy ✅.
- `news_orchestrator_service.py`: `check_news_quota` wired with `429` on denial ✅; tour-orchestrator already had `check_tour_quota`.

Good, clean session. Three **advisory** notes (non-blocking, track for production — do NOT need to fix before the deploy):
1. **`news_max_minutes` (10 min/article) is not actually enforced.** "Bounded by input text" doesn't cap it — a long newsletter could yield >10 min audio. For the free tier's "10 min max per article", you'd need to truncate the article text (~9k chars) before TTS, or cap the audio. Minor; fine for now.
2. **The news-quota wrapper fails OPEN on exception**, which is sensible for the test phase — but it means if `entitlements.py` isn't in the news-orchestrator image, the quota silently doesn't apply. **Deploy note:** confirm `entitlements.py` is bundled into news-orchestrator (and tour-orchestrator) images.
3. **Anonymous user_id bypasses quota** entirely. Fine while the X-API-Key gates the gateway; for production consider rejecting anonymous on cost endpoints.

---

## Part 2 — NEXT TASK: deploy + verify the Cloud Tasks pipeline (remind_kiro item #4)
The code is ready (`tour_worker_service.py`, orchestrator dual-mode, `setup_cloud_tasks_queue.sh`) but **nothing is deployed** — and this deploy is what activates this session's changes (entitlements wiring, the Flask fix, news quota). It unblocks the end-to-end RU/KO retest (#5). Do it in this order:

1. **⚠️ FIRST — bump the test-phase quota** so your own testing isn't throttled to 1 tour/day now that `check_tour_quota` is wired in:
   `UPDATE plans SET tours_per_day=100 WHERE plan_id='free';` (tighten back to 1 before launch).
2. `gcloud services enable cloudtasks.googleapis.com`.
3. Run `migration/setup_cloud_tasks_queue.sh` and **confirm the 3 IAM bindings actually took effect** (the most likely snag): worker-invoker SA → `run.invoker` on tour-worker; orchestrator SA → `cloudtasks.enqueuer` on the queue; orchestrator SA → `iam.serviceAccountUser` on the invoker SA.
4. Deploy **tour-worker** (`--timeout=840 --concurrency=1 --min-instances=0 --max-instances=5 --no-allow-unauthenticated`, with the same secrets).
5. Flip the orchestrator env: `GENERATION_MODE=cloud_tasks`, `JOB_STORE_MODE=database`, plus `TOUR_WORKER_URL` and `WORKER_SERVICE_ACCOUNT`.
6. **Remove the interim always-on flags** from the orchestrator (`--cpu-throttling --min-instances=0`) so it scales to zero (~$30/mo idle → ~$0).
7. **Verify:** generate one tour → `gcloud tasks list` shows it dispatched → worker logs show `[RUN-JOB]` → `/status/<job_id>` reaches `completed` (read from DB). Then force a retry (or simulate a lost response) and confirm the worker logs `already completed — skipping` (idempotency). Confirm a backend `*.run.app` still returns 403 directly (IAM lock intact).
8. **Then** the full end-to-end retest can run: generate → download (`/download/<jobId>`) → translate RU + KO → download translated (map-delivery).

---

## Part 3 — YOUR responsibility now: maintain `remind_kiro.md`
**`remind_kiro.md` is now yours to keep current.** Kiro chat sessions are stateless — when a session ends, the next one starts cold and recovers ONLY by reading `remind_kiro.md`. So:
- **At the end of every session** (and after each meaningful change/deploy), update `remind_kiro.md` — move finished items out of the OUTSTANDING list, add new ones, record what was deployed (image/revision), and note anything in-flight.
- Keep the "OUTSTANDING — start here" section accurate and prioritized; that's what a fresh session reads first.
- To resume after a dropped session, a new Kiro just runs: *"Read development/remind_kiro.md and resume where we left off."*
Treat keeping it accurate as part of finishing each task — it's your memory across sessions.

---

## Bottom line
Entitlements + Flask session approved (verified in code). **Next: deploy and verify the Cloud Tasks pipeline** (bump the test quota first; confirm the 3 IAM bindings; verify enqueue→worker→completed + idempotency; drop the always-on flags), which activates this session's code and unblocks the RU/KO end-to-end retest. And from now on, **keep `remind_kiro.md` updated yourself** so the next stateless session can pick up instantly.
