# Transition Brief — Services Amazon-Q (🔧)

**Date:** 2026-05-28. Supersedes any prior version (lost during A#74 cleanup).
**Audience:** 🔧 SERVICES AMAZON-Q.
**Status of your `remind_Services_ai.md`:** untouched. You own it.

You are the primary executor of the **Universal Services Locations** project — migrating Audioura's 13 Docker backend services from Sir Michael's laptop (LAN-only, `192.168.0.218`) to **Google Cloud (Cloud Run + Cloud SQL Postgres + Cloudflare R2)**. This is your project. Other Q's wait on milestones you deliver.

---

## The spec

`C:\Business\AudioTours.io\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` (57 KB).

**Read it in full before any migration work.** Five phases:

- **Phase A — M01 — Pre-migration audit (~2 hr, read-only).** Per-service inventory: env vars, secrets, file paths, ports, AWS Polly creds, OpenAI creds, persistence dependencies. Output: a per-service migration-readiness table.
- **Phase B — M02 — Local "cloud-ready" rehearsal (~3 hr).** Refactor each service to read env vars, accept injected DB connection strings, use a pluggable storage backend (local FS for dev, R2 for cloud).
- **Phase C — M03 — GCP project setup (~3 hr).** Create `audioura-preprod` + `audioura-prod` projects, enable Cloud Run / Cloud SQL / Artifact Registry / Secret Manager / Cloud Build, provision Cloud SQL Postgres, set up R2 buckets, populate Secret Manager.
- **Phase D — M04 — Per-service deploy to PreProd (~10-15 hr).** For each of 13 services: build → push to Artifact Registry → `gcloud run deploy` to `audioura-preprod` → smoke test. **Order: leaf services first (translation, coordinates, treats), mid (map-delivery, generators), orchestrators last.**
- **Phase E — M05 — Production cutover (~2-4 hr).** Blue-green to `audioura-prod`. Traffic shift 10% → 50% → 100% with monitoring. Custom domain `api.audioura.io`.

**Phase D's completion is the critical handoff.** When PreProd is live, you deliver to Sir Michael:
1. The PreProd HTTPS base URL.
2. Per-service routing (subpaths under one URL, or sub-hostnames — your call).
3. **The authentication model the mobile app must implement** (API key in headers / OAuth / signed requests). Decide this EARLY — iOS Q and Mobile Q block on this decision.
4. Confirmation all 13 services pass smoke tests.

After that, the mobile-app side (iOS Q + Mobile Q) can replace ~37 hardcoded `192.168.0.x` references.

---

## Operational model in this phase

- **Migration assignments arrive at `~/Development/Audioura-build/development/migration/MNN_<name>.md`** — to be created starting with M01. You read them, execute, and write `MNN_results.md` next to each.
- **No USB sneakernet.** You and Claude IO share the same Windows machine and the same git repo. Push your commits to GitHub; Sir Michael syncs by pulling.
- **You have blanket approval** (per your remind doc) — change code, run Python, start/stop Docker, deploy to Cloud Run without per-step confirmation.
- **Sir Michael will give you blanket approval for `gcloud`** explicitly when you start M03 (he'll create the GCP account). Don't try to deploy before then.

---

## Service inventory (your starting point)

13 services, ports 5000–5030. Detail in `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` §2.1. Highlights:

- `polly-tts` (5018) keeps an outbound AWS Polly dependency regardless of compute platform. IAM creds → Secret Manager.
- `newsletter-processor` (5017) runs headless Chrome for Spotify/Apple Podcasts scraping. **5-10x the container footprint of leaf services.** Watch its Cloud Run bill.
- `tour-processor` (5001) is CPU-heavy (audio synthesis). Consider min-instances=1.
- `postgres` (5432) — migrates to Cloud SQL Postgres. **Always-on**; the floor cost of the whole setup.

External dependencies that survive the migration:
- **OpenAI API** — outbound HTTPS, standard Cloud Run egress.
- **AWS Polly** — IAM credentials in Secret Manager.
- **Spotify / Apple Podcasts public pages** — outbound web scraping; Cloud Run container needs Chrome bundled.

---

## Things to surface to Sir Michael as soon as they're known

- **The PreProd URL when M04 completes** — this unblocks the entire mobile-app side and the App Store submission track.
- **Chosen authentication model** — decide early. Mobile-app side cannot start the URL-config work until they know whether it's API-key, OAuth, or signed-request.
- **Cost surprises** — the always-on Cloud SQL is the floor cost; the newsletter-processor is the most likely outlier. If costs run higher than the spec's $10-36/month estimate, surface immediately.
- **Schema changes** — any `ALTER TABLE` against Cloud SQL must be tracked. Commit a migration SQL file to `development/migration/sql/`.

---

## Coordination with the other Qs

- **iOS Q + Mobile Q** are idle on the URL work until you deliver the PreProd URL. They can do unrelated mobile work, but the URL transition is gated on you.
- **Mac Mini Kiro CLI** continues to build iOS releases against the LAN backend until you flip the switch.
- **Strategic Advisor Q** tracks your phase progression. Surface phase completions to it.

---

## What's NOT your scope

- Mobile-app code (Dart). iOS Q + Mobile Q own that.
- iOS / Android builds. Mac Mini Kiro CLI and Mobile Q on Ubuntu VM own those.
- App Store / Play Store submission mechanics. Sir Michael + the iOS / Mobile Qs handle that, gated on your M04+M05.
- Strategic / timeline / budget decisions. Strategic Advisor Q handles those, escalating to Sir Michael.

---

## Where this doc lives

`C:\Users\micha\eclipse-workspace\AudioTours\development\transition_for_Services_AQ.md`. Git-tracked. Sir Michael relays this to you on session start; you reference it as background.
