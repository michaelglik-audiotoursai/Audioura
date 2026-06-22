# Claude Review — Google Play Console Answers: Corrections (2026-06-21)

Reviewed: `GOOGLE_PLAY_CONTENT_RATING_ANSWERS_GUIDE.md`, `GOOGLE_PLAY_ADS_DECLARATION_GUIDE.md`, `GOOGLE_PLAY_CONSOLE_SETUP_ANSWERS_RATIONALE.md`.
**Verdict: not accurate — correct the items below before/after submission.** Priority order.

---

## 🔴 1. Target Audience — DO NOT target children (most important)
**Wrong:** selected all age bands incl. "5 and under / 6–8 / 9–12," and certified COPPA/Families compliance.
**Why it's wrong & risky:**
- Triggers Google's **Families Policy**, which restricts collecting **precise location** + **persistent device identifiers** from children. Audioura collects both → would **fail** review.
- Contradicts your privacy policy (§5: "not directed to children under 13").
- The COPPA certification would be **false** (precise location + device id from kids needs verifiable parental consent).

**Correct answer:** target **13 and over** (select 13–15, 16–17, 18+; **uncheck** 5-and-under, 6–8, 9–12). Do **not** certify the app as child-directed. If already submitted as "all ages," edit and resubmit.

## 🔴 2. Data Safety — use the verified mapping, not this doc
**Wrong in the doc:** "no device identifiers," "location not stored persistently," "no personal info."
**Reality (collect = YES):** Precise **Location** (stored), **Device or other IDs** (USER-hash), **App info & performance → Crash logs + Diagnostics**, **App activity** (search history + interactions), **Personal info → Other info** (optional subscription credentials). Audio = **No** (on-device transcription). Shared = **No** everywhere (service providers ≠ sharing).
**Action:** answer the Data Safety form straight from **`AUDIOURA_DATA_SAFETY_MAPPING.md`**. It already matches the privacy policy; the version in the setup doc does not.

## 🟠 3. Content rating — public UGC needs a report path (or reconsider the answer)
You answered "users exchange content with other users = **Yes**" (shared public tours) but declared **no reporting / no blocking**. For public user-curated content, Google generally expects a **content-report mechanism**. Either:
- add a simple "report this tour" path, or
- reconsider whether "Yes" is the right answer (tours go to a shared library; there's no direct user-to-user interaction or messaging — arguably this is *not* "exchange content with other users").
Either way, **do not** combine public UGC with a child audience (fixed by #1).

## 🟠 4. Ads — "No" is correct only because Treats is off in the Beta
Fine for launch (Treats is gated off in cloud mode → no offers shown). But the doc's claim that Treats coupons are "never ads" is **incorrect** for the v2.3 **paid business placement** model — that is advertising. **Flip this declaration to "Yes" when Treats / paid placement goes live**, and re-review whether even self-served third-party offers count as ads.

## 🟡 5. Minor / verify
- **`info@audioura.com`** — confirm it's a real, monitored mailbox (the privacy-policy contact was a gmail address, and `www` DNS is broken — verify the domain email actually works before listing it as support).
- **"Primarily news or educational = No"** — borderline (Audio mode is half the app); defensible as "primarily tours," but be aware news is a major component.
- **Already-submitted claims** — the content-rating doc says "submitted and accepted." If it was submitted on the wrong target audience / UGC answers, **resubmit** after fixing #1 and #3.
- **Short description** omits the news/Audio mode — optional to mention.

---

## Bottom line
The answers were drafted as if Audioura were a minimal-data, all-ages, COPPA-certified app. The real app collects **precise location + a device id + optional credentials** and is **not for children**. Fix the **target audience (#1)** and **Data Safety (#2)** first — those are the rejection risks — then the UGC report path (#3) and the Ads note (#4). Keep every answer consistent with `https://audioura.com/privacy`.
