# Claude.AI Code Review — PHASE 5.6 Scope Containment + Venue Promotion

**Date:** 2026-06-02  
**File:** `generate_tour_text.py`  
**Commit:** `8f18d3a`  
**Branch:** `services-migration`  
**Based on:** `claude_response_robbins_house_venue_detection_2026_06_02.md`

---

## What was implemented

Both of Claude's recommended fixes:

### Fix 1: PHASE 5.6 — `_validate_stops_within_scope()` (~70 lines)

A post-generation containment guard that verifies each stop is physically inside the requested scope. Runs when:
- The request has a tight geographic scope (BUILDING or DISTRICT precision)
- The museum guard (PHASE 5.5b) did NOT run (because venue_name was null)

For each stop (except stop 0, kept unconditionally), asks GPT:
> "Is '{stop_name}' physically located INSIDE '{scope_name}'? A stop in the same town but OUTSIDE is NOT inside."

Removes stops that GPT confirms are outside scope with medium/high confidence. Keeps stops on low confidence (don't over-remove).

### Fix 4: Venue Promotion (~15 lines)

When `venue_name` is null but:
- Request uses interior preposition ("in", "inside", "within", "of")
- Geographic scope ends in an institutional building noun (museum, house, gallery, library, homestead, mansion, estate, manse)
- Scope precision is BUILDING or DISTRICT

→ Promotes the scope to `venue_name`, allowing PHASE 5.5b (single-venue museum guard) to fire.

This does NOT promote district nouns (square, campus, area) — so "tour in Harvard Square and MIT campus" stays as a district (no promotion).

---

## Test Results

**Request:** "tour in Robbins House and Monument Square museum in Concord, MA" — 4 POIs

**Before fix:** Walden Pond, The Old Manse, Minute Man Park, Concord Museum, Orchard House, Emerson House, Sleepy Hollow Cemetery, North Bridge — ALL wrong, none inside Robbins House.

**After fix:**
- Venue promotion fired: `[venue promotion] scope 'Robbins House and Monument Square museum' promoted to venue_name`
- PHASE 5.5b ran (single-venue museum constraint)
- Result: 3 stops — "Robbins House Exhibit", "Monument Square Gallery", "Emerson-Thoreau Collection"
- Stop count warning correctly issued: "requested 4, delivered 3"

---

## Questions for Review

1. **Should PHASE 5.6 also run when the museum guard DID fire but the scope constraint was also injected?** Currently it only runs when 5.5b didn't fire. Could there be cases where both should run?

2. **The venue promotion uses `split()[-1]` to check the trailing word.** This works for "Monument Square museum" (last word = "museum") but would fail for "Robbins House Art Museum" (last word = "Museum" ✅) or "Robbins House Museum of Art" (last word = "Art" ✗). Should we check any word in the last 2-3 words instead?

3. **Cost:** Each stop check is one GPT-3.5-turbo call (~60 tokens). For a 4-stop tour that's 3 additional API calls (~$0.0003 total). Acceptable?

4. **The `_EXPLICIT_NON_MUSEUM_TOUR_RE` regex check runs AFTER venue promotion.** So "walking tour in Robbins House museum" would: promote venue → but then get overridden by the walking-tour regex. Is this the correct priority order?

---

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `_validate_stops_within_scope()` function (~70 lines). Added venue promotion logic (~15 lines after venue_name sanity check). Added PHASE 5.6 call site after PHASE 5.5b. |
