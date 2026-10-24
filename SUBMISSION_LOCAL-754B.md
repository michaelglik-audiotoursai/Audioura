# SUBMISSION — LOCAL-754B: Organiser-audio tours

**Branch:** `LOCAL-754B-organiser-audio-tours`
**Base (subscribed):** `027584b0d1eb518a7166b3fcdd9f4adacf62c9d1`
`git merge-base --is-ancestor 027584b0 HEAD` → exits 0 (correct base).

## What this delivers

The organiser builds a REAL tour from their OWN hosted audio (an RSS feed and/or
MP3 links). Audioura never stores the audio (D658 addendum 2): the package
carries a `remote_audio.json` mapping stop N → the organiser's URL and **no
MP3**. The phone downloads each URL on download and saves it as `audio_N.mp3`
next to `index.html`, so on the Listening page the tour is **indistinguishable
from a generated Audioura tour** — same page (the shared
`tour_html_map.build_tour_page_html` renderer), same map buttons, same voice
control (next / previous / repeat / stop / play). Translation of organiser audio
is **not offered** (D708): the ⋮ Translate item is hidden and the server refuses
a translate request (403 `translation_not_offered`). Editing is organiser-only
and bumps the version so the LOCAL-746/748/750 refresh reaches members.

## Changes

### Server
- **`migration/sql/049_organiser_audio_tours.sql`** (additive, idempotent):
  `audio_tours.source_kind`, `rights_accepted_by`, `rights_accepted_at` + a
  partial index. No DROP/DELETE/retype — every existing row reads NULL and
  behaves exactly as before.
- **`user-tracking/organiser_audio_tours.py`** (NEW, self-contained pure
  module): `SOURCE_KIND='organiser_audio'`, `MAX_AUDIO_BYTES` (200 MB/stop),
  `keep_audio_enclosures` (audio-only + skipped count), `validate_stops` /
  `validate_audio_urls` (name the first failing stop), `build_package` (ZIP:
  `index.html` via the shared renderer, `audio_N.txt`, `tour_content.txt`,
  `manifest.json`, `service-worker.js`, **`remote_audio.json` — no mp3**),
  `translation_not_offered`.
- **`user-tracking/tour_html_map.py`** (NEW, a copy of the repo-root shared
  renderer — the user-api build context is `./user-tracking`, exactly as
  `communities_rss.py` lives there; `Dockerfile.modernized` already ships the
  root copy to the generator). Guarantees the organiser-audio page is
  byte-for-byte the generated page's stop markup.
- **`user-tracking/communities_api.py`**: `POST
  /communities/<id>/build-audio-tour` (OWNER ONLY — a member/non-owner gets
  403). Validates rights, stops and every audio URL (HEAD → ranged GET via the
  injectable `_audio_url_check` hook), builds the package, stores the ZIP in
  `audio_tours.audio_tour` tagged `community_id` + visibility + `source_kind` +
  the rights acceptance. New → 201; edit (own community's organiser-audio tour)
  archives the old content to `audio_tour_versions` (version bump) → 200.
- **`translation-service/translation_service.py`**: `_is_organiser_audio_tour`
  + a gate at the top of `/translate-with-audio` — a `source_kind='organiser_audio'`
  tour returns 403 `translation_not_offered` before any translation runs. The
  gate is self-contained (no cross-import; the shared contract is the
  `'organiser_audio'` string), so no Dockerfile needs a new COPY line.

### App (`audio_tour_app`)
- **`services/tour_download_service.dart`**: after ZIP extraction, if
  `remote_audio.json` is present, download each URL from the organiser's host
  and write `audio_N.mp3` beside `index.html` (device) / into prefs (web). One
  failing stop → the whole save fails naming the stop (no half-saved tour).
  `reDownloadAndReplace` does the same for edits; `source_kind` is stamped onto
  the saved record; `_countTourStops` falls back to the `remote_audio.json`
  entry count.
- **`screens/my_tours_screen.dart`**: `isOrganiserAudioTour(tour)` + the ⋮
  Translate item is hidden for an organiser-audio tour.
- **`services/communities_service.dart`** + **`communities_models.dart`**:
  `buildAudioTour()` → `BuildAudioTourResult`.
- **`screens/organiser_audio_tour_screen.dart`** (NEW): the builder — feed
  import + MP3 links, ordered stops (name / location / text, reorder, remove),
  tour type, visibility, the required rights checkbox, Publish (names the
  failing stop).
- **`screens/community_page_screen.dart`**: owner-only "Make a tour from your
  own audio" entry → the builder.

## Red tests (fail on 027584b0)
- `tests/test_local754b_organiser_audio.py` — pure module (keep-audio, validate,
  build_package has `remote_audio.json`/no mp3 and `index.html` == the shared
  renderer, translation gate) **and** the Flask endpoint through a scripted
  cursor (member 403 / owner 201 with source_kind + remote_audio / 422 naming
  the failing stop / edit bumps version). On base the module,
  `user-tracking/tour_html_map.py` and the endpoint are ABSENT → red.
- `tests/test_local754b_translation_refusal.py` — organiser-audio → 403
  `translation_not_offered` (and translate never runs); generated → through. On
  base the gate has 0 occurrences → red.
- `audio_tour_app/test/local754b_translate_hidden_test.dart` —
  `isOrganiserAudioTour` (absent on base).

Verified absent on base:
```
git cat-file -e 027584b0:user-tracking/organiser_audio_tours.py → ABSENT
git show 027584b0:user-tracking/communities_api.py | grep -c build-audio-tour → 0
git show 027584b0:translation-service/translation_service.py | grep -c translation_not_offered → 0
```

## Test results (green after implementation)
- **New server tests:** 17/17 pass
  (`test_local754b_organiser_audio.py` + `test_local754b_translation_refusal.py`).
- **Touched Python suites (no regression):** `test_local701_community_tours.py`,
  `test_local578_translation_metering.py`, `test_local745_member_update.py` →
  34 passed total with the new suites.
- **Flutter:** `local754b_translate_hidden_test.dart` 4/4 pass. Full
  `flutter test`: **962 passed, 7 failed** — the 7 are the KNOWN baseline (6
  `local109_swipe_e2e_test.dart` connection-refused + 1
  `storied_compat_screens_404_test.dart`), **no new failures**.
- `flutter analyze` on every touched Dart file: **0 errors** (pre-existing
  info/warning lints only).

## Live test (no OpenAI, own served feed, real test DB) — `live_local754b.py`
Ran against `audiotours_test` (port 5433) after applying additive migrations
017/035/048/049. A local HTTP server serves my OWN RSS feed (3 `audio/mpeg` MP3
enclosures + 1 non-audio PDF). The REAL endpoint and the REAL HEAD/ranged-GET
URL checker run against the live DB. Result (`submission_artifacts/local754b/live_run.log`):

```
[feed] parsed 4 items → kept 3 audio, skipped 1 non-audio ✓
[owner-only] member build refused 403 ✓
[build] owner published source_kind=organiser_audio stops=3 ✓
[row] source_kind=organiser_audio community tags + rights_accepted_by/at ✓
[package] remote_audio.json present, NO mp3, index.html == generated renderer ✓
[phone] fetched remote audio → audio_1/2/3.mp3 beside index.html (plays offline) ✓
[translate] organiser_audio → not offered; generated → offered ✓
[edit] re-publish bumped version → 2 ✓
[budget] $0.00 — organiser-audio uses NO OpenAI/AI calls ✓
```

**Row counts** (`audio_tours`, `community_episodes`, `communities`):
before `{0, 0, 1}` → after `{1, 0, 2}` → after cleanup `{0, 0, 1}` (restored
exactly). All rows created were `is_test=true`; cleanup removed ONLY this run's
is_test rows (D141); no purchase-bearing rows touched (D690). **Budget: $0.00.**

Artifacts in `submission_artifacts/local754b/`: `index.html` (the rendered page
— 🚶 map buttons, "`<name>: Audio N`" headings, `openMap()`, voice control
`nextStop`/`previousStop`/`repeatStop`, identical to a generated page),
`remote_audio.json`, `live_run.log`.

## Notes
- No protected files edited (DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
  `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`).
- No Dockerfile edits needed: user-tracking uses `COPY . .`; translation-service
  copies one-by-one but no new module was added there (self-contained gate).
