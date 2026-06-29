# Audioura — Beta Launch Kit (2026-06-15)

Ready-to-use content for three launch-readiness tasks: store copy, Beta exit criteria, and tester onboarding. Edit names/links in **[brackets]** before publishing.

---

## 1. Store Copy (App Store + Google Play)

**App name:** Audioura
**Subtitle / short tagline (≤30 chars, App Store):** Audio tours, made for you
**Promo line (Play short description, ≤80 chars):** AI audio tour guide that turns any place — or your news — into a guided listen.

**Full description:**

> Audioura turns the world around you into a personal audio guide. Tell it where you are or where you're headed, and it generates a narrated walking or museum tour on the spot — complete with map pins for each stop. Prefer to listen to the news? Audioura can read your articles and newsletters aloud, too.
>
> **What you can do with Audioura:**
> • Generate location-based audio tours for cities, museums, and landmarks near you
> • Follow each stop on an interactive map
> • Translate tours into other languages and listen in the one you prefer
> • Turn news articles and newsletters into audio you can listen to on the go
> • Save tours to your device and re-listen anytime
>
> No account, email, or password required to get started. Just open the app and listen.
>
> Audioura is in Beta — we're a small team refining the experience, and your feedback shapes what comes next.

**Keywords (App Store, comma-separated, ≤100 chars):**
audio tour,tour guide,walking tour,museum,travel,audio news,narration,sightseeing,city guide,podcast

**Category:** Travel (primary) · secondary Lifestyle or News
**Support URL:** https://www.audioura.com/support
**Privacy policy URL:** https://www.audioura.com/privacy
**Marketing URL:** https://www.audioura.com

---

## 2. Beta Exit Criteria

The Beta is deliberately small and unmarketed. It's "done" — i.e., ready to open to a wider audience — when these are answered with evidence, not vibes:

**Scalability & cost**
- [ ] **Cost per active tester per week** is measured and within an acceptable range (define a $ ceiling, e.g. ≤ $[X]/active user/week).
- [ ] The **spend backstop works**: budget alerts fire and the kill-switch caps spend (tested, not assumed).
- [ ] **Tour-generation latency** under realistic concurrent load is acceptable (e.g. p95 ≤ [X] seconds) and Cloud Run scales without errors.
- [ ] No runaway-cost path remains (quota fail-closed verified; attestation logging shows no obviously abusive traffic).

**Stability**
- [ ] **Crash-free sessions ≥ [99%]** across iOS and Android.
- [ ] No P0/P1 bugs open (data loss, failed generation, broken playback, failed account deletion).
- [ ] Account deletion works end-to-end on a real device for a real user (app + server verified).

**Experience & engagement**
- [ ] Engagement telemetry is live and shows **listen-through and drop-off per POI** — and the median tour is actually listened to past stop [N].
- [ ] The "boring/repetitive tour" defect is fixed (no repeated stock phrasing across POIs).
- [ ] Tester feedback themes are captured, and the top 3 usability issues are identified (and triaged).

**Decision gate:** Only when scalability + stability are green do you widen access. Quality/engagement results feed the v2.3 (revenue) and v2.4 (quality) plans.

---

## 3. Tester Onboarding (one-pager to send invitees)

> **Welcome to the Audioura Beta — thank you for testing!**
>
> Audioura is an AI audio tour guide. You're one of a small group trying it before anyone else, and your feedback genuinely shapes it.
>
> **How to install**
>
> *iPhone / iPad (TestFlight):*
> 1. Install **TestFlight** from the App Store (free, by Apple).
> 2. Open this invite link on your device: **[TestFlight invite link]**
> 3. Tap **Accept**, then **Install** to get Audioura.
>
> *Android (Google Play closed test):*
> 1. Tap this opt-in link: **[Play closed-test link]** and tap **Become a tester**.
> 2. Then install Audioura from **[Play store link]** (may take a few minutes to appear).
>
> **What to try**
> • Generate a tour for where you are right now, and for a place you know well.
> • Follow the map and listen to a few stops.
> • Try translating a tour into another language.
> • (Optional) Connect a news source and listen to an article.
> • Try **About → Delete My Account** at the end if you're willing — it should reset cleanly.
>
> **What to tell us**
> • Was the tour interesting and accurate, or repetitive/boring? Where exactly?
> • Anything confusing, slow, or broken?
> • Did the audio and map work as expected?
> • Would you use this for real? Why or why not?
>
> **Send feedback to:** **[support@audioura.com]** (or **[feedback form link]**). Screenshots help.
>
> Please keep the app to yourself for now — we're keeping this round small on purpose. Thanks again!

---

### Where each piece goes
- **Store copy** → App Store Connect + Play Console store listing (Store Submission list).
- **Beta exit criteria** → fill the [brackets] with your target numbers (Launch Readiness task "Define Beta exit criteria").
- **Tester onboarding** → paste the invite/store links once the testing tracks exist, then send to your tester list.
