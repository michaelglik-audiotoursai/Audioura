# Three dead hypotheses and the control that was never taken — 2026-09-02

## First: my race model is dead. The v5 capture killed it.

I proposed that Play Protect's just-in-time scan opened a 6–7 second window in which the
session's owner could be killed. The latest failure has **no dialog and no scan** and dies in
about one second. A model that requires a 6-second window cannot explain a 1-second failure.
Discard it.

## Second: "could not load root hash" is also already refuted — by data we have

The new theory is that `E PackageManager: ERROR: could not load root hash from incremental
install` is the through-line. Two things in the existing log rule it out, and neither needs a
new capture.

**1. The line is followed by the install continuing.** In the v5 trace it appears at `00.440`,
and `Integrity check passed` lands at `00.491`, then `result=ALLOW` at `01.500`. The session ran
for a further **full second** after the line. Whatever it reports, it did not stop anything
there.

**2. An APK with no v4 signature at all tap-installed successfully — three times.** `v2.3.1+3`
is v2+v3, no v4, no `.idsig`. There is no root hash for that file anywhere in the universe, so
whatever code path emits that error must have emitted it during those successful installs too.
A line that appears on successes cannot be the cause of failures.

The same argument covers the TEST APK: its `.idsig` sat on the PC and on the phone as a sibling
file that the installer has no way to open, so it too installed with no root hash available.

**Note the shape of the claim, too.** "The cause is a missing root hash that cannot be supplied
through this path" would mean *no* non-v4 APK could ever tap-install. Two of them did.

## Third — and this is the actual problem

**Nobody has ever captured a successful TAP install.**

Every comparison in this investigation has been *tap-failure* versus *adb-success*. Those two
differ in the installer app, the session owner, the calling UID, the install flags, the
verifier path and the UI lifecycle — a dozen variables at once. That is why three hypotheses in
a row have looked compelling and then died: each was built on a diff that was never controlled.

Kiro's own summary says the marker is absent "on adb successes". The relevant question is
whether it is absent on **tap** successes, and that has never been looked at.

## The experiment. Everything else waits on it.

A success can be produced **on demand**: re-tapping an APK whose exact bytes are already
installed has worked every time it has been tried (+3 reinstalled 3×). So both halves of a
controlled pair are available in the same minute, on the same device, through the same
installer, with one variable — which file.

```bash
# 1. Put the device in a known state: install +3 by tap so it is the current install.

# 2. CAPTURE A SUCCESS — re-tap the same +3 file.
adb logcat -c
#   <tap v2.3.1+3 in Files by Google, let it complete>
adb logcat -d > tap_SUCCESS.txt

# 3. CAPTURE A FAILURE — tap +5, changing nothing else.
adb logcat -c
#   <tap v2.3.1+5 in Files by Google, let it fail>
adb logcat -d > tap_FAIL.txt

# 4. Diff them.
diff <(sed 's/^[0-9: .-]*//' tap_SUCCESS.txt) <(sed 's/^[0-9: .-]*//' tap_FAIL.txt) | less
```

Run both captures with the fuller tag set so the session lifecycle is visible:

```bash
adb logcat -b all -s PackageInstallerSession:V PackageInstaller:V PackageManager:V \
                    StagingManager:V IncrementalService:V ActivityManager:V \
                    ActivityTaskManager:I Finsky:V
```

**What the diff answers immediately:**

* `could not load root hash` present in **both** → confirmed noise, permanently.
* `Session ID is no longer active` present in both → also noise; the real divergence is
  elsewhere and the diff will show where.
* The **last line the two traces share** is the branch point. That single line localises the
  failure better than every hypothesis so far combined.

Look specifically for what the failure trace has *instead of* `Marking session as applied`:
`Abandoning session`, `Destroying session`, `Session was abandoned`, an `ActivityManager:
Killing` line naming `com.google.android.apps.nbu.files`, or a `createSession` with different
flags.

## The second measurement, which nobody has run yet

This was suggested and skipped, and it converts the silent failure into a real error code:

```bash
adb shell settings get global verifier_verify_adb_installs   # 0 means adb SKIPS the verifier
adb shell settings put global verifier_verify_adb_installs 1
adb install -r audioura-dev.apk          # now routed through the same verifier the tap path uses
```

If `adb install` now fails, it prints the `INSTALL_FAILED_*` the UI swallows — the missing error
code, with nothing disabled. If it still succeeds, the verifier is exonerated and the difference
is in the session/owner, not verification. Restore the original value afterwards.

## On the intermittency

> "Why consistent on retry in some sessions, but +4 tap-updated twice successfully in another?"

I do not have a confident answer, and with the race model dead I am not going to invent a
fourth story. What the intermittency does establish is that **the variable is not in the APK** —
the same bytes both succeed and fail. That is worth holding onto, because it means further APK
surgery cannot resolve this. Only the controlled capture will localise it.

## Guidance, and what to do in parallel

The controlled capture is cheap, so it is worth doing. Independently of it, two things help
regardless of the mechanism and neither is speculative:

* **Build a single-ABI APK.** 58 MB across three ABIs; the Pixel 4 needs only arm64.
  `flutter build apk --release --target-platform android-arm64` gives roughly 25 MB. Less to
  copy, less to verify, a smaller window for anything timing-related. Cheap, and it makes every
  future tap test faster.
* **Try a different installer app** — install from Chrome's Downloads instead of Files by
  Google. If the same bytes install, the session owner is the variable and there is a usable
  workaround immediately.

And the standing answer to the last question: **testers use Play, dev uses `adb install -r`.**
That is not a defeat — it is the correct architecture. Play re-signs the AAB and delivers
through its own path, so none of this reaches a tester. What genuinely still needs proving is
the **AAB path itself**, which no amount of sideload work will establish; that needs one build
pushed to internal testing and installed from Play.
