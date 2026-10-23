# SUBMISSION — LOCAL-747

**Saving an edit keeps the map buttons, and the phone can download the saved tour.**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-747-edit-save-html-and-download`
- **Base (subscribed):** `7332bfb59c8190fd405928a40b81e013d03e83ff`
- **code_sha:** `7332bfb59c8190fd405928a40b81e013d03e83ff` (`git merge-base --is-ancestor 7332bfb5 HEAD` → exit 0)

---

## What Michael saw (tour 716, community 10, 2026-10-23 15:35)

1. Edit → change stops 1 and 4 → **Save All**: a green message, then a red *"download failed"*. Edit-service log, same second:
   ```
   POST /tour/716/update-multiple-stops 200
   ERROR in app: Exception on /tour/13ed30d1-.../download [GET]
     return send_file(str(zip_path), as_attachment=True, download_name=f"{tour_path.name}.zip")
   TypeError: send_file() got an unexpected keyword argument 'download_name'
   ```
2. After the save, the tour's own page had **no map buttons** at any stop.
3. The biking tour's stop icon was the generic map pin, not a bike.

## Root causes

1. The edit-service image runs **Flask 1.1.4**, whose `send_file` keyword is `attachment_filename`; the code passed `download_name` (Flask ≥2.0). The `/tour/<id>/download` route raised `TypeError` → 500. (Same class of bug fixed once before in 6 other services, Docker round 4.)
2. `tour_editing_phase2.create_clean_html()` wrote a fresh `index.html` with **no** `.map-btn` / `openMap()`. The generator (`tour_generation_modernized.generate_html_with_external_audio`) adds a map button to every stop whose text has a `Coordinates:` line; the editor's version never did. The edited `audio_N.txt` keep their `Coordinates:` lines, so the data was there — only the HTML dropped it.
3. The per-stop icon map (`_CATEGORY_ICONS`) had walking / restaurant / museum / specialized only; biking fell back to 🗺️.

## Fix

**New shared module `tour_html_map.py`** — single source of truth for the map button so it is not copied a third time:
- `COORDINATES_RE`, `stop_has_coordinates()`
- `CATEGORY_ICONS` (walking 🚶 / restaurant 🍴 / museum 🏛️ / specialized 🗺️ **+ biking 🚲 + cycling 🚲**), `FALLBACK_ICON` 🗺️, `category_icon()`
- `MAP_BTN_CSS`, `OPENMAP_SCRIPT`
- `build_map_button(stop_text, stop_num, tour_category)` — button only when the stop has coordinates, with the per-category icon. Byte-identical to the generator's original button.

**`tour_generation_modernized.py`**
- Replaced the local `_COORDINATES_RE` / `_CATEGORY_ICONS` / `_stop_has_coordinates` with imports from `tour_html_map` (names kept as aliases); the HTML loop now calls `_build_map_button`.
- Added the version-tolerant `_compat_send_file` wrapper and reassigned `send_file`, fixing the raw `download_name` call in its own download route.

**`tour_editing_phase2.py`**
- Added `_compat_send_file` (picks `download_name` vs `attachment_filename` from the installed Flask's `send_file` signature via `inspect`) and `send_file = _compat_send_file` — fixes all three `download_name` call sites in the download route.
- Rewrote `create_clean_html` to inject `MAP_BTN_CSS` + `OPENMAP_SCRIPT` and a per-stop `build_map_button`, reusing the shared module. The editor page's **audio player and voice-control script are kept unchanged** (`playAudio` / `pauseAudio` / `nextStop` / `previousStop` / `goToStop` / `repeatStop` / `pauseAllAudio` / `initializeAudio`).
- Category for the per-stop icon is recovered fail-soft (`_derive_tour_category`): scan the stop texts, then any copied non-audio `.txt`, for a `Tour-Category:` line; unknown → `''` → the generic 🗺️, exactly the generator's default.

**`translation-service/translation_service.py`** (`_generate_translated_html`, the legacy/dead map-button path, ~line 2988)
- Replaced the hardcoded 🗺 with a category-aware inline icon map including biking/cycling → 🚲, derived fail-soft from the stop text. Inlined (not imported) because this service builds its own Docker image and does not share the repo root.

## Red tests (fail on 7332bfb5, pass after the fix)

`tests/test_local747_edit_save_html_and_download.py` — standalone, heavy deps mocked, Windows-safe.

| Assertion | Baseline 7332bfb5 | After fix |
|---|---|---|
| `/tour/<id>/download` returns **200 + ZIP** under a Flask-1.1.4 `send_file` | **500** (TypeError on `download_name`) | **200** |
| `create_clean_html` of a 3-stop coords tour → **3 `class="map-btn"`** + `openMap(` | 0 buttons, no `openMap` | 3 + `openMap` |
| Edited page keeps `playAudio` (voice control) | pass (guard) | pass |
| Biking / cycling tour map button → **🚲** | no 🚲 (generic pin) | 🚲 |
| Walking tour still → 🚶 (no regression) | pass (guard) | pass |

Result: **baseline 3 passed / 6 failed (RED)** → **after fix 9 passed / 0 failed (GREEN)**.

### Existing edit-service tests (baseline vs now)
Ran 11 edit-service tests at a clean 7332bfb5 (changes stashed) and again with the fix:
`test_gcs5e_polly_auth_and_fail`, `test_gcs5r2_update_stop_empty_text`, `test_gcslang1_language_gate_narration`, `test_gcssan1_narration_and_tts_strip`, `test_local153_tour_editing_shims_guard`, `test_local311_versioned_evaluator`, `test_local312_quality_comms_and_user_index`, `test_local595_edit_gate`, `test_local745_member_update`, `test_local745_organiser_only`, `test_local745_zip_only_resolve`.
**All 11 exit 0 at baseline and with the fix.** No pre-existing failures, no regressions.

## Live proof (own container only)

Container `local747-edit` from `audioura-tour-generator:latest` (verified **Flask 1.1.4**, `send_file` signature exposes `attachment_filename`, not `download_name`), on network `development_default`, host port **5099→5022**, volume mode, the fixed code mounted over `/app`, a **temp** tours dir (never `/Users/micha/Audioura/tours`), boto3 pip-installed at boot like the live service. No `audioura-*` container was replaced, renamed, or touched (`tour-editing-phase2-1` stayed up healthy throughout).

Fixture: a 716-like biking tour (`...biking_tour_salem_ma__ad5f966f`, `Tour-Category: biking` in a copied `source_tour.txt`, 3 stops each with a `Coordinates:` line).

- **Baseline contrast (same image):** the 7332bfb5 `tour_editing_phase2.py` served the download → **HTTP 500** with the exact production error `TypeError: send_file() got an unexpected keyword argument 'download_name'`. The fixed file, same request → **HTTP 200** + a valid ZIP.
- **Full flow:** `POST /tour/<id>/update-multiple-stops` editing stops 1 & 3, preserving 2 → **HTTP 200**, green *"Tour updated successfully with 3 text-to-speech audio file(s)"*. Then `GET /tour/<new-uuid>/download` → **HTTP 200**, 82 352 bytes. Unzipped `index.html`:
  - `class="map-btn"` × **3**, `openMap(` present,
  - all three buttons render **🚲** (biking category recovered from the copied source file),
  - `playAudio` + `goToStop` (voice control) preserved.

### Row counts (shared DB `audiotours`, before → after)
| Table | Before | After |
|---|---|---|
| `audio_tours` | 512 | 512 |
| `audio_tour_versions` | 69 | 69 |
| `author_edit_scores` | 0 | 0 |

No `DELETE FROM audio_tours`. The temp fixture is not a DB-registered tour, so the DB-update branch was a no-op; the save wrote only to the temp tours volume (new tour dir + ZIP).

### Budget
Edit TTS only: 3 stops synthesised via the local Kokoro engine — Polly `[COST_METER] $0.000000 engine=kokoro`. **$0.00** (≤ $0.10).

## Files changed
- `tour_html_map.py` (new)
- `tour_editing_phase2.py`
- `tour_generation_modernized.py`
- `translation-service/translation_service.py`
- `tests/test_local747_edit_save_html_and_download.py` (new)
