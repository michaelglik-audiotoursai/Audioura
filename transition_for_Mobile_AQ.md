# Transition Brief — Mobile Amazon-Q (📱)

**Date:** 2026-05-28. Supersedes any prior version (lost during A#74 cleanup).
**Audience:** 📱 MOBILE APP AMAZON-Q.
**Status of your `remind_mobile_ai.md`:** untouched. You own it.

iOS is at v1.2.9+65 (A#75 shipped). **Android is at v1.2.9+61** — three versions behind. Your first immediate task is the Android rebuild catch-up. After that, you wait alongside iOS Q for Services Q's PreProd URL.

---

## Immediate: catch Android up to v1.2.9+65

The Android binary missed A#72 (news article path healing), A#73 (brick-red icon), and A#75 (InAppWebView v6 migration). The Dart code is the same as iOS — no Android-specific code changes needed beyond a clean rebuild.

```bash
# On your Ubuntu VM
cd ~/Audioura-build
git pull origin Newsletters
bash build_flutter_clean.sh
```

After build success: install on a test Android device, smoke-test:
- Tours mode: a saved tour plays without white screen.
- Audio mode: a news article opens without white screen.
- App icon shows brick-red `#A93105` background on home screen.

If smoke passes, this brings Android current. No git changes needed — same code, just compiled.

---

## Layer 1 — Universal Services Locations (Android side)

Same problem as iOS: ~37 hardcoded `192.168.0.x` references in shared Dart code, plus `audio_tour_app/.env`. iOS Q is designing `lib/config/api_config.dart` as the single source of truth. **You don't re-design this — you adopt it.**

Your Android-specific work:

1. **`AndroidManifest.xml` cleanup** (`audio_tour_app/android/app/src/main/AndroidManifest.xml`):
   - Add `android:usesCleartextTraffic="false"` to `<application>` once HTTPS-only.
   - Verify `<uses-permission android:name="android.permission.INTERNET"/>` is present.
   - Add `network_security_config.xml` only if Services Q requires certificate pinning.

2. **Per-environment builds** matching iOS:
   - `flutter build appbundle --release --dart-define=AUDIOURA_ENV=preprod` for PreProd testing.
   - `flutter build appbundle --release --dart-define=AUDIOURA_ENV=prod` for store upload.

3. **Test on real Android device + emulator** after the URL switch lands. Different network stack characteristics than iOS — different failure modes possible.

**Gate:** all of Layer 1 is gated on Services Q's M04 PreProd URL.

---

## Layer 2 — Google Play Store Phase 4 (Internal Testing)

**Spec:** `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`. You own Phase 4 (called A34 in the doc).

### Your work, in order, once the URL switch is done

1. **Play Console signup** — Sir Michael does it ($25 one-time fee). Use the Audioura LLC business account. You walk him through fields if needed.

2. **Create app record** in Play Console with `Audioura` naming.

3. **Build signed AAB.**
   - `flutter build appbundle --release --dart-define=AUDIOURA_ENV=prod`.
   - **Keystore is a one-time event.** Generate via `keytool` if not yet done.
   - **CRITICAL: back up the keystore to 3 places immediately** before any upload. Loss of the keystore = inability to ever update the app on Play Store. Google does NOT keep a copy.
   - Enable Google Play App Signing as an additional backup layer.

4. **Upload to Internal Testing track.** Sir Michael adds his own Google account as internal tester.

5. **Data Safety form** — the Android equivalent of Apple's privacy labels. Must accurately reflect actual behaviour:
   - Device identifiers: yes (analytics).
   - Location: yes (tour recommendations, POI delivery).
   - Microphone audio: yes (voice control).
   - Audio recordings: yes (saved tour playback).
   - Third-party data processors: OpenAI, AWS Polly.
   **Misrepresenting this form is the top Play Console rejection reason.** Over-disclose, don't under-disclose.

6. **`targetSdkVersion` check.** Google's minimum target SDK refreshes annually. Check current `android/app/build.gradle` against Google's current requirement; bump if needed.

7. **Content rating questionnaire** via IARC — likely **Everyone**. Walk Sir Michael through.

---

## Pitfalls

- **Keystore loss = app death on Play Store, forever.** Triple-back-up before first upload.
- **Data Safety form mismatches.** If the app sends device IDs to OpenAI during tour generation, that's in the form. Don't gloss.
- **`targetSdkVersion` lag.** Google's deadline for the current SDK target moves every August. Check before each submission.

---

## What's NOT your scope

- Phase 1 (iOS Info.plist) — iOS Q.
- Phase 2 (privacy/terms) — Sir Michael writes, Advisor Q reviews.
- Phase 3 (TestFlight) — Mac Mini Kiro CLI.
- Phase 6 (production submission button click) — Sir Michael.

---

## Subscription rule — same as iOS

First Play Store release ships WITHOUT in-app subscriptions. Google has equivalent IAP rules. RevenueCat lands in v1.3 post-launch.

---

## Where this doc lives

`C:\Users\micha\eclipse-workspace\AudioTours\development\transition_for_Mobile_AQ.md`. Git-tracked.
