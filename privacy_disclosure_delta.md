# Privacy Disclosure Delta — Storied v2.2.0 vs Beta v2.1.1

New data collected by the Storied release that did not exist in the Beta. This document feeds Sir Michael's privacy policy update and app store declarations.

---

## New Data Points

| Data Point | What is Collected | Purpose | Retention | Third Party |
|-----------|-------------------|---------|-----------|-------------|
| **Persona preference** | User's selected persona (art_lover, history_buff, family, first_time_visitor) | Personalizes tour narration style and story-type weighting | Indefinite (user can change/delete anytime) | None — stored in Audioura DB only |
| **Referral code + redemption linkage** | 6-char referral code tied to user_id; redemption records linking referrer → new user | Tracks word-of-mouth growth; enables future referral rewards | Indefinite | None — stored in Audioura DB only |
| **Attestation token** | Play Integrity / App Attest token sent with requests | Validates app authenticity (anti-abuse); used for logging only — not stored in DB | **Not stored** — logged transiently in Cloud Run logs (30-day retention) | Token sent to Google Play Integrity API or Apple App Attest API for verification |
| **Share count per tour** | Integer counter of how many times a tour's share link was opened | Analytics: measures tour popularity and sharing virality | Indefinite (aggregated, non-PII) | None — stored in Audioura DB only |

---

## Third-Party API Calls (new in Storied)

| Service | Data Sent | Purpose | Data Returned |
|---------|-----------|---------|---------------|
| Google Play Integrity API | Integrity token (opaque, device-generated) | Verify the app is genuine and device is untampered | Device integrity verdict |
| Apple App Attest API | Attestation object (CBOR, device-generated) | Verify the app is running on a legitimate Apple device | Attestation validation result |
| Wikipedia REST API | POI/venue name (public text) | Retrieve factual context to ground tour narration | Public article summary (no user data sent) |
| OpenAI API | Tour text prompts (no PII, no user identifiers) | Generate narrative content, fact sheets, directions | Generated text (not stored by OpenAI per DPA) |

---

## What Did NOT Change

- **Location data** — unchanged from Beta (used only for tour generation, not tracked)
- **Subscription credentials** — unchanged (encrypted at rest, same handling)
- **Tour audio/content** — unchanged (stored as before)
- **User identifier (secret_id)** — unchanged (device-generated, pseudonymous)

---

## Notes for Sir Michael

1. **Privacy policy** needs a new section on "Persona Preferences" and "Referral Program" data.
2. **Google Play Data Safety** needs to add "App interactions → Other user-generated content" for persona.
3. **Apple App Privacy** needs "Identifiers → Device ID" (for attestation token verification) and "Usage Data → Product Interaction" (for referral/share tracking).
4. Attestation tokens are **never stored** — only logged transiently for abuse detection.
