# Owner Decisions — Tours/Privacy + Profile Portability (2026-06-11)

Based on Sir Michael's product principles: **no private tours** (all generated tours are shared/public content); **user identity must be anonymous** (even the owner can't identify a real person unless they connect subscription credentials); **users must be able to move their profile across devices** (multiple devices, replacement, loss).

*(Not legal advice — the policy wording below is a draft for your review.)*

---

## 1. Tours/privacy — RESOLVED: keep content, amend the policy

"No private tours" means the shared-content model is **intended**, so **Kiro's code is correct** — generated tour content (`audio_tours` + blobs) should be **kept** on account deletion, not deleted. Good news: `audio_tours` is **not keyed to the user** (no `secret_id` column), and the deletion endpoint removes `tour_requests`/`coordinates`/`map_requests` plus credentials and device records — so after deletion the retained tour content has **no link back to the person**. That's genuinely anonymized, which is what makes retaining it defensible under GDPR/CCPA.

**What's wrong is only the policy wording** — it currently frames tours as personal data to be deleted. Amend these three spots so the promise matches reality:

**Section 1 table — "Tour content you generate" row (line 43):**
> *To deliver, store, and let you re-download your tours and translations. **Generated tours are added to Audioura's shared, public library and may be available to other users. This content is not linked to your identity.***

**Section 4 Data retention (line 73):**
> We keep your generated tours and device-linked data while you use the App. **Tour content you generate is added to our shared public library and may be retained, in anonymized form not linked to you, even after you delete your data — because other users may rely on those tours and their translations.** Voice input is processed to fulfill your request and not retained for advertising. If you connect a news subscription, your credentials are retained only as long as needed to access content for you and are removed when you disconnect the subscription or delete your data.

**Section 6 Your rights (line 86):**
> You can **delete all your personal data** — your account, usage history, any stored subscription credentials, device-linked records, and the tours downloaded on your device — directly in the App via *About → Delete My Account*, or by emailing us. **Generated tours already added to the shared public library are retained in anonymized form, no longer linked to you.** Depending on your region (e.g. GDPR, CCPA) …

**Also fix the label mismatch:** the policy says *"Settings → Delete My Data"* but the app button is *"Delete My Account"* in the About screen. The draft above aligns the policy to the app (*About → Delete My Account*). Pick one label and use it in both places.

**Net:** no code change to deletion (Kiro's keep-content is right); amend the policy as above; fix the label. The earlier "contradiction" is closed once the wording is updated.

---

## 2. Anonymity — already satisfied

The current model meets your bar. The user id is `USER-<hash>` derived from device hardware — **no email, no password, no name**. Even you can't map it to a real person. The only identity-revealing data is **subscription credentials**, and those are optional and only entered when a user deliberately connects a paid news login. The policy already states no email/password is required. Nothing to change here.

---

## 3. Profile portability — NEW requirement, needs a scope decision

This one isn't supported today and is a real design item.

**Current reality:** the user id is **deterministic from device hardware**, so a **new device = a new id = a brand-new empty profile**. A replaced or lost phone today means the old profile (tours, connected subscriptions) is **not recoverable**. That directly conflicts with "users should be able to move their profile across devices."

**The hook already exists:** the schema has `user_consolidation_map`, `device_consolidation_history`, and `consolidated_user_id` — infrastructure for merging multiple device ids under one identity. What's missing is a **claim/transfer flow** to trigger it.

**The hard part — doing it without breaking anonymity.** Since there's no email/password, you need a portable secret the user holds. Options:
- **Recovery code / passphrase** (recommended): on first run, generate a one-time recovery code the user saves; entering it on a new device links that device to the existing profile. Anonymous, works even if the old phone is lost. Downside: if the user loses the code, the profile is unrecoverable (acceptable given the no-identity design).
- **Device-to-device link (QR):** old device shows a QR, new device scans. Clean, but **only works if the old device still functions** — useless for a lost/dead phone. Good as a secondary path.

**Deletion implication you should know:** once profiles span multiple devices under one `consolidated_user_id`, **account deletion must delete by the consolidated identity across ALL linked devices**, not just the current device's `secret_id`. The current endpoint deletes by `secret_id` (with an `OR consolidated_user_id` hedge) and was tested single-device only. So portability **re-opens** the deletion work — it would need to resolve and wipe every linked device id, and be re-tested with a merged profile.

**Recommendation: defer full portability to the next-version architecture (not v1).** Reasons: it's genuine identity-system design (recovery flow + claim mechanism + security), and your own master plan scopes next-version architecture to a separate track with a July 1 launch target. For v1, keep **device = identity** (the deletion endpoint is correct and tested for that case). Flag portability as a top next-version item, with the deletion-must-be-consolidation-aware note attached so it isn't missed.

**Decision needed from you:** confirm portability is **next-version** (my recommendation), or tell me it's **v1 launch scope** — in which case it becomes a significant new workstream for Kiro (claim/transfer flow + consolidation-aware deletion + re-test) and Mobile (recovery-code UI), and it puts the July 1 date at risk.

---

## What happens next

- **You:** approve the policy wording above (or edit it) — I'll apply it to `PRIVACY_POLICY.html` on your OK. Confirm the portability scope (next-version vs v1).
- **Kiro:** no deletion code change (keep-content confirmed correct). Still do the **T4 → 503 fix**. The policy amendment is owner-side. If you decide portability is v1, he gets the consolidation-aware deletion + claim flow.
- **Mobile:** nothing now (recovery-code UI only if portability becomes v1).
