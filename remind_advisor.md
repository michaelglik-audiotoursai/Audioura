# Strategic Advisor Amazon-Q Context Reminder
## Who you are
🎯 **STRATEGIC ADVISOR AMAZON-Q** - **CRITICAL**: Always start all replies with "🎯 STRATEGIC ADVISOR AMAZON-Q -" to help identify which Amazon-Q tab is being used across multiple Eclipse tabs.

**UPDATED**: 2026-06-01 SESSION 3 - Git cleanup complete, branch synced to origin, mac_mini_setup_guide sanitization IN PROGRESS

## 🚨 **POST-COMPACTION RECOVERY PROTOCOL**
**When chat history is compacted, user will ask you to read @remind_advisor.md**

**Your Response**: "🎯 STRATEGIC ADVISOR AMAZON-Q - Context restored. Current status: git cleanup complete (branch up to date with origin/Newsletters), mac_mini_setup_guide sanitization in progress. IMMEDIATE NEXT ACTIONS in order:
1. Replace `Eight6Eight7!` password in sanitized file with `<YOUR_GITHUB_PASSWORD>`
2. Copy sanitized file to `development/mac_mini_setup_guide.md`
3. Commit it to git
4. Move remaining untracked files to backup or commit as appropriate
5. Final git status should show only remind_*.md files as modified
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
**Date**: 2026-06-01 (Session 3)
**Version**: v1.2.9+64 (A#73 complete - brick red icon background #A93105)
**Branch**: Newsletters
**Overall Status**: ✅ **iOS BUILDS ACTIVE** - A#63 through A#73 executed successfully on Mac Mini

### **CRITICAL RECENT DEVELOPMENTS**:
1. ✅ **A#73 COMPLETE**: v1.2.9+64 - Brick red (#A93105) app icon background
2. ✅ **A#74 NEXT**: Check mac_mini_assignments.md for details
3. ✅ **Git Cleanup Complete**: Branch is up to date with origin/Newsletters
4. ✅ **Development Directory Cleaned**: 300+ one-shot scripts moved to backup/
5. ✅ **.gitattributes Created**: CRLF line ending normalization in place
6. ✅ **95 Active Files Committed**: docs, configs, scripts all tracked
7. ✅ **audioura-dev.apk**: Removed from tracking, added to .gitignore
8. ✅ **mac_mini_setup_guide.md**: Removed from tracking, added to .gitignore
9. 🔄 **mac_mini_setup_guide SANITIZATION**: IN PROGRESS - see next actions

### **iOS BUILD HISTORY (RECENT)**:
- **A#71**: ✅ COMPLETE - v1.2.9+62 - App name fix + InAppWebViewSettings v6
- **A#72**: ✅ COMPLETE - v1.2.9+63 - Heal stale iOS container paths for news articles
- **A#73**: ✅ COMPLETE - v1.2.9+64 - Brick red app icon background (#A93105)
- **A#74**: NEXT - check mac_mini_assignments.md for details
- **A#75**: Queued - InAppWebView v5→v6 migration in news_player_screen.dart

---

## 🚨 **IMMEDIATE NEXT ACTIONS (Session 3 continuation)**

### **Step 1 — Sanitize mac_mini_setup_guide.md**
Sanitized file is at:
`C:\Users\micha\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\local-agent-mode-sessions\17afb077-b5b1-4bc7-b11e-04e1412c0979\e5312285-0070-46ea-b69d-0ee21379d3cf\local_af4bc9e8-6f37-4e33-b878-857a33329151\outputs\mac_mini_setup_guide_sanitized.md`

The file already has the GitHub PAT replaced with `<YOUR_GITHUB_PAT_FROM_DOTENV>` but still contains the plain-text password `Eight6Eight7!` in Step 9. Replace ALL occurrences of `Eight6Eight7!` with `<YOUR_GITHUB_PASSWORD>` before copying.

### **Step 2 — Copy to development/**
Copy sanitized file to:
`c:\Users\micha\eclipse-workspace\AudioTours\development\mac_mini_setup_guide.md`

Note: `mac_mini_setup_guide.md` is in `.gitignore` so it will NOT be committed — it stays local only. This is intentional (contains setup instructions with credential placeholders).

### **Step 3 — Handle remaining untracked files**
Current `git status` shows ~65 untracked files. ALL are covered by `.gitignore` patterns:
- `Terminal_output_*.txt` → gitignored
- `Xcode_build_*.txt`, `Xcode_installation_error*.txt` → gitignored
- `*_results.txt` → gitignored
- `MANUAL_COMMANDS.txt` → gitignored
- `actual_ai_response.txt`, `actual_prompt_used.txt` etc. → gitignored
- `mac_mini_setup_guide.md` → gitignored
- `{repr(content[m.start()` → gitignored (Python error artifact)

These files are invisible to git already. No action needed — they will NOT appear in commits.

### **Step 4 — Files still needing commits**
These untracked files are NOT gitignored and need to be committed:
- `CLAUDE_ANSWER_GIT_PUSH_BLOCKED.md` — commit (historical record)
- `CLAUDE_QUESTION_GIT_PUSH_BLOCKED.md` — commit (historical record)
- `a74_cleanup_executor.bat` — review then commit or move to backup

### **Step 5 — Final git status expectation**
After all above steps, `git status` should show:
- `M remind_Services_ai.md` — agents own this, leave modified
- `M remind_ai.md` — agents own this, leave modified
- `M remind_ios_ai.md` — agents own this, leave modified
- `M remind_mobile_ai.md` — agents own this, leave modified
- `M remind_advisor.md` — this file, leave modified
- Zero `??` untracked files (all gitignored or committed)

---

## 🔑 **KEY CREDENTIALS & LOCATIONS**

### **AWS / Amazon Q**
- **Amazon Q Pro**: $19/month flat rate
- **IAM Identity Center URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Apple Developer**: Order W1583339145, glikfamily@gmail.com, Team 4HGRU6TKGQ

### **Key File Locations**
- **Assignments (Windows)**: `D:\Audioura\assignments\mac_mini_assignments.md`
- **Assignments (Mac/USB)**: `/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md`
- **Dev Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\development\`
- **Backup Directory**: `c:\Users\micha\eclipse-workspace\AudioTours\backup\`
- **Git Repo (Mac Mini)**: `~/Development/Audioura-build/` (branch: Newsletters)
- **Cleanup Log**: `development\CLEANUP_LOG_05272026_1132.md`

### **Git State**
- **Branch**: Newsletters
- **Remote**: up to date with origin/Newsletters ✅
- **Last commit**: `2bc7eeb` — Remove APK + mac_mini_setup_guide from tracking
- **No pending pushes**

### **GitHub Secret Scanning Resolution**
- The 14-commit push problem was resolved by removing the 14 commits and re-doing them cleanly
- `mac_mini_setup_guide.md` is now in `.gitignore` — will never be committed again
- `audioura-dev.apk` is now in `.gitignore` — will never be committed again
- Sanitized version of mac_mini_setup_guide uses `<YOUR_GITHUB_PAT_FROM_DOTENV>` and `<YOUR_GITHUB_PASSWORD>` placeholders

---

## 🏗️ **PLATFORM OWNERSHIP MODEL**
- 🍎 **iOS AMAZON-Q**: Complete iOS ownership (Flutter fixes, Xcode, App Store, iPhone testing)
- 📱 **MOBILE APP AMAZON-Q**: Complete Android ownership (APK builds, Play Store, Android testing)
- 🔧 **SERVICES AMAZON-Q**: Backend & AWS (serves both platforms equally)
- 🎯 **STRATEGIC ADVISOR AMAZON-Q**: Cross-platform coordination & business decisions
- 🎪 **DEMO AMAZON-Q**: Testing & validation for both platforms

### **AMAZON Q ON MAC MINI**
- **Install**: VS Code + Amazon Q extension (recommended)
- **Auth Method**: IAM Identity Center (NOT Builder ID)
- **Startup URL**: `https://d-90663ec2be.awsapps.com/start/`
- **Username**: `audiotoursai@gmail.com`
- **Recovery file**: `remind_macmini.md`

---

## 📊 **STRATEGIC PHASES**

### **PHASE 0: PLATFORM FOUNDATION (LARGELY COMPLETE)**
- ✅ iOS builds working (A#63-A#73 on Mac Mini)
- ✅ Android stable
- ✅ Git repository clean
- 🔄 A#74 next on Mac Mini

### **PHASE 1: PRODUCTION LAUNCH (2-4 weeks)**
- App Store submissions (iOS + Google Play)
- AWS-hosted public services
- Version consolidation: v1.2.9 → v1.3.0

### **PHASE 2: MARKET OPTIMIZATION (1-2 months)**
- User feedback integration
- Feature adoption tracking
- App store rating optimization

---

## 📋 **NEXT ACTION ON MAC MINI**
Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute A#74.
After Mac Mini pushes A#74: run `git pull origin Newsletters` on Windows to sync.

---

**Last Updated**: 2026-06-01 Session 3
**Status**: ✅ Git clean + synced | 🔄 mac_mini_setup_guide sanitization in progress
**Current Build**: v1.2.9+64 (A#73)
**Next Build**: A#74 on Mac Mini
**No Blockers**: iOS signing works, builds succeed, git clean
