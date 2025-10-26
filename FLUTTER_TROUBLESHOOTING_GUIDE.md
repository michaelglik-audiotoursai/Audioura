# Flutter Troubleshooting Guide for AudioTours
**Created: 2025-08-29**  
**Last Updated: 2025-08-29**

## Quick Reference - Common Issues & Solutions

### Issue 1: "Pub failed to delete entry because it was in use by another process"

**Problem:** Flutter can't delete temporary directories during `flutter pub get`

**Root Cause:** Windows file locking (antivirus, background processes, or Flutter itself)

**Solutions (in order of preference):**

1. **Pre-download missing packages:**
   ```cmd
   dart pub cache add speech_to_text
   dart pub cache add speech_to_text_windows
   dart pub cache add speech_to_text_macos
   flutter pub get --offline
   ```

2. **Use dart pub instead of flutter pub:**
   ```cmd
   dart pub get
   ```

3. **Repair cache first:**
   ```cmd
   flutter pub cache repair
   flutter pub get --offline
   ```

4. **Run as Administrator:**
   - Right-click Command Prompt → "Run as administrator"
   - Navigate to project and run `flutter pub get`

### Issue 2: Windows Path Length Limit (260 characters)

**Problem:** Build fails with path too long errors

**Error Example:**
```
Path: x64\Debug\flutter_inappwebview_windows_DEPENDENCIES_DOWNLOAD\flutter_.E8801EB8.tlog\flutter_inappwebview_windows_DEPENDENCIES_DOWNLOAD.lastbuildstate exceeds the OS max path limit
```

**Solutions:**

1. **Move project to shorter path (RECOMMENDED):**
   ```cmd
   mkdir C:\temp\flutter_run
   xcopy "C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app" "C:\temp\flutter_run" /E /I /H
   cd C:\temp\flutter_run
   flutter clean
   flutter run
   ```

2. **Enable Windows long paths (requires restart):**
   ```cmd
   # Run as Administrator
   reg add "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled /t REG_DWORD /d 1
   ```

3. **Use web build instead:**
   ```cmd
   flutter run -d chrome
   ```

### Issue 3: NuGet Missing for Windows Builds

**Problem:** `flutter_inappwebview_windows` plugin requires NuGet

**Error:** `Nuget is not installed! The flutter_inappwebview_windows plugin requires it`

**Solutions:**

1. **Install NuGet:**
   ```cmd
   winget install Microsoft.NuGet
   ```

2. **Use Chrome instead:**
   ```cmd
   flutter run -d chrome
   ```

3. **Manual NuGet install:**
   - Download from https://www.nuget.org/downloads
   - Add to PATH or place in `C:\Windows\System32`

### Issue 4: Platform-Specific Dependencies Missing

**Problem:** Package has platform dependencies that aren't auto-downloaded

**Example:** `speech_to_text` needs `speech_to_text_windows`

**Solution - Download dependency tree:**
```cmd
dart pub cache add speech_to_text
dart pub cache add speech_to_text_windows
dart pub cache add speech_to_text_platform_interface
dart pub cache add speech_to_text_macos
# Note: speech_to_text_android doesn't exist - it's built into the main package
```

## Step-by-Step Troubleshooting Process

### When `flutter pub get` fails:

1. **Try offline mode first:**
   ```cmd
   flutter pub get --offline
   ```

2. **If offline fails, pre-download missing packages:**
   ```cmd
   # Look at the error message for missing package names
   dart pub cache add [PACKAGE_NAME]
   flutter pub get --offline
   ```

3. **If still failing, use dart pub:**
   ```cmd
   dart pub get
   ```

4. **Last resort - run as admin:**
   ```cmd
   # Right-click cmd → Run as administrator
   flutter pub get
   ```

### When Windows build fails with path length:

1. **Copy to short path:**
   ```cmd
   mkdir C:\temp\flutter_run
   xcopy "[LONG_PATH]" "C:\temp\flutter_run" /E /I /H
   cd C:\temp\flutter_run
   flutter clean
   flutter run
   ```

2. **Or use web build:**
   ```cmd
   flutter run -d chrome
   ```

### When web build hangs:

1. **Check verbose output:**
   ```cmd
   flutter run -d chrome -v
   ```

2. **Try different port:**
   ```cmd
   flutter run -d chrome --web-port=8080
   ```

3. **Check browser console (F12) for errors**

4. **Ensure backend services are running:**
   ```cmd
   docker-compose -f docker-compose-complete.yml up -d
   ```

## Prevention Tips

1. **Keep projects in short paths:** Use `C:\Projects\` instead of deep nested folders
2. **Regular cache maintenance:** Run `flutter pub cache repair` monthly
3. **Use offline mode when possible:** Faster and avoids temp directory issues
4. **Enable Windows long paths:** One-time setup prevents future issues

## Emergency Commands

**Complete reset:**
```cmd
flutter clean
flutter pub cache clean
flutter pub cache repair
flutter pub get
```

**Quick copy to temp location:**
```cmd
robocopy "[SOURCE]" "C:\temp\flutter_run" /E /COPYALL
cd C:\temp\flutter_run
flutter clean
flutter run
```

**Force offline mode:**
```cmd
dart pub cache add [MISSING_PACKAGES]
flutter pub get --offline
```

## Notes for Future Reference

- **Date of last major issue:** 2025-08-29
- **Main problems solved:** Temp directory deletion, path length limits
- **Working solutions:** Pre-download packages + offline mode, copy to short path
- **Project location:** `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app`
- **Backup location:** `C:\temp\flutter_run` (when needed)

---
*This guide documents solutions found during troubleshooting session on 2025-08-29*