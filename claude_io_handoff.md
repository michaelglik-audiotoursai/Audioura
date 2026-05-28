# Claude IO Handoff — Audioura Next Phase: Universal Services Locations

## Purpose

Bootstrap for a fresh Claude IO session driving the **next major project**: migrating Audioura's backend services from LAN-only Docker on Sir Michael's laptop to **Google Cloud (Cloud Run + Cloud SQL Postgres + Cloudflare R2)**, then closing the loop on App Store + Google Play submission.

Mobile-app code is at a known-good stable state. The work ahead is mostly services-side, with mobile-side tail-end changes (replacing hardcoded LAN IPs with the public HTTPS URL once the backend is reachable from the public internet).

Last updated: **2026-05-28** at session close. Previous session shipped A#74 (git history sanitization, removed a leaked-and-revoked GitHub PAT from history without rewriting via filter-repo) and A#75 (InAppWebView v6 migration in `news_player_screen.dart`).

---

## Project

**App:** Audioura — iOS/Android Flutter app. Owner: Sir Michael (glikfamily@gmail.com). Tests on iPhone 16 / iOS 18.3.1.

**Current versions:**
- iOS on iPhone 16: **v1.2.9+65** (A#75 shipped 2026-05-28).
- Android: **v1.2.9+61** — pending rebuild on Ubuntu VM to catch up to A#72 + A#73 + A#75.
- Backend services: 13 Docker containers on Sir Michael's Windows laptop (`192.168.0.218`). LAN-only. Untouched architecturally since the spec was approved 2026-05-04.

**Authoritative specs** (read both before planning):
- `C:\Business\AudioTours.io\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` — 57 KB. The migration plan: 13-service inventory, 5-phase approach (M01 audit → M02 local rehearsal → M03 GCP setup → M04 per-service deploy to PreProd → M05 production cutover). 20–30 hours of focused work.
- `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md` — 11 KB. The store roadmap: 6-phase plan (Phase 0 backend HTTPS → Phase 1 Info.plist → ... → Phase 6 production submission). Phase 0 = completion of migration M04/M05. 4–8 week timeline once M04 lands.

---

## Five Amazon-Q agents you coordinate (through Sir Michael)

Sir Michael relays everything. Sessions don't talk to each other.

| Agent | Identifier | What they own | Remind doc |
|---|---|---|---|
| iOS Amazon-Q | 🍎 iOS AMAZON-Q | Dart code architecture for iOS | `remind_ios_ai.md` |
| Mobile Amazon-Q | 📱 MOBILE APP AMAZON-Q | Android-side Dart + Windows git/build chores | `remind_mobile_ai.md` |
| Mac Mini Kiro CLI | 🍎 MAC MINI KIRO CLI | Executes iOS build assignments on Mac Mini via `kiro-cli chat --trust-all-tools` | `remind_macmini.md` |
| Services Amazon-Q | 🔧 SERVICES AMAZON-Q | Backend services + executes the migration | `remind_Services_ai.md` |
| Strategic Advisor Q | 🎯 STRATEGIC ADVISOR AMAZON-Q | Cross-track coordination, business strategy | `remind_advisor.md` |

**Rule: do NOT edit the `remind_*.md` files. Each Q maintains its own.** When you need to communicate intent or scope to a Q, write a separate `transition_for_<role>.md` file (samples in this folder) and instruct Sir Michael to relay it.

---

## Where the project is right now

**Mobile-app track — stable.** A#74 cleared 14 unpushed local commits (some containing a now-revoked GitHub PAT in `mac_mini_setup_guide.md`) using a reset + reapply strategy with the file sanitized in place. The Newsletters branch is clean. A#75 followed up with the actual InAppWebView v6 migration (the one A#71's commit message claimed but didn't do).

**Services track — ready to begin.** Migration architecture decided. Spec written. No execution yet. Phase A (M01) is the next concrete step — a read-only per-service audit. ~2 hours of Services Q's work. Output: a per-service migration-readiness table that informs everything downstream.

**Mobile changes pending for services-migration completion:**
- ~37 hardcoded `192.168.0.x` references across ~21 Dart files plus `audio_tour_app/.env` `API_BASE_URL=http://192.168.0.217:5002`. Replace with environment-driven config once Services Q delivers a stable PreProd URL.
- `Info.plist` `NSAppTransportSecurity` lock-down (`NSAllowsArbitraryLoads=false`). Currently permissive.
- Retry/backoff policy for WAN-grade latency and intermittent failures.

These are gated by Services Q's M04 (PreProd) completion. iOS Q and Mobile Q should not start them yet.

---

## Operating model

Same as the iOS side has been: Claude IO plans and reviews. Services Q executes. Sir Michael relays.

- **Migration assignments live in `development/migration/MNN_<name>.md`** — to be created starting with M01. Mirrors the iOS-side `aNN_directives_for_q.md` convention but under `migration/` since services work is its own track.
- **Companion stub in `D:\Audioura\assignments\mac_mini_assignments.md`** is unnecessary for services work — Services Q runs on the same Windows laptop as Sir Michael's other tooling, no USB sneakernet needed.
- **Format:** each assignment has numbered steps with `[SIR MICHAEL]` and `[SERVICES Q]` labels. Same STOP-condition discipline as iOS assignments.
- **Results:** Services Q writes `MNN_results.md` next to the assignment after completion.

---

## Key paths

**Git repo (Windows):** `C:\Users\micha\eclipse-workspace\AudioTours\development\` — same repo as mobile app. Python services in subdirectories.

**Spec docs (read-only, Claude's permanent area):**
- `C:\Business\AudioTours.io\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`
- `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`
- `C:\Business\AudioTours.io\Claude\Audioura development\Audioura_project_log.md`

**Future migration outputs:** `C:\Users\micha\eclipse-workspace\AudioTours\development\migration\` — to be created at M01 start.

**Future GCP projects:** `audioura-preprod` and `audioura-prod` (us-central1).

**Future custom domain:** `api.audioura.io` (subdomain on existing `audioura.io`).

---

## Working with Services Q — verify before approving

Inherits the iOS Q discipline. Apply:

1. Demand log output, command stdout, or config file contents for any "this worked" claim. Don't accept summaries.
2. Spot-check every "I fixed/edited/cleaned up" by reading the actual change.
3. Partial sweeps are the failure mode — if N sites need changes, expect Q to fix N-1.
4. Cost claims need itemized breakdowns against Cloud Run / Cloud SQL pricing, not "should be cheap."
5. Database migrations require backups before, smoke tests after, and a named rollback path documented.
6. Secrets never appear in commits. Anything `ghp_*` / `AKIA*` / `sk-*` / etc. in a diff blocks the commit and forces rotation.

---

## Reviewer discipline

- For every "deployed" claim: pull the public URL, hit `/health`, post the response.
- For every schema change: backup before, smoke test after, rollback path documented.
- For every cost claim: itemize against published pricing.
- For database changes that touch user data: dry-run on PreProd first.
- For service-to-service auth changes: end-to-end test through the orchestrator.

---

## Tone

Direct verdict up front. Precise language. Sir Michael runs Docker daily — he knows the stack; don't explain Docker basics. Cloud Run "revision" vs "service" matters. Cloud SQL "instance" vs "database" matters. Use the AskUserQuestion tool when uncertain about scope rather than wasting effort.

---

## Document inventory (current, after A#74 cleanup)

**In `development/` (git-tracked):**
- `claude_io_handoff.md` — this file.
- `remind_macmini.md`, `remind_ios_ai.md`, `remind_mobile_ai.md`, `remind_Services_ai.md`, `remind_advisor.md` — each Q's own (do not edit).
- `transition_for_iOS_AQ.md`, `transition_for_Mobile_AQ.md`, `transition_for_MacMini_Kiro.md`, `transition_for_Services_AQ.md`, `transition_for_Advisor_AQ.md` — what each Q does in the new phase.
- `git_branch_strategy.md` — current branches and the merge-to-main plan.
- `a75_directives_for_q.md` — A#75 directives (historical, Mac Mini Q used this).
- `mac_mini_setup_guide.md` — sanitized version (token replaced with placeholder).

**In `C:\Business\AudioTours.io\Claude\Audioura development\` (Claude permanent):**
- `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`
- `STORE_SUBMISSION_ROADMAP.md`
- `Audioura_project_log.md`
- `sir_michael_services_migration_overview.md` — Sir Michael's strategy guide (accounts, costs, autonomy).

**On USB `D:\Audioura\`:**
- `assignments/mac_mini_assignments.md` — iOS-side assignment queue. Services-side has its own queue in `development/migration/` (no USB).

---

## First steps for a fresh services-migration session

1. Read `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` in full. (57 KB, ~20-min read.)
2. Read `STORE_SUBMISSION_ROADMAP.md` to understand the downstream dependency.
3. Read `transition_for_Services_AQ.md` for what Services Q already knows about its role.
4. Read `sir_michael_services_migration_overview.md` (`C:\Business\AudioTours.io\Claude\Audioura development\`) for Sir Michael's strategic framing — accounts, costs, autonomy patterns.
5. Draft **M01 (Phase A audit)** as `development/migration/M01_pre_migration_audit.md`. Read-only assignment for Services Q to produce a per-service migration-readiness table. ~2 hours of Q work.
6. Hand off to Sir Michael for relay.
