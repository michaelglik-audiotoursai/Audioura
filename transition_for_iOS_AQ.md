# Transition Brief — iOS Amazon-Q (🍎)

**Date:** 2026-05-28. Supersedes any prior version (lost during A#74 cleanup).
**Audience:** 🍎 iOS AMAZON-Q.
**Status of your `remind_ios_ai.md`:** untouched. You own it.

A#74 and A#75 are done. iPhone runs v1.2.9+65 with the InAppWebView v6 migration complete. **You are now in waiting mode for the most disruptive change** until Services Q delivers a public HTTPS PreProd URL. Once they do, your work has two layers: replace the LAN URLs, then prep for App Store submission.

---

## Layer 1 — Universal Services Locations (the mobile-app side)

Currently the app has **~37 hardcoded `192.168.0.x` references across ~21 Dart files** plus `audio_tour_app/.env` `API_BASE_URL=http://192.168.0.217:5002`. These all point at Sir Michael's laptop. Apple's review devices can't reach his laptop, so this must be replaced before App Store submission.

### Your steps when Services Q delivers the PreProd URL

1. **Audit.** Produce a complete table of every hardcoded `192.168.x.x` reference. For each: file path, line, port, which service it talks to, the call-site context. **Do not skip files; do not partial-sweep.** Output as a Markdown table in a code-review doc.

2. **Design `lib/config/api_config.dart`.** A single module that:
   - Reads `--dart-define=AUDIOURA_ENV` at build time (values: `dev`, `preprod`, `prod`).
   - Returns the right base URL for each named service from a `const` map keyed by env.
   - Falls back to `dev` if the dart-define is missing (so existing dev workflow keeps working).
   - Is the **only** place in the app that resolves a service URL. No other file should construct one.

3. **Apply.** Replace every audited reference with a call into `ApiConfig.<serviceName>`. Single PR/commit. Claude IO drafts the corresponding Mac Mini Kiro CLI build assignment.

4. **WAN robustness.** Currently most network code assumes LAN-speed, always-reachable. Add:
   - Exponential backoff retries on transient 5xx and network errors (max 2-3 retries).
   - User-facing error UI when retries exhaust.
   - Sensible timeouts (don't hang indefinitely).
   - HTTPS-only certificate validation.

5. **Authentication.** Services Q decides the auth model (API key in headers / OAuth / signed requests). You implement the client side once they specify.

6. **Verify offline behaviour still works.** Tours mode caches generated tour content locally; Audio mode caches news articles. These should keep working when the network is unreachable. After the URL switch, smoke-test offline scenarios.

**Gate:** you cannot start steps 1-6 until Services Q delivers a stable PreProd HTTPS URL (their Phase D / M04). Until then, this is paper planning only.

---

## Layer 2 — Apple App Store Phase 1 (Bundle / ATS / Info.plist)

**Spec:** `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md` — 6 phases. You own work in Phase 1 (called A31 in the doc).

### Your Phase 1 work

1. **`Info.plist` cleanup** in `audio_tour_app/ios/Runner/Info.plist`:
   - Confirm `CFBundleName = Audioura` and `CFBundleDisplayName = Audioura` (already done in A#71).
   - Add `NSAppTransportSecurity` block with `NSAllowsArbitraryLoads = false`. **This locks ATS** — only HTTPS allowed. Coordinate with Layer 1: this lockdown happens at the same time as the URL replacement.
   - Confirm `UIBackgroundModes` array contains `audio`.
   - Review microphone, speech-recognition, location usage description strings for reviewer-friendly clarity.
   - Set `ITSAppUsesNonExemptEncryption = false` after auditing actual crypto use.

2. **Crypto audit.** Review `audio_tour_app/lib/services/` for any crypto use beyond the credential auth path. If anything else uses encryption (e.g., for stored data), the `ITSAppUsesNonExemptEncryption = false` decision must be revisited.

3. **Launch screen.** Replace the default Flutter splash with an Audioura-branded launch image. Spec the image; Sir Michael provides it; you wire it into `LaunchScreen.storyboard`.

4. **App icon set.** Already done in A#73 (`#A93105` brick-red background). Verify nothing slipped — `Icon-App-1024x1024@1x.png` is 1024×1024 RGB (no alpha).

### Not your scope in Layer 2

- Phase 2 (privacy/terms/screenshots) — Sir Michael writes copy, Advisor Q reviews.
- Phase 3 (TestFlight) — Mac Mini Kiro CLI archives + uploads.
- Phase 4 (Play Console) — Mobile Q.
- Phase 5 (external testing) — everyone.
- Phase 6 (production submission) — Sir Michael clicks submit.

---

## Subscription rule 3.1.1 — keep in mind

First store release ships **WITHOUT** in-app subscriptions. RevenueCat lands in v1.3 post-launch. Apple Guideline 3.1.1 is the #1 rejection trigger for paid apps. If you see subscription-related code in dead/orphan files (`subscription_management_screen.dart`, etc.), confirm it's not reachable from any live UI flow before App Store submission.

---

## Where this doc lives

`C:\Users\micha\eclipse-workspace\AudioTours\development\transition_for_iOS_AQ.md`. Git-tracked. Sir Michael relays it; you read it for context.
