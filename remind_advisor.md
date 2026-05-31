# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-02 SESSION 5 - Active branch: services-migration. v1.2.9+66 current. M01 complete, M02 Step 1 done.

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**: "🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Active branch: services-migration. Current build: v1.2.9+66. M01 audit complete, M02 Step 1 done (env-var inter-service URLs in 6 services). IMMEDIATE NEXT ACTIONS:
1. Continue M02 remaining steps (Dockerfiles, /health endpoints, MinIO R2 rehearsal, smoke test)
2. Block App Store / Play Store submission until M04+M05 complete (public HTTPS gate)
3. Read transition_for_Advisor_AQ.md for full decision table
What needs my input?"

---

## 🎯 **ROLE & RESPONSIBILITIES**
1. **Strategic Planning**: High-level roadmap and business strategy for Audioura LLC
2. **Cross-Team Coordination**: Align Mobile App, Services, iOS, and Demo Amazon-Q efforts
3. **Product Vision**: Define feature priorities and market positioning
4. **Risk Assessment**: Identify potential issues and mitigation strategies
5. **Timeline Management**: Realistic project scheduling and milestone tracking

---

## 📊 **CURRENT PROJECT STATUS**
**Date**: 2026-06-02 (Session 5)
**Version**: v1.2.9+66 (map icon restore + museum tour category fix + M02 Step 1 env-var URLs)
**Branch**: services-migration (active dev branch)
**Other branches**: main (stable), Newsletters (kept as precaution, merged into main), ios-dev
**Overall Status**: ✅ **v1.2.9+66 on both platforms** — GCP migration M02 in progress

### **COMPLETED SESSION 4**:
1. ✅ mac_mini_setup_guide.md sanitized and committed (`6c52ef3`)
2. ✅ Git history rewritten — removed commits with GitHub PAT secret
3. ✅ ~100 log/output txt files moved to backup
4. ✅ 27 meaningful files committed (`3764d93`)
5. ✅ a75_directives_for_q.md created and pushed (`76baaf2`)

### **COMPLETED SESSION 5**:
1. ✅ **A#75 complete**: v1.2.9+65 shipped — InAppWebView v6 in news_player_screen.dart (`5adcee7`)
2. ✅ **Claude transition docs committed**: claude_io_handoff.md, git_branch_strategy.md, transition_for_*.md x5 (`bd473f7`)
3. ✅ **Newsletters merged into main** — services-migration is now the active dev branch
4. ✅ **v1.2.9+66** — map icon restore + museum tour category fix + M02 Step 1 env-var inter-service URLs in 6 services
5. ✅ **M01 audit complete**

### **GIT STATE**:
- **Active branch**: services-migration
- **Last commit**: `682a802` — Update remind_mobile_ai.md - add v1.2.9+66 key fix entry
- **Remote**: up to date with origin/services-migration ✅
- **Working tree**: clean

### **BUILD HISTORY (RECENT)**:
- **A#71**: ✅ COMPLETE - v1.2.9+62 - App name fix + InAppWebViewSettings v6 (tour_player_screen only)
- **A#72**: ✅ COMPLETE - v1.2.9+63 - Heal stale iOS container paths for news articles
- **A#73**: ✅ COMPLETE - v1.2.9+64 - Brick red app icon background (#A93105)
- **A#74**: ✅ COMPLETE - Windows-side cleanup (Session 4)
- **A#75**: ✅ COMPLETE - v1.2.9+65 - InAppWebView v6 migration in news_player_screen.dart
- **v1.2.9+66**: ✅ COMPLETE - Map icon restore + museum tour category fix + M02 Step 1 env-var URLs
- **NEXT**: GCP migration M02 remaining steps → M03 → M04 → M05

---

## 🚨 **IMMEDIATE NEXT ACTIONS**

### **GCP Migration M02 — remaining steps**
1. ✅ Step 1 done: env-var-driven inter-service URLs in 6 services
2. Ensure all Dockerfiles have `EXPOSE <port>` + `CMD` bound to `0.0.0.0:$PORT`
3. Replace local file writes with R2 calls behind feature flag — test with MinIO locally
4. Each service responds to `GET /health` → 200 in <1s (Cloud Run liveness)
5. Smoke-test all 13 services locally with new config
6. **$0 GCP cost** — billing only starts at M03 (Cloud SQL provisioning)

### **App Store / Play Store (blocked on Services M04+M05)**
- Spec: `STORE_SUBMISSION_ROADMAP.md`
- No IAP in v1.0 — RevenueCat deferred to v1.3
- Demo account required for Apple App Review before submission
- Pre-write background audio justification for App Review Information
- Mobile Q must back up Android keystore to 3 places — Sir Michael to confirm

---

## 🔑 **KEY CREDENTIALS & LOCATIONS**

### **AWS / Amazon Q**
- **Amazon Q Pro**: $19/month flat rate
- **IAM Identity Center URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Apple Developer**: Order W1583339145, glikfamily@gmail.com, Team 4HGRU6TKGQ

### **Key File Locations**
- **Assignments (Windows/USB)**: `D:\Audioura\assignments\mac_mini_assignments.md`
- **Assignments (Mac/USB)**: `/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md`
- **Dev Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\development\`
- **Backup Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\backup\`
- **Git Repo (Mac Mini)**: `~/Development/Audioura-build/` (branch: services-migration)
- **A#75 Directives**: `development/a75_directives_for_q.md` (committed `76baaf2`) — A#75 complete
- **Transition Docs**: `development/transition_for_*.md` — one per Amazon-Q role (committed `bd473f7`)
- **Cloud Migration Spec**: `C:\Users\micha\eclipse-workspace\AudioTours\development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` (also in git)
- **Store Submission Spec**: `C:\Business\audiotours.com\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`
- **Migration Output Dir**: `C:\Users\micha\eclipse-workspace\AudioTours\development\migration\` (create during M01)

### **GitHub Secret Scanning — Lessons Learned**
- NEVER commit files containing `ghp_` tokens or plain-text passwords
- Resolution: `git reset --mixed <commit-before-bad>`, redo commits cleanly
- NEVER click "Allow secret" on GitHub
- `mac_mini_setup_guide.md` is now sanitized and committed (placeholders only)

---

## 🏗️ **PLATFORM OWNERSHIP MODEL**
- 🍎 **iOS AMAZON-Q**: Complete iOS ownership (Flutter fixes, Xcode, App Store, iPhone testing)
- 📱 **MOBILE APP AMAZON-Q**: Complete Android ownership (APK builds, Play Store, Android testing)
- 🔧 **SERVICES AMAZON-Q**: Backend & AWS (serves both platforms equally)
- 🎯 **STRATEGIC ADVISOR AMAZON-Q**: Cross-platform coordination & business decisions
- 🎪 **DEMO AMAZON-Q**: Testing & validation for both platforms

### **AMAZON Q ON MAC MINI**
- **Install**: VS Code + Amazon Q extension OR Kiro CLI (`kiro-cli chat --trust-all-tools`)
- **Auth Method**: IAM Identity Center (NOT Builder ID)
- **Startup URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Recovery file**: `remind_macmini.md`

---

## 📊 **STRATEGIC PHASES**

### **PHASE 0: PLATFORM FOUNDATION (COMPLETE)**
- ✅ iOS builds working (A#63-A#75 on Mac Mini)
- ✅ Android stable, both platforms on v1.2.9+66
- ✅ Git repository clean and fully synced
- ✅ Development directory cleaned (300+ one-shot files moved to backup)
- ✅ A#75 complete — v1.2.9+65 shipped

### **PHASE 1: GCP MIGRATION (IN PROGRESS — 20-30 hrs total)**
- ✅ **M01** — Pre-migration audit — complete
- 🔄 **M02** — Local cloud-ready rehearsal — Step 1 done, Steps 2-5 remaining — $0 GCP cost
- ⬜ **M03** — GCP project setup (~3 hrs) — **billing starts here ~$35/month**
- ⬜ **M04** — Service-by-service deploy to PreProd (~10-15 hrs)
- ⬜ **M05** — Production cutover (~2-4 hrs) — gates App Store submission
- **Target architecture**: Cloud Run (13 services) + Cloud SQL Postgres + Cloudflare R2
- **Floor cost at launch**: ~$36/month (no load balancer — subdomain-per-service strategy)
- **Key cost outlier**: newsletter-processor (headless Chrome, 4 GB RAM, concurrency=1)

### **PHASE 2: APP STORE SUBMISSION (blocked on M04+M05)**
- iOS App Store + Google Play Store
- Version consolidation: v1.2.9 → v1.3.0
- No IAP in v1.0 — RevenueCat in v1.3 post-launch

### **PHASE 3: MARKET OPTIMIZATION (post-launch)**
- User feedback integration
- Feature adoption tracking
- App store rating optimization

---

## 🛠️ **WINDOWS TOOLING LESSONS (Session 4)**
- **Batch files**: Use `cmd /c "full\path\to\file.bat"` to run batch files from executeBash
- **Multi-command**: Use `&&` operator for short chains instead of batch files
- **Backslash paths**: Windows paths with backslashes cause EOF errors in some tool calls — use batch files for complex operations
- **git status clean**: All `??` untracked files must be either committed or moved to backup — never leave them floating

---

## 🏗️ **GCP MIGRATION — KEY FACTS FOR ADVISOR**

### **Architecture decisions (locked)**
- Cloud Run per service (13 total) — matches current Docker Compose exactly
- Cloud SQL Postgres db-g1-small prod (~$25/mo), db-f1-micro preprod (~$10/mo)
- Cloudflare R2 for audio files — zero egress fees (critical for audio app at scale)
- AWS Polly stays — no migration off Polly for v1
- Two GCP projects: `audioura-preprod` + `audioura-prod` (hard isolation)
- Subdomain-per-service (option b) — saves $18/month vs Cloud Load Balancer
- No prod Cloud SQL until M05 — saves $25/month during M04

### **Cost monitoring responsibilities (Advisor Q owns)**
- Floor: ~$36/month at zero users (Cloud SQL dominates)
- Newsletter-processor is #1 cost outlier — headless Chrome, 4 GB RAM
- AWS Polly + OpenAI are dominant variable costs at scale (~$0.10/tour, ~$0.75/news article)
- Surface to Sir Michael if any phase slips >30% or billing surprises >2x expected

### **Phase gate rules (Advisor Q enforces)**
- **M03 gate**: Don't provision prod Cloud SQL until M05 — saves $25/month
- **App Store gate**: BLOCK Phase 1 submission until M04+M05 complete (public HTTPS required)
- **No IAP gate**: If anyone proposes subscriptions/IAP for v1 — answer is NO (Apple 3.1.1)
- **Cloudflare Tunnel stopgap**: NO — Apple review window catches laptop offline overnight

### **Special service handling**
- newsletter-processor: 4 GB RAM, 2 vCPU, concurrency=1, timeout=900s (Cloud Run max)
- tour-processor + polly-tts: 2 vCPU, 1-2 GB RAM, concurrency=5-10, timeout=300s
- All services need `GET /health` → 200 in <1s (Cloud Run liveness)
- All services need `DATABASE_URL` env var (replace hardcoded localhost:5432)

### **Working agreement**
- Amazon-Q drafts each phase's scripts
- Claude reviews before execution (V2 discipline)
- Sir Michael executes; authorizes destructive operations
- All migration files in `development/migration/` named `m##_<description>_<timestamp>.txt`

---

## 📋 **NEXT ACTION**
Continue M02 remaining steps (Dockerfiles, /health endpoints, MinIO R2 rehearsal, smoke test all 13 services).
Read `transition_for_Advisor_AQ.md` for full decision table and cost monitoring responsibilities.

---

**Last Updated**: 2026-06-02 Session 5
**Status**: ✅ Git clean + synced | ✅ v1.2.9+66 on both platforms | ✅ M01 complete | 🔄 M02 in progress
**Current Build**: v1.2.9+66 — iOS + Android
**Next Milestone**: Complete M02 → M03 (billing starts) → M04 → M05 → App Store submission
**No Blockers**: Both platforms stable, git clean, transition docs ready
