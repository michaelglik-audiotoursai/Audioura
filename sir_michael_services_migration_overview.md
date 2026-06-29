# Services Migration — Sir Michael's Overview

**Date:** 2026-05-28.
**Audience:** Sir Michael only.
**Lives at:** `C:\Business\AudioTours.io\Claude\Audioura development\` (Claude permanent docs area, not git-tracked — your personal strategy doc).

This is the strategic summary you asked for: how the services migration will be done, what accounts you need, what it'll cost, and how to get your Amazon-Q agents working more autonomously like Mac Mini Kiro CLI.

---

## 1. What we're doing, in one paragraph

We're moving Audioura's 13 backend Docker services off your laptop (where they only work over LAN) and onto **Google Cloud Run** (compute), **Cloud SQL Postgres** (database), and **Cloudflare R2** (audio/file storage). The same Docker images you run today will run unchanged in the cloud — only connection strings and hostnames change. After this, the mobile app's ~37 hardcoded `192.168.0.x` references get replaced with `https://api.audioura.io`, the App Store and Play Store can reach your backend during review, and you can ship publicly.

Spec: `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` (in this same folder). 5 phases (M01–M05). ~20-30 hours of focused work for Services Q.

---

## 2. Accounts you need to create (before M03)

| Account | When | Cost to create | Cost at low volume | Notes |
|---|---|---|---|---|
| **Google Cloud Platform** | Before M03 | $0 + $300 free trial credit | $0–$36/month | Use a new Google account or your existing one. Free trial alone covers 1-3 months of setup + testing. |
| **Cloudflare account** | Before M03 | $0 | $0 | R2 has a generous free tier: 10 GB storage, no egress fees. Audioura's storage needs (audio files) fit comfortably in free tier for months. |
| **Domain DNS in Cloudflare** | Before M05 | $0 (if you already own audioura.io) | $0 | Move audioura.io's DNS to Cloudflare so you can route `api.audioura.io → Cloud Run` cleanly. |
| **Google Play Console** | Before App Store Phase 4 | $25 one-time | $0 | Required for publishing to Google Play. |
| **Apple Developer Program** | Already paid | — | $99/year (ongoing) | Active, member of team `4HGRU6TKGQ`. |

**You do NOT need:** AWS account (Audioura's only AWS dep is Polly, which you already have); GitHub paid plan (free is fine for private repos); GitHub Advanced Security (the push protection on free private repos works for our needs); RevenueCat (not until v1.3 post-launch); analytics platforms (not until you have users).

---

## 3. Costs, in detail

### Setup phase ($0–$25 one-time)

- GCP free trial covers it. $0 actual spend.
- Cloudflare free.
- Play Console $25.
- Domain DNS migration $0.

**Total: $25 one-time** (the Play Console fee).

### Running pre-volume ($10–$36/month)

Itemized:

| Item | Cost | What drives it |
|---|---|---|
| Cloud SQL Postgres (smallest instance, db-f1-micro, ~600 MB RAM) | $7–10/month | Always-on; can't scale to zero. The floor cost. |
| Cloud Run compute | $0–5/month | Scales to zero when idle. Pay per request. At low volume, negligible. |
| Cloudflare R2 storage | $0 | Free tier: 10 GB. Audioura's audio is small per tour; you'll be under 10 GB for months. |
| Cloudflare R2 egress | $0 | R2 has zero egress fees — this is its huge advantage over S3. |
| Custom domain SSL | $0 | Cloud Run provides free managed SSL on custom domains. |
| Secret Manager (OpenAI + AWS Polly keys) | $0.30/month | First 6 secret versions free; we have ~5. |
| Cloud Build (CI for Docker images) | $0 | First 120 build-minutes/day free. |
| Apple Developer Program | $99/year | Already paid. |

**Expected: ~$10/month** until you start generating volume traffic.

### Once volume hits (tour/newsletter generation in production)

The biggest cost driver isn't infrastructure — it's the **external APIs you already pay for**:

- **OpenAI API** — costs per request based on token usage. You already pay this for tour generation.
- **AWS Polly** — costs per character of TTS. You already pay this.
- **Cloud SQL** — same low cost until your data grows past the smallest instance (10s of thousands of tours).
- **Cloud Run** — pay per request; if traffic is steady, costs are predictable.

**Volume-related infra cost won't surprise you.** If billing surprises happen, the culprit is almost certainly the **newsletter-processor service** — it runs a headless Chrome browser, so its memory footprint is 5-10x leaf services. Watch that one in particular. Strategic Advisor Q is briefed to flag this.

---

## 4. How the migration actually happens (5 phases)

| Phase | What | Who runs it | Time | Output |
|---|---|---|---|---|
| **M01 — Pre-migration audit** | Per-service inventory: env vars, secrets, ports, deps | Services Q | ~2 hours | A markdown table per service: this service needs X, Y, Z to run in cloud |
| **M02 — Local cloud-ready rehearsal** | Refactor services to read env vars, use injectable DB connection, pluggable storage | Services Q | ~3 hours | Same Docker images, but parameterized for cloud |
| **M03 — GCP project setup** | Create projects, provision Cloud SQL, set up R2, populate Secret Manager | You (account creation) + Services Q (provisioning) | ~3 hours | Empty but working GCP environment ready for deploys |
| **M04 — Per-service migration to PreProd** | Build → push → deploy each of 13 services to `audioura-preprod` | Services Q | ~10-15 hours over several sessions | PreProd HTTPS URL where the app can talk to backend |
| **M05 — Production cutover** | Blue-green to `audioura-prod`, custom domain, gradual traffic shift | Services Q + you (final approval) | ~2-4 hours | `api.audioura.io` live, App Store can submit |

After M05, the mobile-app side (iOS Q + Mobile Q) replaces the LAN URLs with `api.audioura.io`. That's another ~half-day of work. Then App Store + Play Store submission can begin.

**Total wall time: ~3-4 weeks** if you do it steadily. **Total Sir-Michael time: ~3-5 hours** spread across creating accounts, approving deploys, and running smoke tests. Most hours are Services Q execution.

---

## 5. App Store + Play Store timeline (after migration)

Once `api.audioura.io` is live:

- **Phase 1 — Bundle / ATS / Info.plist** (iOS Q, ~1-2 hours + a build cycle)
- **Phase 2 — Privacy, Terms, screenshots** (you write copy, Advisor Q reviews, ~4-6 hours)
- **Phase 3 — iOS TestFlight internal** (Mac Mini Kiro CLI, ~2-4 hours first time)
- **Phase 4 — Play Console internal** (Mobile Q, ~2-3 hours)
- **Phase 5 — External testing** (2 weeks running with friends/family)
- **Phase 6 — Production submission** (~30 min + 1-2 weeks of Apple review iteration)

Plan **4-8 weeks** from `api.audioura.io` live to apps publicly available. Realistically **10 weeks** if Apple kicks back once.

Spec: `STORE_SUBMISSION_ROADMAP.md` in this same folder.

---

## 6. Increasing Amazon-Q autonomy (so they don't ask permission constantly)

You already have this working for two Q's:

- **Mac Mini Kiro CLI** runs via `kiro-cli chat --trust-all-tools` — that CLI flag is the entire autonomy mechanism. Q executes without asking.
- **Services Q** has a written standing instruction in `remind_Services_ai.md` line 7: *"You have blanket approval to change code, run Python programs, start/stop Docker services without waiting for approval."*

The other three Q's (iOS, Mobile, Advisor) ask per-command because they don't have an equivalent standing instruction.

### How to give them the same autonomy

Paste this in chat with each Q. Each one will integrate the instruction into their `remind_*.md` themselves (since they maintain those files):

#### For Mobile Q (📱 MOBILE APP AMAZON-Q)

> Mobile Q — going forward you have blanket approval to execute Windows-side git commands (status, log, fetch, pull, push, branch, checkout, reset, add, commit, rm, gitignore edits) and Ubuntu VM build commands (`bash build_flutter_clean.sh`, `flutter` invocations) without asking for confirmation. Follow Mac Mini Kiro CLI discipline: run each step, check the output, proceed on success / STOP and report on failure or anything matching a documented STOP condition. Update your own `remind_mobile_ai.md` to record this standing instruction.

#### For iOS Q (🍎 iOS AMAZON-Q)

> iOS Q — going forward you have blanket approval to make Dart code changes in `audio_tour_app/lib/`, edit `audio_tour_app/ios/Runner/Info.plist`, run `flutter analyze`, and commit-and-push to feature branches without asking for confirmation. For destructive changes (deleting files, force-pushing, rewriting history), ASK before proceeding. Update your own `remind_ios_ai.md` to record this standing instruction.

#### For Advisor Q (🎯 STRATEGIC ADVISOR AMAZON-Q)

> Advisor Q — going forward you have blanket approval to read any file in the repo, query git history, run analysis scripts, and write coordination/status docs without asking for confirmation. For decisions that span multiple Q's (timeline changes, scope changes, cost-vs-benefit trade-offs), ASK me before proceeding. Update your own `remind_advisor.md` to record this standing instruction.

### What you should NOT give blanket approval for

- **`git push --force` or `git push --force-with-lease`** — these can overwrite remote history. Force-push always requires explicit Sir Michael approval per-instance.
- **Deletion of branches on origin** — always confirm before deleting remote branches.
- **Disabling security features** — push protection toggling, key rotation, anything that affects credentials. Always explicit.
- **Account creation** — GCP, Cloudflare, Google Play. Only you sign up.
- **Paid spend over $5/month new** — any new recurring cost should be your decision.

### Pattern to enforce in any blanket approval

Every Q with autonomy should follow Mac Mini Kiro CLI's loop: **execute → check output → on success proceed / on failure or STOP condition halt and report**. If they wander outside the listed scope, they ask. Specifically: blanket approval covers `<list of operations>`. Anything not in that list requires per-instance approval.

---

## 7. Things to do TODAY (or whenever you want to start)

In order:

1. **Run the git branch consolidation** (per `git_branch_strategy.md` in development/):
   - Merge Newsletters → main (fast-forward).
   - Tag `v1.2.9+65`.
   - Push main + tag.
   - Create `services-migration` branch off main.

2. **Paste the autonomy grants** above to Mobile Q, iOS Q, and Advisor Q in their respective chat tabs.

3. **Start a new Claude IO session** with this prompt:

   > Read `C:\Users\micha\eclipse-workspace\AudioTours\development\claude_io_handoff.md` first. We're starting the services-migration project (Universal Services Locations). Begin by drafting M01 (Phase A pre-migration audit) as an assignment for Services Q.

4. **Optional:** if you don't have a GCP account yet, create one now so Services Q isn't blocked at M03. New accounts get $300 free trial credit valid for 90 days — gives you headroom.

---

## 8. Where this doc lives

`C:\Business\AudioTours.io\Claude\Audioura development\sir_michael_services_migration_overview.md`. **Not in git** — this is your personal strategy reference, not for any Q.

Companion docs in the same folder:
- `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` — the migration spec (Services Q reads).
- `STORE_SUBMISSION_ROADMAP.md` — the store submission spec (multiple Q's read).
- `Audioura_project_log.md` — your running project log.
