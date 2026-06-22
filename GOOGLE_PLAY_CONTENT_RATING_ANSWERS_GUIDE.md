# Google Play Content Rating Questionnaire — Answers (CORRECTED 2026-06-21)

**App:** Audioura (com.audioura.audiotours) · **Entity:** Audioura LLC
**Status:** ⚠️ **DRAFT — verify before submitting.** (The earlier version was marked "submitted and accepted"; if it was submitted with the old Target Audience/UGC answers, **resubmit** after these corrections.)
**Expected IARC rating:** Everyone / 4+ (content is benign).

---

## Content questions — all **No** (correct, unchanged)
- **Downloaded mature content?** No — nothing explicit is bundled; tours are AI-generated on demand.
- **Violence?** No · **Sexuality/nudity?** No · **Offensive language?** No · **Controlled substances?** No.
- **Age-restricted products (alcohol/tobacco/firearms/gambling)?** No — Treats offers are not age-restricted items.
- **Shares user location with other users?** No.
- **Purchase digital goods / cash rewards / gift cards / crypto / NFTs?** No (free app, no IAP at MVP).
- **Web browser or search engine?** No.

These keep the base rating at Everyone/4+.

## Online content — **Yes** (correct)
Tours and news audio are **generated/fetched online**, not bundled. (Google lists AI-generated content as an example.)

## ⚠️ User-generated content / sharing — needs a report path
**"Does the app allow users to interact or exchange content with other users?"** → **Yes** — this is accurate: per the no-private-tours design, a user's curated tours go to a **shared library visible to other users**.

**BUT:** the earlier draft answered "No reporting / No blocking." For an app where user-curated content is visible to others, Google/IARC generally **expects a content-report mechanism.** Two valid paths:
- **Recommended:** add a minimal **"report this tour"** action (even a mailto/report link) — small Mobile task — and answer that a reporting method exists.
- Or, if you conclude tours aren't meaningfully "exchanged with other users" (they go to a shared pool, no direct user-to-user interaction/messaging), answer **No** to the interaction question — but that must be a deliberate, accurate call, not a default.

Do **not** ship public UGC with no report path **and** a child audience (the audience is now correctly 13+, which lowers the risk, but the report path is still the cleaner answer).

## "Primarily a news or educational product?" — No (borderline)
Defensible as "primarily a tours app," **but be aware** the Audio mode (news/newsletter processing) is roughly half the app. If Google questions it, "tours primary, news secondary" is the honest framing.

---

## Notes
- **Status discipline:** don't mark a compliance questionnaire "✅ submitted/accepted" until the answers have been verified — the old draft nearly locked in the wrong Target Audience.
- Cross-check: these answers must stay consistent with **Target Audience = 13+** (see `GOOGLE_PLAY_CONSOLE_SETUP_ANSWERS_RATIONALE.md`) and the **Data Safety** mapping.
- Open item: decide on the **"report content" mechanism** (recommended small Mobile task) before relying on the "Yes" UGC answer.
