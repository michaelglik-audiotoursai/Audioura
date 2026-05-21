# Claude Review — Session 17: PHASE 3D Geographic Relevance Validation

## Context
Branch: `Tours_Step_Maps`. Base commit: `3f9d04e`.
File changed: `generate_tour_text.py` + new `tour_settings.py`.

## Problem Being Solved
User tested `"walking tour over Beacon St in Brookline, ma"` and received:
1. POIs not on Beacon St (GPT picked well-known Brookline landmarks regardless of street)
2. POIs too dispersed for a walking tour (e.g. one stop at 42.3095, -71.1315 — ~3km south of Beacon St corridor at ~42.34)

Root cause: PHASE 3A prompt asks for POIs "relevant to" the request but has no geographic precision guard. PHASE 3C (address-based city guard) only checks city-level membership — it cannot distinguish "Beacon St, Brookline" from "Brookline generally".

## Solution: PHASE 3D — GPT Batch Geographic Relevance Validation

### New file: `tour_settings.py`
```python
MAX_WALKING_TOUR_DISTANCE_KM = 10.0   # reserved for future coordinate-distance layer
MAX_REPLACEMENT_ATTEMPTS = 2           # moved from hardcoded in generate_tour_text.py
```
Rationale: user explicitly requested these not be hardcoded so they can become user-facing parameters.

### New function: `_validate_poi_geographic_relevance(poi_list, user_request, headers)`
Module-level function. One GPT batch call with all stops in a single prompt.

**Prompt design:**
```
The user requested: "{user_request}".
For each POI below, answer whether it geographically and contextually belongs
in this specific tour. Consider the street corridor, neighbourhood, or area
named in the request — a POI that is clearly in a different part of the city
or a different city entirely does NOT belong.

1. Stop Name — address — coords (if available)
...

Return ONLY a JSON array:
[{"name": "...", "belongs": true/false, "reason": "..."}]
```

**Why GPT not coordinate math:**
- Beacon St is long; a centroid-radius would reject valid stops at the far end
- GPT knows "Beacon St Brookline runs through Coolidge Corner (~42.34 lat)" — exactly the geographic knowledge needed
- Handles streets, squares, districts, named areas uniformly — no special-casing for road type

**Cost:** ~450–600 tokens = ~$0.0007–0.0009 per tour. Negligible vs existing pipeline cost.

**Failure mode:** API error or unparseable response → returns empty list (all stops kept). Never blocks the tour.

### Pipeline insertion point
PHASE 3D runs **after** coordinates are finalized (post cluster-detection) and **before** the first-POI coordinate extraction. This means:
- Coordinates are available in the prompt (extra signal for GPT)
- Rejected stops feed into a targeted Part C replacement fetch
- After replacements, PHASE 3B re-runs to re-order the combined set (survivors + new stops)

### Replacement + re-order flow
```
PHASE 3D rejects N stops
  → forbidden_norms updated
  → Part C (post-3D): fetch N replacements with user_request context in prompt
  → New stops validated through PHASE 3D again (prevents bad replacements)
  → PHASE 3B re-order: full combined set re-ordered for optimal walking route
  → Coordinates for new stops fetched via existing fallback
```

**Key design decision**: re-running PHASE 3B after replacements ensures the walking order is globally optimal across the new combined set, not just appended at the end.

### Skipped for:
- Single-venue museum tours (`tour_category == 'museum' and _museum_venue_name`) — all stops are inside one building, geographic relevance is irrelevant

---

## Questions for Claude

### Q1: Prompt robustness — name matching
The response map is built with `entry['name'].strip().lower()` and looked up with `poi['name'].strip().lower()`. GPT sometimes paraphrases names slightly (e.g. "Coolidge Corner Theatre" vs "The Coolidge Corner Theatre"). Should we use fuzzy matching (e.g. check if one is a substring of the other) or is exact lowercase match sufficient given `temperature=0.1` and the instruction "exact name"?

### Q2: PHASE 3D placement — before or after coordinates fallback?
Currently PHASE 3D runs after coordinates are finalized, so coordinates are available as extra signal in the prompt. Alternative: run PHASE 3D immediately after PHASE 3C (before coordinates), which would avoid fetching coordinates for stops that will be rejected anyway (saves ~1–2 API calls per rejected stop). Trade-off: less signal in the prompt. Which placement do you recommend?

### Q3: Re-order PHASE 3B — always or only when replacements were added?
Currently the re-order PHASE 3B only runs when PHASE 3D rejected at least one stop. If PHASE 3D rejects stops but Part C finds no valid replacements (e.g. very specific street with few POIs), we still re-order the survivors. Is this correct, or should we skip re-order when the stop count didn't change?

### Q4: Replacement prompt — should it include the accepted stops as context?
The current replacement prompt tells GPT "do not use these rejected names" but doesn't tell it which stops were accepted. Should we add "the following stops are already accepted: X, Y, Z — suggest stops that complement these geographically" to help GPT pick stops that fill gaps in the route rather than duplicating the same area?

### Q5: Zero-stop guard after PHASE 3D
Currently raises `ValueError` if PHASE 3D rejects all stops (same pattern as PHASE 3C). Is this the right behaviour, or should we fall back to the pre-3D poi_list (i.e. treat 3D as advisory-only when it would eliminate everything)?

---

## Regression Risk Assessment

| Existing behaviour | Impact of PHASE 3D |
|---|---|
| Museum single-venue tours | Not affected — 3D skipped |
| City-wide walking tours (Newton Center, MA) | Low risk — GPT should pass all stops in the correct city |
| Restaurant tours | Low risk — same batch validation, same failure-safe |
| PHASE 3C address guard | Still runs before 3D — 3D is an additional layer, not a replacement |
| Part C replacement loop | Still runs for PHASE 4 / PHASE 3C rejects; 3D has its own targeted replacement block |
| Zero-stop ValueError | Preserved — 3D raises ValueError if all stops rejected |

## Test Cases to Verify
1. `"walking tour over Beacon St in Brookline, ma"` — all stops should be on/near Beacon St corridor (~42.34 lat)
2. `"walking tour in Newton Center, MA"` — regression: all stops should still pass (no false rejects)
3. `"restaurant tour in North End, Boston"` — regression: North End restaurants should pass
4. `"Fairbanks House Tour in Dedham, ma"` — museum, 3D skipped, no change
