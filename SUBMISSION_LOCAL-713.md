# SUBMISSION — LOCAL-713: Community tours download foundation (D675 part 1)

**Branch:** `LOCAL-713-community-downloads` (from `subscribed` = e51247b4)
**Version:** 2.4.28+68 → **2.4.29+69** (patch +1, build +1)

Builds the foundation for "community members get new community tours on their
phone" (D675): a server **new-tours** endpoint, a saved **listening language**,
a **Download / On this phone ✓ / Join to download** status on the community
page, and the **sync-on-open** baseline. LOCAL-714 (background + the join
question + iOS notification) builds on this.

---

## 1. Server — `GET /communities/new-tours` (user-api-2)

`user-tracking/communities_api.py`.

```
GET /communities/new-tours?user_id=<device user>&since=<iso8601|empty>
→ 200 {
    tours: [ { community_id, community_name, tour_id,
               short_title (fallback tour_name), stop_count, created_at,
               languages: [<codes with a finished translation>, original first] }
             … newest first across all the caller's communities ],
    server_time: <iso8601 — store as the next `since`>
  }
```

- Across the caller's **ACTIVE** memberships only
  (`community_memberships.expires_at IS NULL OR > now()`) **plus** the
  communities they **own** (the organiser counts for their own communities).
- Each community's **non-draft ORIGINAL** tours
  (`audio_tours.community_id = X AND original_tour_id IS NULL AND draft = FALSE`),
  newest first; `since` filters to tours created **strictly after** it.
- `languages` is the original's language **first**, then every language with a
  **finished (non-draft) translation row** (`original_tour_id = tour_id`). v1
  lists only languages that already exist — it never requests a new translation
  (D675 §1).
- An **expired or absent** membership contributes **nothing** — never an error
  (D675 §4). `user_id` missing → 400; a blank/garbage `since` is treated as
  "from the beginning", never an error. **Read-only.**

Pure helpers (hermetically testable): `new_tours_for_user`,
`_active_community_ids_for_user`, `_tour_languages`, `_new_tours_for_community`,
`_parse_since`.

**Python test** `tests/test_local713_new_tours.py` (12 tests, hermetic — a
scripted fake cursor, no Postgres): active vs expired vs non-member, owned
community counts, `since` filtering (strictly-after, exact-time excludes),
languages list (original first; a **draft** translation excluded), short_title
fallback, newest-first across communities, and `_parse_since` (Z / offset /
blank / garbage).

---

## 2. Listening language (app)

`lib/services/community_downloads.dart` (dependency-free) + About UI.

- Saved setting `listening_language`, chosen in **About → "Listening language"**
  from the same list `widgets/language_selector` offers (`en, ru, es, fr, de,
  zh`).
- **Default** = the phone's language when Audioura offers it, else English
  (`defaultListeningLanguage`).
- Pure helper **`pickDownloadLanguage(available, preferred, original)`** →
  preferred if available, else original (v1 never requests a new translation).

## 3. Community page — a status per tour

`lib/screens/community_page_screen.dart`.

Every community tour row (from the page payload `tours`, visible to everyone who
can see the page) gets a status via the pure **`rowStatusFor`**:

- **"Download"** — a member/owner who does not have the tour. Runs the **SAME**
  download path a Home/Listen download uses — `TourDownloadService` (see §5),
  never a second path. A member's pass covers the tour, so there is no purchase
  prompt; if the server still refuses with `membership_required` (an expired
  pass), the page's join/buy flow opens, exactly as the existing community-tour
  flow does (D663/D665).
- **"On this phone ✓"** — the tour id is already in Listen (any language).
- **"Join to download"** — a non-member (D663).

## 4. Sync on open (the baseline)

`lib/services/community_tours_sync.dart` + `app_sync_coordinator.dart`.

On app **start / resume / connectivity-gain**, `CommunityToursSync.run()`:

1. calls `/communities/new-tours` with the stored `since`;
2. builds the inputs and runs the **pure** `SyncPlanner.plan(...)`:
   - only communities whose local switch `auto_download_<id>` is ON (default
     OFF — LOCAL-714 adds the join question);
   - skip tours already on the phone, and **never** a tour in the user's deleted
     set (`deleted_tour_ids`, D675 §6);
   - **nothing** on a metered connection unless `auto_download_cellular` (default
     false) is on; nothing offline;
   - language via `pickDownloadLanguage`;
3. downloads each planned tour via the **same** `TourDownloadService`;
4. stores `server_time` as the next `since` **only after** the downloads succeed
   (pure `shouldAdvanceSince`) — a partial failure leaves `since` so the next
   open retries.

## 5. One download path (never a second)

`lib/services/tour_download_service.dart` lifts the download + save
(`GET /download-tour/<id>` on map-delivery → resolve → extract → record in
`saved_tours`) out of `home_screen` into `TourDownloadService`. `home_screen`
now **delegates** its `_saveTourToMyTours` to it, so Home, the community-page
Download button, and the sync runner all share **one** implementation of the
on-phone record contract. Added to `test/storied_compat_allowlist.txt` (CORE —
same download/resolve calls, all try/catch + 200-gated + 402 handled).

---

## Tests

**Dart** `test/community_downloads_test.dart` (26 tests, pure):
`pickDownloadLanguage`; `defaultListeningLanguage`; `rowStatusFor`
(download / on phone / join / owner); `SyncPlanner.plan` (switch gating,
already-on-phone, deleted-never-redownloaded, **nothing on cellular when not
allowed**, cellular-when-allowed, offline, order preserved);
`shouldAdvanceSince` (advances only on success); `NewToursResult.fromJson`.

**Full `flutter test`:** `+628 -6`. The **6** failures are exactly the baseline
`test/local109_swipe_e2e_test.dart` live-server tests (SocketException — no
server on the test host); no new failures.

**Python:** 72 community tests pass (`test_local690/700/701/710b` + the 12 new
`test_local713_new_tours`).

---

## Live test — `live_local713_new_tours.py`

Own throwaway Flask harness mounting `communities_api` on a **spare port
(5099)**, read-only against the dev DB (`…@localhost:5433/audiotours`, the
host-exposed `development-postgres-2-1`). **Never** used `-p audioura`; **never**
renamed or stopped any `audioura-*` container.

Created ONE `is_test` ORIGINAL tour tagged to community 2 + a finished `es`
translation + an active test membership for `LOCAL713-TEST-DEVICE`, then deleted
them.

```
BEFORE:        audio_tours=493  community_memberships=0  is_test audio_tours=423
AFTER CREATE:  audio_tours=495  community_memberships=1  is_test audio_tours=425
               (created original id=705, es translation id=706 → community 2;
                active membership for LOCAL713-TEST-DEVICE)

GET /communities/new-tours?user_id=LOCAL713-TEST-DEVICE&since=
HTTP 200
{
  "server_time": "2026-10-19T03:49:21.918947",
  "tours": [
    { "community_id": 2, "community_name": "Demo Boston Walkers",
      "created_at": "2026-10-19T03:49:20.319707",
      "languages": ["en", "es"],
      "short_title": "LOCAL713 — Walking Tour",
      "stop_count": 4, "tour_id": 705 }
  ]
}
ASSERT OK: returned with languages [en, es], community_id=2, short_title carried.
SINCE=server_time → our tour present again? False   (since filtering works)

AFTER ENDPOINT (read-only): 495 / 1 / 425   (unchanged — endpoint writes nothing)
FINAL (after cleanup):      493 / 0 / 423   MATCHES BEFORE? True
```

No leftover rows; the spare port was freed.

---

## Files

**Server:** `user-tracking/communities_api.py`;
`tests/test_local713_new_tours.py`; `live_local713_new_tours.py`.

**App:** `lib/services/community_downloads.dart` (new),
`lib/services/community_tours_sync.dart` (new),
`lib/services/tour_download_service.dart` (new),
`lib/services/community_tour_service.dart`,
`lib/services/app_sync_coordinator.dart`,
`lib/screens/about_screen.dart`, `lib/screens/community_page_screen.dart`,
`lib/screens/home_screen.dart`, `pubspec.yaml`,
`test/community_downloads_test.dart` (new),
`test/storied_compat_allowlist.txt`.

Did **not** edit DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / .continuous_dev.
