# SUBMISSION — LOCAL-781: /resolve from R2 blob storage (cloud), surface save errors, keep ZIP for retry

**Branch:** `LOCAL-781-resolve-from-blob` · **Base:** `subscribed` @ `c982ebe0`
(verified `git merge-base --is-ancestor c982ebe0 HEAD` → 0)
**Agent:** Mac Mini Kiro

## The bug

On the cloud, EVERY Home/Search download of an **existing** Subscribed tour failed.
map-delivery served the ZIP (200), then the app's `saveTourToMyTours` called
`GET /tour/<id>/resolve` on **tour-id-resolution-subscribed**, which returned
**404**. Cause: `tour_id_resolution_service.py` checked the ZIP's existence on
local disk (`Path("/app/tours")/zip_filename`). On Cloud Run `/app/tours` is
empty — the ZIPs live in Cloudflare R2 (`BLOB_STORAGE_TYPE=r2`, `blobstorage.py`,
the layer map-delivery reads). The disk check failed → legacy name-scan of the
empty dir → 404. Freshly generated tours skip `/resolve`, which is why new tours
saved. The app then showed the user **nothing**.

## What changed

### 1. Backend — `tour_id_resolution_service.py` (resolve without the ZIP on disk)
- Added `_get_blob_storage()` mirroring `map_delivery_service._get_blob_storage`:
  returns `R2BlobStorage()` only when `BLOB_STORAGE_TYPE=r2`, else `None` (disk).
- `_resolve_from_column` is now backend-aware:
  - **Blob mode (cloud):** reads `tour_name, zip_filename, tour_blob_uri,
    stops_count` from the DB row. Existence = `blob.exists(tour_blob_uri)` (the
    key map-delivery stored; falls back to the conventional `tours/<id>.zip`).
    `stops_count` and `editable` come from the **DB** (`stops_count > 0`), so **no
    object is downloaded** just to answer `/resolve` — only a cheap HEAD.
  - **Disk mode (Mac, no BLOB env):** unchanged — the ZIP must exist at
    `TOURS_DIR/zip_filename`.
- `find_edit_tour_id` **skips the filesystem fallback in blob mode** (scanning an
  empty `/app/tours` is meaningless) → a missing object is a clean 404, not a
  misleading "LEGACY FALLBACK … run the backfill" warning.
- `resolve_tour_id` uses the DB-derived `editable`/`stops_count` for a blob-backed
  result; the disk path (`check_tour_editability`, `count_mp3_files_from_zip`) is
  untouched.
- **LOCAL-50 kept:** the edit id is still derived deterministically from the
  stored `zip_filename` column, never guessed by name. Blob mode changes only
  WHERE existence is checked (R2 vs disk).

`zip_filename` (bare filename carrying the UUID, LOCAL-50) and `tour_blob_uri`
(the R2 object key, e.g. `tours/445.zip`) are distinct columns — I use each for
its own purpose: `zip_filename` for the edit id, `tour_blob_uri` for the R2
existence check.

### 2. App — surface the failure + keep the ZIP for retry
Root cause of "silently failed": `home_screen._downloadTour` (the MAIN download
path) had a catch that collapsed **every** non-network error to the generic
`"Error downloading tour"`, so the rich resolve-failure message never reached the
screen. (`_downloadSingleTour` already surfaced the full `$e`; the batch path
already names each failed tour.) Also `saveTourToMyTours` built its failure
message with `baseTourName`, which is only filled on a *successful* resolve — so
a failed resolve always said "Downloaded Tour" instead of the real name.

- `tour_download_service.dart`:
  - New pure, tested `resolveFailureMessage(tourName, tourId, status, serverMsg)`
    that **names the tour** (from the tapped Home/search row's `name`/`title`) and
    tells the user the download is **kept so a retry won't re-download**. Used in
    `saveTourToMyTours`' non-200 block.
  - New in-memory **ZIP retry cache** (`cacheZipForRetry` / `peekCachedZip` /
    `hasCachedZip` / `clearCachedZip`), keyed by server tour id.
- `home_screen.dart` `_downloadTour`:
  - Before the HTTP GET, reuses `peekCachedZip` (via `http.Response.bytes`) if a
    previous attempt kept the bytes — **no re-download**.
  - On save failure, caches the bytes; on success, clears them.
  - The catch now surfaces the real exception message (stripping Dart's
    `Exception: ` prefix) with an 8 s SnackBar, instead of the generic text.

### 3. Env docs — `SUBSCRIBED_GCLOUD_ENV.md` §9 (+ §12)
`tour-id-resolution-subscribed` now reads `BLOB_STORAGE_TYPE=r2` +
`R2_BUCKET`/`R2_ENDPOINT`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY` — the SAME
R2 secrets map-delivery has. Documented with a "why this changed" callout and the
LOCAL-50 note; unset = Mac/local disk behaviour. Added the service to the R2
secrets "Used by" row in §12. The redeploy is mechanical: add the four R2
vars/secrets exactly as map-delivery-subscribed has them.

## Stable (D720) — does Stable need this? **No.**

Config-verified from the gateway manifests:

| Track | `GET /tour/<id>/resolve` routes to | Backend code |
|---|---|---|
| **Subscribed** | `tour-id-resolution` backend (`gateway_routes.subscribed.yaml` ~line 614) | `tour_id_resolution_service.py` — the service with the disk bug, now fixed |
| **Stable** (Beta/Storied) | `map-delivery` backend (`gateway_routes.yaml` lines 43–45) | `map_delivery/app.py` |

The deployed map-delivery image is `map_delivery/app.py` (its `Dockerfile` CMD is
`["python","app.py"]`, and it is the only map-delivery Dockerfile). That file has
**no `/tour/<id>/resolve` route at all** (19 `@app.route` decorators, none is
resolve). The root `map_delivery_service.py` does have a resolve, but it is
**DB-only** (reads `id, tour_name, tour_blob_uri`, never touches disk) — and it is
not the deployed image anyway.

**Conclusion:** the `tour_id_resolution_service.py` disk bug **cannot occur on
Stable**, because Stable never routes `/resolve` to that service. Stable's
`/resolve` is served by map-delivery (DB-only / route-absent), not by the disk
path I fixed. I could NOT run a Stable app build/emulator here, so I did not
observe Stable's app runtime directly; the routing evidence above is what I
verified. Stable does **not** need this specific fix.

## Tests (red → green)

**Python** (`tests/test_local781_resolve_from_blob.py`, 4 tests, red first then green):
1. Blob mode, empty `TOURS_DIR`, object present → **200** + right edit id
   (`a956ce11`); existence checked in the blob store.
2. Blob mode, object missing → clean **404** (no name-scan).
3. Mac mode (no BLOB env), ZIP on disk → unchanged **200**.
5. Blob mode carries `stops_count`/`editable` from the DB.

Existing suites still green (base vs branch): `test_local50_deterministic_resolution.py`
6/6, `test_local759_organiser_resolution.py` 3/3, `test_local325_lazy_resolution.py` 5/5.

**Dart** (`audio_tour_app/test/resolve_from_blob_named_error_local781_test.dart`,
7 tests): `resolveFailureMessage` names the tour / falls back to id / treats a
blank name as none; the ZIP retry cache keeps bytes across a failed save, frees
them on success, and ignores empty/null. Existing
`tour_download_named_error_local759_test.dart` 8/8 still green → **15/15**.
`flutter analyze` on the two changed app files: **no errors** (only pre-existing
info/warning lints).

## Live test (own run, $0, no containers, no real R2)

`local781_tooling/live_resolve_demo.py` runs the REAL `tour_id_resolution_service`
Flask app with `BLOB_STORAGE_TYPE=r2`, an EMPTY `TOURS_DIR`, and a fake blob
store — the exact Cloud Run shape, exercising the same code a MinIO-backed
container would, without spending anything or touching real R2 credentials:

- **CASE 1** `/tour/445/resolve` → **HTTP 200**, `edit_tour_id=a956ce11`,
  `stops_count=7`, `resolution_method=column_blob`, from an EMPTY disk.
- **CASE 2** missing object → clean **404**.
- **CASE 3** Mac shape (no BLOB env, ZIP on disk) → unchanged **200**.

(No containers were started; no `-p` project was used; the Android emulator was
not needed — the app changes are covered by widget/service tests.)

## Files changed
- `tour_id_resolution_service.py`
- `tests/test_local781_resolve_from_blob.py` (new)
- `audio_tour_app/lib/services/tour_download_service.dart`
- `audio_tour_app/lib/screens/home_screen.dart`
- `audio_tour_app/test/resolve_from_blob_named_error_local781_test.dart` (new)
- `SUBSCRIBED_GCLOUD_ENV.md`
- `local781_tooling/live_resolve_demo.py` (new, tooling)

## Deploy note
Redeploy `tour-id-resolution-subscribed` from this branch **and** set
`BLOB_STORAGE_TYPE=r2` + the four `R2_*` vars/secrets (per §9). Without them the
new image still falls back to the (empty) local disk and the bug persists.
