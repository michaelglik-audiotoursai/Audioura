# SUBMISSION — GCS-KS1D: Deploy current Storied stack to Preview

**Agent:** Services Kiro
**Base:** storied (`6fbebdf`)
**Branch:** `kiro/gcs-ks1d` (created from HEAD `6fbebdf`)
**ClickUp:** `wdvrdayh4c`
**Authorised by:** Michael, 2026-09-24 — Preview only. Beta/Stable untouched.
**Run:** `bash deploy_storied_generator.sh` (no flags — the real deploy), Git Bash on Windows.

## Result

**Deploy is complete.** All three Storied services deployed on image
`audioura-storied:v2`, are Ready and serving 100% of traffic, and return `/health` 200.
Beta services are unchanged.

The script exited non-zero on **only** the known cosmetic artifact (Rule 5): its final
`TOUR_TRACK` check compared gcloud's `extract()` output, which adds literal quotes under
Git Bash, and reported:

```
FAILED: TOUR_TRACK on tour-orchestrator-storied is ''storied'', not 'storied' — tours would record as Beta.
```

An independent read-back **without** the quoting idiom confirms the value is exactly `storied`
(see "URL and TOUR_TRACK read-backs" below). This is the only failure, it is cosmetic, and per
Rule 5 **no rollback was performed**. Because this check runs before the release-tag step, the
release tag `v2t1` was **not** created/pushed (no `git tag v2t1` exists locally or on origin).

## Pre-deploy gate (all passed)

- `git rev-parse --short HEAD` = `6fbebdf` (`git merge-base --is-ancestor 6fbebdf HEAD` → exit 0)
- `user_stops_flag.py` exists (`-rwxr-xr-x … 4839 …`)
- `grep -c USER_STOPS_ENABLED=false deploy_storied_generator.sh` = **3**
- `git status --porcelain -uall | grep '\.py$'` = **empty** (no dirty `.py`)
- Preflight guards inside the script all reported OK (TOUR_TRACK read, URL env reads,
  /generate + /status routes, no untracked `.py`, build-context complete).

## Commit deployed / image

- **Commit deployed:** `6fbebdf9` (branch `kiro/gcs-ks1d`, storied line 2)
- **Image built & pushed:** `us-central1-docker.pkg.dev/audiotours-migration/services/audioura-storied:v2`
- **Digest:** `sha256:d29e5a7263c53638929c1ce504ef376617f0d6dd18a7ded967c558f912f06574` (manifest list, size 856)
- **Dockerfile:** `Dockerfile.cloudrun` — build shipped `db_connection.py`, `stop_anchor_detector_v2.py`,
  `story_type_taxonomy.json`, and `templates/` (B4b gaps closed; visible in build steps `#10`–`#13`).
- Repo is `audioura-storied`, separate from Beta's shared `audioura` (Property 1).

## Three Storied services — revisions, URLs, /health

| Service | Revision (after) | URL | /health |
|---|---|---|---|
| tour-generator-storied | `tour-generator-storied-00004-887` | https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app | **200**, `status:"healthy"`, `version:2.2.0.1`, `mode:"true"` |
| tour-modernized-storied | `tour-modernized-storied-00002-xnc` | https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app | **200**, `status:"healthy"`, `version:1.2.5.184` |
| tour-orchestrator-storied | `tour-orchestrator-storied-00003-tzg` | https://tour-orchestrator-storied-ixkp5nkrlq-uc.a.run.app | **200**, `status:"healthy"`, `service:"tour_orchestrator"` |

All three: traffic 100% to the latest revision (`latestRevision: true`).

### /health raw responses
- **tour-generator-storied**: `{"build_time":"no_manifest","code_sha":"no_manifest","cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"drift_files":["<manifest_missing>"],"manifest_ok":false,"mode":"true","service":"tour_text_generator","status":"healthy","version":"2.2.0.1"}`
- **tour-modernized-storied**: `{"service":"tour_generation_modernized","status":"healthy","version":"1.2.5.184"}`
- **tour-orchestrator-storied**: `{"cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"service":"tour_orchestrator","status":"healthy"}`

(HTTP codes re-confirmed with `gcloud auth print-identity-token`: all **200**.)

## URL and TOUR_TRACK read-backs (Rule 5)

Read directly from `tour-orchestrator-storied` (quote artifact stripped):

```
TOUR_TRACK        = storied
STORIED_MODE      = true
USER_STOPS_ENABLED= false
TOUR_GENERATOR_URL= https://tour-generator-storied-ixkp5nkrlq-uc.a.run.app
MODERNIZED_URL    = https://tour-modernized-storied-ixkp5nkrlq-uc.a.run.app
```

Both orchestrator URLs contain `-storied` (script's own AC5 check also passed:
"both orchestrator URLs contain '-storied': OK"). `TOUR_TRACK` is literally `storied`;
the script's `''storied''` was the cosmetic Git-Bash `extract()` quoting only.

## Required env / config on the three Storied services (after)

**tour-generator-storied** — `USER_STOPS_ENABLED=false`, `TOUR_TRACK=storied`, `STORIED_MODE=true`,
`TOUR_STORAGE_MODE=cloud`; Cloud SQL annotation `run.googleapis.com/cloudsql-instances=audiotours-migration:us-central1:audioura-db`;
cpu-throttling false; maxScale 1; concurrency 40; cpu 1; 512Mi. Secrets by reference: `OPENAI_API_KEY`→openai-api-key,
`DB_PASSWORD`/`PGPASSWORD`→db-password.

**tour-modernized-storied** — `USER_STOPS_ENABLED=false`, `TOUR_STORAGE_MODE=cloud`, `BLOB_STORAGE_TYPE=r2`,
`POLLY_FIX=v3`; maxScale 1; concurrency 5; cpu 2; 1Gi. Secrets by reference: aws-access-key-id, aws-secret-access-key,
r2-access-key-id, r2-secret-access-key.

**tour-orchestrator-storied** — `USER_STOPS_ENABLED=false`, `TOUR_TRACK=storied`, `STORIED_MODE=true`;
**maxScale 10, concurrency 80, cpu 1, 512Mi preserved**; Cloud SQL annotation preserved
(`…cloudsql-instances=audiotours-migration:us-central1:audioura-db`); ~20 env vars preserved
(only image + `TOUR_GENERATOR_URL`/`MODERNIZED_URL` + `USER_STOPS_ENABLED`/`TOUR_TRACK` updated via `--update-env-vars`).
Secrets by reference: db-password, openai-api-key, aws-access-key-id, aws-secret-access-key, r2-access-key-id, r2-secret-access-key.

## Before / After — Storied services

| Service | Before revision | Before image | After revision | After image |
|---|---|---|---|---|
| tour-generator-storied | tour-generator-storied-00003-2gf | audioura-storied:v1 | **tour-generator-storied-00004-887** | **audioura-storied:v2** |
| tour-modernized-storied | tour-modernized-storied-00001-b2c | audioura-storied:v1 | **tour-modernized-storied-00002-xnc** | **audioura-storied:v2** |
| tour-orchestrator-storied | tour-orchestrator-storied-00002-rwh | audioura-storied:v1 | **tour-orchestrator-storied-00003-tzg** | **audioura-storied:v2** |

Note: `USER_STOPS_ENABLED` was **absent** on all three before; it is now `false` on all three (per D591 — Igor's user-chosen stops inert).
Orchestrator scaling/resources/Cloud SQL annotation unchanged before→after (maxScale 10, concurrency 80, cpu 1, 512Mi).

## Before / After — Beta services (must be UNCHANGED — they are)

| Service | Before revision | After revision | Image (before = after) |
|---|---|---|---|
| tour-generator | tour-generator-00023-nrv | tour-generator-00023-nrv | audioura:v36-local474 |
| tour-modernized | tour-modernized-00012-7sg | tour-modernized-00012-7sg | audioura:v37 |
| tour-orchestrator | tour-orchestrator-00025-cvz | tour-orchestrator-00025-cvz | audioura:v22-local474 |
| api-gateway | api-gateway-00022-t88 | api-gateway-00022-t88 | api-gateway:v35 |
| translation-service | translation-service-00019-fw8 | translation-service-00019-fw8 | translation-service:v35-tr1 |
| map-delivery | map-delivery-00014-bdp | map-delivery-00014-bdp | audioura:v40 |

All Beta revisions and images are **identical before and after**. No Beta service was named in any
mutating call (the script's `assert_target_is_storied` gate enforces this in code).

## Compliance with rules
1. Ran the real deploy once, no flags; stopped at the single (cosmetic) failure, no retries/workarounds. No rollback.
2. No Beta service touched; the four core Beta services recorded before & after — identical.
3. Three Storied services recorded (revision, image, full env by reference); post-deploy each shows
   `USER_STOPS_ENABLED=false`, `TOUR_TRACK=storied`, `STORIED_MODE=true`; orchestrator kept maxScale 10 /
   concurrency 80 / cpu 1 / 512Mi and its Cloud SQL annotation.
4. Each of the three is Ready, serving 100%, `/health` = 200 with an identity token.
5. Only the cosmetic `''storied''` `TOUR_TRACK` check failed; reported explicitly, deploy otherwise complete,
   no rollback. URL/TOUR_TRACK read-backs pasted above.
6. No tour generation, no SQL, no DB writes performed.
7. Did not edit any of the protected docs.

## Blocking question
None.

## Deploy output
Full build/push/deploy console output captured in `_deploy_output.txt`; before/after captures in
`_before_state.txt` and `_after_state.txt` (working artifacts, not committed). The salient lines:

```
Service [tour-generator-storied] revision [tour-generator-storied-00004-887] has been deployed and is serving 100 percent of traffic.
Service [tour-modernized-storied] revision [tour-modernized-storied-00002-xnc] has been deployed and is serving 100 percent of traffic.
Service [tour-orchestrator-storied] revision [tour-orchestrator-storied-00003-tzg] has been deployed and is serving 100 percent of traffic.
v2: digest: sha256:d29e5a7263c53638929c1ce504ef376617f0d6dd18a7ded967c558f912f06574 size: 856
  tour-generator-storied /health -> ... "status":"healthy" ...
  tour-modernized-storied /health -> ... "status":"healthy" ...
  tour-orchestrator-storied /health -> ... "status":"healthy" ...
  both orchestrator URLs contain '-storied': OK
FAILED: TOUR_TRACK on tour-orchestrator-storied is ''storied'', not 'storied'  <-- cosmetic Git-Bash extract() quoting only
```
