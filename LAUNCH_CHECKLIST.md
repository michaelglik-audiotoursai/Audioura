# Audioura — Store Launch Checklist (v1 Market-Interest Release)

**Target launch date:** July 1, 2026 · **Created:** June 10, 2026
**Goal:** Installable, store-approved v1 of Audioura on Apple App Store + Google Play to test real-user interest.

Status key: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocker / at-risk

---

## 0. CRITICAL PATH — read first

**Resolved approach:** Audioura LLC (registered in MA) → register Play as an **Organization account**, which is
**EXEMPT** from the 14-day / 12-tester closed-test rule (that rule is personal accounts only). No closed test required.

- `[x]` **D-U-N-S number obtained for Audioura LLC: `14-114-4094`.** Android critical path cleared.
  Use this number for both Play (Organization) and Apple (Organization) enrollment.
- `[ ]` Register Play Console as **Organization** (Audioura LLC, D-U-N-S 14-114-4094) — no 14-day test.
- `[ ]` Enroll Apple Developer Program as **Organization** (same D-U-N-S, seller = "Audioura LLC").
  *(Alternative if you want iOS moving instantly: Individual enrollment, no D-U-N-S, seller = personal name.)*

---

## 1. Store accounts (Owner: Sir Michael) — do first, blocks everything

- `[ ]` Apple Developer Program enrollment — **$99/yr** (individual or org). Allow 24–48h for Apple verification.
- `[ ]` Google Play Console account — **$25 one-time**. Register as **Organization** (Audioura LLC) using the D-U-N-S — exempts you from the 14-day test (see §0).
- `[ ]` Set up App Store Connect app record (bundle ID, name "Audioura").
- `[ ]` Create Play Console app entry (package name, app name).

## 2. Launch-gating code fixes (must close before any store test)

- `[ ]` **Per-user quotas** — revert global override (`free`=1/day) and add per-user tiering: testers high, public default 1, changeable via SQL with no redeploy; future paid/phone-verified tier. Spec: `claude_review_per_user_quota_2026_06_10.md`. *(Kiro)*
- `[ ]` Enforce `news_max_minutes`; fix news-quota wrapper fail-OPEN → fail-CLOSED. *(Kiro)*
- `[ ]` Close anonymous `user_id` quota bypass. *(Kiro)*
- `[ ]` **Fix tour-type classification regression (v13)** — make `_MULTI_BUILDING_INSTITUTION_RE` plural-only so single-venue libraries/churches/schools classify as museum again. *(Kiro)*
- `[ ]` **Fix existing/downloaded-tour translation returns English** — app download flow must fire a `translate-with-audio` request like generation does (server ready: de/Marlene). *(Mobile-AQ)*
- `[ ]` **Wire app to cloud news endpoints** — `/news-status/<id>`, `/news-articles`, `/generate-news`, `/news-download/<id>`. *(Mobile-AQ)*

## 3. Security / posture decisions (decide before public installs)

- `[!]` **MUST-SHIP v1 — Anti-mimicry app attestation.** Extracted `X-API-Key` must not let an illicit client drive cost-bearing services. Verify **Play Integrity** (Android) + **App Attest** (iOS) **server-side** on `/generate-complete-tour`, `/generate-news`, translate endpoints; reject forged/missing/replayed → 403. Each store's first build carries its platform's attestation. Docs: `claude_review_app_attestation_and_budget_for_kiro_2026_06_11.md` *(Kiro)* + `REVIEW_FOR_MOBILE_AQ_app_attestation_2026_06_11.md` *(Mobile-AQ)*.
- `[!]` **MUST-SHIP v1 — Hard GCP spend cap (backstop).** Cloud Run `--max-instances` on cost-bearing services + Billing budget + automated kill-switch at 100% (budgets alert only; a Pub/Sub→Function is needed for a true stop) + alerts to Sir Michael. *(Kiro)*
- `[ ]` Confirm raw-SQL endpoints (`:5003`, `execute_sql`, `/sql`, `/postgres/direct`, `/decrypt_credentials`) remain non-public in `gateway_routes.yaml`. *(Kiro)*
- `[!]` **CONFIRMED RISK: news subscription passwords stored in PLAINTEXT at rest.** `user_subscription_credentials` has `decrypted_username`/`decrypted_password` (varchar) and `newsletter_processor_service.py` (~line 2340) inserts the decrypted username+password. Encrypted in transit only. **Fix before real users connect logins:** migrate to the session-token model (log in, keep only the session/cookies — industry standard) OR encrypt credentials at rest. Privacy policy + Data Safety/Nutrition disclose handling honestly (done). *(Kiro — launch-gating security fix)*

## 4. Privacy & permissions (drafts provided — see other files)

- `[ ]` Host **PRIVACY_POLICY** at a public HTTPS URL (e.g. audioura.app/privacy or a GitHub Pages site). *(Sir Michael)*
- `[ ]` Add **iOS Info.plist usage strings** for mic + location (see PERMISSION_JUSTIFICATIONS). *(Mobile-AQ / iOS-AQ)*
- `[ ]` Add **Android runtime permission rationale** UI copy for mic + location. *(Mobile-AQ)*
- `[ ]` **In-app account & data deletion path** — required by Apple, expected by Google. Hard review blocker. *(Mobile-AQ)*

## 5. Android packaging (Owner: Mobile-AQ + Sir Michael)

- `[ ]` Configure signing (upload key / Play App Signing).
- `[ ]` Build signed **release App Bundle (.aab)**.
- `[ ]` Confirm **target API level** meets current Play requirement (API 35 / Android 15 era — verify in Console).
- `[ ]` Complete **Data Safety form** (declare mic, location, account data; match privacy policy).
- `[ ]` Complete **content rating** questionnaire (IARC).
- `[ ]` Write permission justifications for mic + location in listing.
- `[ ]` Upload to **internal testing** track → then **closed testing** (and run 14-day test if §0 applies).

## 6. iOS packaging (Owner: iOS-AQ + Sir Michael)

- `[ ]` Configure signing & provisioning (App Store distribution profile).
- `[ ]` Archive signed build in Xcode → upload to App Store Connect.
- `[ ]` Complete **Privacy Nutrition labels** (match privacy policy).
- `[ ]` Add mic + location **usage description strings** (Info.plist).
- `[ ]` Confirm in-app **account deletion** present (Apple checks this).
- `[ ]` Push build to **TestFlight**, smoke-test on device.
- `[ ]` Submit to **App Store review** (allow 1–3 days; can be longer).

## 7. Store listing assets (Owner: Sir Michael)

- `[ ]` App icon (1024×1024 for iOS; Play adaptive icon).
- `[ ]` Screenshots — iPhone (6.7" + 6.5") and Android phone sizes.
- `[ ]` Listing copy: title, subtitle/short description, full description, keywords.
- `[ ]` Support URL + marketing/contact email (glikfamily@gmail.com or a support alias).
- `[ ]` Version number (1.0.0) + build number.

## 8. Pre-launch verification (Owner: Claude + Sir Michael)

- `[ ]` End-to-end smoke test on real iPhone: generate tour → translate (incl. existing-tour de) → news flow → map pins.
- `[ ]` Smoke test on real Android device from the testing track.
- `[ ]` Crash/analytics wired (Firebase Crashlytics free tier) and reporting.
- `[ ]` Confirm account-deletion flow actually deletes data server-side.

**Quota verification gates (Owner: Kiro):**

Code fixes — all landed & reviewed (deployed `audioura:v19`):
- `[x]` Per-user tiers (free=1/day, tester=100, paid=10); SQL-only, no redeploy.
- `[x]` Tour + news quota fail-CLOSED (missing id → 401, check error → 503, over → 429).
- `[x]` Tour double-count fixed (counter = `source='orchestrator'`; column default `'tracking'`).
- `[x]` Failed tour rolls back usage row on BOTH paths (orchestrator thread + worker cloud_tasks final attempt).
- `[x]` `tour_id == job_id` (UUID). News `news_max_minutes` enforced via word-budget truncation.

Verification still owed (the remaining gate before sign-off):
- `[!]` **News DB-down → 503 (T4) — MANDATORY, not yet run.** Core fail-closed regression; cheap/non-generative.
- `[ ]` **Tour-quota integration test (B4)** — script written (`test_tour_quota_integration.py`); **run it** (cheap gate tests + `--run-generate` for single-count + manual `--check-rollback` for worker rollback).
- `[ ]` News long-article truncation (T5) — run once locally; confirm stored narration ≤ budget + narration-column/TTS target.
- `[x]` Allow-paths proven: news 401/429 (T1/T2); tour anonymous→401 and tour allow→200 queued. *(2026-06-10)*
- `[x]` Real plan values confirmed in prod (free 1/10/wk/10min; tester 100/100/wk/30; paid 10/50/wk/30).
- `[ ]` Confirm Cloud Tasks queue `maxAttempts == MAX_TASK_ATTEMPTS` env (rollback correctness depends on it).

## 9. Go-live (Owner: Sir Michael)

- `[ ]` iOS: release approved build to App Store.
- `[ ]` Android: promote to production (or closed-testing public link if §0 blocks production).
- `[ ]` Tag the release commit; record version in this repo.

---

## Owners summary
- **Sir Michael:** accounts, billing budget, listings, privacy policy hosting, go-live, final decisions.
- **Kiro (cloud):** quotas, classification regex, gateway/security, budget alerts.
- **Mobile-AQ (Android):** existing-tour translation, news endpoints, account-deletion, permission rationale, AAB.
- **iOS-AQ:** signed iOS build, TestFlight, Info.plist strings.
- **Claude:** verification, this checklist, drafts, plan tracking.
