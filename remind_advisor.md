# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-29 SESSION 7 - Storied task generation complete (95 tasks, 5 batch files committed to `storied` branch). Two active tracks: GCP Migration (Track A) + Storied Release (Track B).

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**:
"🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Two active tracks:

TRACK A — GCP Migration: M01 complete, M02 Step 1 done, M02 Steps 2-5 remaining. No GCP billing until M03. App Store submission blocked until M04+M05 complete.

TRACK B — Storied Release: 95 tasks generated across 5 batch files, all committed to `storied` branch. Task generation reviewed by Claude.AI — format approved as excellent. Tasks cover all 5 Storied features: spine/content quality (1-20), de-repetition/directions (21-40), personalization (41-46), sharing/referral (47-52), attestation (53-58), integration/QA (59-80), orchestrator/operations (81-95). Next: Claude.AI imports tasks into ClickUp.

CURRENT BRANCHES:
- `services-migration` — active GCP migration work (currently checked out)
- `storied` — Storied release tasks + 95-task breakdown committed
- `main` — stable Beta (beta-2.1.1+18)

IMMEDIATE NEXT ACTIONS:
1. Claude.AI imports `storied_tasks_index.md` into ClickUp (Track B)
2. Continue M02 remaining steps — Dockerfiles, /health endpoints, MinIO R2 rehearsal (Track A)
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
**Date**: 2026-06-29 (Session 7)
**Beta Version**: v1.2.9+66 (map icon restore + museum tour category fix + M02 Step 1 env-var URLs)
**Storied Version**: v2.2.0+1 (target — not yet built)
**Active dev branch**: `services-migration` (GCP migration work)
**Storied branch**: `storied` (off `main` = `beta-2.1.1+18`)
**Other branches**: `main` (stable), `ios-dev`, `Newsletters` (merged, kept as precaution)

### **COMPLETED SESSION 6**:
1. ✅ **Kiro PATH fixed**: `C:\Users\micha\AppData\Local\Programs\Kiro` added to Windows PATH
2. ✅ **Tour Quality Enhancement architecture designed** — 3 layers: Content Foundation, Narrative Spine, Perspective System
3. ✅ **Narrative spine POC run** — gpt-4o, 11.6s, $0.01421, saved as `chagall_spine_poc.json`
4. ✅ **Chagall current tour saved** as `chagall_current_tour.txt` for comparison
5. ✅ **POC files committed** (`aeae15a`) — `chagall_current_tour.txt`, `chagall_spine_poc.json`, `spine_poc.py`

### **COMPLETED SESSION 7**:
1. ✅ **Full Chagall tour comparison** — original vs POC spine rendered and analyzed (6 identified flaws in Beta output)
2. ✅ **Storied task format validated** by Claude.AI — "Excellent, no changes needed"
3. ✅ **95 Storied tasks generated** across 5 batch files, all committed to `storied` branch:
   - `first_storied_20_tasks.md` — tasks 1–20 — commit `934b2ac`
   - `storied_tasks_21_40.md` — tasks 21–40 — commit `b04d75c`
   - `storied_tasks_41_60.md` — tasks 41–60 — commit `bc2f55f`
   - `storied_tasks_61_80.md` — tasks 61–80 — commit `03abba0`
   - `storied_tasks_81_95.md` — tasks 81–95 — commit `48a9d5a`
4. ✅ **Branch correction**: `first_storied_20_tasks.md` initially committed to wrong branch (`services-migration`), corrected to `storied` via `git reset --mixed` + stash + checkout

### **GIT STATE (Session 7 end)**:
- **Checked out**: `services-migration` (returned here after Storied task commits)
- **storied branch HEAD**: `48a9d5a` — final Storied task batch pushed to `origin/storied`
- **services-migration HEAD**: `aeae15a` — Session 6 POC files + remind_advisor
- **Remote**: both branches up to date with origin ✅

### **BUILD HISTORY (RECENT)**:
- **A#75**: ✅ COMPLETE - v1.2.9+65 - InAppWebView v6 migration in news_player_screen.dart
- **v1.2.9+66**: ✅ COMPLETE - Map icon restore + museum tour category fix + M02 Step 1 env-var URLs
- **Storied v2.2.0+1**: ⬜ Target — Aug 1, 2026 (Google Play closed test + Apple TestFlight)

---

## 🚨 **IMMEDIATE NEXT ACTIONS**

### **TRACK A — GCP Migration M02 remaining steps**
1. ✅ Step 1 done: env-var-driven inter-service URLs in 6 services
2. Ensure all Dockerfiles have `EXPOSE <port>` + `CMD` bound to `0.0.0.0:$PORT`
3. Replace local file writes with R2 calls behind feature flag — test with MinIO locally
4. Each service responds to `GET /health` → 200 in <1s (Cloud Run liveness)
5. Smoke-test all 13 services locally with new config
6. **$0 GCP cost** until M03

### **TRACK B — Storied Release (Aug 1 target)**
- **Next**: Claude.AI imports `storied_tasks_index.md` (#92) into ClickUp as the Storied epic tasks
- **Services Kiro** owns execution of tasks 1–95 on `storied` branch
- **Mobile Q** owns UI tasks (onboarding question, share sheet, referral entry point, attestation token headers) — handed off via `storied_handoff_for_mobile.md` (#80)
- **iOS Q** owns iOS-specific tasks — handed off via `storied_handoff_for_ios.md` (#89)
- **Sir Michael** owns privacy policy update, Data Safety form, App Privacy labels, demo account, keystore backup — documented in `storied_launch_checklist.md` (#71)
- **Aug 1 gate**: `storied_checklist_results.md` (#95) all automated items PASS + Michael items confirmed

### **App Store / Play Store (blocked on M04+M05)**
- No IAP in v1.0 — RevenueCat deferred to v1.3
- Demo account required for Apple App Review before submission
- Pre-write background audio justification for App Review Information
- Mobile Q must back up Android keystore to 3 places — Sir Michael to confirm
- **Storied** goes to Google Play closed test + Apple TestFlight (not production) on Aug 1

---

## 🎨 **STORIED BRANCH STATUS**

### **5 Features in Storied v2.2.0**
1. **Richer POI stories** — narrative spine (gpt-4o, $0.014/tour) + fact extraction + story-type taxonomy — tasks 1–25
2. **Remove repetitive language** — de-repetition guard + auto-rewrite + directions fix — tasks 23–32
3. **User-interest personalization** — onboarding question (4 emoji) + persona storage + weighted story types — tasks 41–46
4. **Tour sharing + referral** — share URL, deep-link resolution, referral code + attribution — tasks 47–52
5. **App attestation (log-only)** — Play Integrity + App Attest, never blocks, enforce stub ready — tasks 53–58

### **Key New Files (all on `storied` branch)**
- `spine_generator.py` — gpt-4o narrative spine, $0.014/tour
- `rag_retriever.py` — Wikipedia API, free
- `fact_extractor.py` — gpt-3.5-turbo fact sheets per stop
- `story_type_assigner.py` — story type taxonomy + persona weighting
- `derepetition_guard.py` — forbidden phrase detection + auto-rewrite
- `directions_generator.py` — museum + walking directions fix
- `onboarding_preference.py` — UserPersona enum + weights
- `persona_preference_store.py` — Postgres-backed persona storage
- `tour_sharing.py` — share ID generation + Postgres storage
- `referral_engine.py` — referral code + redemption tracking
- `attestation_verifier.py` — Play Integrity + App Attest log-only
- `attestation_enforce_gate.py` — enforce stub (NOT wired in for Aug 1)
- `tour_cache_layer1.py` — exact-match tour cache (SHA256 key)
- `storied_db_migration.sql` — all 5 new tables (idempotent)
- `storied_tasks_index.md` — master index of all 95 tasks for ClickUp import
- `storied_launch_checklist.md` — Aug 1 pre-submission gate checklist
- `storied_handoff_for_mobile.md` — Mobile Q integration contract
- `storied_handoff_for_ios.md` — iOS Q integration contract

### **STORIED_MODE Feature Flag**
- `STORIED_MODE=false` → Beta pipeline, zero changes
- `STORIED_MODE=true` → full Storied pipeline active
- Set in docker-compose environment block per service
- Aug 1 production value: `true`
- `ATTESTATION_MODE=log_only` → never blocks requests (Aug 1 value)
- `ATTESTATION_MODE=enforce` → activate post-Aug-1 after log data reviewed

### **Cost Per Tour (Storied)**
- Beta baseline: ~$0.08/tour
- Storied additions: ~+$0.07/tour (spine $0.014 + facts $0.02 + rewrites $0.01 + directions $0.02)
- Cost ceiling guard: $0.15/tour (logged, never aborts)

### **Aug 1 Timeline**
| Week | Milestone |
|---|---|
| Jun 29–Jul 3 | Storied tasks in ClickUp; Services Kiro starts spine + de-repetition |
| Jul 6–10 | Personalization + sharing endpoints; Mobile Q starts onboarding UI |
| Jul 13–17 | Attestation log-only; referral; mid-point review |
| Jul 20–24 | Feature-complete; full regression; `storied` tag |
| Jul 27–31 | Build both stores; submit Google closed test + Apple TestFlight |
| Aug 1 | Testers live on both stores ✅ |

---

## 🏗️ **TOUR QUALITY — KEY INSIGHTS (Session 6-7)**

### **6 Identified Flaws in Beta Tour Output**
1. Stop 1 and Stop 8 both claim "17 large paintings" — factual error (Stop 8 is 5 stained glass windows)
2. Directions are fabricated ("turn right, walk 50 meters") — no floor plan basis
3. Identical 5-paragraph structure on every stop — formulaic
4. "Vibrant colors and dreamlike imagery" appears on nearly every stop — pipeline echo chamber
5. Missing concert hall — genuinely unique feature not in tour
6. Missing outdoor mosaic — first thing visitors physically see

### **Spine POC Evidence**
- File: `development/chagall_spine_poc.json` (committed `aeae15a`)
- Quality verdict: hook genuine, emotional beats differentiated, climax at Stop 7 correct
- Weakness: closing_revelation too abstract — fixed in task #15 (spine template update)
- Cost: $0.01421, 11.6s, 546 tokens in / 1284 out

---

## 🔑 **KEY CREDENTIALS & LOCATIONS**

### **AWS / Amazon Q**
- **Amazon Q Pro**: $19/month flat rate
- **IAM Identity Center URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Apple Developer**: Order W1583339145, glikfamily@gmail.com, Team 4HGRU6TKGQ

### **Key File Locations**
- **Dev Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\development\`
- **Backup Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\backup\`
- **Git Repo (Mac Mini)**: `~/Development/Audioura-build/`
- **Cloud Migration Spec**: `development/AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`
- **Store Submission Spec**: `C:\Business\audiotours.com\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`
- **Storied Dev Plan**: `development/STORIED_DEVELOPMENT_PLAN.md`
- **Storied Architecture Split**: `development/NEW_ARCHITECTURE_STORIED_SPLIT.md`
- **Storied Task Index**: `development/storied_tasks_index.md` (task #92 — for ClickUp import)
- **Transition Docs**: `development/transition_for_*.md` — one per Amazon-Q role
- **Storied Handoffs**: `development/storied_handoff_for_mobile.md` + `storied_handoff_for_ios.md`

### **GitHub Secret Scanning — Lessons Learned**
- NEVER commit files containing `ghp_` tokens or plain-text passwords
- Resolution: `git reset --mixed <commit-before-bad>`, redo commits cleanly
- NEVER click "Allow secret" on GitHub

---

## 🏗️ **PLATFORM OWNERSHIP MODEL**
- 🍎 **iOS AMAZON-Q**: Complete iOS ownership (Flutter fixes, Xcode, App Store, iPhone testing)
- 📱 **MOBILE APP AMAZON-Q**: Complete Android ownership (APK builds, Play Store, Android testing)
- 🔧 **SERVICES AMAZON-Q (Kiro)**: Backend & AWS — owns all 95 Storied service tasks
- 🎯 **STRATEGIC ADVISOR AMAZON-Q**: Cross-platform coordination & business decisions
- 🎪 **DEMO AMAZON-Q**: Testing & validation for both platforms

### **AMAZON Q ON MAC MINI**
- **Install**: VS Code + Amazon Q extension OR Kiro (found at `C:\Users\micha\AppData\Local\Programs\Kiro\Kiro.exe`)
- **Auth Method**: IAM Identity Center (NOT Builder ID)
- **Startup URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Recovery file**: `remind_macmini.md`

---

## 📊 **STRATEGIC PHASES**

### **PHASE 0: PLATFORM FOUNDATION (COMPLETE)**
- ✅ iOS + Android stable on v1.2.9+66
- ✅ Git repository clean and fully synced
- ✅ A#75 complete — v1.2.9+65 shipped

### **PHASE 1: GCP MIGRATION (IN PROGRESS — 20-30 hrs total)**
- ✅ **M01** — Pre-migration audit — complete
- 🔄 **M02** — Local cloud-ready rehearsal — Step 1 done, Steps 2-5 remaining — $0 GCP cost
- ⬜ **M03** — GCP project setup (~3 hrs) — **billing starts here ~$35/month**
- ⬜ **M04** — Service-by-service deploy to PreProd (~10-15 hrs)
- ⬜ **M05** — Production cutover (~2-4 hrs) — gates App Store submission
- **Target architecture**: Cloud Run (13 services) + Cloud SQL Postgres + Cloudflare R2
- **Floor cost at launch**: ~$36/month
- **Key cost outlier**: newsletter-processor (headless Chrome, 4 GB RAM, concurrency=1)

### **PHASE 2: STORIED RELEASE (IN PROGRESS — Aug 1 target)**
- 🔄 **Task generation complete** — 95 tasks on `storied` branch
- ⬜ **ClickUp import** — Claude.AI imports `storied_tasks_index.md`
- ⬜ **Sprint execution** — Services Kiro + Mobile Q + iOS Q (4 weeks)
- ⬜ **Aug 1** — Google Play closed test + Apple TestFlight live

### **PHASE 3: APP STORE PRODUCTION (blocked on M04+M05)**
- iOS App Store + Google Play Store production release
- Version: v2.2.0 Storied (not v1.2.9 Beta)
- No IAP in v1.0 — RevenueCat in v1.3 post-launch

### **PHASE 4: NEW ARCHITECTURE (post-Storied)**
- Deep RAG perspective layers (Artist/Historian/Curator)
- Passive preference inference from replay behavior
- Tour caching Level 2 (fuzzy POI matching)
- Trend intelligence + "Popular near you"
- Epic: `wdvrdaw13n` in ClickUp

---

## 🏗️ **GCP MIGRATION — KEY FACTS FOR ADVISOR**

### **Architecture decisions (locked)**
- Cloud Run per service (13 total) — matches current Docker Compose exactly
- Cloud SQL Postgres db-g1-small prod (~$25/mo), db-f1-micro preprod (~$10/mo)
- Cloudflare R2 for audio files — zero egress fees
- AWS Polly stays — no migration off Polly for v1
- Two GCP projects: `audioura-preprod` + `audioura-prod` (hard isolation)
- Subdomain-per-service — saves $18/month vs Cloud Load Balancer
- No prod Cloud SQL until M05 — saves $25/month during M04

### **Phase gate rules (Advisor Q enforces)**
- **M03 gate**: Don't provision prod Cloud SQL until M05
- **App Store gate**: BLOCK submission until M04+M05 complete (public HTTPS required)
- **No IAP gate**: If anyone proposes subscriptions/IAP for v1 — answer is NO (Apple 3.1.1)
- **Cloudflare Tunnel stopgap**: NO — Apple review window catches laptop offline overnight
- **Storied gate**: BLOCK enforce attestation mode until after Aug 1 log data reviewed

### **Working agreement**
- Amazon-Q drafts each phase's scripts
- Claude reviews before execution (V2 discipline)
- Sir Michael executes; authorizes destructive operations

---

## 🛠️ **WINDOWS TOOLING LESSONS**
- **Batch files**: Use `cmd /c "full\path\to\file.bat"` to run batch files from executeBash
- **Multi-command**: Use `&&` operator for short chains
- **git branch switch blocked**: Use `git stash --include-untracked` then `git checkout`, then `git stash pop`
- **Wrong branch commit**: Use `git reset --mixed HEAD~1` to undo, then checkout correct branch
- **git status clean**: All `??` untracked files must be committed or moved to backup

---

**Last Updated**: 2026-06-29 Session 7
**Status**: ✅ v1.2.9+66 Beta both platforms | ✅ M01 complete | 🔄 M02 in progress | ✅ 95 Storied tasks committed to `storied` branch
**Active Branches**: `services-migration` (GCP migration) | `storied` (Storied release, HEAD `48a9d5a`)
**Two Active Tracks**: A) GCP Migration M02→M05 | B) Storied Release Aug 1
**Next Milestone**: ClickUp import of Storied tasks + M02 remaining steps


---

## 📦 STORIED BRANCH STATUS (Updated by S87)

**Branch**: `storied` (latest on origin)
**Base**: off `main` = `beta-2.1.1+18`

### Task Progress
- **Tasks completed**: 70+ of 95
- **Tasks in review**: ~20
- **Tasks remaining**: ~5 (blocked on live execution or Michael-owned)

### Key Files Added (Python modules)
| File | Purpose |
|------|---------|
| `spine_generator.py` | Narrative spine generation (gpt-4o, $0.014/tour) |
| `fact_extractor.py` | RAG-grounded fact sheets per stop (gpt-3.5-turbo) |
| `story_type_assigner.py` | 6-type taxonomy assignment + persona weighting |
| `derepetition_guard.py` | Cross-stop repetition detection + auto-rewrite |
| `directions_generator.py` | Improved non-fabricated directions (museum + walking) |
| `tour_hook_generator.py` | Tour introduction generated from spine hook |
| `onboarding_preference.py` | 4 personas (art_lover, history_buff, foodie, explorer) + weights |
| `persona_preference_store.py` | Postgres-backed persona persistence |
| `persona_endpoints.py` | POST/GET /user/persona |
| `tour_sharing.py` + `sharing_endpoints.py` | Share links + POST/GET /tour/share |
| `referral_engine.py` + `referral_endpoints.py` | Referral codes + attribution tracking |
| `attestation_verifier.py` | Play Integrity + App Attest (log-only mode) |
| `cost_ceiling_monitor.py` | $0.15/tour ceiling guard (logged, never aborts) |
| `storied_version_constants.py` | v2.2.0 versioning constants |

### Pipeline Changes (STORIED_MODE=true enables)
- Narrative spine generation before per-stop content
- Fact extraction with RAG grounding (Wikipedia API)
- Story-type taxonomy applied per stop
- De-repetition guard scans + rewrites across all stops
- Directions generated from structured data (no fabrication)
- Tour hook/intro generated from spine
- Persona weighting applied to story selection
- Share link auto-created after successful generation (S82)
- Cost ceiling monitored per tour ($0.15 cap, log-only)
- Attestation tokens validated (log-only, never blocks)

### Next Steps
- **S79**: Flip `STORIED_MODE=true` in docker-compose for all services
- **S40**: Full QA pass — regression + new feature validation
- **S94**: Storied launch checklist sign-off
- **S95**: Final gate — all automated items PASS + Michael items confirmed

