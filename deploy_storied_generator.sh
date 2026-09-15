#!/usr/bin/env bash
# Stage the STORIED tour-GENERATOR deploy so approval is one reviewed command.
#
# WHY THIS SCRIPT EXISTS (ClickUp wdvrdaxxm9, Phase 2 — GCS-3)
# Preview has never run Storied generation code. Verified end to end 2026-09-15
# (PREVIEW_IS_RUNNING_BETA_CODE.md). The chain today:
#
#   storied-api -> api-gateway-storied      (api-gateway:v35, from MAIN)
#              -> tour-orchestrator-storied (audioura:storied, TOUR_TRACK=storied)
#                 TOUR_GENERATOR_URL -> tour-generator            <-- BETA's service
#                 MODERNIZED_URL     -> tour-modernized           <-- BETA's service
#              -> tour-generator            (audioura:v36, generate_tour_text.py == main)
#
# tour_orchestrator_service.py:671 POSTs to TOUR_GENERATOR_URL/generate and :769
# POSTs to MODERNIZED_URL/process. The orchestrator does NOT generate — it
# DELEGATES, and it delegates to Beta. So Preview and Stable are the same engine
# and the quality comparison wdvrdaxxm9 exists to enable is impossible today.
#
# This script stages the fix. It DEPLOYS NOTHING on its own beyond what any of
# the sibling deploy scripts do; the real `gcloud run deploy` is a HARD STOP that
# only Michael may approve (runbook wdvrdaxn9f). Run with --dry-run to see the
# exact commands without executing them.
#
# WHAT IT STAGES  (three Cloud Run services, all Storied-only)
#   1. tour-generator-storied   NEW. CMD `python generate_tour_text_service.py`
#      (same CMD as Beta's tour-generator), built from the `storied` branch into
#      the SEPARATE image repo audioura-storied. This is the engine that has
#      never actually run on Preview.
#   2. tour-modernized-storied  NEW. CMD `python tour_generation_modernized.py`
#      (same CMD as Beta's tour-modernized). See the MODERNIZED_URL note below —
#      it has the identical delegation defect, so it must exist too or Step 1.5
#      of every Storied tour still runs Beta's HTML builder.
#   3. tour-orchestrator-storied  REBUILT from current `storied` (its live image
#      audioura:storied is ~a month stale, commit a57dc507 2026-08-11) and
#      REPOINTED: TOUR_GENERATOR_URL and MODERNIZED_URL -> the two new services.
#      TOUR_TRACK=storied is preserved.
#
# All three share ONE audioura-storied:vN image (build once, deploy many, one CMD
# per service — the established Dockerfile.cloudrun pattern). Only the CMD and env
# differ between them.
#
# SIX NON-OBVIOUS, LOAD-BEARING PROPERTIES (do not drop any):
#
#   1. SEPARATE IMAGE REPO: audioura-storied, NEVER audioura. STORIED-4
#      established why: every Beta service shares `audioura:vN` differing only by
#      CMD, so a Storied build on that shared tag means a later routine
#      "bump tour-generator to vN" silently ships Storied code into Beta.
#      Storied gets its OWN repo with its OWN independent tag sequence.
#      (deploy_cloudrun_service.sh does this via --repo-image.)
#
#   2. --update-env-vars, NOT --set-env-vars, when repointing the orchestrator.
#      tour-orchestrator-storied carries ~20 other env vars (DB, R2, secrets,
#      TOUR_TRACK, sibling URLs). --set-env-vars REPLACES all of them and breaks
#      the service. --update-env-vars changes only the named keys.
#
#   3. --no-cpu-throttling is REQUIRED on the generator and the orchestrator.
#      Without it the generation daemon thread is starved once the HTTP response
#      returns and tours never finish (remind_Services_ai.md:217).
#
#   4. --max-instances=1 is REQUIRED. Job state is in-memory; a second instance
#      cannot answer /status/<job_id> for a job the first instance owns.
#
#   5. TOUR_TRACK=storied stays set on the orchestrator. It reads
#      os.getenv('TOUR_TRACK','beta') (tour_orchestrator_service.py:554) and any
#      other value falls back to 'beta' silently. We never clear it; --dry-run
#      shows it is only ever set, never removed.
#
#   6. NO BETA SERVICE IS EVER NAMED. The only `gcloud run deploy` /
#      `update-traffic` targets in this file are the three *-storied services,
#      enforced by assert_target_is_storied() below. tour-generator,
#      tour-modernized, tour-orchestrator, map-delivery, news-orchestrator,
#      newsletter-processor and api-gateway are never passed to a mutating call.
#
# MODELLED ON  deploy_storied_service.sh (branch kiro/storied-4) for the
# orchestrator half, and deploy_cloudrun_service.sh for the --repo-image idea and
# release tagging. WHAT DIFFERS: that script deploys ONE service; this stages
# THREE that together move the whole generation path off Beta, and it repoints
# two orchestrator URLs the single-service script never touches.
#
# USAGE
#   ./deploy_storied_generator.sh --dry-run     # print the exact commands (default-safe)
#   ./deploy_storied_generator.sh               # deploy all three (Michael only)
#   ./deploy_storied_generator.sh --tag v3      # build/deploy a specific storied tag
#   ./deploy_storied_generator.sh --rollback    # revert all three to previous revision
#
# Requires: gcloud (authenticated), docker, an amd64 build host, repo root cwd.

set -euo pipefail

# Release tagging: every deploy is pinned to a pushed git tag so the deployed
# source can be reconstituted exactly. Storied is release line 2 (release_tag.sh).
. "$(dirname "$0")/release_tag.sh"

PROJECT="audiotours-migration"
REGION="us-central1"

# Storied's OWN image repo — NOT the shared `audioura`. Property 1.
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"
IMAGE_NAME="audioura-storied"
DOCKERFILE="Dockerfile.cloudrun"

# The three Storied services and the CMD each runs. All Storied-named (property 6).
ORCH_SERVICE="tour-orchestrator-storied"
GEN_SERVICE="tour-generator-storied"
MOD_SERVICE="tour-modernized-storied"

# CMDs mirror the Beta services exactly (docker-compose.yml + generate service).
ORCH_ARGS="tour_orchestrator_service.py"
GEN_ARGS="generate_tour_text_service.py"
MOD_ARGS="tour_generation_modernized.py"

# Runtime config. --no-cpu-throttling and --max-instances=1 are non-negotiable
# (properties 3 and 4) and passed explicitly on every deploy below.
CPU="2"
MEMORY="1Gi"
CONCURRENCY="5"
TIMEOUT="300"
MAX_INSTANCES="1"

TOUR_TRACK="storied"   # property 5

DRY_RUN=0
FORCED_TAG=""
ROLLBACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  DRY_RUN=1 ;;
    --tag)      FORCED_TAG="${2:-}"; shift ;;
    --rollback) ROLLBACK=1 ;;
    -h|--help)  sed -n '2,90p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# Property 6, enforced in code: refuse to name any non-storied service in a
# mutating gcloud call. Every deploy/rollback target passes through here first.
assert_target_is_storied() {
  case "$1" in
    *-storied) : ;;
    *) fail "refusing to run a mutating gcloud command against '$1' — this script
       only ever touches *-storied services (property 6). Beta is never named." ;;
  esac
}

# ---------------------------------------------------------------- rollback ---
# Roll all three Storied services back to their previous revision, newest first.
if [ "$ROLLBACK" = "1" ]; then
  for SVC in "$ORCH_SERVICE" "$MOD_SERVICE" "$GEN_SERVICE"; do
    assert_target_is_storied "$SVC"
    say "Rollback: available revisions for ${SVC}"
    gcloud run revisions list --service "$SVC" --region "$REGION" \
      --format="table(metadata.name,metadata.creationTimestamp,spec.containers[0].image)" --limit 5 || true
    prev=$(gcloud run revisions list --service "$SVC" --region "$REGION" \
      --format="value(metadata.name)" --sort-by="~metadata.creationTimestamp" --limit 2 | tail -1)
    [ -n "$prev" ] || fail "could not determine previous revision for ${SVC}"
    say "Routing 100% of traffic on ${SVC} to ${prev}"
    run "gcloud run services update-traffic '$SVC' --region '$REGION' --to-revisions '${prev}=100'"
  done
  exit 0
fi

# ------------------------------------------------------------- preflight ----
say "Preflight"
command -v gcloud >/dev/null || fail "gcloud not on PATH"
command -v docker >/dev/null || fail "docker not on PATH"
gcloud auth print-access-token >/dev/null 2>&1 || fail "gcloud not authenticated — run: gcloud auth login"
[ -f "$DOCKERFILE" ] || fail "$DOCKERFILE not found — run this from the repo root"
echo "  project=${PROJECT} region=${REGION}"
echo "  image repo=${IMAGE_NAME} (separate from Beta's shared 'audioura')"
echo "  services: ${GEN_SERVICE}, ${MOD_SERVICE}, ${ORCH_SERVICE}"

# Guard 1: the orchestrator must still read TOUR_TRACK, or every Storied tour
# records as Beta (STORIED-1). Invisible at the HTTP layer, so check the source.
grep -q "os.getenv('TOUR_TRACK'" tour_orchestrator_service.py \
  || fail "tour_orchestrator_service.py no longer reads os.getenv('TOUR_TRACK').
       Deploying now could record every Storied tour as Beta. Check your branch."
echo "  orchestrator source reads TOUR_TRACK: OK"

# Guard 2: the orchestrator must still delegate via the two repointable env vars,
# or repointing them achieves nothing.
grep -q "TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL'" tour_orchestrator_service.py \
  || fail "orchestrator no longer reads TOUR_GENERATOR_URL from env — repointing would be a no-op."
grep -q "MODERNIZED_URL = os.getenv('MODERNIZED_URL'" tour_orchestrator_service.py \
  || fail "orchestrator no longer reads MODERNIZED_URL from env — repointing would be a no-op."
echo "  orchestrator reads TOUR_GENERATOR_URL and MODERNIZED_URL from env: OK"

# Guard 3: the generator service the new tour-generator-storied will run must
# expose /generate and /status/<job_id>, the two endpoints the orchestrator uses.
grep -q "@app.route('/generate'" generate_tour_text_service.py \
  || fail "generate_tour_text_service.py has no /generate route — wrong CMD for the generator."
grep -q "@app.route('/status/<job_id>'" generate_tour_text_service.py \
  || fail "generate_tour_text_service.py has no /status/<job_id> route — orchestrator polling would fail."
echo "  generator service exposes /generate and /status: OK"

# Guard 4: no UNTRACKED .py in the build context. Dockerfile.cloudrun does
# COPY *.py, so an untracked module would become production code with no history.
UNTRACKED_PY=$(git status --porcelain -uall | grep '^??' | grep -E '\.py$' || true)
[ -z "$UNTRACKED_PY" ] || fail "untracked .py file(s) in the build context — COPY *.py would
       ship them into the image with no git history. Commit or remove first:
$(printf '%s\n' "$UNTRACKED_PY" | sed 's/^/         /')"
echo "  no untracked .py in build context: OK"

# ------------------------------------------------------------- pick a tag ---
# Storied's tag sequence is INDEPENDENT of the shared audioura sequence — its own
# repo (property 1). Start at v1 if the repo has no tags yet. All three services
# share the ONE tag chosen here (build once, deploy many).
say "Choosing image tag (repo: ${IMAGE_NAME})"
if [ -n "$FORCED_TAG" ]; then
  TAG="$FORCED_TAG"
else
  highest=$(gcloud artifacts docker tags list "${REPO}/${IMAGE_NAME}" \
    --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
    | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1 || true)
  if [ -z "$highest" ]; then
    TAG="v1"
    echo "  no existing tags in ${IMAGE_NAME} — starting at ${TAG}"
  else
    TAG="v$((highest + 1))"
    echo "  highest existing tag in ${IMAGE_NAME}: v${highest} -> using ${TAG}"
  fi
fi
FULL_IMAGE="${REPO}/${IMAGE_NAME}:${TAG}"
echo "  will build and deploy: ${FULL_IMAGE}"

# Never overwrite an existing tag — rollback depends on old tags staying immutable.
if gcloud artifacts docker images describe "$FULL_IMAGE" >/dev/null 2>&1; then
  fail "${FULL_IMAGE} already exists. Never overwrite a tag — rollback depends on
       old tags staying immutable. Pass a different --tag."
fi

# --------------------------------------------------------- release tag ------
BRANCH=$(git rev-parse --abbrev-ref HEAD)
RELEASE_LINE=$(release_line_for_branch "$BRANCH")
# storied maps to line 2. A task branch off storied is not in the map, so fall
# back to line 2 for the storied deploy while still refusing main/unknown lines.
if [ -z "$RELEASE_LINE" ]; then
  echo "  branch '$BRANCH' not in the release map; this is a Storied build -> using line 2 (storied)"
  RELEASE_LINE=2
fi
[ "$RELEASE_LINE" = "2" ] || fail "release line is '${RELEASE_LINE}', not 2 (storied).
       This script only ships the Storied line. Deploy from storied (or a storied task branch)."
assert_image_content_clean || exit 1
RELEASE_TAG=$(next_release_tag "$RELEASE_LINE")
DEPLOY_COMMIT=$(git rev-parse HEAD)
echo "  release tag: ${RELEASE_TAG}  (line ${RELEASE_LINE}, branch ${BRANCH}, commit ${DEPLOY_COMMIT:0:8})"

# ------------------------------------------------------------- build/push ---
# Dockerfile.cloudrun does COPY *.py — one image carries every module, incl. the
# 17k-line generate_tour_text.py engine. The three services differ only by CMD.
say "Building ${FULL_IMAGE} from ${DOCKERFILE} (current ${BRANCH})"
run "docker build -f '$DOCKERFILE' -t '$FULL_IMAGE' --build-arg RELEASE_TAG='$RELEASE_TAG' --build-arg GIT_SHA='$DEPLOY_COMMIT' ."

say "Pushing to Artifact Registry"
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '$FULL_IMAGE'"

# ---------------------------------------------------- deploy generator ------
# tour-generator-storied: the engine that has never actually run on Preview.
assert_target_is_storied "$GEN_SERVICE"
say "Deploying ${GEN_SERVICE} (CMD: python ${GEN_ARGS})"
run "gcloud run deploy '$GEN_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$GEN_ARGS' \
  --no-cpu-throttling \
  --max-instances='$MAX_INSTANCES' \
  --concurrency='$CONCURRENCY' \
  --cpu='$CPU' \
  --memory='$MEMORY' \
  --timeout='$TIMEOUT' \
  --quiet"

# ---------------------------------------------------- deploy modernizer -----
# tour-modernized-storied: Step 1.5 HTML builder, same delegation defect as the
# generator (MODERNIZED_URL points at Beta today). See the MODERNIZED_URL note.
assert_target_is_storied "$MOD_SERVICE"
say "Deploying ${MOD_SERVICE} (CMD: python ${MOD_ARGS})"
run "gcloud run deploy '$MOD_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$MOD_ARGS' \
  --no-cpu-throttling \
  --max-instances='$MAX_INSTANCES' \
  --concurrency='$CONCURRENCY' \
  --cpu='$CPU' \
  --memory='$MEMORY' \
  --timeout='$TIMEOUT' \
  --quiet"

# ------------------------------------------ resolve the new service URLs -----
# The orchestrator must point at the two services just deployed. Under --dry-run
# these describes return nothing, so fall back to the internal Cloud Run names so
# the printed repoint command is still concrete and reviewable.
say "Resolving new service URLs for the orchestrator repoint"
GEN_URL=$(gcloud run services describe "$GEN_SERVICE" --region "$REGION" --format="value(status.url)" 2>/dev/null || true)
MOD_URL=$(gcloud run services describe "$MOD_SERVICE" --region "$REGION" --format="value(status.url)" 2>/dev/null || true)
[ -n "$GEN_URL" ] || GEN_URL="https://${GEN_SERVICE}-<hash>-uc.a.run.app"
[ -n "$MOD_URL" ] || MOD_URL="https://${MOD_SERVICE}-<hash>-uc.a.run.app"
echo "  TOUR_GENERATOR_URL -> ${GEN_URL}"
echo "  MODERNIZED_URL     -> ${MOD_URL}"

# ---------------------------------------------- deploy/repoint orchestrator --
# Rebuild the orchestrator from current storied (its live image is ~a month
# stale) AND repoint both delegation URLs. --update-env-vars preserves the ~20
# other env vars incl. TOUR_TRACK (properties 2 and 5).
assert_target_is_storied "$ORCH_SERVICE"
say "Deploying ${ORCH_SERVICE} (CMD: python ${ORCH_ARGS}) + repointing URLs to Storied"
run "gcloud run deploy '$ORCH_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$ORCH_ARGS' \
  --update-env-vars 'TOUR_TRACK=${TOUR_TRACK},TOUR_GENERATOR_URL=${GEN_URL},MODERNIZED_URL=${MOD_URL}' \
  --no-cpu-throttling \
  --max-instances='$MAX_INSTANCES' \
  --concurrency='$CONCURRENCY' \
  --cpu='$CPU' \
  --memory='$MEMORY' \
  --timeout='$TIMEOUT' \
  --quiet"

[ "$DRY_RUN" = "1" ] && { echo; echo "dry run complete — nothing changed. No Beta service was named."; exit 0; }

# ---------------------------------------------------------------- verify ----
# Verify by effect, never by exit code (remind_Services_ai.md:40).
say "Verifying deployments"
TOKEN=$(gcloud auth print-identity-token)
for SVC in "$GEN_SERVICE" "$MOD_SERVICE" "$ORCH_SERVICE"; do
  URL=$(gcloud run services describe "$SVC" --region "$REGION" --format="value(status.url)")
  HEALTH=$(curl -s -m 30 -H "Authorization: Bearer $TOKEN" "${URL}/health" || true)
  echo "  ${SVC} /health -> ${HEALTH:-<no response>}"
  printf '%s' "$HEALTH" | grep -q 'healthy' \
    || fail "${SVC} did not report healthy — roll back with: $0 --rollback"
done

# Confirm the orchestrator actually carries storied track + the repointed URLs.
ORCH_ENV=$(gcloud run services describe "$ORCH_SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env)" 2>/dev/null | tr ';' '\n' || true)
printf '%s' "$ORCH_ENV" | grep -qi 'TOUR_TRACK.*storied' \
  || fail "TOUR_TRACK is not 'storied' on ${ORCH_SERVICE} — tours would record as Beta. Roll back: $0 --rollback"
printf '%s' "$ORCH_ENV" | grep -qi "$GEN_SERVICE" \
  || fail "TOUR_GENERATOR_URL does not point at ${GEN_SERVICE} — still delegating to Beta. Roll back: $0 --rollback"
printf '%s' "$ORCH_ENV" | grep -qi "$MOD_SERVICE" \
  || fail "MODERNIZED_URL does not point at ${MOD_SERVICE} — still delegating to Beta. Roll back: $0 --rollback"
echo "  orchestrator env: TOUR_TRACK=storied, both URLs repointed to Storied: OK"

# Tag only AFTER a verified deploy.
if create_and_push_release_tag "$RELEASE_TAG" "$DEPLOY_COMMIT" "$ORCH_SERVICE (+generator,+modernized)" "$FULL_IMAGE"; then
  echo "  tagged and pushed: $RELEASE_TAG -> ${DEPLOY_COMMIT:0:8}"
else
  echo "  WARNING: deploy succeeded but tagging did not — reconstitution is not guaranteed" >&2
fi

say "Done"
cat <<EOF
  image     : ${FULL_IMAGE}   (repo audioura-storied — NOT Beta's audioura)
  generator : ${GEN_SERVICE}   CMD python ${GEN_ARGS}
  modernized: ${MOD_SERVICE}   CMD python ${MOD_ARGS}
  orchestr. : ${ORCH_SERVICE}   TOUR_TRACK=storied
              TOUR_GENERATOR_URL -> ${GEN_URL}
              MODERNIZED_URL     -> ${MOD_URL}

  No Beta service (tour-generator, tour-modernized, tour-orchestrator,
  map-delivery, news-orchestrator, newsletter-processor, api-gateway) was named.

  MANDATORY post-deploy check — track alone is NOT evidence (tour 422 proved a
  Beta-generated tour can read track='storied'). Generate one tour for the SAME
  venue on each track, then show the generator logs come from DIFFERENT services:

    # Storied job -> logs MUST appear on tour-generator-storied
    gcloud run services logs read ${GEN_SERVICE} --region ${REGION} --limit 50
    # Same-venue Beta job -> logs MUST appear on Beta's tour-generator
    gcloud run services logs read tour-generator     --region ${REGION} --limit 50

  Then diff the two tours' text — a visible difference confirms different engines.

  Roll back all three with:
    $0 --rollback
EOF
