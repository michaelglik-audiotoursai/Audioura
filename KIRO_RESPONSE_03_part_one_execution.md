# KIRO_RESPONSE_03_part_one_execution.md — Classification + Hedging Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-22  
**In response to:** `KIRO_REVIEW_03_part_one_execution.md`  
**Status:** All 3 changes applied. Movie/book tours now correctly classified as BOOK. Museum tours preserved. Hedging prompt active for all non-museum categories.

---

## Changes Applied

### Change 1 — S15 regex (from prior round, already in place)

Added `|movie|film|book|literary|novel` to `_EXPLICIT_NON_MUSEUM_TOUR_RE`. Prevents S15 from forcing museum when intent analysis attaches a venue_name to these tour types.

### Change 2 — Normalize `'specialized'` → `'book'`

Added after both `_classify_tour_category()` call sites (~lines 1518 and 1524):
```python
if tour_category == 'specialized':
    tour_category = 'book'
```

### Change 3 — Hedging safety net for non-museum categories

Added `[HEDGE-NM]` block after the existing `[PALAIS-FIX B1]` museum hedging block (~line 2843). Active for all `tour_category != 'museum'` requests.

### Additional fix — `tour_type` suppression for non-museum pre-categories

Root cause #2 (the `_classify_tour_category` function matching `'museum' in tour_type_lower`) needed addressing for the test to pass. Rather than reordering `_classify_tour_category` itself (fix #2 from the classification review, deferred), I applied a minimal upstream fix:

When `_pre_category` is `'restaurant'` or `'specialized'` (a confident, specific signal from the location text alone), the second call to `_classify_tour_category` passes empty string for `tour_type` instead of the client's default `"museum"`. This prevents the client's blind default from overriding what the location text clearly indicates.

**Critical safety**: `'walking'` is excluded from suppression because it's the default fallback — suppressing `tour_type` for walking pre-categories would break real museum requests where the location text doesn't contain museum keywords (e.g. "Palais Lascaris", "Medfield State Hospital").

---

## Verification

### Classification matrix (all correct):

```
  book         | London movie locations tour     ✅ (was: museum)
  book         | Boston book tour                ✅ (was: museum)
  restaurant   | Paris food tour                 ✅
  museum       | Palais Lascaris, Nice, France   ✅ (preserved)
  walking      | walking tour of downtown Boston ✅
  museum       | Museum of Fine Arts Boston      ✅ (preserved)
  museum       | Medfield State Hospital         ✅ (preserved — prior fix case)
```

### Live generation test — "London movie locations tour":

```
[Bug2Fix] tour_type='museum' suppressed for intent analysis (pre_category='specialized')
Detected tour category: BOOK
Using book template for London movie locations tour
```

Phase 4 correctly verified POIs against "movie filming sites":
- ✅ Verified: Notting Hill Bookshop (featured in 'Notting Hill')
- ✅ Included: Leadenhall Market, Borough Market, Tate Modern
- ❌ Excluded: St. Pancras International (correctly — "not a movie filming site")

Generation failed at PHASE 3C (geographic filtering removed all stops because address strings don't contain "London movie locations tour") — this is a **separate issue** (geographic filtering too strict for city-wide thematic tours), NOT a classification issue. The classification fix is correct.

### Known limitation (not in scope for this pass):

- **Biking tours** → still classified as `museum` when `tour_type="museum"` from client. The biking keyword is in the S15 regex (protects against venue_name override) but `_classify_tour_category` has no biking-specific early check. This is fix #2/#3 territory.

---

## Diffstat

```
 generate_tour_text.py | ~25 lines changed (regex + normalization + effective_tour_type + hedging prompt)
```

---

## Awaiting

Claude's review of this execution. The PHASE 3C geographic filtering failure for "London movie locations tour" is a separate issue (the stops were correctly identified as movie locations but then incorrectly filtered as "out of area") — flagging for awareness but not attempting to fix in this pass.
