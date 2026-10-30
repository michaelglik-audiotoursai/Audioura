# SUBMISSION — LOCAL-841

**A tour that finished while the app was in the background never reached the phone (Michael's coffee‑tour 503)**

Branch: `LOCAL-841-resume-pending-downloads`
Base: `subscribed` (contains `2478ad45`) — `git merge-base --is-ancestor 2478ad45 HEAD` ⇒ 0.

---

## The defect

Michael's own tour 503 ("coffee… Vườn Thiên Giới", Vietnam) was generated and
**stored on the cloud**, but the app never downloaded it — he switched away and
iOS suspended the app while it was polling. GCloud_Storied had to hand him the
MP3 and text.

Root cause, confirmed by reading the code:

- The foreground **Generate** path, `_generateTourInner → _pollAndAutoDownload`
  (`tour_generator_screen.dart`), gets a `job_id` back from
  `POST /generate-complete-tour` and then polls `GET /status/<job_id>` **in the
  screen** until the tour is ready.
- That poll loop lives and dies with the screen: when iOS suspends the app the
  loop stops (`mounted == false`) and **the `job_id` is never persisted**, so on
  return there is nothing to resume. The tour finishes on the server and is lost
  to the phone.
- The only persistence that existed was for the *separate* "Generate in
  Background" button (`pending_background_tours` → `BackgroundService` /
  `BackgroundTourMonitor`). The ordinary foreground Generate — the one every
  traveller uses — persisted nothing.

The server side is already durable: `GET /status/<job_id>` reads the in‑memory
job **or** the DB (LOCAL‑821 `orchestrator_jobs`), so a `job_id` is still
answerable after a suspend/kill and even an orchestrator restart, and
`GET /download/<job_id|final_tour_id>` returns the zip. **No new server route was
needed** (task 3 in the ticket).

## The fix

Persist every in‑flight request the moment the POST returns, and finish it on
the next app start / resume.

**New — `lib/services/pending_tour_requests_store.dart`**
- `PendingTourRequest` value object: `jobId`, `title`, `startedAt`,
  `clientRequestId`, `languages`, `stopCount` (JSON‑round‑trips, decodes old
  entries safely).
- `PendingTourRequestsStore` over a dedicated SharedPreferences key
  `pending_tour_requests` (kept separate from the legacy
  `pending_background_tours` so the existing background flow is untouched):
  `add` (idempotent on `jobId`), `load` (skips corrupt entries), `remove`,
  `saveAll`.

**New — `lib/services/pending_tour_resume_handler.dart`**
- `ResumeDecision.decide(...)` — a PURE policy: `completed → download`,
  `error|failed → removeFailed`, still processing / unknown and younger than 2 h
  → `keepWaiting`, 2 h or older → `removeStale`, transient/404‑young →
  `keepWaiting`.
- `PendingTourResumeHandler.instance.run()` — for each pending entry asks
  `GET /status/<job_id>`, and on `completed` downloads
  `GET /download/<final_tour_id|job_id>`, extracts to `tours/<id>`, saves via
  `SavedToursStore.save` (the one writer that nudges the Listen page), bumps
  `SavedToursRefresh`, and surfaces "Your tour is ready". It **never blocks the
  UI** (LOCAL‑794's rule): no spinner gate, runs off a lifecycle trigger, has an
  in‑flight guard, and never throws. Idempotent: a tour already saved is not
  re‑added. IO (`httpGet`, docs dir, clock, ready/fail callbacks) is injected so
  the whole thing is unit‑testable.

**New — `lib/services/tour_ready_message.dart`**
- `TourReadyMessage` + `routeTourReadyMessage`: foreground → in‑app SnackBar with
  a **"View"** action that jumps to Listen (reuses `PendingListenOpen`);
  background → the existing `NotificationService` system notification. That
  service is Android‑only, i.e. a **no‑op on iOS with no new permissions** — so
  the "optional, cheap, skip if it needs new permissions" notification (ticket
  task 4) is satisfied without asking for anything.

**Wiring**
- `tour_generator_screen.dart` `_generateTourInner`: persist the
  `PendingTourRequest` the moment `job_id` returns; remove it on the foreground
  path's own `completed` and terminal `error`. Best‑effort — a storage hiccup
  never blocks generation.
- `app_sync_coordinator.dart` `_syncAll`: `unawaited(PendingTourResumeHandler
  .instance.run())` — runs on app **start**, on **AppLifecycleState.resumed**,
  and on a connectivity regain, alongside the existing syncs.
- `main.dart`: set `PendingTourResumeHandler.instance.readyRouter` to
  `routeTourReadyMessage(...)` before `AppSyncCoordinator.start()`.

## Tests

**Unit — `test/pending_tour_resume_local841_test.dart` (14 tests, all pass):**
- store: add/load round‑trip, idempotent add, corrupt‑entry skip, targeted remove;
- `ResumeDecision.decide`: completed / error / failed / processing‑young /
  processing‑old / 404‑young / 404‑old / network‑young;
- `run`: completed → downloads (by `final_tour_id`), saves, clears, surfaces
  ready; failed → removes + reports reason; stale (>2 h) → removes quietly;
  processing‑young → kept; empty list → no‑op.

`flutter analyze` on every changed file: clean (the only lints reported are
pre‑existing in `main.dart`). The `storied_compat_guard_test` failure on
`services/failure_reporter.dart` is **pre‑existing** — it fails identically with
all of my changes stashed — and is not touched here; my new raw‑call file is
covered by a new allow‑list entry in `test/storied_compat_allowlist.txt`.

## Live — iOS simulator against the Mac stack

iPhone 17 simulator (iOS 26), app pointed at the local stack with
`--dart-define=DEBUG_SERVER_IP=127.0.0.1` (orchestrator :5002). The shared
`audioura-*` containers were **not** restarted or modified. The test user
`sim-live807` was granted generation on the **local dev DB** only for the run and
reverted afterwards; the live DB was never touched.

`integration_test/local841_resume_live_headless_test.dart` **passes on the
simulator against the live stack**: a real 1‑stop tour is generated on the live
stack while the app is backgrounded (`AppLifecycleState.paused`); on resume the
**real** `PendingTourResumeHandler` downloads it from the live `/download/872`
and it appears on the **real** `MyToursScreen` (Listen) — in well under 30 s:

```
LIVE: a backgrounded generation is resumed and shows on Listen < 30 s
RESUME: downloaded + saved "A short coffee walk near Union Square San Francisco
        - Restaurant Tour" (id 872, job 5a44535d-...)
RESUME: pass done — downloaded=1 failed=0 stale=0 kept=0
LOCAL841TEST downloaded=1 elapsed=0s
LISTEN: Loading 1 tours from storage
LISTEN: Loaded 1 valid tours (0 skipped)
LOCAL841TEST PASS: tour on Listen after resume
All tests passed!
```

Reproduced across fresh jobs (`6c321774`, `5a44535d`). The **real app**
(`flutter run`) also auto‑resumed on launch — see
`submission_artifacts/local841/real_app_resume.log`.

Artifacts in `submission_artifacts/local841/`:
`01_app_launched.png`, `02_after_resume_home.png` (real app on the local stack),
`LIVE_TEST_RESULT.txt`, `real_app_resume.log`, `live_screenshot_hold_test.log`.

**Honest limitation:** a screenshot of the *populated Listen row* could not be
captured — a freshly provisioned simulator shows an OS location‑permission prompt
over the foreground app/test‑runner, and this sandbox lacks the
accessibility/screen‑recording permissions (and tap tooling) to dismiss it
programmatically. The populated‑Listen state is instead proven by the passing
live test above (`LISTEN: Loaded 1 valid tours` + the empty‑state assertion going
`findsNothing` after resume). An in‑Dart poll loop stalls on this
Flutter 3.41 + iOS 26 integration binding, and `convertFlutterSurfaceToImage`
(the `flutter drive` screenshot path) hangs on the same combo, so the live test
is shell‑driven (generation + wait) with a single‑shot resume in the test — the
`flutter drive` + screenshot variant is kept at
`integration_test/local841_resume_live_test.dart` for environments where surface
conversion works.

## Files

New (lib): `pending_tour_requests_store.dart`, `pending_tour_resume_handler.dart`,
`tour_ready_message.dart`.
Edited (lib): `main.dart`, `screens/tour_generator_screen.dart`,
`services/app_sync_coordinator.dart`.
Tests: `test/pending_tour_resume_local841_test.dart`,
`test/storied_compat_allowlist.txt` (+1 line), and the live integration tests +
driver under `integration_test/` and `test_driver/`.
