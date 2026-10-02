# SUBMISSION — GCS-5R: tour editing in the cloud, fix the three blockers on `storied`

**Agent:** Services Kiro **Base:** storied = `f51b8f5` **Branch:** `kiro/gcs-5r`
**ClickUp:** `wdvrdaycwj` **Runbook:** `wdvrdaxn9f`
**Bounce of:** GCS-5 (`kiro/gcs-5` @ `e0e55d2`, built on `main`).
**Deploy status:** NOTHING DEPLOYED. Everything staged (`--dry-run` pasted) and
**verified by effect** against a locally running editing container in
cloud-equivalent mode (Postgres + MinIO-as-R2 + a Polly stub). Deploy is Michael's call.

Base check: `git merge-base --is-ancestor f51b8f5 HEAD` → exit 0. Branched from
HEAD, not origin.

GCS-5's design is kept: R2 read, R2-persisted edits + additive `tour_edit_blobs`,
four `auth: api_key` routes, app API key. The three LEAD-verified blockers and the
smaller defects are fixed below. **Committed after each blocker; branch pushed.**

---

## Files changed (production)
- `tour_editing_phase2.py` — port of GCS-5's R2 read/persist onto storied's file,
  **plus** B1 (single handler per rule) and B3 (source `content_language`).
- `api-gateway/gateway_routes.yaml` — `tour-editing` backend + 4 `auth: api_key` routes.
- `audio_tour_app/lib/services/tour_editing_service.dart` — GCS-5's change verbatim
  (`e0e55d2`; API key on all four calls, cloud-mode gate removed). storied's copy
  was byte-identical to the diff's "before", so it applied cleanly.
- `audio_tour_app/pubspec.yaml` — `2.3.2+22` → `2.3.2+23` (nothing else).

## New files
- `deploy_gcs5_tour_editing.sh` — rewritten (B2 + smaller defects).
- `api-gateway/route_diff.py` — proves the gateway route delta vs the v35 image.
- `api-gateway/test_editing_routes.py` — in-process gateway route/auth test (from GCS-5).
- `tests/gcs5r_b1_import_guard.py` — B1 red→green import guard.
- `tests/gcs5r_verify_ru.py`, `tests/gcs5r_polly_stub.py` — B3 + E2E harness (Russian tour).

---

## B1 — the port crashed the service at import  ✅ fixed

storied's `tour_editing_phase2.py` already carried LOCAL-153 shims that `main` never
had: `def update_single_stop` for `/tour/<id>/update-stop` and `def get_job_status`
for `/tour/<id>/job-status/<job_id>`. GCS-5's naive port ADDS a second
`def update_single_stop` and a `def job_status` on those same rules → Flask raises at
import and the container never starts.

**Fix:** exactly one handler per rule. I **replaced** storied's LOCAL-153 update-stop
shim with GCS-5's persisting handler (it folds the single edit into `_bulk_save_core`,
the shared bulk path) rather than adding a duplicate; kept storied's single
`get_job_status` for the job-status rule. `app.url_map` now has each editing rule
exactly once. `tests/test_local153_tour_editing_shims_guard.py` still passes unchanged
(it asserts both rules are registered — they are).

**Red → green** (`python tests/gcs5r_b1_import_guard.py`):
```
[RED] naive port import error:
      AssertionError: View function mapping is overwriting an existing endpoint function: update_single_stop
  PASS: naive port fails to import (endpoint overwrite)
  PASS: current file imports cleanly
  PASS: rule registered exactly once: /tour/<tour_id>/bulk-save
  PASS: rule registered exactly once: /tour/<tour_id>/download
  PASS: rule registered exactly once: /tour/<tour_id>/edit-info
  PASS: rule registered exactly once: /tour/<tour_id>/job-status/<job_id>
  PASS: rule registered exactly once: /tour/<tour_id>/update-multiple-stops
  PASS: rule registered exactly once: /tour/<tour_id>/update-stop
RESULT: PASS
```
LOCAL-153 guard: `2 passed in 0.57s`.

---

## B3 — Russian tour, saves treated as English  ✅ fixed (server-side only)

The app sends no `content_language` (confirmed: no match anywhere in
`audio_tour_app/lib`), and the old `_bulk_save_core` defaulted to `'en'`. Michael's
tour "Excursion over Jewish Cemetery" is Russian, so the old default rejects the edit
(`LANGUAGE_MISMATCH`) or synthesizes English TTS over Russian text.

**Fix (no further app change):** when the request omits `content_language`,
`_bulk_save_core` reads `audio_tours.content_language` for the source tour — numeric id
directly, or for an edited UUID via `tour_edit_blobs.source_tour_id`. An explicit request
value still wins. Which source was used is logged (`[LANG] ...`).

**Red → green with a Russian tour** (seed `content_language='ru'`, `audio_tour` NULL,
`tour_blob_uri=tours/1.zip`; Polly stub records the voice asked for):
```
[SETUP] seeded tour id=1 audio_tour_is_null=True content_language='ru' tour_blob_uri=tours/1.zip

[B3 RED]   status=200 voices=['Joanna']    # explicit content_language='en' (== old default) -> English voice
[B3 GREEN] status=200 voices=['Tatyana']   # NO content_language (what the app sends) -> server reads 'ru' -> Russian voice
```
Server log on GREEN: `[LANG] no content_language in request; using source tour 1 content_language=ru`.

---

## B2 — the deploy never shipped the routes  ✅ fixed

`api-gateway/Dockerfile` does `COPY main.py gateway_routes.yaml /app/` — **routes are
baked into the image.** Both gateways run `api-gateway:v35` (confirmed via
`gcloud run services describe … --format='value(...image)'`), built from `main`, whose
baked manifest has **no** editing routes. GCS-5's script only set `TOUR_EDITING_URL` on
those v35 revisions → still 404.

**Fix:** the script now **builds and pushes a new gateway image and deploys the gateway
onto it.** To guarantee the new image is *exactly v35 + the 4 routes*, I pulled the
running v35 image, extracted its baked `gateway_routes.yaml`, and diffed it against the
repo manifest.

**v35 finding:** v35 **already contains** the `/user` + `/user/<secret_id>` routes, so
storied's manifest equals v35's manifest — there is **no** accidental `/user` drift.

**Route diff** (`python api-gateway/route_diff.py <v35-image-yaml> api-gateway/gateway_routes.yaml`):
```
OLD: gw_v35.yaml            (25 route-methods, 6 backends)
NEW: api-gateway/gateway_routes.yaml  (29 route-methods, 7 backends)
Added backends:   tour-editing
Removed backends: (none)
Added routes:
  + GET   /tour/<tour_id>/download
  + GET   /tour/<tour_id>/job-status/<job_id>
  + POST  /tour/<tour_id>/update-multiple-stops
  + POST  /tour/<tour_id>/update-stop
Removed routes:   (none)
PASS: only difference is the 4 tour-editing routes + tour-editing backend.
```
The script runs this same diff at apply time and aborts if it is not exactly that delta.
New gateway tag = highest existing + 1 = **v36**.

In-process gateway auth test (`python api-gateway/test_editing_routes.py`): all four
routes registered, backend `tour-editing`, `auth: api_key`, save timeouts ≥300s,
map-delivery `/resolve` untouched, and every route `no-key=401 wrong-key=401 good-key!=401`.

---

## Smaller defects — all fixed

- **Preview first (Michael 2026-09-15):** the script targets **`api-gateway-storied`
  (Preview) by default**; `api-gateway` (Stable) only with `--stable`. Verified:
  default → `Target gateway(s): api-gateway-storied`; `--stable` →
  `api-gateway-storied api-gateway`.
- **gcloud flags:** one `--set-env-vars` (comma-joined) and one `--set-secrets`
  (gcloud keeps only the LAST occurrence of a repeated flag, silently dropping earlier
  vars). `REPLACE_WITH_R2_ENDPOINT` replaced with the live value
  `https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com`.
- **Own image:** `tour-editing` builds as `services/tour-editing:<tag>` (its own name),
  **not** the shared `audioura:vN` sequence (the shared-tag hazard for the Beta control).
  `GIT_SHA` and `RELEASE_TAG` are passed as `--build-arg`s (Dockerfile.cloudrun bakes them).
- **`_ensure_edit_map_table` once per process:** guarded by a module flag
  (`_edit_map_table_ready`) so `CREATE TABLE IF NOT EXISTS` runs once, not on every
  resolve/download. It also **commits** the DDL (the read-only lookup connection was
  rolling the CREATE back, which caused an early `EDIT_PERSIST_FAILED` — found and fixed
  by effect).
- **`_resolve_tour_from_db`:** when an edit key is found but blob storage is unavailable,
  it now returns `None` instead of falling through to an `ILIKE` name match on a UUID.

---

## Acceptance criteria — evidence

Local cloud-equivalent stand-ins: Postgres (`gcs5r-pg`, 127.0.0.1:5544) + MinIO as the
R2 S3 API (`gcs5r-minio`, 127.0.0.1:9010, bucket `v1-audiotours-r2-bucket`), editing
service run as real subprocesses in `TOUR_STORAGE_MODE=cloud BLOB_STORAGE_TYPE=r2`,
Polly stub recording the requested voice.

1. **B1 red → green, import error pasted** — see B1 above (AssertionError pasted).
2. **B3 red → green on a Russian tour, voice pasted** — RED `Joanna`, GREEN `Tatyana`.
3. **End-to-end on THIS branch's code** (`tests/gcs5r_verify_ru.py`):
   ```
   [E2E] instance A killed; starting fresh instance B
   [E2E] download from fresh instance B: status=200 size=2286
   [E2E] ZIP files: ['audio_1.mp3','audio_1.txt','audio_2.mp3','audio_2.txt','index.html']
   [E2E] audio_1.txt prefix: 'ИЗМЕНЕНО_ Это новый текст первой остановки на русском языке '
   [E2E] fresh instance served edited Russian text from R2: True
   ```
   (The `:`→`_` is the pre-existing `sanitize_user_input` path-safety substitution, not a regression.)
4. **`python api-gateway/test_editing_routes.py` passes; v35-vs-new route diff pasted** — above.
5. **`deploy_gcs5_tour_editing.sh --dry-run`** — builds the gateway image, targets only
   `api-gateway-storied` by default, single env flag, real R2 endpoint. Full output in
   the ClickUp comment / reproducible via the command. Key lines:
   - `Build + push tour-editing image …/services/tour-editing:vNEXT (own image, not shared audioura)`
   - `--set-env-vars '…,R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com,…'` (single flag)
   - `Build + push NEW gateway image …/services/api-gateway:v36 (bakes the 4 new routes)`
   - `Deploy gateway api-gateway-storied onto …api-gateway:v36 + set TOUR_EDITING_URL`
   - `Target gateway(s): api-gateway-storied` (Stable absent without `--stable`)
6. **Row counts before/after; no production row/blob/R2 key touched:**
   ```
   audio_tours rows = 1  (before seed=0 → after=1; edits add 0)
     audio_tours row: (1, audio_tour IS NULL=True, content_language='ru', tour_blob_uri='tours/1.zip')  # unchanged
   tour_edit_blobs rows: additive only (grows by 1 per save)
   R2 (MinIO): tours/1.zip 804B (source, untouched) + tours/edits/1/<uuid>.zip (new edit objects)
   ```
   No `UPDATE`/`DELETE` on `audio_tours`; only new R2 keys under `tours/edits/` and rows in
   the additive `tour_edit_blobs` table.

---

## PROCESS compliance
- **Deployed nothing.** No `gcloud run deploy`, no IAM change, no image push to the prod
  registry. The only gcloud/registry calls made were **read-only**: `describe` the two
  gateways (to confirm both run `api-gateway:v35`) and `docker pull` v35 to extract its
  baked manifest for the route diff. All mutations are staged behind `--apply`.
- **Verified by effect** against running containers, not by reading source.
- Did **not** edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
  `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
- **No `DELETE FROM audio_tours`** anywhere. Verification used local Postgres + MinIO only;
  the harness hard-refuses any `r2.cloudflarestorage.com` endpoint (it printed the SAFETY
  line each run because the dev shell's ambient `R2_ENDPOINT` is production — it was ignored).
- No untracked `.py` in the build context; `.dockerignore` already excludes `test_*.py`,
  `deploy_*.py`, and the `tests/` harness is not copied by the root `COPY *.py`.
- Windows: `encoding="utf-8"` on every file read/write; `subprocess(..., text=True)`.
- **Did not build the APK** (Michael builds on Ubuntu). `flutter analyze
  lib/services/tour_editing_service.dart` → **No issues found!**
- Committed after each blocker; branch `kiro/gcs-5r` pushed. Not merged to `storied`/`main`.

---

## Could not verify
- Real Cloud Run deploy, real Cloudflare R2, real Cloud SQL, real Polly/Comprehend — not
  exercised (deploy is Michael's). Verified against local Postgres + MinIO (S3 API-identical).
- Exact secret **names** and confirming `R2_ENDPOINT` on the live services — the script
  prints the `gcloud run services describe … | grep secretKeyRef` check to confirm before
  `--apply`. The R2 endpoint value used is the one supplied in the ticket.
- On-device app flow end-to-end (needs a signed build + deployed gateway). The Dart change
  is static-analysed clean but not run on a device.

## Note on the stop-2 / preservation nuance (carried from GCS-5, still applies)
`create_complete_tour_with_preservation` matches an unedited stop's original audio by exact
`text_content` equality, and the save runs incoming text through `sanitize_user_input`. If
the app marks a stop "unchanged/preserve" but its post-sanitisation text no longer
byte-matches the stored original, that stop is regenerated via TTS instead of preserved.
That is a latent correctness bug independent of B1–B3 (it would surface as *regenerated*,
not zero-length, audio) and should be tracked separately (match by stop index, or compare
post-sanitisation text). In my green run the preserved stop's original audio was copied
intact, so the happy path does not zero-out audio.
