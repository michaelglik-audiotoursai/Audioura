# SUBMISSION — GCS-5: Make tour editing work in the cloud (both tracks)

**Agent:** Services Kiro **Base:** main = `912cdd1` **Branch:** `kiro/gcs-5`
**ClickUp:** `wdvrdaycwj` **Runbook:** `wdvrdaxn9f`
**Deploy status:** NOTHING DEPLOYED. Deploy is Michael's call. Everything below is
staged (`--dry-run` pasted) and verified by effect against a locally running
editing container in cloud-equivalent mode (R2 + Postgres).

Base check: `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0. Branched from HEAD,
not origin.

---

## TL;DR — the five gaps, and what fixes each

| # | Gap (verified, not re-derived) | Fix |
|---|---|---|
| 1 | No editing backend in Cloud Run | Staged a **new** `tour-editing` Cloud Run service from the shared `audioura` image (`deploy_gcs5_tour_editing.sh`). |
| 2 | Gateway has no backend/route for editing | Added `tour-editing` backend + 4 routes to `api-gateway/gateway_routes.yaml`; script sets `TOUR_EDITING_URL` on **both** gateways. |
| 3 | Cloud lookup can't find R2-migrated tours | `_resolve_tour_from_db` now selects on `(audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)` and reads the ZIP from **R2** (`R2BlobStorage`) when BYTEA is NULL, falling back to BYTEA. |
| 4 | Saved edits discarded (ephemeral /tmp, UUID never resolves) | Edited ZIP is stored as a **new R2 object** `tours/edits/<src>/<uuid>.zip`, mapped durably in an additive `tour_edit_blobs` table; `/tour/<uuid>/download` serves it from R2 on **any** instance. |
| 5 | App sends no API key on editing calls | All four calls in `tour_editing_service.dart` now use `Endpoints.apiHeaders(Service.tourEditing)`; removed the cloud-mode gate that hard-blocked editing. |

Files changed (production): `tour_editing_phase2.py`, `api-gateway/gateway_routes.yaml`,
`audio_tour_app/lib/services/tour_editing_service.dart`
(+410/−70). New: `deploy_gcs5_tour_editing.sh`, `api-gateway/test_editing_routes.py`,
and a local verification harness under `tests/gcs5_*`.

---

## What I changed and why

### `tour_editing_phase2.py`
- **R2 helpers** (`_get_blob_storage`, `EDIT_BLOB_PREFIX`, `_edit_blob_key`) mirroring
  `map_delivery_service.py:_get_blob_storage` — lazy `R2BlobStorage` when
  `BLOB_STORAGE_TYPE=r2`, else `None`.
- **`STORAGE_MODE`** module constant from `TOUR_STORAGE_MODE`.
- **Durable edit mapping** (`tour_edit_blobs`): additive table created on demand,
  `new_tour_id → (source_tour_id, blob_uri)`. Chosen over "R2-key-naming alone"
  because the download request carries only the bare UUID; without a lookup we cannot
  reconstruct `tours/edits/<src>/<uuid>.zip` (the source id is unknown at download time).
- **Gap 3** in `_resolve_tour_from_db`: dual-read select + R2 read + edit-blob fast path.
- **Gap 4** in `_bulk_save_core` (extracted from `bulk_save_stops`): after building the
  new tour, in cloud mode upload the ZIP to `tours/edits/<src>/<uuid>.zip`, record the
  mapping, and clean up both the source and the built `/tmp` dirs. If R2 is not
  configured or the upload fails, the save returns an error (never a success whose
  download would 404).
- **`download_tour_with_flags`**: cloud-mode fast path serves the edited ZIP straight
  from R2 bytes; otherwise builds the ZIP **in-memory / under the resolved dir** instead
  of the `TOURS_DIR` cache (which is ephemeral and per-instance on Cloud Run). Volume
  mode is unchanged.
- **New routes** `POST /tour/<id>/update-stop` and `GET /tour/<id>/job-status/<job_id>`
  so the gateway routes reach real handlers. `update-stop` folds the single edit into the
  same preserve+persist path and returns `new_tour_id`/`download_url` with **no** `job_id`
  (app then refreshes immediately). `job-status` returns `completed` (editing is
  synchronous here).
- **Entrypoint** now honours `$PORT` (default 5022) and guards `os.makedirs(TOURS_DIR)`
  — required for Cloud Run.

### `api-gateway/gateway_routes.yaml`
- Added backend `tour-editing: ${TOUR_EDITING_URL:-https://tour-editing-...run.app}`.
- Added 4 **additive** routes (`update-multiple-stops`, `update-stop`,
  `job-status/<job_id>`, `download`), all `auth: api_key`, save routes `timeout: 300`.
- **Collision check:** the app calls unprefixed `/tour/<id>/...`. Existing map-delivery
  route is `/tour/<tour_id>/resolve` — a distinct trailing segment, so no Flask rule
  collision. `map_delivery_service.py` also *defines* `/tour/<id>/update-stop`, but it is
  **not exposed by either gateway** (only `/resolve` is) and is a non-persisting stub, so
  routing this path to `tour-editing` is additive and non-conflicting. No existing route
  changed.

### `audio_tour_app/lib/services/tour_editing_service.dart`
- All 4 HTTP calls now send `Endpoints.apiHeaders(Service.tourEditing[, requestBody:])`.
- Removed the `server_mode == 'cloud'` gate that threw "only available on local WiFi".
- Removed 2 now-unused imports and one always-true null check so `flutter analyze` is clean.
- Did **not** bump version or build a release.

### LEAD decisions — followed
- Never overwrite a production tour: no `UPDATE audio_tours SET audio_tour/tour_blob_uri`.
  Edits go to a new R2 key namespace + additive table. ✔
- Routes stay `auth: api_key`; fixed the app rather than making routes public. ✔
- All four paths routed; save timeout 300 s (see measurement below). ✔
- One service, both tracks; separate deploy from GCS-3. ✔

---

## Acceptance criteria — evidence

Local cloud-equivalent stand-in: Postgres (`gcs5-pg`, 127.0.0.1:5544) + MinIO as the R2
S3 API (`gcs5-minio`, 127.0.0.1:9010, bucket `v1-audiotours-r2-bucket`), editing service
run as a real subprocess with `TOUR_STORAGE_MODE=cloud BLOB_STORAGE_TYPE=r2`, Polly stub
returning MP3 bytes. Harness: `tests/gcs5_local_verify_setup.py`,
`tests/gcs5_run_service.bat`, `tests/gcs5_polly_stub.py`.

Seed (reproduces gap 3 exactly):
```
[SETUP] audio_tours row count BEFORE seed: 0
[SETUP] audio_tours row count AFTER seed: 1
[SETUP] seeded tour id=1 audio_tour_is_null=True tour_blob_uri=tours/1.zip
[SETUP] R2 object: s3://v1-audiotours-r2-bucket/tours/1.zip (708 bytes)
```

### (2) RED — current code fails on that tour
Against the **unmodified** `HEAD:tour_editing_phase2.py` (cloud mode):
```
$ curl -s -X POST http://127.0.0.1:5123/tour/1/update-multiple-stops \
       -H "Content-Type: application/json" --data-binary @tests/_save_body.json
{"error_code":"TOUR_NOT_FOUND","message":"Tour with ID '1' could not be found for bulk
 save operation","recoverable":false,"status":"error", ...}

$ curl -s -o NUL -w "%{http_code}" \
       http://127.0.0.1:5123/tour/00000000-0000-0000-0000-000000000000/download
HTTP_STATUS=404
```

### (1) GREEN — save then download from a FRESH instance
Save (new code, instance A on :5123):
```
$ curl -s -X POST http://127.0.0.1:5123/tour/1/update-multiple-stops \
       -H "Content-Type: application/json" --data-binary @tests/_save_body.json
{"status":"success",
 "new_tour_id":"adaccadc-4c59-4d5d-902d-94d07f0b0acd",
 "download_url":"/tour/adaccadc-4c59-4d5d-902d-94d07f0b0acd/download",
 "message":"Tour updated successfully with 1 text-to-speech audio file(s)", ...}
SAVE_ELAPSED_MS=937          # 2-stop tour, 1 edited + 1 preserved
```
Kill instance A; start a **fresh** instance B on :5124 (different process = different
Cloud Run instance); download:
```
$ curl -s -o edited.zip -w "%{http_code} %{size_download}" \
       http://127.0.0.1:5124/tour/adaccadc-4c59-4d5d-902d-94d07f0b0acd/download
HTTP_STATUS=200 SIZE=2058
```
ZIP contents (fresh instance served it from R2 via the durable mapping):
```
VALID_ZIP files: ['audio_1.mp3','audio_1.txt','audio_2.mp3','audio_2.txt','index.html']
audio_1.txt = 'EDITED via GCS-5 verification_ this is the new first-stop text.'
CONTAINS_EDIT = True
audio_2.txt = 'This is the second stop of the original tour, describing the...'  # preserved
```
(The `:` → `_` is the service's pre-existing `sanitize_user_input` path-safety
substitution, not a regression.)

`update-stop` and `job-status` also verified against the fresh instance:
```
$ curl -s -X POST http://127.0.0.1:5124/tour/1/update-stop --data-binary @tests/_updatestop_body.json
{"status":"success","new_tour_id":"81e68bb2-...","download_url":"/tour/81e68bb2-.../download", ...}   # no job_id
$ curl -s http://127.0.0.1:5124/tour/1/job-status/somejob123
{"job_id":"somejob123","status":"completed","tour_id":"1"}
```

**Save timeout justification:** measured ~0.9 s for a 2-stop save with the stub Polly.
Real Polly synth is roughly ~1–2 s/stop; a large tour (e.g. 30–50 stops) that regenerates
every stop can approach a few minutes. `timeout: 300` (5 min) on the save routes covers a
whole-tour synth with headroom. Cloud Run service `--timeout 600` is set even higher.

### (3) Gateway route test (in-process, no deploy)
`python api-gateway/test_editing_routes.py`:
```
[1] Manifest static checks:
  OK: 4 editing routes present, backend=tour-editing, auth=api_key, save timeouts >=300s,
      map-delivery resolve untouched
[2] Live app auth checks (Flask test client):
  OK: POST /tour/<tour_id>/update-multiple-stops  no-key=401 wrong-key=401 good-key!=401
  OK: POST /tour/<tour_id>/update-stop            no-key=401 wrong-key=401 good-key!=401
  OK: GET  /tour/<tour_id>/job-status/<job_id>    no-key=401 wrong-key=401 good-key!=401
  OK: GET  /tour/<tour_id>/download               no-key=401 wrong-key=401 good-key!=401
PASSED: all editing routes registered and fail-closed without X-API-Key
```
(Complements `test_route_lock.py`, which probes a *live* deployed gateway post-deploy.)

### (4) App
All four calls send `Endpoints.apiHeaders(Service.tourEditing)`.
`flutter analyze lib/services/tour_editing_service.dart` → **No issues found!**
No version bump, no release build.

### (5) Staged deploy — `deploy_gcs5_tour_editing.sh --dry-run`
Deploys nothing (default is dry-run; `--apply` required, Michael only). It:
builds/pushes the shared `audioura` image (next `vN`), CREATEs `tour-editing`
(`--command python --args tour_editing_phase2.py`, port 5022,
`--no-allow-unauthenticated`, Cloud SQL `audiotours-migration:us-central1:audioura-db`,
`TOUR_STORAGE_MODE=cloud`, `BLOB_STORAGE_TYPE=r2`, R2 + AWS + `POLLY_TTS_URL` env/secrets),
grants each gateway SA `roles/run.invoker`, sets `TOUR_EDITING_URL` on **both**
`api-gateway` and `api-gateway-storied`, and prints the exact post-deploy curls for
`https://api.audioura.com` and `https://storied-api.audioura.com` (401-without-key,
save→download with key, then `test_route_lock.py` against both). Full dry-run output is in
the ClickUp comment / reproducible via the command above.
> Before `--apply`: confirm the exact `R2_ENDPOINT` value and the secret **names**
> (`db-password`, r2/aws secrets) against a live service — the script flags this inline and
> uses `REPLACE_WITH_R2_ENDPOINT` as a deliberate placeholder so a wrong endpoint can't be
> applied silently.

### (6) No production tour row/blob/column modified
```
audio_tours rows = 1  (before) → 1 (after)
tour 1 row (unchanged) = (1, audio_tour IS NULL = True, tour_blob_uri = 'tours/1.zip')
tour_edit_blobs rows = 1
  edit map: ('adaccadc-...','1','tours/edits/1/adaccadc-...zip')
R2 objects: tours/1.zip 708B (original, untouched) + tours/edits/1/adaccadc-...zip 2058B (new)
```
No `UPDATE`/`DELETE` on `audio_tours`; only a new R2 key and a row in the additive table.

---

## storied port — exactly what to change

At the base, `storied` differs from `main` only in `tour_editing_phase2.py` (+147) and
`gateway_routes.yaml` (+17); the Dart file is **identical** on both.

- **`tour_editing_phase2.py`** — applies cleanly. The storied-only additions are entirely
  inside `promote_custom_tour` (LOCAL-306/312 edit-scoring: imports `tour_scoring_service`,
  `quality_guardrails`, `user_quality_index`). My edits are in `_resolve_tour_from_db`,
  `_bulk_save_core`, `create_complete_tour*`, `download_tour_with_flags`, the new routes,
  and the entrypoint — **zero overlap** with the scoring hunks. Cherry-pick / re-apply the
  same diff.
- **`gateway_routes.yaml`** — storied has extra `/user` + `/user/<secret_id>` routes
  (news-orchestrator, wdvrdaycef). My block is inserted between the `treats` block and
  `internal_only`, which exists identically on storied; the new paths don't collide with
  `/user`. Apply the same 4 routes + `tour-editing` backend.
- **Dart file** — identical on both branches; apply as-is.
- **Deploy** — `deploy_gcs5_tour_editing.sh` already wires **both** gateways
  (`api-gateway` and `api-gateway-storied`) and grants invoker for each. One service backs
  both tracks.

---

## Also report (not fixed)

### Stop-2 audio shows 0 length / won't play
**Best explanation: primarily a consequence of these gaps, with one separable nuance.**
Before this fix, every cloud save returned `TOUR_NOT_FOUND` and the download 404'd, so the
app never received a working updated tour — on-device stop 2 was left in a stale/partial
state. In my green run the preserve path copied the unedited stop's original audio intact
(the source ZIP is now correctly read from R2), so the pipeline itself does not zero-out
audio when the source audio exists.
The **separable nuance**: `create_complete_tour_with_preservation` matches an original
stop's audio by **exact `text_content` equality**. The save path runs incoming text through
`sanitize_user_input` (strips control chars, collapses whitespace, replaces `<>:"/\|?*`
with `_`, removes SQL-ish tokens). If the app sends a stop marked "unchanged/preserve" whose
text, after sanitisation, no longer byte-matches the stored original, the preserve-by-content
match fails and it regenerates via TTS instead of preserving. That is a latent correctness
bug independent of gaps 1–5 and would surface as *regenerated* (not zero-length) audio; it
should be tracked separately (match by stop index, or compare post-sanitisation text).
I could not reproduce a genuine 0-byte MP3 from the backend on the happy path; if it recurs
after deploy, capture the save request body + the resulting `audio_2.mp3` size to confirm
whether Polly returned an empty body (a Polly/text issue) vs a preservation miss.

### Remaining persistent-local-filesystem assumptions in `tour_editing_phase2.py`
These are fine in volume mode but are ephemeral/per-instance on Cloud Run:
- `TOURS_DIR = /app/tours` writes — the download ZIP **cache** (was line ~1586) is now
  bypassed in cloud mode (I serve from R2 / build in-memory), but volume mode still uses it.
- **Custom audio** (`save_custom_audio_from_base64`, `process_multi_part_audio`,
  `_apply_custom_audio_file`) writes to `/app/custom_audio/…` and records absolute
  `file_path` in `custom_audio_files`. On Cloud Run those files vanish with the instance and
  the stored path won't resolve on another instance — custom-audio upload/preservation is
  **not** cloud-safe yet. Out of scope for this ticket (the reported failure is text-edit
  Save All); flagging for a follow-up (custom audio should also go to R2).
- `resolve_numeric_to_uuid_directory` / volume-mode `resolve_tour_to_directory` scan
  `/app/tours` — only used in volume mode; harmless in cloud mode (cloud path returns early).

### Beta image drift check
`tools/beta_image_drift_check.py` is **not on `main`** (it lives on `gcs-4-services-fixes`,
not merged into `912cdd1`), so it could not be run here. It does not apply to this change:
GCS-5 adds a **new** service (`tour-editing`) and **additive** gateway routes; it does not
modify tour-generation code, the Beta control image, or any existing service's behaviour,
so it cannot drift the Beta control (`wdvrdaxxm9`). If desired, run it after cherry-picking
that tool onto the deploy branch.

---

## Could not verify
- Real Cloud Run deploy, real Cloudflare R2, real Cloud SQL, real Polly/Comprehend — not
  exercised (deploy is Michael's; no gcloud/deploy/secret access executed). Verified against
  local Postgres + MinIO (S3 API-identical) stand-ins.
- Exact secret **names** and the precise `R2_ENDPOINT` value on the live services — the
  deploy script flags these to confirm via `gcloud run services describe` before `--apply`.
- The on-device app flow end-to-end (needs a signed build + the deployed gateway); the Dart
  change is static-analysed clean but not run on a device.

## Safety notes
- Authoritative read-only audit confirmed **no** object was written to production
  Cloudflare R2 (`tours/1.zip` and `tours/edits/` both absent on real R2) and no production
  row was modified. All verification used the local MinIO bucket; the setup harness now
  hard-refuses any `r2.cloudflarestorage.com` endpoint to prevent accidental production
  writes.
- No `DELETE FROM audio_tours`; no writes to production `tours/<id>.zip`.
