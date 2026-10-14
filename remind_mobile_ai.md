# Mobile App — Kiro Context Reminder (POST-COMPACTION RECOVERY)

_Last updated: 2026-09-03 by Mobile Kiro_

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
When chat history is compacted, the user will ask you to read `remind_ai.md` and `remind_mobile_ai.md`.
**Your response:**
"📱🔧 MOBILE KIRO — I've read both files. Branch `storied` at `c0049a8`, version `2.3.2+20`, published to Play Closed testing. Done this cycle: Stable/Preview selector + Version menu (wdvrdaxxmb), API-36 compliance build (wdvrdaxxma), credential-log security fix (wdvrday4pk, verified). Next up: Subscribed variant then Production before Nov 1 (wdvrday53b). Ubuntu-only builds; adb/Chrome for sideload (Files-by-Google broken by Play Protect). Ready to continue."

## Who you are
1. **Kiro (Android Mobile Agent)** — Audioura Android code changes, commits, and build coordination. Replaced Mobile Amazon-Q as of 2026-06-07.
2. **❌ Cannot build in Windows** — Flutter builds ONLY in the Ubuntu VM (`Ubuntu@UbuntuBase`).
3. **❌ iOS is not yours** — handled by iOS Amazon-Q / Storied_Tours on the Mac Mini.
4. **⚠️ AUTONOMY** — user grants full approval to implement changes directly. No propose-then-wait cycle.
5. **Dev location (Windows, source of truth):** `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`

## 🌿 CURRENT BRANCH & VERSION
- **Branch:** `storied` (NOT `services-migration`, NOT `main`). Services Kiro's entire backlog is on `storied`. Check out `origin/storied`; never create a new branch off it without being told.
- **Version:** `2.2.1+2` (in `pubspec.yaml`). Version-number rule: no zeros in the minor (Michael's convention — that's why it's 2.2.1, not 2.2.0).
- **`main`** = frozen Beta baseline. Never commit there.
- **Application ID:** `com.audioura.audiotours` (changed from `com.audioura.app` for Play Store).
- **Bundle ID (iOS):** `com.glikfamily.audioura`.

## 🧰 BUILD ENVIRONMENT (as of 2026-08-31 — toolchain task wdvrdaxy8q DONE)
The Ubuntu VM was upgraded to match the Mac Mini. Do NOT let the three machines drift again.
- **Flutter:** `3.41.6` (pinned via `git checkout 3.41.6` in `/home/Ubuntu/flutter`; detached HEAD is expected). Dart 3.11.4.
- **Android SDK:** platform `android-36`, build-tools `36.0.0`. `compileSdk = 36`, `targetSdk = flutter.targetSdkVersion` (= 36 on 3.41.6). Google requires API 35 — we exceed it.
- **NDK:** `28.2.13676358` (r28c) — required by `speech_to_text`. Pinned in `build.gradle.kts`.
- **Real SDK location:** `/home/Ubuntu/Android/Sdk` (had two stray SDK dirs; consolidated here). `ANDROID_HOME=/home/Ubuntu/Android/Sdk`, cmdline-tools on PATH. Added to `~/.bashrc`.
- **Licenses:** accepted via the CLASSIC `sdkmanager --licenses` (download `commandlinetools-linux-11076708_latest.zip`, run `./cmdline-tools/bin/sdkmanager --sdk_root=/home/Ubuntu/Android/Sdk --licenses`, answer `y`). The NEW "android CLI" tools deprecated `--licenses` and won't write them. NOTE: `flutter doctor` still shows a license ✗ — it's a **FALSE NEGATIVE**; builds work.
- **VM RAM:** 7.3GB total, ~0 swap by default → added a **4GB swapfile** (`/swapfile`) or the Gradle daemon gets OOM-killed.
- **`gradle.properties` (committed on storied):** `-Xmx2g -XX:MaxMetaspaceSize=512m`, `org.gradle.workers.max=2`, `android.enableJetifier=false` (app is AndroidX-native; Jetifier was the OOM culprit), `flutter.*` synced to SDK 36 / NDK 28.

### Build command (Ubuntu VM)
```bash
cd /media/sf_audiotours
git status                 # if clean: git pull origin storied
git reset --hard origin/storied   # if the shared folder has stray local changes (common — vboxsf + CRLF)
bash build_flutter_clean.sh
```
- The shared folder `/media/sf_audiotours` is a VirtualBox mount = the Windows dev tree. It is BUILD-ONLY; never author code there. All edits happen on Windows → committed → GitHub → pulled on the VM.
- Do NOT run `flutter build` directly inside `/media/sf_audiotours` — the vboxsf mount can't create plugin symlinks (`Operation not permitted`). `build_flutter_clean.sh` copies to `/tmp/audiotours_clean_build` first, which avoids this.
- Script outputs: `audioura-dev.apk` (release APK) + `audioura-release.aab` (signed AAB) copied back to `/media/sf_audiotours` (Windows shared folder).
- Script needs `build_secrets.env` in `/media/sf_audiotours` with `GATEWAY_API_KEY=...` (gitignored; fail-fast if missing).

### 📲 Installing an APK on the phone (Files-by-Google is BROKEN — use Chrome or adb)
Proven 2026-09-02 on Pixel 4 / Android 13: **tapping an APK in Files by Google fails with "The app wasn't installed"** — even byte-identical, valid, signed APKs. Root cause: Play Protect queues a background upload/scan (`Adding apk for upload`, `upload_consent=1`) and the Files `PackageInstaller` session times out (`Session ID is no longer active`). NOT a build/signing/versionCode/tour-data issue — ruled all out. Same bytes install fine via adb and via Chrome. (See ClickUp `wdvrday4x3` how-to + `wdvrdaxxmb` investigation.)
- **adb (phone via USB):** `adb install -r <apk>` — reliable, preserves data. adb is at `C:\Users\micha\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- **Chrome sideload (no USB):** `adb reverse tcp:8765 tcp:8765`, copy apk into a serve dir, `python -m http.server 8765` there; on phone Chrome → `localhost:8765/audioura.apk` → download → tap in Chrome's download bar → Install. Chrome is a different session owner, unaffected by the Play Protect upload path.
- **Testers (Yury/Igor):** Play Store internal-testing track — no sideload, updates auto-deliver. This is the real distribution path.
- Do NOT change phone Play Protect settings to work around this (Michael's standing instruction).

## 📋 WORKFLOW (ClickUp-driven)
- Work is tracked in **ClickUp** via the MCP server. Mobile queue list: **🟩 Mobile — Kiro** (`1000410000000734`). Services list: **🟦 Services — Kiro** (`1000410000000733`). Michael's list: **👤 Michael** (`1000410000000735`).
- Loop: read task → implement fully → commit to `storied` → push to GitHub → tell Michael "Ready to build on Ubuntu" → comment results on the task → move to review/appropriate status.
- **GitHub is the only cross-machine sync channel.** Never share Docker images across architectures.
- **Ask Michael before any Play Console upload** — outward-facing, not undoable.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md` (LEAD-owned).

## 🎯 STATE AS OF 2026-09-03 (latest session)

**Current branch tip:** `origin/storied` = commit `c0049a8`, version **`2.3.2+20`**.
**Published to Play Closed testing (Alpha):** release 20 (2.3.2), status Published 2026-09-03. NOT in Production yet.
**Phone (Pixel 4, Android 13):** running adb-installed 2.3.2+20.

### wdvrdaxy8q — Ubuntu toolchain upgrade — ✅ DONE
Flutter 3.41.6 + SDK 36 + NDK 28 + licenses + swap + gradle.properties. Commits `edfeaac`, `ce82c73`.

### wdvrdaxxmb — Stable/Preview (Beta/Storied) selector — ✅ DONE & SHIPPED to Closed testing
- Selector in About→Cloud section. **UI labels are Stable (=beta) / Preview (=storied)** per Michael 2026-09-01 — but pref/DB/API values stay `beta`/`storied`. Default Stable.
- Only the base URL changes: Beta=`https://api.audioura.com`, Storied=`https://storied-api.audioura.com` (NOTE order: storied-api, NOT api-storied; goes through Cloudflare like Beta — do not revert to the bare Cloud Run URL). `endpoints.dart` `cloudTrack()`/`setCloudTrack()`/`base()` + `trackLabel()`/`isPreviewTrack()` helpers.
- Per-tour `track` + optional `build_number` stored on the saved tour record (read from `/status` response, never recomputed; missing track⇒beta, missing build_number⇒no suffix).
- **Provenance NOT shown as a list/player chip** (confused testers). Instead: tour ⋮ menu → **Version** dialog shows generation date, release (track+build), services version. (my_tours_screen `_showVersionDialog`.)
- Services contract confirmed: same paths/auth; `audio_tours.track` 'beta'|'storied'. `build_number`/`code_sha` not yet populated by services (tracked wdvrdaxyud) → label shows bare Stable/Preview until then.

### wdvrdaxxma — Android release AAB + Play upload — ✅ substantially done
Compliance (API 36) + selector shipped together as 2.3.2+20 to Closed testing. Live Play versionCode WAS 18; must always exceed it. Play App Signing ENABLED (Play re-signs; sideload uses local key — different signature, can't cross-install). DO NOT generate a new keystore.

### wdvrday4pk — 🔴 SECURITY: credential/AES-key leak in debug log — ✅ DONE & VERIFIED
Plaintext passwords + AES key were written to persisted, in-app-viewable `debug_logs` + console. Fixed (in c0049a8):
- Removed secrets at source in `subscription_service.dart`, `subscription_encryption_service.dart`, and `subscription_credential_dialog.dart` (3rd file not in ticket) → log field names/lengths/existence only.
- Added `lib/services/log_redactor.dart` (`LogRedactor.redact`) + routed ALL `DebugLogHelper.addDebugLog` through it (guard against recurrence; NOT a kDebugMode gate).
- `main()` one-time purge of legacy `debug_logs` (keyed `debug_logs_security_purged_v2`).
- iOS `UIBackgroundModes [audio]` added to Info.plist (single key — a merge dup was removed).
- `test/log_redactor_test.dart` asserts secrets absent (can go red). Verified on device: submitted probe creds, full logcat had NO password/username/key; purge fired.

### wdvrday52p — Services bug (my report) — handed to Services Kiro
`/submit_credentials` returned 400 "Decryption failed: No module named 'cryptography'" — missing Python dep in newsletter service image. Services deployed a fix 2026-09-03.

### wdvrday53b — 🗓️ Production release plan (Michael's list) — TRACKING, due ~Oct 15
- API-36 compliance needs a **Production** release before **Nov 1, 2026** (Google extension). Reminder set Oct 15.
- Business decision: ship the **Subscribed** build variant (revenue path — a variant of the shared app like Beta/Storied) BEFORE Production, so public compute spend has a revenue offset. Subscribed variant not yet scoped as its own task.
- Fallback if Subscribed slips past mid-Oct: ship 2.3.2+20 (already in Closed testing) to Production anyway to keep update ability.

### wdvrday4x3 — HOW-TO (Michael's list, complete): sideload via Chrome/adb (Files-by-Google broken)

## 📲 SIDELOAD / INSTALL FACTS (proven 2026-09-02)
- **Files by Google tap-install FAILS** ("App wasn't installed") intermittently→consistently: Play Protect runs a Just-in-Time scan + `upload_requested`/`PlayProtectDialogsActivity` that outlives the PackageInstaller session (`Session ID is no longer active`). NOT a build/signing/versionCode/data issue. Ruled out v1/v2/v3/v4+.idsig (T2==T3 both failed), key, versionCode, residual pkg, storage, transfer.
- **Working install paths:** `adb install -r <apk>` (preserves data) OR Chrome download → tap in Chrome. adb at `C:\Users\micha\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- Chrome-serve method: `adb reverse tcp:8765 tcp:8765`; serve dir with `python -m http.server 8765`; phone Chrome → `localhost:8765/audioura.apk`.
- Signing is **v2+v3** (release config dropped the ineffective forced-v1/v4). Do NOT reintroduce v4 as a "fix" — it isn't one.
- Play tester opt-in link format: `https://play.google.com/apps/testing/com.audioura.audiotours` (confirm exact link on Closed testing → Alpha → Testers tab).
- Alpha testers list "Audioura Beta Testers": yury.makedonov@gmail.com, ilinkov@yahoo.com, michael.glik@gmail.com, elie.glik, glepsky, jacobnglik.

## 🚫 OWNERSHIP BOUNDARIES
- ✅ **MY files:** `remind_mobile_ai.md`, `code_review_v*.md`, files in `amazon-q-communications/audiotours/`
- ❌ **NEVER write:** `remind_ios_ai.md`, `remind_Services_ai.md`, `mac_mini_assignments.md`, `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`
- ✅ **To reach Services/iOS Kiro:** post a ClickUp comment on their task, OR write a markdown file in `amazon-q-communications/audiotours/requirements/`.

## 📡 iOS COMMUNICATION
Write iOS build requests to `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\IOS_BUILD_*.md`. iOS Kiro reads them. The Storied iOS build doc: `IOS_BUILD_v2.2.0.1_STORIED_2026_06_30.md` (note: predates the 2.2.1 bump; update when iOS build is next scheduled).

## 🧱 CODE CONVENTIONS (STANDING)
- **Debug output:** ALWAYS `DebugLogHelper.addDebugLog()` — NEVER `print()` (mobile apps can't console/file-print).
- **WebView:** `flutter_inappwebview` v6 — `initialSettings` only (not `initialOptions`); `addJavaScriptHandler` for JS↔Dart.
- **Map:** `flutter_map` + OpenStreetMap — no API keys, no cost.
- **NEVER use `IndexedStack`** — it keeps tab screens mounted so `initState()` never re-runs (broke mode-switching once). Use a `_buildBody()` switch so State is recreated per tab.
- **File hygiene:** no `_fixed`/`_backup`/`.bak` copies — Git is the history. Throwaway files go in `scratch/` (gitignored).
- **Version rule:** only bump version for functional changes; NEVER bump for a build-error fix. (Exception honored here: `2.2.1+2` bump was for Play `versionCode` uniqueness, a release requirement, not a build-error fix.)
- **Dead files to ignore:** `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `widget_test.dart`.

## 🔑 ENDPOINTS ARCHITECTURE (`lib/config/endpoints.dart`)
- `server_mode` pref: `cloud` (default) or `local`. Cloud → `https://api.audioura.com` (baked in, no user override read). Local → `http://<server_ip>:<port>` (dev server `192.168.0.218`).
- Cloud mode adds `X-API-Key` (built-in via `--dart-define=GATEWAY_API_KEY`) + `X-App-Attestation` for protected services (orchestrator, translation).
- **App Attestation** (`app_attestation_service.dart`): Play Integrity (Android, via `MainActivity.kt` MethodChannel `com.audioura.app/attestation`) + App Attest (iOS, Dart side ready, native Swift `AppAttestHandler.swift` still TODO for iOS Kiro). Log-only mode — token attached, gateway observes but doesn't enforce yet. Graceful: missing plugin ⇒ null ⇒ request proceeds.
- **Onboarding personalization** (`onboarding_screen.dart`): first-launch "What brings you here?" → 4 emoji → saves `narrative_tone` pref → sent in tour generation request body for Services routing.

## RECENT VERSION HISTORY (latest first)
- **v2.3.2+20** — SECURITY: credential/AES-key log leak fixed + redaction guard + legacy-log purge; iOS UIBackgroundModes audio. Shipped to Play Closed testing. Commit `c0049a8`.
- **v2.3.1+19/+5..+1** — Stable/Preview selector + Version menu; v2+v3 signing; versionCode walked up past live Play 18. (Superseded by +20.)
- **v2.2.1+2 / +1** — Play versionCode bump; Flutter 3.41.6 build-env fixes (Kotlin 2.2.0, NDK 28, Jetifier off, heap sizing).
- **v2.2.0+1** — Storied line: onboarding personalization + Play Integrity attestation.
- **v2.1.1+18** — Beta baseline (on `main`): signed AAB, `applicationId=com.audioura.audiotours`.

## ⚠️ CRITICAL REMINDERS
- ❌ NEVER build Flutter in Windows — Ubuntu VM only. (flutter not installed on Windows; `flutter test` also Ubuntu-only.)
- 🌿 All mobile commits go to `storied` (current release line), never `main`.
- 🔐 Never commit keystores/keys: `.gitignore` must exclude `key.properties`, `*.jks`, `*.keystore`, `*.apk`, `build_secrets.env`.
- 📱 `flutter doctor` license ✗ on the VM is a known false negative — builds work.
- ⚠️ **GIT SAFETY (hard lesson 2026-09-02):** `git reset --hard origin/storied` on the Ubuntu shared tree DESTROYED Mac Mini Claude's unpushed commit once. ALWAYS run `git log --oneline origin/storied..HEAD` FIRST — if it is non-empty, STOP and preserve those commits (push them) before resetting. Only reset when that check is empty. The shared `/media/sf_audiotours` tree is build-only; never author code there.
- 🤝 **Shared branch with Mac Mini Claude:** he also commits to `origin/storied` (iOS + Python/services work). On push rejection, `git fetch` + rebase onto origin/storied — NEVER force-push. Resolve dup edits (e.g. both added UIBackgroundModes once).
- 🔒 **NEVER log secrets:** passwords, usernames, keys, tokens. All `DebugLogHelper` goes through `LogRedactor`. Don't add raw `print()` of credentials/keys. See wdvrday4pk.
- 🏷️ Tester-facing track names are **Stable/Preview**, never Beta/Storied (internal only). DB/API/pref values stay beta/storied.
- 🧠 Secret-verification + any device test must run on Ubuntu/device, not Windows.
