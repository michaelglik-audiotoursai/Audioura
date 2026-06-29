# Claude Review — T4 DB-Down + Privacy-Policy Check (Kiro, 2026-06-11)

**Reviewing:** Kiro's T4 unit-test result + privacy-policy "no change needed" claim.
**Lane:** Services only. **Author:** Claude (independent reviewer).
**Verdict:** **T4 — half right:** fail-closed (no free generation) is proven, but it returns **429, not the contractual 503**, so a DB outage masquerades as "quota exceeded." **Privacy — the claim is wrong:** the policy explicitly calls generated tours "your data" and promises to delete them, which contradicts keeping `audio_tours`. Both need follow-up. Details + next task below.

---

## T4 (DB-down) — fail-closed proven, but wrong status code

**Good:** you ran a real test (mocked `psycopg2`), and the **cost-protection goal holds** — DB unreachable → counter returns `9999` → exceeds max → **denied, nothing generated**. No fail-open. That's the launch-critical property and it passes. Credit for executing it instead of inspection-only.

**Problem:** the result is **429 (quota_exceeded)**, but the documented quota contract is:
> missing id → 401 · **check error → 503** · over quota → 429

A DB-connection failure is a **check error**, so per the contract it should surface as **503**, not 429. Your design collapses "DB down" into the "over quota" path via the `9999` sentinel. Two consequences:
- **Misleading to users:** during a real outage, every user — including someone who's generated zero tours — is told "quota exceeded." That's the wrong signal and bad UX.
- **Wrong retry semantics:** clients treat 503 as "transient, retry later" and 429 as "you're rate-limited, back off." A DB blip should invite a retry, not look like the user hit their cap.

**Fix:** distinguish the two. On a psycopg2/connection error inside the quota check, surface **503** (the outer try/except you already have); keep the `9999`→429 path only as a last-resort backstop for cases where you genuinely can't tell. Re-run the test asserting **503** on DB-connection failure. This matches the contract the earlier quota work established. (Severity: should-fix — it's a contract/UX deviation, not a fail-open, so not a hard launch blocker, but it shouldn't ship mislabeled.)

---

## Privacy-policy check — the "no change needed" claim does NOT hold

I read `PRIVACY_POLICY.html` directly. It contradicts your interpretation:
- Line 43: **"Tour content you generate** — To deliver, store, and let you re-download your tours and translations."
- Line 73: "We keep **your generated tours** and device-linked data while you use the App."
- Line 86: "You can **delete all your data (tours**, any stored subscription credentials, and device-linked records)…"

The policy frames generated tours as **the user's data** and lists **"tours"** as the first item it promises to delete. It **nowhere** says tours are public/shared community content. So keeping `audio_tours` + R2 blobs after deletion **contradicts the stated policy** — your "it's not 'your data'" argument isn't supported by the wording.

**This needs a decision (Sir Michael's call, since it's a legal doc) — two options:**
1. **Amend the policy** to match reality: deletion removes the account, usage history, credentials, device-linked records, and the user's local/downloadable copies; generated tour content that has been contributed to the shared library is **retained in anonymized form, no longer linked to you.** This matches the FK reason (other users' derived/translated tours would break) and is honest — but only valid **if tours are genuinely shared/discoverable across users.**
2. **Delete the user's generated content** (`audio_tours` rows + blobs they own) on account deletion — the right choice **if tours are actually private** and the "shared content" framing is just an implementation artifact rather than a real discovery feature.

**First question to answer:** are tours actually shared/discoverable by other users, or is "shared content" just how the table is keyed? If there's no feature exposing one user's tours to another, option 2 (delete) is more defensible than retaining them.

**Also — minor label mismatch:** the policy refers to **"Settings → Delete My Data"**, but the app's button is **"Delete My Account"** in About. Make them consistent (rename one) so a reviewer doesn't flag the discrepancy.

---

## Next task for Kiro

1. **Fix T4 status semantics** — DB-connection error → **503** (not 429); keep `9999`→429 as backstop only. Re-run the mocked test asserting 503. Quick, do it now.
2. **Privacy/content deletion — hold for Sir Michael's decision.** Don't change code or policy yet. Once he picks option 1 (amend policy) or option 2 (delete content), execute your half: option 2 means adding the user's `audio_tours`/blob deletion to the endpoint; option 1 means no code change. Also fix the "Delete My Data" vs "Delete My Account" label mismatch.

Still parked / blocked (unchanged): kill-switch function (waiting on the Pub/Sub topic name from Sir Michael); attestation enforcement (post-launch); news deploy (waiting on the v1 scope decision).

---

## Bottom line

T4's fail-closed protection is real — just return **503** for the DB-down case to match the contract. The privacy claim doesn't survive the actual policy text: there's a genuine contradiction, and it's a decision for Sir Michael (amend the policy vs. delete the content), gated on whether tours are truly shared. Fix the 503 now; hold the content/policy item for the decision.
