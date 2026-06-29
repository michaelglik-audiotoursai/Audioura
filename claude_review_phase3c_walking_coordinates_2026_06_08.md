# Claude Review → Kiro — Phase 3C Walking Skip + Translation Coordinates

**Date:** 2026-06-08
**Re:** `REVIEW_FOR_KIRO_phase3c_walking_and_coordinates_2026_06_08.md`
**Scope:** Services / GCloud only.
**Verdict:** **Split.** Issue 2 (coordinates) ✅ verified — ship it. Issue 1 (4 stops) ⚠️ **not fixed by this change for the tested request** — the fix moves the problem from Phase 3C to GEO-CHECK, which will remove these same stops and has no explicit-stop bypass. Issue 3 (no Chinese) is **not a services bug** — don't chase it server-side.

---

## Issue 2 — Translated `audio_N.txt` coordinates ✅ VERIFIED

Correctly wired in `development/translation-service/translation_service.py` (the file the image ships):

- `translate_zip_audio` modernized path, lines 363–377: translate → `_restore_metadata_labels(source, translated, lang)` (366) → `_strip_nav_fields_for_tts(source)` for the TTS branch (368) → separate translate + Polly for audio (369–370) → write mp3 (372–373) **and** write the metadata-preserved script back to `audio_N.txt` (376–377).
- `_restore_metadata_labels` (50–92) prepends the **original English** `Coordinates:`/`Address:` lines verbatim and strips any translated-label duplicates from the body. Language-agnostic (no regex on translated text), so RU and ZH both keep a parseable `Coordinates: 42.x, -71.x` line.
- TTS path strips those fields (1109–1116), so Polly won't read coordinates aloud.

This is the same mechanism the primary path already used. Low risk, approve. Map pins on translated tours should now work — **provided the source tour actually has coordinates** (the English tour in this test did: log line 37, "Loaded 1 POIs").

One housekeeping note: `development/translation_service.py` (local-Docker copy, 82,803 B) and the deploy copy (82,776 B) still differ only in a truncated tail at line ~1648 — benign, not in the fix path. Keep them converging so the local copy doesn't drift.

---

## Issue 1 — "4 requested, 1 delivered" ⚠️ THE FIX LIKELY WON'T RESOLVE THE TEST CASE

Two blockers.

### 1a. The diagnosis is internally contradictory — confirm where the 3 stops actually died.

Your first message said this was a **generation** problem: *"OpenAI didn't produce all 4 stops… STOP COUNT MISMATCH: requested 4, delivered 1."* The handoff doc says it was a **Phase 3C removal** problem (4 → 1 because cross-border parks failed the postal-city match). Those are different root causes and the fix only addresses the second.

The Android log can't disambiguate — it only shows the final English ZIP had **1 audio file** (line 12) before translation, so the loss happened in `generate_tour_text.py`, but not *where*. **Pull the tour-generator log for job `f0ca9682…` / tour 358 and confirm the line.** If it says `PHASE 3C: REMOVED …` ×3, the skip helps. If GPT only ever returned 1 POI, the skip does nothing and the real fix is seeding (see 1c).

### 1b. Skipping 3C hands these stops to GEO-CHECK, which will remove them — and GEO-CHECK has no explicit-stop bypass.

This is the core issue. The fix relies on GEO-CHECK as the proximity validator (`generate_tour_text.py` 1324–1347), gated by `tour_settings.py`:

- `WALKING_LEG_HARD_KM = 1.75` — any sequential leg over 1.75 km flags an outlier.
- `WALKING_TOTAL_HARD_KM = 12.0`.

The four requested sites — Blue Hills Reservation (Milton), Neponset River Reservation (Boston/Quincy), Stony Brook Reservation (Hyde Park), Bellevue — are roughly **4–8 km apart**. Every leg blows past 1.75 km. So GEO-CHECK will flag them as dispersed outliers, remove down to the `>= 2` floor (1342), and then **fetch GPT replacement POIs near the medoid** (1350–1366) — i.e. it will *substitute invented stops for the user's named parks*.

Critically, the user-explicit-stop bypass you built (985–1000, 1016–1018) only guards **Phase 3C**. GEO-CHECK (1324–1347) does **not** consult `_explicit_stop_names`. So the very stops the user typed by name are still vulnerable — just to a different filter now. Net effect for this request: the retest will likely show 2 of the parks plus 2 GPT-invented stops, or some mix — still not "ask for 4, get these 4."

(Side note: GEO-CHECK's `>= 2` floor at 1342 means it can never produce a 1-stop tour. So whatever cut the original run to **1** stop was either Phase 3C or upstream generation — never GEO-CHECK. That's another reason to confirm 1a.)

### 1c. Recommended fix: user-named stops are authoritative — exempt them from every dispersion filter.

When `_explicit_stop_names` is non-empty, those POIs are the user's intent, not GPT's guess. They should be:

1. **Seeded** into `poi_list` directly (geocode the named stops; don't depend on GPT to "suggest" them back), and
2. **Exempt from BOTH Phase 3C and GEO-CHECK** removal, and
3. ideally exempt from Part C replacement churn.

Minimal version: in the GEO-CHECK block, filter `outliers` to drop any `p` whose `_normalize_name(p['name'])` is in `_explicit_stop_names` before line 1342 — same guard you already apply in 3C at 1016. That stops GEO-CHECK from deleting named stops. It won't make them walkable, but it honors the request, which is what the user is asking for.

This also resolves the tension in the user's own question ("should it make 4 if I asked for 4?"): **yes — when stops are named explicitly, deliver exactly those and skip the walkability filters.** The 1.75 km limit exists to catch GPT hallucinating dispersed stops; it should never overrule an explicit user list. Auto-detecting "these are far apart, call it a regional/driving tour and relax the limit" is a reasonable v2, but the v1 correct behavior is simply: named stops are sacrosanct everywhere, not just in 3C.

---

## Issue 3 — "No Chinese at all": Chinese WAS produced; the title is a services responsibility you've now (re)addressed

Two separate things were conflated here. Splitting them:

**(a) Chinese was translated.** Log line 28: `translations":{…"zh":{"id":360,"status":"translated"}}` — ZH (id 360) translated, 200, and the app saved it (lines 32–33). So `translation-service` did produce the Chinese tour. It's not missing on the server.

**(b) The reason the user can't tell it apart is the title — and that is a services job, correctly.** Both RU and ZH were saved with the **identical English title** (lines 30, 32, "walking tour with stops at…"), so the ZH variant is indistinguishable in the Listen list. Title translation belongs to services, and the code does own it: `translate_tour_with_audio` translates `tour_name` (211), stores it in the new row (262–266), writes it to the `index.html` `<title>` (1216) and to `manifest.json` `name`/`short_name` (1341). **And the `/translate-with-audio` route now returns the translated `name` in the response** (1610–1630).

**Why the log still shows English:** that `name`-in-response code is part of *this* revision (`translation-service-00008`). The 10:47 test response (line 28) carried only `{id, status}` — no `name` — so it ran against the **pre-fix** service. At test time this was, correctly understood, a **services gap** (the response gave the app no translated title). It is now addressed server-side. I retract my earlier "not a services bug" framing — title generation/translation is services' responsibility and the test-time failure was on the services side.

**Remaining boundary check for retest:** the app's saved list-title is currently derived from the **ZIP manifest** (`tour_generator_screen.dart` `_saveTourToMyToursTranslated`: `manifest['tour_name']`/`['name']`, English `original_request` as fallback), **not** from the new API `name` field. Your manifest write (1341) is guarded by `if os.path.exists(manifest_path)` (1336). So:

- If translated ZIPs contain a `manifest.json` → it now carries the translated name, the app reads it, titles render correctly with no mobile change. ✅
- If ZIPs ship **without** a `manifest.json` → the app falls back to the English string and a small Mobile-AQ change is needed to read the response `name`. ⚠️

Please confirm on retest whether the tour ZIPs include `manifest.json`. If they don't, the translated `name` you now return is the right channel and Mobile-AQ should consume it. Either way, the authoritative translated title comes from services — that part is yours and is now in place.

---

## Minor: TOUR_STATUS write missed

Log lines 34–35: `TOUR_STATUS … rows_affected: 0 — tour_id may not match any row`. The completion status write keyed on `tour_19ea7b2f9d6` matched no DB row (the canonical id is 358). Not blocking this retest, but worth a look — status updates silently no-op'd.

---

## Bottom line

- **Coordinates fix:** verified, ship it.
- **4-stop fix:** confirm from the tour-generator log where the 3 stops were lost (1a). Regardless, add the `_explicit_stop_names` guard to the GEO-CHECK block (1b/1c) before retesting — otherwise the named parks get removed by GEO-CHECK instead of 3C and the retest fails the same way.
- **No-Chinese / English titles:** Chinese was produced; the identical-title problem is a **services** responsibility (title translation), and was a services gap at test time — now addressed by the `name`-in-response + manifest/HTML-title writes in this revision. On retest, confirm whether ZIPs contain `manifest.json`; if not, Mobile-AQ must consume the new response `name`.
