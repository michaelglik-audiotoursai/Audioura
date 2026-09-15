#!/usr/bin/env bash
# =============================================================================
# GCS-5 — Staged deploy for the NEW `tour-editing` Cloud Run service + wiring
#         both API gateways to it. Runbook: ClickUp wdvrdaxn9f.
#
# THIS SCRIPT DEPLOYS NOTHING BY DEFAULT. Every mutating gcloud call goes
# through run(), which only PRINTS in --dry-run mode (the default here is to
# require an explicit --apply to actually run). Deploy is Michael's call.
#
# What it stages, in order:
#   1. Build + push the shared `audioura` image from main (Dockerfile.cloudrun,
#      COPY *.py — bundles tour_editing_phase2.py and blobstorage.py).
#   2. CREATE Cloud Run service `tour-editing` (command: tour_editing_phase2.py)
#      with the runtime config copied from tour-orchestrator-storied /
#      tour-modernized (Cloud SQL, R2, AWS, Polly), port 5022, --no-allow-
#      unauthenticated (only the gateways may call it).
#   3. Grant each gateway's service account roles/run.invoker on tour-editing.
#   4. Wire BOTH gateways (api-gateway and api-gateway-storied) by setting
#      TOUR_EDITING_URL to the new service URL (they read gateway_routes.yaml
#      which already has the `tour-editing` backend defaulting to that URL).
#   5. Print the EXACT post-deploy curl verification for BOTH domains.
#
# Usage:
#   ./deploy_gcs5_tour_editing.sh --dry-run     # default; prints only
#   ./deploy_gcs5_tour_editing.sh --apply       # actually deploy (Michael only)
#   ./deploy_gcs5_tour_editing.sh --dry-run --tag v42
# =============================================================================
set -euo pipefail

PROJECT="audiotours-migration"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"
IMAGE_NAME="audioura"
DOCKERFILE="Dockerfile.cloudrun"

SERVICE="tour-editing"
CLOUDSQL_INSTANCE="audiotours-migration:us-central1:audioura-db"
POLLY_TTS_URL="https://polly-tts-60899077572.us-central1.run.app"

# Both gateway services that must learn about the new backend.
GATEWAYS=("api-gateway" "api-gateway-storied")

# Public domains fronting each gateway (for the verification curls).
declare -A GATEWAY_DOMAIN=(
  ["api-gateway"]="https://api.audioura.com"
  ["api-gateway-storied"]="https://storied-api.audioura.com"
)

DRY_RUN=1          # default: stage only
FORCED_TAG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --apply)   DRY_RUN=0 ;;
    --tag)     FORCED_TAG="${2:-}"; shift ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
cap()  { if [ "$DRY_RUN" = "1" ]; then printf '<%s>' "$1"; else eval "$2"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

say "Preflight"
run "command -v gcloud >/dev/null || { echo 'gcloud not on PATH'; exit 1; }"
run "command -v docker >/dev/null || { echo 'docker not on PATH'; exit 1; }"
run "gcloud auth print-access-token >/dev/null 2>&1 || { echo 'not authenticated'; exit 1; }"
[ -f "$DOCKERFILE" ] || fail "$DOCKERFILE not found — run from repo root"

# ---------------------------------------------------------------- tag -------
say "Choosing image tag (shared audioura sequence — highest + 1)"
if [ -n "$FORCED_TAG" ]; then
  TAG="$FORCED_TAG"
else
  if [ "$DRY_RUN" = "1" ]; then
    TAG="vNEXT"   # resolved at apply time from the registry
    echo "  [dry-run] tag will be (highest existing vN)+1 at apply time"
  else
    highest=$(gcloud artifacts docker tags list "${REPO}/${IMAGE_NAME}" \
      --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
      | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1)
    [ -n "$highest" ] || fail "could not list tags — pass --tag"
    TAG="v$((highest + 1))"
    echo "  highest existing: v${highest} -> using ${TAG}"
  fi
fi
FULL_IMAGE="${REPO}/${IMAGE_NAME}:${TAG}"

# ---------------------------------------------------------- build / push ----
say "Build + push shared image ${FULL_IMAGE} (from main)"
run "docker build -f '$DOCKERFILE' -t '$FULL_IMAGE' ."
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '$FULL_IMAGE'"

# ------------------------------------------------- create tour-editing ------
# Secrets mirror the live services (db-password, R2 + AWS). Env values copied
# from tour-orchestrator-storied / tour-modernized describe output (ticket).
say "CREATE Cloud Run service ${SERVICE}"
DEPLOY="gcloud run deploy '${SERVICE}' \
  --project '${PROJECT}' --region '${REGION}' \
  --image '${FULL_IMAGE}' \
  --command 'python' --args 'tour_editing_phase2.py' \
  --port 5022 \
  --no-allow-unauthenticated \
  --add-cloudsql-instances '${CLOUDSQL_INSTANCE}' \
  --set-env-vars 'TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2' \
  --set-env-vars 'DB_HOST=/cloudsql/${CLOUDSQL_INSTANCE},DB_NAME=audiotours,DB_USER=admin' \
  --set-env-vars 'R2_ENDPOINT=REPLACE_WITH_R2_ENDPOINT,R2_BUCKET=v1-audiotours-r2-bucket' \
  --set-env-vars 'POLLY_TTS_URL=${POLLY_TTS_URL}' \
  --set-env-vars 'AWS_DEFAULT_REGION=us-east-1' \
  --set-secrets 'DB_PASSWORD=db-password:latest' \
  --set-secrets 'R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest' \
  --set-secrets 'AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest' \
  --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 \
  --quiet"
echo "  NOTE: confirm the exact R2_ENDPOINT and secret NAMES against a live"
echo "        service before --apply:  gcloud run services describe tour-orchestrator-storied --region ${REGION} --format=yaml | grep -A2 -iE 'R2_ENDPOINT|secretKeyRef'"
run "$DEPLOY"

say "Resolve ${SERVICE} URL"
if [ "$DRY_RUN" = "1" ]; then
  EDITING_URL="https://tour-editing-60899077572.us-central1.run.app"
  echo "  [dry-run] EDITING_URL (predicted) = ${EDITING_URL}"
else
  EDITING_URL=$(gcloud run services describe "${SERVICE}" --region "${REGION}" --format="value(status.url)")
  echo "  EDITING_URL = ${EDITING_URL}"
fi

# --------------------------------------- grant invoker + wire gateways ------
for GW in "${GATEWAYS[@]}"; do
  say "Wiring gateway: ${GW}"
  if [ "$DRY_RUN" = "1" ]; then
    GW_SA="<service-account of ${GW}>"
    echo "  [dry-run] GW_SA = (from: gcloud run services describe ${GW} --region ${REGION} --format='value(spec.template.spec.serviceAccountName)')"
  else
    GW_SA=$(gcloud run services describe "${GW}" --region "${REGION}" \
      --format="value(spec.template.spec.serviceAccountName)")
    [ -n "$GW_SA" ] || fail "could not read service account for ${GW}"
    echo "  GW_SA = ${GW_SA}"
  fi

  # 1) let this gateway invoke tour-editing (identity-token auth, like other backends)
  run "gcloud run services add-iam-policy-binding '${SERVICE}' \
    --project '${PROJECT}' --region '${REGION}' \
    --member 'serviceAccount:${GW_SA}' \
    --role 'roles/run.invoker' --quiet"

  # 2) point the gateway at the new backend (YAML already has the route+backend key)
  run "gcloud run services update '${GW}' \
    --project '${PROJECT}' --region '${REGION}' \
    --update-env-vars 'TOUR_EDITING_URL=${EDITING_URL}' --quiet"
done

# ---------------------------------------------------------------- verify ----
say "POST-DEPLOY VERIFICATION — run these after --apply"
cat <<EOF

  # Requires the gateway API key:
  #   export KEY=\$(gcloud secrets versions access latest --secret=gateway-api-key --project=${PROJECT})

  for BASE in ${GATEWAY_DOMAIN[api-gateway]} ${GATEWAY_DOMAIN[api-gateway-storied]}; do
    echo "== \$BASE =="

    # 1) No key -> MUST be 401 (fail-closed), NOT 404 (route now exists)
    curl -s -o /dev/null -w '  no-key   update-multiple-stops -> %{http_code} (expect 401)\n' \\
      -X POST "\$BASE/tour/1/update-multiple-stops" -H 'Content-Type: application/json' -d '{}'

    # 2) With key -> a real save (expect 200 + new_tour_id; use a real R2-migrated tour id)
    curl -s -X POST "\$BASE/tour/<REAL_TOUR_ID>/update-multiple-stops" \\
      -H "X-API-Key: \$KEY" -H 'Content-Type: application/json' \\
      -d '{"content_language":"en","stops":[{"stop_number":1,"text":"deploy smoke test","action":"modify","generate_audio_from_text":true}]}'
    #   -> capture new_tour_id + download_url from the JSON

    # 3) Download the edited tour (expect 200 + a valid ZIP)
    curl -s -o /tmp/edited.zip -w '  download -> %{http_code} size=%{size_download}\n' \\
      -H "X-API-Key: \$KEY" "\$BASE<download_url>"

    # 4) update-stop + job-status reachability
    curl -s -o /dev/null -w '  no-key   update-stop -> %{http_code} (expect 401)\n' \\
      -X POST "\$BASE/tour/1/update-stop" -H 'Content-Type: application/json' -d '{}'
    curl -s -o /dev/null -w '  no-key   job-status  -> %{http_code} (expect 401)\n' \\
      "\$BASE/tour/1/job-status/x"
  done

  # Then re-run the deploy-gate lock test against BOTH gateways:
  #   GATEWAY_BASE_URL=${GATEWAY_DOMAIN[api-gateway]}         python api-gateway/test_route_lock.py --key \$KEY
  #   GATEWAY_BASE_URL=${GATEWAY_DOMAIN[api-gateway-storied]} python api-gateway/test_route_lock.py --key \$KEY
EOF

[ "$DRY_RUN" = "1" ] && { echo; echo "DRY RUN COMPLETE — nothing was deployed."; exit 0; }
say "APPLIED. Verify by effect using the curls above before calling it done."
