# Mobile App — Kiro Context Reminder (POST-COMPACTION RECOVERY)

_Last updated: 2026-08-31 by Mobile Kiro_

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
When chat history is compacted, the user will ask you to read `remind_ai.md` and `remind_mobile_ai.md`.
**Your response:**
"📱🔧 MOBILE KIRO — I've read both files. Current branch is `storied`, version `2.2.1+2`. Ubuntu VM toolchain upgraded to Flutter 3.41.6 / Android SDK 36 / NDK 28.2.13676358. Release APK + signed AAB build successfully via `build_flutter_clean.sh`. Ready to continue."

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

## 📋 WORKFLOW (ClickUp-driven)
- Work is tracked in **ClickUp** via the MCP server. Mobile queue list: **🟩 Mobile — Kiro** (`1000410000000734`). Services list: **🟦 Services — Kiro** (`1000410000000733`). Michael's list: **👤 Michael** (`1000410000000735`).
- Loop: read task → implement fully → commit to `storied` → push to GitHub → tell Michael "Ready to build on Ubuntu" → comment results on the task → move to review/appropriate status.
- **GitHub is the only cross-machine sync channel.** Never share Docker images across architectures.
- **Ask Michael before any Play Console upload** — outward-facing, not undoable.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md` (LEAD-owned).

## 🎯 ACTIVE TASKS (as of 2026-08-31)

### wdvrdaxy8q — Ubuntu toolchain upgrade — ✅ DONE
Flutter 3.41.6 + SDK 36 + NDK 28 + licenses + swap + gradle.properties fixes. Debug AND release builds pass on `storied`. Commits: `edfeaac` (NDK/Jetifier/props), `ce82c73` (heap 2g + workers 2). Results logged on the task.

### wdvrdaxxma — URGENT: Android release AAB + Play upload — 🔄 IN PROGRESS
- AAB builds successfully (`audioura-release.aab`, ~46M, `2.2.1+2`). Signing key IS on the Windows laptop (build succeeds with release signing).
- **Remaining before close:** (1) Michael tests audio/map/downloads/permissions on device; (2) confirm `versionCode` not a duplicate in Play (bumped to `2.2.1+2` for this); (3) Michael approves + uploads to Closed testing; (4) confirm target-API warning clears; (5) document keystore home (Google Cloud Secret Manager recommended, NOT ClickUp) + second copy.
- Play App Signing is ENABLED (losing upload key is recoverable). Package `com.audioura.audiotours`.
- DO NOT generate a new keystore. DO NOT upload without Michael's OK.

### wdvrdaxxmb — Beta vs Storied selector in Cloud option — ⏳ BLOCKED on Services
- Build: in the Cloud option add a **Beta / Storied** selector. **Beta is and stays the default** (older installed apps send no track field → must behave unchanged; missing/unknown track = Beta).
- The choice changes ONLY the base URL the app posts to. Nothing else in the request changes (Michael's requirement: like-for-like comparison of the same venue on both tracks).
- Persist to a `cloud_track` pref. Show a small track label on the tour list AND the player. Store `track` on the saved tour record — READ `audio_tours.track` from server responses, do not recompute.
- **Blocked:** needs the Storied base URL + path/auth/response-field confirmation from Services Kiro (deployment task `wdvrdaxxm9`). Contract request already posted as a comment on `wdvrdaxxm9`.
- **Version when built:** `2.3.1+1` (Michael's call — bump minor to 2.3, no zeros).
- Deliberately NOT coupled to wdvrdaxxma (compliance AAB ships first without the selector).

### wdvrdaxxm9 — Services: Deploy Storied to GCloud ALONGSIDE Beta — (Services Kiro's task, my dependency)
- Two Cloud Run services, one Postgres, `audio_tours.track` discriminator (`'beta'|'storied'`, NOT NULL DEFAULT 'beta'). Beta stays byte-for-byte unchanged. I need the Storied URL from this.

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
- **v2.2.1+2** — build-number bump for Play upload (avoid duplicate versionCode). Commit `da870f8`.
- **v2.2.1+1** — corrected version label (was mislabeled 2.2.0). Build-env fixes for Flutter 3.41.6: Kotlin→2.2.0, NDK→28, Jetifier off, heap sizing.
- **v2.2.0+1** — Storied release line: onboarding personalization + Play Integrity attestation (Android MethodChannel + iOS Dart side). Branch `storied`.
- **v2.1.1+18** — Beta baseline (on `main`): signed AAB support, `applicationId=com.audioura.audiotours`, translation-failure modal dialog, AAB copy-back in build script.
- **v2.1.1+9 and earlier** — cloud auth (`user_id` in tour body), news/newsletter URL migration to `Endpoints`, account deletion UI, existing-tour translation, poll hardening. (Full history in git log.)

## ⚠️ CRITICAL REMINDERS
- ❌ NEVER build Flutter in Windows — Ubuntu VM only.
- 🌿 All mobile commits go to `storied` (current release line), never `main`.
- 🔐 Never commit keystores/keys: `.gitignore` must exclude `key.properties`, `*.jks`, `*.keystore`, `*.apk`, `build_secrets.env`.
- 📱 `flutter doctor` license ✗ on the VM is a known false negative — builds work.
- 🧠 If the shared folder blocks a `git pull` with "local changes would be overwritten", use `git reset --hard origin/storied` (safe — build-only folder).
