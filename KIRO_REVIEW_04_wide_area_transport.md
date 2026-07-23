# Review for Kiro — Wide-Area Transport Mode (Camel/Horse/Auto/Road-Trip Tours)

**Reviewer:** Claude (main dev Mac)
**Subject:** Camel/horse/auto-tour requests fail because the system has no concept of "stops can be far apart because you're not walking between them" — separate from, but related to, the tour-type classification fixes in `KIRO_REVIEW_01`.
**Design:** Word-locator (regex) first pass, falling back to the *existing* AI intent-analysis call (not a new one) only when the phrasing isn't explicit. No new content category — this is an orthogonal dimension to `tour_category`, not a fifth value alongside museum/walking/restaurant/book.

---

## Why this isn't a fifth `tour_category`

A camel tour and a road trip don't need their own story template — `spine_walking.txt` or `spine_book.txt` (a historical-route narrative) might genuinely fit a camel tour past old trade-route waypoints just fine. What's different isn't the *story style*, it's the *geographic-spread rule*: stops can legitimately be many kilometers apart because travel between them isn't on foot. That's true whether the tour is telling a walking-style narrative, a specialized/historical one, or something else. So this should be a separate signal that modifies distance handling, not a new branch of `tour_category`.

## Where this actually breaks today

Two places, confirmed in `generate_tour_text.py`:

**1. The museum single-venue trap (same root cause as `KIRO_REVIEW_01`).** "Camel tour" matches no walking/food/movie/book keyword, so it falls through to the same `tour_type_lower` contamination already documented — `_classify_tour_category` sees `tour_type_lower == "museum"` (from the client default) and returns `'museum'`. This is very likely the exact cause of the "This venue could not be verified with enough works to generate a quality tour" failure already seen in testing — the system tries to validate a desert route as if it were a single museum building with verifiable exhibits.

**2. The walking-distance hard limit, and a comment that already anticipated this exact case:**
```python
# line 2522
if tour_category == 'walking':
    ...
    if leg > WALKING_LEG_HARD_KM:   # legs longer than this get flagged as outliers and REMOVED
        ...
    # line 2540
    # Protect user-explicit stops from GEO-CHECK removal — the user knows
    # their named stops may be far apart (regional/driving tour); honor the request.
    if _explicit_stop_names:
        protected = [o for o in outliers if _normalize_name(o['name']) in _explicit_stop_names]
```
Someone already built a bypass for this — but only for stops the user named explicitly. An AI-suggested camel/horse/road-trip itinerary gets no such protection and will have legitimately-spread-out stops silently removed as "outliers."

There's also no `scope_precision` value wider than `CITY` (`BUILDING | CORRIDOR | DISTRICT | CITY`) — nothing represents "spans a region."

---

## Design: two layers, no new API call unless the first layer misses

### Layer 1 — word locator (regex, zero cost, checked first)

New regex, same style as the existing `_EXPLICIT_NON_MUSEUM_TOUR_RE`:
```python
_WIDE_AREA_TRANSPORT_RE = re.compile(
    r'\b(camel|horse(back)?|auto|car|driving|jeep|off[- ]road|motorcycle|scooter|boat|cruise|train)'
    r'\s+tour\b'
    r'|\broad\s*trip\b'
    r'|\bcross[- ]country\b'
    r'|\bsafari\b',
    re.IGNORECASE,
)
```
Tune the exact word list against real examples before landing — the goal is to catch explicit phrasing ("camel tour," "auto tour," "road trip through...") without over-matching things like "car museum tour" (word-boundary + "tour" anchoring, same pattern as the existing regex, should keep this narrow — verify with test cases in the checklist below).

### Layer 2 — extend the *existing* intent-analysis call, don't add a new one

`analyze_tour_intent()` already runs once per request (`generate_tour_text.py:133`, ~$0.0008/call) and already extracts `scope_precision` in the same JSON response. Add one more field to that same schema rather than making a second AI call:

```python
# In the intent_prompt JSON schema (generate_tour_text.py:143-155), add:
"wide_area_transport": "true if stops may be geographically dispersed because travel between
    them is by vehicle or animal (car, camel, horse, boat, safari, road trip) rather than on
    foot; false for walking-distance tours, single-venue tours, or anything not explicitly
    indicating non-walking travel between stops."
```
Add 1-2 examples to the existing example list (same format as the existing ones at lines 157-177), e.g.:
```
- "Camel tour through the desert oasis trail, Abu Dhabi" → wide_area_transport: true, venue_name: null
- "Road trip along the California coast" → wide_area_transport: true, venue_name: null
- "Walking tour of the North End" → wide_area_transport: false
```

### Combine the two signals

```python
_wide_area_keyword_match = bool(_WIDE_AREA_TRANSPORT_RE.search(location))
_wide_area_from_intent = bool(intent and intent.get('wide_area_transport'))
wide_area_transport = _wide_area_keyword_match or _wide_area_from_intent
```
Layer 1 (regex) needs no intent-analysis result at all, so it's available even if the AI call fails or hasn't run yet. Layer 2 only matters when Layer 1 doesn't match — no extra network round-trip either way, since `analyze_tour_intent()` already runs regardless.

---

## Where `wide_area_transport` needs to be checked (three touchpoints)

**1. S15 force-museum override (`generate_tour_text.py:1506`)** — don't force museum on a wide-area tour even if a venue_name was found:
```python
if intent.get('venue_name') and not wide_area_transport and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
    tour_category = 'museum'
```

**2. Museum single-venue containment gate (`generate_tour_text.py:1861` and the later validation-consuming checks)** — defense in depth, in case `tour_category` still ends up `'museum'` via the location text containing a museum keyword (e.g. "desert museum by camel"):
```python
if tour_category == 'museum' and _museum_venue_name and not wide_area_transport:
```

**3. Walking-distance GEO-CHECK (`generate_tour_text.py:2522` and the explicit-stops bypass at 2540-2547)** — extend the existing bypass philosophy from "explicitly-named stops only" to "the whole tour, when wide-area":
```python
if tour_category == 'walking' and not wide_area_transport:
    ... # existing hard-limit + outlier-removal logic, unchanged
```
Simplest correct behavior: skip the entire GEO-CHECK block for wide-area tours, the same way it's already skipped for non-walking categories today. Don't try to compute a "looser" numeric threshold for camels vs. cars vs. horses — that's precision this doesn't need yet; skipping the check entirely (same as it's already skipped for museum/restaurant/book tours) is consistent with how every other category already works.

---

## Not doing right now

- Not adding a `REGION` value to `scope_precision`'s existing four-value enum — that field is consumed in multiple `in (...)` checks elsewhere in the file, and widening its contract means auditing every one of those call sites. The boolean `wide_area_transport` field is purpose-built for the one decision that actually needs to change and only needs checking in the three places above — smaller, safer diff.
- Not attempting per-transport-mode distance tuning (camel vs. horse vs. car likely cover very different real ranges) — skipping the check entirely is the same posture already used for every non-walking category today. Revisit only if real usage shows it's needed.

---

## Verify

Test each of these via direct API call (same pattern as `KIRO_REVIEW_03`), and check both the logged `tour_category` and whether stops actually survive with realistic geographic spread:

1. `"Camel tour through the desert oasis trail, Abu Dhabi"` — should not hit the museum "verified works" failure; should not classify as `museum`.
2. `"Road trip along the California coast"` — no walking-distance-outlier removal on far-apart real stops.
3. `"Horseback tour of the ranch trails, Wyoming"` — same.
4. **Control/regression check:** `"Walking tour of the North End, Boston"` — confirm `wide_area_transport` is `false` and the existing walking-distance GEO-CHECK still runs and still removes genuinely-too-far outliers exactly as before. This must not regress.
5. **Edge case:** `"Tour of the Auto Museum in Turin"` — confirm the word-locator regex does NOT false-positive on "auto" here (it shouldn't, since "auto" isn't followed by "tour" in this phrasing — but verify).

Report back the logged `wide_area_transport` value and `tour_category` for each, plus whether the stop list for the camel/road-trip/horseback cases actually reflects realistic spread rather than being collapsed to a tight cluster or failing outright.
