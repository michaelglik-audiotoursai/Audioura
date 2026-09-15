#!/usr/bin/env bash
# deploy_beta_local474.sh — port LOCAL-474 to Beta as an OVERLAY, image-only.
#
# GCS-7. Builds two overlay images (v22-local474 / v36-local474) that COPY only
# the three LOCAL-474 files onto the exact images Beta runs (audioura:v22 / v36),
# then points the Beta Cloud Run services at them. IMAGE ONLY — never touches env,
# scaling, concurrency, or any other setting, and names no service other than
# tour-orchestrator and tour-generator.
#
# Default is --dry-run: it prints every command and touches nothing. --apply runs
# them. Runs in Git Bash on Windows.
#
# The only behaviour change shipped: an empty/missing tour_type is classified
# instead of rejected with 400. Proven no-drift in SUBMISSION_GCS-7.md.
set -euo pipefail

# ---- configuration -----------------------------------------------------------
REGION="us-central1"
PROJECT="audiotours-migration"
REPO="us-central1-docker.pkg.dev/${PROJECT}/services"

ORCH_BASE_TAG="v22"
GEN_BASE_TAG="v36"
ORCH_NEW_TAG="v22-local474"
GEN_NEW_TAG="v36-local474"

ORCH_BASE_IMAGE="${REPO}/audioura:${ORCH_BASE_TAG}"
GEN_BASE_IMAGE="${REPO}/audioura:${GEN_BASE_TAG}"
ORCH_NEW_IMAGE="${REPO}/audioura:${ORCH_NEW_TAG}"
GEN_NEW_IMAGE="${REPO}/audioura:${GEN_NEW_TAG}"

ORCH_SERVICE="tour-orchestrator"
GEN_SERVICE="tour-generator"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DOCKERFILE="${SCRIPT_DIR}/Dockerfile.local474.orchestrator"
GEN_DOCKERFILE="${SCRIPT_DIR}/Dockerfile.local474.generator"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1
[[ "${1:-}" == "--dry-run" ]] && APPLY=0

# ---- helpers -----------------------------------------------------------------
run() {
  # Print, then execute only under --apply.
  echo "+ $*"
  if [[ "${APPLY}" -eq 1 ]]; then
    "$@"
  fi
}

banner() { echo; echo "==== $* ===="; }

if [[ "${APPLY}" -eq 1 ]]; then
  echo "### MODE: --apply  (commands WILL run)"
else
  echo "### MODE: --dry-run  (default; nothing is executed, commands only printed)"
  echo "### Re-run with --apply to actually build, push, and update the two services."
fi

# ---- 0. record BEFORE revisions ---------------------------------------------
banner "0. Record current (BEFORE) revisions and images"
run gcloud run services describe "${ORCH_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --format="value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)"
run gcloud run services describe "${GEN_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --format="value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)"

# ---- 1. build overlay images -------------------------------------------------
banner "1. Build overlay images (FROM ${ORCH_BASE_TAG}/${GEN_BASE_TAG}, COPY only the LOCAL-474 files)"
run docker build -f "${ORCH_DOCKERFILE}" -t "${ORCH_NEW_IMAGE}" "${SCRIPT_DIR}"
run docker build -f "${GEN_DOCKERFILE}"  -t "${GEN_NEW_IMAGE}"  "${SCRIPT_DIR}"

# ---- 2. push overlay images --------------------------------------------------
banner "2. Push overlay images"
run docker push "${ORCH_NEW_IMAGE}"
run docker push "${GEN_NEW_IMAGE}"

# ---- 3. update services (IMAGE ONLY) ----------------------------------------
banner "3. Point the two Beta services at the overlay images — IMAGE ONLY"
# --image is the ONLY thing changed. No --set-env-vars, no --min/max-instances,
# no --concurrency, no --cpu/--memory. Cloud Run carries every other setting
# forward from the current revision unchanged.
run gcloud run services update "${ORCH_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --image "${ORCH_NEW_IMAGE}"
run gcloud run services update "${GEN_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --image "${GEN_NEW_IMAGE}"

# ---- 4. record AFTER revisions ----------------------------------------------
banner "4. Record new (AFTER) revisions and images"
run gcloud run services describe "${ORCH_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --format="value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)"
run gcloud run services describe "${GEN_SERVICE}" --region "${REGION}" --project "${PROJECT}" \
    --format="value(status.latestReadyRevisionName, spec.template.spec.containers[0].image)"

# ---- 5. rollback commands ----------------------------------------------------
banner "5. ROLLBACK (run these to restore the pre-LOCAL-474 images)"
echo "gcloud run services update ${ORCH_SERVICE} --region ${REGION} --project ${PROJECT} --image ${ORCH_BASE_IMAGE}"
echo "gcloud run services update ${GEN_SERVICE} --region ${REGION} --project ${PROJECT} --image ${GEN_BASE_IMAGE}"

banner "DONE"
if [[ "${APPLY}" -eq 0 ]]; then
  echo "Dry run complete. Nothing was built, pushed, or changed."
fi
