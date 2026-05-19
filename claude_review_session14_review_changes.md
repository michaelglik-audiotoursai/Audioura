# Claude.AI Review — Session 14 Review Changes + Test Results

**Branch:** `Tours_Step_Maps`
**Commits:** `ed1acad` (code), `05c2162` (remind doc)
**Service version:** `1.2.5.183`
**Status:** Awaiting mobile test results — document will be updated with any new failures found

---

## What Was Changed and Why

### Change 1 — PHASE 3C: replaced `parts[-2]` city check with all-tokens-scan + alias map

**File:** `generate_tour_text.py`

**Why:** The original helper extracted only `parts[-2]` (second-to-last comma token) as the city. Claude's review identified two failure modes:
1. **Boston neighborhoods**: USPS uses neighborhood names as the city field — `"100 Maverick Square, East Boston, MA 02128"` has `parts[-2] = "east boston"`, which is not a substring of `"walking tour in boston, ma"`. The stop would be silently rejected even though it is a valid Boston address.
2. **International addresses**: `"12 Rue de Rivoli, Paris, 75001, France"` has `parts[-2] = "75001"` (a postcode), not a city name.

**Fix applied:**
- Scan **all** comma-separated tokens (not just `parts[-2]`)
- Strip postcode-looking tokens before scanning (purely numeric `\d{4,6}` or UK-style `AB12 3CD`)
- Apply `_NEIGHBORHOOD_TO_CITY` alias map before the substring check

**`_NEIGHBORHOOD_TO_CITY` covers:**
- Boston neighborhoods: East Boston, Jamaica Plain, Roxbury, Dorchester, South Boston, Mattapan, Brighton, Allston, Hyde Park, Roslindale, West Roxbury, Charlestown
- NYC boroughs: Brooklyn, Queens, Bronx, Staten Island
- Newton villages: Newton Centre, West Newton, Newton Corner, Newton Highlands, Newtonville

**Known remaining limitation:** The alias map is a fixed list. A city not in the map with a neighborhood-distinct USPS name would still be rejected. Expanding the map is the fix if new false-rejections are found.

---

### Change 2 — Removed dead `state_token` branch

**File:** `generate_tour_text.py`

**Why:** The original return statement was:
```python
return city in loc_lower or (state_token and state_token in loc_lower and city in loc_lower)
```
The right side of `or` requires `city in loc_lower` as one of its `and` clauses — meaning the right side is a strict logical subset of the left side. If the right side is True, the left side is already True. The `state_token` half never added anything. Claude confirmed this was dead code.

**Fix:** Removed. The new all-tokens-scan handles the cases the state_token branch was intended to cover.

---

### Change 3 — Moved PHASE 3C before Part C

**File:** `generate_tour_text.py`

**Why:** In the previous pipeline, PHASE 3C ran **after** PHASE 3B. Part C (the replacement loop) had already exhausted its attempts before PHASE 3C could reject out-of-area stops. This meant a rejected stop reduced the final tour count with no chance of replacement.

**New pipeline order:**
```
PHASE 3A  →  PHASE 4.5  →  PHASE 4  →  PHASE 3C  →  Part C  →  PHASE 3B  →  Coords fallback  →  Cluster detection
```

PHASE 3C now runs on the PHASE 3A addresses (before PHASE 3B enriches them). PHASE 3A already includes addresses, so the location check is valid at this stage. Stops rejected by PHASE 3C are added to `forbidden_norms` so Part C fetches genuinely different replacements.

**Trade-off:** PHASE 3B reorders stops for optimal walking route. If PHASE 3C rejects a stop after PHASE 3B, the route order would need re-optimisation. By running PHASE 3C before PHASE 3B, the route is optimised over the final confirmed set of stops. This is the correct order.

---

### Change 4 — Zero-stop guard after PHASE 3C

**File:** `generate_tour_text.py`

**Why:** If GPT hallucinates stops entirely outside the requested location (e.g. all 5 stops in Sudbury for an Arlington tour), PHASE 3C would reject all of them. Without a guard, the pipeline would continue with an empty `poi_list` and produce a broken tour or crash later. Claude recommended surfacing a clear error instead.

**Fix:** `raise ValueError(f"PHASE 3C rejected all stops for location '{location}'")` — caught by the outer `except Exception` block, which returns `None, None, (None, None)` to the orchestrator. The orchestrator surfaces this as a failed job.

---

### Change 5 — Duplicate-coordinate cluster detection

**File:** `generate_tour_text.py`

**Why:** GPT sometimes returns the same lat/lng for all stops on a linear route (confirmed in Session 14: Commonwealth Ave tour had all 5 stops at `42.3503, -71.0852`). The coords fallback only fills in *missing* coordinates — it does not detect when coordinates are present but wrong/duplicated.

**Fix:** After the coords fallback, count coordinate strings with `Counter`. If the most common coordinate appears in ≥50% of stops (and at least 2 stops), clear those coordinates and re-run `_fetch_coords` in parallel for the affected stops. This is one extra round-trip (~$0.001 worst case).

**Threshold logic:** `top_count >= max(2, len(poi_list) // 2)` — requires at least 2 duplicates AND at least half the stops. A 2-stop tour where both happen to share a coordinate would trigger this (both get refetched), which is acceptable.

---

### Change 6 — `[:500]` slice in `tour_generation_modernized.py`

**File:** `tour_generation_modernized.py`

**Why:** The `[:200]` slice was added as a defense against false positives (a stop description starting with `Tour-Category:` far into the file). Claude measured that a 223-character tour title would push the `Tour-Category:` header past byte 200, causing the regex to miss it and silently default to 🗺️. Bumping to `[:500]` gives ~3× headroom with no meaningful increase in false-positive risk (a stop description starting at column 0 with `Tour-Category:` is equally unlikely at byte 300 as at byte 199).

---

## Test Results (to be filled in)

*User will test by generating new tours after deploying v1.2.5.183. Results will be recorded here.*

### Test 1 — Walking tour in Boston, MA (neighborhood stop validation)
- **Purpose:** Confirm East Boston / Jamaica Plain stops are NOT rejected by PHASE 3C
- **Expected:** All stops with Boston neighborhood addresses pass through
- **Result:** _pending_

### Test 2 — Walking tour in Arlington, MA (out-of-area rejection)
- **Purpose:** Confirm Sudbury/Lexington stops ARE still rejected
- **Expected:** PHASE 3C removes out-of-area stops; Part C fetches replacements
- **Result:** _pending_

### Test 3 — Tour icons (walking / restaurant / museum)
- **Purpose:** Confirm 🚶 / 🍴 / 🏛️ icons appear correctly on newly generated tours
- **Expected:** Icon matches tour category
- **Result:** _pending_

### Test 4 — Map pins (all stops have pins)
- **Purpose:** Confirm coords fallback + cluster detection produce distinct pins for all stops
- **Expected:** No missing map pins; no cluster of pins at same location
- **Result:** _pending_

---

## New Failures Found During Testing

*This section will be filled in as the user reports test failures.*

---

## Questions for Claude (to be added if new issues arise)

*This section will be filled in based on test results and any new edge cases observed.*
