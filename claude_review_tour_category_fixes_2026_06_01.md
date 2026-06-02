# Claude.AI Code Review Request: Tour Category Classification Fixes

**Date:** 2026-06-01  
**File Changed:** `generate_tour_text.py`  
**Function:** `_classify_tour_category(location, tour_type)`  
**Commits:** `9d0ce76` (museum icon fix) + `06ba427` (walking priority fix)  
**Branch:** `services-migration`

---

## Symptom 1 (fixed in 9d0ce76)

"Medfield State Hospital, Medfield, MA" with `tour_type="museum"` generated a tour with walking icons (🚶) instead of museum icons (🏛️).

**Root cause:** `_classify_tour_category` checked `tour_type` for food keywords but only checked `location` for museum keywords. "Medfield State Hospital" doesn't contain "museum" in its name, so the function fell through to the default `return 'walking'`.

**Fix:** Added `or keyword in tour_type_lower` to the museum keyword check.

---

## Symptom 2 (fixed in 06ba427)

"walking tour in Portsmouth, NH with a stop at Strawbery Banke Museum" with `tour_type="museum"` (mobile app sends museum when the word appears anywhere in the request) generated a museum tour with only one map icon on the first stop.

**Root cause:** The fix from commit 9d0ce76 now correctly detects "museum" in `tour_type`, but this created a regression: when the user explicitly says "walking tour" in the location but mentions a museum as one stop, the function returns `museum` because the museum check fires before the walking check.

**Fix:** Added explicit walking-tour phrase detection with highest priority, before restaurant and museum checks.

---

## Current state of `_classify_tour_category`:

```python
def _classify_tour_category(location, tour_type):
    """
    Detect the appropriate tour template based on location and tour_type.
    Returns: 'restaurant', 'walking', 'museum', or 'specialized'
    """
    location_lower = location.lower()
    tour_type_lower = tour_type.lower()
    
    # EXPLICIT WALKING TOUR detection (highest priority — overrides everything)
    # If the user explicitly says "walking tour" in the location, honor that
    # even if a museum name appears as one of the stops
    explicit_walking_phrases = ['walking tour', 'walk tour', 'walking in', 'walk in']
    if any(phrase in location_lower for phrase in explicit_walking_phrases):
        return 'walking'
    
    # Restaurant/Food tour detection
    food_keywords = ['restaurant', 'food', 'dining', 'culinary', 'eat', 'cafe', 'bistro', 'eatery']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in food_keywords):
        return 'restaurant'
    
    # Museum indicators — check location first, then tour_type as fallback
    museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in museum_keywords):
        return 'museum'
    
    # Specialized tour indicators
    specialized_keywords = ['book', 'movie', 'film', 'botanical', 'garden', 'park', 'novel', 'story', 'literary', 'filming']
    if any(keyword in location_lower or keyword in tour_type_lower for keyword in specialized_keywords):
        return 'specialized'
    
    # Walking tour indicators (default for cities, neighborhoods)
    walking_keywords = ['city', 'downtown', 'neighborhood', 'district', 'street', 'avenue', 'center', 'town']
    if any(keyword in location_lower for keyword in walking_keywords):
        return 'walking'
    
    # Default to walking tour
    return 'walking'
```

---

## Context: How this function is called

`_classify_tour_category` is called as a **fallback** when the S15 intent analysis doesn't force a category. The S15 logic (lines 547-556) handles the case where intent analysis finds a `venue_name`:

```python
if intent.get('venue_name') and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location):
    tour_category = 'museum'  # S15 forced
else:
    tour_category = _classify_tour_category(location, tour_type)  # Fallback
```

The `_EXPLICIT_NON_MUSEUM_TOUR_RE` regex catches phrases like "walking tour", "restaurant tour", etc. — so for the Portsmouth case, S15 correctly says "override the museum venue name" and falls through to `_classify_tour_category`. Our fix then ensures the fallback also respects "walking tour" in the location.

---

## Questions for Review

1. **Is the priority order correct?** Current: walking-explicit > restaurant > museum > specialized > walking-implicit > default-walking. Should restaurant also have explicit phrase detection like walking does? (e.g., "restaurant tour near the MFA" should be restaurant, not museum)

2. **Edge case: "museum walking tour"** — The phrase "walking tour" appears, so it returns `walking`. But a user requesting "walking tour of the MFA" probably wants museum-style exhibits with walking icons between them. Is this acceptable, or should we detect "of the [museum]" as a modifier?

3. **Should `_classify_tour_category` also check for explicit restaurant phrases** like "restaurant tour" or "food tour" with the same highest-priority pattern as walking? Currently food keywords have second priority.

4. **The mobile app always sends `tour_type` as either "walking" or "museum"** based on keyword detection in the request string. Should the mobile app send a more neutral default (e.g., "auto") and let the services decide the category entirely? This would eliminate the entire class of "mobile guesses wrong" bugs.

---

## Test Cases That Now Pass

| Request String | tour_type from mobile | Expected Category | Result |
|---|---|---|---|
| "Medfield State Hospital, Medfield, MA" | museum | museum | ✅ |
| "walking tour in Portsmouth, NH with a stop at Strawbery Banke Museum" | museum | walking | ✅ |
| "the old manse house-museum, Concord, MA" | museum | museum | ✅ (S15 forces it) |
| "Boston Common, Boston, MA" | walking | walking | ✅ |
| "MFA Boston" | museum | museum | ✅ |
| "restaurant tour in North End, Boston" | walking | restaurant | ✅ |
