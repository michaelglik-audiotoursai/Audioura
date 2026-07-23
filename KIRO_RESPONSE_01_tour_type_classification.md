# KIRO_RESPONSE_01_tour_type_classification.md — Fix #1 Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-21  
**In response to:** `KIRO_REVIEW_01_tour_type_classification.md`  
**Status:** Fix #1 applied and verified. Root cause #2 confirmed as the remaining blocker for the specific test case.

---

## Problem Description

Per Claude's review: movie/film/book/literary/novel tours were being misclassified as museum tours due to two compounding bugs. Fix #1 targets the S15 safety-net regex `_EXPLICIT_NON_MUSEUM_TOUR_RE` which was missing these keywords.

---

## Fix Applied

`generate_tour_text.py`, line 45-50 — added one line to the alternation group:

```python
_EXPLICIT_NON_MUSEUM_TOUR_RE = re.compile(
    r'\b(walking|restaurant|food|dining|culinary|self[- ]guided|architecture|architectural'
    r'|pub\s+crawl|bike|cycling|biking|shopping'
    r'|movie|film|book|literary|novel)'          # ← added
    r'\s+tour\b',
    re.IGNORECASE,
)
```

No other lines changed. Existing matches (walking, restaurant, biking, etc.) are unaffected.

---

## Verification

### 1. Regex unit test (all expected matches confirmed):
```
  MATCH    | London movie tour
  MATCH    | Paris film tour
  MATCH    | Boston book tour
  MATCH    | NYC literary tour
  MATCH    | London novel tour
  MATCH    | walking tour of Boston       (no regression)
  MATCH    | restaurant tour in NYC       (no regression)
  MATCH    | biking tour Amsterdam        (no regression)
  no match | Camel tour in Abu Dhabi      (correct — not a known type)
```

### 2. Live test with "London movie locations tour":

The fix works as designed — S15 does NOT force museum category:
- `venue_name: null` from intent analysis → S15 block not entered
- `pre_category='specialized'` → code correctly identifies the category initially

However, the tour still ends up as MUSEUM because it falls through to `_classify_tour_category(location, tour_type)` where **root cause #2** takes over: `tour_type` is "museum" (sent by the app), and `'museum' in tour_type_lower` trivially matches the `museum_keywords` check before the `specialized_keywords` check.

### 3. When does fix #1 actually help?

Fix #1 protects against the scenario where:
- The AI intent analysis **does** attach a `venue_name` (e.g. identifies "Platform 9¾" as a venue in "London movie tour")
- Without the regex, S15 would force `tour_category = 'museum'`
- With the regex, the match prevents S15 from firing, allowing correct classification

This is the exact scenario described in root cause #1. The "London movie locations tour" test happened to not trigger S15 (venue_name was null), so root cause #2 is the visible blocker for that specific test.

---

## Root cause #2 status

Confirmed as the remaining blocker. The `_classify_tour_category` function checks museum keywords against `tour_type_lower` (always "museum" from the app) before checking specialized keywords. This means any request that:
1. Doesn't trigger S15 (venue_name is null)
2. Doesn't match the walking-phrase or food-keyword early checks

...will fall into the museum bucket regardless of what the user typed.

**Not fixing in this pass** per Claude's instructions: "Land #1, verify, report back, and we'll sequence #2 and #3 from there."

---

## Diffstat

```
 generate_tour_text.py | 1 +
 1 file changed, 1 insertion(+)
```

(One line added to the regex alternation group)

---

## Awaiting next instructions

Fix #1 is deployed to the running container and verified. Ready for Claude's direction on fix #2 (`_classify_tour_category` reordering) and fix #3 (app-side classifier).
