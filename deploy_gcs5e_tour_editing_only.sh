#!/usr/bin/env bash
# =============================================================================
# GCS-5E — tour-editing-ONLY staged redeploy (Preview/STORIED line).
#          Runbook: ClickUp wdvrdaycwj.
#
# WHY A SEPARATE SCRIPT (not a --editing-only flag on deploy_gcs5_tour_editing.sh):
#   deploy_gcs5_tour_editing.sh interleaves the tour-editing build (steps 1-2)
#   with a MANDATORY gateway rebuild (steps 3-5): it pulls api-gateway:v35,
#   byte-diffs main.py, builds api-gateway:v36 and redeploys a gateway, all
#   under one shared mktemp/trap. Threading an --editing-only guard through that
#   block would leave the gateway machinery one missed conditional away from
#   running. GCS-5E must NOT touch either gateway, so a self-contained script
#   that has NO gateway code at all is the safer, more auditable choice: you can
#   read it top to bottom and see it only ever names `tour-editing`.
#
#   It reuses v1's EXACT image name, env, secrets and run flags (copied from
#   deploy_gcs5_tour_editing.sh step 2) so v2 differs from v1 only in the code.
#
# THIS SCRIPT DEPLOYS NOTHING BY DEFAULT. Every mutating gcloud/docker call goes
# through run(), which only PRINTS in dry-run (the default). Deploy is LEAD's
# call: pass --apply to actually run.
#
# What it stages, in order:
#   1. Build + push the tour-editing backend image tour-editing:<tag> (default
#      v3 for GCS-SAN1). GIT_SHA / RELEASE_TAG baked in as build-args, exactly
#      like v1/v2.
#   2. `gcloud run deploy tour-editing` onto the new image with the SAME env,
#      secrets and flags as v1/v2 (port 5022, --no-allow-unauthenticated, Cloud
#      SQL, R2 + AWS + Polly). A deploy of an existing service creates a new
#      revision and keeps the service's identity/IAM; no gateway is touched.
#   3. Print the EXACT rollback to the previous known-good image tour-editing:v2
#      (GCS-5E). v2's revision name must be confirmed against the live service.
#
# It NEVER references api-gateway / api-gateway-storied and has no gateway image
# code. It does not modify IAM (v1/v2's invoker bindings already exist).
#
# Usage:
#   ./deploy_gcs5e_tour_editing_only.sh --dry-run            # default; prints only
#   ./deploy_gcs5e_tour_editing_only.sh --apply              # deploy v3 (LEAD)
#   ./deploy_gcs5e_tour_editing_only.sh --dry-run --editing-tag v3
# =============================================================================
set -euo pipefail

PROJECT="audiotours-migration"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"

# --- tour-editing backend: identical identity to v1 --------------------------
EDITING_SERVICE="tour-editing"
EDITING_IMAGE_NAME="tour-editing"
EDITING_DOCKERFILE="Dockerfile.cloudrun"   # same as v1 (COPY *.py bundles editing + blobstorage)
CLOUDSQL_INSTANCE="audiotours-migration:us-central1:audioura-db"
POLLY_TTS_URL="https://polly-tts-60899077572.us-central1.run.app"
# Live R2 endpoint (base URL only; blobstorage strips any bucket path). Same
# value v1 uses — a wrong endpoint must not be shippable.
R2_ENDPOINT="https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com"

# The known-good previous revision to roll back to.
# GCS-SAN1 ships tour-editing:v3; the live known-good image is now GCS-5E's
# tour-editing:v2. Roll back to v2 by tag (Option B redeploys the image and does
# not need the revision suffix). The exact v2 revision name must be confirmed
# against the live service before --apply (it is not hard-coded here to avoid a
# fabricated/stale revision ID):
#   gcloud run revisions list --service tour-editing --region us-central1 \
#     --format='value(metadata.name)' | head
ROLLBACK_TAG="v2"
ROLLBACK_REVISION="<CONFIRM_LIVE_V2_REVISION>"   # e.g. tour-editing-00002-xxx

DRY_RUN=1
EDITING_TAG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ;;
    --apply)       DRY_RUN=0 ;;
    --editing-tag) EDITING_TAG="${2:-}"; shift ;;
    -h|--help)     sed -n '2,60p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# next_tag <image-name> <forced> <dry-default>: highest existing vN + 1
next_tag() {
  local image="$1" forced="$2" dry_default="$3"
  if [ -n "$forced" ]; then echo "$forced"; return; fi
  if [ "$DRY_RUN" = "1" ]; then echo "$dry_default"; return; fi
  local highest
  highest=$(gcloud artifacts docker tags list "${REPO}/${image}" \
    --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
    | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1)
  [ -n "$highest" ] || fail "could not list tags for ${image} — pass --editing-tag"
  echo "v$((highest + 1))"
}

say "Preflight (tour-editing ONLY — no gateway is referenced by this script)"
run "command -v gcloud >/dev/null || { echo 'gcloud not on PATH'; exit 1; }"
run "command -v docker >/dev/null || { echo 'docker not on PATH'; exit 1; }"
run "gcloud auth print-access-token >/dev/null 2>&1 || { echo 'not authenticated'; exit 1; }"
[ -f "$EDITING_DOCKERFILE" ] || fail "$EDITING_DOCKERFILE not found — run from repo root"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
RELEASE_TAG="${RELEASE_TAG:-v3t-gcs-san1}"   # line 2 = storied; override via env if desired
echo "  GIT_SHA=${GIT_SHA}  RELEASE_TAG=${RELEASE_TAG}"

# --------------------------------------------- 1. build + push v2 image ------
ETAG=$(next_tag "$EDITING_IMAGE_NAME" "$EDITING_TAG" "v3")
EDITING_IMAGE="${REPO}/${EDITING_IMAGE_NAME}:${ETAG}"
say "Build + push tour-editing image ${EDITING_IMAGE} (own image, not shared audioura)"
run "docker build -f '${EDITING_DOCKERFILE}' \
  --build-arg GIT_SHA='${GIT_SHA}' --build-arg RELEASE_TAG='${RELEASE_TAG}' \
  -t '${EDITING_IMAGE}' ."
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '${EDITING_IMAGE}'"

# --------------------------------------------- 2. deploy new revision --------
# SAME env/secrets/flags as v1 (copied verbatim from deploy_gcs5_tour_editing.sh
# step 2). One --set-env-vars and one --set-secrets: gcloud KEEPS ONLY THE LAST
# occurrence of a repeated flag, so everything goes in a single flag each.
# `gcloud run deploy` on an EXISTING service creates a new revision and keeps the
# service's service-account and IAM invoker bindings — no gateway change needed.
say "Deploy new tour-editing revision onto ${EDITING_IMAGE} (v1's env/secrets/flags)"
ENV_VARS="TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2"
ENV_VARS="${ENV_VARS},DB_HOST=/cloudsql/${CLOUDSQL_INSTANCE},DB_NAME=audiotours,DB_USER=admin"
ENV_VARS="${ENV_VARS},R2_ENDPOINT=${R2_ENDPOINT},R2_BUCKET=v1-audiotours-r2-bucket"
ENV_VARS="${ENV_VARS},POLLY_TTS_URL=${POLLY_TTS_URL},AWS_DEFAULT_REGION=us-east-1"
SECRETS="DB_PASSWORD=db-password:latest"
SECRETS="${SECRETS},R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest"
SECRETS="${SECRETS},AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest"
echo "  NOTE: confirm secret NAMES against the LIVE v1 service before --apply:"
echo "    gcloud run services describe ${EDITING_SERVICE} --region ${REGION} --format=yaml | grep -iE 'secretKeyRef|name:'"
run "gcloud run deploy '${EDITING_SERVICE}' \
  --project '${PROJECT}' --region '${REGION}' \
  --image '${EDITING_IMAGE}' \
  --command python --args tour_editing_phase2.py \
  --port 5022 --no-allow-unauthenticated \
  --add-cloudsql-instances '${CLOUDSQL_INSTANCE}' \
  --set-env-vars '${ENV_VARS}' \
  --set-secrets '${SECRETS}' \
  --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet"

# ------------------------------------------------------------- rollback ------
say "ROLLBACK (if v3 misbehaves) — route 100% of traffic back to ${ROLLBACK_TAG}"
cat <<EOF

  # Option A: pin traffic to the known-good v2 revision (fastest, no rebuild):
  gcloud run services update-traffic ${EDITING_SERVICE} \\
    --project ${PROJECT} --region ${REGION} \\
    --to-revisions ${ROLLBACK_REVISION}=100 --quiet

  # Option B: redeploy the v2 image (if the revision was pruned):
  gcloud run deploy ${EDITING_SERVICE} \\
    --project ${PROJECT} --region ${REGION} \\
    --image ${REPO}/${EDITING_IMAGE_NAME}:${ROLLBACK_TAG} \\
    --command python --args tour_editing_phase2.py \\
    --port 5022 --no-allow-unauthenticated \\
    --add-cloudsql-instances ${CLOUDSQL_INSTANCE} \\
    --set-env-vars '${ENV_VARS}' \\
    --set-secrets '${SECRETS}' \\
    --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet

  # Neither gateway is involved in deploy OR rollback.
EOF

say "POST-DEPLOY VERIFICATION — run after --apply"
cat <<EOF

  export KEY=\$(gcloud secrets versions access latest --secret=gateway-api-key --project=${PROJECT})
  BASE="https://storied-api.audioura.com"   # Preview gateway (unchanged by this script)

  # Edit a REAL Russian R2-migrated tour (no content_language: server uses the
  # tour's own language). Expect 200 + new_tour_id, then a download whose ZIP
  # contains audio_1.mp3 (> 0 bytes) for the edited stop.
  curl -s -X POST "\$BASE/tour/<REAL_RU_TOUR_ID>/update-multiple-stops" \\
    -H "X-API-Key: \$KEY" -H 'Content-Type: application/json' \\
    --data-binary @edited_ru_body.json     # \u-escaped JSON file (Git Bash mangles raw Cyrillic)
  curl -s -o /tmp/edited.zip -w '  download -> %{http_code} size=%{size_download}\n' \\
    -H "X-API-Key: \$KEY" "\$BASE<download_url>"
  python -c "import zipfile,sys; z=zipfile.ZipFile('/tmp/edited.zip'); \\
    i=z.getinfo('audio_1.mp3'); print('audio_1.mp3', i.file_size, 'bytes'); \\
    sys.exit(0 if i.file_size>0 else 1)"

  # Negative: with Polly unreachable a save MUST fail AUDIO_GENERATION_FAILED
  # (4xx/5xx) and create NO new downloadable tour — never a 200 with a missing MP3.
EOF

[ "$DRY_RUN" = "1" ] && { echo; echo "DRY RUN COMPLETE — nothing was deployed. No gateway referenced."; exit 0; }
say "APPLIED (tour-editing only). Verify by effect using the curls above before calling it done."
