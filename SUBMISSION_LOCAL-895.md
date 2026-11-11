# SUBMISSION LOCAL-895 — Listen shows real stop count

Base 2129990b, branch LOCAL-895-listen-stop-count. No generation, $0 OpenAI. Nothing installed on any phone.

## Change
New `audio_tour_app/lib/utils/saved_tour_stops.dart` (one helper): `countAudioMp3s`, `serverStopCount`, `resolveRealStopCount` (mp3s on disk > server `actual_stops`/`stops_count` > user list length), `stopsEntry` (omits `stops` if unknown), `repairSavedTourStops`.

Writers fixed (no more stop-count box / literal '10'):
- `tour_generator_screen.dart`: `_saveTourInfo`, background-tour download (was `?? '10'`), translation path (no `=10` fallback); `stop_count_$jobId` / pending `stopCount` now only written for a user-named list (its length).
- `background_service.dart`, `background_tour_monitor.dart`, `pending_tour_resume_handler.dart`, `map_service.dart`.
- `edit_tour_screen.countStopsOnDisk` now delegates to the shared helper.
- tour_download_service / home_screen / tour_translation_helper already used backend or zip counts; unchanged.

One-time repair: `main.dart` recounts MP3s for every saved tour whose folder exists and fixes `stops` (idempotent, unawaited, silent on failure) — fixes Michael's 10→8 entry.

## Tests
`test/saved_tour_stops_local895_test.dart`: list 8 + box 10 → 8; mp3s beat server/list; server fallback; unknown → no `stops`; repair 10→8 (others, missing folder, malformed untouched; second pass no-op). Passed, plus listen_stop_count_test and no_raw_saved_tours_write_test.
`flutter analyze`: 1388 issues before and after (no new).

## Not verified
No emulator run; the repair and save paths are covered by unit tests only.
