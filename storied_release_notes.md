# Storied v2.2.0 — Release Notes for Testers

**Build:** 2.2.0+1 · **Branch:** `storied` · **Target:** Aug 1, 2026 closed test (Google Play + Apple TestFlight)

---

## What's New

### 1. Richer POI Stories
Tours now draw from a taxonomy of six narrative styles — history, anecdote, architecture, art, culture, and nature — so consecutive stops feel varied rather than following a single template. Each stop is assigned a story type that best fits its subject, and a narrative spine structures the tour as a journey with a beginning, middle, and end.

### 2. De-repetition Guard
A cross-stop repetition checker identifies near-identical phrasing between stops and rewrites repeated sentences. Forbidden-phrase filtering removes clichéd tourism language ("hidden gem", "vibrant atmosphere") that previously appeared across multiple tours.

### 3. Personalized Tour Narration
On first launch you'll see a "What brings you here?" prompt with four personas: Art Lover, History Buff, Family, and First-Time Visitor. Your choice biases which story types appear in your tours and adjusts the narrative tone. Persona is saved server-side and can be changed anytime.

### 4. Tour Sharing and Referrals
You can share a completed tour via a short link (e.g. `audioura.io/tour/abc12345`). Recipients open the link to view the full tour text. A referral system generates a personal invite code — when a new user redeems it, the attribution is recorded for future reward features.

### 5. App Attestation (Log-Only)
The app now sends a platform attestation token (Play Integrity on Android, App Attest on iOS) with each cloud request. For this release the token is **logged but never blocks** — no request will be rejected due to attestation. This lets us observe real-world data before enabling enforcement in a future update.

---

## Known Limitations

- **Perspective layers** (Artist's View, Architect's View, etc.) are deferred to the New Architecture release and will not appear in Storied tours.
- **Attestation enforce mode** is not active — all requests pass through regardless of token validity.
- **Referral rewards** are not yet implemented — codes are generated and redemptions tracked, but no discount or credit is applied.
- **Personalization quality** depends on the story-type taxonomy; niche POIs may not have enough variety to fully differentiate personas.

---

## How to Test Each Feature

**Richer Stories:**
1. Generate a museum tour (e.g. "Chagall Museum Nice, 10 stops").
2. Read through the stops — verify each one has a distinct narrative style (some tell history, some share anecdotes, some describe architecture).

**De-repetition:**
1. Generate any 10-stop tour and read it end-to-end.
2. Check that no two stops use substantially similar phrasing or repeat the same fact.

**Personalization:**
1. Open the app fresh (or clear data) — the "What brings you here?" screen should appear.
2. Select "Art Lover" and generate a museum tour — expect more art-focused narratives.
3. Change persona to "History Buff" via settings and generate the same tour — narratives should shift toward historical context.

**Sharing:**
1. After generating a tour, tap Share — you should receive a short link.
2. Open that link in a browser or send it to another device — the full tour text should display.

**Attestation (log-only):**
1. Generate a tour normally — it should succeed.
2. Check service logs for `ATTESTATION LOG:` or `PLAY_INTEGRITY_VERDICT:` / `APP_ATTEST_VERDICT:` lines confirming the token was logged.

---

## Cost Expectations

Storied tours cost approximately **$0.07–$0.15** per generation (vs ~$0.04 for Beta). The additional cost comes from the narrative spine generation step and richer per-stop prompts. A cost ceiling monitor logs any tour exceeding $0.15 but never aborts generation.

---

## Privacy Changes

Storied collects four new data points compared to Beta:
- Persona preference (stored in DB, user-changeable)
- Referral code linkage (stored in DB)
- Attestation token (logged transiently, not stored)
- Share count per tour (aggregated, non-PII)

Full details: see `privacy_disclosure_delta.md`.
