# Assignment 21 Walkthrough (Archived)

## Assignment 21 — Revert Podfile and Diagnose Framework Embedding

**Goal:** Roll the iOS Podfile back to a clean Flutter-template state, build cleanly, and capture diagnostic evidence about why `CwlCatchException.framework` is not being embedded properly. **This assignment does NOT attempt a fix.** It gathers data so the next assignment can apply a precise fix.

**Script to run:** `podfile_revert_and_diagnose.sh`.

This walkthrough is self-contained.

### Prerequisites (verify on Windows side BEFORE switching the KVM)

- [ ] `D:\Audioura\scripts\podfile_revert_and_diagnose.sh` exists.
- [ ] `D:\Audioura\results\` exists.
- [ ] The USB stick is plugged in and visible at `D:\` in Windows.
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) is plugged into the Mac Mini.

### Step 1 — Switch KVM to Mac Mini

Standard KVM switch.

### Step 2 — Confirm USB stick

Open Terminal. Run:
```
ls /Volumes/
```
You should see `USB DISK`.

### Step 3 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x podfile_revert_and_diagnose.sh
```

### Step 4 — Run the script

```
./podfile_revert_and_diagnose.sh
```

The script runs straight through with no manual intervention required (no Podfile-edit prompts, no Path A/B/C decision tree). It will:

1. Back up the current Podfile to `ios/Podfile.before_revert`.
2. Overwrite `ios/Podfile` with a clean version (removes our v1/v2/v3 additions).
3. Run `flutter clean`, `flutter pub get`, `pod install`, `flutter build ios --release`.
4. Print a long block of "DIAGNOSTIC 1" through "DIAGNOSTIC 6" output. **This is the whole point of the run** — let it complete.
5. Sign and install on the iPhone.

Run time: ~5–15 minutes.

### Step 5 — Test the app on the iPhone

Open Audioura. The app **is expected to crash** at launch with a `Library not loaded: @rpath/CwlCatchException.framework/...` error. That confirms we're back to the original baseline. **Do not panic — this is intentional. We're reproducing the original problem in a controlled way so we can fix it precisely.**

If by some chance the app launches successfully — do not believe your eyes, but tell Claude. That would mean the original crash has somehow already been fixed by a side effect, and we'd take a fresh look.

### Step 6 — (Optional, only if you want to) Capture an iPhone crash log

If you want to give Claude richer crash data:

1. On the iPhone, open **Settings → Privacy & Security → Analytics & Improvements → Analytics Data**.
2. Scroll to find a recent log starting with `Audioura-` (named with today's date and time).
3. Tap it, then tap the share icon (square with up-arrow), then **AirDrop** to the Mac Mini (or **Save to Files** and transfer manually).
4. On the Mac Mini, copy the received `.ips` file into `/Volumes/USB DISK/Audioura/results/`.

This step is optional. If it's hassle, skip it — the script's diagnostics are the priority.

### Step 7 — Copy results back to USB

```
cp ~/Desktop/revert_and_diagnose_session.txt "/Volumes/USB DISK/Audioura/results/revert_and_diagnose_session.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile "/Volumes/USB DISK/Audioura/results/Podfile_after_revert.txt"
cp ~/Development/AudioTours/development/audio_tour_app/ios/Podfile.lock "/Volumes/USB DISK/Audioura/results/Podfile.lock_after_revert.txt"
```

### Step 8 — Eject USB and switch back to Windows

```
diskutil eject "/Volumes/USB DISK"
```

Switch the KVM back to Windows.

### Step 9 — Tell Claude

Switch back to Cowork on the Windows laptop and say:
> Assignment 21 done. Results are in `D:\Audioura\results\`. App [crashed at launch / launched successfully — describe what you saw].

Claude will read all the diagnostic output from the session log and write the fix script as Assignment 22.