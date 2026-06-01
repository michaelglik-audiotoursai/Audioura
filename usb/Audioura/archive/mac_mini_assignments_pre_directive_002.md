# Mac Mini Assignment Instructions
## iOS Development Task Execution

---
# Time: 04/25/2026 21:45 - ASSIGNMENT 18 COMPLETE, ASSIGNMENT 19 READY
🍎 iOS AMAZON-Q - ASSIGNMENT 19: ELIMINATE CWLCATCHEXCEPTION COMPLETELY

## 🎉 ASSIGNMENT 18 ANALYSIS: MANUAL INSTALLATION SUCCESS, CRASH PERSISTS!
✅ Manual Xcode installation successful (drag-and-drop works)
✅ Release app bundle created and signed (21MB)
✅ App appears on iPhone home screen with correct icon
❌ CwlCatchException crash STILL occurs in release build
❌ Dependency now in MAIN Runner executable (not debug dylib)

## 🔍 CWLCATCHEXCEPTION ROOT CAUSE IDENTIFIED:
**Issue**: Library not loaded: @rpath/CwlCatchException.framework/CwlCatchException
**Referenced from**: Runner.app/Runner (MAIN EXECUTABLE, not debug dylib)
**Root Cause**: Test dependencies in pubspec.yaml being included in release builds
**Solution**: Remove ALL dev_dependencies and rebuild completely clean

## 🔍 LEARNED PATTERN - iOS INSTALLATION 3-STEP SEQUENCE:
**CRITICAL**: iOS ALWAYS requires these 3 components simultaneously:
1. **Code Signature (0xe800801c)**: All components signed with Apple Developer certificate
2. **Provisioning Profile (0xe8008015)**: embedded.mobileprovision with device UDID
3. **Entitlements (application-identifier)**: entitlements.plist with 4HGRU6TKGQ.com.glikfamily.audioura

**NEVER**: Handle one-by-one (leads to sequential error fixing)
**ALWAYS**: Handle all 3 simultaneously with comprehensive script

## 📱 ASSIGNMENT 19: ELIMINATE CWLCATCHEXCEPTION COMPLETELY

### **STRATEGY**: Remove ALL dev_dependencies from pubspec.yaml and rebuild completely clean
### **SCRIPT READY**: clean_build_no_cwl.sh on D:\ drive (USB)
### **EXPECTED**: Working Audioura app with NO CwlCatchException dependency

### **Step 1: Execute Clean Build (No CwlCatchException) (MAIN ACTION)**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/clean_build_no_cwl.sh" ../
bash ../clean_build_no_cwl.sh
```

### **Step 2: Test Clean App Launch**
1. App should install automatically (clean build)
2. Launch Audioura from iPhone home screen
3. App should NOT crash (NO CwlCatchException dependency)
4. Test basic navigation and interface
5. Verify all core functionality works

### **Step 3: Verify CwlCatchException Elimination**
1. Confirm no CwlCatchException references in app bundle
2. Test app stability and performance
3. Verify network configuration (192.168.0.136:5002/5004)
4. Test all Audioura features (tours, maps, voice, audio)

### **Step 4: Create Comprehensive Results**
```
echo "Clean Build (No CwlCatchException) Results:" > ~/Desktop/clean_build_results.txt
echo "Date: $(date)" >> ~/Desktop/clean_build_results.txt
echo "Approach: Removed all dev_dependencies" >> ~/Desktop/clean_build_results.txt
echo "Installation: [SUCCESS/MANUAL_REQUIRED]" >> ~/Desktop/clean_build_results.txt
echo "App Launch: [WORKS/CRASHES - describe behavior]" >> ~/Desktop/clean_build_results.txt
echo "CwlCatchException: [ELIMINATED/STILL_PRESENT]" >> ~/Desktop/clean_build_results.txt
echo "Functionality: [FULL/PARTIAL/NONE - test all features]" >> ~/Desktop/clean_build_results.txt
cp ~/Desktop/clean_build_results.txt "/Volumes/USB DISK/clean_build_results.txt"
```

## 🎯 WHAT clean_build_no_cwl.sh DOES:
1. **Backs up original pubspec.yaml** (preserves current configuration)
2. **Creates clean pubspec.yaml** (removes ALL dev_dependencies and test frameworks)
3. **Complete project cleanup** (removes all build artifacts and caches)
4. **Fresh dependency resolution** (flutter pub get with clean dependencies)
5. **Clean release build** (flutter build ios --release with no test frameworks)
6. **Verifies CwlCatchException elimination** (checks all binaries for references)
7. **Signs and installs clean app** (complete installation of dependency-free app)

## 🔧 TECHNICAL DETAILS:
- **Certificate**: Apple Development: Mikhail Glik (594584F3D3BC571D94A822A2158871CA13898701)
- **Bundle ID**: com.glikfamily.audioura
- **Team ID**: 4HGRU6TKGQ
- **Device UDID**: 00008140-000558A902BA801C (for provisioning profile)
- **Build Type**: Release (optimized, no debug frameworks)
- **Network**: Already configured (192.168.0.136:5002/5004)

## 📱 SUCCESS CRITERIA:
- Clean build completes without any dev_dependencies
- CwlCatchException dependency completely eliminated from all binaries
- App installs successfully (manual or automatic)
- App launches without any dyld crashes
- Audioura interface appears and navigation works perfectly
- All functionality works (voice, audio, location, tours, maps)
- Service connectivity to Windows laptop established (192.168.0.136)
- Complete iOS development success achieved with stable app

## 🚑 CWLCATCHEXCEPTION DEPENDENCY KNOWLEDGE:
- **Source**: Test frameworks in dev_dependencies section of pubspec.yaml
- **Impact**: Compiled into main Runner executable in both debug AND release builds
- **Flutter Issue**: Test dependencies incorrectly included in production builds
- **Solution**: Remove ALL dev_dependencies and rebuild completely clean
- **Key Insight**: CwlCatchException is a Swift testing framework, not needed for production

## 🌐 NETWORK ARCHITECTURE (CORRECTED UNDERSTANDING):
- **iPhone (Audioura)** → **Windows Laptop (Docker services)** (direct connection)
- **Mac Mini**: Build environment only, NOT part of runtime network path
- **Configuration**: Already set to Windows laptop IP (192.168.0.136:5002/5004)
- **Services**: Docker containers on Windows laptop (ports 5002, 5004, 5005, 5006, 5007, 5012)

## 📝 POST-ASSIGNMENT-19 NEXT STEPS:
1. Verify CwlCatchException dependency completely eliminated
2. Test complete Audioura functionality without crashes
3. Confirm service connectivity to Windows laptop Docker services
4. Document complete iOS development success
5. Prepare for production deployment and App Store submission
6. Create final iOS development documentation and runbook
7. Celebrate successful iOS app deployment!

---
**CRITICAL**: Assignment 17 should resolve the final crash barrier
**READY**: CwlCatchException fix script prepared and ready
**NEXT**: Execute Assignment 17 for complete working iOS app
🍎 iOS AMAZON-Q - CWLCATCHEXCEPTION FRAMEWORK CRASH FIX

## 🎯 BREAKTHROUGH ANALYSIS FROM ASSIGNMENT 16!
✅ **Installation Success**: All 3-step sequence worked perfectly
✅ **Correct Icon**: Audioura icon displays properly on iPhone
✅ **Network Ready**: Already configured to Windows laptop (192.168.0.136)
❌ **Launch Crash**: CwlCatchException.framework missing from debug build

## 🔍 CRASH ANALYSIS FROM LOG FILES:
**Error**: Library not loaded: @rpath/CwlCatchException.framework/CwlCatchException
**Referenced from**: Runner.debug.dylib
**Reason**: Debug builds include testing frameworks not bundled in app
**Solution**: Release builds exclude debug-only dependencies

---

## For strategic Mac Mini Amazon-Q establishement
### Phase 1: SSH Remote Execution (This Week)
1. Mac Mini Setup (one-time)<br>
sudo systemsetup -setremotelogin on<br>
ssh-keygen -t rsa -b 4096 -C "windows-amazonq"<br>
2. Copy public key to Windows for secure access
3. Copy public key to Windows for secure access
### Phase 2: Local Amazon Q Deployment (Next Week)
1. Install AWS CLI and Docker on Mac Mini<br>
brew install awscli docker
2. Deploy Amazon Q Developer container<br>
docker run -d --name on-mini-amazonq -v ~/Development:/workspace -p 8080:8080  amazon/q-developer:latest
### IMMEDIATE ACTION PLAN: For Assignment 17 (Today)
1. Execute manually as planned (fix_cwl_framework_crash.sh)
2. Document process for automation blueprint
3. Test SSH access from Windows to Mac Mini
4. Validate remote execution capability
---
# Time: 04/23/2026 23:30
🍎 iOS AMAZON-Q - FLUTTER NATIVE ASSETS BUG BYPASS (CRITICAL FIX)

## 📋 CRITICAL DISCOVERY FROM ASSIGNMENT 7:
❌ `--no-native-assets` flag doesn't exist in Flutter 3.41.6
❌ Flutter native assets bug still occurs: xcode_backend.dart:345:68 null check error
✅ Icon fix worked perfectly (correct Audioura icons generated)
✅ App signing and installation successful

## 📱 ASSIGNMENT 8: FLUTTER NATIVE ASSETS BUG BYPASS

### **CRITICAL DISCOVERY**: `--no-native-assets` flag doesn't exist in this Flutter version!
### **ROOT CAUSE**: Flutter 3.41.6 xcode_backend.dart:345:68 null check error during post-build
### **SOLUTION**: Alternative bypass methods

### **Step 1: Execute Native Assets Bypass**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/flutter_native_assets_bypass.sh" ../
bash ../flutter_native_assets_bypass.sh
```

### **Step 2: Test New App Installation**
(Script will auto-open Xcode and Finder)
1. Drag new Runner.app to Xcode Devices
2. Test if app launches without crashing
3. Check if correct Audioura icon appears

### **Step 3: Create Results**
```
echo "Native Assets Bypass Results:" > ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "Date: $(date)" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "FLUTTER BUILD STATUS:" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "Audioura immidiately crashed upon double-click on the application icon" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "APP BUNDLE STATUS:" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
ls -la build/ios/Debug-iphoneos/Runner.app >> ~/Desktop/bypass_results_04_24_2026_10_43.txt 2>/dev/null || echo "No app bundle" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "INSTALLATION & LAUNCH:" >> ~/Desktop/bypass_results_04_24_2026_10_43.txt
echo "[DESCRIBE: Does app install? Launch? Crash? Icon correct?]" >> ~/Desktop/bypass_results.txt
cp ~/Desktop/bypass_results.txt "/Volumes/USB DISK/bypass_results.txt"
```

## 🎯 WHAT THIS SCRIPT DOES:
1. **Disables native assets** via configuration file
2. **Sets environment variable** FLUTTER_DISABLE_NATIVE_ASSETS=true
3. **Tries Flutter build** with overrides
4. **Falls back to direct Xcode build** if Flutter fails
5. **Auto-signs** the resulting app bundle
6. **Opens installation windows** automatically

## 📱 SUCCESS CRITERIA:
- Flutter build completes without native assets error
- App bundle created and signed
- App installs and launches without white screen crash
- Correct Audioura icon displays

---
# Time: 04/23/2026 23:05
🍎 iOS AMAZON-Q - APP INSTALLED BUT CRASHES + WRONG ICON

## 🎉 MAJOR BREAKTHROUGH: APP SUCCESSFULLY INSTALLED!
✅ Installation barriers completely overcome
✅ Audioura appears on iPhone home screen
❌ Wrong app icon (not matching Android)
❌ App crashes instantly (white screen flash → home screen)

## 📱 ASSIGNMENT 7: FIX ICON + ANALYZE CRASH

### **Step 1: Fix iOS App Icon**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/fix_ios_app_icon.sh" ../
bash ../fix_ios_app_icon.sh
```

### **Step 2: Analyze App Crash**
```
cp "/Volumes/USB DISK/ios_crash_analysis.sh" ../
bash ../ios_crash_analysis.sh
```

### **Step 3: Rebuild with Icon Fix**
```
flutter build ios --debug --no-codesign --no-native-assets
```

### **Step 4: Re-sign and Install**
```
bash ../complete_app_signing.sh
```
(Then drag-and-drop install via Xcode)

### **Step 5: Create Results**
```
echo "Icon Fix + Crash Analysis Results:" > ~/Desktop/icon_crash_results.txt
echo "Date: $(date)" >> ~/Desktop/icon_crash_results.txt
echo "" >> ~/Desktop/icon_crash_results.txt
echo "ICON FIX STATUS:" >> ~/Desktop/icon_crash_results.txt
ls -la ios/Runner/Assets.xcassets/AppIcon.appiconset/ >> ~/Desktop/icon_crash_results.txt
echo "" >> ~/Desktop/icon_crash_results.txt
echo "CRASH ANALYSIS:" >> ~/Desktop/icon_crash_results.txt
cat crash_summary.txt >> ~/Desktop/icon_crash_results.txt 2>/dev/null
echo "" >> ~/Desktop/icon_crash_results.txt
echo "NEW APP BEHAVIOR:" >> ~/Desktop/icon_crash_results.txt
echo "[DESCRIBE: Does new app have correct icon? Does it still crash?]" >> ~/Desktop/icon_crash_results.txt
cp ~/Desktop/icon_crash_results.txt "/Volumes/USB DISK/icon_crash_results.txt"
```

## 📱 ASSIGNMENT 8: FLUTTER NATIVE ASSETS BUG BYPASS

### **CRITICAL DISCOVERY**: `--no-native-assets` flag doesn't exist in this Flutter version!
### **ROOT CAUSE**: Flutter 3.41.6 xcode_backend.dart:345:68 null check error during post-build
### **SOLUTION**: Alternative bypass methods

### **Step 1: Execute Native Assets Bypass**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/flutter_native_assets_bypass.sh" ../
bash ../flutter_native_assets_bypass.sh
```

### **Step 2: Test New App Installation**
(Script will auto-open Xcode and Finder)
1. Drag new Runner.app to Xcode Devices
2. Test if app launches without crashing
3. Check if correct Audioura icon appears

### **Step 3: Create Results**
```
echo "Native Assets Bypass Results:" > ~/Desktop/bypass_results.txt
echo "Date: $(date)" >> ~/Desktop/bypass_results.txt
echo "" >> ~/Desktop/bypass_results.txt
echo "FLUTTER BUILD STATUS:" >> ~/Desktop/bypass_results.txt
echo "[SUCCESS/FAILED - describe what happened]" >> ~/Desktop/bypass_results.txt
echo "" >> ~/Desktop/bypass_results.txt
echo "APP BUNDLE STATUS:" >> ~/Desktop/bypass_results.txt
ls -la build/ios/Debug-iphoneos/Runner.app >> ~/Desktop/bypass_results.txt 2>/dev/null || echo "No app bundle" >> ~/Desktop/bypass_results.txt
echo "" >> ~/Desktop/bypass_results.txt
echo "INSTALLATION & LAUNCH:" >> ~/Desktop/bypass_results.txt
echo "[DESCRIBE: Does app install? Launch? Crash? Icon correct?]" >> ~/Desktop/bypass_results.txt
cp ~/Desktop/bypass_results.txt "/Volumes/USB DISK/bypass_results.txt"
```

## 🎯 WHAT THIS SCRIPT DOES:
1. **Disables native assets** via configuration file
2. **Sets environment variable** FLUTTER_DISABLE_NATIVE_ASSETS=true
3. **Tries Flutter build** with overrides
4. **Falls back to direct Xcode build** if Flutter fails
5. **Auto-signs** the resulting app bundle
6. **Opens installation windows** automatically

## 📱 SUCCESS CRITERIA:
- Flutter build completes without native assets error
- App bundle created and signed
- App installs and launches without white screen crash
- Correct Audioura icon displays

---

### **Step 1: Execute Complete Signing Script**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/complete_app_signing.sh" ../
bash ../complete_app_signing.sh
```

### **What This Script Does (All At Once):**
1. **Finds Apple Developer Certificate** (SHA-1 hash)
2. **Creates entitlements.plist** (application-identifier: 4HGRU6TKGQ.com.glikfamily.audioura)
3. **Signs all frameworks** (prevents framework signature errors)
4. **Signs main app with entitlements** (fixes code signature + entitlements)
5. **Checks provisioning profile** (guides you through creation if missing)
6. **Opens Xcode + Finder** (ready for drag-and-drop)

### **Step 2: Manual Provisioning Profile (If Prompted)**
If script says "No provisioning profile found":
1. Go to https://developer.apple.com
2. Sign in: glikfamily@gmail.com
3. Account → Certificates, Identifiers & Profiles
4. Profiles → + → iOS App Development
5. App ID: com.glikfamily.audioura
6. Certificate: Apple Development: Mikhail Glik
7. Device: iPhone UDID: 00008140-000558A902BA801C
8. Download as Audioura_Development.mobileprovision
9. Copy to: build/ios/Debug-iphoneos/Runner.app/embedded.mobileprovision

### **Step 3: Install via Drag-and-Drop**
1. Xcode: Select "Mikhail Glik's iPhone"
2. Finder: Drag "Runner.app" to "Installed Apps"
3. Wait for installation
4. Test app on iPhone

### **Step 4: Create Results**
```
echo "Complete Signing Results:" > ~/Desktop/complete_results.txt
echo "Date: $(date)" >> ~/Desktop/complete_results.txt
echo "Installation: [SUCCESS/FAILED]" >> ~/Desktop/complete_results.txt
echo "App Launch: [WORKS/CRASHES - describe behavior]" >> ~/Desktop/complete_results.txt
cp ~/Desktop/complete_results.txt "/Volumes/USB DISK/complete_results.txt"
```

## 🎯 KEY INSIGHT:
This script handles ALL THREE issues we encountered before in one execution, preventing the need to go through the sequence multiple times.

## 📱 SUCCESS CRITERIA:
- No code signature errors
- No provisioning profile errors  
- No entitlements errors
- App installs and appears on iPhone home screen

---

## 🔍 ANALYSIS FROM ALL FILES:
✅ App Bundle Created: 118MB Runner.app (much larger than 416 bytes - this is the real app!)
✅ iPhone Connected: Device properly detected and installation attempted
❌ Installation Failed: "No code signature found" (error 0xe800801c)
❌ Root Cause: App built with --no-codesign flag, needs signing before installation

## 📱 ASSIGNMENT 5: SIGN AND INSTALL THE APP

### **Step 1: Navigate to Project**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
```

### **Step 2: Check Current App Bundle**
```
ls -la build/ios/Debug-iphoneos/Runner.app
codesign -dv build/ios/Debug-iphoneos/Runner.app
```
(Should show "not signed" or similar)

### **Step 3: Find Apple Developer Certificate**
```
security find-identity -v -p codesigning
```
(Look for "Apple Development: Mikhail Glik" and copy the SHA-1 hash)

### **Step 4: Sign the App Bundle**
```
codesign --force --sign "[PASTE_SHA1_HASH_HERE]" --timestamp build/ios/Debug-iphoneos/Runner.app
```
(Replace [PASTE_SHA1_HASH_HERE] with actual hash from Step 3)

### **Step 5: Verify Signing**
```
codesign -dv build/ios/Debug-iphoneos/Runner.app
```
(Should now show Team ID 4HGRU6TKGQ)

### **Step 6: Install via Xcode Drag-and-Drop**
1. **Open Xcode Devices**: 
   ```
   open -a Xcode
   ```
   Then: Window → Devices and Simulators (⌘+Shift+2)

2. **Open Finder to App**:
   ```
   open build/ios/Debug-iphoneos/
   ```

3. **Drag and Drop**:
   - Select "Mikhail Glik's iPhone" in Xcode
   - Drag "Runner.app" to "Installed Apps" section
   - Wait for installation

### **Step 7: Test and Report**
1. Check iPhone home screen for "Audioura" app
2. Tap to launch and note behavior
3. Create results:
   ```
   echo "Signed App Installation Results:" > ~/Desktop/signed_results.txt
   echo "Date: $(date)" >> ~/Desktop/signed_results.txt
   echo "Signing Status: $(codesign -dv build/ios/Debug-iphoneos/Runner.app 2>&1 | head -3)" >> ~/Desktop/signed_results.txt
   echo "Installation: [SUCCESS/FAILED]" >> ~/Desktop/signed_results.txt
   echo "App Launch: [WORKS/CRASHES - describe what happens]" >> ~/Desktop/signed_results.txt
   cp ~/Desktop/signed_results.txt "/Volumes/USB DISK/signed_results.txt"
   ```

## 🎯 KEY INSIGHT:
We have a complete 118MB app bundle! The only issue is missing code signature. Once signed with Apple Developer certificate, it should install successfully.

## 📱 SUCCESS CRITERIA:
- App signs successfully with Team ID 4HGRU6TKGQ
- Installation completes without signature errors
- Audioura appears on iPhone home screen
- App launches (may crash due to runtime issues, but installation should work)

---

## 🔍 ANALYSIS FROM ALL THREE TERMINAL OUTPUTS:
✅ App Bundle Exists: build/ios/Debug-iphoneos/Runner.app (416 bytes)
❌ Command Syntax Issues: Typing ```bash literally instead of executing commands
❌ Device ID Parsing: Script got "Mikhail" instead of "00008140-000558A902BA801C"
❌ Xcode Build Fails: Same Flutter native assets bug (Command PhaseScriptExecution failed)
❌ Plugin Warnings: Deprecation warnings (non-fatal but numerous)

## 📱 ASSIGNMENT 4: MANUAL XCODE INSTALLATION (BYPASS ALL AUTOMATION)

### **Step 1: Switch to ZSH Shell**
```
zsh
```
(Type this command directly, not the markdown syntax)

### **Step 2: Navigate to Project**
```
cd ~/Development/AudioTours/development/audio_tour_app
```

### **Step 3: Verify App Bundle Exists**
```
ls -la build/ios/Debug-iphoneos/Runner.app
```
(Should show the app bundle directory)

### **Step 4: Open Xcode Devices Window**
```
open -a Xcode
```
Then in Xcode: Window → Devices and Simulators (⌘+Shift+2)

### **Step 5: Manual Drag-and-Drop Installation**
1. **Open Finder to App Bundle**:
   ```
   open build/ios/Debug-iphoneos/
   ```

2. **In Xcode Devices Window**:
   - Left sidebar: Select "Mikhail Glik's iPhone"
   - Right panel: Find "Installed Apps" section

3. **Drag and Drop**:
   - Drag "Runner.app" from Finder
   - Drop into "Installed Apps" in Xcode
   - Wait for installation progress

### **Step 6: Test App Launch**
1. Check iPhone home screen for "Audioura" app
2. Tap app icon to launch
3. Note if it crashes or works

### **Step 7: Create Simple Results**
```
echo "App Installation Results:" > ~/Desktop/results.txt
echo "Date: $(date)" >> ~/Desktop/results.txt
echo "App Bundle Size: $(du -sh build/ios/Debug-iphoneos/Runner.app)" >> ~/Desktop/results.txt
echo "Installation: [SUCCESS/FAILED - write what happened]" >> ~/Desktop/results.txt
echo "App Launch: [WORKS/CRASHES - write what happened]" >> ~/Desktop/results.txt
```

### **Step 8: Copy Results to USB**
```
cp ~/Desktop/results.txt "/Volumes/USB DISK/manual_install_results.txt"
```

## 🎯 KEY INSIGHT:
We have a working app bundle! The Flutter native assets bug happens AFTER the app is built. We can install the existing app bundle manually and bypass all the automation issues.

## 📱 SUCCESS CRITERIA:
- App installs via drag-and-drop
- Audioura appears on iPhone home screen  
- App launches (may crash, but that's a separate issue to fix)

---

## 🔍 ANALYSIS FROM TERMINAL OUTPUT:
✅ Flutter Build Almost Works: "Project built and packaged successfully"
❌ Same Flutter Bug: Null check operator used on a null value in xcode_backend.dart:345:68
❌ Bash Commands Failed: Wrong shell (bash-3.2$ instead of zsh) + heredoc syntax issues
❌ No App Bundle: Build failed in post-processing, so no Runner.app created

## 📋 ASSIGNMENT 3: XCODE DIRECT BUILD (BYPASS FLUTTER ENTIRELY)

### **Step 1: Switch to Correct Shell**
```bash
zsh
cd ~/Development/AudioTours/development/audio_tour_app
```

### **Step 2: Execute Xcode Direct Build**
```bash
cp /Volumes/USB\ Disk/xcode_direct_build.sh ../
bash ../xcode_direct_build.sh
```

### **Step 3: Create Simple Results File**
```bash
echo "=== XCODE DIRECT BUILD RESULTS ===" > ~/Desktop/results.txt
echo "Date: $(date)" >> ~/Desktop/results.txt
echo "" >> ~/Desktop/results.txt
echo "XCODE BUILD OUTPUT:" >> ~/Desktop/results.txt
echo "[Copy terminal output here after script runs]" >> ~/Desktop/results.txt
echo "" >> ~/Desktop/results.txt
echo "APP BUNDLE STATUS:" >> ~/Desktop/results.txt
ls -la ios/build/Debug-iphoneos/Runner.app 2>/dev/null >> ~/Desktop/results.txt || echo "No app bundle found" >> ~/Desktop/results.txt
echo "" >> ~/Desktop/results.txt
echo "DEVICE CONNECTION:" >> ~/Desktop/results.txt
xcrun devicectl list devices | grep iPhone >> ~/Desktop/results.txt || echo "No iPhone detected" >> ~/Desktop/results.txt
```

### **Step 4: Copy Results to USB**
```bash
cp ~/Desktop/results.txt "/Volumes/USB DISK/xcode_results.txt"
```

## 🎯 KEY INSIGHT:
Flutter 3.41.6 has the native assets bug we can't avoid. Xcode direct build bypasses Flutter entirely and should work.

## 📱 SUCCESS CRITERIA:
- Xcode builds app successfully
- App installs automatically on iPhone 16  
- Audioura appears on iPhone home screen
- App launches without crashing

---

---

## 🔍 **CRITICAL INFORMATION TO CAPTURE**

### **Always Include in Results:**
1. **Complete terminal output** - copy/paste everything
2. **Error messages** - exact text of any errors
3. **File paths** - where files were created or not found
4. **Device status** - iPhone connection and recognition
5. **App behavior** - does it install? launch? crash?

### **Key Questions to Answer:**
- Did Flutter build succeed or fail?
- Was an app bundle (Runner.app) created?
- Did signing work with Apple Developer certificate?
- Is iPhone 16 detected and connected?
- Did app install on iPhone home screen?
- Does app launch without crashing?

---

## 📱 **SUCCESS CRITERIA**

### **Assignment 17 Success:**
- ✅ Release build completes without CwlCatchException dependency
- ✅ App installs and replaces crashing debug version
- ✅ App launches without CwlCatchException crash
- ✅ Audioura interface appears and navigation works
- ✅ All functionality works (voice, audio, location, tours)

---

## 🚨 **IF THINGS GO WRONG**

### **Common Issues & Quick Fixes:**

#### **Flutter Build Fails:**
```bash
# Try cleaning everything
flutter clean
cd ios
rm -rf Pods Podfile.lock
pod install
cd ..
flutter pub get
```

#### **Certificate Issues:**
```bash
# Check available certificates
security find-identity -v -p codesigning
# Look for "Apple Development: Mikhail Glik"
```

#### **iPhone Not Detected:**
```bash
# Check device connection
xcrun devicectl list devices
# iPhone should appear in list
```

#### **App Won't Install:**
- Try manual Xcode installation: Window → Devices and Simulators
- Drag Runner.app to iPhone in device list
- Check for provisioning profile errors

---

## 📋 **EXECUTION CHECKLIST**

### **Before Starting:**
- [ ] iPhone 16 connected via USB
- [ ] iPhone unlocked and computer trusted
- [ ] Developer Mode enabled on iPhone
- [ ] USB drive mounted and accessible

### **During Execution:**
- [ ] Copy complete terminal outputs to results file
- [ ] Note any manual steps taken
- [ ] Document exact error messages
- [ ] Test app installation and launch

### **After Completion:**
- [ ] Results file copied to USB drive
- [ ] USB drive safely ejected
- [ ] Ready to return to Windows for iOS Amazon-Q analysis

---

**REMEMBER**: iOS Amazon-Q will analyze your results and provide the next steps. Capture everything - even seemingly minor details can be crucial for troubleshooting!

**Last Updated**: 2025-01-31
**Priority**: HIGH - iOS app launch critical path

## Assignment 20 (v2) — Execution Walkthrough on Mac Mini

**Goal:** Eliminate `CwlCatchException` from the Audioura iOS build without removing `speech_to_text` or `flutter_sound`.
**Script to run:** `podfile_cwl_fix_v2.sh` (Claude-reviewed, current version).
**Date format reminder:** all timestamps in this assignment should use the result of `python3 -c "import datetime; print(datetime.datetime.now())"`.

This walkthrough is **self-contained**. Sir Michael should not need to refer to chat or any other document during the run. Read this once before switching the KVM, then execute step-by-step.

### Prerequisites (verify on Windows side BEFORE switching the KVM)

- [ ] `D:\Audioura\scripts\podfile_cwl_fix_v2.sh` exists and is the current version.
- [ ] `D:\Audioura\results\` exists (this is where Mac Mini outputs will land).
- [ ] The USB stick (D:\ drive) is plugged in and visible in Windows Explorer at `D:\`.
- [ ] The iPhone 16 (UDID `00008140-000558A902BA801C`) is plugged into the Mac Mini.

### Step 1 — Switch the KVM to the Mac Mini

Use the standard KVM switch. Wait for the Mac Mini desktop to appear and the keyboard / mouse / monitor to respond on the Mac Mini side.

### Step 2 — Confirm the USB stick is mounted

Open Terminal (Applications → Utilities → Terminal, or Spotlight: Cmd+Space, type "Terminal", press ENTER).

Type:

```
ls /Volumes/
```

Press ENTER. You should see `USB DISK` listed among the volumes. If you do not, unplug and re-plug the USB stick — the KVM may have desynced its USB pass-through.

### Step 3 — Navigate to the scripts folder

In the same Terminal:

```
cd "/Volumes/USB DISK/Audioura/scripts"
ls
```

You should see at least these files:
- `podfile_cwl_fix_v2.sh`
- `podfile_cwl_fix_review_notes.md`
- `remove_cwl_source_plugin.sh` (the destructive fallback — do NOT run this unless v2 fails)

### Step 4 — Make the script executable (one-time setup, harmless to repeat)

```
chmod +x podfile_cwl_fix_v2.sh
```

### Step 5 — Run the script

```
./podfile_cwl_fix_v2.sh
```

The script will start printing colored output. Watch the Terminal carefully — the next two sub-steps depend on what you see.

### Step 5A — Path A (no pause): script runs straight through

If you do NOT see the message "⚠️ Existing post_install block found", the script is auto-appending the required Podfile changes. There is nothing for you to do during the run. **Skip to Step 7.**

### Step 5B — Path B (pause): script needs you to edit the Podfile manually

If you see this output:

```
⚠️ Existing post_install block found - manual edit required
Please manually add CwlCatchException exclusion to existing post_install block

ADD THESE LINES inside the existing post_install block:
    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)
      target.build_configurations.each do |config|
        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'
        config.build_settings['SKIP_INSTALL'] = 'YES'
      end
    end

Press ENTER when manual edit is complete...
```

…the script is **paused** and waiting for you. Go to Step 6.

### Step 6 — Manually edit the Podfile (only if you reached Path B)

Follow these sub-steps in order. Do **not** close or press anything in the script's Terminal window until Step 6.8.

#### Step 6.1 — Leave the script's Terminal window open and paused

Do not close it. Do not press ENTER yet.

#### Step 6.2 — Open a NEW Terminal tab

In Terminal: press `Cmd+T` (new tab in the same window) **or** `Cmd+N` (new window). A fresh prompt appears.

#### Step 6.3 — Open the Podfile in `nano`

In the new tab, type exactly:

```
nano ~/Development/AudioTours/development/audio_tour_app/ios/Podfile
```

Press ENTER. The `nano` text editor opens with the Podfile contents.

#### Step 6.4 — Find the existing `post_install` block

Scroll down using the arrow keys until you find a line that reads:

```
post_install do |installer|
```

A few lines below it you should see something like:

```
  installer.pods_project.targets.each do |target|
    flutter_additional_ios_build_settings(target)
  end
```

(The exact lines may vary slightly, but the structure of `post_install do |installer|` … `installer.pods_project.targets.each do |target|` … `end` … `end` is constant.)

#### Step 6.5 — Insert the CwlCatchException exclusion lines

Position the cursor at the **end of the line containing `flutter_additional_ios_build_settings(target)`** (or, if that line is missing, at the end of the line just before the **inner** `end` that closes the `do |target|` block).

Press ENTER once to start a new line.

Then type (or paste using `Cmd+V` if you copied from this document) exactly the following block. Indentation matters — each indent level is two spaces.

```
    target.build_configurations.each do |config|
      config.build_settings['BUILD_LIBRARY_FOR_DISTRIBUTION'] = 'NO'
    end
    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)
      target.build_configurations.each do |config|
        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'
        config.build_settings['SKIP_INSTALL'] = 'YES'
      end
    end
```

After insertion the relevant section should read approximately:

```
post_install do |installer|
  installer.pods_project.targets.each do |target|
    flutter_additional_ios_build_settings(target)
    target.build_configurations.each do |config|
      config.build_settings['BUILD_LIBRARY_FOR_DISTRIBUTION'] = 'NO'
    end
    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)
      target.build_configurations.each do |config|
        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'
        config.build_settings['SKIP_INSTALL'] = 'YES'
      end
    end
  end
end
```

#### Step 6.6 — Save and exit `nano`

1. Press `Ctrl+O` (the letter O, not zero). At the bottom you will see `File Name to Write: ...Podfile`.
2. Press ENTER to confirm the filename. The bottom shows `[ Wrote N lines ]`.
3. Press `Ctrl+X` to exit `nano`. You return to the shell prompt.

#### Step 6.7 — Verify the edit (optional sanity check)

Still in the second tab, type:

```
grep -A2 "CwlCatchException" ~/Development/AudioTours/development/audio_tour_app/ios/Podfile
```

You should see the lines you just inserted echoed back. If you see nothing, repeat Step 6.3–6.6.

#### Step 6.8 — Return to the script's Terminal and resume

Click on (or `Cmd+~` to switch to) the FIRST Terminal tab/window — the one where the script is paused at "Press ENTER when manual edit is complete...".

Press ENTER. The script will continue.

### Step 7 — Watch the script run to completion

The script will perform: `pod install`, `flutter build ios --release --no-codesign`, `otool` verification, `codesign`, and `devicectl install`. Key success markers to look for:

- `✅ pod install` (no `❌` errors)
- `✅ No CwlCatchException references found in Runner binary`
- `✅ App signed successfully`
- `✅ App installation attempted`
- `🎉 PODFILE FIX COMPLETE - TEST APP LAUNCH ON IPHONE`

Total run time is typically 5–15 minutes depending on Mac Mini speed and CocoaPods cache state.

### Step 8 — Test the app on the iPhone

Pick up the iPhone 16. Find the **Audioura** app icon on the home screen. Tap to open.

Expected outcome:
- App launches to its home screen.
- No crash, no immediate exit.
- Voice and audio features still work (try whatever you normally do that uses `speech_to_text` or `flutter_sound`).

If the app crashes on launch: do NOT panic, and do NOT run `remove_cwl_source_plugin.sh`. Continue to Step 9 — Claude will diagnose from the artifacts.

### Step 9 — Copy results back to USB

In Terminal (either tab), run these commands. They copy the session log and three project files into `D:\Audioura\results\` (which appears as `/Volumes/USB DISK/Audioura/results/` on the Mac Mini side).

```
cp ~/Desktop/podfile_cwl_fix_session.txt "/Volumes/USB DISK/Audioura/results/podfile_cwl_fix_session.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile "/Volumes/USB DISK/Audioura/results/Podfile_after_v2.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile.lock "/Volumes/USB DISK/Audioura/results/Podfile.lock_after_v2.txt"
cp ~/Development/AudioTours/development/audio_tour_app/pubspec.yaml "/Volumes/USB DISK/Audioura/results/pubspec_after_v2.txt"
```

If any `cp` reports "No such file or directory", note which file it was and continue. The session log is the most important; everything else is supporting evidence.

### Step 10 — Eject the USB stick (good practice) and switch the KVM back to Windows

In Terminal:

```
diskutil eject "/Volumes/USB DISK"
```

Then physically unplug-and-replug the USB stick or just switch the KVM to the Windows laptop. The files in `D:\Audioura\results\` are now visible to Claude through Cowork.

### Step 11 — Tell Claude the run is done

Switch back to Cowork on the Windows laptop. Tell Claude that the results are in `D:\Audioura\results\` and what happened on the iPhone (app launched / app crashed / build error). Claude will read the artifacts and either declare Assignment 20 complete or diagnose the next step.

### What to do if the script reports `❌ Podfile fix failed`

The script gates on the `otool` binary check. If `otool` shows `cwl` references in the Runner binary, the Podfile fix did not eliminate the framework. **Do not** run `remove_cwl_source_plugin.sh` yet. Instead:

1. Complete Step 9 (copy results to USB).
2. Switch KVM back to Windows.
3. Tell Claude. Claude will read `Podfile_after_v2.txt` and `Podfile.lock_after_v2.txt` to diagnose why the exclusion did not take effect — usually a typo in the inserted block or an unexpected Podfile structure that needs a different insertion point.
---
# Time: $(python3 -c "import datetime; print(datetime.datetime.now())") - PRE-ASSIGNMENT 20: PODFILE CWLCATCHEXCEPTION FIX
🍎 iOS AMAZON-Q - PRE-ASSIGNMENT 20: ATTEMPT PODFILE FIX BEFORE PLUGIN REMOVAL

## 🎯 STRATEGY CHANGE: TRY PODFILE FIX FIRST (PRESERVE CORE FUNCTIONALITY)
Before removing speech_to_text and flutter_sound (core Audioura features), attempt targeted Podfile exclusion to eliminate CwlCatchException WITHOUT losing functionality.

## 🔍 ROOT CAUSE UNDERSTANDING:
CwlCatchException is a Swift testing framework pulled in as TRANSITIVE CocoaPods dependency. It should be excluded from production builds entirely.

## 📱 PRE-ASSIGNMENT 20: PODFILE CWLCATCHEXCEPTION EXCLUSION

### **STRATEGY**: Exclude CwlCatchException in Podfile post_install block
### **SCRIPT READY**: podfile_cwl_fix.sh on D:\ drive (USB)
### **EXPECTED**: Working Audioura app WITH full functionality (speech + audio preserved)

### **Step 1: Execute Podfile Fix (MAIN ACTION)**
```
zsh
cd ~/Development/AudioTours/development/audio_tour_app
cp "/Volumes/USB DISK/podfile_cwl_fix.sh" ../
bash ../podfile_cwl_fix.sh
```

### **Step 2: Test Full-Functionality App Launch**
1. App should install automatically (CwlCatchException excluded)
2. Launch Audioura from iPhone home screen
3. App should NOT crash (CwlCatchException eliminated via Podfile)
4. Test ALL features including voice commands and audio recording
5. Verify speech_to_text and flutter_sound work properly

### **Step 3: Verify Complete Success**
1. Confirm no CwlCatchException in app bundle or Podfile.lock
2. Test app stability with FULL functionality
3. Verify all Audioura features work (voice, audio, maps, tours)
4. Confirm speech_to_text and flutter_sound preserved in pubspec.yaml

### **Step 4: Create Results (Success or Failure)**
```
echo "Podfile CwlCatchException Fix Results:" > ~/Desktop/podfile_fix_results.txt
echo "Date: $(python3 -c "import datetime; print(datetime.datetime.now())")" >> ~/Desktop/podfile_fix_results.txt
echo "Approach: Podfile post_install CwlCatchException exclusion" >> ~/Desktop/podfile_fix_results.txt
echo "Installation: [SUCCESS/MANUAL_REQUIRED]" >> ~/Desktop/podfile_fix_results.txt
echo "App Launch: [WORKS/CRASHES - describe behavior]" >> ~/Desktop/podfile_fix_results.txt
echo "CwlCatchException: [ELIMINATED/STILL_PRESENT]" >> ~/Desktop/podfile_fix_results.txt
echo "speech_to_text preserved: [YES/NO]" >> ~/Desktop/podfile_fix_results.txt
echo "flutter_sound preserved: [YES/NO]" >> ~/Desktop/podfile_fix_results.txt
echo "Full Functionality: [WORKING/BROKEN - test all features]" >> ~/Desktop/podfile_fix_results.txt
cp ~/Desktop/podfile_fix_results.txt "/Volumes/USB DISK/podfile_fix_results.txt"
```

## 🎯 WHAT podfile_cwl_fix.sh DOES:
1. **Backs up current Podfile** (preserves existing configuration)
2. **Adds CwlCatchException exclusion** to post_install block
3. **Rebuilds CocoaPods** with exclusion rules applied
4. **Verifies elimination** in both Podfile.lock and binary
5. **Builds release app** with CwlCatchException excluded
6. **Signs and installs** complete app with full functionality
7. **Preserves all plugins** (speech_to_text, flutter_sound remain)

## 🔧 PODFILE EXCLUSION BLOCK ADDED:
```ruby
post_install do |installer|
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |config|
      config.build_settings['BUILD_LIBRARY_FOR_DISTRIBUTION'] = 'NO'
    end
    if ['CwlCatchException', 'CwlCatchExceptionSupport'].include?(target.name)
      target.build_configurations.each do |config|
        config.build_settings['EXCLUDED_ARCHS[sdk=iphoneos*]'] = 'arm64'
        config.build_settings['SKIP_INSTALL'] = 'YES'
      end
    end
  end
end
```

## 📱 SUCCESS CRITERIA (PODFILE FIX):
- CocoaPods rebuild excludes CwlCatchException completely
- No CwlCatchException references in Podfile.lock or Runner binary
- App installs and launches without dyld crashes
- speech_to_text functionality works (voice commands)
- flutter_sound functionality works (audio recording)
- Full Audioura feature set preserved and working
- Network connectivity to Windows laptop established

## 🔄 DECISION TREE:
**IF Podfile fix works** → Assignment 20 complete, full functionality preserved
**IF Podfile fix fails** → Execute remove_cwl_source_plugin.sh (with UDID fix applied)

## ⚠️ FIXES APPLIED TO remove_cwl_source_plugin.sh:
1. **Hardcoded device UDID**: "00008140-000558A902BA801C" (reliable vs dynamic parsing)
2. **Transitive dependency note**: podspec grep is informational only, Podfile.lock is definitive

---
**CRITICAL**: Try Podfile exclusion FIRST to preserve core functionality
**READY**: Both podfile_cwl_fix.sh and corrected remove_cwl_source_plugin.sh prepared
**NEXT**: Execute PRE-Assignment 20 for optimal outcome (full functionality preserved)