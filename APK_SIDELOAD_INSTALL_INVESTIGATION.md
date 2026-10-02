# "App wasn't installed" on tap-install — evidence, 2026-09-01

**Session:** `GCloud_Storied` (Windows laptop). Written in reply to Mobile Kiro's v4-signing
hypothesis. Everything below is measured with `build-tools/35.0.1` `apksigner`, `aapt2` and
`zipalign` against the actual files in this repo.

## Headline: the apksigner reading the hypothesis rests on is a misread

`apksigner verify` reports which schemes were **used to verify in the applicable SDK range**,
not which schemes are **present**. `audioura-dev.apk` declares `minSdkVersion=24`, and above
API 24 v1 is never consulted — so apksigner prints `v1: false` for an APK that carries a
perfectly valid JAR signature.

```
$ apksigner verify -v audioura-dev.apk
Verified using v1 scheme (JAR signing): false        <-- what Kiro saw
$ apksigner verify -v --min-sdk-version 21 audioura-dev.apk
Verified using v1 scheme (JAR signing): true         <-- same file, v1 is valid
$ unzip -l audioura-dev.apk | grep -E "CERT\.(SF|RSA)"
    44422  META-INF/CERT.SF
     1414  META-INF/CERT.RSA
```

**So `2ff1641` (enableV1Signing) did take effect.** The shipped APK is v1 + v2, both valid.

`v4: false` is the same artifact of the tool: v4 lives in a **separate `.idsig` file**, and
apksigner reports `false` unless you pass `--v4-signature-file`. Demonstrated by re-signing
`audioura-dev.apk` with `--v4-signing-enabled true`: `v4: false` without the flag,
`v4: true` with it, same APK.

## v4 cannot be the requirement — proved from the artifacts that worked

Every APK in this repo, including every one that tap-installed fine:

| APK | package | signer | v1 | v2 | v4 |
|---|---|---|---|---|---|
| `audioura-dev.apk` **(fails)** | `com.audioura.audiotours` 2.3.1 (vc 2) | **CN=Mikhail Glik, Audioura LLC** | ✅ | ✅ | ❌ |
| `APK_BUILDS/app-release_v1.0.0.149.apk` **(the "easy install" one)** | `com.example.audio_tour_app` | Android Debug | ✅ | ✅ | ❌ |
| `APK_BUILDS/app-release.apk` | `com.example.audio_tour_app` | Android Debug | ✅ | ✅ | ❌ |
| `APK_BUILDS/app-debug*.apk` (1.1.20.4 / 1.2.2.16 / 1.2.2.19 / 1.2.3) | `com.audiotours.dev` | Android Debug | ✅ | ✅ | ❌ |
| `app-release-autotest.apk` | `com.audiotours.autotest` | Android Debug | ✅ | ✅ | ❌ |
| `app-release-dev.apk` | `com.audioura.app` 1.2.7 | Android Debug | ❌ | ✅ | ❌ |

**Not one artifact that ever installed has a v4 signature.** If the tap-install path required
v4, none of them could have installed either.

The mechanism argues the same way: a `.idsig` is a **separate file next to the APK**. Picking
an `.apk` in a file manager gives the installer no way to deliver one. Incremental install is
the adb/Studio fast-deploy path (`adb install --incremental`); the PackageInstaller UI session
writes bytes into an ordinary session. `could not load root hash from incremental install` is
what the framework logs when it probes for a v4 signature and finds none — it is noisy at `E`
level and appears on installs that succeed.

## Answers to the three questions

1. **The 1.2.1.1 APK does not exist in this repo.** Nearest are `com.audiotours.dev` 1.2.2.16 /
   1.2.2.19 / 1.2.3 and `com.example.audio_tour_app` 1.0.0.149/152 — **all debug-signed,
   all v1+v2, none with v4.** Michael's "installed easily" build was a debug-signed build of a
   *different package*.
2. **No — there is no record of a release-signed `com.audioura.audiotours` ever tap-installing,
   because none ever existed before this one.** `com.audioura.audiotours` appears in exactly one
   artifact in the repo: the failing `audioura-dev.apk`. Every other build carries one of
   `com.audiotours.dev`, `com.example.audio_tour_app`, `com.audiotours.autotest`,
   `com.audioura.app`. This is the **first** release-signed build of this package — so "it used
   to work" is not a regression, it is a path never walked before.
3. **No, v4 is not the fix**, per the table above.

## The APK itself is structurally clean — ruled out, do not re-check

* zipalign 4-byte check: **PASS**
* native libs `Stored` (uncompressed), `extractNativeLibs=false` — consistent
* `minSdkVersion=24`, `targetSdkVersion=36`, 2 dex, 14 permissions
* no `testOnly`, no `debuggable`, no `sharedUserId`, no `com.android.vending.splits.required`
* signature verifies, single signer, RSA 2048

## What is actually still unknown

**The failure reason was never captured.** The lines quoted are adjacent noise; Android always
logs a specific `INSTALL_FAILED_*`. Get it:

```bash
adb logcat -c
# reproduce the tap-install
adb logcat -d | grep -iE "INSTALL_FAILED|PackageInstaller|installStage|onSessionFinished|StagingManager|ReconcileFailure"
```

Then, in order of cost:

1. **`adb shell pm list packages -u | grep -i audioura`** — `-u` includes uninstalled-but-retained
   packages. A residual `com.audioura.audiotours` from any earlier differently-signed build gives
   `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, which surfaces as exactly this generic message. "Clean
   phone" usually means "I uninstalled it", which is not the same thing.
2. **`adb install -r audioura-dev.apk`** with **no** `--no-incremental`. If that also succeeds,
   the incremental path is exonerated outright and the problem is specific to the
   PackageInstaller UI / Files by Google.
3. **A one-variable APK is staged** at the scratchpad path in the session log: `audioura-dev.apk`
   re-signed with the same release key plus **v3 and v4** (`.idsig` emitted). If tap-install still
   fails with v3+v4 present, signing is dead as a hypothesis and the answer is on the device side.

## On the two candidate fixes

* **(a) enable v4 signing** — do not do this to fix tap-install; the evidence above says it is
  not the mechanism. It is worth having eventually for `adb install --incremental` speed, which
  is a different benefit.
* **(b) accept `adb install --no-incremental` for dev, testers get Play builds** — sound as a
  *workaround*, and the reasoning that it never reaches testers is correct: Play re-signs with
  the Play App Signing key, so the sideload path is not the tester path. But do not adopt it as
  the *answer* before step 1 above runs. If the cause is a residual package or a device policy,
  it will bite again the moment someone sideloads, and it is a two-minute check.
