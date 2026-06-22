# Audioura — Google Play Data Safety Form: Field-by-Field Mapping (2026-06-21)

Form-ready answers for the Data Safety section, correlated to what the app actually does and to the published privacy policy (`https://audioura.com/privacy`).

## Two rules that govern every answer
1. **The form must match the privacy policy.** Google compares them. Your policy discloses **location, microphone, device identifier, subscription credentials, and diagnostics** — so the form must declare those. (This is why "collect NONE" is wrong and would get the app flagged.)
2. **Service providers ≠ "sharing."** Google Cloud, OpenAI, Amazon Polly, and crash reporting process data **on your behalf** (per privacy-policy §3). That counts as **"collected," NOT "shared."** So across the whole form: **Collected = Yes where applicable; Shared = No** everywhere.

---

## Data types — what to select

| Google category → subtype | Collect? | Why (Audioura behavior) | Collected/Shared | Ephemeral? | Required/Optional | Purpose |
|---|---|---|---|---|---|---|
| **Location → Precise location** | ✅ **YES** | App reads GPS (`Geolocator.getCurrentPosition()`) and sends lat/lng to the server (stored in `coordinates`/`map_requests`) to generate location tours, place map pins, show Treats. | Collected, not shared | No (stored) | **Optional** (only when you request a location tour or open Treats) | App functionality |
| **Personal info → Other info** (third-party subscription credentials) | ✅ **YES** | *Only if* a user connects a paid news subscription: the publisher **username + password** are sent to the server and stored to log in on the user's behalf. Username may be an email. | Collected, not shared | No (stored) | **Optional** | App functionality |
| **App activity → In-app search history** | ✅ **YES** | Voice/text search queries (the recognized command/search string, e.g. tour/news searches) are sent to the server. | Collected, not shared | No | Optional | App functionality, Analytics |
| **App activity → App interactions** | ✅ **YES** | Tour-generation requests and tour/news listening activity are tracked (tied to the device id). | Collected, not shared | No | Required | App functionality, Analytics |
| **App info and performance → Crash logs** | ✅ **YES** | Crash logs collected to diagnose crashes (policy §1). | Collected, not shared | No | Required | Analytics / app stability |
| **App info and performance → Diagnostics** | ✅ **YES** | Basic usage/diagnostics for reliability (policy §1). | Collected, not shared | No | Required | Analytics / app stability |
| **Device or other IDs → Device or other IDs** | ✅ **YES** | The device-derived identifier (`USER-<hash>`) identifies the install, saves tours, and enforces fair-use quotas. | Collected, not shared | No (stored) | Required (automatic) | App functionality, Fraud prevention/security |

### Select **NO** for all of these
- **Location → Approximate location** — only precise GPS is used (declare Precise; you may add Approximate if you ever downgrade, but Precise is the honest one).
- **Personal info →** Name, Email address (as an account), User IDs, Address, Phone number, Race/ethnicity, Political/religious beliefs, Sexual orientation — **No.** (No accounts; no email/name/password to use the app.)
- **Financial info** (all) — No. App is free; no payments collected.
- **Health and fitness** — No.
- **Messages** (Emails, SMS, in-app) — No messaging features.
- **Photos and videos** — No. Users don't upload media.
- **Audio files → Voice or sound recordings** — **No.** Voice uses **on-device speech-to-text** (`speech_to_text` package); the **raw audio is transcribed on the device and never transmitted** — only the resulting text command leaves the device (declared above under search history). The microphone permission is used, but audio data is not *collected*.
- **Audio files →** Music files, Other audio files — No.
- **Files and docs** — No uploads.
- **Calendar** — No.
- **Contacts** — No.
- **App activity →** Installed apps, Other user-generated content, Web browsing history — No.

---

## Notes on the two judgment calls

**Subscription credentials (the publisher username/password).** There's no perfect Google bucket for "third-party login credentials." Declaring them under **Personal info → Other info** as *collected, optional, not shared* is the honest, defensible choice — your privacy policy already discloses this, so omitting it from the form would be the inconsistency that gets flagged. (Do **not** mark it "shared": you use it only to log into the publisher *on the user's behalf*, which is functionality, not sharing.)

**Voice/audio.** The conclusion "no audio" is correct, but the reason is on-device transcription, not "tours aren't stored." Don't check "Voice or sound recordings."

---

## The other Data Safety questions (same section)

- **Is all of the user data collected encrypted in transit?** → **Yes** (HTTPS to api.audioura.com; credentials additionally encrypted before transit).
- **Do you provide a way for users to request that their data is deleted?** → **Yes.** In-app **About → Delete My Account** (calls the server's full-erase endpoint), and users can also request via the contact on `https://audioura.com/privacy`.
- **Has your app been independently security-reviewed (e.g., against MASVS)?** → **No** (optional; leave unchecked unless you've had a formal third-party audit).

---

## Detail-screen answers — recorded as entered in Console (2026-06-21)

For each data type, the four follow-up questions and the reasoning. ✅ = entered in Console; ⬜ = to enter. Shared = **No** for every type (service providers ≠ sharing; user-initiated logins are exempt).

### Personal info → Other info  (= third-party subscription credentials) ✅
- **Collected** (not Shared) · **Ephemeral: No** (stored, encrypted at rest) · **Optional** (only if a user connects a paid subscription) · **Purpose: App functionality** only.
- Why: used solely to log into the publisher on the user's behalf and fetch requested content (policy §1/§3). Not "Account management" — that's for *your* app's accounts; these are a third party's.

### Location → Precise location ✅
- **Collected** (not Shared) · **Ephemeral: No** (stored in `coordinates`/`map_requests`) · **Optional** (only when requesting a location tour or opening Treats; permission can be denied) · **Purpose: App functionality** only.
- Caveat: add **Advertising or marketing** as a purpose only if/when Treats **paid** offers go live. Treats is gated off in cloud mode for the Beta, so App functionality only for now.

### Device or other IDs ✅
- **Collected** (not Shared) · **Ephemeral: No** (the `USER-<hash>` persists; saved with tours + quota counters) · **Required** ("Users can't turn off this data collection" — generated automatically) · **Purpose: App functionality** + **Fraud prevention, security, and compliance** (enforces fair-use quotas / abuse prevention).

### App activity → In-app search history ✅
- **Collected** (not Shared) · **Ephemeral: No** · **Optional** ("Users can choose whether this data is collected" — only when the user searches by voice/text) · **Purpose: App functionality** (+ Analytics if used to improve results).

### App activity → App interactions ✅
- **Collected** (not Shared) · **Ephemeral: No** · **Required** ("Users can't turn off this data collection" — tour requests + listening are inherent to using the app, no opt-out) · **Purpose: App functionality** + **Analytics**.

### App info & performance → Crash logs ✅
- **Collected** (not Shared) · **Ephemeral: No** · **Required** (automatic) · **Purpose: Analytics** (app stability/diagnostics).

### App info & performance → Diagnostics ✅
- Same as Crash logs: **Collected / Not ephemeral / Required / Analytics.**

> Rule of thumb that produced the above: *Collected* (it leaves the device), *not Shared* (providers act on our behalf), *not Ephemeral* (we store it), *Optional* unless the app can't run without it (device id, basic interactions, crash logs = Required; everything user-triggered = Optional), and *App functionality* as the purpose unless it's quotas/abuse (Fraud prevention) or stability (Analytics).

## Why "select NONE" was wrong
Whoever drafted that missed three things your **own privacy policy** already commits you to: (1) **location** is read from GPS and sent to the server — not manually typed; (2) the **device identifier** is collected (it wasn't even in the list); and (3) **crash logs/diagnostics** are collected. Declaring "nothing" against a policy that discloses those is the exact mismatch Google rejects for. The mapping above keeps the form and the policy consistent.

---

## AS SUBMITTED — full App content + Store settings (verified in Console 2026-06-22)

Snapshot of every answer as actually entered in Play Console, so it can be recalled and kept consistent across resubmissions.

### Data safety — Store-listing preview confirmed
- **Data shared with third parties:** None. ✅
- **Data collected** (all *Collected, not Shared, not Ephemeral, encrypted in transit*):
  - Personal info → **Other info** (subscription creds) — Optional — App functionality
  - Location → **Precise location** — Optional — App functionality
  - App info & performance → **Crash logs** — Required — Analytics
  - App info & performance → **Diagnostics** — Required — Analytics
  - App activity → **App interactions** — **Required** ("users can't turn off") — App functionality + Analytics
  - App activity → **In-app search history** — Optional — App functionality
  - **Device or other IDs** — **Required** ("users can't turn off") — App functionality + Fraud prevention/security
- **Encrypted in transit:** Yes. **Data deletion path:** Yes — in-app Delete My Account + request via `https://audioura.com/privacy`. **Independent security review:** No.
- **Privacy policy URL:** `https://audioura.com/privacy` (no-www; the only host that resolves).

### Other App content declarations
- **Target audience:** 13+ (13–15, 16–17, 18+). NOT child-directed; NOT Families program.
- **Ads:** No, app does not contain ads (Treats gated off in cloud — flip to Yes when paid placement ships).
- **Financial features:** No — "My app doesn't provide any financial features."
- **Health features:** No — "My app doesn't provide any health features."
- **Government apps:** No.
- **Advertising ID:** No (app does not use an advertising ID).

### Store settings (Grow users → Store presence → Store settings)
- **App or game:** App. **Category:** Travel & Local.
- **Tags:** Maps & navigation, News & magazines, News aggregator, Travel & local, Travel guide.
- **Contact email:** info@audioura.com *(verify mailbox is live + monitored)*.
- **Website:** `https://audioura.com` (no-www). **Phone:** +1 617 744 9562.
- **External marketing:** ON ("Advertise my app outside of Google Play") — benign; lets Google promote the app. (Changes take up to 60 days.)

> Consistency check passed: target audience (13+), Data Safety (location + device id + creds collected), privacy policy, and category/tags all agree. No child-directed flags anywhere alongside precise-location/device-id collection.
