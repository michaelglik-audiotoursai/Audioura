# Play Release Notes — Audioura v2.1.1 (build 18)

**Track:** Closed testing
**Bundle:** `audioura-release.aab` (27.4 MB)
**Package:** com.audioura.audiotours

---

## Paste-ready (English) — for the Play Console "Release notes" box

Play wraps notes in a language tag. Paste this exactly (it's well under Play's 500-character limit):

```
<en-US>
Welcome to the Audioura beta! Thanks for testing.

Audioura turns any place into a guided audio tour, and turns the news into an audio briefing you can listen to hands-free.

This build:
- Generate AI audio tours for anywhere, in multiple languages
- Audio news mode: listen to articles and newsletters
- Browse and play nearby community tours on the map
- More reliable downloads and translations
- Clearer messages when a translated tour isn't available

Please send feedback to info@audioura.com.
</en-US>
```

---

## Shorter alternative (if you prefer something minimal)

```
<en-US>
Audioura beta — thanks for testing! Create AI audio tours for any place, or listen to the news as an audio briefing. This build improves download and translation reliability and adds clearer in-app messages. Feedback: info@audioura.com
</en-US>
```

---

## Internal change summary (NOT for the store — your reference only)

What actually changed since the last internal build:

- **Translation now works for older / R2-stored tours.** Tours whose audio lives in blob storage (database `audio_tour` column NULL, `tour_blob_uri` set) can now be translated — the translation service fetches the ZIP from R2 using the shared storage helper. (Tour 79 → Russian/Chinese verified.)
- **Clearer translation-failure UX.** When a translation genuinely isn't available, the app now shows a modal "Translation Not Available" dialog instead of a transient snackbar people were missing — it no longer silently plays English without explanation.
- **Auth / gateway reliability.** All cloud calls carry the API key (fixed the keyless `/tours-near`, `/download-tour`, `/search-tours`, and `PUT /user` calls that 401'd on the locked gateway); the gateway is fully locked (every route key-gated).
- **App icon** now renders with the brick-orange (#A93105) background instead of white.
- **"Report this tour" email** fixed on Android 11+ and points to info@audioura.com.
- First **Play-signed App Bundle** (release keystore, applicationId `com.audioura.audiotours`).
