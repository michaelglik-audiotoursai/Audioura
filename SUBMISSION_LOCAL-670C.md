# SUBMISSION — LOCAL-670C

**Offline-first listening record, ratings and thumbs: verified on the phone, synced when a connection returns**

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-670C-offline-sync` (from `subscribed` @ `70a0bf83`, which contains LOCAL-670B)
**Base verified:** `git merge-base --is-ancestor 70a0bf83 HEAD` → exit 0.

---

## Why

Michael (2026-10-10): *"Many places where people are listening to the tours may not have internet
and therefore cannot connect to the server. So Audioura must do some storage and verification locally,
and send info to a server only that was valid and when it had connection."*

Tours play fully offline from the downloaded ZIP. LOCAL-670B recorded a stop as listened and POSTed it,
and gated the per-tour rating **on the server** — which fails with no connection. 670C moves verification
and the gate **onto the phone**, and ships every fact to the server through a durable **outbox** when a
connection returns.

---

## What shipped

### 1. Local verification of "listened" — real played time, not a scrub

`audio_tour_app/lib/services/playback_accumulator.dart` (new, pure/unit-testable).

The 670B rule marked a stop listened the instant `currentTime/duration ≥ 0.8` — so a listener could
**scrub** to 85% and fake it. 670C counts only **genuinely played** media time:

- accumulate media-time **only while playing**,
- only at **normal or near-normal speed** (≤ 1.5×, so speed-listening counts but a 3× skim does not),
- a **seek/scrub** — a `currentTime` jump far larger than the wall-clock time that actually elapsed —
  adds **nothing**; only the plausible real slice is credited.

A stop is **listened** when the accumulated played time reaches **80%** of the audio duration, or the
audio reaches the **end** after ≥ 80% was genuinely played.

The player (`tour_player_screen.dart`) now feeds the accumulator **raw** `play/pause/seek/ratechange/
timeupdate/ended` events (with `currentTime`, `duration`, `playbackRate`) from the WebView via a new
`onPlaybackEvent` bridge handler, one `PlaybackAccumulator` per stop. When a stop is verified it is stored
**locally with a timestamp**, per `(tour, stop)` — `tour_listen_service.dart`, key
`listened_stops_v2_<tourId>` = `{ "<stopIndex>": "<ISO-8601 UTC>" }`. The legacy 670B index-only list
(`listened_stops_<tourId>`) is **migrated forward** on first read so an app update loses nothing.

### 2. Local rating gate; offline rating saved and shown at once

The gate reads the **local** record (`TourListenService.hasListenedEnough` / `requiredThreshold`), so
"Rate this tour" appears once the device has **≥ 2 listened stops** (or **all** stops when the tour has
fewer than 2), and the polite Audible-style message uses the **local** count — all with no connection.

`tour_rating_service.dart` is now **offline-first**: `submitRating` **always** saves the listener's own
rating locally (`my_tour_rating_<tourId>`), enqueues it in the outbox, and returns a `RatingSubmission`
the dialog shows immediately as **"Your rating: 8"**, or **"Your rating: 8 (pending sync)"** when offline.
An online direct POST still refreshes the aggregate badge straight away.

### 3. One outbox for listened events, ratings, reviews and per-stop thumbs

`audio_tour_app/lib/services/outbox_service.dart` (new). Every fact that must reach the server is written
here **first** (durable — same shared storage as downloaded-tour state, so it survives restart **and** an
app update), then flushed opportunistically. Each item carries a **client UUID** and a **created_at**.

- **Per-stop thumbs moved in.** `stop_feedback_service.dart` was rewritten to enqueue `thumb` items in the
  single outbox (public API — `recordSwipe/undoLastSwipe/queueLength/getPendingQueue/flush` — unchanged, so
  `SwipeFeedbackWidget` and callers are untouched). Today's `/user/<id>/stop-feedback` no longer fails
  offline.
- **Sync triggers** (`app_sync_coordinator.dart`, wired in `main.dart`): on **app start**, on **resume**
  (`WidgetsBindingObserver`), and on a **connectivity change** that gains a connection
  (`connectivity_plus` ^6.0.5). The coordinator is the only place that watches connectivity; the outbox
  stays a pure, plugin-free, unit-testable class.
- **Ordering:** `listened` items are sent **before** the `rating` that depends on them.
- **Exponential backoff** while items remain (5 s → 15 min cap).
- **Removal policy:** an item is removed only after the server **accepts** (2xx) or explicitly **rejects**
  it (a 4xx-style per-item verdict → dropped and logged locally). A 5xx / network error / no connection
  **keeps** every item.
- **Nothing is lost:** durable across restart & update; an item **older than 90 days** is dropped **with a
  log line**.

### 4. Server batch endpoint — `POST /sync`

`tour_rating_service.py` (+ route registered on the orchestrator at port 5002).

`POST /sync { user_id, items:[…] }` → `{ "results": [ { client_uuid, status } ] }`,
`status ∈ accepted | duplicate | invalid`.

- **Idempotent on the client UUID** via a self-healing `sync_items` ledger (this is what makes per-stop
  **thumbs** idempotent too, since they have no natural unique key).
- **Listen-then-rate in one batch:** the whole batch runs in one transaction, applying **listens before
  ratings**, so the 670B gate counts **this batch's own listens** — an offline listen-then-rate pair is
  accepted together.
- **Rejections** (per-item, inside a 2xx so the client drops exactly the bad item): a timestamp **> 10 min
  in the future** (clock-skew guard); a `listened` event for a stop the tour **does not have**
  (`stop_index ≥ stops_count`).
- **Translation → source:** a translation id maps to its original before every read/write (670B rule).
- **D650:** a `thumb` goes to `user_stop_feedback` as an **internal signal only** (personalization / stop
  quality) and is **never** mixed into the tour's 1–10 score.
- **Reviews** are persisted to a dedicated `tour_review_sync` table so nothing is lost before LOCAL-672.
  (Deliberately a distinct table — a pre-existing `tour_reviews` with a different schema already exists.)

Migration `migration/sql/021_sync_offline_outbox.sql` mirrors the service's self-healing DDL
(`sync_items`, `tour_review_sync`) — purely additive, idempotent, no DROP/DELETE, no change to any
existing table.

---

## Tests

**Dart (33 pass)** — `flutter test` on the three files:

- `playback_accumulator_test.dart` — straight play (≥80% listened; halfway not), **seek-to-end**
  (a scrub to the end is NOT listened; genuine ≥80%-then-end is), **scrub** (repeated jumps and a big
  in-tick jump credit nothing), **1.5×** counts / **3×** does not, pause-resume.
- `outbox_service_test.dart` — ordering (listens before the rating), retry keeps every item on no network,
  **90-day expiry** drop + log, durability across reload, and the local gate
  (`requiredThreshold`/`hasListenedEnough`/dedup/enqueue).
- `stop_feedback_test.dart` — rewritten to assert the outbox-backed thumb queue.

**Python (12 pass)** — `tests/test_local670c_sync.py`:

- idempotency on `client_uuid` (re-send → `duplicate`, one row), **offline listen+rate in one batch**
  accepted together, rate-without-enough-listens rejected, **future timestamp** rejected,
  **nonexistent stop** rejected, translation → source, **D650** thumb accepted but not in the tour score,
  review stored, route 400 guards.

**Regression:** 670B listened-gate (25) and 670 ratings suites remain green. Full `flutter test`: **310
pass**; the only failures are the 6 live-server e2e cases in `local109_swipe_e2e_test.dart`
(`Connection refused` — they need a backend at `:5102`; pre-existing, network-dependent, not this change).

**Build & analyze:**

- `flutter analyze` — **clean** (no errors/warnings) for every changed/added file and test. (The repo's
  pre-existing analyzer errors in `audio_handler.dart` / `subscription_management_screen.dart` reference
  packages absent from `pubspec` and are unrelated to this ticket; the iOS release build does not include
  them.)
- `flutter build ios --no-codesign` — **succeeded** (`Runner.app`, 37.5 MB), confirming `connectivity_plus`
  integrates and the whole app compiles for iOS.

**No paid calls. Own containers only; no `audioura-*` container replaced. No GCloud.**

---

## Files

New:
- `audio_tour_app/lib/services/playback_accumulator.dart`
- `audio_tour_app/lib/services/outbox_service.dart`
- `audio_tour_app/lib/services/app_sync_coordinator.dart`
- `audio_tour_app/test/playback_accumulator_test.dart`
- `audio_tour_app/test/outbox_service_test.dart`
- `tests/test_local670c_sync.py`
- `migration/sql/021_sync_offline_outbox.sql`

Changed:
- `audio_tour_app/lib/services/tour_listen_service.dart` — timestamped local record + outbox enqueue, legacy migration
- `audio_tour_app/lib/services/tour_rating_service.dart` — offline-first `submitRating` → `RatingSubmission`
- `audio_tour_app/lib/services/stop_feedback_service.dart` — thumbs delegate to the outbox
- `audio_tour_app/lib/widgets/rate_tour_dialog.dart` — pending-sync UI, prefill from local rating
- `audio_tour_app/lib/screens/tour_player_screen.dart` — raw playback-event bridge → accumulator
- `audio_tour_app/lib/screens/{home_screen,my_tours_screen}.dart` — adopt `RatingSubmission`
- `audio_tour_app/lib/main.dart` — start the sync coordinator
- `audio_tour_app/pubspec.yaml` / `pubspec.lock` — `connectivity_plus` ^6.0.5
- `audio_tour_app/test/stop_feedback_test.dart` — outbox-backed assertions
- `tour_rating_service.py` — `POST /sync` batch, idempotency ledger, in-batch gate, skew/stop validation, D650

## Design notes

- **SharedPreferences, not a new DB.** The outbox and listen record use the same durable store the app
  already relies on for downloaded-tour state, so "survives restart and app update" is free and no heavy
  dependency (sqflite) was added — keeping the iOS build risk low.
- **Connectivity is injected, not embedded.** The outbox has no plugin dependency; `AppSyncCoordinator`
  owns `connectivity_plus` + lifecycle, so the sync policy (ordering, backoff, expiry, idempotency) is
  fully unit-testable without a device.
- **Idempotency ledger over per-table keys.** `sync_items` gives one uniform idempotency guarantee across
  all four item types; listens and ratings keep their own natural UNIQUE/UPSERT keys as defence in depth.
