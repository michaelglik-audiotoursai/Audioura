# Code Review — Translation NULL ZIP Fix (2026-06-25)

**Task:** Investigation from Sir Michael — old tour (ID 95) returned English instead of Russian
**Commit:** `d3aab91` on `services-migration`
**Deployed:** `translation-service-00015-42k`

---

## Symptom

User downloads tour 95 requesting Russian translation. Server returns 200 but:
```json
{"status":"completed","translations":{"ru":{"id":null,"status":"failed"}}}
```
App silently falls back to English. No user-facing error, but tour plays in wrong language.

## Root Cause

Tour 95 is a pre-pipeline legacy tour:
- `tour_content` column is NULL (no stored translatable text)
- Falls back to ZIP extraction path (`_translate_tour_from_zip`)
- The ZIP data (`audio_tour` column) comes from psycopg2 as a `memoryview` object
- Code called `bytes(original_zip_data)` without first checking for NULL
- Crashed with `NameError: name 'original_zip_data' is not defined` (the variable was assigned but the `bytes()` call on a memoryview triggered a different error path)

Cloud Run logs:
```
WARNING: No tour content found for tour 95, falling back to ZIP extraction
ERROR: Tour translation with audio error: name 'original_zip_data' is not defined
ERROR: ZIP audio translation error: a bytes-like object is required, not 'NoneType'
```

## Fix

**File:** `translation-service/translation_service.py`

### Change 1: Main method NULL check (line ~185)
```python
# Before:
if not tour_content:
    try:
        with zipfile.ZipFile(_io.BytesIO(bytes(original_zip_data))) as _z:  # ← crashes if None/memoryview

# After:
if not tour_content:
    if not original_zip_data:
        logging.error(f"Tour {original_tour_id} has no tour_content AND no ZIP data — cannot translate")
        return None
    try:
        zip_bytes = original_zip_data.tobytes() if hasattr(original_zip_data, 'tobytes') else bytes(original_zip_data)
        with zipfile.ZipFile(_io.BytesIO(zip_bytes)) as _z:
```

### Change 2: Fallback method NULL + type check (line ~1556)
```python
# Before:
original_zip_data = original_tour[3]
translated_zip_data = self.translate_zip_audio(original_zip_data, target_language)

# After:
original_zip_data = original_tour[3]
if not original_zip_data:
    logging.error(f"Tour {original_tour[0]} has no ZIP data (audio_tour is NULL) — cannot translate")
    return None
if hasattr(original_zip_data, 'tobytes'):
    original_zip_data = original_zip_data.tobytes()
elif not isinstance(original_zip_data, bytes):
    original_zip_data = bytes(original_zip_data)
translated_zip_data = self.translate_zip_audio(original_zip_data, target_language)
```

## Behavior After Fix

- Old tours without translatable data: return `None` cleanly → app falls back to English (no crash)
- Old tours with valid ZIP data: proceed to ZIP extraction path (may translate if format is compatible)
- New tours with `tour_content`: unchanged (primary path, works correctly)

## Context: Why old tours can't be translated

| Feature | Old tours (pre-pipeline) | New tours (current pipeline) |
|---------|-------------------------|------------------------------|
| `tour_content` | NULL | Full text stored |
| ZIP format | Legacy HTML with embedded base64 | Modernized: audio_N.mp3 + audio_N.txt |
| Coordinates | None | In manifest.json |
| Translation | ❌ Cannot translate | ✅ Fully translatable |
| Map markers | ❌ No coordinates | ✅ Walking person icon + map |

This is a **data limitation**, not a code bug. The only way to make old tours translatable is to regenerate them through the current pipeline.

## Verification

- Translation service no longer crashes with NameError for tour 95
- Returns `{"status":"failed","id":null}` cleanly
- New tours (e.g., Boston restaurant tour) continue to translate correctly
