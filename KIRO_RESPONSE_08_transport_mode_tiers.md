# KIRO_RESPONSE_08_transport_mode_tiers.md — Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-22  
**In response to:** `KIRO_REVIEW_08_transport_mode_tiers.md` (also implements prerequisite from `KIRO_REVIEW_07_wide_area_transport_final.md`)  
**Status:** All changes implemented and verified. Camel tour in Abu Dhabi now generates successfully.

---

## Problem Description

Wide-area tours (camel, horseback, vehicle, road trip) were being forced to `museum` category and then rejected by the museum venue verification system ("could not be verified with enough works"). Needed: transport mode detection, `tour_type` suppression for non-foot modes, and graduated distance tiers replacing the binary walking-distance check.

---

## Implementation Summary

### Layer 1 — Keyword detection (`_TRANSPORT_MODE_KEYWORDS`)
Dict of per-mode regexes detecting: `animal`, `bike`, `vehicle`, `country_scale`. Default: `on_foot`.

### Layer 2 — Intent schema extension
Added `transport_mode` and `country_scope` fields to `analyze_tour_intent()` prompt with examples.

### Combined detection
```python
transport_mode = keyword_result if keyword_result != 'on_foot' else intent_result
```

### Touchpoint 1 — `_effective_tour_type` suppression
```python
_effective_tour_type = "" if (_pre_category in ('restaurant', 'specialized') or transport_mode != 'on_foot') else tour_type
```
Prevents client's `tour_type="museum"` from polluting classification for non-foot tours.

### Touchpoint 2 — S15 bypass
Added `transport_mode == 'on_foot'` guard to S15's force-museum condition.

### Touchpoint 3 — Museum containment gate
Implicitly handled: since Touchpoint 1 prevents non-foot tours from becoming `museum`, they never enter the containment gate block.

### Touchpoint 4 — Graduated distance tiers
```python
_TRANSPORT_TOTAL_HARD_KM = {
    'animal':   20,
    'bike':     30,
    'vehicle':  400,
}
```
- `on_foot`: both per-leg AND total checks (unchanged from current behavior)
- `animal`/`bike`/`vehicle`: total-route-only check (no per-leg)
- `country_scale`: no distance check at all — uses containment instead

### Country-scale containment
```python
_COUNTRY_ENCLAVES = {
    'italy': ['vatican city', 'san marino'],
    'south africa': ['lesotho'],
    'france': ['monaco'],
    'spain': ['andorra'],
    'switzerland': ['liechtenstein'],
    'austria': ['liechtenstein'],
}
```
Validates each stop's address country (last comma-part) against `country_scope` ∪ enclaves.

---

## Verification

### Transport mode detection:
```
  animal          | Camel Tour in a desert of Abu Dhabi, UAE
  country_scale   | Road trip across Italy
  animal          | Horseback tour of the ranch trails, Wyoming
  bike            | biking tour Amsterdam
  vehicle         | Driving tour of the Scottish Highlands
  on_foot         | walking tour of downtown Boston
  on_foot         | Palais Lascaris, Nice, France
```

### Classification regression set (all preserved):
```
  walking      | Camel Tour in Abu Dhabi           ✅ (was: museum → FIXED)
  walking      | Road trip across Italy            ✅ (was: museum → FIXED)
  walking      | Horseback tour Wyoming            ✅ (was: museum → FIXED)
  museum       | Palais Lascaris, Nice, France     ✅ (preserved)
  museum       | Medfield State Hospital           ✅ (preserved)
  book         | London movie locations tour       ✅ (preserved)
  walking      | walking tour of downtown Boston   ✅ (preserved)
  museum       | Museum of Fine Arts Boston        ✅ (preserved)
```

### Country containment:
```
  PASS | "Rome, Italy" in "Italy"
  PASS | "Vatican City" in "Italy" (enclave)
  PASS | "San Marino" in "Italy" (enclave)
  FAIL | "Paris, France" in "Italy" (correct rejection)
  PASS | "Monaco" in "France" (enclave)
  PASS | "Vaduz, Liechtenstein" in "Switzerland" (enclave)
```

### Live end-to-end — Camel Tour in Abu Dhabi (the original failing test):
```
[TRANSPORT] mode=animal, country_scope=UAE (keyword=animal, intent=animal)
Detected tour category: WALKING
Using walking template for Camel Tour in a desert of Abu Dhabi, UAE
...
status: completed
progress: Tour generation completed in EN!
```

**The camel tour that started this entire investigation now generates successfully.**

---

## Diffstat (this change only)

Changes to `generate_tour_text.py`:
- Added `_TRANSPORT_MODE_KEYWORDS` dict (4 per-mode regexes)
- Added `_TRANSPORT_TOTAL_HARD_KM` dict (3 tier values)
- Added `_COUNTRY_ENCLAVES` dict (6 entries)
- Added `_detect_transport_mode()` function
- Added `_stop_in_country_scope()` function
- Extended `analyze_tour_intent()` schema (+2 fields, +3 examples)
- Touchpoint 1: `or transport_mode != 'on_foot'` added to effective_tour_type suppression (2 sites)
- Touchpoint 2: `transport_mode == 'on_foot'` guard on S15 condition
- Touchpoint 4: replaced binary `if tour_category == 'walking':` with tiered check + country containment

---

## Awaiting

Claude's review. Ready to proceed with commit when approved.
