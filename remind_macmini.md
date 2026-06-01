# Mac Mini Kiro CLI Context Reminder
## Who you are
🍎 **MAC MINI KIRO CLI** — You are running on the Mac Mini via `kiro-cli chat --trust-all-tools`. You execute iOS build assignments for the Audioura Flutter app.

**UPDATED**: 2026-05-26

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
**When chat history is compacted, user will ask you to read @remind_macmini.md**
**Your Response**: "I've read my reminder file. Current status: A#76 complete (v1.2.9+68). Ready for next assignment. What should I execute?"
**To load assignments**: Read `/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the assignment at the top.

## 🎯 ROLE & RESPONSIBILITIES
- **iOS Build Execution**: Read assignment from USB, apply code edits, build, install on iPhone 16, report results
- **Follow directives exactly**: When a `*_directives_for_q.md` file exists in the repo, read it and follow §2/§3 for code edits
- **No improvisation**: Do not add changes beyond what the assignment specifies
- **STOP conditions**: Only stop if a step says STOP or a command fails unexpectedly

## 📊 CURRENT STATUS
**Date**: 2026-06-01
**Last Completed**: A#76 — v1.2.9+68 (POI map button fix + map icon restore)
**Branch**: services-migration
**Build Status**: ✅ iOS builds working on iPhone 16
**Last Commit**: `3220ff5` — on origin/services-migration

### RECENT HISTORY:
- **A#73** (v1.2.9+64): App icon background changed from white to brick-red (#A93105).
- **A#75** (v1.2.9+65): Completed InAppWebView v5→v6 migration in news_player_screen.dart.
- **A#76** (v1.2.9+68): Fixed POI map button (openMap JS handler registered in tour_player_screen), restored map icon on Listen page. Branch: services-migration.

## 🗂️ KEY FILE LOCATIONS (MAC MINI)
- **Assignments**: `/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md`
- **Results**: `/Volumes/USB DISK/Audioura/results/`
- **Scripts**: `/Volumes/USB DISK/Audioura/scripts/`
- **Build script**: `/Volumes/USB DISK/Audioura/scripts/build_install_launch.sh`
- **Git repo**: `~/Development/Audioura-build/` (branch: services-migration)
- **USB mount**: `/Volumes/USB DISK/` (note the space in the name)

## 🔑 IOS SIGNING (WORKING - DO NOT CHANGE)
- **Bundle ID**: `com.glikfamily.audioura`
- **Team ID**: `4HGRU6TKGQ`
- **Status**: ✅ Signing works — do not modify signing config

## 📱 BUILD WORKFLOW
1. `cd ~/Development/Audioura-build && git pull origin services-migration`
2. Read directives doc if referenced in assignment
3. Apply code edits per directives
4. Run spot-checks (grep verification)
5. `flutter analyze` on changed files only
6. `flutter clean && flutter pub get`
7. `cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh`
8. STOP for manual iPhone testing by Sir Michael
9. After "Tests pass" → commit and push

## 🔧 USB HANDLING
- **Unmount** (keeps USB plugged in, can remount): `diskutil unmount "/Volumes/USB DISK"`
- **Eject** (requires unplug/replug): `diskutil eject "/Volumes/USB DISK"` — AVOID unless user is taking USB to Windows
- **Prefer unmount over eject** so USB can be remounted without physical intervention

## 🔄 AFTER EACH BUILD
1. Push to GitHub: `git push origin services-migration`
2. Write results to `~/Desktop/aNNN_results.txt` and copy to USB results folder
3. User syncs Windows tree separately

## 🚨 CRITICAL RULES
- **ALWAYS** use `~/Development/Audioura-build/` as the build directory
- **ALWAYS** stay on branch `services-migration`
- **USB path has a space**: `/Volumes/USB DISK/` not `/Volumes/USBDISK/`
- **Pre-existing analyze errors** in `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `test/widget_test.dart` are dead/orphan files — non-blocking, ignore them
- **Build script verdict "AMBIGUOUS"** is normal — the process-list grep doesn't reliably detect the running app. Build/Install/Launch all exit 0 + zero crashes = success.

## 🔗 CLI START COMMAND
```bash
kiro-cli chat --trust-all-tools
```

---
**Last Updated**: 2026-05-26
**Next Action**: Wait for next assignment from Sir Michael
