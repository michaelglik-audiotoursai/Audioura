# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

---

### 🎯 **CURRENT PRIORITY — ASSIGNMENT 35**
- **Status**: READY FOR EXECUTION (files prepared, not yet deployed to Mac Mini)
- **Focus**: Drop `permission_handler` for mic check, use `speech_to_text` natively — v1.2.9+30
- **Scripts**: `copy_ios_fixes.sh` (13 files) then `build_install_launch.sh`
- **Instructions**: Full details in `D:\Audioura\assignments\mac_mini_assignments.md` (A#35 at top)

---

### 🚀 **QUICK CONTEXT RECOVERY**
- **Mission**: iOS Amazon-Q for Audioura LLC mobile app
- **App name**: Audioura (com.glikfamily.audioura)
- **Device**: iPhone 16, UDID `F9D6F807-D301-59EE-B574-5747D617D82C`, iOS 18.3.1
- **Apple Dev**: Team ID `4HGRU6TKGQ`, paid license (Order W1583339145, glikfamily@gmail.com), valid until April 7 2027
- **Certificate**: Apple Development: Mikhail Glik (594584F3D3BC571D94A822A2158871CA13898701)
- **Flutter UDID** (provisioning): `00008140-000558A902BA801C`
- **Repo**: `https://github.com/michaelglik-audiotoursai/Audioura`
- **Branches**: `main` (stable Android), `Newsletters` (Android dev), `ios-dev` (iOS dev)
- **Git status**: Both `Newsletters` and `ios-dev` at commit `85f0fff` (v1.2.9+26) — v1.2.9+27 through v1.2.9+30 NOT yet committed
- **Network**: iPhone → Windows laptop Docker services at `192.168.0.218:5002/5004/5005`
- **Build environment**: Mac Mini M4 + Xcode 16, project at `~/Development/AudioTours/development/audio_tour_app`

---

### 📱 **APP STATUS**
- **Version ready to deploy**: 1.2.9+30
- **Last version on iPhone**: 1.2.9+29 (A#34 — still showing "Microphone Access Required" even with permission granted in Settings)
- **Features confirmed working on iPhone**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, first-launch mic dialog
- **Known backend issue**: Tour generation fails with `generate_enhanced_prompt() takes 2 positional arguments but 3 were given` — Services-side Python bug, NOT mobile.

---

### 🔧 **WHAT CHANGED IN v1.2.9+30 (A#35 fix)**

**Bug — `permission_handler` caches `permanentlyDenied`, never re-reads iOS Settings**
- File: `voice_control_service.dart`
- Root cause: `permission_handler` is a known iOS limitation — once it sees `permanentlyDenied`, it caches that state internally and never re-queries iOS, even after the user enables the permission in Settings. Every call to `Permission.microphone.status` kept returning `permanentlyDenied` regardless of actual state.
- Fix: `startVoiceListening()` no longer uses `permission_handler` at all. Instead calls `_speechToText.initialize()` fresh on every mic button press. `speech_to_text` calls iOS `SFSpeechRecognizer.requestAuthorization()` and `AVAudioSession` directly — always reflects live iOS state, no caching.
- If `initialize()` returns `true` → voice starts immediately.
- If `initialize()` returns `false` → "Open Settings" dialog shown.

---

### 📋 **A#35 ASSETS READY ON USB**
13 files in `D:\Audioura\assets\` — only 2 changed from A#34:
- `lib/services/voice_control_service.dart` ← speech_to_text native check
- `pubspec.yaml` ← version 1.2.9+30

**⚠️ Delete app from iPhone before installing** to get a clean permission state.

---

### 🔄 **WORKFLOW RULES (enforced)**
1. `copy_ios_fixes.sh` — file copy only. NEVER add build/install logic.
2. `build_install_launch.sh` — proven stable build/install rig. NEVER modify unless Flutter/Xcode toolchain changes.
3. `build_install_launch_a28.sh` — history only, do not reuse.
4. Every new assignment = update assets + bump pubspec.yaml + run copy script + run build script.
5. After successful Mac Mini build → commit to `Newsletters` branch → merge to `ios-dev` → push both.

---

### 📌 **PENDING AFTER A#35**
- Git commit v1.2.9+27 through v1.2.9+30 to `Newsletters` and `ios-dev` (none committed yet)
- Services Amazon-Q needs to fix `generate_enhanced_prompt()` Python bug for tour generation to work
- After tour generation works: test end-to-end tour generation on iPhone (future assignment)

---

### 🔄 **ASSIGNMENT HISTORY**
- **A#18**: Manual Xcode install proven, CwlCatchException crash identified
- **A#19–A#26**: CwlCatchException elimination + xcconfig fix attempts
- **A#27**: ✅ baseConfigurationReference fix — build barrier eliminated
- **A#28**: ✅ App running on iPhone 16 — iOS barrier completely eliminated
- **A#29**: ✅ v1.2.9+24 — device info, settings persistence, location permissions
- **A#30**: ✅ v1.2.9+25 — full feature parity (home_screen + all services/widgets)
- **A#31**: ✅ v1.2.9+26 — keyboard dismissal fix on Tour Generator screen
- **A#32**: ✅ v1.2.9+27 — mic permanentlyDenied handling + download spinner fix
- **A#33**: ✅ v1.2.9+28 — mic first-launch system dialog + build_install_launch.sh rename
- **A#34**: ✅ v1.2.9+29 — mic permission request logic fix (still failed — permission_handler caching bug)
- **A#35**: 🎯 READY — v1.2.9+30 drop permission_handler for mic, use speech_to_text natively

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **CRLF ISSUE**: `home_screen.dart` and `tour_generator_screen.dart` have CRLF line endings. `fsReplace` tool fails on these files. Always use a Python script via `fsWrite` + `executeBash` to modify them.
- **PYTHON OUTPUT**: Python `print()` output is NOT visible in `executeBash` stdout. Write results to a file and read with `fsRead`.
- **COPY SCRIPT**: `copy_ios_fixes.sh` (version-neutral).
- **BUILD SCRIPT**: `build_install_launch.sh` (generic, from A#33 onward). `build_install_launch_a28.sh` is history.
- **permission_handler iOS CACHING BUG**: Once `permission_handler` sees `permanentlyDenied`, it never re-reads from iOS. Do NOT use it for mic status checks in `startVoiceListening()`. Use `speech_to_text.initialize()` instead.
- **MIC PERMISSION FLOW (v1.2.9+30)**:
  - First install → `requestMicPermissionOnFirstLaunch()` (uses `permission_handler` once for the initial dialog — this is fine)
  - Mic button / triple-click → `startVoiceListening()` → `_speechToText.initialize()` called fresh → if `true` → voice starts; if `false` → "Open Settings" dialog

---

### 🔧 **TROUBLESHOOTING**
```bash
# iPhone not detected — try in order:
sudo launchctl kickstart -k system/com.apple.usbd
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
# Restart Mac Mini as last resort

# Flutter checks
flutter doctor -v
flutter devices
security find-identity -v -p codesigning
```

---
**Last Updated**: 2026-05-08 — A#35 ready, v1.2.9+30 assets prepared, not yet deployed
**iOS Amazon-Q Version**: 41.0
