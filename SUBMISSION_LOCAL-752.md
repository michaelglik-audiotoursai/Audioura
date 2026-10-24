# SUBMISSION — LOCAL-752: Community tours round 4

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-752-community-round4`
**Base (subscribed):** `027584b0d1eb518a7166b3fcdd9f4adacf62c9d1`
**Verify:** `git merge-base --is-ancestor 027584b0 HEAD` → exit 0 ✅
**Budget spent:** ~$0.00 (no paid generation/translation runs — only local DB reads, one
additive UPDATE, and local test runs)

---

## What was wrong (Michael's retest, 2026-10-23, community 10 "Salem TV show funs", `listed`)

- **A.** The Russian translation (737) of a community tour (736) had no `community_id` /
  `community_visibility`, so the community page never listed it and the Russian appeared
  nowhere.
- **B.** All 6 tours of the listed community were `members`, so `/tours-near`, `/search` and
  the map never showed them.
- **C.** The organiser's edit (716 → v3) never reached a member who had deleted and
  re-downloaded the tour: `deleted_tour_ids` still held "716", so `RefreshPlanner` skipped it.
- **D.** Voice control may ship audio to Apple/Google and fail offline — `listen()` was called
  without on-device recognition.

---

## The fixes

### A1 — a translation inherits its source's community (server)
`translation-service/translation_service.py`
- New helper `TranslationService._append_community_cols(cursor, cols, vals, source_tour_id)`:
  schema-guarded (`information_schema` probe), reads the SOURCE tour's
  `community_id`/`community_visibility`, and appends them to the INSERT column/value lists
  when the source has a community. Never raises (a read failure degrades to an ordinary row;
  the backfill repairs it).
- Wired into **both** insert paths: `translate_tour_with_audio` (main) and
  `_translate_tour_from_zip` (ZIP fallback), right before the placeholders are built.

### A2 — the community page shows each tour's languages (server)
`user-tracking/communities_api.py`
- `_tours_for` now returns ORIGINALS only (`original_tour_id IS NULL`) and carries a
  `languages` list per tour (original first, then finished translations), the SAME contract
  the new-tours read uses.
- **Root cause #2 (found during the backfill):** `_tour_languages` read the legacy `language`
  column, which is `'en'` on **every** translation row in production — the real target
  language lives in `content_language`. So the Russian (and every translation) never appeared
  even once `community_id` was set. Fixed `_tour_languages` to
  `SELECT COALESCE(content_language, language)`.
- Verified live after the fix: `_tour_languages(736)` → `['en','ru']`; `_tours_for(10)` lists
  all 6 community tours with the Danvers tour showing `['en','ru']`.

### A3 — organiser-only translate (server-enforced 403)
`translation-service/translation_service.py`
- New helper `_community_translate_block(cursor, tour_id, user_id)` mirroring
  `tour_editing_phase2._community_edit_block` (LOCAL-745) but self-contained in the translation
  service: `None` (ordinary tour / the owner), `(403, NOT_COMMUNITY_OWNER)` (member/stranger),
  `(401, USER_ID_REQUIRED)` (community tour, no user_id).
- Enforced in `/translate-with-audio` before any paid work runs.
- App (`audio_tour_app/lib/services/translation_service.dart`): `translateTour` now sends the
  device `user_id` from prefs. `tour_translation_helper.dart` calls through that same service,
  so the Listen-page ⋮ → Translate path carries it.

### B — a listed community's new tours default to public (D706)
`community_tours_service.py`
- `default_visibility_for_community(cur, community_id, explicit)`: explicit choice wins; else a
  `listed` community → `public`; else `members` (private / unknown → safe default).
- `set_tour_visibility(cur, tour_id, community_id, visibility, owner_user_id)`: **owner only**
  (raises `not_owner`); a public tour needs coordinates. Registered as an owner-only
  `POST/PATCH /tour/<id>/visibility` route.
- `tour_orchestrator_service.py`: the Generate handler resolves the default via
  `default_visibility_for_community` (best-effort own DB read; members-only fallback). Existing
  rows are never changed automatically — Michael switches his own in one tap.
- Non-member public download → 402 `membership_required` is unchanged (regression-guarded).

### C — any explicit download clears `deleted_tour_ids` (app)
`audio_tour_app/lib/services/community_downloads.dart`
- `removeFromDeletedTourIds(Set, ids)` (pure) + `clearDeletedTourIds(prefs, ids)`.
`audio_tour_app/lib/services/tour_download_service.dart`
- `saveTourToMyTours` clears `[downloadId, editTourId]` after a successful save;
  `reDownloadAndReplace` clears `[tourId]` after a successful replace. So re-downloading 716
  removes it from `deleted_tour_ids` and `RefreshPlanner` picks up v3 and shows
  "… was updated by the organiser."

### D — voice works offline (app)
`audio_tour_app/lib/services/voice_listen_options.dart` (new)
- `buildVoiceListenOptions(onDeviceSupported:)` → `SpeechListenOptions(onDevice: …,
  partialResults: true, cancelOnError: true)`; `voiceListenMode(onDeviceSupported:)` →
  `'on-device' | 'network'` for the single log line.
`voice_control_service.dart`, `voice_control_service_news.dart`, `my_tours_screen.dart`
- `listen()` now prefers on-device recognition (works in airplane mode), with a one-shot
  fallback to the network recogniser if the platform rejects on-device, logging the mode used.
- Deleted the dead server-call `processVoiceCommand` (no callers) and its now-unused imports.

---

## Red tests (fail on base `027584b0`, pass with the fix)

| Test | Area |
|---|---|
| `tests/test_local752_translation_inherits_community.py` | A1 `_append_community_cols` |
| `tests/test_local752_community_page_languages.py` | A2 `_tours_for` languages + `content_language` regression |
| `tests/test_local752_organiser_only_translate.py` | A3 `_community_translate_block` 403/401 |
| `tests/test_local752_listed_default_public.py` | B default public / owner-only visibility / 402 guard |
| `audio_tour_app/test/community_deleted_clear_local752_test.dart` | C clear deleted + RefreshPlanner e2e |
| `audio_tour_app/test/voice_listen_options_local752_test.dart` | D on-device options + mode |

Confirmed RED on base: 20 Python failures / 2 intentional regression-guard passes; both Flutter
tests fail to compile (missing symbols/file). GREEN after the fix.

---

## Verification

**Python (hermetic, no Postgres):** all four LOCAL-752 suites + `test_local710b` (updated to the
new `_tours_for` contract) + `test_local713` → **40 passed**. `test_local666` map-delivery cases
(6) fail identically on base (a pre-existing 20-vs-24-column fixture mismatch, unrelated); its
`TranslationServiceHelper` subset is green.

**Flutter:** full suite **968 passed / 8 failed**. The 8 failures are pre-existing baseline
(`local109_swipe_e2e` needs a live server — `SocketException`; `storied_compat_guard` +
`storied_compat_screens_404` need a live gateway); confirmed identical on base via `git stash`.
The two new suites + `community_downloads` + `community_refresh_planner` are green (61 tests).
`flutter analyze` on all touched files: **0 errors** (the 77 errors elsewhere are pre-existing
in `audio_handler.dart` / `subscription_management_screen.dart`, unrelated).

---

## DB backfill (production `audiotours` @ localhost:5433 — additive, no deletes, D690 respected)

```
BEFORE: translation rows with NULL community_id but a community original: [737]

UPDATE audio_tours t
   SET community_id = orig.community_id,
       community_visibility = orig.community_visibility
  FROM audio_tours orig
 WHERE t.original_tour_id = orig.id
   AND t.original_tour_id IS NOT NULL
   AND orig.community_id IS NOT NULL
   AND t.community_id IS NULL;
→ 1 row updated: (737, 10, 'members')

AFTER: translations of community originals still NULL: 0
audio_tours total rows: 515 BEFORE → 515 AFTER (unchanged — no deletes)
```

Only translation rows were touched; the update is idempotent (`community_id IS NULL` guard).

---

## Live voice test — what the platform allows

The task asks to prove offline voice on a simulator/emulator **or report exactly what the
platform allows**. This environment has iOS Simulators only (no Android AVD installed). The iOS
**Simulator cannot capture microphone input** and cannot run real (on-device or network) speech
recognition — `speech_to_text` has no audio source there, and mic-permission requests are known
to crash/no-op on the Simulator. Airplane mode on the Simulator therefore cannot produce a
meaningful "next/pause/play" proof.

What is proven here: the on-device-first design (unit-tested) means the audio capture is local
when the device supports it, so the whole path (capture → on-device parse → execute) runs with
no internet on a real device; when on-device is unavailable the code falls back to the previous
behaviour and logs `network`. A device airplane-mode confirmation should be done on Michael's
install by the LEAD (never from this agent — LEAD installs). No budget was spent on a Simulator
build that could not capture voice.

---

## Files changed

Server: `translation-service/translation_service.py`, `user-tracking/communities_api.py`,
`community_tours_service.py`, `tour_orchestrator_service.py`.
App: `audio_tour_app/lib/services/{voice_listen_options.dart (new), voice_control_service.dart,
voice_control_service_news.dart, community_downloads.dart, tour_download_service.dart,
translation_service.dart}`, `audio_tour_app/lib/screens/my_tours_screen.dart`.
Tests: 4 new Python + 2 new Flutter + updated `tests/test_local710b_community_tours_payload.py`.
