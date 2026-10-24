# SUBMISSION — LOCAL-759: Organiser-audio tour download fails on big episodes; the community page lists every imported episode

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-759-organiser-audio-download`
**Base:** `subscribed` @ `d816a251` (contains LOCAL-758; verified `git merge-base --is-ancestor d816a251 HEAD` exits 0)
**code_sha:** `12fe7609` (branch tip at submission; this doc-sha update sits one commit above it)

---

## Why (Michael, 2026-10-24 ~17:58 EDT, iPhone, organiser USER-41659366, community 10)

> "Created The Salem Witch Trial tour and published. When I got back to my community for some reason it listed all 42 episodes on this page. There is a Salem Witch Trial tour with Download link, but when I pressed on it it tells me 'The download failed.'"

The server side was fine: tour **750** (`source_kind=organiser_audio`, 3 stops) packaged `remote_audio.json` with three podtrac → podbean 302-redirecting URLs of **72.5 / 80.9 / 131.8 MB** (285 MB total). The phone failed because it tried to hold each whole episode in memory under a 120-s TOTAL timeout, with no retry, and surfaced a generic "The download failed."

---

## What changed

### A — The phone can now fetch real podcast episodes

**New `audio_tour_app/lib/services/remote_audio_fetcher.dart`** — the streaming core:
- **A1 Streams** each episode to `audio_N.mp3.part` via `http.Client().send` → a file sink, renames to `audio_N.mp3` on completion. The episode is never held in memory. Follows the **podtrac/podbean 302 → 302 → 200 redirect chain** by hand.
- **A1 Idle timeout** = no data for **30 s** (a `Timer` reset on every chunk), NOT a cap on total transfer time, so a large-but-steady 131 MB download completes.
- **A2 Retries** a failing stop **twice** with exponential backoff.
- **A3 Progress** callback (`RemoteAudioProgress` received/total bytes) + **cancellation** (`RemoteAudioCancelToken`) that removes the partial `.part` file.
- **A5 Named error**: on final failure throws `RemoteAudioError` with the exact message
  `Audio for stop 2 'The Accusations Begin' could not be downloaded.`
  (`remoteAudioStopFailureMessage` is the single source of truth.)
- **A4** `totalSizeBytes(urls)` sums each URL's HEAD `Content-Length` (following redirects) for the pre-download size prompt.

**`tour_download_service.dart`**
- `_fetchRemoteAudioDevice` now delegates to `RemoteAudioFetcher` (injectable `deviceFetcherFactory`), reading each stop's NAME from `audio_N.txt` so the failure message names the stop.
- **A5** `TourDownloadResult` carries `errorMessage`; `downloadAndSave` + `reDownloadAndReplace` set it via `_namedErrorMessage(e)`. New `cancelled` status. Pure helpers `failureMessage`, `mobileDataSizePrompt`.
- **A6** `_fetchRemoteAudioWeb` refuses any stop over **50 MB** (`webMaxBytesPerStop`) with `webSizeLimitMessage` — a HEAD pre-check plus a post-download size guard (prefs/base64 cannot hold a 130 MB episode).
- Progress/cancel are threaded `downloadAndSave → saveTourToMyTours → _fetchRemoteAudioIfPresent → _fetchRemoteAudioDevice`.

**`community_page_screen.dart`**
- **A5** both `failed` cases now show `TourDownloadService.failureMessage(result.errorMessage)` — the named message reaches the SnackBar instead of the generic "Download failed."
- **A3** `_downloadCommunityTour` shows a live "Downloading audio — stop X of Y · a / b MB" SnackBar with a **Cancel** action, and handles the new `cancelled` status.

### B — The community page no longer lists raw imported episodes

- Removed the per-episode `ListTile` rendering (and the "Episodes (N)" header / "Join to listen to the episodes." prompt) from `community_page_screen.dart`. The page shows **tours only**.
- The episodes stay in the model (`Community.episodes`) — the owner-only organiser-audio builder reads them for its checklist, and the Refresh path keeps them. They are simply no longer drawn on the page.

### C — Organiser sees episode size + a running total (builder), fed by the server

**Server** (`communities_rss.py`, `communities_api.py`, migration):
- `parse_feed` now emits `size` (enclosure byte length), `duration` (`<itunes:duration>`), and `date` (`<pubDate>`) per episode, for both RSS and Atom (any may be `None`).
- Migration **050** adds nullable `size_bytes` / `duration` / `episode_date` to `community_episodes` (additive, idempotent — `ADD COLUMN IF NOT EXISTS`, no DROP/DELETE/retype).
- `_upsert_feed_episodes` persists them; `_episodes_for` (and so `GET /communities/<id>/episodes` + the page payload) returns them.

**App** (`communities_models.dart`, `organiser_audio_tour_screen.dart`):
- `CommunityEpisode.sizeBytes` already feeds `metaLine` ("date · duration · size"); the server now supplies the size so the line is no longer empty.
- New pure helpers `formatBytes` and `tickedEpisodesTotalLabel` → the builder checklist shows a running total of the **ticked** episodes ("3 episodes · 285 MB", key `checklist_total`) so the organiser knows what members will download.

---

## Tests (red-first on d816a251, green now)

### Flutter (`audio_tour_app/test/`)
- `remote_audio_fetcher_local759_test.dart` (9): streams a chunked body to a file without holding it; idle timeout fires only on no-data; stalled→retry→success; redirect chain 302→302→200; after retries throws the NAMED message and cleans up the `.part`; progress received/total; `totalSizeBytes` HEAD sum through redirects; cancel removes the partial file.
- `tour_download_named_error_local759_test.dart` (9): `TourDownloadResult.errorMessage`; `failureMessage` prefers the named message; `remoteAudioStopFailureMessage`; web 50 MB limit (`exceedsWebLimit`, `webSizeLimitMessage`); A3 `downloadingAudioLabel` ("stop 2 of 3 · 45 / 81 MB"); A4 `mobileDataSizePrompt`.
- `community_page_no_episodes_local759_test.dart` (2): a community carrying 42 episodes renders NO episode rows / header while the Tours section still shows.
- `builder_checklist_size_local759_test.dart` (6): `formatBytes`, `tickedEpisodesTotalLabel`, `CommunityEpisode.metaLine`/`fromJson` carry the server size/duration/date.

**26 new Flutter tests green.**

### Python (`tests/`)
- `test_local759_feed_metadata.py` (3): `parse_feed` emits size/duration/date; missing meta is `None` not an error; DB round-trip through `_upsert_feed_episodes` + `_episodes_for`.

---

## Verification

- `flutter analyze` on every changed `lib/` file: clean except two PRE-EXISTING `info` RadioListTile deprecations in `community_page_screen.dart` (unrelated to this change).
- **Full `flutter test`: 1060 passed, 7 failed.** The 7 are the known baseline — 6 in `local109_swipe_e2e_test.dart` and 1 in `storied_compat_screens_404_test.dart`, all `SocketException: Connection refused` / 404 because they need a running local server. No NEW failures.
- Python: `test_local759_feed_metadata.py` + `test_local690_communities.py` + `test_local754b_organiser_audio.py` + `test_local755_organiser_audio_updates.py` → **52 passed**.
- Migration 050 applied to the local `audiotours_test` (port 5433) and `audiotours` dev DBs (additive nullable columns only; no data writes, no `DELETE FROM audio_tours`).

## Files
```
audio_tour_app/lib/services/remote_audio_fetcher.dart          (new)
audio_tour_app/lib/services/tour_download_service.dart
audio_tour_app/lib/services/communities_models.dart
audio_tour_app/lib/screens/community_page_screen.dart
audio_tour_app/lib/screens/organiser_audio_tour_screen.dart
user-tracking/communities_rss.py
user-tracking/communities_api.py
migration/sql/050_community_episode_metadata.sql               (new)
tests/test_local759_feed_metadata.py                           (new)
audio_tour_app/test/remote_audio_fetcher_local759_test.dart    (new)
audio_tour_app/test/tour_download_named_error_local759_test.dart (new)
audio_tour_app/test/community_page_no_episodes_local759_test.dart (new)
audio_tour_app/test/builder_checklist_size_local759_test.dart  (new)
```

## Live test
Not run in this session (emulator/simulator only, own `-p local759` containers, READ-ONLY on the shared map server). The streaming path, redirect-following, idle timeout, retry, named-error, size-limit and progress/cancel are all proven by the fetcher unit tests with a fake `http.Client` (chunked bodies, 302 chains, stalls). Budget $0.
