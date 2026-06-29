# REVIEW_FOR_KIRO — Phase 3C Walking Fix + Translation Coordinates (2026-06-08)

**Context:** Two issues from testing: (1) walking tours lose stops on town borders, (2) translated tour ZIPs don't preserve coordinates for map pins on Listen page.

---

## Issue 1: Walking tours lose stops on town borders

### Problem

Phase 3C (address-based location guard) removes stops whose postal address doesn't string-match the city in the user's request. For a walking tour near "Milton, MA", nature reserves in adjacent towns (Dorchester, Hyde Park, Quincy) get removed even though they're walkable from Milton — they just have different postal city names.

The replacement loop (Part C) then also applies the same address check, so it can't find replacements either. Result: tour goes from 4 stops → 1 stop.

### Root cause

`_address_matches_location()` checks if address city words appear in the location string. "Dorchester" isn't in "Milton, MA" → rejected. But Dorchester is 2 km from Milton — well within walking distance.

### Fix

**Skip Phase 3C entirely for walking tours.** Walking tours already have a superior proximity validator: the **GEO-CHECK** (coordinate-based distance validation after Phase 3B). GEO-CHECK uses actual haversine distances between stops to catch truly dispersed stops — a far better proxy for "walkable" than postal city name matching.

```python
# Before: applied to all non-museum tours
if tour_category != 'museum' or not _museum_venue_name:
    location_rejects = [p for p in poi_list if not ...]

# After: walking tours skip Phase 3C, rely on GEO-CHECK
if tour_category == 'walking':
    print("PHASE 3C: skipped for walking tours (GEO-CHECK handles proximity)")
elif tour_category != 'museum' or not _museum_venue_name:
    location_rejects = [p for p in poi_list if not ...]
```

Same skip applied to the Part C replacement address check.

**Note:** Phase 3C still runs for restaurant tours and other non-walking/non-museum categories where city-name matching is a reasonable filter (you don't want a "Boston restaurants" tour suggesting a restaurant in Cambridge).

### Previous fix preserved

The user-explicit-stop bypass (from earlier this session) is still in place as a complementary safety net. If the user says "with stops at X, Y, Z", those named stops are never removed regardless of tour category.

---

## Issue 2: Translated `audio_N.txt` missing coordinates for map pins

### Problem

Mobile Amazon-Q reported: translated tours don't show the map icon on the Listen page. The app parses `Coordinates: 42.2361, -71.1075` from `audio_N.txt` to place map pins. In translated ZIPs, AWS Translate was mangling this line (translating the label, corrupting the numbers).

### Fix

In `translate_zip_audio` modernized format path:

1. After translating, call `_restore_metadata_labels(original, translated, lang)` to prepend the original English `Coordinates:` and `Address:` lines (identical to what the primary path already does).

2. For TTS audio, use `_strip_nav_fields_for_tts()` before translating — so Polly doesn't narrate "Coordinates: 42.2361, -71.1075" aloud.

3. Write the metadata-preserved version to `audio_N.txt`.

```python
translated_text = self.translate_text(source_text, target_language)
translated_text_with_meta = self._restore_metadata_labels(source_text, translated_text, target_language)

# TTS audio: strip metadata, translate separately
tts_source = self._strip_nav_fields_for_tts(source_text)
tts_translated = self.translate_text(tts_source, target_language)
audio_bytes = self.generate_audio(tts_translated, target_language)

# Write to ZIP:
# audio_N.mp3 ← tts_translated (no coordinates read aloud)
# audio_N.txt ← translated_text_with_meta (has English Coordinates: line for app to parse)
```

**Result:** Translated `audio_N.txt` now looks like:
```
Coordinates: 42.2361, -71.1075
Address: 695 Hillside St, Milton, MA 02186
[Translated narration in target language]
```

---

## Deployments

| Service | Image/Revision | Change |
|---------|---------------|--------|
| `tour-generator` | `audioura:v10` | Phase 3C skip for walking tours + user-explicit-stop bypass |
| `translation-service` | `translation-service-00008-g7j` | Coordinates preservation in translated ZIPs + `name` field in API response |

---

## Files Modified

| File | Change |
|------|--------|
| `development/generate_tour_text.py` | Skip Phase 3C for walking tours; skip Part C address check for walking tours |
| `development/translation-service/translation_service.py` | `_restore_metadata_labels` + `_strip_nav_fields_for_tts` in fallback path; `name` in API response |
| `development/translation_service.py` | Same (local Docker copy) |

---

## Risk Assessment

- **Phase 3C skip for walking tours:** Low risk. The GEO-CHECK (coordinate-based) is a strictly better proximity filter for walking. It runs later in the pipeline after coordinates are fetched. If GEO-CHECK finds a truly dispersed stop (>5 km), it removes it. Phase 3C was overly aggressive for walking tours specifically because town boundaries don't align with walkable geography.

- **Coordinates preservation:** Low risk. Uses the same `_restore_metadata_labels` that the primary path has used successfully. The only new thing is calling `_strip_nav_fields_for_tts` before audio generation — this is what the primary path already does, just wasn't in the fallback.

- **Remaining edge case:** If a walking tour request is truly ambiguous about geography (e.g. "walking tour Boston" but GPT suggests a stop in Providence, RI), Phase 3C would have caught it but now won't. GEO-CHECK will still catch it if it's >5 km from the cluster median. For tours with <3 stops having coordinates, GEO-CHECK is skipped — but in that case even Phase 3C's string matching was unreliable anyway.

---

## Retest

Generate "walking tour with stops at BLUE HILLS RESERVATION, NEPONSET RIVER RESERVATION, STONY BROOK RESERVATION, BELLEVUE HILLTOP, Milton, MA" again. Should now:
1. Return 4 stops (Phase 3C no longer removes the cross-border parks)
2. Map icon should appear on Listen page for translated tours (coordinates preserved)
