# SUBMISSION — GCS-5ED

**Task:** Deploy the reviewed Polly-auth fix (GCS-5E, `gcs-5e-authenticate-polly-tts` @ `a9bd8b0`)
to the Preview backend service `tour-editing` (STORIED line). Execute only.
**Agent:** Services Kiro
**Authorised by:** Michael, 2026-09-15 (tour-editing deploy ~14:22; queue `wdvrdaxxm9` 15:42)
**ClickUp:** `wdvrdaycwj`

## Base verification (before any git command)
- Worktree HEAD: `61a96b96dd670d8e9975ae17e1a81b9824e8efb1` (== storied base `61a96b9`).
- `git merge-base --is-ancestor 61a96b9 HEAD` → exit 0 (correct base).
- Working branch created from HEAD: `gcs-5ed-deploy-tour-editing`.
- Preconditions confirmed:
  - `deploy_gcs5e_tour_editing_only.sh` present at worktree root.
  - `tour_editing_phase2.py` contains `class AudioGenerationError` (line 168).

## Command run
From the worktree root, in Git Bash:

```bash
bash deploy_gcs5e_tour_editing_only.sh --apply
```

No edits, no extra flags.

## Result: SUCCESS

### tour-editing:v2 image
- **Digest:** `sha256:8e4cadac6ee76fa5917f839d5c7a3fc2838c6c5b65c160fdb08ce91e1f900e22`
- Image: `us-central1-docker.pkg.dev/audiotours-migration/services/tour-editing:v2`
- Build args baked in: `GIT_SHA=61a96b9`, `RELEASE_TAG=v2t-gcs5e`.

### New ready revision
- **`tour-editing-00002-wc7`** — deployed, serving 100% of traffic.
- Service URL: `https://tour-editing-60899077572.us-central1.run.app`
- Deployed with v1's exact env/secrets/flags (port 5022, `--no-allow-unauthenticated`,
  Cloud SQL `audiotours-migration:us-central1:audioura-db`, R2 + AWS + Polly).

## Three services — revision & image, before and after

| Service               | Before (revision / image)                                   | After (revision / image)                                    | Changed? |
|-----------------------|-------------------------------------------------------------|-------------------------------------------------------------|----------|
| tour-editing          | `tour-editing-00001-924` / `tour-editing:v1`                | `tour-editing-00002-wc7` / `tour-editing:v2`                | YES (intended) |
| api-gateway           | `api-gateway-00022-t88` / `api-gateway:v35`                 | `api-gateway-00022-t88` / `api-gateway:v35`                 | no       |
| api-gateway-storied   | `api-gateway-storied-00003-5zp` / `api-gateway:v36`         | `api-gateway-storied-00003-5zp` / `api-gateway:v36`         | no       |

Both gateways unchanged, as required.

## No-key curl (verification)
```
POST https://storied-api.audioura.com/tour/1/update-multiple-stops   (no X-API-Key)
→ HTTP 401
```
Expected 401 received. No keyed save was run (LEAD verifies).

## Rules compliance
1. Ran only the one approved command; stopped-at-first-failure not triggered (no failure).
2. Touched only `tour-editing`; both gateways confirmed unchanged before and after.
3. No SQL / no DB writes.
4. Only the no-key curl was run (401); no keyed save.
5. None of the protected docs were edited.
6. No blocking questions.

## Rollback (documented by the script, not executed)
```bash
# Fastest: pin traffic back to the known-good v1 revision
gcloud run services update-traffic tour-editing \
  --project audiotours-migration --region us-central1 \
  --to-revisions tour-editing-00001-924=100 --quiet
```
