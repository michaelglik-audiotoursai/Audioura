# SUBMISSION — GCS-5E

Edited stops get no audio in the cloud: authenticate the Polly call and stop
reporting success when TTS fails.

- **Agent:** Services Kiro
- **Base:** storied (`0de517c`) — `git merge-base --is-ancestor 0de517c HEAD` exits 0.
- **Branch:** `gcs-5e-authenticate-polly-tts`
- **ClickUp:** `wdvrdaycwj`
- **Scope touched:** `tour_editing_phase2.py` only (service code) + new test/deploy
  files. No `api-gateway/`, no `audio_tour_app/`, no other service. Nothing deployed.

---

## Root cause (confirmed against the code)
`tour_editing_phase2.py` made the Polly call with a bare, unauthenticated
`requests.post(f"{POLLY_TTS_URL}/synthesize", ...)`. `polly-tts` is a private
Cloud Run service (`roles/run.invoker` only, no public access), so the call
returned **403**. On a non-200 the generator returned `("error", [])` **without
logging**, and the callers (`create_complete_tour_with_preservation` /
`create_complete_tour`) ignored the return value — so the save reported success
with a missing `audio_1.mp3`. This is why LEAD's Russian edit of tour 421 saved
200 but the ZIP lacked `audio_1.mp3`, and why Michael saw "Audio Editing shows 0
length and will not play".

## What I changed

### 1. Authenticate every private Cloud Run call from this service
Added, mirroring the orchestrator's proven pattern
(`tour_orchestrator_service.py` `_get_auth_headers` / `_authenticated_request`):

- `_get_identity_token(audience)` — fetches a Google-signed identity token from
  the GCE/Cloud Run metadata server (`audience` = the target base URL). On local
  dev there is no metadata server, so it returns `None` and no token is sent
  (behaviour unchanged).
- `_auth_headers_for(url)` — audience = `scheme://netloc`; attaches
  `Authorization: Bearer <token>` for `https://` targets.
- `_authenticated_request(method, url, **kwargs)` — `requests.request` wrapper
  that merges in the auth header.

The Polly `/synthesize` call now goes through `_authenticated_request`.
**Audit:** the only outbound `requests.*` in this file was the Polly call; the
remaining two `requests` references are now the metadata token fetch and the
wrapper itself. No other private call was missed.

Injection seams for tests (production never sets them, so default behaviour is
unchanged):
- `_identity_token_fn` — a `callable(audience)->token` (used by the in-process
  unit test).
- `LOCAL_IDENTITY_TOKEN` env var — lets a local E2E harness attach a token to an
  http Polly stub and exercise the real `_authenticated_request` path.

### 2. Never report success for a stop that needed audio and did not get it
`generate_audio_for_stop` now, on a Polly failure for a stop being generated:
- **logs** the upstream status and a body snippet
  (`[TTS] Polly /synthesize failed for stop N: status=... body=...`), and
- raises `AudioGenerationError(stop_number, status, body_snippet)` instead of
  silently returning `("error", [])`.

`_bulk_save_core` catches `AudioGenerationError` **before** the R2 upload / DB
insert and returns an error:
- `error_code: "AUDIO_GENERATION_FAILED"`, `recoverable: true`, with
  `stop_number` and `upstream_status`;
- 4xx/5xx (502 for upstream 401/403/5xx, else 500);
- because the exception is raised during tour build, the R2 upload and the
  `tour_edit_blobs` insert never run — **no R2 object, no mapping row**.

A preserved stop whose original MP3 is simply copied is not a TTS call and is
unaffected. Synthesised text, voices and preservation matching are unchanged.

## Acceptance criteria — status

**1. Red → green with an auth-requiring Polly stub** — `tests/test_gcs5e_polly_auth_and_fail.py` (9/9 PASS)
   - Auth-requiring stub (403 unless `Authorization: Bearer <token>`) + injected
     `_identity_token_fn`, so the token path is genuinely exercised.
   - RED: pre-fix bare-post generator gets 403 and writes **no** `audio_1.mp3`.
   - GREEN(a): real bulk-save with token injected → 200; built ZIP has
     `audio_1.mp3` > 0; R2 upload + mapping row created (cloud mode).
   - GREEN(b): Polly 403 → **502 `AUDIO_GENERATION_FAILED`**, **no** R2 object,
     **no** `tour_edit_blobs` row.

**2. Existing guards still pass** (all exit 0):
   - `tests/gcs5r_b1_import_guard.py`
   - `tests/test_local153_tour_editing_shims_guard.py`
   - `tests/test_gcs5r2_update_stop_empty_text.py`
   - `api-gateway/test_editing_routes.py`

**3. End-to-end on this branch (local Postgres + MinIO), Russian tour** — `tests/gcs5e_verify_ru_auth.py` (PASS)
   - Stands up its own local Postgres (5544) + MinIO (9010), seeds a Russian
     R2-migrated tour (`content_language='ru'`, `audio_tour` NULL), runs the real
     service against an auth-requiring Polly stub with `LOCAL_IDENTITY_TOKEN`.
   - Proven by effect: save → 200; **0 unauthenticated 403 hits**; edited stop
     synthesised with voice **`Tatyana`**; fresh instance B serves the edited ZIP
     from R2 with `audio_1.mp3` = 135 bytes (> 0) and the edited Russian text;
     `audio_tours` grew only by the seeded row. Talks only to local MinIO;
     no `DELETE FROM audio_tours`.

**4. Staged `tour-editing`-only redeploy** — `deploy_gcs5e_tour_editing_only.sh`
   (companion script; `--dry-run` output below).

## Deploy: companion script vs `--editing-only` flag (justification)
I wrote a **separate companion script** rather than adding `--editing-only` to
`deploy_gcs5_tour_editing.sh`. That script interleaves the tour-editing build
(steps 1–2) with a **mandatory gateway rebuild** (steps 3–5: pull
`api-gateway:v35`, byte-diff `main.py`, build `api-gateway:v36`, redeploy a
gateway) under one shared `mktemp`/`trap`. Threading an `--editing-only` guard
through that block would leave the gateway machinery one missed conditional away
from firing. GCS-5E must not touch either gateway, so a script that contains
**no gateway code at all** is safer and auditable end to end. It reuses v1's
**exact** image name, env, secrets and run flags (copied from step 2), so v2
differs from v1 only in the code. It deploys nothing without `--apply`, modifies
no IAM (v1's invoker bindings persist across a new revision), and prints the
rollback to `tour-editing:v1` (`tour-editing-00001-924`).

### `--dry-run` output
```
== Preflight (tour-editing ONLY — no gateway is referenced by this script)
  [dry-run] command -v gcloud >/dev/null || { echo 'gcloud not on PATH'; exit 1; }
  [dry-run] command -v docker >/dev/null || { echo 'docker not on PATH'; exit 1; }
  [dry-run] gcloud auth print-access-token >/dev/null 2>&1 || { echo 'not authenticated'; exit 1; }
  GIT_SHA=b5e695e  RELEASE_TAG=v2t-gcs5e

== Build + push tour-editing image us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2 (own image, not shared audioura)
  [dry-run] docker build -f 'Dockerfile.cloudrun'   --build-arg GIT_SHA='b5e695e' --build-arg RELEASE_TAG='v2t-gcs5e'   -t 'us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2' .
  [dry-run] gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
  [dry-run] docker push 'us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2'

== Deploy new tour-editing revision onto us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2 (v1's env/secrets/flags)
  NOTE: confirm secret NAMES against the LIVE v1 service before --apply:
    gcloud run services describe tour-editing --region us-central1 --format=yaml | grep -iE 'secretKeyRef|name:'
  [dry-run] gcloud run deploy 'tour-editing'   --project 'audiotours-migration' --region 'us-central1'   --image 'us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2'   --command python --args tour_editing_phase2.py   --port 5022 --no-allow-unauthenticated   --add-cloudsql-instances 'audiotours-migration:us-central1:audioura-db'   --set-env-vars 'TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2,DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db,DB_NAME=audiotours,DB_USER=admin,R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com,R2_BUCKET=v1-audiotours-r2-bucket,POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app,AWS_DEFAULT_REGION=us-east-1'   --set-secrets 'DB_PASSWORD=db-password:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest'   --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet

== ROLLBACK (if v2 misbehaves) — route 100% of traffic back to v1

  # Option A: pin traffic to the known-good v1 revision (fastest, no rebuild):
  gcloud run services update-traffic tour-editing \
    --project audiotours-migration --region us-central1 \
    --to-revisions tour-editing-00001-924=100 --quiet

  # Option B: redeploy the v1 image (if the revision was pruned):
  gcloud run deploy tour-editing \
    --project audiotours-migration --region us-central1 \
    --image us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v1 \
    --command python --args tour_editing_phase2.py \
    --port 5022 --no-allow-unauthenticated \
    --add-cloudsql-instances audiotours-migration:us-central1:audioura-db \
    --set-env-vars '...same as above...' \
    --set-secrets '...same as above...' \
    --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet

  # Neither gateway is involved in deploy OR rollback.

== POST-DEPLOY VERIFICATION — run after --apply
  (edit a real Russian R2-migrated tour, assert download ZIP has audio_1.mp3 > 0;
   negative case: Polly unreachable → AUDIO_GENERATION_FAILED, no new tour)

DRY RUN COMPLETE — nothing was deployed. No gateway referenced.
```

## PROCESS compliance
1. **Deployed nothing** — no `docker push`, no `gcloud run deploy/update`. Deploy
   script is dry-run by default; the `--dry-run` output above only prints.
2. Touched only `tour-editing` (`tour_editing_phase2.py`) + new test/deploy
   files. No `api-gateway/`, `audio_tour_app/`, or any other service.
3. E2E used local Postgres/MinIO only; harness overrides any ambient
   `R2_ENDPOINT` to local MinIO and asserts it is not a real R2 endpoint. No
   `DELETE FROM audio_tours` anywhere.
4. Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`,
   `.continuous_dev/STATUS.md`, `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
5. Windows: `encoding="utf-8"` on every file read/write in new code; the E2E
   sends Cyrillic via JSON serialised in-process (no Git Bash body mangling).
6. Committed after each step and would push; see commit log below.

## Files
- `tour_editing_phase2.py` — auth helpers, `AudioGenerationError`, authenticated
  Polly call with logging, `AUDIO_GENERATION_FAILED` handling before R2/DB.
- `tests/test_gcs5e_polly_auth_and_fail.py` — red→green auth + fail-on-TTS guard.
- `tests/gcs5e_polly_auth_stub.py` — auth-requiring Polly stub (records voice).
- `tests/gcs5e_verify_ru_auth.py` — local PG/MinIO E2E, Russian tour, Tatyana.
- `deploy_gcs5e_tour_editing_only.sh` — tour-editing-only staged redeploy (dry-run default).

## Commits (branch `gcs-5e-authenticate-polly-tts`, from `0de517c`)
- `f1b7c7d` authenticate Polly call and fail save when TTS fails
- `100b979` red→green guard for Polly auth + fail-on-TTS-failure
- `b5e695e` E2E harness (auth Polly + local PG/MinIO) + LOCAL_IDENTITY_TOKEN seam
- `d47b3bf` tour-editing-only redeploy companion script (dry-run default)

## Blocking questions / notes for LEAD
- **Secret names for `--apply`.** The deploy script reuses the secret refs from
  `deploy_gcs5_tour_editing.sh` step 2 (`db-password`, `r2-access-key-id`,
  `r2-secret-access-key`, `aws-access-key-id`, `aws-secret-access-key`, all
  `:latest`). The script prints a `gcloud run services describe tour-editing`
  reminder to confirm the live v1 secret names before applying. Please confirm.
- **Failure HTTP code.** I return **502** for upstream 401/403/5xx (a genuine
  upstream/auth failure) and 500 otherwise, both with
  `error_code: "AUDIO_GENERATION_FAILED"`. If you prefer a single fixed code
  (e.g. always 502, or 503 to signal "retry later"), it is a one-line change.
