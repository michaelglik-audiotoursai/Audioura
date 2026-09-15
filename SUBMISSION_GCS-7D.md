# SUBMISSION — GCS-7D

**Task:** Deploy the reviewed LOCAL-474 overlay (GCS-7 @ `1e7c2cb`) to Beta. Execute only.
**Agent:** Services Kiro
**Branch base:** main = `912cdd1` (verified `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0)
**Working branch:** `gcs-7d-deploy-local474` (created from HEAD `912cdd1`)
**ClickUp:** `wdvrdaxxm9` (Storied_Tours' deploy request, item 2)
**Authorised by:** Michael, 2026-09-15 15:42 — "has my approval".
**Executed:** 2026-09-15 (from `/c/adev-wt/GCS-7`, HEAD `1e7c2cb`, clean tree)

## Result

SUCCESS. Both Beta services updated **image-only**. No other service touched.
Env and annotations on both targets are **identical** before and after. All
recorded neighbours are fully unchanged. No SQL / DB writes / tour generation.

- `tour-orchestrator`: `v22` → `v22-local474`, rev `tour-orchestrator-00024-b7t` → `tour-orchestrator-00025-cvz`
- `tour-generator`: `v36` → `v36-local474`, rev `tour-generator-00022-wgn` → `tour-generator-00023-nrv`

## Overlay image digests

| Image | Digest |
|---|---|
| `audioura:v22-local474` (orchestrator overlay, FROM `audioura:v22`) | `sha256:e2aea697de6b85b53e0338a2c574f8e22dc24cc56cb95bdca6a27a5c666e5216` |
| `audioura:v36-local474` (generator overlay, FROM `audioura:v36`) | `sha256:aec5d038c060ee31e8201c7cc6586c6868e2f58f0469894d2756301f32771261` |

Base image digests resolved during build:
- `audioura:v22` → `sha256:93bc056731162c1b528b2f8b3101c7506a0eff9dfee1684bd30ac976686c2946`
- `audioura:v36` → `sha256:0e5e36732b50e750320f2375d91c851b8b72b13761fb1b714949a207d811b0ba`

---

## Pre-run gate checks

```
# my worktree (C:\adev-wt\GCS-7D)
git rev-parse HEAD                              -> 912cdd1cfa5083d3932a502f699b7950612901c8
git merge-base --is-ancestor 912cdd1 HEAD       -> exit 0
git checkout -b gcs-7d-deploy-local474          -> Switched to a new branch

# GCS-7 worktree (C:\adev-wt\GCS-7) — where the script runs
git rev-parse --short HEAD                      -> 1e7c2cb
git status --porcelain                          -> (empty; no modified tracked files)

# environment (Git Bash)
docker Server.Version                           -> 27.3.1
gcloud                                          -> Google Cloud SDK 571.0.0
gcloud config project                           -> audiotours-migration
```

---

## Full `--apply` output

```
1e7c2cb
### MODE: --apply  (commands WILL run)

==== 0. Record current (BEFORE) revisions and images ====
+ gcloud run services describe tour-orchestrator --region us-central1 --project audiotours-migration --format=value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)
tour-orchestrator-00024-b7t	us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22
+ gcloud run services describe tour-generator --region us-central1 --project audiotours-migration --format=value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)
tour-generator-00022-wgn	us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36

==== 1. Build overlay images (FROM v22/v36, COPY only the LOCAL-474 files) ====
+ docker build -f /c/adev-wt/GCS-7/Dockerfile.local474.orchestrator -t us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22-local474 /c/adev-wt/GCS-7
  #5 [1/2] FROM ...audioura:v22@sha256:93bc056731162c1b528b2f8b3101c7506a0eff9dfee1684bd30ac976686c2946
  #7 [2/2] COPY tour_orchestrator_service.py /app/  (CACHED)
  naming to ...audioura:v22-local474
  manifest list sha256:e2aea697de6b85b53e0338a2c574f8e22dc24cc56cb95bdca6a27a5c666e5216
+ docker build -f /c/adev-wt/GCS-7/Dockerfile.local474.generator -t us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474 /c/adev-wt/GCS-7
  #4 [1/2] FROM ...audioura:v36@sha256:0e5e36732b50e750320f2375d91c851b8b72b13761fb1b714949a207d811b0ba
  #6 [2/2] COPY generate_tour_text.py generate_tour_text_service.py /app/  (CACHED)
  naming to ...audioura:v36-local474
  manifest list sha256:aec5d038c060ee31e8201c7cc6586c6868e2f58f0469894d2756301f32771261

==== 2. Push overlay images ====
+ docker push us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22-local474
v22-local474: digest: sha256:e2aea697de6b85b53e0338a2c574f8e22dc24cc56cb95bdca6a27a5c666e5216 size: 856
+ docker push us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474
v36-local474: digest: sha256:aec5d038c060ee31e8201c7cc6586c6868e2f58f0469894d2756301f32771261 size: 856

==== 3. Point the two Beta services at the overlay images — IMAGE ONLY ====
+ gcloud run services update tour-orchestrator --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22-local474
Service [tour-orchestrator] revision [tour-orchestrator-00025-cvz] has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-orchestrator-60899077572.us-central1.run.app
+ gcloud run services update tour-generator --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474
Service [tour-generator] revision [tour-generator-00023-nrv] has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-generator-60899077572.us-central1.run.app

==== 4. Record new (AFTER) revisions and images ====
+ gcloud run services describe tour-orchestrator ...
tour-orchestrator-00025-cvz	us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22-local474
+ gcloud run services describe tour-generator ...
tour-generator-00023-nrv	us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36-local474

==== 5. ROLLBACK (run these to restore the pre-LOCAL-474 images) ====
gcloud run services update tour-orchestrator --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22
gcloud run services update tour-generator --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36

==== DONE ====
```

(Docker layer "Waiting / Layer already exists" progress lines omitted for brevity; both
pushes completed with the digests above. The COPY layers were `CACHED`, confirming the
overlay content matches the reviewed build.)

---

## Before / After — targets (rule 2)

### tour-orchestrator

| | latestReadyRevision | image |
|---|---|---|
| BEFORE | `tour-orchestrator-00024-b7t` | `audioura:v22` |
| AFTER  | `tour-orchestrator-00025-cvz` | `audioura:v22-local474` |

Annotations (BEFORE == AFTER):
```
autoscaling.knative.dev/maxScale: '10'
autoscaling.knative.dev/minScale: '0'
run.googleapis.com/client-name: gcloud
run.googleapis.com/client-version: 571.0.0
run.googleapis.com/cloudsql-instances: audiotours-migration:us-central1:audioura-db
run.googleapis.com/cpu-throttling: 'false'
run.googleapis.com/sessionAffinity: 'false'
run.googleapis.com/startup-cpu-boost: 'true'
```

Env (BEFORE == AFTER), 18 entries:
```
DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db
DB_NAME=audiotours
DB_USER=admin
DB_PORT=5432
TOUR_STORAGE_MODE=cloud
JOB_STORE_MODE=memory
BLOB_STORAGE_TYPE=r2
R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com
R2_BUCKET=v1-audiotours-r2-bucket
DB_PASSWORD -> secret db-password:latest
OPENAI_API_KEY -> secret openai-api-key:latest
AWS_ACCESS_KEY_ID -> secret aws-access-key-id:latest
AWS_SECRET_ACCESS_KEY -> secret aws-secret-access-key:latest
R2_ACCESS_KEY_ID -> secret r2-access-key-id:latest
R2_SECRET_ACCESS_KEY -> secret r2-secret-access-key:latest
TOUR_GENERATOR_URL=https://tour-generator-60899077572.us-central1.run.app
MODERNIZED_URL=https://tour-modernized-60899077572.us-central1.run.app
TRANSLATION_URL=https://translation-service-60899077572.us-central1.run.app
COORDINATES_URL=https://coordinates-60899077572.us-central1.run.app
POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app
TOUR_UPDATE_URL=https://tour-orchestrator-ixkp5nkrlq-uc.a.run.app
USER_API_URL=https://tour-orchestrator-ixkp5nkrlq-uc.a.run.app
```
**Env diff: EMPTY. Annotations diff: EMPTY.**

### tour-generator

| | latestReadyRevision | image |
|---|---|---|
| BEFORE | `tour-generator-00022-wgn` | `audioura:v36` |
| AFTER  | `tour-generator-00023-nrv` | `audioura:v36-local474` |

Annotations (BEFORE == AFTER):
```
autoscaling.knative.dev/maxScale: '5'
autoscaling.knative.dev/minScale: '0'
run.googleapis.com/client-name: gcloud
run.googleapis.com/client-version: 571.0.0
run.googleapis.com/cpu-throttling: 'true'
run.googleapis.com/sessionAffinity: 'false'
run.googleapis.com/startup-cpu-boost: 'true'
```

Env (BEFORE == AFTER), 5 entries:
```
TOUR_STORAGE_MODE=cloud
OPENAI_API_KEY -> secret openai-api-key:latest
PYTHONUNBUFFERED=1
KEY_FIX=v3
OAIFIX=done
```
**Env diff: EMPTY. Annotations diff: EMPTY.**

---

## Before / After — neighbours & gateways (rule 3) — all UNCHANGED

| Service | latestReadyRevision (before==after) | image (before==after) | env/annotations |
|---|---|---|---|
| `tour-orchestrator-storied` | `tour-orchestrator-storied-00001-pk9` | `audioura:storied` | identical |
| `tour-modernized` | `tour-modernized-00012-7sg` | `audioura:v37` | identical |
| `api-gateway` (gateway) | `api-gateway-00022-t88` | `api-gateway:v35` | identical |
| `api-gateway-storied` (gateway) | `api-gateway-storied-00003-5zp` | `api-gateway:v36` | identical |

No new revisions were created on any of these four services; revision names, images,
env, and annotations are byte-for-byte identical before and after the deploy.

---

## Rules compliance

1. No failure occurred; ran the single `--apply` invocation exactly, no retries/workarounds/extra flags.
2. Only `tour-orchestrator` and `tour-generator` changed, image-only. Env + annotations identical before/after (diffs empty). Full before/after recorded above.
3. `tour-orchestrator-storied`, `tour-modernized`, and both gateways recorded before/after — all unchanged.
4. No SQL, no DB writes, no tour generation performed. (LEAD to verify with gate probe.)
5. Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md, GCLOUD_STORIED_START_HERE.md, BUILD_NUMBERS.md.
6. No blocking questions arose.

## Rollback (for LEAD; NOT executed)

```
gcloud run services update tour-orchestrator --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v22
gcloud run services update tour-generator   --region us-central1 --project audiotours-migration --image us-central1-docker.pkg.dev/audiotours-migration/services/audioura:v36
```
