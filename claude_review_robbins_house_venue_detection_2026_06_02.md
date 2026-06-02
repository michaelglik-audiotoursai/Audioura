# Claude.AI Review — Robbins House Venue Detection Failure

**Date:** 2026-06-02  
**Request:** "tour in Robbin's House and Monument Square museum in Concord, MA" — 8 POIs  
**Result:** Generated 8 Concord landmarks (Walden Pond, Old Manse, etc.) instead of exhibits inside The Robbins House  
**Branch:** `services-migration`

---

## Diagnosis

The intent analysis returned:
```json
{
    "venue_name": null,
    "geographic_scope": "Robbin's House and Monument Square museum",
    "scope_precision": "DISTRICT"
}
```

Because `venue_name` is null, the single-venue museum constraint was skipped:
```
[Museum constraint] No venue_name from intent — single-venue constraint skipped
```

The S17 scope constraint was injected ("Do NOT include landmarks outside Robbin's House and Monument Square museum"), but OpenAI treated it as an area/district and generated famous Concord-wide landmarks.

---

## Why this happened

1. **The "and" in the name** confused the intent analysis. "Robbin's House AND Monument Square museum" looks like two separate places, not one museum name. The AI classified it as `scope_precision: "DISTRICT"` rather than a single venue.

2. **The museum is very small.** The Robbins House at Monument Square is a tiny historic house museum with 2-3 rooms about African American history in Concord. Asking for 8 POIs inside it is unrealistic — there aren't 8 distinct exhibits. Even if venue_name had been detected, the PHASE 3A prompt asking for "8 specific museum exhibits" would likely hallucinate.

3. **PHASE 5.5b didn't fire** because `venue_name` was null (it only runs when `tour_category == 'museum' and _museum_venue_name`).

---

## Questions for Claude

1. **Should the intent analysis be more aggressive about detecting single venues?** The phrase "tour IN Robbin's House" (with "in" indicating a single interior space) is a strong signal. But "tour in Harvard Square and MIT campus" should NOT be treated as a single venue. How do we distinguish?

2. **Should we cap total_stops for small museums?** If the venue is a single historic house (vs. a large museum like the MFA), 8 stops is unrealistic. Should the system detect "small venue" and cap stops at 3-4 automatically? Or is this the user's responsibility to request a reasonable number?

3. **Is this worth fixing now?** The user would get correct results by requesting "Robbins House museum, Concord, MA" (without "and Monument Square"). The failure mode is: multi-place phrasing in the request confuses venue detection. This is an AI prompt engineering challenge, not a code bug per se.

4. **Fallback strategy:** When the AI generates stops that are all outside the requested scope (like Walden Pond for a "Robbins House" request), should there be a post-generation check that measures "what % of generated stops are actually inside the scope area?" If >50% are outside, regenerate with tighter constraints?

---

## What was NOT changed

No code fix applied. This is an intent-analysis limitation that requires either:
- Better prompt engineering for the intent analysis (risky — could break multi-venue cases)
- A post-generation geographic validation (new feature)
- User education (request specific venue names without "and" multi-place phrasing)

Filed for review — not blocking Phase B.
