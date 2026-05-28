# Transition Brief — Strategic Advisor Amazon-Q (🎯)

**Date:** 2026-05-28. Supersedes any prior version (lost during A#74 cleanup).
**Audience:** 🎯 STRATEGIC ADVISOR AMAZON-Q.
**Status of your `remind_advisor.md`:** untouched. You own it.

The mobile-app track is stable at v1.2.9+65 (A#75 shipped). **The next big effort is the services migration to GCP**, which gates the App Store + Google Play submission. Your role: cross-track coordination, timeline tracking, cost monitoring, and resolving decisions that span Services Q and the mobile-app Qs.

---

## Two concurrent projects to coordinate

### Project A — Services migration (Services Q owns execution)

Spec: `C:\Business\AudioTours.io\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md`. Five phases M01–M05. Estimated 20–30 hours of focused Services Q work.

**Your job:**
- Track which phase Services Q is in. If a phase slips by >30%, surface to Sir Michael.
- **Cost monitoring.** Cloud Run scales to zero (cheap), but always-on Cloud SQL is the floor cost. Expected $10–36/month per spec. Watch the actual bill for the first 30 days. If newsletter-processor's Cloud Run footprint surprises (it runs headless Chrome, 5-10x leaf services), recommend a resize.
- **Newsletter-processor cost outlier** — first place to look if billing surprises.
- **AWS Polly cost continuity** — stays as external dep; verify IAM creds are migrated to Secret Manager cleanly during M03.
- **Failure escalation** — if Services Q can't unblock alone (Cloud SQL connectivity, R2 quirks, AWS auth from GCP), suggest a Cloudflare Tunnel stopgap or escalate to Sir Michael with options.

### Project B — App Store + Google Play submission (multiple Q's)

Spec: `C:\Business\AudioTours.io\Claude\Audioura development\STORE_SUBMISSION_ROADMAP.md`. Six phases.

**Your job:**
- **Phase 0 gate enforcement.** Phase 0 = "backend reachable via public HTTPS" = Services Q's M04 + M05. **Block any attempt to start Phase 1 work before this gate clears.** If iOS Q tries to start Phase 1 early, push back.
- **Subscription/IAP discipline.** Locked decision: **no IAP in v1.0.** RevenueCat in v1.3 post-launch. If anyone proposes adding subscriptions, your answer is NO, citing Apple Guideline 3.1.1.
- **Demo account.** Apple App Review needs login credentials for any app that requires login. If Services Q's auth model lands as "user accounts required," ensure Sir Michael creates a demo account before submission and types it into App Store Connect's App Review Information section. **Forgetting this is the single most common rejection trigger.**
- **App Review iteration budget.** Plan for at least one Apple rejection cycle (1-2 weeks). Realistic 8 weeks; optimistic 6 weeks from M04 completion.
- **Background audio justification.** Apple sometimes rejects background-audio apps. **Pre-emptively write a 2-sentence justification** for the App Review Information: "Audioura is an audio tour application; users start a tour and continue listening while their phone is in their pocket, while walking, or while the screen is off. Background audio is core functionality."
- **Keystore backup reminder.** Mobile Q generates the Android keystore. **You own reminding Sir Michael to back it up to 3 places.** Loss = app death on Play Store forever.
- **Privacy/Terms consistency check.** Sir Michael writes copy in Phase 2. Review for: are OpenAI and AWS Polly named as third-party processors? Are all data categories disclosed? Does the wording match what the Android Data Safety form will say? Inconsistencies between iOS privacy policy and Android Data Safety = rejection trigger on both sides.

---

## Cross-track decisions you make on Sir Michael's behalf

These are decisions that span both projects. Sir Michael will route them to you.

| Decision | When it arises | Default position |
|---|---|---|
| Submit to App Store now vs wait for Cloud Run `min-instances=1` | Just before Phase 6 / A36 | **Wait.** $10-20/month for min-instances during the 1-2 week review window is cheap insurance against cold-start timeouts during App Review. |
| Use Cloudflare Tunnel as Phase 0 stopgap | If Services Q's M04 slips badly | **No.** Mechanically works but Apple's review window catches the laptop being offline overnight. Wait for real Cloud Run. |
| Amazon Appstore for v1 | Anyone proposes it | **No, deferred.** Apple + Google Play only. Amazon Appstore is <2% of Android download volume and doubles publishing maintenance. |
| Add a fifth translation language for v1 | Anyone proposes it | **No, deferred.** Translation stays as-is for v1.0. |
| Sunset the LAN dev workflow once cloud is up | After M05 completes | **No, keep both.** Sir Michael's daily dev still benefits from laptop Docker. Cloud is production; laptop is iteration. |

---

## Cost expectation Sir Michael set

**Near-zero before volume.** Specifically:
- GCP free tier and free trial credits cover initial setup ($0).
- Cloudflare R2 free tier: 10 GB storage, no egress fees ($0).
- Cloud SQL minimum instance: ~$10/month (the floor).
- Cloud Run scale-to-zero: $0 when idle, $cents per request otherwise.
- Domain (audioura.io): probably already owned ($0 incremental).
- DNS via Cloudflare: $0.
- Apple Developer Program: $99/year (already paid).
- Google Play Console: $25 one-time.

**Total to live PreProd: $0–25 one-time + ~$10/month.**
**At low volume in production: $10–36/month.**
**At scale (volume tour/newsletter generation): scales with usage; primarily OpenAI API + AWS Polly costs, which Sir Michael already pays.**

Watch the bill. If anything surprises >2x expected, surface.

---

## Where this doc lives

`C:\Users\micha\eclipse-workspace\AudioTours\development\transition_for_Advisor_AQ.md`. Git-tracked.
