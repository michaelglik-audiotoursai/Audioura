# Why it behaves this way — a model that fits every observation

**2026-09-02.** Written against the full experiment log. This is a hypothesis with a clear
falsification test, not a conclusion.

## Short answer: not random. A race with a stable bias, plus a feedback loop.

Two independent clocks run during a tap-install:

1. **Play Protect's just-in-time scan** — `PT6.0–6.7s` in the logs, and it only runs when Play
   has **no cached verdict for this APK's hash**.
2. **The PackageInstaller session's survival** — the session is created and owned by **Files by
   Google**, which is backgrounded the moment `PlayProtectDialogsActivity` comes to the front.

When clock 1 runs at all, there is a ~6–7 second window in which the session's owner is a
backgrounded, low-priority app on a 6 GB Pixel 4 that has just been asked to handle a 58 MB
file. When the owner does not survive that window, the session is abandoned. `W/huf: Session ID
is no longer active` is Play discovering that afterwards — **the symptom, not the cause** — which
is also why no `INSTALL_FAILED_*` is ever emitted: nothing *rejected* the install, the session
simply ceased to exist before `Marking session as applied`.

## The feedback loop — this is the part that answers the open question

> "Why do retries fail consistently rather than intermittently?"

**Because a failed install never records the verdict.** The scan completes, the verdict is
`ALLOW`, and then the session dies before commit — so nothing is cached against that hash. The
next tap of the same file therefore re-runs the **full** 6-second scan and re-enters exactly the
same race, with the device in the same state seconds later. Failure is self-reinforcing.

A **successful** install does record it. That is why re-tapping an APK that already installed
succeeds repeatedly and quickly — no dialog, no scan, no window, no race.

So the behaviour is bimodal, not random:

| regime | what happens | outcome |
|---|---|---|
| **no cached verdict** (new hash, or every retry after a failure) | dialog shown, 6–7 s scan, long window | fails whenever the owner does not survive; **repeats** |
| **cached verdict** (hash that previously installed) | no dialog, near-instant commit | succeeds, and keeps succeeding |

## It explains every row in the log

* **+3 tap-installed, then tap-reinstalled 3× with tours present** — the first install cached the
  verdict; the three reinstalls were the same hash, so they took the fast path. This also
  dissolves the "adding a tour breaks it" theory: the tours were irrelevant, the *cache* was.
* **+4 failed repeatedly, yet Michael tap-updated +4 twice successfully** — same hash, different
  device state. Once one of those taps succeeded the verdict was cached, so the second was easy.
  Those two successes were probably adjacent, not independent.
* **+5, T2, T3 fail** — every one is a **new hash**, so every one re-enters the scan regime.
* **T2 and T3 identical and both failing** — consistent; they share a hash and neither ever got
  far enough to cache anything.
* **adb always works** — the `shell`/system-owned session has no backgroundable UI app to lose.
  Nothing about the APK differs.
* **No `INSTALL_FAILED_*` ever** — expected under this model. Nothing rejected anything.

## The one prediction that falsifies it cheaply

> **Successful taps do not show `PlayProtectDialogsActivity`, and do not log a multi-second
> `scanTime`. Failing taps always do.**

The failure logcat was captured 3+ times and always contains both. **Nobody has captured a
success.** One `adb logcat` across a *successful* tap settles it:

* Success shows the dialog and a 6 s scan too → the model is wrong, the scan is incidental, and
  the session is dying for an unrelated reason.
* Success shows neither → the pattern is real and this stops being mysterious.

## Cause vs symptom — the tags that distinguish them

```bash
adb logcat -b all -s PackageInstallerSession:V PackageInstaller:V StagingManager:V \
                    ActivityManager:V ActivityTaskManager:I Finsky:V lowmemorykiller:V
```

Read for these, in order of decisiveness:

| line | means |
|---|---|
| `Killing <pid>:com.google.android.apps.nbu.files` / `am_kill` | **the smoking gun** — the session's owner was killed mid-scan |
| `PackageInstallerSession: Abandoning session <id>` | who abandoned it, and when relative to the scan |
| `Destroying session` / `Session was abandoned` | same |
| `Marking session <id> as applied` | present on every success, absent on every failure (already established) |

And while the Play Protect dialog is on screen — this is the measurement that matters:

```bash
adb shell dumpsys package installer                       # active sessions + owning installer
adb shell dumpsys activity processes | grep -A4 nbu.files # oom_adj of the owner while backgrounded
```

If Files by Google sits at a killable adj while holding the session, the mechanism is confirmed
without having to catch the kill itself.

## Experiments, cheapest first

**E1 — capture one success.** The falsification test above. Costs one tap.

**E2 — reboot, then tap immediately.** Fresh boot, nothing else opened, tap a previously-failing
APK. If it now installs, memory pressure is implicated, and "consistent retry failure" is
explained by device state being stable over minutes but not across reboots.

**E3 — change the installer app.** Put the APK on the phone and install it from **Chrome's
Downloads** instead of Files by Google. Chrome is heavier and far less likely to be killed while
backgrounded. If Chrome succeeds where Files fails on the same bytes, the owner's lifecycle is
confirmed as the variable — and that is a usable workaround by itself.

**E4 — shrink the APK.** The current one is 58 MB carrying **three ABIs**; the Pixel 4 needs only
`arm64-v8a`:

```bash
flutter build apk --release --target-platform android-arm64
```

Roughly a 25 MB file — less to copy, less to scan, a shorter window. If the small one installs
reliably where the fat one does not, that is both strong evidence and a practical fix. **Run this
second, after E1.**

**E5 — remove the scan variable without disabling Play Protect.** Play Store → Play Protect →
Settings → **"Improve harmful app detection"** OFF (this is the `upload_consent=0` setting),
leaving scanning ON. Also worth knowing: once the package reaches **Play internal testing**, Play
recognises it and the just-in-time scan short-circuits — which may make sideload reliable as a
side effect.

**E6 — confirm the cache mechanic directly.** Take an APK that has just *succeeded*. Uninstall the
app. Tap the same file again — under this model it should still succeed (verdict cached, no
dialog). Then change one byte of a resource, re-sign, and tap: a new hash should re-enter the scan
regime and fail. If both hold, the cache is doing exactly what the model says.

## On making sideload robust

An installer app that owns the session and holds a **foreground service** across the scan would
not be killable, and that is genuinely how a robust sideloader would be built — but writing one
for this is disproportionate to the problem.

The honest ordering:

1. **Testers → Play** (internal/closed testing). Play re-signs the AAB and delivers through its own
   path; none of this applies. It is also the only way the AAB path gets verified, which is a real
   gap Michael is right to be uneasy about.
2. **Dev → `adb install -r`**, wired or wireless. Verified to preserve data across +3→+4→+5.
3. **If tap-install is wanted anyway**, E3 and E4 are the two changes most likely to make it
   dependable, and both are cheap.
