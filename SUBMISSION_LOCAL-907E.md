# SUBMISSION — LOCAL-907E: topics reach the phone (offline, $0)

Branch `LOCAL-907E-fillings-delivery`, from `subscribed` c00dd708 (`merge-base --is-ancestor` = 0). No paid call; DB and Kokoro mocked.

## What changed
1. **fillings.json in the ZIP** — `fillings_payload.add_fillings_to_zip` appends `{"fillings":[...]}` (zip append mode: existing entries byte-identical; no fillings = no file). The orchestrator now computes `fillings_for_tour` right after `tour_content.txt` is added and BEFORE `store_audio_tour` (so the ZIP stored in the DB, which map-delivery serves, contains it); the same list is still put on the job for `/status`. Logs `[LOCAL-907E] fillings.json: <legs> legs, <items> items`.
   - Translation: a non-English tour is generated through this same orchestrator path (`language` is passed), so it is covered. Not covered: `tour_worker_service.py` (cloud_tasks mode, separate ZIP build, never calls fillings) and `tour_editing_*` rebuilds; left alone to keep this change to one path.
2. **Item fields** — `language`, `sources` (title+url, http/https only), `source_url` (first), `sentence_ends`. `topic_picker.segment_ref` carries them through. Items with no audio are filtered **before** picking, so a leg is filled with segments that have audio rather than left short.
3. **Audio** — `topic_library_build.py --render-audio` renders **per sentence** (Kokoro), concatenates, and sets `sentence_ends` = running sum of each sentence MP3's duration (mutagen, ffprobe fallback) — exact, no estimation. Row is UPDATEd by id (`PgSegmentStore.set_audio_path(id, path, ends)`); no DELETE. Migration `migrations/local907e_topic_sentence_ends.sql` (`ADD COLUMN IF NOT EXISTS sentence_ends JSONB`). **Run it before deploying this code**: `topic_segments` SELECTs now include the column (until then `fillings_for_tour` returns [] by design; tours still deliver).
   - Route `GET /topic-audio/<path>` is in **map-delivery**: it is the service the app already downloads tours from (relative `/topic-audio/...` resolves against the same base), and it is stateless/read-only. Serves only `.mp3` regular files under `TOPIC_AUDIO_DIR`; rejects `..`, absolute, backslash, NUL, symlinks escaping the dir; `audio/mpeg`, Range (206) works. 404 otherwise. docker-compose mounts `./topic_audio` read-only into map-delivery with `TOPIC_AUDIO_DIR`.
4. **Phone** — new `TopicAudioDownloader`: after the tour's own audio is saved (both `saveTourToMyTours` and `reDownloadAndReplace`), fire-and-forget download of each item into `topic_<id>.mp3` (via `.part`), writes `topic_audio_status.json`. Failure never fails the tour; failed items are hidden by `applyLocal`; the player uses the local `file://` copy when present. `WebViewTopicAudio` default base moved orchestrator → map-delivery. Skipped on web.
5. **Bottom bar** — `SwipeFeedbackWidget(topicTitle:)`; label "Topic · <title>" while `OtwMode.topic`, "This stop: <name>" otherwise; the player rebuilds it from the controller.

## Tests
- `tests/test_local907e_fillings_delivery.py` (23): ZIP with/without fillings (sha256 of existing entries equal), orchestrator ordering, full fields, no-audio skipped, route serves/Range/404s (`../`, symlink, non-mp3, absolute), render-audio with mocked Kokoro (UPDATE, same id, sentence_ends), Pg SQL is UPDATE only, migration additive.
- Updated `test_local907_topic_library.py` for the new contract (text-only item now omitted; new column in the mocked row; duration_fn injected).
- Required Python set (907*, 906*, 896–899, 90*, lead905): **1191 passed**.
- Flutter: 908 files + `test/topic_audio_local907e_test.dart` (7 new): **62 passed**. `flutter analyze` on changed files: no errors (41 pre-existing infos/warnings, same count as before).

## Not verified
- Real Kokoro/real MP3 durations, the real Postgres column, a live download on a device/simulator (no simulator was booted; widget/unit tests only). `file://` playback inside the tour WebView is assumed from how the page is loaded; LEAD's live check should confirm it.
- No sentence splitter parity with the app is needed (app only reads the end times), but the highlight depends on sentence count matching the displayed text — the player's text source is not part of this task.
