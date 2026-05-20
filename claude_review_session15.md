# Claude.AI Review — Session 15: Fairbanks House Museum Category Fix

**Branch:** `Tours_Step_Maps`
**Base branch:** `Newsletters`
**Merge target:** `Newsletters` (pending this review + mobile test)

**Commit in this review:**
| Commit | Description |
|--------|-------------|
| `1e9a718` | Fix: venue_name from PHASE 1 forces museum category; remove unconditional classifier override at PHASE 2 (Fairbanks House bug) |

**File changed:**
- `generate_tour_text.py` → container `development-tour-generator-1:5000`

**Previous review doc:** `claude_review_final_session14.md` (13 changes, all reviewed and applied)

---

## Problem Identified During Testing

**Test input (Android device):**
```
"Fairbanks House Tour in Dedham, ma"
tour_type = "museum"   ← sent by mobile app
total_stops = 4
```

**Expected result:** Museum tour with stops inside the Fairbanks House (rooms, exhibits, historical features of the building itself).

**Actual result:** Walking tour of Dedham, MA — stops were separate buildings and landmarks around the town, not inside the Fairbanks House.

**Tour ID generated:** 288 (walking tour — incorrect)

---

## Root Cause Analysis

Two compounding issues were found in the container logs:

### Issue 1 — Bug2Fix suppressed `tour_type="museum"` from mobile

The `_pre_category` guard (introduced in Session 4) was designed to prevent the mobile app's hardcoded `tour_type="museum"` from polluting the intent analysis prompt. It computes the category from the location string alone (no `tour_type`), then suppresses `tour_type` from the PHASE 1 prompt if `_pre_category != 'museum'`.

```
[Bug2Fix] tour_type='museum' suppressed (pre_category='walking')
```

The location string `"Fairbanks House Tour in Dedham, ma"` contains no museum keywords (`museum`, `gallery`, `mfa`, `moma`, `exhibition`, `collection`, `art center`, `cultural center`). So `_pre_category = 'walking'` and the mobile's `tour_type="museum"` was suppressed from the PHASE 1 prompt.

This is correct behaviour for the Bug2Fix guard — the mobile app does hardcode `tour_type="museum"` for all museum requests, and the guard exists to prevent that from contaminating intent analysis. The guard is not the bug.

### Issue 2 — Unconditional `_classify_tour_category()` call at PHASE 2 overwrote the correct result

After PHASE 1, `analyze_tour_intent()` correctly identified `venue_name = "Fairbanks House"` — GPT recognised this as a single-venue historic house tour. This is the authoritative signal.

However, the code at PHASE 2 then called `_classify_tour_category(location, tour_type)` **unconditionally**, overwriting whatever PHASE 1 had established:

```python
# BEFORE FIX (buggy code at line 507):
tour_category = _classify_tour_category(location, tour_type)
```

`_classify_tour_category` is a keyword-matching function. Its museum keyword list is:
```python
museum_keywords = ['museum', 'gallery', 'mfa', 'moma', 'exhibition', 'collection', 'art center', 'cultural center']
```

`"Fairbanks House Tour in Dedham, ma"` contains none of these keywords → classifier returns `'walking'`.

```
Detected tour category: WALKING
```

The `venue_name` signal from PHASE 1 was completely ignored. The tour was generated as a walking tour of Dedham.

### Why the keyword classifier cannot solve this

Historic houses, estates, and named buildings are a large and open-ended category:
- Fairbanks House, Dedham MA
- Lyman Estate, Waltham MA
- Codman Estate, Lincoln MA
- Longfellow House, Cambridge MA
- Adams National Historical Park, Quincy MA

None of these contain `museum`, `gallery`, or any other keyword in the classifier list. Expanding the keyword list with `house`, `estate`, `homestead`, `mansion` would cause false positives for walking tours (e.g. `"walking tour near the Old State House, Boston"` would be misclassified as museum).

**The correct signal is already available:** PHASE 1 GPT intent analysis returns `venue_name` when the tour is inside a single named building. This is the authoritative determination. The keyword classifier is a fallback for when PHASE 1 is unavailable or returns no venue.

---

## Fix Applied

**File:** `generate_tour_text.py`
**Commit:** `1e9a718`

### Before (buggy):

```python
        elif raw_venue:
            print(f"  [venue_name sanity] '{raw_venue}' OK")
        
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        tour_category = _classify_tour_category(location, tour_type)
    
    # PHASE 2: Detect tour type and get appropriate template
    tour_category = 'intelligent'                                    # ← dead assignment, immediately overwritten
    tour_category = _classify_tour_category(location, tour_type)    # ← unconditional override — BUG
    print(f"\nDetected tour category: {tour_category.upper()}")
```

### After (fixed):

```python
        elif raw_venue:
            print(f"  [venue_name sanity] '{raw_venue}' OK")

        # If PHASE 1 identified a specific venue, this is definitively a single-venue
        # museum tour — override the keyword classifier which cannot know every historic
        # house, mansion, or named building (e.g. "Fairbanks House", "Lyman Estate").
        tour_category = 'museum' if intent.get('venue_name') else _classify_tour_category(location, tour_type)
    else:
        print("⚠️ Intent analysis failed, using fallback detection")
        intent = None
        tour_category = _classify_tour_category(location, tour_type)

    # PHASE 2: Detect tour type and get appropriate template
    # NOTE: tour_category already set above — do NOT call _classify_tour_category again here
    # (that was the bug: it overwrote the venue_name-based 'museum' decision with 'walking').
    print(f"\nDetected tour category: {tour_category.upper()}")
```

**Two changes in one commit:**
1. Replaced the unconditional `_classify_tour_category()` call with a conditional: `'museum' if intent.get('venue_name') else _classify_tour_category(location, tour_type)`
2. Removed the dead `tour_category = 'intelligent'` assignment that was immediately overwritten

---

## Pipeline Impact

The fix affects PHASE 2 only. Downstream behaviour when `venue_name` is set:

| Phase | Behaviour (unchanged) |
|-------|-----------------------|
| PHASE 3A | Museum constraint injected: `"All stops must be inside {venue_name}"` |
| PHASE 4 | Skipped for `tour_category == 'museum'` |
| PHASE 3C | Skipped for single-venue museum tours (address guard not applicable) |
| PHASE 5.5b | `_validate_museum_stop_descriptions()` runs — validates stops are inside venue |
| PHASE 6 | `Tour-Category: museum` written to file header → 🏛️ icon in mobile app |

The fix restores the intended flow: PHASE 1 GPT analysis is authoritative; keyword classifier is fallback only.

---

## Regression Risk

**Walking tours:** `intent.get('venue_name')` returns `None` for walking tours (GPT correctly returns `venue_name: null` when the tour covers multiple locations). The classifier runs as before. No regression.

**Restaurant tours:** Same — `venue_name` is null for multi-stop restaurant tours. No regression.

**Named museum with "museum" in the name (e.g. "Museum of Fine Arts, Boston"):** `_classify_tour_category` would have returned `'museum'` anyway. The fix produces the same result via a different path. No regression.

**PHASE 1 failure (intent = None):** The `else` branch still calls `_classify_tour_category(location, tour_type)` as before. No regression.

**`_venue_matches_location` sanity check discards venue_name:** If the sanity check fires and sets `intent['venue_name'] = None`, then `intent.get('venue_name')` returns `None` → classifier runs. This is correct — if the venue name has no word overlap with the location, it's likely a GPT hallucination and we should not force museum category.

---

## Test Results

**Before fix (tour ID 288):** Walking tour of Dedham — stops were separate buildings around town.

**After fix (pending mobile test):** Expected:
- `tour_category = museum`
- `venue_name = "Fairbanks House"` (or similar)
- Museum constraint injected in PHASE 3A: all stops inside Fairbanks House
- PHASE 5.5b validates stops are inside the venue
- 🏛️ icon in mobile app
- Single map pin at Fairbanks House address (not per-stop pins)

**System test to run:**
```
Location: "Fairbanks House Tour in Dedham, ma"
tour_type: "museum"
total_stops: 4
Expected: tour_category=museum, stops = rooms/exhibits inside Fairbanks House
```

---

## Questions for Claude

**Q1 — Should `_pre_category` also use `venue_name` to set category?**

Currently `_pre_category` is computed before PHASE 1 using `_classify_tour_category(location, "")`. It is used only to decide whether to suppress `tour_type` from the PHASE 1 prompt (Bug2Fix guard). After the S15 fix, `tour_category` is set correctly after PHASE 1. But `_pre_category` is still computed and still suppresses `tour_type="museum"` from the PHASE 1 prompt for historic houses.

Is this a problem? The argument for "no problem": PHASE 1 receives the location string `"Fairbanks House Tour in Dedham, ma"` without `tour_type`, and GPT correctly identifies `venue_name = "Fairbanks House"` from the location string alone. The `tour_type` suppression does not prevent correct identification.

Is there a case where suppressing `tour_type` from PHASE 1 would cause GPT to miss the `venue_name`? Or is the location string always sufficient?

**Q2 — Is the `venue_name → museum` mapping always correct?**

The fix assumes: if PHASE 1 returns a `venue_name`, the tour is always a museum-style single-venue tour. Are there cases where PHASE 1 might return a `venue_name` for a non-museum tour? For example:
- `"Walking tour starting at Faneuil Hall, Boston"` — GPT might return `venue_name = "Faneuil Hall"` even though the tour is a walking tour of the surrounding area.
- `"Restaurant tour near the Prudential Center, Boston"` — similar risk.

Should the fix be more conservative: `'museum' if intent.get('venue_name') and tour_type in ('museum', '')` — only force museum when the mobile app also sent `tour_type="museum"` or no tour_type? Or is the PHASE 1 prompt sufficiently constrained to only return `venue_name` for genuine single-venue tours?

**Q3 — Dead `tour_category = 'intelligent'` assignment — was it ever meaningful?**

The removed line `tour_category = 'intelligent'` was immediately overwritten by the `_classify_tour_category()` call on the next line. It appears to be a leftover from an earlier design where `'intelligent'` was a valid category. Confirmed: `'intelligent'` does not appear in any template lookup, prompt selection, or PHASE 6 output. Removing it is safe. But: is there any path in the codebase where `tour_category = 'intelligent'` could have been read before being overwritten? (e.g. a closure capturing the variable before the overwrite?)

---

## Summary

| Change | File | Commit | What | Why |
|--------|------|--------|------|-----|
| S15 | `generate_tour_text.py` | `1e9a718` | `tour_category = 'museum' if intent.get('venue_name') else _classify_tour_category(...)` at PHASE 2; removed dead `tour_category = 'intelligent'` | Keyword classifier cannot detect historic houses/estates; PHASE 1 GPT intent is authoritative when `venue_name` is returned |
