# Claude Code Review — Session Digest (as of 2026-06-10)

Compact cross-session context. Claude is the **independent code reviewer** for Audioura: read each agent's
hand-off doc, verify claims against actual code/logs, write **agent-scoped** review docs.

> **NORTH STAR — FIRST RELEASE TO STORES (target July 1, 2026).** Make Audioura installable from Google Play
> (Android) + Apple App Store (iOS) for a real-install interest test. Master plan/tracker:
> **`LAUNCH_CHECKLIST.md`** — start there. (Next-version architecture is a separate chat; out of scope here.)

## Project
- **Audioura** — AI audio-tour-guide app. Flutter/Dart (Android + iOS) + ~12 Python/Flask microservices on
  **Google Cloud Run** (project `audiotours-migration`, region `us-central1`). Owner: Sir Michael.

## Agents & lane rules (operational — keep)
- **Kiro Amazon-Q** — cloud services/GCloud. Hand-offs `REVIEW_FOR_KIRO_*.md`; my reviews `claude_review_*.md`.
- **Mobile Amazon-Q** — Android Flutter (`audio_tour_app/`). My docs `REVIEW_FOR_MOBILE_AQ_*.md`.
- **iOS Amazon-Q** — iPhone build (inherits shared commits). **Strategic Advisor.**
- **HARD RULE:** one doc per agent; never mix services + mobile in one file; never edit `audio_tour_app/` in
  Kiro's lane or services in Mobile's lane.
- **Naming:** Kiro writes `REVIEW_FOR_KIRO_`; I write `claude_review_*` (Kiro) / `REVIEW_FOR_MOBILE_AQ_*` (Mobile)
  so I never overwrite Kiro's files. `remind_kiro.md` = Kiro's memory.

## Architecture essentials (stable)
- **api-gateway** — YAML-driven (`api-gateway/gateway_routes.yaml`); routes by **ROOT path**
  (`cloud_use_path_prefixes` stays **false**). `auth: api_key` → `X-API-Key` fail-closed; service-to-service OIDC;
  backends `--no-allow-unauthenticated`. Every backend endpoint must be in the YAML or it 404s on cloud.
- **tour_orchestrator_service.py** — dual-mode dispatch: `GENERATION_MODE='cloud_tasks'` (prod) enqueues to Cloud
  Tasks → **tour_worker_service.py** runs generation; else thread fallback. **Any usage-lifecycle logic must cover
  BOTH paths.**
- **generate_tour_text.py** — tour text/POI pipeline; `_classify_tour_category` → restaurant|walking|museum|specialized.
- **translation-service/translation_service.py** — single source of truth; voices incl. `ru:Tatyana, zh:Zhiyu, ko:Seoyeon, de:Marlene`.
- **entitlements.py** — per-user quotas via `users.plan` → `plans` table; fail CLOSED.

## Security constraints (preserve)
- Raw-SQL endpoints (`:5003`, `execute_sql`, `/sql`, `/postgres/direct`) NEVER public; `/decrypt_credentials` `internal_only`.
- X-API-Key is **extractable from the APK** → not a real boundary. **Owner decision (2026-06-11): anti-mimicry app
  attestation is now a MUST-SHIP v1 gate** (not deferred). Verify Play Integrity (Android) + App Attest (iOS)
  server-side on cost endpoints (header `X-App-Attestation`; protected: `/generate-complete-tour`,
  `/translate-with-audio`, `/generate-complete-tour-background`); roll out log-only → enforce. **Hard GCP spend cap**
  (Cloud Run max-instances + budget + kill-switch) ships regardless = the backstop. Docs:
  `claude_review_app_attestation_and_budget_for_kiro_2026_06_11.md` (Kiro) +
  `REVIEW_FOR_MOBILE_AQ_app_attestation_2026_06_11.md` (Mobile).
- **News subscription passwords stored PLAINTEXT at rest** (`user_subscription_credentials.decrypted_*`). Fix to
  session-token model or encrypt-at-rest before real users connect logins. **Owner: Kiro** (LAUNCH_CHECKLIST §3).
- Secret Manager: avoid `\r\n`. Pin `Flask==2.3.3`.

## Recurring failure class
"Works locally, breaks on Cloud Run": CPU-throttle stalls post-response work (→ Cloud Tasks); Secret `\r\n`;
`debug=True` port-binding. "Reachable locally, 404 on cloud" = endpoint missing from `gateway_routes.yaml`.

## Quota work — DONE & reviewed (deployed `audioura:v19`)
Per-user tiers (free=1 tour/day, tester=100, paid=10; news free=10/wk≤10min; SQL-only changes). Tour+news quota
**fail-CLOSED** (missing id→401, check error→503, over→429). Tour **double-count fixed** (counter
`source='orchestrator'`; column default `'tracking'`). **Failed tours roll back** on both orchestrator(thread) +
worker(cloud_tasks final-attempt). `tour_id==job_id`. News **`news_max_minutes` enforced** (word-budget truncation
in generator). Reviews: `claude_review_*quota*_2026_06_10.md` (latest: `..._double_count_final_fix_implementation_`).
**Remaining = verification only** (see LAUNCH_CHECKLIST §8): **News DB-down→503 (T4, mandatory, not run)**;
**tour-quota integration test (B4, to write — mirror `test_news_quota_integration.py`)**; news truncation T5 (run
once local); confirm Cloud Tasks queue `maxAttempts == MAX_TASK_ATTEMPTS`.

## Other open launch items
- **Tour-type classification regression (v13).** `_MULTI_BUILDING_INSTITUTION_RE` matches singular words → blocks
  museum for single-venue libraries/churches/schools. Fix = plural-only regex. Map pins safe (v12). **Owner: Kiro.**
- **Existing/downloaded-tour translation returns English** — app download flow doesn't fire `translate-with-audio`
  (server ready, de/Marlene). **Owner: Mobile-AQ.**
- **News cloud paths** — app must call `/news-status/<id>`, `/news-articles`, `/generate-news`, `/news-download/<id>`.
  **Owner: Mobile-AQ.**
- **In-app account/data deletion** — required by Apple/Google. Docs written: `REVIEW_FOR_MOBILE_AQ_launch_gating_2026_06_11.md`
  (app UI) + `claude_review_account_deletion_endpoint_for_kiro_2026_06_11.md` (server full-erase). **Contract to
  agree:** Mobile doc expects `DELETE /user/<id>` on `Service.userDb` (user-api `:5003`); Kiro doc proposed
  `/delete-account/<secret_id>`. ⚠️ `:5003` is the NEVER-public raw-SQL service — gateway must expose ONLY the delete
  route, and the endpoint must erase ALL personal tables incl. `user_subscription_credentials`. **Owners: Mobile-AQ + Kiro.**
- The 3 app blockers (account-deletion, news cloud paths, existing-tour translation) are speced in
  `REVIEW_FOR_MOBILE_AQ_launch_gating_2026_06_11.md`. **Owner: Mobile-AQ.**
- `TOUR_STATUS rows_affected=0` — completion write key mismatch (string vs int id). **Owner: Mobile-AQ.**

## Store launch status (LAUNCH_CHECKLIST.md is the tracker)
- **Accounts:** Audioura LLC (MA) has **D-U-N-S 14-114-4094** → register Play + Apple as **Organization**
  (Play org = exempt from the 14-day/12-tester closed-test rule). Apple $99/yr, Play $25 one-time.
- **Privacy/permissions drafted:** `PRIVACY_POLICY.html` (host at HTTPS URL), `PERMISSION_JUSTIFICATIONS.md`
  (mic+location; users identified by `device_id`, no email account; subscription-credential disclosure included).
- **Plan to July 1:** `RELEASE_PLAN_JULY1.md`. iOS achievable if fixes land wk1 + submit Apple review by ~Jun 26.

## Quota verification (remaining; not blockers but launch gates)
News DB-down→503 (T4, mandatory, not run); run `test_tour_quota_integration.py` (written, not run) +
`test_news_quota_integration.py --test-db-down`; news truncation T5 (run once local); confirm Cloud Tasks queue
`maxAttempts == MAX_TASK_ATTEMPTS`.

## Key files
- Launch: `LAUNCH_CHECKLIST.md` (master tracker), `RELEASE_PLAN_JULY1.md`, `PRIVACY_POLICY.html`, `PERMISSION_JUSTIFICATIONS.md`.
- Tests: `test_news_quota_integration.py` (+ T2 harness `db-job/run.py`), `test_tour_quota_integration.py`.
- Current hand-offs (2026-06-11): Mobile — `REVIEW_FOR_MOBILE_AQ_launch_gating_2026_06_11.md`,
  `REVIEW_FOR_MOBILE_AQ_app_attestation_2026_06_11.md`; Kiro — `claude_review_account_deletion_endpoint_for_kiro_2026_06_11.md`,
  `claude_review_app_attestation_and_budget_for_kiro_2026_06_11.md`.
- App code IS in repo: `audio_tour_app/lib/` (Flutter). Reviews: `claude_review_*.md` (Kiro), `REVIEW_FOR_MOBILE_AQ_*.md` (Mobile).
- Gateway routing source of truth: `api-gateway/gateway_routes.yaml` (news routes already live).
