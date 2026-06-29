# REVIEW_FOR_KIRO — Stop Count Fix + Translation Titles (2026-06-08)

**Context:** Testing with Audioura v2.1.1+7, request: "walking tour with stops at BLUE HILLS RESERVATION, NEPONSET RIVER RESERVATION, STONY BROOK RESERVATION, BELLEVUE HILLTOP, Milton, MA" in English, Russian, Chinese.

---

## Issues Found and Fixed

### 1. 🔴 Only 1 stop generated instead of 4

**Root cause from Cloud Run logs:**
```
PHASE 3C: REMOVED 'NEPONSET RIVER RESERVATION' -- address 'Dorchester, MA 02124' not in '...Milton, MA'
PHASE 3C: REMOVED 'STONY BROOK RESERVATION' -- address 'Hyde Park, MA 02136' not in '...Milton, MA'
PHASE 3C: REMOVED 'BELLEVUE HILLTOP' -- address 'Bellevue Hill, Boston, MA 02132' not in '...Milton, MA'
PHASE 3C: 3 out-of-area stop(s) removed; 1 remain
```

Phase 3C validates that each POI's address matches the location string. The location ends with "Milton, MA", so Phase 3C checked if each address contains "Milton". It doesn't — these parks are in Dorchester, Hyde Park, and Boston. All three were removed despite the user **explicitly naming them** in the request.

The replacement loop (Part C) then tried to find 3 replacement POIs in Milton but couldn't find valid ones either.

**Fix:** Added explicit-stop detection before Phase 3C. When the user request contains "with stops at X, Y, Z" (or "stops: X, Y, Z"), those POI names are parsed and protected from Phase 3C address-based removal.

```python
# Detect user-explicit stops from request pattern "with stops at X, Y, Z"
_explicit_match = re.search(r'(?:with\s+)?stops\s+(?:at|:)\s*(.+?)...', location)
# ... parse stop names ...

# In Phase 3C loop:
if p_norm in _explicit_stop_names:
    print(f"   PHASE 3C: KEPT '{p['name']}' (user-explicit stop, address check bypassed)")
    continue
```

**File:** `development/generate_tour_text.py`  
**Deployed:** `audioura:v9` image → `tour-generator` service

---

### 2. 🔴 Titles all in English on Listen Page

**Root cause:** The translation API response only included `{"id": 359, "status": "translated"}` — no translated title. The mobile app had no choice but to use its own cached English title.

**DB verification confirmed the translated names ARE stored correctly:**
- Tour 359 (ru): Russian title ✅
- Tour 360 (zh): Chinese title ✅

**Fix:** Modified `/translate-with-audio` endpoint to include the translated `tour_name` in the response:

```json
// Before:
{"ru": {"id": 359, "status": "translated"}}

// After:
{"ru": {"id": 359, "status": "translated", "name": "Пешая прогулка с остановками..."}}
```

The mobile app needs to use this `name` field when saving the translated tour info. If the app currently ignores unknown fields, a small app-side change is needed to pick up `name`.

**File:** `development/translation-service/translation_service.py` + `development/translation_service.py`  
**Deployed:** `translation-service-00007-gr6`

---

### 3. Chinese tour investigation

**Finding:** The Chinese tour (ID 360) IS correctly generated and stored:
- ZIP contains: `index.html` (6220 bytes, Chinese title/headings), `audio_1.mp3` (918 KB, Chinese Polly TTS), `audio_1.txt` (Chinese script)
- The app log shows: `TOUR: Saved translated tour 360 (zh)` — it WAS downloaded

The Chinese tour IS on the Listen Page (`LISTEN: Loaded 6 valid tours`). The user couldn't distinguish it because all titles appeared in English (issue #2 above). With the title fix, the Chinese tour will show its Chinese title.

---

## Deployments This Session

| Service | Image/Revision | Change |
|---------|---------------|--------|
| `tour-generator` | `audioura:v9` | Phase 3C user-explicit-stop bypass |
| `translation-service` | `translation-service-00007-gr6` | `name` field in translation response |

---

## What the App Needs (for Mobile Amazon-Q)

The translation API now returns a `name` field per language:
```json
{
  "status": "completed",
  "translations": {
    "ru": {"id": 359, "status": "translated", "name": "Пешая прогулка..."},
    "zh": {"id": 360, "status": "translated", "name": "步行游览..."}
  }
}
```

The app should use `translations[lang]['name']` as the display title when saving the translated tour, instead of using the English `original_request`.

---

## Retest Instructions

1. Generate a new tour with the same request ("walking tour with stops at BLUE HILLS RESERVATION, NEPONSET RIVER RESERVATION, STONY BROOK RESERVATION, BELLEVUE HILLTOP, Milton, MA") — should now get 4 stops.
2. Check translation titles — server now sends `name` field. If app doesn't parse it yet, titles stay English until Mobile-AQ updates.
3. All three languages should appear on Listen Page (they always did — Chinese was there but visually indistinguishable due to English titles).
