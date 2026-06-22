# Google Play Console Setup: Answers & Rationale (CORRECTED 2026-06-21)

**Project:** Audioura (com.audioura.audiotours) · **Entity:** Audioura LLC
**Status:** Corrected by Claude review. Earlier draft mis-declared target audience and data collection — fixed below.
**Governing rule:** every answer must match the app's real behavior and the privacy policy at `https://audioura.com/privacy`.

> ⚠️ Audioura is **NOT** a children's app. It collects **precise location** + a **device identifier** + (optional) **subscription credentials** — so it must be declared as a **13+** app with accurate data disclosure. Declaring "all ages / collects nothing" fails review.

---

## Task 1: Target Audience  ✅ CORRECTED

**Question:** What are the target age groups of your app?

**Correct answer — select ONLY:**
- ☑️ 13–15
- ☑️ 16–17
- ☑️ 18 and over
- ☐ 5 and under — **UNCHECK**
- ☐ 6–8 — **UNCHECK**
- ☐ 9–12 — **UNCHECK**

**"Does your app appeal to children?"** → **No.**
**Do NOT** opt into the Families/Designed-for-Families program. **Do NOT** certify the app as child-directed.

**Rationale:**
1. The privacy policy (§5) states Audioura is **not directed to children under 13**. The audience selection must match.
2. The app collects **precise GPS** and a **persistent device identifier** — both are **restricted for children** under Google's Families Policy. A child-targeted app collecting these **fails** review.
3. Certifying COPPA/Families compliance while collecting precise location + device id from kids would be a **false certification.** Targeting 13+ avoids this entirely.

---

## Task 2: Data Safety  ✅ CORRECTED — answer from the mapping doc

Answer the Data Safety form directly from **`AUDIOURA_DATA_SAFETY_MAPPING.md`** (it's reconciled with the privacy policy). Summary:

**Collected (= Yes), none Shared, all encrypted in transit:**
- **Location → Precise location** — GPS sent to server for tours/Treats; stored. Optional.
- **Device or other IDs** — the `USER-<hash>` device identifier; saves tours + enforces quotas. Required.
- **App info & performance → Crash logs + Diagnostics** — per privacy policy §1.
- **App activity → In-app search history + App interactions** — voice/text search, tour requests, listening.
- **Personal info → Other info** — optional third-party **subscription credentials** (username/password) when a user connects a paid news source.

**Not collected:** Name/Email (no accounts), Financial, Health, Messages, Photos/Videos, **Audio** (on-device transcription — raw audio never leaves the device), Files, Calendar, Contacts.

**Other Data-Safety answers:** Encrypted in transit → **Yes**. Provide a way to request data deletion → **Yes** (in-app About → Delete My Account + contact on the privacy page). Independent security review → **No**.

*(The earlier draft's "no device identifiers / location not stored / no personal info" was wrong and contradicted the privacy policy.)*

---

## Task 3: Government Apps  ✅ (unchanged — correct)
**Answer: No.** Audioura LLC is a private company; not a government service.

## Task 4: Financial Features  ✅ (correct for MVP)
**Answer: No.** Free at launch; no IAP, no payments, no banking/investment.
*Note: revisit when v2.3 subscriptions launch — in-app subscriptions are a monetization/financial feature and may change this.*

## Task 5: Health  ✅ (unchanged — correct)
**Answer: No.** Travel/audio-tour app; no fitness, medical, or health data.

## Task 6: App Category & Contact Details
| Field | Value | Note |
|---|---|---|
| Category | **Travel & Local** (primary) | Core function = location-based audio tours |
| App name | Audioura | |
| Support email | **info@audioura.com** | ⚠️ Verify this mailbox is real + monitored (the policy contact was a gmail; `www` DNS is currently broken) |
| Support website | **https://audioura.com** | Use the no-`www` URL (the `www` host doesn't resolve yet) |
| Privacy policy | **https://audioura.com/privacy** | Live ✅ |

## Task 7: Store Listing
App name **Audioura**; short description e.g. *"AI audio tours + audio news for any place"* (include the **Audio/news mode** — it's half the app, omitted in the earlier draft). Full description, screenshots (Mobile/Mac-Mini), icon 512×512, feature graphic 1024×500. Copy/assets in the **Beta Launch Kit** doc.

---

## Compliance status (corrected)
| Item | Status |
|---|---|
| Target audience | **13+** (NOT all-ages / NOT Families) |
| Data Safety | Location, Device ID, Crash logs, Diagnostics, App activity, Subscription creds = collected; none shared |
| COPPA / Families Policy | **N/A** — app is not child-directed (this is the correct posture) |
| Ads | No for Beta (Treats off); becomes Yes when paid placement ships |
| Financial / Health / Government | No |

**Fix order in Console:** Target Audience (#1) → Data Safety (#2) → confirm the rest. Keep every answer consistent with the privacy policy.
