# Storied Release — Development Plan

**Created:** 2026-06-26 · **Owner:** Sir Michael · maintained by Claude (reviewer/coordinator)
**Goal:** Storied submitted to **Google Play (closed test) + Apple (TestFlight)** by **end of July 2026**; testers run Storied on both stores **from Aug 1**.
**Scope decision:** FULL Storied — all 5 features (Sir Michael, 2026-06-26).
**Branch:** `storied` (off `main` = `beta-2.1.1+18`). **Version line:** `2.2.0+…` (kept distinct from Beta's 2.1.x).

---

## Relationship to Beta
- **Beta (`beta-2.1.1+18`)** goes to **Google closed testing now** — this starts Google's mandatory ~14-day / 12-tester clock and validates the pipeline. Apple TestFlight follows once the org migration clears.
- **Storied** is built on top of Beta and becomes the Aug-1 tester build on both stores.
- **Bug-fix rule:** Beta bugs are fixed on `main`, re-tagged, then **merged forward into `storied`** (never hand-applied twice).

---

## The 5 features → per-agent, trackable work

### 1. Richer POI stories  ·  owner: Services Kiro
- Define a **story-type taxonomy** (history / anecdote / architecture / culture / nature…).
- Update tour-generation prompts so each POI draws a *varied* story type, not a uniform template.
- Content QA pass on 5–10 representative tours.

### 2. Remove repetitive POI language  ·  owner: Services Kiro  ·  (existing task `86aj2jnh7`)
- De-duplicate near-identical phrasing across POIs (generation-time variation / anti-repetition).
- Verify against the same QA tours as #1 (these two ship together).

### 3. User-interest personalization  ·  owner: Services + Mobile + Sir Michael/Claude
- **Services:** server-side per-user interest table (schema), capture signals (plays, skips, chosen story types), tailor POI story selection.
- **Mobile:** interest/preferences UI + explicit consent toggle.
- **Sir Michael/Claude:** update **privacy policy + Data Safety / App Privacy** disclosures — this is behavioral profiling and must be declared on both stores BEFORE the build ships.

### 4. Tour sharing + referral  ·  owner: Mobile + Services
- **Mobile:** native share sheet (email + social apps) for a tour; "invite a friend" referral entry point.
- **Services:** referral link generation + attribution; deep-link resolution to the shared tour.

### 5. App attestation (log-only → enforce)  ·  owner: Mobile + Services  ·  (scaffold already approved)
- **Mobile:** Play Integrity (Android) + App Attest (iOS) token generation on cloud calls.
- **Services:** verify attestation tokens at the gateway, **in addition to** the API key (key stays as outer gate — see `GATEWAY_API_KEY_PURPOSE.md`).
- Roll out **log-only first** (observe, don't block) so it can ship Aug 1 without risk; flip to **enforce** as an update during the test window.

### Fast-follows (fold in if time allows; otherwise updates during testing)
- **Encrypt-at-rest for subscription credentials** (KMS envelope) — Services, code already approved, task `86aj58e6h`.
- **Cert pinning + attestation-gated short-lived tokens** — Mobile + Services (defense-in-depth).

---

## July timeline (milestones)

| Week | Services Kiro | Mobile Kiro | Sir Michael / Claude |
|---|---|---|---|
| **Jun 29–Jul 3** | Freeze/branch (`wdvrdaw4bt`); start richer stories + de-repetition | Sharing UI; attestation client scaffold | Privacy-policy + App Privacy update draft (for personalization) |
| **Jul 6–10** | Personalization interest table + tailoring | Interest/consent UI; attestation tokens on calls | Review designs; confirm privacy disclosures |
| **Jul 13–17** | Attestation server verify (log-only); referral attribution; encrypt-at-rest | Referral/deep-link; integrate personalization UI | Mid-point review of each feature vs. committed code |
| **Jul 20–24** | Feature-complete; full regression; cut `storied` tag | iOS+Android device builds from the `storied` tag | Apple migration check → App Store Connect record + signing |
| **Jul 27–31** | — | Build both stores from one `storied` tag | Submit Google closed test + Apple TestFlight; reviews/fixes |
| **Aug 1** | — | — | **Testers live on both stores** |

---

## Risks & de-risking
- **Apple org migration is an external dependency** that gates the Apple submission. Google can hit Aug 1 regardless; Apple may slip if migration is late — start/expedite it now.
- **Personalization** is the heaviest feature and carries a **privacy-disclosure dependency** — the policy/labels must update before it ships.
- **Attestation** ships **log-only** for Aug 1; enforce is a follow-up so it can't block the release.
- **Sync guarantee:** both stores' Storied build come from a **single `storied` tag**, the same way Beta is anchored to `beta-2.1.1+18`.

---

## ClickUp
- Storied epic: `② Storied` (`wdvrdaw13k`) in Go-To-Market → Release Roadmap; broken into the per-feature tasks above.
- Active Storied work is promoted to the Backend/Mobile queues (tagged `storied`) as it starts; `MVP -- Release 1` stays focused on Beta bugs + the Apple submission.
