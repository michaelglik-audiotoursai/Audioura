# CLAIM AUDIT — LOCAL-121

**Date:** 2026-08-02  
**Agent:** Mac Mini Kiro  
**Method:** Manual reading of every named document, verbatim quoting, evidence classification.

---

## Documents swept

| Document | Claims examined | Flags raised |
|----------|----------------|--------------|
| `UNWIRED_AUDIT.md` | ~45 factual claims | 6 |
| `RETURN_BRIEFING.md` | ~30 factual claims | 3 |
| `SUBMISSION_LOCAL-95.md` | ~20 factual claims | 2 |
| `SUBMISSION_LOCAL-98.md` | ~15 factual claims | 1 |
| `SUBMISSION_LOCAL-100.md` | ~12 factual claims | 0 |
| `SUBMISSION_LOCAL-108.md` | ~18 factual claims | 1 |
| `SUBMISSION_LOCAL-110.md` | ~12 factual claims | 0 |
| `SUBMISSION_LOCAL-111.md` | ~10 factual claims | 0 |
| `SUBMISSION_LOCAL-113.md` | ~12 factual claims | 0 |
| `SUBMISSION_LOCAL-114.md` | ~10 factual claims | 0 |
| `SUBMISSION_LOCAL-115.md` | ~8 factual claims | 0 |
| `SUBMISSION_LOCAL-117.md` | ~14 factual claims | 0 |
| `SUBMISSION_LOCAL-118.md` | ~10 factual claims | 0 |
| `SUBMISSION_LOCAL-119.md` | ~12 factual claims | 0 |
| `SUBMISSION_LOCAL-120.md` | ~15 factual claims | 0 |
| `TOUR_HOOK_ANALYSIS.md` | ~12 factual claims | 0 |
| **Total** | **~255** | **13** |

`SUBSCRIBED_STATUS.md` does not exist in this worktree. Omitted.

---

## Flagged claims — Acted-Upon first

| # | Rating | File:Line | Verbatim quote | Why it overreaches | What would settle it | Notes |
|---|--------|-----------|----------------|-------------------|---------------------|-------|
| 1 | **Acted-Upon** | `UNWIRED_AUDIT.md:154` | "Blueprint never registered. Mobile persona UI sends these requests to 404." | No Dart file was checked. Zero evidence the mobile app calls this endpoint. The "Mobile persona UI" is an invention — `grep "persona" audio_tour_app/lib/` returns zero HTTP calls. | `grep -rn "persona\|/user/persona" audio_tour_app/lib/` showing a caller, or showing none. | Dispatched LOCAL-113 at inflated severity. Wiring was still correct but the priority framing ("broken user-facing feature") was wrong. Corrected in LOCAL-120 amendment. |
| 2 | **Acted-Upon** | `UNWIRED_AUDIT.md:182–183` | "The mobile app has referral UI (LOCAL-52). All requests 404." | No Dart file contains the word "referral". The citation "LOCAL-52" appears to reference a planned feature, not an existing one. No caller verified. | `grep -rn "referral" audio_tour_app/lib/` — zero hits confirms no UI exists. | Dispatched LOCAL-114 at inflated severity. Corrected in LOCAL-120 amendment. |
| 3 | **Acted-Upon** | `UNWIRED_AUDIT.md:114–115` | "Without registration, every swipe from every user returns 404. The mobile app sends these requests; they silently fail." | No swipe UI exists in the mobile app. Zero Dart files call `/user/<id>/stop-feedback` or reference swipe/like/dislike. Claim of "every user" failing implies an active user base exercising this feature. | `grep -rn "stop-feedback\|swipe\|dislike" audio_tour_app/lib/` — zero hits. | Dispatched LOCAL-112 at inflated severity. Corrected in LOCAL-120 amendment. |
| 4 | **Acted-Upon** | `UNWIRED_AUDIT.md:189` | "Share button in app is non-functional for creating new shares." | No share button exists in the mobile app. Zero Dart files call POST /tour/share or show a share icon. | `grep -rn "tour/share\|Icons.share\|share" audio_tour_app/lib/` — zero hits for share UI. | Dispatched LOCAL-110 at inflated severity. Corrected in LOCAL-120 amendment. |
| 5 | **Acted-Upon** | `SUBMISSION_LOCAL-95.md:38–44` | "Run 1: facts=38, callbacks=8, stops_w_callbacks=6/8 [...] Mean callbacks: 8.0 [...] Max stops with callbacks: 6 (fraction: 75%) [...] GATE (≥50% stops with callbacks in ≥1 run): PASS ✓" | Count produced by substring matching (any two title words appearing anywhere later = "callback"). D25 records that independent human reading found 2, 0, and 1 real callbacks across three readings. The "spread: 0" was the measurement being insensitive, not the system being consistent. | Human reading of the generated text, counting genuine narrative callbacks (not substring hits). D25 provides the correction. | Reported to Michael as clearing a 50% threshold. The "75%" was told as a fact; the method (substring matching) was only discoverable by reading the script. Limitation §2 acknowledges the cache artifact for "spread: 0" but presents it as a disclaimer rather than qualifying the headline number. |
| 6 | **Acted-Upon** | `SUBMISSION_LOCAL-98.md:90` | "Target ≥6: **MET** (all three runs at 6/6)." | D27 records that LEAD's independent generation measured 5/8, not 6/6. The "6 testable stops" denominator excluded stops 1 and 7 from the count, making "6/6" technically "6 of the 6 stops I chose to measure" — but the headline reads as "all stops carry material and period." The claim did not survive independent reproduction. | Reproduce on same code with an independent run, counting all 8 stops. D27 settles it at "5–6 of 8, improving." | The claim's framing led LEAD to report it to Michael before independent verification. D27 corrects it. The submission itself is not dishonest — it explicitly defines its denominator — but the headline number is presented more confidently than the variance supports. |
| 7 | **Acted-Upon** | `RETURN_BRIEFING.md:79` | "tour hook generator (hook field in spine never becomes audio)" | This repeats the UNWIRED_AUDIT's incorrect claim. LOCAL-118 (TOUR_HOOK_ANALYSIS) proved the hook IS consumed at `generate_tour_text.py:6091` and reaches audio via the prolog system. The module is dead (superseded), not a missing feature. | Read `generate_tour_text.py:6091` — `_tour_hook = _storied_spine.get("tour_hook", "")`. Already settled by LOCAL-118. | Told to Michael in his return briefing. The briefing was written 2026-08-01 (LOCAL-116); the correction came 2026-08-02 (LOCAL-118). Temporal sequence explains it — the claim was accurate relative to knowledge at write time — but the document was not amended when the correction landed. |
| 8 | **Misleading** | `UNWIRED_AUDIT.md:175–177` | "The mobile app calls `POST /user/persona` after onboarding (LOCAL-45/S45). [...] the WRITE endpoint (which the mobile app hits) returns 404." | Same error as #1. The mobile app does NOT call POST /user/persona. It stores persona locally. This is in the Category 2 detail section — the same claim as #1 but with the additional false specificity of "after onboarding (LOCAL-45/S45)". | Already settled by LOCAL-113 §"What the Flutter App Actually Does". | Not separately dispatched but reinforces the inflated severity of #1. Present in the un-amended body of the audit. |
| 9 | **Misleading** | `UNWIRED_AUDIT.md:325` | "6. `tour_hook_generator` — hook never becomes audio" | The hook DOES become audio via `generate_tour_text.py:6091–6199` → prolog → Stop 1 → TTS. The module is superseded, not the feature. | Already settled by TOUR_HOOK_ANALYSIS §2. | Listed in the "8 UNWIRED findings" summary. The amendment at top corrects it, but the body still states it as a finding. |
| 10 | **Misleading** | `SUBMISSION_LOCAL-95.md:130` | "The \"spread: 0\" is real but an artifact of caching, not a genuine measurement of variation." | This is in the Limitations section, which is good — but the headline evidence section (line 42) presents "Mean distinct facts: 38.0 (spread: 0)" without qualification. The limitation acknowledges the artifact; the evidence section doesn't. A reader who stops at the evidence table gets a false impression of consistency. | Run with cache busted. Already acknowledged in the limitation but not in the headline number. | Not dispatched as a task, but the unqualified "spread: 0" in the evidence section contributed to LEAD's confidence when reporting the callback count to Michael. |
| 11 | **Misleading** | `SUBMISSION_LOCAL-108.md:19–20` | "Three Flask Blueprints (`persona_bp`, `referral_bp`, `sharing_bp`) are defined, correct, and never registered — identical to the LOCAL-106 `register_preference_routes` pattern." | The detection is correct. The word "identical" implies the same severity (user-facing breakage). In fact, persona/referral/sharing had no mobile caller — unlike register_preference_routes which at least had a plausible near-future caller (swipe mechanism was being built). The "identical" framing carries the severity claim implicitly. | Check whether each endpoint has an active caller. LOCAL-120 settles it. | This is the summary of LOCAL-108 that LEAD read. The framing contributed to dispatching all four wiring tasks at equal priority. |
| 12 | **Harmless** | `RETURN_BRIEFING.md:79` | "spine quality scorer (wired as a gate with threshold 2, max 1 retry — it never fires on real spines since all score ≥3)" | Contradicts its own sentence framing: introduced under "Still unwired (lower severity)" but then describes it as wired with a threshold and retry logic. This is confusing, not wrong — LOCAL-111 wired it. The sentence is structurally garbled: it belongs in the "fixed" list, not the "still unwired" list. | Read LOCAL-111 — confirms it IS wired. | No action dispatched from this. The reader (Michael) might be confused about whether it's wired or not. |
| 13 | **Harmless** | `UNWIRED_AUDIT.md:119–123` | "**Proposed task:** Wire `register_preference_routes(app)` call in `generate_tour_text_service.py` or `tour_orchestrator_service.py` (whichever hosts the user-facing API for the mobile app). Verify with a live `POST /user/<id>/stop-feedback` → 200 test." | The parenthetical "whichever hosts the user-facing API for the mobile app" implicitly assumes the mobile app calls this endpoint. The register_preference_routes function WAS correctly wired, so the task proposal was sound — but the framing again bundles the assumption that users are hitting 404s. | Already settled by LOCAL-112 (wired) and LOCAL-120 (severity correction). | Harmless because the wiring was still the right call — just at wrong priority. |

---

## Positive examples (honest hedging that should be preserved)

These show the behavior the project wants:

1. **SUBMISSION_LOCAL-100.md:169** — "Stop 7 (Kannon à mille bras) is always THIN. [...] The corpus for this work appears to lack structured catalogue data." Honest about a gap, does not overclaim a fix.

2. **SUBMISSION_LOCAL-113.md, §"What the Flutter App Actually Does"** — "Critical finding: The mobile app does NOT call `/user/persona`." This submission discovered and reported the overstatement in the audit it was implementing. Exactly right behavior.

3. **SUBMISSION_LOCAL-95.md:128–130** — Limitations section explicitly flags the "spread: 0" artifact and the cache-driven determinism. The problem is headline-vs-limitation placement, not dishonesty.

4. **SUBMISSION_LOCAL-100.md:84–97** — "Fact coverage — settles D27" section gives per-run, per-stop detail and acknowledges the prior claim differently measured. Transparent.

5. **RETURN_BRIEFING.md:181–196** — "Corrections to prior reporting" section. Proactively tells Michael which earlier claims were wrong. This is the gold standard.

6. **D25 (DECISIONS.md:519–547)** — LEAD admits "I generalised from two real examples to a count produced by substring matching. That is the same error I have bounced others for [...] and made myself twice before." Self-correction with method diagnosis.

---

## Summary statistics

- **Documents swept:** 16 (all named in scope except `SUBSCRIBED_STATUS.md` which does not exist)
- **Total claims examined:** ~255
- **Flags raised:** 13 (5.1% flag rate)
- **Acted-Upon:** 7
- **Misleading:** 4
- **Harmless:** 2

---

## Pattern analysis

All 13 flags fall into exactly 3 patterns:

### Pattern A: Absence of callers presented as "users hit 404" (flags 1–4, 8, 11, 13)

The audit found correct detections (zero importers) and inferred user-visible impact without verifying the client. Seven of 13 flags are this single pattern. It was already diagnosed in LOCAL-120 and D31/D33.

### Pattern B: A count from pattern matching reported as a measurement (flags 5, 6, 10)

The callback counter used substring matching; the fact-coverage counter used a non-standard denominator. Both were reported as headline numbers without the method's limitations being visible at the same level.

### Pattern C: A corrected claim that was not amended in all locations (flags 7, 9, 12)

LOCAL-118 corrected "hook never becomes audio" but the RETURN_BRIEFING (written before the correction) still says it. The UNWIRED_AUDIT body still lists it as finding #6 even though the amendment at top corrects it.

---

## What the ratio tells us

Flag rate: 13 of ~255 claims examined = **5.1%**.

This is notably low. The majority of submissions carry honest limitations sections, explicit caveats about what was not verified, and direct statements of uncertainty. The problems cluster in two documents (UNWIRED_AUDIT's original body, SUBMISSION_LOCAL-95) and one temporal gap (RETURN_BRIEFING written before LOCAL-118's correction). The rest of the record is conservative and self-correcting — often more cautious than necessary.

The Acted-Upon flags (7 of 13) all share a single root cause: inferring user-facing impact from server-side absence without checking the client codebase. This failure mode has now been diagnosed (LOCAL-120), codified in a checklist (UNWIRED_AUDIT amendment), and recorded as a decision (D31). The risk of recurrence is low because the checklist exists and three subsequent submissions (LOCAL-113, LOCAL-118, LOCAL-120) demonstrate the corrected behavior.
