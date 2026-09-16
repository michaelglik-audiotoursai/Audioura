# SUBMISSION — GCS-SAN1D

**Agent:** Services Kiro
**Task:** Deploy the reviewed narration fix (`gcs-san1-narration-sanitiser`) as `tour-editing:v3`. Preview line only; Stable untouched.
**Base:** local `storied` = `0fe5ac1` ("Merge branch 'gcs-san1-narration-sanitiser' into storied")
**Branch:** `gcs-san1d-deploy-tour-editing-v3` (created from HEAD)
**Authorised by:** Michael — Preview tour-editing deploys approved 2026-09-15 ~14:22; "work your queue … wdvrdayd3d".
**Result:** SUCCESS. `tour-editing:v3` built, pushed, deployed. New revision Ready and serving 100%. `/health` = 200. Both gateways unchanged.

---

## Preconditions verified

- `git merge-base --is-ancestor 0fe5ac1 HEAD` → exit 0 (correct base).
- HEAD = `0fe5ac1 Merge branch 'gcs-san1-narration-sanitiser' into storied`.
- `deploy_gcs5e_tour_editing_only.sh` present at worktree root.
- `tour_editing_phase2.py` contains `def sanitize_narration_text` (line 295).
- gcloud authenticated as `michael.glik@gmail.com`, project `audiotours-migration`.

## Command run (exactly as specified, no extra flags)

```bash
bash deploy_gcs5e_tour_editing_only.sh --apply
```

---

## Services — revision / image BEFORE and AFTER

| Service | BEFORE revision | BEFORE image | AFTER revision | AFTER image |
|---|---|---|---|---|
| **tour-editing** | tour-editing-00002-wc7 | tour-editing:v2 | **tour-editing-00003-vpt** | **tour-editing:v3** |
| api-gateway | api-gateway-00022-t88 | api-gateway:v35 | api-gateway-00022-t88 | api-gateway:v35 |
| api-gateway-storied | api-gateway-storied-00003-5zp | api-gateway:v36 | api-gateway-storied-00003-5zp | api-gateway:v36 |

Both gateways are **unchanged** (match the required `api-gateway-00022-t88` @ v35 and `api-gateway-storied-00003-5zp` @ v36). Only `tour-editing` was touched.

## Image digest and new ready revision

- **Image:** `us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3`
- **Digest:** `sha256:4e241c0fad22adc643bd86d32efaeb648ff5121fd031a9069dafc5dde1d5f531`
- **New ready revision:** `tour-editing-00003-vpt`
- **Traffic:** `{'latestRevision': True, 'percent': 100, 'revisionName': 'tour-editing-00003-vpt'}` — serving 100%.
- Build args baked in: `GIT_SHA=0fe5ac1`, `RELEASE_TAG=v3t-gcs-san1`.

## /health result

```
GET https://tour-editing-60899077572.us-central1.run.app/health
Authorization: Bearer $(gcloud auth print-identity-token)
-> HTTP=200
```

## Rollback (real v2 revision confirmed live: tour-editing-00002-wc7)

Revision list confirms `tour-editing-00002-wc7` still present.

```bash
# Option A: pin traffic to the known-good v2 revision (fastest, no rebuild):
gcloud run services update-traffic tour-editing \
  --project audiotours-migration --region us-central1 \
  --to-revisions tour-editing-00002-wc7=100 --quiet

# Option B: redeploy the v2 image (if the revision was pruned):
gcloud run deploy tour-editing \
  --project audiotours-migration --region us-central1 \
  --image us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2 \
  --command python --args tour_editing_phase2.py \
  --port 5022 --no-allow-unauthenticated \
  --add-cloudsql-instances audiotours-migration:us-central1:audioura-db \
  --set-env-vars 'TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2,DB_HOST=/cloudsql/audiotours-migration:us-central1:audioura-db,DB_NAME=audiotours,DB_USER=admin,R2_ENDPOINT=https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com,R2_BUCKET=v1-audiotours-r2-bucket,POLLY_TTS_URL=https://polly-tts-60899077572.us-central1.run.app,AWS_DEFAULT_REGION=us-east-1' \
  --set-secrets 'DB_PASSWORD=db-password:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest,AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest' \
  --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet

# Neither gateway is involved in deploy OR rollback.
```

---

## Full `--apply` output

Below is the script's own stdout (banners + push summary + deploy result). The build's apt/docker layer progress is emitted on stderr and elided for readability; the material lines (image naming, push digest, deploy result) are included.

```
== Preflight (tour-editing ONLY — no gateway is referenced by this script)
  GIT_SHA=0fe5ac1  RELEASE_TAG=v3t-gcs-san1

== Build + push tour-editing image us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3 (own image, not shared audioura)
The push refers to repository [us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing]
3678bb828654: Layer already exists
f9efa1b83d06: Layer already exists
db840d086b65: Layer already exists
6310eb16bf42: Layer already exists
0e1f159b707f: Layer already exists
4571dea7d3b0: Pushed
164d3b9b11be: Pushed
708afd4e56b6: Pushed
722e2fb2e6fb: Pushed
7e1bd89bdb00: Pushed
5fab1b2797a9: Pushed
3ac8467c02eb: Pushed
fa8ed2b1755f: Pushed
cee45a03eae1: Pushed
v3: digest: sha256:4e241c0fad22adc643bd86d32efaeb648ff5121fd031a9069dafc5dde1d5f531 size: 856

# Docker build (from stderr): image built and named
#15 naming to us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3 done
#15 unpacking to us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3 done

== Deploy new tour-editing revision onto us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v3 (v1's env/secrets/flags)
  NOTE: confirm secret NAMES against the LIVE v1 service before --apply:
    gcloud run services describe tour-editing --region us-central1 --format=yaml | grep -iE 'secretKeyRef|name:'

# gcloud run deploy (from stderr):
Deploying container to Cloud Run service [tour-editing] in project [audiotours-migration] region [us-central1]
Deploying...
Setting IAM Policy.............done
Creating Revision......done
Routing traffic.....done
Done.
Service [tour-editing] revision [tour-editing-00003-vpt] has been deployed and is serving 100 percent of traffic.
Service URL: https://tour-editing-60899077572.us-central1.run.app

== ROLLBACK (if v3 misbehaves) — route 100% of traffic back to v2
  (rollback commands printed by script; script placeholder <CONFIRM_LIVE_V2_REVISION>
   is filled with the real revision tour-editing-00002-wc7 in the Rollback section above)

== POST-DEPLOY VERIFICATION — run after --apply
  (verification curls printed by script; LEAD verifies by effect)

== APPLIED (tour-editing only). Verify by effect using the curls above before calling it done.
```

Note on the deploy script's printed `NOTE`/rollback placeholder: the script always prints those lines regardless of `--apply`; the actual deploy used the exact env/secrets/flags shown, created the new revision, and routed 100% traffic (confirmed by `gcloud run services describe` above). The `<CONFIRM_LIVE_V2_REVISION>` placeholder is a deliberate part of the script and was NOT edited; the real value `tour-editing-00002-wc7` is supplied here in the Rollback section.

## Compliance with rules

1. No failure occurred; image pushed AND deploy succeeded. No retries/workarounds; ran the single command as specified.
2. Only `tour-editing` touched. Both gateways verified unchanged before and after.
3. New revision `tour-editing-00003-vpt` Ready and serving 100%. `/health` (with identity token) = 200.
4. Rollback section uses the real live v2 revision `tour-editing-00002-wc7`. Script was not edited.
5. No SQL, no DB writes, no tour generation, no keyed save performed.
6. No protected docs edited (DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/STATUS.md, GCLOUD_STORIED_START_HERE.md, BUILD_NUMBERS.md).
7. No blocking question — task completed.
