#!/usr/bin/env bash
# Deploy ANY Audioura service to Cloud Run, preserving its current runtime config.
#
# Companion to deploy_tour_modernized.sh (which hard-codes tour-modernized's
# settings). Use this one for every other service.
#
# WHAT IT DOES DIFFERENTLY
# It reads the service's live config first and re-applies it, so per-service
# tuning is never silently lost. That matters because at least one setting is
# load-bearing and non-obvious:
#
#   --no-cpu-throttling on tour-modernized and tour-orchestrator.
#   Without it the generation daemon thread is starved once the HTTP response
#   returns and tours never finish (remind_Services_ai.md:217).
#
# TAGS ARE A SHARED SEQUENCE
# All services share the `audioura` image and its vN tag sequence — the tag is
# NOT per-service. tour-modernized sat on v8 while v31 already existed. Always
# take the registry's highest + 1, never "this service's tag + 1". Tags are
# immutable here: rollback depends on old tags still pointing at old code.
#
# BUILD ONCE, DEPLOY MANY
# Dockerfile.cloudrun does `COPY *.py`, bundling every module. The per-service
# Dockerfiles copy a single .py and silently omit imported siblings — which is
# why several of them cannot produce a working container at all
# (see ClickUp wdvrdaxn8y). Prefer this image.
#
# USAGE
#   ./deploy_cloudrun_service.sh tour-orchestrator
#   ./deploy_cloudrun_service.sh news-generator --dry-run
#   ./deploy_cloudrun_service.sh coordinates --tag v40
#   ./deploy_cloudrun_service.sh tour-generator --rollback
#
# NOTE the translation-service uses its OWN image repo
# (services/translation-service), not `audioura` — pass --repo-image
# translation-service for it.

set -euo pipefail

# Release tagging: every deploy is pinned to a pushed git tag so the deployed
# source can be reconstituted exactly. See release_tag.sh for why a commit count
# could not do this.
. "$(dirname "$0")/release_tag.sh"

PROJECT="audiotours-migration"
REGION="us-central1"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"
IMAGE_NAME="audioura"
DOCKERFILE="Dockerfile.cloudrun"

SERVICE=""
DRY_RUN=0
FORCED_TAG=""
ROLLBACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)    DRY_RUN=1 ;;
    --tag)        FORCED_TAG="${2:-}"; shift ;;
    --rollback)   ROLLBACK=1 ;;
    --repo-image) IMAGE_NAME="${2:-}"; shift ;;
    -h|--help)    sed -n '2,40p' "$0"; exit 0 ;;
    -*)           echo "unknown flag: $1" >&2; exit 2 ;;
    *)            SERVICE="$1" ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[ -n "$SERVICE" ] || fail "no service given. Example: $0 tour-orchestrator"

# ---------------------------------------------------------------- rollback ---
if [ "$ROLLBACK" = "1" ]; then
  say "Rollback: revisions for ${SERVICE}"
  gcloud run revisions list --service "$SERVICE" --region "$REGION" \
    --format="table(metadata.name,metadata.creationTimestamp,spec.containers[0].image)" --limit 5
  prev=$(gcloud run revisions list --service "$SERVICE" --region "$REGION" \
    --format="value(metadata.name)" --sort-by="~metadata.creationTimestamp" --limit 2 | tail -1)
  [ -n "$prev" ] || fail "could not determine previous revision"
  say "Routing 100% of traffic to ${prev}"
  run "gcloud run services update-traffic '$SERVICE' --region '$REGION' --to-revisions '${prev}=100'"
  exit 0
fi

# ------------------------------------------------------------- preflight ----
say "Preflight"
command -v gcloud >/dev/null || fail "gcloud not on PATH"
command -v docker >/dev/null || fail "docker not on PATH"
gcloud auth print-access-token >/dev/null 2>&1 || fail "gcloud not authenticated"
[ -f "$DOCKERFILE" ] || fail "$DOCKERFILE not found — run from the repo root"

gcloud run services describe "$SERVICE" --region "$REGION" >/dev/null 2>&1 \
  || fail "no Cloud Run service named '${SERVICE}' in ${REGION}"

# --------------------------------------------- capture live configuration ---
say "Reading current config for ${SERVICE}"
CURRENT_IMAGE=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].image)")
CPU=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].resources.limits.cpu)")
MEMORY=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].resources.limits.memory)")
CONCURRENCY=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containerConcurrency)")
TIMEOUT=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.timeoutSeconds)")
MAXSCALE=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])")
THROTTLING=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.metadata.annotations['run.googleapis.com/cpu-throttling'])")

printf '  image=%s\n  cpu=%s memory=%s concurrency=%s timeout=%s maxScale=%s cpu-throttling=%s\n' \
  "$CURRENT_IMAGE" "$CPU" "$MEMORY" "$CONCURRENCY" "$TIMEOUT" "${MAXSCALE:-<unset>}" "${THROTTLING:-<unset>}"

THROTTLE_FLAG="--cpu-throttling"
if [ "$THROTTLING" = "false" ]; then
  THROTTLE_FLAG="--no-cpu-throttling"
  echo "  NOTE: this service runs with CPU throttling DISABLED — preserving it."
fi

# ------------------------------------------------------------- pick a tag ---
say "Choosing image tag"
if [ -n "$FORCED_TAG" ]; then
  TAG="$FORCED_TAG"
else
  highest=$(gcloud artifacts docker tags list "${REPO}/${IMAGE_NAME}" \
    --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
    | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1)
  [ -n "$highest" ] || fail "could not list tags for ${REPO}/${IMAGE_NAME} — pass --tag"
  TAG="v$((highest + 1))"
  echo "  highest existing tag: v${highest} (shared across services) -> using ${TAG}"
fi
FULL_IMAGE="${REPO}/${IMAGE_NAME}:${TAG}"

gcloud artifacts docker images describe "$FULL_IMAGE" >/dev/null 2>&1 \
  && fail "${FULL_IMAGE} already exists — tags are immutable, pass a different --tag"

# ------------------------------------------------------------- build/push ---
# --- release tag -------------------------------------------------------------
BRANCH=$(git rev-parse --abbrev-ref HEAD)
RELEASE_LINE=$(release_line_for_branch "$BRANCH")
if [ -z "$RELEASE_LINE" ]; then
  fail "no release line mapped for branch '$BRANCH'. Deploys must come from
       main (1), storied (2) or subscribed (3) — see release_tag.sh."
fi
assert_image_content_clean || exit 1
RELEASE_TAG=$(next_release_tag "$RELEASE_LINE")
DEPLOY_COMMIT=$(git rev-parse HEAD)
echo "  release tag: ${RELEASE_TAG}  (line ${RELEASE_LINE}, branch ${BRANCH}, commit ${DEPLOY_COMMIT:0:8})"

say "Building ${FULL_IMAGE}"
run "docker build -f '$DOCKERFILE' -t '$FULL_IMAGE' --build-arg RELEASE_TAG='$RELEASE_TAG' --build-arg GIT_SHA='$DEPLOY_COMMIT' ."
say "Pushing"
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '$FULL_IMAGE'"

# ---------------------------------------------------------------- deploy ----
say "Deploying ${SERVICE} (preserving captured config)"
DEPLOY="gcloud run deploy '$SERVICE' --region '$REGION' --image '$FULL_IMAGE' ${THROTTLE_FLAG} --quiet"
[ -n "$CPU" ]         && DEPLOY="$DEPLOY --cpu='$CPU'"
[ -n "$MEMORY" ]      && DEPLOY="$DEPLOY --memory='$MEMORY'"
[ -n "$CONCURRENCY" ] && DEPLOY="$DEPLOY --concurrency='$CONCURRENCY'"
[ -n "$TIMEOUT" ]     && DEPLOY="$DEPLOY --timeout='$TIMEOUT'"
[ -n "$MAXSCALE" ]    && DEPLOY="$DEPLOY --max-instances='$MAXSCALE'"
run "$DEPLOY"

[ "$DRY_RUN" = "1" ] && { echo; echo "dry run complete — nothing changed"; exit 0; }

# ---------------------------------------------------------------- verify ----
# Verify by effect. Never trust an exit code alone — docker-compose build has
# been observed exiting 0 while actually failing.
say "Verifying"
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")
TOKEN=$(gcloud auth print-identity-token)
HEALTH=$(curl -s -m 30 -H "Authorization: Bearer $TOKEN" "${URL}/health" || true)
echo "  /health -> ${HEALTH:-<no response>}"
printf '%s' "$HEALTH" | grep -q 'healthy' \
  || fail "did not report healthy — roll back with: $0 $SERVICE --rollback"

REV=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(status.traffic[0].revisionName)")
# Tag only AFTER a verified deploy. Tagging first would leave a tag pointing at
# something that never shipped.
if create_and_push_release_tag "$RELEASE_TAG" "$DEPLOY_COMMIT" "$SERVICE" "$FULL_IMAGE"; then
  echo "  tagged and pushed: $RELEASE_TAG -> ${DEPLOY_COMMIT:0:8}"
else
  echo "  WARNING: deploy succeeded but tagging did not — reconstitution is not guaranteed" >&2
fi

say "Done"
cat <<EOF
  service  : ${SERVICE}
  image    : ${FULL_IMAGE}
  revision : ${REV}
  previous : ${CURRENT_IMAGE}

  Roll back with:
    $0 ${SERVICE} --rollback
EOF
