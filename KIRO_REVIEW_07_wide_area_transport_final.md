# Review for Kiro — Wide-Area Transport, Final Spec (supersedes KIRO_REVIEW_04)

**Reviewer:** Claude (main dev Mac)
**Subject:** Finish tour-type classification so camel/horse/auto/road-trip tours stop being forced into `museum`. This is the current live test case: **"Camel Tour in a desert of Abu Dhabi, UAE"**.
**Status:** `KIRO_REVIEW_04_wide_area_transport.md` had the right overall design but was written before your Part One fix (`_effective_tour_type` suppression) landed, and it's missing one integration point as a result. I proved this empirically against the current code, not just by re-reading the design. This document is the complete, corrected spec — follow this one, not `KIRO_REVIEW_04`, for the actual implementation.

---

## Proof the camel tour is still broken today, even with Part One applied

Ran this directly against the current, already-patched `generate_tour_text.py`:

```python
from generate_tour_text import _classify_tour_category
loc = 'Camel Tour in a desert of Abu Dhabi, UAE'
loc_normalized = loc.replace('Tour', '').replace('tour','').strip().strip(',').strip()

pre = _classify_tour_category(loc_normalized, '')
print(pre)          # -> walking

real = _classify_tour_category(loc, 'museum')
print(real)          # -> museum
```

**Result: `pre_category` is `'walking'`, and the real classification is still `'museum'`.** Here's exactly why, and why your Part One fix doesn't cover it:

1. No keyword in *any* of `_classify_tour_category`'s category lists matches "camel," "desert," or "Abu Dhabi" — not walking-phrase, not food, not museum, not specialized. So it falls through every check to the final default: `return 'walking'`.
2. Your Part One fix suppresses `tour_type` only when `_pre_category in ('restaurant', 'specialized')` — deliberately **excluding** `'walking'`, because that's needed to protect real museum requests like "Medfield State Hospital" (which also default to `'walking'` pre-category, since the location text has no museum keyword either).
3. Since a camel tour's `_pre_category` is also `'walking'`, it gets the **same exclusion** as Medfield State Hospital — `tour_type` is *not* suppressed, so the real classification call runs with the client's actual `tour_type="museum"`, and the already-documented `tour_type_lower` contamination bug fires: `'museum' in tour_type_lower` trivially matches, and `tour_category` becomes `'museum'`.

This is exactly the failure mode already observed in testing ("This venue could not be verified with enough works to generate a quality tour") — now root-caused with certainty, not inferred.

**The fix from `KIRO_REVIEW_04` (S15 bypass, containment-gate bypass, GEO-CHECK bypass) is necessary but insufficient on its own** — none of those three gates matter if `tour_category` never stops being forced to `'museum'` in the first place. This document adds the missing fourth touchpoint and gives the complete, sequenced set.

---

## The complete design (word locator → existing AI call → four touchpoints)

### Layer 1 — word locator (regex, unchanged from `KIRO_REVIEW_04`)

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

### Layer 2 — extend the existing intent-analysis call (unchanged from `KIRO_REVIEW_04`)

Add `"wide_area_transport"` to the JSON schema in `analyze_tour_intent()`'s prompt (`generate_tour_text.py:143-155`), with 1-2 examples, as specified in `KIRO_REVIEW_04`. Not a new API call — same one that already runs.

### Combine

```python
_wide_area_keyword_match = bool(_WIDE_AREA_TRANSPORT_RE.search(location))
_wide_area_from_intent = bool(intent and intent.get('wide_area_transport'))
wide_area_transport = _wide_area_keyword_match or _wide_area_from_intent
```

### Touchpoint 1 (NEW — this is the missing piece) — extend the `_effective_tour_type` suppression

This is the actual fix for the empirical failure above. In the exact code Kiro already added:

```python
# BEFORE (current, from Part One):
_effective_tour_type = "" if _pre_category in ('restaurant', 'specialized') else tour_type

# AFTER:
_effective_tour_type = "" if (_pre_category in ('restaurant', 'specialized') or wide_area_transport) else tour_type
```

Apply at both call sites (same two places Part One already touched — the `if intent:` branch and the `else` fallback branch). With this change, `_classify_tour_category(location, "")` runs for the camel tour instead of `_classify_tour_category(location, "museum")` — and since no category keyword matches "camel"/"desert"/"Abu Dhabi" either way, it correctly falls through to the same default: **`'walking'`** — not `'museum'`.

**This alone fixes the misclassification.** The remaining three touchpoints (below, from `KIRO_REVIEW_04`, unchanged) make sure `'walking'` category behaves correctly for a tour that isn't actually walking-distance.

### Touchpoint 2 — S15 force-museum override (`generate_tour_text.py:1506`)

```python
if intent.get('venue_name') and not wide_area_transport and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
    tour_category = 'museum'
```
Defense in depth, in case the AI intent analysis attaches a venue_name to a wide-area request for some other reason.

### Touchpoint 3 — museum single-venue containment gate (`generate_tour_text.py:1861` and related)

```python
if tour_category == 'museum' and _museum_venue_name and not wide_area_transport:
```
Same defense-in-depth reasoning.

### Touchpoint 4 — walking-distance GEO-CHECK (`generate_tour_text.py:2522`)

```python
if tour_category == 'walking' and not wide_area_transport:
    ... # existing hard-limit + outlier-removal logic, unchanged
```

**One elegant consequence worth knowing, not a fifth touchpoint to build:** `PHASE 3C` (the address-token-matching guard that separately failed on "London movie locations tour" — see `KIRO_REVIEW_05`) is **already skipped whenever `tour_category == 'walking'`** (`generate_tour_text.py:2193`, pre-existing code: `if tour_category == 'walking': print("PHASE 3C: skipped for walking tours...")`). Since Touchpoint 1 above makes camel/horse/auto/road-trip tours correctly land in `'walking'` category, they get this exemption automatically — no separate PHASE 3C fix needed for wide-area tours specifically. (The PHASE 3C postcode-tokenization bug from `KIRO_REVIEW_05` is still real and still needs its own fix for city-wide `book`/`restaurant` tours like the London movie-locations case — that's unrelated to this document and unaffected by it.)

---

## Known adjacent risk, not introduced by this fix — flagging for awareness

`_classify_tour_category`'s `specialized_keywords` list includes bare words like `'park'`, `'garden'`, `'botanical'`. A request like "Hyde Park tour, London" (no "walking" phrase) would compute `_pre_category == 'specialized'` from the word "park" alone — already true today, unrelated to this change. Not fixing in this pass; noted so it isn't mistaken for a regression later (same note as in `KIRO_REVIEW_05`).

---

## Verify — primary test case first, then the regression set

**1. The actual live test case:**
```
curl -X POST http://localhost:5002/generate-complete-tour \
  -d '{"location":"Camel Tour in a desert of Abu Dhabi, UAE","tour_type":"museum","total_stops":5,"user_id":"test","narrative_tone":"general"}'
```
Check logs for `Detected tour category: WALKING` (not `MUSEUM`), confirm no "could not be verified with enough works" error, confirm stops survive with realistic desert-route spread (not collapsed or rejected).

**2. Secondary wide-area cases** (from `KIRO_REVIEW_04`):
- `"Road trip along the California coast"`
- `"Horseback tour of the ranch trails, Wyoming"`

**3. Regression set — must not change:**
- `"Medfield State Hospital"` → still `museum` (this is the case Kiro's exclusion of `'walking'` pre-category from suppression was specifically protecting — confirm it still works with the added `or wide_area_transport` condition, since Medfield's `wide_area_transport` should correctly be `false`)
- `"Palais Lascaris, Nice, France"` → still `museum`
- `"Walking tour of downtown Boston"` → still `walking`, and GEO-CHECK still runs and still removes genuinely-too-far outliers
- `"London movie locations tour"` → still `book` (independent of this fix — don't let this document's changes touch that path)

Report back with actual log output for the camel-tour case and the full regression set — same evidence standard as every round so far.
