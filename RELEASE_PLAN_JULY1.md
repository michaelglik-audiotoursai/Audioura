# Audioura — Release Plan to July 1, 2026

**Today:** Wednesday June 10 · **Target:** Wednesday July 1 · **Working window:** ~3 weeks.

This is the fix → test → submit roadmap. It is sequenced so the two biggest schedule risks —
the App Store review queue and (if applicable) Google's 14-day closed-test rule — are handled first.

---

## The two hard constraints that set the schedule

1. **D-U-N-S number for Audioura LLC.** Registering Play as an **Organization** account (Audioura LLC)
   exempts you from the 14-day/12-tester closed test entirely — but org accounts require a D-U-N-S number.
   → **Look up / request the D-U-N-S June 10.** If already issued, Android is unblocked. If not, request
   the free expedited D-U-N-S; issuance can take days to ~30 days and is now the binding Android constraint.
   (Optional: enroll Apple as Individual to start iOS before the D-U-N-S issues.)

2. **Apple App Store review** takes ~1–3 days (sometimes longer, and rejections cost a round-trip).
   → **Submit iOS to review no later than June 26** to keep a buffer before July 1.

---

## Week 1 — June 10–16 · Accounts + close all code fixes

**Decisions (June 10–11, Sir Michael):**
- Confirm Play account type; if personal, decide org-upgrade vs Android-after-July-1. *(Task #1)*
- Register Apple ($99/yr) + Play ($25) accounts now — Apple verification can take 1–2 days. *(Task #2)*
- Lock the API-key vs attestation posture (recommended: rate-limits + budget caps for v1). *(Task #7)*

**Cloud fixes (Kiro, by June 14):**
- Tighten free-tier quotas; fix news-quota fail-open + `news_max_minutes`; close anon bypass. *(Task #3)*
- Plural-only classification regex (v13 fix), deploy + verify. *(Task #4)*
- Set GCP budget + alerts.

**Mobile fixes (Mobile-AQ / iOS-AQ, by June 16):**
- Existing/downloaded-tour translation fires `translate-with-audio`. *(Task #5)*
- Wire cloud news endpoints. *(Task #6)*
- Implement in-app account-deletion flow. *(Task #8)*

**If Play account is personal:** create the closed-testing track and **start the 14-day test by June 16**
with ≥12 testers (friends/colleagues/test-service). Keep them opted-in continuously.

**End-of-week gate:** all six code fixes merged and deployed; quotas verified enforcing.

---

## Week 2 — June 17–23 · Package, fill forms, get on test tracks

- Host the privacy policy at a public HTTPS URL. *(Task #9)*
- Add iOS Info.plist usage strings + Android permission rationale. *(Task #9)*
- Build signed Android **.aab** (confirm target API level) and signed iOS archive. *(Task #10)*
- Complete: Play **Data Safety** + content rating; iOS **Privacy Nutrition labels**. *(Task #11)*
- Prepare listing assets: icon, screenshots, copy, support URL, version 1.0.0. *(Task #11)*
- Upload iOS build to **TestFlight**; upload Android to **internal testing**.
- **Full device smoke test** (iPhone + Android): generate → translate (incl. existing-tour `de`) →
  news → map pins → account deletion. Log and fix anything user-visible. *(Task — verification)*

**End-of-week gate:** both builds installable from test tracks, all compliance forms drafted,
privacy policy live, no known user-visible bugs.

---

## Week 3 — June 24–30 · Submit, review, release

- **June 24–25:** final regression pass; freeze the build.
- **By June 26:** **submit iOS to App Store review.** (Earliest submission = most buffer for a rejection.)
- **Android:** if org account → promote to production review; if personal → ensure the 14-day closed test
  completes (started ~June 16 finishes ~June 30) then apply for production.
- **June 27–30:** respond fast to any review feedback; resubmit same day if rejected.
- **July 1:** release approved iOS build; promote Android to production (or share closed-test link if
  production approval is still pending).

---

## Daily cadence I'll run with you
Each working day I can: (1) check task status, (2) flag the day's blockers, (3) verify the latest
deployed fix against logs/code, and (4) tell you exactly what's on the critical path that day.
Say the word and I'll set this up as a recurring morning check-in.

---

## Realistic read on July 1
- **iOS by July 1: achievable** if code fixes land in Week 1 and you submit to review by ~June 26.
- **Android by July 1: achievable** via an Organization Play account (Audioura LLC), which skips the
  14-day test — **provided the D-U-N-S is already issued or comes through quickly.** The binding
  constraint is now D-U-N-S timing, not your code or a testing window.

---

## Fastest path if the D-U-N-S is delayed
1. Enroll Apple as an **Individual** (no D-U-N-S) and ship **iOS on July 1**.
2. Once the D-U-N-S issues, register Play as Organization and release Android (no 14-day test needed).
3. You still get a real-install interest signal on July 1.
