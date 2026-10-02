#!/usr/bin/env bash
# =============================================================================
# GCS-5R — Staged deploy for cloud tour editing on the STORIED (Preview) line.
#          Runbook: ClickUp wdvrdaxn9f.
#
# THIS SCRIPT DEPLOYS NOTHING BY DEFAULT. Every mutating gcloud/docker call goes
# through run(), which only PRINTS in dry-run (the default). Deploy is Michael's
# call: pass --apply to actually run.
#
# What it stages, in order:
#   1. Build + push the tour-editing backend as its OWN image
#      (services/tour-editing:<tag>), NOT the shared audioura:vN sequence.
#      GIT_SHA / RELEASE_TAG are baked in as build-args so the running image
#      identifies its commit (GCLOUD_STORIED_START_HERE.md finding 2: the shared
#      tag is a standing hazard for the Beta control).
#   2. CREATE Cloud Run service `tour-editing` (command: tour_editing_phase2.py),
#      port 5022, --no-allow-unauthenticated (only the gateway may call it),
#      Cloud SQL + R2 + AWS + Polly env/secrets.
#   3. BUILD A NEW GATEWAY IMAGE. This is the core B2 fix: the gateway bakes
#      gateway_routes.yaml INTO the image (api-gateway/Dockerfile: COPY main.py
#      gateway_routes.yaml). The deployed api-gateway:v35 has NO editing routes,
#      so merely setting TOUR_EDITING_URL on it still 404s. We pull v35, extract
#      its baked manifest, PROVE the only route delta is the 4 editing routes +
#      tour-editing backend, build api-gateway:<v35+1>, and push it.
#   4. Deploy the PREVIEW gateway (api-gateway-storied) onto the new image and
#      set TOUR_EDITING_URL. Stable (api-gateway) is touched ONLY with --stable
#      (Michael's 2026-09-15 ruling: test on Preview before Stable gets anything).
#   5. Grant the target gateway's SA roles/run.invoker on tour-editing.
#   6. Print the EXACT post-deploy curl verification.
#
# Usage:
#   ./deploy_gcs5_tour_editing.sh --dry-run           # default; prints only
#   ./deploy_gcs5_tour_editing.sh --apply             # deploy Preview (Michael)
#   ./deploy_gcs5_tour_editing.sh --apply --stable    # ALSO deploy Stable
#   ./deploy_gcs5_tour_editing.sh --dry-run --editing-tag v3 --gw-tag v36
# =============================================================================
set -euo pipefail

PROJECT="audiotours-migration"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"

# --- tour-editing backend: its OWN image name (not the shared audioura tag) ---
EDITING_SERVICE="tour-editing"
EDITING_IMAGE_NAME="tour-editing"
EDITING_DOCKERFILE="Dockerfile.cloudrun"   # COPY *.py bundles editing + blobstorage
CLOUDSQL_INSTANCE="audiotours-migration:us-central1:audioura-db"
POLLY_TTS_URL="https://polly-tts-60899077572.us-central1.run.app"
# Live R2 endpoint (base URL only; blobstorage strips any bucket path). This is
# the real value, not a placeholder — a wrong endpoint must not be shippable.
R2_ENDPOINT="https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com"

# --- gateway image (routes are baked in; must rebuild + redeploy) ------------
GATEWAY_IMAGE_NAME="api-gateway"
GATEWAY_DOCKERFILE="api-gateway/Dockerfile"

# Preview is the default target; Stable only with --stable.
PREVIEW_GATEWAY="api-gateway-storied"
STABLE_GATEWAY="api-gateway"
declare -A GATEWAY_DOMAIN=(
  ["api-gateway"]="https://api.audioura.com"
  ["api-gateway-storied"]="https://storied-api.audioura.com"
)

DRY_RUN=1
DO_STABLE=0
EDITING_TAG=""
GW_TAG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     DRY_RUN=1 ;;
    --apply)       DRY_RUN=0 ;;
    --stable)      DO_STABLE=1 ;;
    --editing-tag) EDITING_TAG="${2:-}"; shift ;;
    --gw-tag)      GW_TAG="${2:-}"; shift ;;
    -h|--help)     sed -n '2,52p' "$0"; exit 0 ;;
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
  [ -n "$highest" ] || fail "could not list tags for ${image} — pass a tag flag"
  echo "v$((highest + 1))"
}

say "Preflight"
run "command -v gcloud >/dev/null || { echo 'gcloud not on PATH'; exit 1; }"
run "command -v docker >/dev/null || { echo 'docker not on PATH'; exit 1; }"
run "gcloud auth print-access-token >/dev/null 2>&1 || { echo 'not authenticated'; exit 1; }"
[ -f "$EDITING_DOCKERFILE" ] || fail "$EDITING_DOCKERFILE not found — run from repo root"
[ -f "$GATEWAY_DOCKERFILE" ] || fail "$GATEWAY_DOCKERFILE not found — run from repo root"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
RELEASE_TAG="${RELEASE_TAG:-v2t-gcs5r}"   # line 2 = storied; override via env if desired
echo "  GIT_SHA=${GIT_SHA}  RELEASE_TAG=${RELEASE_TAG}"

TARGET_GATEWAYS=("$PREVIEW_GATEWAY")
if [ "$DO_STABLE" = "1" ]; then TARGET_GATEWAYS+=("$STABLE_GATEWAY"); fi
echo "  Target gateway(s): ${TARGET_GATEWAYS[*]}   (Preview default; Stable only with --stable)"

# ------------------------------------------------- 1. tour-editing image ----
ETAG=$(next_tag "$EDITING_IMAGE_NAME" "$EDITING_TAG" "vNEXT")
EDITING_IMAGE="${REPO}/${EDITING_IMAGE_NAME}:${ETAG}"
say "Build + push tour-editing image ${EDITING_IMAGE} (own image, not shared audioura)"
run "docker build -f '${EDITING_DOCKERFILE}' \
  --build-arg GIT_SHA='${GIT_SHA}' --build-arg RELEASE_TAG='${RELEASE_TAG}' \
  -t '${EDITING_IMAGE}' ."
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '${EDITING_IMAGE}'"

# ------------------------------------------------- 2. create tour-editing ---
# One --set-env-vars (comma-joined) and one --set-secrets: gcloud KEEPS ONLY THE
# LAST occurrence of a repeated flag, so multiple --set-env-vars silently drop
# earlier vars. Everything goes in a single flag each.
say "CREATE Cloud Run service ${EDITING_SERVICE}"
ENV_VARS="TOUR_STORAGE_MODE=cloud,BLOB_STORAGE_TYPE=r2"
ENV_VARS="${ENV_VARS},DB_HOST=/cloudsql/${CLOUDSQL_INSTANCE},DB_NAME=audiotours,DB_USER=admin"
ENV_VARS="${ENV_VARS},R2_ENDPOINT=${R2_ENDPOINT},R2_BUCKET=v1-audiotours-r2-bucket"
ENV_VARS="${ENV_VARS},POLLY_TTS_URL=${POLLY_TTS_URL},AWS_DEFAULT_REGION=us-east-1"
SECRETS="DB_PASSWORD=db-password:latest"
SECRETS="${SECRETS},R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest"
SECRETS="${SECRETS},AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest"
echo "  NOTE: confirm secret NAMES against a live service before --apply:"
echo "    gcloud run services describe tour-orchestrator-storied --region ${REGION} --format=yaml | grep -iE 'secretKeyRef|name:' "
run "gcloud run deploy '${EDITING_SERVICE}' \
  --project '${PROJECT}' --region '${REGION}' \
  --image '${EDITING_IMAGE}' \
  --command python --args tour_editing_phase2.py \
  --port 5022 --no-allow-unauthenticated \
  --add-cloudsql-instances '${CLOUDSQL_INSTANCE}' \
  --set-env-vars '${ENV_VARS}' \
  --set-secrets '${SECRETS}' \
  --cpu 1 --memory 1Gi --timeout 600 --concurrency 20 --max-instances 4 --quiet"

say "Resolve ${EDITING_SERVICE} URL"
if [ "$DRY_RUN" = "1" ]; then
  EDITING_URL="https://tour-editing-60899077572.us-central1.run.app"
  echo "  [dry-run] EDITING_URL (predicted) = ${EDITING_URL}"
else
  EDITING_URL=$(gcloud run services describe "${EDITING_SERVICE}" --region "${REGION}" --format="value(status.url)")
  echo "  EDITING_URL = ${EDITING_URL}"
fi

# ------------------------------------- 3. new gateway image (route-baked) ----
# GCS-5R2 core fix. The deployed api-gateway:v35 runs a SPECIFIC main.py. The
# storied tree's api-gateway/main.py has DIVERGED from it (LEAD: 54 insertions,
# 29 deletions — attestation rewrite that imports attestation_verifier, a
# sys.path hack, ATTESTATION_MODE/PLAY_INTEGRITY_API_KEY/APP_* env, extra
# /health fields). Building the gateway image from the storied tree (the old
# `docker build ... api-gateway`) would therefore change attestation handling on
# every cost-bearing route — on Preview now and Stable later. That is NOT "v35 +
# 4 routes". GCS-5R's proof only diffed the YAML, so it missed this.
#
# Correct image = v35's EXACT main.py + v35's EXACT Dockerfile + this branch's
# gateway_routes.yaml (which is v35's YAML + exactly the 4 editing routes). LEAD
# verified origin/main:api-gateway/main.py and :Dockerfile are identical to the
# v35 image's (only a line-1 BOM their export added), so we stage from
# origin/main and PROVE byte-identity against the image before building.
#
# The read-only proof (pull v35, extract /app/main.py + /app/gateway_routes.yaml,
# SHA256 + route_diff) runs in BOTH --dry-run and --apply: pulling is allowed,
# only build/push are gated. --apply ABORTS if either check fails.
say "Stage gateway build context from origin/main (v35 code) + this branch's routes"
V35_IMAGE="${REPO}/${GATEWAY_IMAGE_NAME}:v35"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
# v35's code and Dockerfile come from origin/main (NOT the storied working tree).
git show origin/main:api-gateway/main.py    > "${STAGE_DIR}/main.py"    || fail "cannot read origin/main:api-gateway/main.py"
git show origin/main:api-gateway/Dockerfile > "${STAGE_DIR}/Dockerfile" || fail "cannot read origin/main:api-gateway/Dockerfile"
# The routes are the ONLY intended change: v35 YAML + the 4 editing routes.
cp api-gateway/gateway_routes.yaml "${STAGE_DIR}/gateway_routes.yaml"    || fail "cannot stage gateway_routes.yaml"
echo "  Staged context: ${STAGE_DIR}"
echo "    main.py            <- git origin/main:api-gateway/main.py"
echo "    Dockerfile         <- git origin/main:api-gateway/Dockerfile"
echo "    gateway_routes.yaml<- api-gateway/gateway_routes.yaml (this branch)"

say "PROVE the staged main.py is byte-identical to the running v35 image (read-only)"
# These run in dry-run too — a read-only pull + extract, no mutation.
docker pull "${V35_IMAGE}" || fail "docker pull ${V35_IMAGE} failed (read-only)"
V35CID="$(docker create "${V35_IMAGE}")" || fail "docker create ${V35_IMAGE} failed"
docker cp "${V35CID}:/app/main.py"            "${STAGE_DIR}/v35_main.py" || fail "extract /app/main.py from v35 failed"
docker cp "${V35CID}:/app/gateway_routes.yaml" "${STAGE_DIR}/v35_routes.yaml" || fail "extract /app/gateway_routes.yaml from v35 failed"
docker rm "${V35CID}" >/dev/null || true
python api-gateway/main_sha_check.py "${STAGE_DIR}/main.py" "${STAGE_DIR}/v35_main.py" \
  || fail "staged main.py is NOT byte-identical to the v35 image main.py — refusing to build"

say "PROVE the route delta is exactly +4 editing routes +1 backend (read-only)"
python api-gateway/route_diff.py "${STAGE_DIR}/v35_routes.yaml" "${STAGE_DIR}/gateway_routes.yaml" \
  || fail "route delta is not exactly the 4 editing routes + tour-editing backend"

say "PROVE the editing-route test passes against the STAGED main.py (v35 code), not storied's"
# test_editing_routes.py imports 'main' and reads gateway_routes.yaml from its
# OWN directory, so copy it into the staged context and run it there: this
# exercises v35's main.py + this branch's routes, exactly what ships.
cp api-gateway/test_editing_routes.py "${STAGE_DIR}/test_editing_routes.py" || fail "cannot stage test_editing_routes.py"
( cd "${STAGE_DIR}" && python test_editing_routes.py ) \
  || fail "test_editing_routes.py failed against the staged (v35) context"

GWTAG=$(next_tag "$GATEWAY_IMAGE_NAME" "$GW_TAG" "v36")   # v35 + 1
GATEWAY_IMAGE="${REPO}/${GATEWAY_IMAGE_NAME}:${GWTAG}"
say "Build + push NEW gateway image ${GATEWAY_IMAGE} (v35 code + Dockerfile + the 4 routes)"
# Build from the STAGED context (v35's main.py/Dockerfile), NOT the storied tree.
run "docker build -f '${STAGE_DIR}/Dockerfile' -t '${GATEWAY_IMAGE}' '${STAGE_DIR}'"
run "docker push '${GATEWAY_IMAGE}'"

# ---------------------------------------- 4/5. deploy + wire target gateways -
for GW in "${TARGET_GATEWAYS[@]}"; do
  say "Deploy gateway ${GW} onto ${GATEWAY_IMAGE} + set TOUR_EDITING_URL"
  if [ "$DRY_RUN" = "1" ]; then
    GW_SA="<service-account of ${GW}>"
    echo "  [dry-run] GW_SA from: gcloud run services describe ${GW} --region ${REGION} --format='value(spec.template.spec.serviceAccountName)'"
  else
    GW_SA=$(gcloud run services describe "${GW}" --region "${REGION}" \
      --format="value(spec.template.spec.serviceAccountName)")
    [ -n "$GW_SA" ] || fail "could not read service account for ${GW}"
    echo "  GW_SA = ${GW_SA}"
  fi

  # Let this gateway invoke tour-editing (identity-token auth, like other backends).
  run "gcloud run services add-iam-policy-binding '${EDITING_SERVICE}' \
    --project '${PROJECT}' --region '${REGION}' \
    --member 'serviceAccount:${GW_SA}' --role 'roles/run.invoker' --quiet"

  # Deploy the NEW image AND set the backend URL in one update. Deploying the
  # image is what actually ships the routes; the env var points them at the
  # backend. (Doing only --update-env-vars on v35 was the B2 bug: still 404.)
  run "gcloud run services update '${GW}' \
    --project '${PROJECT}' --region '${REGION}' \
    --image '${GATEWAY_IMAGE}' \
    --update-env-vars 'TOUR_EDITING_URL=${EDITING_URL}' --quiet"
done

# ---------------------------------------------------------------- verify ----
say "POST-DEPLOY VERIFICATION — run after --apply"
PRIMARY_DOMAIN="${GATEWAY_DOMAIN[$PREVIEW_GATEWAY]}"
cat <<EOF

  export KEY=\$(gcloud secrets versions access latest --secret=gateway-api-key --project=${PROJECT})
  BASE="${PRIMARY_DOMAIN}"     # Preview first (Stable only if you passed --stable)

  # 1) No key -> MUST be 401 (fail-closed), NOT 404 (route now baked into image)
  curl -s -o /dev/null -w '  no-key update-multiple-stops -> %{http_code} (expect 401)\n' \\
    -X POST "\$BASE/tour/1/update-multiple-stops" -H 'Content-Type: application/json' -d '{}'

  # 2) With key -> real save on a REAL Russian R2-migrated tour id (no content_language:
  #    the server must pick the tour's own language). Expect 200 + new_tour_id.
  curl -s -X POST "\$BASE/tour/<REAL_RU_TOUR_ID>/update-multiple-stops" \\
    -H "X-API-Key: \$KEY" -H 'Content-Type: application/json' \\
    -d '{"stops":[{"stop_number":1,"text":"<edited russian text>","action":"modify","generate_audio_from_text":true}]}'

  # 3) Download the edited tour (expect 200 + valid ZIP with the edited text)
  curl -s -o /tmp/edited.zip -w '  download -> %{http_code} size=%{size_download}\n' \\
    -H "X-API-Key: \$KEY" "\$BASE<download_url>"

  # 4) update-stop + job-status reachability (expect 401 without key, not 404)
  curl -s -o /dev/null -w '  no-key update-stop -> %{http_code} (expect 401)\n' \\
    -X POST "\$BASE/tour/1/update-stop" -H 'Content-Type: application/json' -d '{}'
  curl -s -o /dev/null -w '  no-key job-status -> %{http_code} (expect 401)\n' \\
    "\$BASE/tour/1/job-status/x"

  # 5) Deploy-gate lock test against the Preview gateway:
  #   GATEWAY_BASE_URL=${PRIMARY_DOMAIN} python api-gateway/test_route_lock.py --key \$KEY
EOF

[ "$DRY_RUN" = "1" ] && { echo; echo "DRY RUN COMPLETE — nothing was deployed."; exit 0; }
say "APPLIED. Verify by effect using the curls above before calling it done."
