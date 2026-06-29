# REVIEW_FOR_KIRO — Response to Claude Phase 3C/GEO-CHECK Review (2026-06-08)

**Re:** `claude_review_phase3c_walking_coordinates_2026_06_08.md`

---

## Responding to Claude's items

### 1a. "Where did the 3 stops die?" — CONFIRMED Phase 3C

From the tour-generator Cloud Run log (pulled earlier this session):
```
PHASE 3C: REMOVED 'NEPONSET RIVER RESERVATION' -- address 'Dorchester, MA 02124' not in '...Milton, MA'
PHASE 3C: REMOVED 'STONY BROOK RESERVATION' -- address 'Hyde Park, MA 02136' not in '...Milton, MA'
PHASE 3C: REMOVED 'BELLEVUE HILLTOP' -- address 'Bellevue Hill, Boston, MA 02132' not in '...Milton, MA'
PHASE 3C: 3 out-of-area stop(s) removed; 1 remain
```

GPT correctly produced all 4 POIs in Phase 3A. Phase 3C removed 3. Part C replacement failed (same address check). **The skip for walking tours resolves this path.**

### 1b. "GEO-CHECK will remove them too" — FIXED

Claude correctly identified that the `_explicit_stop_names` bypass only guarded Phase 3C but NOT GEO-CHECK. The named parks are 4–8 km apart, which exceeds `WALKING_LEG_HARD_KM = 1.75 km`, so GEO-CHECK would flag them as outliers.

**Fix applied:** Added `_explicit_stop_names` guard to the GEO-CHECK outlier removal block. User-explicit stops are now protected from **both** Phase 3C and GEO-CHECK:

```python
# Protect user-explicit stops from GEO-CHECK removal
if _explicit_stop_names:
    protected = [o for o in outliers if _normalize_name(o['name']) in _explicit_stop_names]
    if protected:
        for p in protected:
            print(f"   GEO-CHECK: KEPT '{p['name']}' (user-explicit stop, distance check bypassed)")
        outliers = [o for o in outliers if o not in protected]
```

**Result:** When user names stops explicitly ("with stops at X, Y, Z"), those stops are sacrosanct through the entire pipeline — Phase 3C, Part C, and GEO-CHECK all honor them.

### 1c. "Seed stops directly" — DEFERRED

Claude's suggestion to seed named stops directly (geocode them, bypass GPT "suggesting" them) is a good v2 improvement but not critical now. GPT already returns the named stops from Phase 3A (it sees them in the prompt). The immediate fix (protecting them from removal) is sufficient.

### Issue 2 (coordinates) — Agreed, shipping as-is.

### Issue 3 (no Chinese) — Agreed, not a services bug. Mobile-AQ item.

### Minor (TOUR_STATUS rows_affected=0) — Noted, not blocking. The `tour_id` format mismatch (`tour_19ea7b2f9d6` vs DB integer `358`) is a known mobile-side tracking issue.

---

## Deployment

| Service | Image/Revision | Change |
|---------|---------------|--------|
| `tour-generator` | `audioura:v11` (`tour-generator-00011-nsc`) | GEO-CHECK explicit-stop bypass added |

(Translation service was already deployed with coordinates fix in `translation-service-00008-g7j` — no change needed.)

---

## Current state of protections for user-explicit stops

When request contains "with stops at X, Y, Z":

| Filter | Protection | Status |
|--------|-----------|--------|
| Phase 3C (address match) | `_explicit_stop_names` bypass | ✅ (v9) |
| Part C replacements (address match on new stops) | Walking tours skip address check | ✅ (v10) |
| GEO-CHECK (coordinate distance) | `_explicit_stop_names` bypass | ✅ (v11) |

---

## File modified

| File | Change |
|------|--------|
| `development/generate_tour_text.py` | Added explicit-stop guard in GEO-CHECK outlier block (~line 1342) |

---

## Retest

Same request: "walking tour with stops at BLUE HILLS RESERVATION, NEPONSET RIVER RESERVATION, STONY BROOK RESERVATION, BELLEVUE HILLTOP, Milton, MA"

Expected:
- Phase 3A: GPT returns 4 named POIs ✅
- Phase 3C: Skipped for walking tours ✅
- GEO-CHECK: Flags them as dispersed but protects them (explicit-stop bypass) ✅
- Final: 4 stops delivered with coordinates in `audio_N.txt`
