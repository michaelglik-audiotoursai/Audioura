# Review for Kiro — Transport-Mode Distance Tiers (refines KIRO_REVIEW_07)

**Reviewer:** Claude (main dev Mac)
**Subject:** Replace the binary `wide_area_transport` skip from `KIRO_REVIEW_07` with graduated distance tiers by transport mode, plus a containment-based (not distance-based) rule for country-scale tours.
**Relationship to prior documents:** `KIRO_REVIEW_07`'s detection mechanism (word locator + extended AI-intent call) and its three classification touchpoints (S15 bypass, museum-containment bypass, tour_type suppression) are unchanged and still required — implement those first if not already done. This document only changes what happens at **Touchpoint 4** (the walking-distance GEO-CHECK): instead of skip-or-don't, look up the right threshold for the detected transport mode.

---

## Detection: same two layers as `KIRO_REVIEW_07`, richer output

Layer 1 (word locator) and Layer 2 (extended `analyze_tour_intent()` call) work exactly as already specified — no new API call. The only change is what they return: not a boolean, but one of five `transport_mode` values.

```python
_TRANSPORT_MODE_KEYWORDS = {
    'animal':  re.compile(r'\b(camel|horse(back)?)\s+tour\b', re.IGNORECASE),
    'bike':    re.compile(r'\b(bike|biking|cycling)\s+tour\b', re.IGNORECASE),
    'vehicle': re.compile(r'\b(auto|car|driving|jeep|off[- ]road|motorcycle|scooter)\s+tour\b', re.IGNORECASE),
    'country_scale': re.compile(r'\broad\s*trip\b|\bcross[- ]country\b|\bsafari\b|\bnational(?:\s+parks?)?\s+tour\b', re.IGNORECASE),
}
```
Check in the order above (or any order — these are mutually exclusive keyword sets, tune against real examples). Fall back to Layer 2 (extend `analyze_tour_intent`'s schema with a `"transport_mode"` field taking the same five values, `on_foot` being the default) when none match.

## Distance tiers — your numbers, single leg-distance ceiling per tier

```python
_TRANSPORT_TOTAL_HARD_KM = {
    'on_foot':  WALKING_TOTAL_HARD_KM,   # existing constant, unchanged
    'animal':   20,
    'bike':     30,
    'vehicle':  400,
}
```

**Corrected per your note: these are TOTAL route caps, not per-leg.** No per-leg check for `animal`/`bike`/`vehicle` — only the total-route-sum check applies, matching the existing fallback mechanism the walking tour already has for "no single leg jumped out, but the whole route is still too sprawling."

**Touchpoint 4, updated:**
```python
if tour_category == 'walking':
    _total_limit = _TRANSPORT_TOTAL_HARD_KM.get(transport_mode, WALKING_TOTAL_HARD_KM)
    legs = [_haversine_km(pts_valid[i][1], pts_valid[i+1][1]) for i in range(len(pts_valid) - 1)]
    total_route_km = sum(legs)
    medoid = min(pts_valid, key=lambda pc: sum(_haversine_km(pc[1], o) for _, o in pts_valid))[1]
    outliers = []
    # Per-leg check only applies to on_foot — animal/bike/vehicle skip straight to the total check
    if transport_mode == 'on_foot':
        for i, leg in enumerate(legs):
            if leg > WALKING_LEG_HARD_KM:
                a, b = pts_valid[i], pts_valid[i+1]
                farther = a[0] if _haversine_km(a[1], medoid) > _haversine_km(b[1], medoid) else b[0]
                outliers.append(farther)
    if total_route_km > _total_limit and not outliers:
        outliers = [max(pts_valid, key=lambda pc: _haversine_km(pc[1], medoid))[0]]
    ...
```
When the total is over the tier's cap, the existing fallback (flag the single stop farthest from the route's medoid, remove it, fetch a replacement) still applies unchanged — just driven by the tier-specific total instead of `WALKING_TOTAL_HARD_KM`. `on_foot` (ordinary walking tours) keeps both its per-leg and total checks exactly as today — zero regression risk there.

---

## Country-scale: containment, not distance — this is the right call

A fixed km ceiling can't work here: "as long as it's in the country" means ~1,200 km is fine for a USA tour but wrong for a Luxembourg tour. What actually matters is whether each stop is *in* the named country or in a small, well-known enclave/exclave embedded in or immediately adjacent to it — Vatican City and San Marino for Italy, per your example.

### Extend the intent schema once more (same existing AI call, still no new API call)

Add a `country_scope` field alongside `transport_mode`:
```python
"country_scope": "If this is a country-scale tour, the country name (e.g. 'Italy'). Null otherwise."
```

### A small, explicit enclave table — this is a short, finite list, not an open-ended problem

There are only a handful of true geographic micro-state enclaves/exclaves in the world. A hardcoded table is the right size of solution here — no need for a lookup service:

```python
_COUNTRY_ENCLAVES = {
    'italy':        ['vatican city', 'san marino'],
    'south africa': ['lesotho'],
    'france':       ['monaco'],
    # Andorra sits on the France/Spain border — include under both
    'spain':        ['andorra'],
    'switzerland':  ['liechtenstein'],
    'austria':      ['liechtenstein'],
}
```
Extend this list as edge cases come up — it's meant to be small and readable, not exhaustive on day one.

### Validation approach

For `country_scale` tours, replace the distance-based GEO-CHECK/PHASE-3C-style validation with a country-match check per stop:
```python
def _stop_in_country_scope(stop_country: str, country_scope: str) -> bool:
    target = country_scope.strip().lower()
    stop_c = (stop_country or '').strip().lower()
    if stop_c == target:
        return True
    return stop_c in _COUNTRY_ENCLAVES.get(target, [])
```
This needs the stop's resolved country — check whether the existing geocoding/address-fetch step already returns a country field (likely does, given addresses like `"...London...United Kingdom"` seen in `KIRO_REVIEW_05`'s PHASE 3C investigation — the country is usually the last comma-part). If so, this is a small addition, not new infrastructure: parse the last comma-part of the address as the country and check it against `country_scope` ∪ its enclave list, instead of running the word-token `_address_matches_location` logic (which is designed for city/district containment, not country containment, and would need its own fix path anyway per `KIRO_REVIEW_05`).

**No leg/total distance limit at all for `country_scale`** — containment is the only check. A domestic flight between two stops on a USA tour is expected, not an outlier.

---

## Full picture — where each transport mode's stops get validated

| `transport_mode` | Validation | Total-route ceiling | Per-leg ceiling |
|---|---|---|---|
| `on_foot` | GEO-CHECK (unchanged) | `WALKING_TOTAL_HARD_KM` (existing) | `WALKING_LEG_HARD_KM` (existing) |
| `animal` | GEO-CHECK, new tier | 20 km total | none |
| `bike` | GEO-CHECK, new tier | 30 km total | none |
| `vehicle` | GEO-CHECK, new tier | 400 km total | none |
| `country_scale` | Country/enclave containment (new mechanism) | none | none |

---

## Verify

1. Re-run the `KIRO_REVIEW_07` test set (camel tour in Abu Dhabi, road trip, horseback tour) — confirm each now resolves to the correct `transport_mode` and the right distance ceiling applies (not just "skipped entirely").
2. New test: a camel tour whose stops sum to well over 20km total route distance (e.g., 5 stops spread so the cumulative route exceeds 20km even if no single leg looks extreme) — confirm the total-route check catches it and removes the farthest-from-medoid stop, unlike the old binary skip which would have let anything through.
3. New test: `"Road trip across Italy"` or similar country-scale request including Rome + Vatican City as stops — confirm Vatican City is NOT rejected as out-of-country, and confirm no distance-based rejection occurs even for stops far apart within Italy.
4. Regression: ordinary walking tour — confirm `on_foot` tier behaves identically to current behavior (same constants, same logic).

Report back actual `transport_mode` values logged per test case, plus whether the country-containment check correctly passed Vatican City — same evidence standard as every round.
