## Assignment 20 (v3) — Execution Walkthrough on Mac Mini

**Goal:** Eliminate `CwlCatchException` from the Audioura iOS build without removing `speech_to_text` or `flutter_sound`.
**Script to run:** `podfile_cwl_fix_v3.sh` (Claude-reviewed, current version).
**Date format reminder:** all timestamps in this assignment should use the result of `python3 -c "import datetime; print(datetime.datetime.now())"`.

This walkthrough is **self-contained**. Sir Michael should not need to refer to chat or any other document during the run. Read this once before switching the KVM, then execute step-by-step.

### Prerequisites (verify on Windows side BEFORE switching the KVM)

- [ ] `D:\Audioura\scripts\podfile_cwl_fix_v3.sh` exists and is the current version.
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
- `podfile_cwl_fix_v3.sh`
- `podfile_cwl_fix_review_notes.md`
- `remove_cwl_source_plugin.sh` (the destructive fallback — do NOT run this unless v3 fails)

### Step 4 — Make the script executable (one-time setup, harmless to repeat)

```
chmod +x podfile_cwl_fix_v3.sh
```

### Step 5 — Run the script

```
./podfile_cwl_fix_v3.sh
```

The script will start printing colored output. Watch the Terminal carefully — there are now THREE possible paths.

### Step 5A — Path A1 (already-edited Podfile, MOST LIKELY for Sir Michael): script skips the edit step

If you see this message:

```
✅ CwlCatchException exclusion already present in Podfile — skipping edit step
```

…the script has detected that the Podfile already contains the CwlCatchException exclusion (from a previous run). The edit step is skipped entirely and the script proceeds straight to `pod install`. There is nothing for you to do during the run. **Skip to Step 7.**

**This is the expected path on the next run** because the manual edit from the previous v2 run is still in place.

### Step 5B — Path A2 (no existing post_install block): script auto-appends the changes

If you see:

```
✅ No existing post_install block - adding complete block
```

…the script automatically appends the entire `post_install` block to the Podfile. Nothing for you to do. **Skip to Step 7.**

### Step 5C — Path B (pause): script needs you to edit the Podfile manually

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
cp ~/Desktop/podfile_cwl_fix_session.txt "/Volumes/USB DISK/Audioura/results/podfile_cwl_fix_session_v3.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile "/Volumes/USB DISK/Audioura/results/Podfile_after_v3.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile.lock "/Volumes/USB DISK/Audioura/results/Podfile.lock_after_v3.txt"
cp ~/Development/AudioTours/development/audio_tour_app/pubspec.yaml "/Volumes/USB DISK/Audioura/results/pubspec_after_v3.txt"
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
3. Tell Claude. Claude will read `Podfile_after_v3.txt` and `Podfile.lock_after_v3.txt` to diagnose why the exclusion did not take effect — usually a typo in the inserted block or an unexpected Podfile structure that needs a different insertion point.