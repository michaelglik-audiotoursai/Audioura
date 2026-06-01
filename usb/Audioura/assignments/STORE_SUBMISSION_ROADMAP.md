# Audioura — App Store + Play Store Submission Roadmap

**Goal:** Take the working iOS + Android dev build (currently `1.2.9+25`, validated on iPhone 16 via A28 Path A) all the way to public availability on the Apple App Store and the Google Play Store.

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-05-01. This is a SPEC, not Claude-authored scripts. Amazon-Q drafts the per-phase scripts/assignments using this roadmap; Claude reviews each before USB transfer (V2 lesson — review-before-execute discipline).

**Total timeline:** 4–8 weeks depending on Apple review iteration.

**Total cost (one-time + ongoing):** ~$25–40 one-time (Play Console fee + optional domain) + the chosen backend hosting cost (see Phase 0). Apple Developer Program membership ($99/year) is already paid — signing identity `594584F3D3BC571D94A822A2158871CA13898701` is in keychain and proven working.

---

## Pre-flight assumptions (verified state at start of A31)

These should all be `true` going into Phase 1. If any are false, fix before proceeding:

- [ ] iOS app launches on iPhone 16 without CwlCatchException crash (A28 Path A SUCCESS — verified visually 2026-05-01).
- [ ] All A29 + A30 features work (device info, settings persistence, location permission, tour clustering, location search, tour search, newsletter mode, language selector, subscription dialog).
- [ ] Android build still works (project log: "Android works"; should re-verify after A30 Dart changes).
- [ ] Apple Developer Program membership active for team `4HGRU6TKGQ` ($99/year — already paid).
- [ ] Backend is reachable from the iPhone over the home network at `http://192.168.0.218:5005` (the dev URL inside the app).

If Android hasn't been re-verified after A30, that's a Phase 0a side task: build APK, install on an Android device, verify the same feature set works.

---

## Phase 0 — Backend reachable via public HTTPS

**Goal:** External testers (anyone not on Sir Michael's home Wi-Fi) can hit the backend over HTTPS. This is the precondition for everything else: TestFlight builds going to anyone external, Play Console internal testing, App Store review (Apple reviewers are on Apple's network, NOT your home network), and ATS compliance in `Info.plist`.

**Three options — choose one before A31.** Whichever is chosen, the rest of the roadmap is identical from Phase 1 onward.

### Option A: Cloudflare Tunnel (RECOMMENDED for first month or two)

- **Cost:** $0
- **Setup time:** 30–60 minutes
- **Throwaway when migrating later:** removing `cloudflared` from laptop, ~5 minutes
- **Pros:** Free; HTTPS terminated at Cloudflare's edge with their cert; stable hostname across laptop reboots and ISP IP changes; no firewall/port-forwarding work; doesn't move backend off the laptop.
- **Cons:** Laptop must be on for testers to use the app. Tunnel restart needed if `cloudflared` crashes. Not appropriate for production-scale traffic but fine for tens of testers.

**Amazon-Q tasks for A31a:**
- Install `cloudflared` on the Windows laptop (`winget install Cloudflare.cloudflared` or download MSI).
- `cloudflared tunnel login` → opens browser, authenticates with a free Cloudflare account.
- `cloudflared tunnel create audioura-dev` → creates a tunnel and returns a tunnel UUID.
- Choose hostname: either a free `<random>.trycloudflare.com` (no account needed past login) OR a custom domain hosted on Cloudflare DNS (recommended — `api.audioura.io` or similar; cheap and stable).
- Configure `~/.cloudflared/config.yml` to point hostname at `http://localhost:5005`.
- `cloudflared tunnel run audioura-dev` (run in foreground for now; later we make it a Windows service).
- Verify `https://<hostname>/health` returns the same response as `http://192.168.0.218:5005/health`.
- Document the chosen hostname in `D:\Audioura\assignments\backend_hostname.md` so all subsequent assignments can reference one source of truth.

### Option B: VPS migration (recommended once tester count > 20 or laptop-uptime becomes a constraint)

- **Cost:** $4–6/month (Hetzner CX22 / DigitalOcean droplet / Linode 1GB)
- **Setup time:** 2–4 hours first time
- **Pros:** Stable; doesn't depend on laptop being on; gives a real production-grade endpoint; HTTPS via Let's Encrypt + Caddy/Traefik/nginx; same Docker Compose stack moves verbatim.
- **Cons:** Real money; one more thing to maintain; data backups become your problem.

**Amazon-Q tasks for A31b (skip if doing A31a):**
- Provision the VPS (Ubuntu 22.04 or 24.04).
- SSH key setup, basic hardening (ufw, fail2ban, automatic updates).
- Install Docker + docker-compose-plugin.
- `git clone` (or rsync from laptop) the dev backend.
- Copy `.env` + secrets (manually — DO NOT commit to git).
- Reverse proxy via Caddy with automatic Let's Encrypt: `Caddyfile` with `api.audioura.io { reverse_proxy localhost:5005 }`.
- DNS A record at the registrar pointing the hostname at the VPS IP.
- `docker compose up -d` and verify HTTPS endpoint responds.

### Option C: AWS migration

Defer per Claude's review of `AUDIOURA_DEPLOYMENT_STRATEGY.md` (see project log). Revisit after data exists from Phase 5 external testing. Not part of this roadmap.

### Phase 0 success criteria (regardless of option chosen)

- `https://<chosen-hostname>` responds 200 to `/health` (or whatever the existing healthcheck endpoint is).
- The hostname is on a TLS cert that's valid for that hostname (Cloudflare Universal SSL or Let's Encrypt).
- The Flutter app, rebuilt with `BACKEND_BASE_URL = https://<chosen-hostname>`, can list tours / generate a tour / play audio end-to-end through the public hostname.

---

## Phase 1 — Bundle / ATS / Info.plist cleanup (Assignment 31)

**Goal:** Make the iOS build acceptable for Apple's automated submission checks. None of this affects the dev workflow; it's all submission-prep hygiene.

**Time estimate:** 1–2 hours of code/config changes plus one A28 build cycle to verify.

**Source of truth:** these files live in `D:\Audioura\assets\` (Windows side, copied to Mac via `copy_ios_fixes.sh`) and `~/Development/AudioTours/development/audio_tour_app/` (Mac side after copy).

### A31 task list — Amazon-Q to draft + execute

**1. Bundle name + display name.**

Current state in `D:\Audioura\assets\ios\Runner\Info.plist`:
```xml
<key>CFBundleName</key><string>audio_tour_app</string>
<key>CFBundleDisplayName</key><string>Audio Tour App</string>
```

Required state:
```xml
<key>CFBundleName</key><string>Audioura</string>
<key>CFBundleDisplayName</key><string>Audioura</string>
```

Also in `D:\Audioura\assets\pubspec.yaml`:
```yaml
name: audio_tour_app_dev   # → leave as-is for the package name (internal)
description: AudioTours Dev - AI-powered audio tour generator   # → "Audioura — AI-generated audio walking tours"
```

The Dart package name doesn't have to change; users never see it. The `description` in pubspec.yaml is mostly internal but should match marketing.

**2. ATS lock-down.**

Current state: `Info.plist` has NO `NSAppTransportSecurity` key. With ATS defaults, plain HTTP is blocked. The dev build presumably works against `http://192.168.0.218:5005` because of `flutter_inappwebview` carve-outs or similar; this won't survive App Review.

Required state: add an explicit ATS block that *disallows* arbitrary loads, signaling compliance to App Review:

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <false/>
</dict>
```

After this change, EVERY backend URL the app talks to MUST be HTTPS. That's why Phase 0 has to land first.

**3. Backend URL switch.**

Wherever the app currently has `http://192.168.0.218:5005` (likely `lib/services/` somewhere — Amazon-Q to grep), replace with the Phase 0 HTTPS hostname. Recommended pattern: a single `lib/config/api_config.dart` with a const `BACKEND_BASE_URL` so future changes are one-line.

If there's any need to keep the local dev URL for testing on the home network, use a build flag (`--dart-define=USE_LOCAL_BACKEND=true`) so release builds NEVER include the localhost/IP URL.

**4. Encryption export compliance.**

The new `subscription_encryption_service.dart` uses AES-128-CBC via `pointycastle`. That's non-exempt encryption under U.S. export rules. Two paths:

- **Easier:** add `<key>ITSAppUsesNonExemptEncryption</key><false/>` to Info.plist if the encryption is ONLY for password/credential auth (which it might be for the Diffie-Hellman key exchange — needs verification by Amazon-Q reading `subscription_service.dart` and `subscription_encryption_service.dart`). Apple has a specific exemption for "encryption to protect user authentication only."
- **Harder:** if encryption is used more broadly, set `<true/>` and submit an annual self-classification report to BIS (Bureau of Industry and Security). Free, but paperwork.

**Decision needed:** Amazon-Q reviews the actual usage of pointycastle in the codebase and reports back which exemption applies, then adds the right Info.plist key.

**5. Background modes (audio playback).**

The app plays audio while the user walks; if the user locks the screen or backgrounds the app, audio should continue. That requires:

```xml
<key>UIBackgroundModes</key>
<array>
    <string>audio</string>
</array>
```

Verify the app actually plays audio in the background after this change — without it, Apple may reject. With it, the App Privacy section needs to disclose audio collection if microphone is used in background.

**6. Microphone / speech / location strings — verify they're user-facing-friendly.**

Already present and acceptable in current `Info.plist`. Just confirm the wording is what you'd want a reviewer to read.

**7. App icon set.**

Apple requires icons in many sizes. Flutter's `flutter_launcher_icons` package handles this from a single 1024×1024 source. Amazon-Q to:
- Verify a 1024×1024 source icon exists at e.g. `assets/icons/app_icon_1024.png`.
- Generate the iOS icon set via `flutter pub run flutter_launcher_icons:main`.
- Verify the icon file `Runner/Assets.xcassets/AppIcon.appiconset/Contents.json` contains all required sizes.

**8. Launch screen branding.**

Current `LaunchScreen.storyboard` is the default Flutter splash. For App Review, replace with an Audioura-branded launch image (or use `flutter_native_splash` to generate one). Doesn't have to be fancy — just not the literal "Flutter" text.

### A31 validation

- Run `copy_ios_fixes.sh` (renamed per Goal 1) followed by `build_install_launch_a28.sh`. Build must succeed; codesign must verify; install must succeed; iPhone screen check confirms app still launches.
- Open the app on iPhone, verify backend calls work over HTTPS through the new hostname (no "could not connect" errors).
- `codesign -d --entitlements - ~/Development/AudioTours/development/audio_tour_app/build/ios/iphoneos/Runner.app` to confirm `application-identifier` and `team-identifier` are correctly populated.

### A31 pitfalls

- **Background-audio entitlement** triggers App Review questions. Be prepared to justify in the App Review notes ("audio playback continues during walking tours so users hear narration as they move between POIs").
- **ATS lock-down** will break dev workflow if a developer forgets to use the HTTPS hostname. Use a `--dart-define` to allow an HTTP override only in debug builds.
- **`flutter_launcher_icons`** sometimes doesn't regenerate cleanly. Verify the .appiconset folder contents BEFORE running A28; missing icons trigger immediate App Review rejection.

---

## Phase 2 — Privacy / Terms / store assets (Assignment 32)

**Goal:** Have all non-code submission materials ready before opening App Store Connect or Play Console.

**Time estimate:** 4–6 hours, mostly writing.

### A32 task list

**1. Privacy Policy.**

Required by both stores. Must be hosted at a public HTTPS URL.

Content needs to disclose, at minimum:
- That the app collects: device identifier (`identifierForVendor`), location (when in use), microphone audio (only when speech recognition is active), audio recordings (subscription credentials), email (if user accounts), tour requests (location + preferences sent to backend for AI generation).
- What you do with each: tour generation, personalization, analytics if any.
- Third parties: OpenAI (for tour text generation), any analytics SDK if used.
- User rights: access, deletion, opt-out.
- Children's policy: not designed for children under 13 (probably) — affects COPPA / age rating.
- Contact email.

**Easiest path:** use a free generator (termsfeed.com, freeprivacypolicy.com, iubenda free tier), customize, host as `/privacy` on the backend (`https://<hostname>/privacy`).

Amazon-Q drafts a first version that can be reviewed and refined before publishing.

**2. Terms of Service.**

Same hosting, `/terms`. Standard ToS template covering:
- Acceptable use
- Intellectual property of generated tours
- Subscription terms (auto-renew, cancellation — affects Apple's `Auto-Renewable Subscription` rules)
- Disclaimer of warranty
- Limitation of liability
- Governing law

**3. Subscription terms specifically — read Apple Guideline 3.1.1 carefully.**

CRITICAL: the new `subscription_service.dart` is the highest-risk rejection point. Apple requires that any digital content unlocked by subscription be paid for via Apple's StoreKit / In-App Purchase, with Apple taking 15-30% of the revenue. The only exception is "Reader" apps (purely external service consumed in-app) and certain enterprise apps.

**Decision needed by Sir Michael, before submission:**
- Is the Audioura subscription for AI-generated tours / cloud features that the app delivers? → Must use Apple StoreKit IAP.
- Is it a separately-purchased credential to a third-party service that the app merely displays? → May use external billing under specific Reader-app rules (rare and specific).
- Hybrid? → Probably needs StoreKit for the in-app version.

If StoreKit IAP: there's nontrivial implementation work — `in_app_purchase` Flutter plugin, server-side receipt validation, App Store Connect product configuration. That's its own assignment (probably A33 or A34 inserted before TestFlight) and easily 8-16 hours of work.

**Recommendation:** for the FIRST submission, ship without subscriptions enabled (hide the UI in release builds) so you don't tangle the IAP question with the first review. Add subscriptions in a follow-up release. This dramatically reduces first-review rejection risk.

**4. Marketing assets.**

App Store Connect requires:
- App name (30 char max): `Audioura`
- Subtitle (30 char max): suggest `AI Audio Walking Tours`
- Promotional text (170 char): one-line pitch
- Description (4000 char): full marketing copy
- Keywords (100 char, comma-separated): `audio tour, walking tour, GPS tour, AI tour, travel guide, sightseeing, audio guide, ...`
- Screenshots: 6.7" iPhone (iPhone 15 Pro Max class) at 1290×2796, ideally 5–10 screenshots; 5.5" iPhone (iPhone 8 Plus class) at 1242×2208, optional but recommended; iPad screenshots if shipping for iPad
- App preview video (optional but improves conversion)
- App Store icon: 1024×1024 PNG, no transparency, no rounded corners (Apple rounds them)
- Support URL: backend `/support` page or a static page
- Marketing URL (optional)

Play Console requires:
- App name (30 char max)
- Short description (80 char)
- Full description (4000 char)
- Screenshots: at least 2 phone screenshots (320×320 to 3840×3840, max ratio 2:1)
- Feature graphic: 1024×500 banner
- Hi-res icon: 512×512 PNG with alpha
- Optional video URL (YouTube)

Amazon-Q drafts the marketing copy + a screenshot capture script using `xcrun simctl` (iOS) and `adb shell screencap` (Android) to take consistent screenshots. Sir Michael writes the actual copy because marketing voice is human work.

**5. Age rating + content rating questionnaires.**

Both stores ask a series of yes/no questions. Audioura's answers are likely:
- No violence, no sexuality, no gambling, no profanity, no realistic violence depiction.
- May reference historical events with violence (battles, war memorials) — probably "Cartoon or Fantasy Violence: Infrequent/Mild" depending on tour content.
- User-generated content: no.
- Unrestricted web access: no (the in-app webview is for specific endpoints).
- Likely 4+ on Apple, Everyone on Google.

Amazon-Q drafts the answers; Sir Michael verifies before submitting.

### A32 validation

- `curl https://<hostname>/privacy` returns the privacy policy.
- `curl https://<hostname>/terms` returns the ToS.
- All required image assets exist in a single staging dir on `D:\Audioura\store_assets\` (new dir).

### A32 pitfalls

- **Subscription rule 3.1.1 trap.** If Audioura screens mention "Subscribe", "Premium", "Pro", anything that implies a paid tier, App Review will look closely. Either implement IAP correctly OR hide subscription UI for first submission.
- **Privacy policy must be live before submission.** Apple checks the URL during review.
- **Screenshots must reflect actual app.** Apple rejects screenshots that show features not present in the build.

---

## Phase 3 — iOS TestFlight internal testing (Assignment 33)

**Goal:** Audioura is on TestFlight, available to internal testers (Sir Michael's Apple ID + up to 99 internal testers from the Apple Developer team).

**Time estimate:** 2-4 hours first time. Subsequent uploads are 10-15 min.

### A33 task list

**1. App Store Connect setup.**

- Log in to https://appstoreconnect.apple.com.
- "My Apps" → "+" → "New App". Enter:
  - Bundle ID: `com.glikfamily.audioura` (must match `Info.plist`)
  - SKU: any unique string, e.g. `audioura-ios-1`
  - Primary language: English
  - Name: `Audioura`
- Create app record. (No review yet.)
- Fill out "App Information" tab: category (Travel; secondary Reference or Education).
- Fill out "App Privacy" section — every data type the app collects (matches the privacy policy from A32).

**2. Archive + upload from Xcode.**

The Mac Mini does this; Amazon-Q drafts the script. Roughly:

```bash
cd ~/Development/AudioTours/development/audio_tour_app
flutter build ipa --release   # produces build/ios/ipa/audio_tour_app.ipa
xcrun altool --upload-app --type ios \
    -f build/ios/ipa/*.ipa \
    -u <apple-id-email> -p <app-specific-password>
```

Note: `<app-specific-password>` is generated at appleid.apple.com under Sign-In & Security → App-Specific Passwords. NOT the Apple ID password itself. Sir Michael creates this once and stores it in the Mac keychain (or 1Password).

Alternative: use `xcrun altool` is being phased out; modern equivalent is `xcrun notarytool` for notarization but for App Store Connect upload it's `xcrun altool` or `Transporter.app` from the Mac App Store. Amazon-Q to verify which is current on Xcode 26.4.

**3. Wait for Apple processing.**

After upload, the build appears under TestFlight → "Builds" with status "Processing" for 5-30 minutes, then "Ready to Submit" for review. For INTERNAL testing only (Apple Developer team members), no review needed. For EXTERNAL testers (next phase), a brief review is required.

**4. Internal testing setup.**

- TestFlight → Internal Testing → add Sir Michael's Apple ID as a tester.
- Install TestFlight app on iPhone 16. Accept the invite. Install build.
- Verify it runs identically to direct-install build.

### A33 validation

- Build appears in App Store Connect with status "Ready to Submit" within 1 hour of upload.
- TestFlight install on iPhone 16 produces an identical experience to the direct-installed A28 build.
- Backend HTTPS calls work from the TestFlight build.

### A33 pitfalls

- **Build number must increment.** Apple rejects re-uploads of the same `CFBundleVersion`. Each upload bumps `pubspec.yaml`'s `+25` to `+26`, etc.
- **Encryption export compliance.** The first TestFlight build will prompt for encryption answers if `ITSAppUsesNonExemptEncryption` isn't set in Info.plist (added in A31). Should be a no-op if A31 done correctly.
- **App-specific password expiration.** Apple's app-specific passwords don't expire automatically but get invalidated if the Apple ID password changes. Re-generate as needed.
- **Beta App Description.** Apple requires a beta app description for TestFlight (~250 char) — write it as part of A32.

---

## Phase 4 — Android Play Console internal testing (Assignment 34)

**Goal:** Audioura is in the Play Console "Internal Testing" track.

**Time estimate:** 2-3 hours first time.

### A34 task list

**1. Play Console signup.**

- Go to https://play.google.com/console.
- Pay one-time $25 registration fee.
- Verify identity (Google sometimes asks for ID).

**2. Create app record.**

- "Create app" → fill out:
  - App name: `Audioura`
  - Default language: English (United States)
  - App or game: App
  - Free or paid: Free (you charge later via subscription if you do)
  - Declarations: Developer Program Policies + US export laws
- Complete the "Set up your app" onboarding tasks: app access, ads declaration, content rating, target audience, news app declaration (no), data safety, app category, store listing.

**3. Build signed Android App Bundle (.aab).**

```bash
cd ~/Development/AudioTours/development/audio_tour_app   # On the Windows side or Mac, doesn't matter
flutter build appbundle --release
# Output: build/app/outputs/bundle/release/app-release.aab
```

For signing, Android requires a Java keystore. Steps:
- Generate keystore once (back this up — losing it = losing the ability to update the app):
  ```bash
  keytool -genkey -v -keystore audioura-release.keystore -alias audioura \
      -keyalg RSA -keysize 2048 -validity 10000
  ```
- Add `android/key.properties` (gitignored):
  ```
  storePassword=<password>
  keyPassword=<password>
  keyAlias=audioura
  storeFile=/absolute/path/to/audioura-release.keystore
  ```
- Update `android/app/build.gradle` to use the signing config (Flutter docs have the canonical snippet).

**4. Internal Testing track upload.**

- Play Console → Testing → Internal testing → "Create new release".
- Upload the .aab.
- Add release notes.
- "Internal Testing → Testers" → add tester emails (these are Google accounts that get a Play Store opt-in link).
- Save → Review release → Roll out to internal testing.

### A34 validation

- The .aab is signed with the keystore (verify via `bundletool` or `apksigner`).
- Internal testing track is live; tester emails receive opt-in invite.
- App installs from Play Store on a physical Android device and runs identically to debug build.

### A34 pitfalls

- **KEYSTORE LOSS = APP DEATH.** Back up `audioura-release.keystore` to multiple secure locations immediately. If lost, you cannot update the app on Play Store ever. (Google has Play App Signing which mitigates this somewhat — opt in during first upload.)
- **`targetSdkVersion`** has Google deadlines. As of mid-2025, target API 34 minimum. Verify `android/app/build.gradle` is at least at the current minimum.
- **Data Safety form** is required and detailed. Plan ~30 min to fill out accurately. Use the privacy policy from A32 as the source of truth.

---

## Phase 5 — External TestFlight + Play closed testing (Assignment 35)

**Goal:** 5–20 friends/family install Audioura on their own iPhones / Androids and use it for real. Real bugs surface here.

**Time estimate:** Submission setup is 1-2 hours. Testing window is 2-4 weeks.

### A35 task list

**iOS — External TestFlight.**

- App Store Connect → TestFlight → External Testing → Create a public link OR add specific email addresses.
- "Submit for Beta Review" — Apple does a brief review (24-72 hours typical).
- After approval, share the public link or wait for invitees to accept email invites.
- Up to 10,000 external testers per app.

**Android — Play Console Closed Testing.**

- Play Console → Testing → Closed Testing → "Manage track" → Create new track or use the default.
- Add tester emails or a Google Group.
- Upload a .aab (likely the same one from A34, or a newer build).
- Review release → Roll out.
- No Google review needed for closed testing — testers can install immediately.

### A35 validation

- 5+ testers receive invites and successfully install on their personal devices.
- Crash reports come back through TestFlight (Apple) and Play Console Vitals (Google).
- Direct feedback collection: a Google Form linked from inside the app, or a simple email collector.

### A35 pitfalls

- **External TestFlight beta review** can be rejected for the same reasons as full App Review. Plan one rejection cycle.
- **Tester expectation management.** Tell testers explicitly: this is beta, expect bugs, here's how to report them. Otherwise you get vague "it didn't work" reports that you can't act on.
- **Build expiration.** TestFlight builds expire after 90 days. If your beta runs longer, upload new builds.

---

## Phase 6 — Production submission (Assignment 36)

**Goal:** Audioura is live on the App Store and Play Store, publicly downloadable.

**Time estimate:** Submission is 30 minutes. Apple review is 24-72 hours typical, longer if rejected. Plan 1-2 weeks total for first iOS public release.

### A36 task list

**iOS — App Store submission.**

- App Store Connect → App Store tab → "+ Version" → fill out new version metadata (description, what's new in this version, screenshots, etc.).
- Add the build from TestFlight ("Build" section → select the latest TestFlight build).
- "Submit for Review" → answer the export compliance + content rights + advertising identifier questions.
- Wait for Apple review.

**Android — Play Console production submission.**

- Play Console → Production → "Create new release".
- Promote the closed-testing build to production.
- Set rollout percentage (start with 20% staged rollout to catch issues early).
- Review release → Roll out.
- Google review is automated and usually completes in hours, sometimes days.

### Common Apple rejection reasons (plan for at least one)

- App crashes on Apple's review device. (Mitigated by TestFlight testing on multiple iOS versions / device classes.)
- Broken core functionality (Apple reviewer can't generate a tour because the backend is down or returned an error).
- Missing or inaccurate privacy policy.
- Subscription rule 3.1.1 violation (covered in A32 — hide subscription if not using StoreKit).
- Vague app description that doesn't accurately describe the app.
- Demo account credentials missing for review (Apple needs to log in as a test user — provide an account in the "App Review Information" section).
- Background audio without justification (already covered in A31).

### Common Google rejection reasons (less common than Apple)

- Misleading screenshots.
- Permission usage not explained in description (e.g. location permission without clear reason).
- Data Safety form mismatches actual app behavior.
- Target API level too low.

### A36 validation

- Both stores show the app as "Available" in their respective regions.
- Direct App Store / Play Store URLs work and lead to the app listing.
- A non-developer can search for "Audioura" and find + install the app.

---

## Cost summary

| Item | One-time | Monthly |
|---|---|---|
| Apple Developer Program | $99/year (paid) | — |
| Google Play Console | $25 | — |
| Custom domain (recommended) | $10-15/year | — |
| Backend hosting (Phase 0 Option A — Cloudflare Tunnel) | $0 | $0 |
| Backend hosting (Phase 0 Option B — VPS) | $0 | $4-6 |
| Privacy policy generator (free tier) | $0 | $0 |
| **TOTAL TO LAUNCH** | **~$25-40** | **$0-6** |

If you go with AWS later: defer that decision per the project log review of `AUDIOURA_DEPLOYMENT_STRATEGY.md`.

---

## Timeline summary

| Phase | Duration | Calendar week |
|---|---|---|
| Phase 0 — backend HTTPS | 0.5–4 hours | Week 1 day 1 |
| Phase 1 — A31 Bundle/ATS | 1–2 hours + A28 cycle | Week 1 day 1-2 |
| Phase 2 — A32 Privacy/assets | 4–6 hours | Week 1 day 3-5 |
| Phase 3 — A33 TestFlight internal | 2–4 hours | Week 2 day 1 |
| Phase 4 — A34 Play internal | 2–3 hours | Week 2 day 2 |
| Phase 5 — A35 External testing | 2 weeks running | Weeks 3-5 |
| Phase 6 — A36 Production | 30 min + 1-2 wk review | Weeks 6-8 |

Critical path is Apple review iteration. Plan optimistically for 6 weeks total, realistically for 8.

---

## Working agreement for these assignments

- **Amazon-Q drafts the per-phase scripts** (`copy_ios_fixes.sh` updates, App Store Connect navigation walkthroughs, Play Console walkthroughs, signing key generation scripts, build/upload scripts).
- **Claude reviews each before USB transfer** (V2 lesson — review-before-execute discipline).
- **Sir Michael executes on the Mac Mini** for iOS work; **on the Windows laptop** for Android work + web admin (App Store Connect / Play Console).
- **All result files land in `D:\Audioura\results\`** with timestamped filenames per established convention.
- **Project log gets updated** at the end of each phase (`C:\Business\AudioTours.io\Claude\Audioura development\Audioura_project_log.md`).

---

## Risks worth naming explicitly

1. **Subscription/IAP rule 3.1.1.** Highest single rejection-risk factor. Strong recommendation: hide subscription UI for first release.
2. **Apple review iteration.** 6-week-best-case assumes one clean review pass. Two rejections = 8-9 weeks. Three = 10+. Real-world rate is "second submission usually approved" but plan accordingly.
3. **Backend uptime during App Review.** If Apple's reviewer hits the backend during the 24-72h review window and gets a 500, rejection. Phase 0's backend HOST (laptop or VPS) must be reliable for that window. This argues for VPS over laptop for the actual review submission, even if Cloudflare Tunnel suffices for general external testing.
4. **Encryption export compliance ambiguity.** If the encryption usage is borderline non-exempt, get the answer right — wrong answers can trigger Apple to flag the developer account.
5. **Keystore loss (Android).** Losing `audioura-release.keystore` after first Play Store publish = cannot update app forever. Back up immediately to 3 places.
6. **First public release is irreversible-ish.** Once Audioura is on the public App Store, the bundle ID is committed; major rebrand later is painful. Confirm "Audioura" is the final name before A36.

---

**Last Updated:** 2026-05-01 by Claude (session "Audioura Build and Start #4")
**Status:** SPEC ready for Amazon-Q to draft phase-by-phase scripts/assignments.
**Next step:** Amazon-Q drafts A31 (bundle + ATS + Info.plist cleanup); Claude reviews; Sir Michael executes once Phase 0 backend HTTPS is in place.
