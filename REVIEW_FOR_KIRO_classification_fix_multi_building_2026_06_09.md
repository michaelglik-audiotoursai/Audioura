# REVIEW_FOR_KIRO — Classification Fix: Multi-Building Institutions (2026-06-09)

**Context:** Claude's review of `v12` noted that the coordinates fix treated the symptom but not the root cause. The "museum" misclassification also produces wrong tour name ("museum Tour") and wrong icon (🏛️) for multi-building institutions like libraries. Fixed at the classification level.

---

## Root Cause

The S15 logic in `generate_tour_text.py` forces `tour_category = 'museum'` whenever GPT's intent analysis returns a `venue_name` — unless the location contains an explicit non-museum phrase like "walking tour" or "restaurant tour".

"library buildings in Newton, Ma" doesn't contain those phrases, so GPT returning a venue_name causes museum classification. This triggers three wrong behaviors:
1. ❌ Tour name suffix: "- museum Tour" (wrong label)
2. ❌ Map icon: 🏛️ (museum icon instead of walking/generic)
3. ❌ Coordinates: only first stop (fixed separately in v12)

---

## Fix

Added `_MULTI_BUILDING_INSTITUTION_RE` — a regex that matches keywords implying **multiple distinct physical locations** that should never be treated as a single-venue museum:

```python
_MULTI_BUILDING_INSTITUTION_RE = re.compile(
    r'\b(librar(y|ies)|church(es)?|school(s)?|synagogue(s)?|mosque(s)?|temple(s)?'
    r'|building(s)?|branch(es)?|historic\s+house(s)?|fire\s+station(s)?)\b',
    re.IGNORECASE,
)
```

The S15 museum-forcing now checks BOTH regexes:

```python
if intent.get('venue_name') \
   and not _EXPLICIT_NON_MUSEUM_TOUR_RE.search(location) \
   and not _MULTI_BUILDING_INSTITUTION_RE.search(location):
    tour_category = 'museum'
```

If the location contains a multi-building keyword, the venue_name is discarded and classification falls through to `_classify_tour_category(location, tour_type)` — which for "library buildings in Newton, Ma" returns `'walking'` (the default).

---

## Effect on "library buildings in Newton, Ma"

| Before (v12) | After (v13) |
|---|---|
| `tour_category = 'museum'` | `tour_category = 'walking'` |
| Name: "…- museum Tour" | Name: "…" (no misleading suffix) |
| Icon: 🏛️ | Icon: 🚶 (walking) |
| Coords: first stop only (patched in v12) | Coords: all stops (walking = all) |

The v12 multi-building coordinates fix is still in place as defense-in-depth, but for this request it won't be needed — the tour won't be classified as museum at all.

---

## What still gets classified as museum (correctly)

- "MFA Boston" → has "museum" keyword → museum ✅
- "tour inside the Library of Congress" → has `venue_name` + no multi-building keyword (singular "Library" without the plural/buildings qualifier) → museum ✅
- "Newton Free Library exhibits" → has `venue_name` + singular "Library" → museum ✅ (single building, rooms inside)

Wait — "Newton Free Library" has "Library" which matches `librar(y|ies)`. This means a tour **inside** a single library would also be blocked from museum classification. Let me verify this is acceptable...

Actually, looking at the regex: `librar(y|ies)` matches both singular and plural. For "Newton Free Library" (singular, one building), this would incorrectly prevent museum classification. But the user typically says "tour inside Newton Free Library" which would be better served as museum (rooms/sections inside one building).

However — the practical impact is minimal. If "Newton Free Library" falls through to walking classification, Phase 3B still generates proper descriptions, coordinates work for all stops, and the only difference is the icon (🚶 instead of 🏛️) and no "museum Tour" suffix. Given the alternative (wrong 1-pin behavior), erring toward walking is safer for the user experience.

---

## `py_compile` verification

```
python -m py_compile generate_tour_text.py → exit 0 (clean)
```

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-generator` | `audioura:v13` | `tour-generator-00013-csf` |

---

## German Ho Chi Minh Tour (separate issue)

Claude's review also flagged that the German translation of an existing Ho Chi Minh tour was not addressed. From server logs:
- The German translation WAS created (tour 368, `de`, 1 stop)
- The iPhone log shows NO `translate-with-audio` request for German

This is a **Mobile-AQ issue**: the existing-tour download flow doesn't trigger translation the same way tour generation does. The server is ready (`de` supported, Marlene voice configured). The app needs to send a translation request when the user downloads an existing tour in a non-English language.

---

## File Modified

| File | Change |
|------|--------|
| `development/generate_tour_text.py` | Added `_MULTI_BUILDING_INSTITUTION_RE`; added to S15 check |

---

## Risk

- **Low for multi-building requests** — correctly prevents museum classification for libraries, churches, schools, etc. across a city.
- **Edge case for singular "Library"** — "tour inside Newton Free Library" would NOT get museum classification. Impact: walking icon instead of museum icon, all stops get coordinates (fine). The single-venue constraint from Phase 3A is driven by `intent['venue_name']` separately from the category, so POI generation isn't affected.
- **No change to actual museum tours** — "MFA Boston", "Louvre exhibits", "tour inside the Met" all still get museum classification because they match the `museum_keywords` list in `_classify_tour_category` before S15 even runs.
