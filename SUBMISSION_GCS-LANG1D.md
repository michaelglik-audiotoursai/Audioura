# SUBMISSION — GCS-LANG1D

**Agent:** Services Kiro
**Base:** storied (`bd387c6`) — worktree HEAD; `git merge-base --is-ancestor bd387c6 HEAD` → exit 0
**Branch:** `kiro/gcs-lang1d`
**ClickUp:** `wdvrdayd40`
**Authorised by:** Michael, 2026-09-17 ~11:00 — "Deploy now" for the language-check fix (`tour-editing:v4`)

## Task
Deploy the reviewed language-gate fix (GCS-LANG1, merged into local `storied` as `2109754`) as
`tour-editing:v4`. Touch only `tour-editing`; both gateways must remain unchanged.

## Preconditions verified
- HEAD = `bd387c6fc464534ddfb1f23b88c4648bb064379a` (exact base).
- `bd387c6` is an ancestor of HEAD (exit 0).
- `tour_editing_phase2.py` contains **both** required functions:
  - `def _narration_for_language_detection(text):` (line 257)
  - `def sanitize_narration_text(text):` (line 354)
- Deploy script present: `deploy_gcs5e_tour_editing_only.sh`.

## Command executed (exactly one)
```bash
bash deploy_gcs5e_tour_editing_only.sh --apply --editing-tag v4
```

## Services — BEFORE and AFTER

| Service               | Before revision            | Before image        | After revision             | After image         | Changed? |
|-----------------------|----------------------------|---------------------|----------------------------|---------------------|----------|
| tour-editing          | tour-editing-00003-vpt     | tour-editing:v3     | tour-editing-00004-zp7     | tour-editing:v4     | YES (intended) |
| api-gateway           | api-gateway-00022-t88      | api-gateway:v35     | api-gateway-00022-t88      | api-gateway:v35     | no       |
| api-gateway-storied   | api-gateway-storied-00003-5zp | api-gateway:v36  | api-gateway-storied-00003-5zp | api-gateway:v36  | no       |

Both gateways unchanged, as required.

## `--apply` output (key lines)
```
== Preflight (tour-editing ONLY — no gateway is referenced by this script)
  GIT_SHA=bd387c6  RELEASE_TAG=v3t-gcs-san1

== Build + push tour-editing image .../services/tour-editing:v4
v4: digest: sha256:779e4071ace0375fcce32cd9abaa878a06cace684318088d1499baf662dcefa6 size: 856

== Deploy new tour-editing revision onto .../services/tour-editing:v4
Setting IAM Policy...done
Creating Revision...done
Routing traffic...done
Done.
Service [tour-editing] revision [tour-editing-00004-zp7] has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-editing-60899077572.us-central1.run.app

== APPLIED (tour-editing only).
```
The build (steps 1–10 of `Dockerfile.cloudrun`), push, and `gcloud run deploy` all completed.
The script references only `tour-editing`; no gateway commands were emitted or run.

## tour-editing:v4 — digest and new revision
- **Image:** `us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v4`
- **Digest:** `sha256:779e4071ace0375fcce32cd9abaa878a06cace684318088d1499baf662dcefa6`
- **New revision:** `tour-editing-00004-zp7`
- **Traffic:** 100% to `tour-editing-00004-zp7` (latestRevision), Ready and serving.
- **GIT_SHA baked in:** `bd387c6` (correct base).

## /health result
Direct call to the `--no-allow-unauthenticated` tour-editing service with an identity token:
```bash
curl -s -o /dev/null -w 'HTTP=%{http_code}\n' \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://tour-editing-60899077572.us-central1.run.app/health
```
Result: **HTTP=200**

## ROLLBACK (live v3 revision = `tour-editing-00003-vpt`)
```bash
# Option A: pin traffic back to the known-good v3 revision (fastest, no rebuild):
gcloud run services update-traffic tour-editing \
  --project audiotours-migration --region us-central1 \
  --to-revisions tour-editing-00003-vpt=100 --quiet

# Option B: redeploy the v3 image (if the revision was pruned):
gcloud run deploy tour-editing \
  --project audiotours-migration --region us-central1 \
  --image us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3 \
  --command python --args tour_editing_phase2.py \
  --port 5022 --no-allow-unauthenticated \
  --add-cloudsql-instances audiotours-migration:us-central1:audioura-db \
  --set-env-vars 'TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2,DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db,DB_NAME=audiotours,DB_USER=admin,R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com,R2_BUCKET=v1-audiotours-r2-bucket,POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app,AWS_DEFAULT_REGION=us-east-1' \
  --set-secrets 'DB_PASSWORD=db-password:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest' \
  --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet
```

## Compliance notes
- Stopped at no failure; ran exactly the one authorized command, no retries/workarounds/individual gcloud deploy commands.
- Only `tour-editing` was mutated. Both gateways verified unchanged before and after.
- New revision `tour-editing-00004-zp7` is Ready, serving 100%; `/health` = 200.
- No SQL, no DB writes, no tour generation, no keyed save.
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md,
  GCLOUD_STORIED_START_HERE.md, BUILD_NUMBERS.md, or the deploy script.
