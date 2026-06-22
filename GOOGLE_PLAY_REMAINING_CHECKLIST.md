# Audioura — Google Play: Remaining Steps to Beta Release (2026-06-22)

App is in **Draft** (com.audioura.audiotours, org account 6479034412302847455). Below is everything still open, grouped by whether it needs the Android build or not. Open the app **Dashboard** for Google's own live checklist.

---

## A. Can do NOW (no build needed)

### A1. Finish "App content" declarations
Path: **Policy and programs → App content**. Confirm nothing says "Need attention."

- [x] Data safety — done (App interactions + Device IDs set to Required; preview confirmed)
- [x] Target audience — 13+ (not child-directed)
- [x] Ads — No
- [x] Financial features — No
- [x] Health features — No
- [ ] **Government apps — No** (confirm submitted)
- [ ] **Advertising ID — No** (app doesn't use an ad ID; confirm submitted)
- [ ] **News apps** declaration — answer if shown (Audio mode reads news; answer accurately if Google asks whether it's a news app — "No, not primarily a news publisher" is defensible since tours are primary)
- [ ] **Content ratings** — complete/confirm the IARC questionnaire (expected Everyone/4+); ensure the UGC "users interact/exchange content" answer matches the report-content decision
- [ ] **Privacy policy URL** present: `https://audioura.com/privacy`

### A2. Store listing (Grow users → Store presence → Store listings)
- [ ] App name: **Audioura**
- [ ] Short description (≤80 chars) — include the Audio/news mode, e.g. "AI audio tours + audio news for any place"
- [ ] Full description
- [ ] App icon **512×512**
- [ ] Feature graphic **1024×500**
- [ ] Phone screenshots (min 2; ideally 4–8)
- [ ] (Optional) 7-inch / 10-inch tablet screenshots
- Copy/assets source: **AUDIOURA_BETA_LAUNCH_KIT.md**

### A3. Store settings — DONE
- [x] Category Travel & Local; tags set; contact email/website/phone; external marketing ON
- [ ] Verify **info@audioura.com** mailbox is real + monitored (shown publicly)

### A4. Account-level
- [ ] **Android developer verification** (left nav) — complete identity verification; newer accounts can't publish until done
- [ ] Confirm **Payments profile** only needed if charging — app is Free, so likely N/A

---

## B. BLOCKED on the Android build (.aab)

### B1. Create a release
Path: **Test and release**. For Beta use a **testing track**, not Production:
- [ ] Choose **Closed testing** (recommended for Beta) or Internal testing
- [ ] Upload the **Android App Bundle (.aab)** — output of Kiro Mobile's Android build
- [ ] Add testers (email list or Google Group) for closed testing
- [ ] Set **Countries/regions**
- [ ] Confirm app is **Free** (no pricing)
- [ ] Release name + release notes

### B2. Submit for review
- [ ] After the release is filled in and all App content is green → **Send for review**
- [ ] Google review (typically a few days for first submission)

---

## C. Critical-path order
1. **Now:** finish A1 (Government/Ads-ID/News/Content rating), write A2 store listing, complete A4 developer verification.
2. **When the .aab is ready** (Kiro Mobile Android build): B1 upload to Closed testing.
3. **Then:** B2 send for review.

The only true blocker for actually shipping is the **signed .aab from the Android build**. Everything in section A you can complete today.

---

## D. iOS (parallel track, separate)
App Store submission is a separate pipeline gated on Apple Developer enrollment + a Mac Mini build (tracked in the Mobile queue). Not part of this Play Console checklist.
