#!/usr/bin/env bash
# GCS-TR1 deploy for translation-service ONLY. Ships the v35 overlay (v35-tr1).
#
# SAFE BY DEFAULT: --dry-run is the default. Nothing is built, pushed or deployed
# unless you pass --apply. Michael is field-testing build 26; LEAD coordinates the
# actual deploy. This script names NO other service.
#
#   Dry run (default):   bash deploy_translation_tr1.sh
#   Real deploy:         bash deploy_translation_tr1.sh --apply
#
# Rollback (printed below, run manually):
#   gcloud run services update translation-service --region us-central1 \
#     --image us-central1-docker.pkg.dev/audiotours-migration/services/translation-service:v35
set -euo pipefail

# --- config (translation-service only) ---
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/audiotours-migration/services"
SERVICE="translation-service"
BASE_TAG="v35"
NEW_TAG="v35-tr1"
BASE_IMAGE="$REPO/$SERVICE:$BASE_TAG"
NEW_IMAGE="$REPO/$SERVICE:$NEW_TAG"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTEXT="$HERE/translation-service"
DOCKERFILE="$CONTEXT/Dockerfile.tr1"

APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

echo "=============================================================="
echo " GCS-TR1 deploy — service: $SERVICE (and no other)"
echo " base image : $BASE_IMAGE"
echo " new image  : $NEW_IMAGE"
echo " dockerfile : $DOCKERFILE   (overlay: COPY translation_service.py /app/)"
echo " context    : $CONTEXT"
echo " mode       : $([ $APPLY -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo "=============================================================="
echo
echo "Build:"
echo "  docker build -f $DOCKERFILE -t $NEW_IMAGE $CONTEXT"
echo "Push:"
echo "  docker push $NEW_IMAGE"
echo "Deploy (image only — no other flags, no other service):"
echo "  gcloud run services update $SERVICE --region $REGION --image $NEW_IMAGE"
echo
echo "Rollback (manual):"
echo "  gcloud run services update $SERVICE --region $REGION --image $BASE_IMAGE"
echo

if [ $APPLY -ne 1 ]; then
  echo "DRY-RUN: no build, no push, no deploy performed. Re-run with --apply to execute."
  exit 0
fi

echo ">>> APPLY: building overlay"
docker build -f "$DOCKERFILE" -t "$NEW_IMAGE" "$CONTEXT"

echo ">>> APPLY: pushing overlay"
docker push "$NEW_IMAGE"

echo ">>> APPLY: updating Cloud Run service image (image only)"
gcloud run services update "$SERVICE" --region "$REGION" --image "$NEW_IMAGE"

echo ">>> Done. Rollback if needed:"
echo "    gcloud run services update $SERVICE --region $REGION --image $BASE_IMAGE"
