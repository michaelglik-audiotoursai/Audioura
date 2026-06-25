# Code Review — Translation R2 Blob Fallback (2026-06-25)

**Commit:** `8f1ef19` on `services-migration`
**Deployed:** `translation-service-00017-lt6`

---

## Symptom

User selects a tour on the home page (tour ID 79 — "Very Short walking tour for Newton Center") and requests download in Russian. The server returns HTTP 200 but the translation is `{"status":"failed","id":null}`. The app silently falls back to serving the English version. No error shown to user.

Same behavior for tour 95 (Nice, France) — any tour stored in R2 blob storage cannot be translated.

## Analysis

1. The English download works fine — `map_delivery_service.py` serves tour 79 correctly by reading from R2 blob (`tour_blob_uri = 'tours/79.zip'`).

2. The translation service queries:
   ```sql
   SELECT id, tour_name, request_string, audio_tour, ... FROM audio_tours WHERE id = 79
   ```
   Result: `audio_tour` (BYTEA column) is **NULL**. The data lives in R2 (`tour_blob_uri`), not in the DB.

3. The translation service only checked `original_tour[3]` (the BYTEA column) and never read `tour_blob_uri`. Found NULL → "cannot translate."

4. **Why the BYTEA column is NULL:** When tours were migrated to R2 blob storage, the large binary data was moved out of PostgreSQL to save DB space. The `tour_blob_uri` column points to the R2 object key, and `audio_tour` was set to NULL.

## Root Cause

The translation service had no R2 integration. It could only translate tours whose ZIP was stored inline in the `audio_tour` BYTEA column. All R2-stored tours (the majority of community/old tours) were untranslatable.

## Fix

**File:** `translation-service/translation_service.py`

### 1. Extended the SQL query to include `tour_blob_uri` (line ~172)
```python
# Before:
"SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language FROM audio_tours WHERE id = %s"

# After:
"SELECT id, tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language, tour_blob_uri FROM audio_tours WHERE id = %s"
```

### 2. Added R2 download fallback when `audio_tour` is NULL (lines ~193–207)
```python
tour_blob_uri = original_tour[9]
if not original_zip_data and tour_blob_uri:
    s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT, ...)
    response = s3.get_object(Bucket=R2_BUCKET, Key=tour_blob_uri)
    original_zip_data = response['Body'].read()
```

### 3. Pass R2 data to fallback method via `zip_data_override` parameter (line ~225)
```python
# Before:
return self._translate_tour_from_zip(original_tour, target_language)

# After:
return self._translate_tour_from_zip(original_tour, target_language, zip_data_override=original_zip_data)
```

### 4. Updated `_translate_tour_from_zip` signature (line ~1569)
```python
def _translate_tour_from_zip(self, original_tour, target_language, zip_data_override=None):
    original_zip_data = zip_data_override if zip_data_override else original_tour[3]
```

### 5. Deployed with R2 credentials
Added `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` env vars to the translation-service (same values as map-delivery).

## Verification

**Before fix:**
```
POST /translate-with-audio {content_id: "79", content_type: "tour", languages: ["ru"]}
→ {"status":"completed","translations":{"ru":{"id":null,"status":"failed"}}}
```

**After fix:**
```
POST /translate-with-audio {content_id: "79", content_type: "tour", languages: ["ru"]}
→ {"status":"completed","translations":{"ru":{"id":385,"name":"Очень короткая пешеходная экскурсия...","status":"translated"}}}
```

Tour 79 now translates to Russian (tour ID 385 created) with full audio re-synthesis via Polly TTS.

## Impact

All R2-stored tours (the majority of community tours in the DB) are now translatable. Previously only tours with inline BYTEA data could be translated.
