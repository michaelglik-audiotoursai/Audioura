# REVIEW_FOR_KIRO — Manifest Title Fix + Single Source of Truth (2026-06-08)

**Context:** Cloud-generated translated tours showed English titles on Listen page while locally-generated ones showed translated titles. Root cause: two code paths + a stale duplicate file.

---

## Problem

The app reads the tour title from `manifest.json` inside the ZIP (`data['name']`). Two translation code paths exist:

1. **Primary path** (`translate_tour_with_audio` → `_create_mobile_compatible_zip`): Updates `manifest['name']` with the translated name ✅ — this is what runs locally because local tours have `tour_content` populated.

2. **Fallback path** (`_translate_tour_from_zip` → `translate_zip_audio`): Did NOT update `manifest.json` ❌ — this is what runs on cloud because cloud tours often have `tour_content = NULL` (older generation).

Same code file, different branch taken due to data state. Not a cloud-vs-local code difference.

---

## Fix 1: `manifest.json` update in `translate_zip_audio` modernized path

Added manifest update to the fallback path, matching what the primary path already does:

```python
# In translate_zip_audio, modernized format section, after translating HTML:
manifest_path = os.path.join(extract_dir, 'manifest.json')
if os.path.exists(manifest_path):
    manifest = json.load(open(manifest_path))
    original_name = manifest.get('name', '')
    if original_name:
        translated_manifest_name = self.translate_text(original_name, target_language)
        manifest['name'] = translated_manifest_name
        manifest['short_name'] = translated_manifest_name[:12]
    json.dump(manifest, open(manifest_path, 'w'), indent=2, ensure_ascii=False)
```

Now BOTH code paths update `manifest.json` → titles show translated regardless of which branch runs.

---

## Fix 2: Eliminated stale duplicate — single source of truth

**Before:** Two copies of the translation service existed:
- `development/translation_service.py` (82 KB) — stale duplicate, unused
- `development/translation-service/translation_service.py` (83 KB) — canonical, used by BOTH Docker Compose and Cloud Run

**Evidence it was unused:**
- `docker-compose.yml` line 124: `build: ./translation-service` (builds from subdirectory)
- No other compose file references translation service
- No Python file imports from the top-level copy
- `Dockerfile.cloudrun` copies `*.py` but that image is NOT used for the translation service

**Action:** Deleted `development/translation_service.py`.

**After:** Single file at `development/translation-service/translation_service.py`:
- Docker Compose builds from `./translation-service` → uses this file locally
- Cloud Run deploys from `--source=development/translation-service` → uses this file on cloud
- **One file, one truth. No more drift.**

---

## Why the local/cloud behavior differed (data, not code)

| | Local | Cloud |
|---|---|---|
| `tour_content` in DB | Populated (fresh generation) | NULL (older tours) |
| Translation path | Primary (`translate_tour_with_audio`) | Fallback (`translate_zip_audio`) |
| `manifest.json` updated? | ✅ (primary path had it) | ❌ (fallback path was missing it) |
| Title on Listen page | Translated ✅ | English ❌ |

After the fix, both paths update manifest → both produce translated titles.

---

## Deployment

| Service | Revision | Change |
|---------|----------|--------|
| `translation-service` | `translation-service-00009-7rh` | manifest.json update in fallback path |

---

## Files

| Action | File |
|--------|------|
| Modified | `development/translation-service/translation_service.py` |
| **Deleted** | `development/translation_service.py` (stale duplicate) |

---

## Risk

- **Manifest fix:** Zero risk. Additive — reads existing `name` from manifest, translates it, writes it back. Same logic the primary path has used successfully.
- **File deletion:** Low risk. Verified no imports, no Dockerfile references, no compose references to the top-level copy. Docker Compose and Cloud Run both use the subdirectory file.
- **Regression concern:** If any future service accidentally imports from the deleted path, it will fail immediately at startup (import error) rather than silently using stale code. Fail-fast is better than silent divergence.

---

## Retest

Generate a cloud tour, request translations (RU, ZH). Listen page should now show translated titles — same as local behavior.
