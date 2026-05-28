# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-01 SESSION 4 - Git fully clean, branch synced, A#75 directives committed, ready for Mac Mini

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**: "🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Current status: git fully clean and synced with origin/Newsletters. mac_mini_setup_guide.md committed and pushed. A#75 directives committed and pushed. IMMEDIATE NEXT ACTIONS:
1. Eject USB drive, carry to Mac Mini, switch KVM
2. On Mac Mini: git pull origin Newsletters
3. Execute A#75 per a75_directives_for_q.md (verify v6 migration, bump to v1.2.9+65, build, commit, push)
4. After Mac Mini pushes: git pull origin Newsletters on Windows to sync
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
**Date**: 2026-06-01 (Session 4)
**Version**: v1.2.9+64 (A#73 complete — brick red icon background #A93105)
**Next Version**: v1.2.9+65 (A#75 — InAppWebView v6 migration in news_player_screen.dart)
**Branch**: Newsletters
**Overall Status**: ✅ **iOS BUILDS ACTIVE** — A#63 through A#73 executed successfully on Mac Mini

### **COMPLETED THIS SESSION (Session 4)**:
1. ✅ **mac_mini_setup_guide.md sanitized**: `Eight6Eight7!` → `<YOUR_GITHUB_PASSWORD>`, PAT already replaced in prior session
2. ✅ **mac_mini_setup_guide.md committed and pushed**: commit `6c52ef3`
3. ✅ **Git history rewritten**: Removed commits containing GitHub PAT secret (771ac20, 926af38, 68f98c7) — redone cleanly
4. ✅ **~100 log/output txt files moved to backup**: terminal_output_*, Xcode_*, *_results.txt, fix_*, verify_*, etc.
5. ✅ **27 meaningful files committed**: requirements*.txt, prompt templates, tour content, architecture docs — commit `3764d93`
6. ✅ **enhanced_tour_content.txt committed, mobile_app_logs removed**: commit `e31f87e`
7. ✅ **a75_directives_for_q.md created and pushed**: commit `76baaf2`
8. ✅ **Branch fully clean**: zero untracked files, zero modified files, up to date with origin/Newsletters

### **GIT STATE**:
- **Branch**: Newsletters
- **Last commit**: `76baaf2` — A#75 directives for v6 InAppWebView migration
- **Remote**: up to date with origin/Newsletters ✅
- **Working tree**: clean — zero `??` untracked, zero modified

### **iOS BUILD HISTORY (RECENT)**:
- **A#71**: ✅ COMPLETE - v1.2.9+62 - App name fix + InAppWebViewSettings v6 (tour_player_screen only)
- **A#72**: ✅ COMPLETE - v1.2.9+63 - Heal stale iOS container paths for news articles
- **A#73**: ✅ COMPLETE - v1.2.9+64 - Brick red app icon background (#A93105)
- **A#74**: ✅ COMPLETE - Windows-side cleanup (this session)
- **A#75**: 🔄 NEXT — InAppWebView v6 migration in news_player_screen.dart → v1.2.9+65

---

## 🚨 **IMMEDIATE NEXT ACTIONS**

### **A#75 Execution on Mac Mini**
1. Eject USB drive from Windows
2. Carry USB to Mac Mini, switch KVM
3. On Mac Mini: `git pull origin Newsletters`
4. Mac Mini Q reads `a75_directives_for_q.md` and executes:
   - Verify `news_player_screen.dart` already has v6 API (`initialSettings: InAppWebViewSettings(...)`)
   - If confirmed correct → skip code change
   - Bump `pubspec.yaml`: `1.2.9+64` → `1.2.9+65`
   - `flutter analyze` → must show no issues in our code
   - `flutter build ios --release --no-codesign`
   - `git commit -m "v1.2.9+65 - A#75: InAppWebView v6 migration in news_player_screen.dart"`
   - `git push origin Newsletters`
5. After Mac Mini pushes: `git pull origin Newsletters` on Windows

### **Key insight about A#75**:
The Windows copy of `news_player_screen.dart` already uses v6 API (`initialSettings: InAppWebViewSettings(...)` with flat settings). Mac Mini Q should verify this is in the pulled code and skip the migration step if confirmed. The only guaranteed work is version bump + build + commit.

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
- **Git Repo (Mac Mini)**: `~/Development/Audioura-build/` (branch: Newsletters)
- **A#75 Directives**: `development/a75_directives_for_q.md` (committed `76baaf2`)

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

### **PHASE 0: PLATFORM FOUNDATION (LARGELY COMPLETE)**
- ✅ iOS builds working (A#63-A#73 on Mac Mini)
- ✅ Android stable
- ✅ Git repository clean and fully synced
- ✅ Development directory cleaned (300+ one-shot files moved to backup)
- ✅ mac_mini_setup_guide.md sanitized and committed
- 🔄 A#75 next on Mac Mini

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

## 📋 **NEXT ACTION ON MAC MINI**
Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute A#75.
Companion doc: `development/a75_directives_for_q.md` (already in git, pulled with `git pull`).
After Mac Mini pushes A#75: run `git pull origin Newsletters` on Windows to sync.

---

**Last Updated**: 2026-06-01 Session 4
**Status**: ✅ Git fully clean + synced | ✅ mac_mini_setup_guide committed | ✅ A#75 directives committed
**Current Build**: v1.2.9+64 (A#73)
**Next Build**: v1.2.9+65 (A#75) on Mac Mini
**No Blockers**: iOS signing works, builds succeed, git clean, directives ready
