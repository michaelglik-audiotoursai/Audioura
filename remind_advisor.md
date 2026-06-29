# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-29 SESSION 6 - Tour Quality Enhancement architecture designed. Spine POC proven. enhancement_tasks.md next.

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**: "🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Active branch: services-migration. Current build: v1.2.9+66. TWO parallel tracks active:
TRACK A — GCP Migration: M01 complete, M02 Step 1 done, M02 Steps 2-5 remaining.
TRACK B — Tour Quality Enhancement: Architecture designed, spine POC proven ($0.014/tour, 11.6s). Next: draft enhancement_tasks.md for parallel Amazon-Q execution.
IMMEDIATE NEXT ACTIONS:
1. Draft enhancement_tasks.md (~100 independent tasks for all Amazon-Q teams)
2. Continue M02 remaining steps
3. Block App Store submission until M04+M05 complete
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

### **COMPLETED SESSION 6 (2026-06-29)**:
1. ✅ **Kiro PATH fixed**: `C:\Users\micha\AppData\Local\Programs\Kiro` added to Windows user PATH via PowerShell
2. ✅ **Claude transition docs pushed**: `bd473f7` — all 7 Claude.AI handoff/transition docs + audioura-dev.apk
3. ✅ **transition_for_Advisor_AQ.md reviewed** — accurate, two projects: GCP migration + App Store submission
4. ✅ **AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md fully read** — Advisor Q now has complete migration knowledge
5. ✅ **Tour Quality Enhancement architecture designed** — see section below
6. ✅ **Narrative spine POC run** — gpt-4o, 11.6s, $0.01421, saved as `chagall_spine_poc.json`
7. ✅ **Chagall current tour saved** as `chagall_current_tour.txt` for comparison

### **GIT STATE**:
- **Active branch**: services-migration
- **Last commit**: `32f596c` — Update remind_advisor.md (Session 5 update)
- **Untracked**: `chagall_current_tour.txt`, `chagall_spine_poc.json`, `spine_poc.py` — commit or backup before next session
- **Remote**: up to date with origin/services-migration ✅

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

### **TRACK A — GCP Migration M02 remaining steps**
1. ✅ Step 1 done: env-var-driven inter-service URLs in 6 services
2. Ensure all Dockerfiles have `EXPOSE <port>` + `CMD` bound to `0.0.0.0:$PORT`
3. Replace local file writes with R2 calls behind feature flag — test with MinIO locally
4. Each service responds to `GET /health` → 200 in <1s (Cloud Run liveness)
5. Smoke-test all 13 services locally with new config
6. **$0 GCP cost** — billing only starts at M03 (Cloud SQL provisioning)

### **TRACK B — Tour Quality Enhancement (next action)**
- Draft `development/enhancement_tasks.md` — ~100 independent tasks for parallel Amazon-Q execution
- POC files to commit: `chagall_current_tour.txt`, `chagall_spine_poc.json`, `spine_poc.py`
- See Tour Quality Enhancement section below for full architecture

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

## 🎨 **TOUR QUALITY ENHANCEMENT — ARCHITECTURE (Session 6)**

### **Strategic Vision**
Tours must be strikingly different from generic AI output — factually accurate, narratively connected, personalized, engaging enough that users pay money and share with friends.

### **Three Architectural Layers**

**Layer 1 — Content Foundation (accuracy)**
- Fact sheet per POI generated BEFORE narrative writing
- gpt-3.5-turbo at low temperature for structured JSON facts (NOT gpt-4o — cost unjustified)
- RAG: Wikipedia API (free) + museum website content retrieved per stop, fed as grounding
- Hallucination flag: low-confidence facts flagged, not published

**Layer 2 — Narrative Spine (differentiator)**
- ONE gpt-4o call per tour generation (not per stop) — $0.014/tour, 11.6s ✅ PROVEN
- Produces: tour_hook, connecting_thread, per-stop emotional_beat + unique_angle + plant + callback + cliffhanger, climax_stop, closing_revelation
- Spine varies by tour type — saved as reusable templates per type
- Spine template files: `templates/spine_museum.txt`, `spine_walking.txt`, `spine_restaurant.txt`, `spine_book.txt`
- Spine injected into existing Phase 5 description prompts as context (no extra API call)

**Layer 3 — Perspective System (personalization)**
- 3 perspective layers per stop: 🎨 Artist/Creator, 📚 Historian, 👁️ Curator
- Generated via RAG: Wikipedia → Artist layer, historical period article → Historian layer, museum site → Curator layer
- Model: gpt-3.5-turbo for narrative rewrite of RAG content (~$0.001-0.003/perspective)
- User preference inferred PASSIVELY: replay behavior + single emoji onboarding question
- Onboarding: "What brings you here today?" → 🎨 Art lover / 📖 History buff / 👨‍👩‍👧 Family / ✈️ First-time visitor

### **Tour Caching + Trend Intelligence (3 levels)**
- **Level 1 — Exact cache**: hash(location + tour_type + total_stops) → Postgres lookup before OpenAI call
- **Level 2 — Partial reuse**: fuzzy-match POIs by name+coordinates, reuse fact sheets and descriptions (~70-80% cost saving on similar requests)
- **Level 3 — Trend intelligence**: request frequency counter → proactive pre-generation during off-peak → "Popular this week" surface in app
- All 3 levels buildable on existing Postgres + Docker stack, migrate to Cloud Run in M04

### **Tour Type Spine Variations**
| Tour Type | Spine Structure | Connecting Thread |
|---|---|---|
| Museum | Linear chapters — each room builds on last | Artist's life arc, thematic evolution |
| Walking | Geographic journey — arrival → discovery → departure | Neighborhood character, hidden history |
| Restaurant | Culinary journey — appetizer → main → dessert metaphor | Cuisine culture, chef stories |
| Book/Movie | Plot-parallel — stops mirror story chapters | Character motivations, scene context |

### **Revised Cost Table**
| Component | Effort | Quality Impact | Cost per tour |
|---|---|---|---|
| Fact extraction + hallucination guard | Medium | High | +$0.002 (gpt-3.5-turbo) |
| RAG retrieval (Wikipedia API) | Medium | Very High | $0 (free API) |
| Narrative spine (gpt-4o, 1 call/tour) | Medium | Very High | +$0.014 ✅ proven |
| Callback injection into Phase 5 | Medium | High | $0 (context only) |
| Perspective layers x3 per stop | High | Very High | +$0.03 (gpt-3.5-turbo) |
| Passive preference inference | High | Medium | $0 (client-side) |
| Single onboarding question | Low | High | $0 (UI only) |
| Tour caching Level 1 | Low | Cost saving | -$0.10+ per cache hit |
| Tour caching Level 2 | Medium | Cost saving | -70-80% on similar requests |
| Trend pre-generation | Medium | Revenue | Near-zero marginal per user |
| **Total upgrade cost** | | | **+~$0.05/tour net** |

### **Implementation Sprints**
- **Sprint 1** (2-3 weeks): Fact extraction + RAG + Narrative spine + callback injection → immediately market-differentiated
- **Sprint 2** (3-4 weeks): Perspective layers (Artist/Historian/Curator) + onboarding question
- **Sprint 3** (post-launch): Passive preference inference from replay behavior + trend intelligence

### **POC Evidence**
- Spine generated for Chagall museum tour: `development/chagall_spine_poc.json`
- Current tour baseline: `development/chagall_current_tour.txt`
- POC script: `development/spine_poc.py` (runs inside `development-tour-generator-1` container)
- Measured: 11.6s, 546 tokens in / 1284 out, $0.01421 total
- Quality verdict: hook genuine, emotional beats differentiated, climax at Stop 7 correct, closing_revelation needs strengthening with RAG facts

### **Next Step**
Draft `development/enhancement_tasks.md` — ~100 independent tasks broken down for parallel Amazon-Q execution across Services Q, Mobile Q, iOS Q, and Demo Q.

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

**Last Updated**: 2026-06-29 Session 6
**Status**: ✅ v1.2.9+66 both platforms | ✅ M01 complete | 🔄 M02 in progress | 🔄 Tour Enhancement architecture designed
**Current Build**: v1.2.9+66 — iOS + Android
**Two Active Tracks**: A) GCP Migration M02→M05 | B) Tour Quality Enhancement Sprint 1
**Next Milestone**: draft enhancement_tasks.md + complete M02
**POC Files to commit**: chagall_current_tour.txt, chagall_spine_poc.json, spine_poc.py
