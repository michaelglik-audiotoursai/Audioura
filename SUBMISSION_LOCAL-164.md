##### READY FOR REVIEW

# LOCAL-164: Version bump to 2.3.0+20 and rebuild wallet debug APK

**Branch:** `kiro/local164-version-bump-and-apk`
**Commit:** `01a2ad5`
**Commits ahead of subscribed:** 1

---

## Summary

Bumped `pubspec.yaml` version from `2.2.0+1` to `2.3.0+20` per D1
(globally monotonic build numbers). Rebuilt the debug APK with the same
`--dart-define` flags from LOCAL-157 and placed it at
`~/Desktop/audioura-wallet-debug-2.3.0+20.apk` for sideloading.

---

## Per-file changes

| File | Change |
|---|---|
| `audio_tour_app/pubspec.yaml` | `version: 2.2.0+1` → `version: 2.3.0+20` |
| `SUBMISSION_LOCAL-164.md` | This file |

---

## Evidence

### 1. pubspec.yaml diff

```diff
-version: 2.2.0+1
+version: 2.3.0+20
```

### 2. Version in binary (aapt dump badging)

```
$ /Users/micha/Library/Android/sdk/build-tools/35.0.0/aapt dump badging ~/Desktop/audioura-wallet-debug-2.3.0+20.apk | grep package:
package: name='com.audioura.audiotours' versionCode='20' versionName='2.3.0' platformBuildVersionName='15' platformBuildVersionCode='35' compileSdkVersion='35' compileSdkVersionCodename='15'
```

**versionCode=20, versionName=2.3.0** — matches `2.3.0+20`.

### 3. APK on Desktop

```
$ ls -la ~/Desktop/audioura-wallet-debug-2.3.0+20.apk
-rw-r--r--@ 1 micha  staff  165687320 Aug  3 11:17 /Users/micha/Desktop/audioura-wallet-debug-2.3.0+20.apk
```

165 MB debug APK.

### 4. git status clean

```
$ git status --short
(empty)
```

No android/ changes, no binary committed, no untracked files.

### 5. Build command used

```
flutter build apk --debug \
  --dart-define=WALLET_DEBUG_PORT=5102 \
  --dart-define=DEBUG_SERVER_IP=192.168.0.136
```

Same flags as LOCAL-157. Wallet traffic routes to `192.168.0.136:5102`.

### 6. No higher build number found

Checked: git tags (`git tag -l '*2.3*'` — none), git log
(`git log --all --oneline --grep="2.3.0"` — only DECISIONS.md), no installed
APK on disk. Build number 20 is safe.

---

## Limitations

1. **Not tested on a device.** No Android device/emulator connected. The APK
   compiles and packages with correct version metadata, but runtime behaviour
   is not confirmed on this machine.

2. **Disk space was critically low.** Build required clearing ~4.6 GB of
   stale build artifacts from other worktrees and Gradle caches. The machine
   had only 116 MB free at one point. Future builds may need similar cleanup.

3. **debug.keystore is untracked.** The build requires
   `audio_tour_app/android/app/debug.keystore` which is gitignored. Copied
   from the LOCAL-157 worktree. Any fresh worktree on a new machine will need
   this file generated or copied.

4. **Pre-existing analyzer warnings** (79 errors in dead files, NDK version
   mismatch, Java 8 source warnings) — identical to LOCAL-157, not introduced
   here.
