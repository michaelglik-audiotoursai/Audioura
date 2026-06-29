# REVIEW_FOR_KIRO — Museum Multi-Building Coordinates Fix (2026-06-09)

**Context:** "library buildings in Newton, Ma" (2 stops) — map showed only 1 pin despite both stops having distinct coordinates. Server-side bug in Phase 6 assembly.

---

## Problem

Phase 6 of `generate_tour_text.py` (line ~1679) had this logic:

```python
coords_eligible = (tour_category == 'museum' and i == 0) or (tour_category != 'museum')
```

**Effect:** For any tour classified as `museum`, only the FIRST stop gets a `Coordinates:` line. All subsequent stops get no coordinates in their text → no coordinates in `audio_N.txt` → no map pin.

**Why "library buildings" hits this:** `_classify_tour_category` treats "library" as an institution (same class as museum). So a request for "library buildings in Newton, Ma" gets `tour_category = 'museum'`, and the single-building assumption kicks in.

**The assumption's intent was valid for actual single-building museums** — if you're touring exhibits inside the MFA, all stops are at the same address; only one pin makes sense. But it's wrong for multi-building "museum-class" tours (libraries across a city, historic houses in a district, etc.).

---

## Root Cause Evidence

DB inspection of tour 366 (English, 2 stops):
```
audio_1.txt: Coordinates: 42.3298, -71.2071  ✅
audio_2.txt: NO Coordinates line found        ❌
```

Generator log confirmed BOTH stops had coordinates assigned:
- Stop 1: Newton Free Library — `42.3298, -71.2071`
- Stop 2: Newtonville Branch Library — `42.3521, -71.2084`

The coordinates existed in the POI data but were suppressed during text assembly because `i > 0` and `tour_category == 'museum'`.

---

## Fix

**Logic:** If a "museum" tour has stops at **different** geographic locations (unique coordinate sets > 1), it's a multi-building tour — emit coordinates for every stop. Only suppress non-first-stop coordinates when all stops share the same coordinates (truly a single building with rooms/exhibits).

```python
if tour_category == 'museum':
    all_coords = [p.get("coordinates") for p in poi_list if p.get("coordinates")]
    unique_coords = set(all_coords)
    is_single_building = len(unique_coords) <= 1
    coords_eligible = (i == 0) if is_single_building else True
else:
    coords_eligible = True
```

**Behavior matrix:**

| Tour type | Coordinates | Result |
|-----------|-------------|--------|
| Walking/restaurant/specialized | Any | All stops get coordinates ✅ |
| Museum, all stops same coords | `42.33, -71.20` × 5 | First stop only (single building) ✅ |
| Museum, stops at different coords | `42.33, -71.20` + `42.35, -71.21` | All stops get coordinates ✅ |
| Museum, only 1 stop has coords | 1 coord set | First stop only ✅ |

---

## File Modified

| File | Change |
|------|--------|
| `development/generate_tour_text.py` | Phase 6 coordinates eligibility logic (~line 1679) |

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-generator` | `audioura:v12` | `tour-generator-00012-fnr` |

---

## Retest

Generate "library buildings in Newton, Ma" with 2 stops. Both stops should now have `Coordinates:` in their `audio_N.txt` → map shows 2 pins.

Also valid for: "historic houses in Concord", "churches in Boston" — any multi-location "institution" tour that was previously classified as museum.

---

## Risk

- **Low.** The fix is additive — previously-suppressed coordinates now get emitted. No existing behavior changes for actual single-building museum tours (coordinates are identical → `unique_coords` has 1 entry → first-stop-only behavior preserved).
- **Edge case:** A museum tour where GPT assigns slightly different coordinates to rooms in the same building (unlikely but possible with coordinate noise). In that case all stops would get pins clustered at the same location — cosmetically suboptimal but not wrong. The real single-building case is when coordinates are identical or only one stop has any.

---

## Also noted (not fixed this session)

The **museum icon** showing for libraries is because `_classify_tour_category` groups institutions together. This is cosmetic — the icon comes from `_CATEGORY_ICONS = {'museum': '🏛️'}`. A more accurate fix would add 'library' as its own category or use a book icon, but this is purely visual and not blocking.
