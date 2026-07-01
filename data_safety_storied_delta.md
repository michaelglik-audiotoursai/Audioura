# Data Safety — Storied v2.2.0 Delta for Google Play

Additions to the Google Play Data Safety form for the Storied release. Format mirrors `AUDIOURA_DATA_SAFETY_MAPPING.md` so entries can be merged directly.

---

## New Data Types Collected

| Data Type Category | Data Subtype | Collected | Shared with Third Parties | Optional or Required | Purpose |
|---|---|---|---|---|---|
| App activity | Other user-generated content | Yes | No | Optional | User's selected persona preference (art_lover, history_buff, family, first_time_visitor) for tour personalization |
| App activity | Other actions | Yes | No | Optional | Referral code creation and redemption events — tracks which user referred whom |
| App info and performance | Other app performance data | Yes | No | Required | Tour share_count (integer counter of link opens per tour) for analytics |
| Device or other IDs | Other IDs | Yes | Yes — Google Play Integrity API | Required | Play Integrity attestation token sent to Google for device verification (not stored in Audioura DB) |

---

## Data Handling Details

### Persona Preference
- **Collected:** Yes — stored when user selects persona during onboarding
- **Shared:** No — stored only in Audioura's database
- **Processing purpose:** App functionality (personalizes tour narrative style)
- **User control:** User can change persona anytime; data deleted on account deletion
- **Ephemeral:** No — persisted until changed or deleted
- **Required:** Optional — app functions without it (default persona applied)

### Referral Code + Redemption Linkage
- **Collected:** Yes — code generated from user_id hash; redemption links referrer to new user
- **Shared:** No — stored only in Audioura's database
- **Processing purpose:** App functionality (referral attribution for future rewards)
- **User control:** Code is deterministic from user_id; cannot be deleted without account deletion
- **Ephemeral:** No — persisted indefinitely
- **Required:** Optional — user can choose not to create or share referral codes

### Share Count
- **Collected:** Yes — incremented each time a shared tour link is opened
- **Shared:** No — stored only in Audioura's database
- **Processing purpose:** Analytics (measures tour popularity)
- **User control:** Aggregated counter, non-PII, not individually attributable
- **Ephemeral:** No — persisted indefinitely
- **Required:** Required — automatic when sharing feature is used

### Attestation Token (Play Integrity)
- **Collected:** Yes — device-generated token sent with each cloud API request
- **Shared:** Yes — token sent to Google Play Integrity API for verification
- **Third party:** Google (Play Integrity API) — receives opaque device integrity token
- **Processing purpose:** Security (verifies app is genuine, device untampered)
- **User control:** Automatic, no opt-out (required for app security)
- **Ephemeral:** Yes — logged transiently in Cloud Run logs (30-day retention), NOT stored in database
- **Required:** Required — automatic on every API request (log-only mode, does not block)

---

## Summary of Changes to Existing Declarations

| Existing Category | Change |
|---|---|
| Device or other IDs | **Add** "Other IDs" subcategory for attestation token |
| App activity | **Add** "Other user-generated content" for persona + "Other actions" for referrals |
| App info and performance | **Add** "Other app performance data" for share_count |

---

## Notes

- No new "third party = yes" entry without naming the third party. The only third-party share is the attestation token → Google Play Integrity API (already named above).
- Attestation token is **not stored** in Audioura systems — only logged transiently for abuse detection.
- All new data points are clearly optional (persona, referral) or automated/required (attestation, share_count).
