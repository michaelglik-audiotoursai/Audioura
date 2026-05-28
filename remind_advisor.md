# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-02 SESSION 5 - A#75 complete, v1.2.9+65 shipped on both iOS and Android, Claude transition docs committed, services migration next

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**: "🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Current status: v1.2.9+65 shipped on both iOS and Android (A#75 complete). Git clean and synced. Claude transition docs committed. IMMEDIATE NEXT ACTIONS:
1. Read transition_for_Advisor_AQ.md for full strategic context
2. Coordinate Services Q to begin GCP migration (M01) per AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md
3. Block App Store / Play Store submission until Services M04+M05 complete (public HTTPS gate)
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
**Version**: v1.2.9+65 (A#75 complete — InAppWebView v6 migration in news_player_screen.dart)
**Branch**: services-migration
**Overall Status**: ✅ **BOTH PLATFORMS ON v1.2.9+65** — iOS and Android synchronized

### **COMPLETED SESSION 4**:
1. ✅ mac_mini_setup_guide.md sanitized and committed (`6c52ef3`)
2. ✅ Git history rewritten — removed commits with GitHub PAT secret
3. ✅ ~100 log/output txt files moved to backup
4. ✅ 27 meaningful files committed (`3764d93`)
5. ✅ a75_directives_for_q.md created and pushed (`76baaf2`)

### **COMPLETED SESSION 5**:
1. ✅ **A#75 complete**: v1.2.9+65 shipped — InAppWebView v6 in news_player_screen.dart (`5adcee7`)
2. ✅ **Claude transition docs committed**: claude_io_handoff.md, git_branch_strategy.md, transition_for_*.md x5, audioura-dev.apk (`bd473f7`)
3. ✅ **Branch fully clean**: up to date with origin/services-migration

### **GIT STATE**:
- **Branch**: services-migration
- **Last commit**: `bd473f7` — Claude transition/handoff docs + audioura-dev.apk
- **Remote**: up to date with origin/services-migration ✅
- **Working tree**: clean (log_iphone_05282026_0038.txt intentionally untracked)

### **BUILD HISTORY (RECENT)**:
- **A#71**: ✅ COMPLETE - v1.2.9+62 - App name fix + InAppWebViewSettings v6 (tour_player_screen only)
- **A#72**: ✅ COMPLETE - v1.2.9+63 - Heal stale iOS container paths for news articles
- **A#73**: ✅ COMPLETE - v1.2.9+64 - Brick red app icon background (#A93105)
- **A#74**: ✅ COMPLETE - Windows-side cleanup (Session 4)
- **A#75**: ✅ COMPLETE - v1.2.9+65 - InAppWebView v6 migration in news_player_screen.dart (`5adcee7`)
- **NEXT**: Services GCP migration M01 (Services Q owns execution)

---

## 🚨 **IMMEDIATE NEXT ACTIONS**

### **Services GCP Migration (Services Q owns)**
1. Services Q reads `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` and begins M01
2. Advisor Q tracks phase progress — surface to Sir Michael if any phase slips >30%
3. Watch GCP billing — floor is ~$10/month (Cloud SQL). Newsletter-processor is cost outlier (headless Chrome)
4. **GATE**: App Store + Play Store submission blocked until M04+M05 complete (public HTTPS required)

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
- **Cloud Migration Spec**: `C:\Business\AudioTours.io\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`
- **Store Submission Spec**: `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`

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
- ✅ Android stable, both platforms on v1.2.9+65
- ✅ Git repository clean and fully synced
- ✅ Development directory cleaned (300+ one-shot files moved to backup)
- ✅ mac_mini_setup_guide.md sanitized and committed
- ✅ A#75 complete — v1.2.9+65 shipped

### **PHASE 1: PRODUCTION LAUNCH (2-4 weeks)**
- App Store submissions (iOS + Google Play)
- AWS-hosted public services
- Version consolidation: v1.2.9 → v1.3.0

### **PHASE 2: MARKET OPTIMIZATION (1-2 months)**
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

## 📋 **NEXT ACTION**
Coordinate Services Q to begin GCP migration M01 per `AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`.
Read `transition_for_Advisor_AQ.md` for full decision table and cost monitoring responsibilities.

---

**Last Updated**: 2026-06-02 Session 5
**Status**: ✅ Git fully clean + synced | ✅ v1.2.9+65 on both platforms | ✅ Claude transition docs committed
**Current Build**: v1.2.9+65 (A#75) — iOS + Android
**Next Milestone**: Services GCP migration M01 → gates App Store submission
**No Blockers**: Both platforms stable, git clean, transition docs ready
