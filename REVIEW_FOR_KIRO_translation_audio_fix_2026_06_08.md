# REVIEW_FOR_KIRO — Translation Audio Fix (2026-06-08)

**Session scope:** Fix translation service bugs found during testing with Audioura v2.1.1+7 — translated tours had English audio and Korean was going to Chinese.

---

## Problem Summary (from test log)

**Test:** Generated a walking tour of Boston (9 stops), then requested translations to Russian (`ru`) and Korean (app sent `zh`).

**Symptoms:**
1. **Listen Page:** All 3 tours showed English titles (mobile-side issue — see below)
2. **Russian tour:** HTML text was translated to Russian ✅, but audio mp3 files were still English ❌
3. **Korean tour:** Everything was in English (actually Chinese — app sent `zh` not `ko`) ❌

**Root cause from Cloud Run logs:**
```
WARNING: No tour content found for tour 355, falling back to ZIP extraction
INFO: Found 0 embedded audio data URLs
INFO: Generated translated audio 1/10 (132344 chars)  ← audio WAS generated
...
INFO: Successfully translated ZIP with 0 embedded audio files  ← but never written to mp3 files!
```

---

## Root Cause Analysis

### Bug 1: `translate_zip_audio()` doesn't handle modernized ZIP format

**Flow:** Tour 355 had `tour_content = NULL` in the database → `translate_tour_with_audio()` fell back to `_translate_tour_from_zip()` → which calls `translate_zip_audio()`.

**The bug:** `translate_zip_audio()` ONLY handled the legacy format (base64-embedded audio in the HTML). For the modernized format (separate `audio_1.mp3`, `audio_2.mp3`, ... files), it:
1. Found 0 embedded base64 audio patterns ✅ (correct — they're separate files)
2. Generated translated audio via Polly ✅ (correct — audio bytes were produced)
3. Tried to replace base64 in HTML using `zip(audio_matches, translated_audio_data)` — but `audio_matches` was empty, so the loop iterated zero times ❌
4. Re-packaged the ZIP with the **original untouched mp3 files** ❌

**Compare with `_create_mobile_compatible_zip()`** (the primary path when `tour_content` exists): it already had modernized format detection and writes translated bytes directly to `audio_N.mp3` files. The fallback path simply never got this logic.

### Bug 2: Korean → Chinese language code

The mobile app sent `zh` (Chinese) when the user selected "Korean". Korean is `ko`. This is a **mobile-side bug** (not fixable server-side), but we added `ko` to all server-side supported-language lists and the Polly voice map so it'll work once the app sends the right code.

### Issue 3: English titles on Listen Page (mobile-side)

The log shows: `TOUR: Saved translated tour 356 (ru) as: walking tour with stops at COLUMBUS WATERFRONT PARK...`

The app saves translations using the **original English request string** as the display title. The server correctly stores a translated `tour_name` and `request_string` in the database (confirmed in `_translate_tour_from_zip`), but the app's local save logic uses its own cached title. This is a **mobile-side fix** — the app should either:
- Use the translated `tour_name` from the downloaded ZIP's manifest.json, or
- Fetch the translated name from a server metadata endpoint

---

## Changes Made

### 1. `translation-service/translation_service.py` — Modernized format support in `translate_zip_audio()`

Added detection of separate `audio_N.mp3` files and a new code path that:
- Extracts paragraph text from HTML, grouped to match the mp3 file count
- Translates each text block via AWS Translate
- Generates Polly TTS audio in the target language
- **Writes translated audio bytes directly to `audio_N.mp3` files** (overwriting originals)
- Translates HTML headings and paragraphs using `NavigableString` (safe for nested tags)
- Translates the `<title>` tag
- Re-packages the ZIP

The legacy base64-embedded path is preserved unchanged for older tours.

### 2. `translation-service/translation_service.py` — Added Korean voice (`ko: Seoyeon`)

```python
voice_map = {
    ...
    'ko': 'Seoyeon'
}
```

### 3. `development/translation_service.py` — Same two fixes (local Docker copy)

Applied identical changes to the top-level file used by Docker Compose.

### 4. `tour_orchestrator_service.py` — Added `ko` to supported languages

```python
supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh', 'ko']
```

### 5. `news_orchestrator_service.py` — Added `ko` to supported languages

Same change.

---

## Why the Russian Tour HTML Was Translated But Audio Wasn't

The `translate_zip_audio()` code **did** translate HTML text (paragraphs and headings) because that section runs unconditionally after the audio replacement attempt. So you got:
- ✅ Translated HTML (visible text in Russian)
- ❌ English audio (mp3 files untouched because the base64 replacement loop did nothing)

After the fix, both the HTML text AND the mp3 files will be translated.

---

## Mobile-Side Issues (NOT fixed here — for Mobile Amazon-Q)

| Issue | Details |
|-------|---------|
| Korean sends `zh` instead of `ko` | App's language picker maps Korean to wrong code |
| Titles in English on Listen Page | App saves translations with local English `original_request` instead of server's `translated_name` |

---

## Files Modified

| File | Change |
|------|--------|
| `development/translation-service/translation_service.py` | Modernized ZIP audio fix + Korean voice |
| `development/translation_service.py` | Same (local Docker copy) |
| `development/tour_orchestrator_service.py` | Added `ko` to supported languages |
| `development/news_orchestrator_service.py` | Added `ko` to supported languages |

---

## Deployment

After review, deploy the translation service:
```bash
gcloud run deploy translation-service \
  --source=development/translation-service \
  --region=us-central1 \
  --project=audiotours-migration
```

Then re-test: generate a new tour (so `tour_content` gets populated — OR test with tour 355 which will hit the now-fixed fallback path) and translate to Russian.

**Note:** The existing translated tours (356, 357) in the database still have English audio. To fix them without re-generating, you could:
```sql
DELETE FROM audio_tours WHERE id IN (356, 357);
```
Then re-request translation from the app — the service will regenerate them with the fixed code.

---

## Risk Assessment

- **`translate_zip_audio` fix:** Medium confidence. The text-grouping heuristic (matching paragraph count to mp3 count) is imperfect — if the HTML has more paragraphs than stops, it concatenates text per stop. This may produce slightly different text-to-audio mapping than the primary path (`translate_tour_with_audio` with `tour_content`). But it's strictly better than the current behavior (English audio).
- **Korean voice:** Zero risk — additive.
- **Supported languages list:** Zero risk — additive, no existing behavior changed.

## Why `tour_content` Was NULL

Tour 355 was likely generated by an older version of the orchestrator that didn't store `tour_content` in the `audio_tours` table. Newer generations (after the Cloud Tasks restructure) store it. The fallback path will remain needed for any pre-existing tours.
