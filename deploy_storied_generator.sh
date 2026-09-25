#!/usr/bin/env bash
# Stage the STORIED tour-GENERATOR deploy so approval is one reviewed command.
#
# WHY THIS SCRIPT EXISTS (ClickUp wdvrdaxxm9, Phase 2 — GCS-3 / GCS-3R)
# Preview has never run Storied generation code. Verified end to end 2026-09-15
# (PREVIEW_IS_RUNNING_BETA_CODE.md). The chain today:
#
#   storied-api -> api-gateway-storied      (api-gateway:v35, from MAIN)
#              -> tour-orchestrator-storied (audioura:storied, TOUR_TRACK=storied)
#                 TOUR_GENERATOR_URL -> tour-generator            <-- BETA's service
#                 MODERNIZED_URL     -> tour-modernized           <-- BETA's service
#
# tour_orchestrator_service.py:671 POSTs to TOUR_GENERATOR_URL/generate and :769
# POSTs to MODERNIZED_URL/process. The orchestrator does NOT generate — it
# DELEGATES, and it delegates to Beta. So Preview and Stable are the same engine
# and the quality comparison wdvrdaxxm9 exists to enable is impossible today.
#
# This script STAGES the fix. It DEPLOYS NOTHING unless run with no flags AND by
# someone who has approved the deploy (runbook wdvrdaxn9f). Run with --dry-run to
# see the exact commands without executing them; --dry-run is the default-safe way
# to review it and is what GCS-3R uses. The real `gcloud run deploy` is a separate
# dispatch after LEAD review.
#
# ============================================================================
# GCS-3R BOUNCE FIXES (LEAD-verified against live Cloud Run, 2026-09-15)
# ============================================================================
# B1  The two NEW services now carry full runtime config (env, secrets, Cloud SQL).
#     Before, tour-generator-storied / tour-modernized-storied were deployed with
#     NO env, NO secrets, NO Cloud SQL — they would boot and fail on first request.
#     See build_generator_env()/build_modernized_env() and the --set-secrets below.
#     Config sources (all read from live config or the code, never guessed):
#       - generator floor = live Beta tour-generator (TOUR_STORAGE_MODE, OPENAI, PYTHONUNBUFFERED)
#       - + the DB block the live tour-orchestrator-storied carries (Cloud SQL socket)
#       - + DATABASE_URL in libpq socket form, REQUIRED because venue_resolver.py,
#         work_story_searcher.py and area_resolver.py read ONLY the URL vars and
#         otherwise fall back to host 'postgres-2' (unresolvable on Cloud Run).
#       - + STORIED_MODE=true (master switch; false => Beta parity, the whole point lost)
#       - modernized = live Beta tour-modernized env/secrets/flags, mirrored exactly.
# B1.3 Memory chosen from a MEASURED local run (B4), not a guess: a 2-stop restaurant
#     tour peaked at ~120 MiB, so 512Mi (Beta's generator floor) is ample. The
#     generator runs generation on a BACKGROUND daemon thread after the HTTP
#     response returns, so --no-cpu-throttling is REQUIRED or that thread starves
#     (remind_Services_ai.md; generate_tour_text_service.py background thread).
# B2  Both new services deploy --no-allow-unauthenticated and get an invoker
#     binding for the orchestrator's runtime SA (matches live Beta IAM exactly:
#     roles/run.invoker for serviceAccount:60899077572-compute@...). The
#     orchestrator sends an identity token (tour_orchestrator_service.py:81-108).
#     The generator must NOT be public — it spends OpenAI money.
# B3  The orchestrator redeploy changes ONLY the image and the two URLs via
#     --update-env-vars. It NO LONGER forces max-instances/concurrency/cpu/memory,
#     which would have silently downgraded the live service (maxScale 10,
#     concurrency 80, cpu 1, 512Mi). See the orchestrator deploy block.
# B4  Built from `storied` >= 0de517c with GIT_SHA = actual HEAD, and the image is
#     actually built (GCS-3 never ran docker build). A local end-to-end tour from
#     the built image is the acceptance proof (SUBMISSION_GCS-3R.md).
# B4b BLOCKER surfaced by that local run: Dockerfile.cloudrun does `COPY *.py` only,
#     so the running generator is MISSING db_connection.py and stop_anchor_detector_v2.py
#     (both live under tests/), plus the data files templates/ and story_type_taxonomy.json.
#     Without them a Storied tour ERRORS mid-generation ("No module named
#     'db_connection'"/"...'stop_anchor_detector_v2'"). assert_build_context_complete()
#     below refuses to build until the image will contain them. This is a Dockerfile
#     fix; see SUBMISSION_GCS-3R.md "Open blocking question".
#
# SIX NON-OBVIOUS, LOAD-BEARING PROPERTIES (unchanged from GCS-3; do not drop):
#   1. SEPARATE IMAGE REPO audioura-storied, NEVER audioura (STORIED-4).
#   2. --update-env-vars, NOT --set-env-vars, on the orchestrator (keeps ~20 vars).
#   3. --no-cpu-throttling on the generator and the orchestrator.
#   4. --max-instances=1 on the two NEW services (in-memory job state; a second
#      instance cannot answer /status/<job_id> for another instance's job).
#      NOTE: this is applied to the NEW services only, never forced on the
#      orchestrator (B3).
#   5. TOUR_TRACK=storied stays set on the orchestrator (never cleared).
#   6. NO BETA SERVICE IS EVER NAMED in a mutating call (assert_target_is_storied).
#
# USAGE
#   ./deploy_storied_generator.sh --dry-run     # print the exact commands (default-safe)
#   ./deploy_storied_generator.sh               # deploy all three (approved runbook only)
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

TOUR_TRACK="storied"   # property 5

# --- Cloud SQL / DB (from live tour-orchestrator-storied config, 2026-09-15) ---
CLOUDSQL_INSTANCE="${PROJECT}:${REGION}:audioura-db"
DB_SOCKET="/cloudsql/${CLOUDSQL_INSTANCE}"
DB_NAME="audiotours"
DB_USER="admin"
DB_PORT="5432"
# DATABASE_URL in libpq URI form WITHOUT an inline password. The password lives
# in the db-password secret and is surfaced to the container as PGPASSWORD (see
# GEN_SECRETS); libpq completes the password-less URL from PGPASSWORD. This is
# REQUIRED because venue_resolver.py, work_story_searcher.py and area_resolver.py
# read ONLY the URL vars (DATABASE_URL / VENUE_CACHE_DB_URL) and otherwise fall
# back to host 'postgres-2', which is unresolvable on Cloud Run. Verified locally
# (SUBMISSION_GCS-3R.md, "password-less URL + PGPASSWORD"): psycopg2 connects.
# For the modules that use DB_* keyword args, DB_PASSWORD (also from the secret)
# serves them. Socket form uses host as a query param with an empty authority.
DATABASE_URL_NOPASS="postgresql://${DB_USER}@/${DB_NAME}?host=${DB_SOCKET}"

# --- Resource config -------------------------------------------------------
# Generator: Beta generator floor (cpu 1, 512Mi, concurrency 40, maxScale 5) is
# enough — measured peak ~120 MiB for a 2-stop tour (B4). --no-cpu-throttling and
# --max-instances=1 are the two Storied-specific overrides (properties 3, 4).
GEN_CPU="1"; GEN_MEMORY="512Mi"; GEN_CONCURRENCY="40"; GEN_MAXSCALE="5"; GEN_TIMEOUT="300"
# Modernized: mirror live Beta tour-modernized EXACTLY (cpu 2, 1Gi, concurrency 5,
# maxScale 1, cpu-throttling false, timeout 300).
MOD_CPU="2"; MOD_MEMORY="1Gi"; MOD_CONCURRENCY="5"; MOD_MAXSCALE="1"; MOD_TIMEOUT="300"

# Orchestrator runtime SA that must be able to invoke the two new services.
# = live Beta invoker member (roles/run.invoker) and the orchestrator's own SA.
INVOKER_SA="serviceAccount:60899077572-compute@developer.gserviceaccount.com"

# R2 config for the modernizer (from live Beta tour-modernized).
R2_ENDPOINT="https://4b4aa47cda0cc65f20b20fac0b363ac7.r2.cloudflarestorage.com"
R2_BUCKET="v1-audiotours-r2-bucket"
POLLY_TTS_URL="https://polly-tts-60899077572.us-central1.run.app"

DRY_RUN=0
FORCED_TAG=""
ROLLBACK=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)  DRY_RUN=1 ;;
    --tag)      FORCED_TAG="${2:-}"; shift ;;
    --rollback) ROLLBACK=1 ;;
    -h|--help)  sed -n '2,120p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  [dry-run] %s\n' "$*"; else eval "$@"; fi; }
fail() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# Property 6, enforced in code: refuse to name any non-storied service in a
# mutating gcloud call. Every deploy/rollback/iam target passes through here first.
assert_target_is_storied() {
  case "$1" in
    *-storied) : ;;
    *) fail "refusing to run a mutating gcloud command against '$1' — this script
       only ever touches *-storied services (property 6). Beta is never named." ;;
  esac
}

# B4: the deployed source MUST be storied >= 0de517c (predecessors miss LOCAL-474,
# LOCAL-467, D558, LOCAL-470). GCS-3 staged 06b890e, which is too old.
STORIED_FLOOR="0de517c"
assert_commit_at_or_after_floor() {
  git merge-base --is-ancestor "$STORIED_FLOOR" HEAD 2>/dev/null \
    || fail "HEAD is not at or after the storied floor ${STORIED_FLOOR}.
       GCS-3 built 06b890e, which predates LOCAL-474/467, D558, LOCAL-470.
       Check out storied (>= ${STORIED_FLOOR}) before building."
}

# B4b BLOCKER: Dockerfile.cloudrun does `COPY *.py` only. Several modules the
# generator imports at generation time live ONLY under tests/ (db_connection.py,
# stop_anchor_detector_v2.py), and two data assets it reads (templates/,
# story_type_taxonomy.json) are non-.py. A local end-to-end run proved a Storied
# tour ERRORS without them. Refuse to build an image that would ship broken.
assert_build_context_complete() {
  local missing=0
  # 1) The two tests/-only modules the generator pulls in via style_validator_detector.
  #    They must be COPY'd to /app by the Dockerfile. We check the Dockerfile
  #    actually copies them (root COPY *.py will NOT — they are under tests/).
  for need in db_connection stop_anchor_detector_v2; do
    if ! grep -qE "COPY[^#]*(tests/)?${need}\.py" "$DOCKERFILE"; then
      echo "  build-context GAP: ${need}.py (lives under tests/, not copied by 'COPY *.py')"
      missing=1
    fi
  done
  # 2) Non-.py assets the engine reads at runtime.
  grep -qE "COPY[^#]*templates/" "$DOCKERFILE" || { echo "  build-context GAP: templates/ not COPY'd"; missing=1; }
  grep -qE "COPY[^#]*story_type_taxonomy\.json" "$DOCKERFILE" || { echo "  build-context GAP: story_type_taxonomy.json not COPY'd"; missing=1; }
  [ "$missing" = "0" ] || fail "Dockerfile.cloudrun will build an INCOMPLETE generator image
       (see gaps above). A Storied tour errors mid-generation without these.
       Fix Dockerfile.cloudrun to COPY them, then rebuild. Proven by the local
       end-to-end run in SUBMISSION_GCS-3R.md (B4b)."
}

# Generator env. DB pointed at Cloud SQL via socket; STORIED_MODE on; the URL-idiom
# modules get DATABASE_URL/VENUE_CACHE_DB_URL in socket form, completed by PGPASSWORD
# (which we set from the db-password secret via --set-secrets below).
GEN_ENV="STORIED_MODE=true,TOUR_STORAGE_MODE=cloud,PYTHONUNBUFFERED=1,TOUR_TRACK=${TOUR_TRACK},USER_STOPS_ENABLED=false,DB_HOST=${DB_SOCKET},DB_NAME=${DB_NAME},DB_USER=${DB_USER},DB_PORT=${DB_PORT},DATABASE_URL=${DATABASE_URL_NOPASS},VENUE_CACHE_DB_URL=${DATABASE_URL_NOPASS}"
# Secrets: OPENAI for generation, db-password for DB_PASSWORD, and the SAME secret
# surfaced as PGPASSWORD so libpq can complete the password-less DATABASE_URL.
GEN_SECRETS="OPENAI_API_KEY=openai-api-key:latest,DB_PASSWORD=db-password:latest,PGPASSWORD=db-password:latest"

# Modernizer env/secrets — mirror live Beta tour-modernized exactly.
MOD_ENV="TOUR_STORAGE_MODE=cloud,USER_STOPS_ENABLED=false,BLOB_STORAGE_TYPE=r2,R2_ENDPOINT=${R2_ENDPOINT},R2_BUCKET=${R2_BUCKET},POLLY_TTS_URL=${POLLY_TTS_URL},POLLY_FIX=v3"
MOD_SECRETS="AWS_ACCESS_KEY_ID=aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=aws-secret-access-key:latest,R2_ACCESS_KEY_ID=r2-access-key-id:latest,R2_SECRET_ACCESS_KEY=r2-secret-access-key:latest"

# ---------------------------------------------------------------- rollback ---
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

assert_commit_at_or_after_floor            # B4
echo "  HEAD >= storied floor ${STORIED_FLOOR}: OK"

# Guard 1: the orchestrator must still read TOUR_TRACK, or every Storied tour
# records as Beta (STORIED-1).
grep -q "os.getenv('TOUR_TRACK'" tour_orchestrator_service.py \
  || fail "tour_orchestrator_service.py no longer reads os.getenv('TOUR_TRACK'). Check your branch."
echo "  orchestrator source reads TOUR_TRACK: OK"

# Guard 2: the orchestrator must still delegate via the two repointable env vars.
grep -q "TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL'" tour_orchestrator_service.py \
  || fail "orchestrator no longer reads TOUR_GENERATOR_URL from env — repointing would be a no-op."
grep -q "MODERNIZED_URL = os.getenv('MODERNIZED_URL'" tour_orchestrator_service.py \
  || fail "orchestrator no longer reads MODERNIZED_URL from env — repointing would be a no-op."
echo "  orchestrator reads TOUR_GENERATOR_URL and MODERNIZED_URL from env: OK"

# Guard 3: the generator service must expose /generate and /status/<job_id>.
grep -q "@app.route('/generate'" generate_tour_text_service.py \
  || fail "generate_tour_text_service.py has no /generate route — wrong CMD for the generator."
grep -q "@app.route('/status/<job_id>'" generate_tour_text_service.py \
  || fail "generate_tour_text_service.py has no /status/<job_id> route — orchestrator polling would fail."
echo "  generator service exposes /generate and /status: OK"

# Guard 4: no UNTRACKED .py in the build context (COPY *.py would ship them).
UNTRACKED_PY=$(git status --porcelain -uall | grep '^??' | grep -E '\.py$' || true)
[ -z "$UNTRACKED_PY" ] || fail "untracked .py file(s) in the build context — COPY *.py would
       ship them into the image with no git history. Commit or remove first:
$(printf '%s\n' "$UNTRACKED_PY" | sed 's/^/         /')"
echo "  no untracked .py in build context: OK"

# Guard 5 (B4b): the image must actually contain the modules/assets the generator
# imports at generation time, or a Storied tour errors mid-run.
assert_build_context_complete
echo "  build context ships db_connection, stop_anchor_detector_v2, templates/, story_type_taxonomy.json: OK"

# ------------------------------------------------------------- pick a tag ---
say "Choosing image tag (repo: ${IMAGE_NAME})"
if [ -n "$FORCED_TAG" ]; then
  TAG="$FORCED_TAG"
else
  highest=$(gcloud artifacts docker tags list "${REPO}/${IMAGE_NAME}" \
    --format="value(tag)" 2>/dev/null | sed 's|.*/||' \
    | grep -E '^v[0-9]+$' | sed 's/^v//' | sort -n | tail -1 || true)
  if [ -z "$highest" ]; then
    TAG="v1"; echo "  no existing tags in ${IMAGE_NAME} — starting at ${TAG}"
  else
    TAG="v$((highest + 1))"; echo "  highest existing tag in ${IMAGE_NAME}: v${highest} -> using ${TAG}"
  fi
fi
FULL_IMAGE="${REPO}/${IMAGE_NAME}:${TAG}"
echo "  will build and deploy: ${FULL_IMAGE}"

if gcloud artifacts docker images describe "$FULL_IMAGE" >/dev/null 2>&1; then
  fail "${FULL_IMAGE} already exists. Never overwrite a tag — rollback depends on
       old tags staying immutable. Pass a different --tag."
fi

# --------------------------------------------------------- release tag ------
BRANCH=$(git rev-parse --abbrev-ref HEAD)
RELEASE_LINE=$(release_line_for_branch "$BRANCH")
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
say "Building ${FULL_IMAGE} from ${DOCKERFILE} (current ${BRANCH}, HEAD ${DEPLOY_COMMIT:0:8})"
run "docker build -f '$DOCKERFILE' -t '$FULL_IMAGE' --build-arg RELEASE_TAG='$RELEASE_TAG' --build-arg GIT_SHA='$DEPLOY_COMMIT' ."

say "Pushing to Artifact Registry"
run "gcloud auth configure-docker us-central1-docker.pkg.dev --quiet"
run "docker push '$FULL_IMAGE'"

# ---------------------------------------------------- deploy generator ------
# B1/B2: full env + secrets + Cloud SQL, private (--no-allow-unauthenticated),
# background-safe (--no-cpu-throttling), single instance (in-memory job state).
assert_target_is_storied "$GEN_SERVICE"
say "Deploying ${GEN_SERVICE} (CMD: python ${GEN_ARGS}) — private, Storied config, Cloud SQL"
run "gcloud run deploy '$GEN_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$GEN_ARGS' \
  --no-allow-unauthenticated \
  --add-cloudsql-instances '$CLOUDSQL_INSTANCE' \
  --set-env-vars '$GEN_ENV' \
  --set-secrets '$GEN_SECRETS' \
  --no-cpu-throttling \
  --max-instances=1 \
  --concurrency='$GEN_CONCURRENCY' \
  --cpu='$GEN_CPU' \
  --memory='$GEN_MEMORY' \
  --timeout='$GEN_TIMEOUT' \
  --quiet"
# B2: grant the orchestrator's runtime SA permission to invoke the generator.
say "Granting invoker on ${GEN_SERVICE} to ${INVOKER_SA}"
run "gcloud run services add-iam-policy-binding '$GEN_SERVICE' \
  --region '$REGION' \
  --member='$INVOKER_SA' \
  --role='roles/run.invoker' \
  --quiet"

# ---------------------------------------------------- deploy modernizer -----
# B1: mirror live Beta tour-modernized env/secrets/flags exactly. B2: private + invoker.
assert_target_is_storied "$MOD_SERVICE"
say "Deploying ${MOD_SERVICE} (CMD: python ${MOD_ARGS}) — mirrors Beta tour-modernized"
run "gcloud run deploy '$MOD_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$MOD_ARGS' \
  --no-allow-unauthenticated \
  --set-env-vars '$MOD_ENV' \
  --set-secrets '$MOD_SECRETS' \
  --no-cpu-throttling \
  --max-instances='$MOD_MAXSCALE' \
  --concurrency='$MOD_CONCURRENCY' \
  --cpu='$MOD_CPU' \
  --memory='$MOD_MEMORY' \
  --timeout='$MOD_TIMEOUT' \
  --quiet"
say "Granting invoker on ${MOD_SERVICE} to ${INVOKER_SA}"
run "gcloud run services add-iam-policy-binding '$MOD_SERVICE' \
  --region '$REGION' \
  --member='$INVOKER_SA' \
  --role='roles/run.invoker' \
  --quiet"

# ------------------------------------------ resolve the new service URLs -----
say "Resolving new service URLs for the orchestrator repoint"
GEN_URL=$(gcloud run services describe "$GEN_SERVICE" --region "$REGION" --format="value(status.url)" 2>/dev/null || true)
MOD_URL=$(gcloud run services describe "$MOD_SERVICE" --region "$REGION" --format="value(status.url)" 2>/dev/null || true)
[ -n "$GEN_URL" ] || GEN_URL="https://${GEN_SERVICE}-<hash>-uc.a.run.app"
[ -n "$MOD_URL" ] || MOD_URL="https://${MOD_SERVICE}-<hash>-uc.a.run.app"
echo "  TOUR_GENERATOR_URL -> ${GEN_URL}"
echo "  MODERNIZED_URL     -> ${MOD_URL}"

# ---------------------------------------------- deploy/repoint orchestrator --
# B3: change ONLY the image and the two URLs. --update-env-vars preserves the ~20
# other env vars incl. TOUR_TRACK (properties 2, 5). NO resource/scaling/throttling
# flags — those stay as they are live (maxScale 10, concurrency 80, cpu 1, 512Mi).
assert_target_is_storied "$ORCH_SERVICE"
say "Deploying ${ORCH_SERVICE} (CMD: python ${ORCH_ARGS}) + repointing URLs to Storied (image + 2 URLs only)"
run "gcloud run deploy '$ORCH_SERVICE' \
  --region '$REGION' \
  --image '$FULL_IMAGE' \
  --command 'python' \
  --args '$ORCH_ARGS' \
  --update-env-vars 'TOUR_TRACK=${TOUR_TRACK},USER_STOPS_ENABLED=false,TOUR_GENERATOR_URL=${GEN_URL},MODERNIZED_URL=${MOD_URL}' \
  --quiet"

[ "$DRY_RUN" = "1" ] && { echo; echo "dry run complete — nothing changed. No Beta service was named."; exit 0; }

# ---------------------------------------------------------------- verify ----
# Verify by effect, never by exit code (remind_Services_ai.md).
say "Verifying deployments"
TOKEN=$(gcloud auth print-identity-token)
for SVC in "$GEN_SERVICE" "$MOD_SERVICE" "$ORCH_SERVICE"; do
  URL=$(gcloud run services describe "$SVC" --region "$REGION" --format="value(status.url)")
  HEALTH=$(curl -s -m 30 -H "Authorization: Bearer $TOKEN" "${URL}/health" || true)
  echo "  ${SVC} /health -> ${HEALTH:-<no response>}"
  printf '%s' "$HEALTH" | grep -q 'healthy' \
    || fail "${SVC} did not report healthy — roll back with: $0 --rollback"
done

# AC5: read back TOUR_GENERATOR_URL and MODERNIZED_URL on the orchestrator and
# FAIL unless BOTH contain '-storied'. Track alone is not evidence (tour 422).
say "Post-deploy check: orchestrator URLs must point at *-storied services"
ORCH_GEN_URL=$(gcloud run services describe "$ORCH_SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env.filter(\"name:TOUR_GENERATOR_URL\").extract(value))" 2>/dev/null | tr -d '[]')
ORCH_MOD_URL=$(gcloud run services describe "$ORCH_SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env.filter(\"name:MODERNIZED_URL\").extract(value))" 2>/dev/null | tr -d '[]')
echo "  TOUR_GENERATOR_URL (read back) = ${ORCH_GEN_URL:-<empty>}"
echo "  MODERNIZED_URL     (read back) = ${ORCH_MOD_URL:-<empty>}"
case "$ORCH_GEN_URL" in *-storied*) : ;; *) fail "TOUR_GENERATOR_URL on ${ORCH_SERVICE} does not contain '-storied' (='${ORCH_GEN_URL}') — still delegating to Beta. Roll back: $0 --rollback" ;; esac
case "$ORCH_MOD_URL" in *-storied*) : ;; *) fail "MODERNIZED_URL on ${ORCH_SERVICE} does not contain '-storied' (='${ORCH_MOD_URL}') — still delegating to Beta. Roll back: $0 --rollback" ;; esac
echo "  both orchestrator URLs contain '-storied': OK"

# Also confirm TOUR_TRACK is still storied.
ORCH_TRACK=$(gcloud run services describe "$ORCH_SERVICE" --region "$REGION" \
  --format="value(spec.template.spec.containers[0].env.filter(\"name:TOUR_TRACK\").extract(value))" 2>/dev/null | tr -d '[]')
[ "$ORCH_TRACK" = "storied" ] \
  || fail "TOUR_TRACK on ${ORCH_SERVICE} is '${ORCH_TRACK}', not 'storied' — tours would record as Beta. Roll back: $0 --rollback"
echo "  TOUR_TRACK=storied: OK"

# Tag only AFTER a verified deploy.
if create_and_push_release_tag "$RELEASE_TAG" "$DEPLOY_COMMIT" "$ORCH_SERVICE (+generator,+modernized)" "$FULL_IMAGE"; then
  echo "  tagged and pushed: $RELEASE_TAG -> ${DEPLOY_COMMIT:0:8}"
else
  echo "  WARNING: deploy succeeded but tagging did not — reconstitution is not guaranteed" >&2
fi

say "Done"
cat <<EOF
  image     : ${FULL_IMAGE}   (repo audioura-storied — NOT Beta's audioura)
  generator : ${GEN_SERVICE}   CMD python ${GEN_ARGS}   (private, Cloud SQL, STORIED_MODE=true)
  modernized: ${MOD_SERVICE}   CMD python ${MOD_ARGS}   (private, mirrors Beta tour-modernized)
  orchestr. : ${ORCH_SERVICE}   TOUR_TRACK=storied (image + 2 URLs changed only)
              TOUR_GENERATOR_URL -> ${GEN_URL}
              MODERNIZED_URL     -> ${MOD_URL}

  No Beta service (tour-generator, tour-modernized, tour-orchestrator,
  map-delivery, news-orchestrator, newsletter-processor, api-gateway) was named.

  MANDATORY post-deploy evidence — track alone is NOT proof (tour 422):
    gcloud run services logs read ${GEN_SERVICE} --region ${REGION} --limit 50
    gcloud run services logs read tour-generator --region ${REGION} --limit 50
  Then diff the two tours' text — a visible difference confirms different engines.

  Roll back all three with:
    $0 --rollback
EOF
