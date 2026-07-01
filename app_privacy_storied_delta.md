# Apple App Privacy Labels — Storied v2.2.0 Delta

New privacy label declarations required for App Store Connect when submitting the Storied release.

---

## New Data Types to Declare

| Data Point | Apple Data Type | Collected | Linked to Identity | Used for Tracking | Purpose |
|-----------|----------------|-----------|-------------------|-------------------|---------|
| **Persona preference** | Other Usage Data → Product Interaction | Yes | **Yes** | No | App Functionality, Analytics |
| **Referral code + redemption** | Identifiers → User ID (pseudonymous) | Yes | Yes | No | App Functionality |
| **Attestation token** | Diagnostics → Performance Data | **No** (logged transiently, not stored) | No | No | — |
| **Share count** | Usage Data → Product Interaction | Yes | No | No | Analytics |

---

## Detailed Answers for App Store Connect

### Persona Preference
- **Data type:** Other Usage Data → Product Interaction
- **Is this data collected?** Yes
- **Is it linked to the user's identity?** **Yes** (stored with device_id in user_preferences table)
- **Is it used for tracking?** No (never shared with third parties for advertising)
- **Purpose:** App Functionality (personalizes tour narration), Analytics (aggregate persona distribution)
- ⚠️ **Note:** Per Apple's guidelines, persona preference IS behavioral profiling and must be declared even though it's first-party only.

### Referral Code + Redemption
- **Data type:** Identifiers → User ID
- **Is this data collected?** Yes
- **Is it linked to the user's identity?** Yes (referrer_user_id + new_user_id linked at redemption)
- **Is it used for tracking?** No (internal referral program only, no third-party sharing)
- **Purpose:** App Functionality (referral rewards)

### Attestation Token
- **Data type:** Diagnostics → Performance Data
- **Is this data collected?** **No** — the token is sent to Google/Apple verification APIs but is NOT stored in our database. It appears only in transient Cloud Run logs (30-day auto-delete).
- Since it's not collected/stored, it does NOT need to be declared as "collected" data.

### Share Count
- **Data type:** Usage Data → Product Interaction
- **Is this data collected?** Yes
- **Is it linked to the user's identity?** No (aggregated per tour, not per user)
- **Is it used for tracking?** No
- **Purpose:** Analytics (measure tour popularity)

---

## App Store Connect Review Notes (plain English)

> Audioura v2.2.0 adds tour personalization (user selects a preference from 4 options to customize narration style), a share-a-tour feature with referral codes, and app attestation for abuse prevention. The personalization preference is linked to the device identifier and used only to customize the in-app experience — it is never shared with third parties. Attestation tokens are validated by Apple/Google but not stored by Audioura. The referral system links two pseudonymous device IDs at the moment of redemption for internal analytics only.
