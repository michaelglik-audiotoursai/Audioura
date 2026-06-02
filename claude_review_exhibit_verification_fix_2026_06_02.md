# Claude.AI Code Review Request: Museum Exhibit Verification Fix

**Date:** 2026-06-02  
**File Changed:** `generate_tour_text.py`  
**Functions:** `_validate_museum_stop_descriptions()` + PHASE 5 description prompt  
**Commit:** `50c61d6`  
**Branch:** `services-migration`  
**Based on:** `claude_investigation_exhibit_verification_gap_2026_06_01.md`

---

## What was implemented

Both of Claude's recommended fixes from the investigation doc:

### Fix 1 (§4.1): Check ALL stops on single-venue museum tours

**Before:**
```python
suspect = [p for p in candidates if _is_suspect(p.get('name', ''))]
clean = [p for p in candidates if not _is_suspect(p.get('name', ''))]
```

**After:**
```python
# Single-venue museum tours: verify EVERY stop's description is inside the venue.
if len(candidates) <= 12:
    suspect = list(candidates)
    clean = []
else:
    # Fallback to name-based pre-filter only for unusually large tours (cost guard)
    suspect = [p for p in candidates if _is_suspect(p.get('name', ''))]
    clean = [p for p in candidates if not _is_suspect(p.get('name', ''))]
```

The cost guard threshold (12 stops) means typical tours (3-8 stops) always get full verification, while pathologically large tours fall back to the name-based pre-filter.

### Fix 2 (§4.2): Venue containment constraint in PHASE 5 description prompt

Added to the description generation prompt (conditionally for single-venue museum tours):

```python
if tour_category == 'museum' and _museum_venue_name:
    description_prompt += f"""
CRITICAL CONSTRAINT: Every stop MUST be a room, gallery, exhibit, or area physically 
located INSIDE '{_museum_venue_name}'. Do NOT include artifacts, collections, or rooms 
that are housed at any other institution, even if thematically related to the same 
person or topic. If '{poi_name}' is not actually inside '{_museum_venue_name}', describe 
what IS at that location within the venue instead.
"""
```

This is defense-in-depth: the prompt makes OpenAI less likely to generate out-of-venue content in the first place, and the PHASE 5.5b check catches anything that slips through.

---

## Test Results

Generated "the old manse house-museum, Concord, MA" with 4 stops.

New run produced: Emerson Study, Alcott Parlor, Hawthorne's Bedroom, Thoreau's Desk

- "Emerson Study" — ✅ legitimate (Emerson lived and worked at The Old Manse)
- "Alcott Parlor" — ✅ legitimate (Alcott family connection to The Old Manse)
- "Hawthorne's Bedroom" — ✅ legitimate (Hawthorne lived at The Old Manse 1842-1845, wrote "Mosses from an Old Manse" there)
- "Thoreau's Desk" — ⚠️ borderline (Thoreau visited and briefly stayed, but his famous desk artifacts are primarily at Concord Museum)

The previous run (before fix) had "Thoreau's Bedroom" with personal artifacts explicitly described as "on display" — that was clearly wrong. The new generation is more cautious ("Thoreau's Desk" as a writing spot vs. "Thoreau's Bedroom with artifacts on display").

---

## Questions for Review

1. **Is the 12-stop threshold appropriate for the cost guard?** Current tours are 3-8 stops. The threshold exists to prevent a hypothetical large-tour request from making 20+ GPT calls. Is 12 the right number, or should it be higher/lower?

2. **Should §4.3 (accept shorter tour if stops are removed) be explicitly implemented?** Currently the code already handles this — PHASE 5.5b removes bad stops and the tour continues with fewer. But there's no explicit log/warning when the tour has fewer stops than requested due to removal.

3. **The "Thoreau's Desk" edge case:** The verification likely asked "is Thoreau's Desk inside The Old Manse?" and GPT said yes (Thoreau did live there briefly). This is a harder hallucination to catch — the desk may have been there historically, even if it's now at Concord Museum. Is this an acceptable level of accuracy, or do we need temporal awareness ("is this exhibit CURRENTLY displayed there")?

4. **Should `_is_suspect()` be removed entirely?** It's currently dead code for tours ≤12 stops. Keeping it adds no value if we always check all stops. Remove for clarity?

---

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | Lines ~415-425: Replace name-only pre-filter with check-all-stops (with 12-stop cost guard). Lines ~1380-1390: Add venue containment constraint to PHASE 5 description prompt for museum tours. |
