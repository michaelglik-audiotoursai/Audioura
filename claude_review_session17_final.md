# Claude Review — Session 17 Final: Geographic Scope + Walking-Compactness

**For:** Claude.AI review
**Branch:** `Tours_Step_Maps`
**Base commit:** `78363ad` (review doc + remind update)
**Files changed:** `generate_tour_text.py`, `tour_settings.py`
**Status:** Deployed to container, syntax verified. Awaiting Claude approval before git commit.

---

## 1. PHASE 3D — Fully Removed

Confirmed removed:
- Function `_validate_poi_geographic_relevance()` — deleted entirely
- PHASE 3D pipeline block (phase_3d_rejects, post-3D Part C, duplicate PHASE 3B copy) — deleted entirely
- No orphaned imports left behind

Verified via container grep: zero occurrences of `_validate_poi_geographic_relevance` in deployed file.

---

## 2. Fix A — `geographic_scope` + `scope_precision` in PHASE 1

### Schema additions (lines 118–119 in deployed file)
```
"geographic_scope": "The most specific bounded area the tour must stay within, in the
   user's own terms — a street or corridor, a square, a named district or quarter, a
   waterfront, a campus, a market, a cluster of blocks, or a single building. Copy the
   phrasing the request uses. If the request only names a whole city or town with no
   tighter anchor, return that city/town name. Never invent a tighter scope than the
   request states.",
"scope_precision": "One of exactly these four strings: BUILDING (one structure) |
   CORRIDOR (one street or strip) | DISTRICT (a neighbourhood, quarter, square, or
   named area) | CITY (a whole town with no tighter anchor given)."
```

### New examples added (lines 138–142)
```
- "walking tour over Beacon St in Brookline, ma" → geographic_scope: "Beacon St, Brookline", scope_precision: "CORRIDOR"
- "Fairbanks House Tour in Dedham, ma" → geographic_scope: "Fairbanks House", scope_precision: "BUILDING"
- "tour of the old mill district in Lowell" → geographic_scope: "the old mill district, Lowell", scope_precision: "DISTRICT"
- "walking tour around the harbor in Gloucester" → geographic_scope: "the harbor waterfront, Gloucester", scope_precision: "DISTRICT"
- "walking tour in Newton, MA" → geographic_scope: "Newton, MA", scope_precision: "CITY"
```

### Relationship to `venue_name` / S15 logic
`venue_name` and the S15 museum-category decision are unchanged. `geographic_scope` is the new general field. `scope_precision == 'BUILDING'` will agree with `venue_name` being set, but the two fields are independent in this commit. Unification deferred as specified.

---

## 3. PHASE 3A — Scope + Compactness Constraints

### Scope constraint (injected for CORRIDOR and DISTRICT only)
```python
_geo_scope = (intent.get('geographic_scope') or '').strip() if intent else ''
_scope_precision = (intent.get('scope_precision') or '').strip().upper() if intent else ''
_scope_constraint = ''
if _geo_scope and _scope_precision in ('CORRIDOR', 'DISTRICT'):
    _scope_constraint = (
        f"\nGEOGRAPHIC SCOPE — ALL stops MUST be located within: {_geo_scope}.\n"
        f"- Do NOT include well-known landmarks elsewhere in the city just because "
        f"they are famous — if it is outside {_geo_scope}, it does not belong.\n"
    )
```
`BUILDING` → handled by existing museum venue constraint. `CITY` → no constraint (today's behaviour).

### Compactness constraint (walking tours only)
```python
if tour_category == 'walking':
    _compactness_constraint = (
        f"\nWALKING-TOUR COMPACTNESS — this is a walking tour:\n"
        f"- All stops must form ONE compact cluster, close enough to walk between comfortably.\n"
        f"- No stop should be more than a 10–15 minute walk (roughly {WALKING_LEG_TARGET_KM:.0f} km) "
        f"from its nearest neighbour in the tour.\n"
        f"- Prefer a tight set of stops in one walkable area over famous landmarks scattered "
        f"across the city. A shorter, denser route is better than a long, spread-out one.\n"
    )
```
Not added for restaurant, museum, or specialized.

---

## 4. PHASE 3B — Sequential-Closeness Line + Reusable Function

### Sequential-closeness line added
```
"Reorder them for an OPTIMAL walking route (minimise backtracking).\n"
"- Keep the overall route as short as possible; minimise the longest single leg "
"between any two consecutive stops.\n"
```

### PHASE 3B extracted into `_run_phase_3b(current_poi_list)`
Inner function (closure over `location`, `total_stops`, `headers`, `_parse_json_array_loose`, `_normalize_name`, `_new_poi`, `total_tokens`, `total_cost` via `nonlocal`).

- Takes a poi_list, returns a reordered poi_list with structured details + directions
- On any failure (API error, unparseable response, no recognisable entries) → returns `current_poi_list` unchanged
- Re-appends any POI the AI dropped
- Caps to `total_stops`
- Preserves coordinates from original stops when PHASE 3B omits them (merged from `orig`)

Called in two places:
1. Main PHASE 3B (line 1107): `poi_list = _run_phase_3b(poi_list)`
2. After GEO-CHECK replacements (line 1282): `poi_list = _run_phase_3b(poi_list)`

No copy-paste duplication.

---

## 5. Geometric Verification Block (GEO-CHECK)

### Module-level helpers
```python
from math import radians, sin, cos, asin, sqrt

def _haversine_km(a, b):
    lat1, lon1 = a; lat2, lon2 = b
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * 6371.0 * asin(sqrt(h))

def _parse_coords(s):
    m = re.match(r'\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', s or '')
    return (float(m.group(1)), float(m.group(2))) if m else None
```

### Verification block (walking tours only, after coords finalized)
```python
if tour_category == 'walking':
    pts_valid = [(p, _parse_coords(p.get('coordinates', ''))) for p in poi_list filtered to those with coords]
    if len(pts_valid) >= 3:
        legs = [haversine between consecutive stops]
        total_route_km = sum(legs)
        medoid = stop closest to all others (geometric median approximation)
        outliers = stops where adjacent leg > WALKING_LEG_HARD_KM (1.75 km)
        if total_route_km > WALKING_TOTAL_HARD_KM (12 km) and no leg outliers:
            outliers = [stop farthest from medoid]
        dedupe outliers by id()
        if outliers and len(outliers) < len(poi_list):   # ADVISORY guard
            → remove outliers, add to forbidden_norms
            → fetch replacements with geographic_scope + accepted stop names in prompt
            → fetch coordinates for replacement stops (_fetch_coords parallel)
            → re-order via _run_phase_3b()
        elif outliers (all stops flagged):
            → log advisory, keep original list
        else:
            → log all-clear with max leg + total km
    else:
        → log skipped (< 3 stops with coords)
```

### Advisory guarantee
`len(outliers) < len(poi_list)` guard ensures the check never removes all stops. No `ValueError` raised. Tour always completes.

### Replacement prompt carries geographic anchor (spec requirement 3.5.3)
```python
scope_hint = f" located within {_geo_scope}" if _geo_scope else f" in {location}"
accepted_names = "; ".join(p['name'] for p in poi_list)
rep_prompt = (
    f"Suggest exactly {needed} ... {poi_type_hint}{scope_hint}, "
    f"close to these already-accepted stops: {accepted_names}.\n"
    ...
)
```

### Replacement coordinates fetched (spec requirement 3.5.1)
After replacements added to `poi_list`:
```python
missing_geo = [p for p in poi_list if not p.get('coordinates')]
if missing_geo:
    # parallel _fetch_coords for all missing
```

---

## 6. `tour_settings.py` — Final Contents
```python
WALKING_LEG_TARGET_KM    = 1.0    # what the prompt asks GPT for
WALKING_LEG_HARD_KM      = 1.75   # verifier rejects a sequential leg above this
WALKING_TOTAL_HARD_KM    = 12.0   # backstop on total straight-line route length
SPECIALIZED_LEG_HARD_KM  = 4.0    # biking / driving / themed tours — looser (future)
MAX_REPLACEMENT_ATTEMPTS = 2      # Part C replacement loop cap
```
`MAX_WALKING_TOUR_DISTANCE_KM` removed (was "reserved for future", unused).

Import in `generate_tour_text.py`:
```python
from tour_settings import (
    WALKING_LEG_TARGET_KM, WALKING_LEG_HARD_KM, WALKING_TOTAL_HARD_KM,
    MAX_REPLACEMENT_ATTEMPTS,
)
```

---

## 7. Regression Guards Verified

| Guard | Status |
|---|---|
| Museum single-venue tours (S15) | GEO-CHECK is `walking`-only; museum tours untouched ✅ |
| `venue_name` / S15 logic | Unchanged ✅ |
| Restaurant tours | No compactness constraint, no GEO-CHECK ✅ |
| Specialized tours | No walking compactness constraint ✅ |
| PHASE 3C address guard | Runs unchanged before all new code ✅ |
| `forbidden_norms` init | Unchanged — GEO-CHECK adds to same set, does not re-init ✅ |
| Existing Part C (PHASE 4 / PHASE 3C rejects) | Unchanged ✅ |
| Zero-stop ValueError (PHASE 3C) | Unchanged ✅ |

---

## 8. Test Matrix Results

Tests not yet run — awaiting Claude approval before generating tours. Will run after commit.

| # | Input | Expected |
|---|---|---|
| 1 | `"walking tour over Beacon St in Brookline, ma"` | scope_precision=CORRIDOR; PHASE 3A constrained to "Beacon St, Brookline"; GEO-CHECK removes any leg > 1.75 km |
| 2 | `"walking tour in Newton Center, MA"` | scope_precision=DISTRICT or CITY; regression — no false GEO-CHECK removals |
| 3 | `"Fairbanks House Tour in Dedham, ma"` | scope_precision=BUILDING; museum; GEO-CHECK skipped; S15 unchanged |
| 4 | `"restaurant tour in North End, Boston"` | restaurant; no compactness; no GEO-CHECK; unchanged |
| 5 | `"tour of the old mill district in Lowell"` | scope_precision=DISTRICT; PHASE 3A constrained to district |

---

## 9. Questions for Claude

### Q1: `nonlocal total_tokens, total_cost` in `_run_phase_3b`
The function uses `nonlocal` to accumulate token costs into the outer function's counters. Is this the right pattern, or should `_run_phase_3b` return `(poi_list, tokens_used, cost)` and let the caller accumulate? The nonlocal approach is simpler but less explicit.

### Q2: GEO-CHECK threshold values
`WALKING_LEG_HARD_KM = 1.75` and `WALKING_TOTAL_HARD_KM = 12.0` — do these feel right for a typical walking tour? The user said 10 km max total; we set 12 km as the hard backstop to avoid fighting GPT over borderline cases. Is 1.75 km per leg too tight or too loose?

### Q3: `scope_precision == 'BUILDING'` and scope_constraint
Currently `BUILDING` gets no scope_constraint injection (handled by museum venue constraint). But a BUILDING tour that is NOT a museum (e.g. a library tour that doesn't trigger museum category) would get neither constraint. Is this a gap worth closing in this commit, or defer?

### Q4: Medoid approximation
The medoid is computed as `min(pts, key=lambda pc: sum(haversine(pc, o) for o in pts))` — this is O(n²) but n ≤ 10 stops so it's fine. Just confirming this is the intended approach vs. a simple centroid.
