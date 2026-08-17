#!/usr/bin/env bash
# Deploy tour-modernized (the tour HTML builder) to Cloud Run.
#
# WHY THIS SCRIPT EXISTS
# There was no runbook for updating a single Cloud Run service. The procedure had
# to be reconstructed on 2026-08-17, and two details are easy to get wrong and
# expensive to discover later:
#
#   1. --no-cpu-throttling is REQUIRED. Without it the tour-generation daemon
#      thread is starved once the HTTP response returns, and generation silently
#      never finishes. This was diagnosed and fixed once already
#      (remind_Services_ai.md:217) — do not lose it again.
#   2. --max-instances=1 is REQUIRED. Job state is in-memory, so a second
#      instance cannot answer /status/<job_id> for a job the first one owns.
#
#   gcloud run deploy preserves unspecified settings, but they are passed
#   explicitly here so the intent survives even if someone edits this file.
#
# SAFETY
#   - Every service pins its own image tag, so a new tag touches ONLY this
#     service. Other services keep theirs (tour-generator:v15, polly-tts:v3, ...).
#   - The previous tag is never overwritten, so rollback is instant.
#   - Only NEWLY generated tours are affected. Tours already on a device keep the
#     HTML they shipped with.
#
# USAGE
#   ./deploy_tour_modernized.sh                 # deploy next tag
#   ./deploy_tour_modernized.sh --dry-run       # print what would happen
#   ./deploy_tour_modernized.sh --tag v12       # deploy a specific tag
#   ./deploy_tour_modernized.sh --rollback      # revert to previous revision
#
# Requires: gcloud (authenticated), docker, and amd64 build host.

set -euo pipefail

PROJECT="audiotours-migration"
REGION="us-central1"
SERVICE="tour-modernized"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"
IMAGE_NAME="audioura"
DOCKERFILE="Dockerfile.cloudrun"

# Runtime config — see the WHY block above before changing any of these.
CPU="2"
MEMORY="1Gi"
CONCURRENCY="5"
TIMEOUT="300"
MAX_INSTANCES="1"

DRY_RUN=0
FORCED_TAG=""
ROLLBACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  DRY_RUN=1 ;;
    --tag)      FORCED_TAG="${2:-}"; shift ;;
    --rollback) ROLLBACK=1 ;;
    -h|--help)  sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- rollback ---
if [ "$ROLLBACK" = "1" ]; then
  say "Rollback: available revisions for ${SERVICE}"
  gcloud run revisions list --service "$SERVICE" --region "$REGION" \
    --format="table(metadata.name,metadata.creationTimestamp,spec.containers[0].image)" --limit 5
  prev=$(gcloud run revisions list --service "$SERVICE" --region "$REGION" \
    --format="value(metadata.name)" --sort-by="~metadata.creationTimestamp" --limit 2 | tail -1)
  [ -n "$prev" ] || fail "could not determine previous revision"
  say "Routing 100% of traffic to ${prev}"
  run "gcloud run services update-traffic '$SERVICE' --region '$REGION' --to-revisions '${prev}=100'"
  exit 0
fi

# ------------------------------------------------------------ preflight -----
say "Preflight"
command -v gcloud >/dev/null || fail "gcloud not on PATH"
command -v docker >/dev/null || fail "docker not on PATH"
gcloud auth print-access-token >/dev/null 2>&1 || fail "gcloud not authenticated — run: gcloud auth login"
[ -f "$DOCKERFILE" ] || fail "$DOCKERFILE not found — run this from the repo root"
echo "  project=${PROJECT} region=${REGION} service=${SERVICE}"

# The fix this script was first written to ship. Guards against deploying an
# image built from a tree where the generator regressed.
if ! grep -q "otherAudio.pause()" tour_generation_modernized.py; then
  fail "tour_generation_modernized.py has no pause-others logic in the play listener.
       Deploying would ship the concurrent-audio bug (BETA-1, wdvrdaxmq2).
       Check you are on a branch that contains the fix."
fi
echo "  concurrent-audio fix present in source: OK"

# ------------------------------------------------------------ pick a tag ----
say "Choosing image tag"
CURRENT_IMAGE=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].image)" 2>/dev/null || true)
echo "  currently deployed: ${CURRENT_IMAGE:-<none>}"

if [ -n "$FORCED_TAG" ]; then
  TAG="$FORCED_TAG"
else
  # The vN tag sequence is SHARED across every service using this image — it is
  # not per-service. tour-modernized sat on v8 while v31 already existed, so
  # "current + 1" would collide. Always take the registry's highest + 1.
  highest=$(gcloud artifacts docker tags list "${REPO}/${IMAGE_NAME}" \
    --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
    | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1)
  [ -n "$highest" ] || fail "could not list existing tags — pass --tag explicitly"
  TAG="v$((highest + 1))"
  echo "  highest existing tag in registry: v${highest} (shared across services)"
fi
FULL_IMAGE="${REPO}/${IMAGE_NAME}:${TAG}"
echo "  will build and deploy: ${FULL_IMAGE}"

if gcloud artifacts docker images describe "$FULL_IMAGE" >/dev/null 2>&1; then
  fail "${FULL_IMAGE} already exists. Never overwrite a tag — rollback depends on
       old tags staying immutable. Pass a different --tag."
fi

# ------------------------------------------------------------ build/push ----
say "Building ${FULL_IMAGE} from ${DOCKERFILE}"
# Dockerfile.cloudrun does COPY *.py — it bundles every module, which is why the
# cloud works while the per-service Dockerfiles omit imported siblings (see
# ClickUp wdvrdaxn8y). Build once, deploy many, one CMD per service.
run "docker build -f '$DOCKERFILE' -t '$FULL_IMAGE' ."

say "Pushing to Artifact Registry"
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '$FULL_IMAGE'"

# ---------------------------------------------------------------- deploy ----
say "Deploying ${SERVICE}"
run "gcloud run deploy '$SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --no-cpu-throttling \
  --max-instances='$MAX_INSTANCES' \
  --concurrency='$CONCURRENCY' \
  --cpu='$CPU' \
  --memory='$MEMORY' \
  --timeout='$TIMEOUT' \
  --quiet"

[ "$DRY_RUN" = "1" ] && { echo; echo "dry run complete — nothing changed"; exit 0; }

# ---------------------------------------------------------------- verify ----
# "Containers are the source of truth for deployed code" (remind_Services_ai.md:40).
# Verify by effect, never by exit code — docker-compose build has been observed
# exiting 0 while actually failing.
say "Verifying deployment"

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)")
TOKEN=$(gcloud auth print-identity-token)
HEALTH=$(curl -s -m 30 -H "Authorization: Bearer $TOKEN" "${URL}/health" || true)
echo "  /health -> ${HEALTH:-<no response>}"
printf '%s' "$HEALTH" | grep -q '"status":"healthy"' || fail "service did not report healthy — roll back with: $0 --rollback"

echo "  checking the deployed image actually contains the fix..."
if docker run --rm --entrypoint sh "$FULL_IMAGE" -c \
     "grep -A4 \"addEventListener('play'\" /app/tour_generation_modernized.py" | grep -q "otherAudio.pause()"; then
  echo "  deployed image contains the pause-others fix: OK"
else
  fail "deployed image does NOT contain the fix — roll back with: $0 --rollback"
fi

REV=$(gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(status.traffic[0].revisionName)")

say "Done"
cat <<EOF
  service   : ${SERVICE}
  image     : ${FULL_IMAGE}
  revision  : ${REV}
  previous  : ${CURRENT_IMAGE}

  Only NEWLY generated tours are affected. Existing tours on a device keep the
  HTML they shipped with, so retesting an old tour will look like a failure.

  Roll back with:
    $0 --rollback
EOF
