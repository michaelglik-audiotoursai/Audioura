# SUBMISSION — GCS-TR1D

**Agent:** Services Kiro
**Branch:** `kiro/gcs-tr1d` (base main = `912cdd1`; `git merge-base --is-ancestor 912cdd1 HEAD` → exit 0)
**ClickUp:** `wdvrdaydr1`
**Authorised by:** Michael, 2026-09-17 ~11:00 ("Deploy now" for the translation fix; "I am okay to lose them" for hiding 368/378).

## Outcome summary

- **Step 1 (deploy translation-service): DONE.** New revision `translation-service-00019-fw8`, image `v35-tr1`, digest `sha256:2d46586be250dc6523ebfbdad586e619842613d811eb17af5c24bf9315b7adf8`, serving 100% traffic.
- **Step 2 (hide orphans 368/378): NOT STARTED — BLOCKED.**

## ⛔ BLOCKER — `tour-editing` changed during the task window

The deliverable requires that `tour-editing` (and five other services) be **unchanged** before/after.
It is **not** unchanged:

| service | before (revision / image) | after (revision / image) |
|---|---|---|
| tour-editing | `tour-editing-00003-vpt` / `tour-editing:v3` | `tour-editing-00004-zp7` / `tour-editing:v4` |

Timing:
- `tour-editing-00004-zp7` created `2026-09-17T15:17:10.662606Z`
- my `translation-service-00019-fw8` created `2026-09-17T15:16:12.932919Z`
- prior `tour-editing-00003-vpt` created `2026-09-16T00:44:06.830072Z`

**My deploy could not have caused this.** `deploy_translation_tr1.sh` hardcodes
`SERVICE="translation-service"` and issues a single image-only
`gcloud run services update translation-service ... --image ...:v35-tr1`. It names no other
service and passes no other flags (script and full `--apply` output below). A `translation-service`
image update cannot create a `tour-editing` revision.

Therefore an **external** deploy pushed `tour-editing` v3→v4 at essentially the same minute as my
deploy. Per the task rules ("Stop at the first failure. No retries with changes, no workarounds…
Do not roll back yourself."), I stopped **before** Step 2. No production DB write was performed.
No rollback was performed. I need LEAD/Michael to confirm whether the `tour-editing` v3→v4 change is
expected/authorised and whether to proceed with Step 2 given the precondition is no longer satisfied.

## Step 1 — deploy detail

### Before / after — all services

| service | before (rev / image) | after (rev / image) | unchanged? |
|---|---|---|---|
| translation-service | `translation-service-00018-7nc` / `translation-service:v35` | `translation-service-00019-fw8` / `translation-service:v35-tr1` | changed (intended) |
| tour-generator | `tour-generator-00023-nrv` / `audioura:v36-local474` | `tour-generator-00023-nrv` / `audioura:v36-local474` | ✅ unchanged |
| tour-orchestrator | `tour-orchestrator-00025-cvz` / `audioura:v22-local474` | `tour-orchestrator-00025-cvz` / `audioura:v22-local474` | ✅ unchanged |
| tour-orchestrator-storied | `tour-orchestrator-storied-00002-rwh` / `audioura-storied:v1` | `tour-orchestrator-storied-00002-rwh` / `audioura-storied:v1` | ✅ unchanged |
| tour-editing | `tour-editing-00003-vpt` / `tour-editing:v3` | `tour-editing-00004-zp7` / `tour-editing:v4` | ❌ **CHANGED (external)** |
| api-gateway | `api-gateway-00022-t88` / `api-gateway:v35` | `api-gateway-00022-t88` / `api-gateway:v35` | ✅ unchanged |
| api-gateway-storied | `api-gateway-storied-00003-5zp` / `api-gateway:v36` | `api-gateway-storied-00003-5zp` / `api-gateway:v36` | ✅ unchanged |

### translation-service env names + secret refs (before == after)

Env var names (order identical before/after):
`DB_HOST; DB_NAME; DB_USER; DB_PORT; DB_PASSWORD; AWS_DEFAULT_REGION; AWS_ACCESS_KEY_ID; AWS_SECRET_ACCESS_KEY; R2_ENDPOINT; R2_BUCKET; R2_ACCESS_KEY_ID; R2_SECRET_ACCESS_KEY`

Secret refs (identical before/after):
- `AWS_ACCESS_KEY_ID` → secretKeyRef name `aws-access-key-id`, key `latest`
- `AWS_SECRET_ACCESS_KEY` → secretKeyRef name `aws-secret-access-key`, key `latest`

All other env vars are inline `value` entries; their names and structure are identical before and
after. (Secret/inline values are intentionally not reproduced here.)

### `v35-tr1` digest
`sha256:2d46586be250dc6523ebfbdad586e619842613d811eb17af5c24bf9315b7adf8`

### Preconditions verified before deploy
- GCS-TR1 worktree HEAD = `522d25c`; `git status --porcelain` empty (no modified tracked files).
- Overlay proof: `git diff --stat 912cdd1 522d25c` in GCS-TR1 shows the only runtime service file
  changed is `translation-service/translation_service.py` (remainder: tests_tr1 scaffolding,
  `deploy_translation_tr1.sh`, `Dockerfile.tr1`, `SUBMISSION_GCS-TR1.md`, `.gitattributes`).
- `Dockerfile.tr1` is `FROM …/translation-service:v35` + `COPY translation_service.py /app/` only.

### Full `--apply` output

```
==============================================================
 GCS-TR1 deploy — service: translation-service (and no other)
 base image : us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35
 new image  : us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35-tr1
 dockerfile : /c/adev-wt/GCS-TR1/translation-service/Dockerfile.tr1   (overlay: COPY translation_service.py /app/)
 context    : /c/adev-wt/GCS-TR1/translation-service
 mode       : APPLY
==============================================================

Build:
  docker build -f /c/adev-wt/GCS-TR1/translation-service/Dockerfile.tr1 -t us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35-tr1 /c/adev-wt/GCS-TR1/translation-service
Push:
  docker push us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35-tr1
Deploy (image only — no other flags, no other service):
  gcloud run services update translation-service --region us-central1 --image us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35-tr1

Rollback (manual):
  gcloud run services update translation-service --region us-central1 --image us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35

>>> APPLY: building overlay
#5 [1/2] FROM ...translation-service:v35@sha256:29d390d5fed7da4337da910dac51e1c1e7743adfef6433cdc92d0df67938ad12
#7 [2/2] COPY translation_service.py /app/
#7 CACHED
#8 exporting manifest list sha256:2d46586be250dc6523ebfbdad586e619842613d811eb17af5c24bf9315b7adf8 done
#8 naming to ...translation-service:v35-tr1 done
>>> APPLY: pushing overlay
99eedc9e3182: Pushed
c516bbd8c5a0: Pushed
v35-tr1: digest: sha256:2d46586be250dc6523ebfbdad586e619842613d811eb17af5c24bf9315b7adf8 size: 856
>>> APPLY: updating Cloud Run service image (image only)
Deploying...
Creating Revision...done
Routing traffic...done
Done.
Service [translation-service] revision [translation-service-00019-fw8] has been deployed and is serving 100 percent of traffic.
Service URL: https://translation-service-60899077572.us-central1.run.app
>>> Done. Rollback if needed:
    gcloud run services update translation-service --region us-central1 --image us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35
```

## Step 2 — NOT PERFORMED

Blocked by the `tour-editing` precondition failure above. No Cloud SQL Auth Proxy was started, no DB
connection was made, and **no production DB write (UPDATE/DELETE/INSERT/DDL) was performed**.
Awaiting LEAD/Michael decision.

## Cleanup
- No proxy binary was downloaded (Step 2 not started).
- No secret or temp files created; none committed.
