# Google Play — Ads Declaration (CORRECTED 2026-06-21)

**App:** Audioura · **Location:** App content → Ads

## Answer for the Beta launch: **"No, my app does not contain ads"** ✅ — but read why

This is correct **only because the Treats feature (local business offers) is gated OFF in cloud mode** — the treats service isn't deployed to cloud, so the Beta shows **no offers at all.** With nothing being served, there are no ads. Today:
- No third-party ad networks / SDKs (no AdMob, Meta Audience Network, AppLovin, etc.).
- No ad monetization.
- Treats = disabled in cloud → no promotional content shown.

## ⚠️ Correction to the earlier framing
The previous draft claimed Treats coupons are "**never** ads." That's **not safe to assume.** When the **v2.3 monetization** ships — **local businesses paying for placement / map presence** — that is **paid third-party promotional content**, which Google treats as **ads**. At that point the declaration must change to **"Yes,"** and you'd resubmit.

So the accurate position is: **"No" now because Treats is off**, not "Treats can never be ads."

## When you MUST flip this to "Yes"
- You add any third-party ad network/SDK, **or**
- Treats goes live showing **paid** business offers/placements (the v2.3 model), **or**
- You display promotional content for other businesses in exchange for payment.

Update the declaration **before** resubmitting the app for review when any of the above is true.

## Quick reference
| Item | Beta answer | Notes |
|---|---|---|
| Third-party ad networks? | No | None deployed |
| Treats (paid business offers)? | **Off in Beta** → No | **Becomes "ads" when live → flip to Yes** |
| Declaration for launch | **No, app does not contain ads** | Correct *while Treats is disabled* |
