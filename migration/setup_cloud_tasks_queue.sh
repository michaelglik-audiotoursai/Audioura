#!/bin/bash
# ============================================================================
# Setup Cloud Tasks queue + IAM for tour generation
# ============================================================================
# Run this ONCE after GCP project is configured.
# This script is IDEMPOTENT — safe to re-run.
#
# Prerequisites:
#   - gcloud configured with project audiotours-migration
#   - Cloud Tasks API enabled
#   - tour-worker Cloud Run service deployed
#   - tour-orchestrator Cloud Run service deployed
# ============================================================================

set -e

PROJECT_ID="audiotours-migration"
LOCATION="us-central1"
QUEUE_NAME="tour-generation"

# The service account used by the orchestrator's Cloud Run instance
# (usually the default compute service account or a custom SA)
ORCHESTRATOR_SA="${ORCHESTRATOR_SA:-$(gcloud iam service-accounts list --filter='displayName:Compute Engine default' --format='value(email)' --project=$PROJECT_ID)}"

# The service account used to authenticate tasks TO the worker
# Can be the same as ORCHESTRATOR_SA or a dedicated one
WORKER_INVOKER_SA="${WORKER_INVOKER_SA:-$ORCHESTRATOR_SA}"

echo "=== Cloud Tasks Setup for Audioura ==="
echo "Project:        $PROJECT_ID"
echo "Location:       $LOCATION"
echo "Queue:          $QUEUE_NAME"
echo "Orchestrator SA: $ORCHESTRATOR_SA"
echo "Worker Invoker SA: $WORKER_INVOKER_SA"
echo ""

# --- Step 1: Enable Cloud Tasks API ---
echo "[1/5] Enabling Cloud Tasks API..."
gcloud services enable cloudtasks.googleapis.com --project=$PROJECT_ID 2>/dev/null || true

# --- Step 2: Create the queue (idempotent — update if exists) ---
echo "[2/5] Creating/updating queue: $QUEUE_NAME..."
if gcloud tasks queues describe $QUEUE_NAME --location=$LOCATION --project=$PROJECT_ID >/dev/null 2>&1; then
    echo "  Queue already exists — updating..."
    gcloud tasks queues update $QUEUE_NAME \
        --location=$LOCATION \
        --max-dispatches-per-second=2 \
        --max-concurrent-dispatches=3 \
        --max-attempts=3 \
        --min-backoff=30s \
        --max-backoff=300s \
        --project=$PROJECT_ID
else
    echo "  Creating new queue..."
    gcloud tasks queues create $QUEUE_NAME \
        --location=$LOCATION \
        --max-dispatches-per-second=2 \
        --max-concurrent-dispatches=3 \
        --max-attempts=3 \
        --min-backoff=30s \
        --max-backoff=300s \
        --project=$PROJECT_ID
fi

# --- Step 3: IAM Binding #1 — Worker accepts tasks from the invoker SA ---
# Without this: every task dispatch gets 403 from the worker.
echo "[3/5] IAM: Granting run.invoker on tour-worker to $WORKER_INVOKER_SA..."
gcloud run services add-iam-policy-binding tour-worker \
    --region=$LOCATION \
    --member="serviceAccount:$WORKER_INVOKER_SA" \
    --role="roles/run.invoker" \
    --project=$PROJECT_ID 2>/dev/null || true

# --- Step 4: IAM Binding #2 — Orchestrator can enqueue tasks ---
# Without this: orchestrator's create_task() call gets permission-denied.
echo "[4/5] IAM: Granting cloudtasks.enqueuer to $ORCHESTRATOR_SA..."
gcloud tasks queues add-iam-policy-binding $QUEUE_NAME \
    --location=$LOCATION \
    --member="serviceAccount:$ORCHESTRATOR_SA" \
    --role="roles/cloudtasks.enqueuer" \
    --project=$PROJECT_ID 2>/dev/null || true

# --- Step 5: IAM Binding #3 — Orchestrator can mint OIDC token as the invoker SA ---
# Without this: create_task() fails when setting oidc_token.service_account_email.
# Only needed if WORKER_INVOKER_SA != ORCHESTRATOR_SA (if they're the same, skip).
if [ "$WORKER_INVOKER_SA" != "$ORCHESTRATOR_SA" ]; then
    echo "[5/5] IAM: Granting iam.serviceAccountUser on $WORKER_INVOKER_SA to $ORCHESTRATOR_SA..."
    gcloud iam service-accounts add-iam-policy-binding $WORKER_INVOKER_SA \
        --member="serviceAccount:$ORCHESTRATOR_SA" \
        --role="roles/iam.serviceAccountUser" \
        --project=$PROJECT_ID 2>/dev/null || true
else
    echo "[5/5] IAM: Orchestrator SA == Worker Invoker SA — serviceAccountUser binding not needed."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Queue configuration:"
echo "  - Max 2 tasks dispatched per second"
echo "  - Max 3 concurrent tasks (= 3 parallel tour generations)"
echo "  - Max 3 retry attempts on failure"
echo "  - Backoff: 30s → 300s"
echo ""
echo "IAM bindings configured:"
echo "  1. tour-worker accepts requests from $WORKER_INVOKER_SA (roles/run.invoker)"
echo "  2. $ORCHESTRATOR_SA can enqueue to $QUEUE_NAME (roles/cloudtasks.enqueuer)"
echo "  3. $ORCHESTRATOR_SA can mint tokens as $WORKER_INVOKER_SA (roles/iam.serviceAccountUser)"
echo ""
echo "Next steps:"
echo "  1. Deploy tour-worker:  gcloud run deploy tour-worker --source=. --dockerfile=Dockerfile.tour-worker --timeout=840 --min-instances=0 --max-instances=5 --concurrency=1 --no-allow-unauthenticated"
echo "  2. Set env vars on orchestrator:  GENERATION_MODE=cloud_tasks, JOB_STORE_MODE=database, TOUR_WORKER_URL=<worker-url>, WORKER_SERVICE_ACCOUNT=$WORKER_INVOKER_SA"
echo "  3. Remove always-on from orchestrator:  gcloud run services update tour-orchestrator --cpu-throttling --min-instances=0"
echo "  4. Test: generate a tour, verify Cloud Tasks dispatches to worker, /status returns completed"
