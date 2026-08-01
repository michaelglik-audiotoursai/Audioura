#!/usr/bin/env bash
# verify-tourquality.sh — One-command tour quality verification loop
# ==================================================================
# Brings up the tourquality stack, generates a tour, scores it, tears down.
#
# Usage:
#   ./verify-tourquality.sh "Nice France walking" 8
#   ./verify-tourquality.sh "Boston historical" 6
#
# Arguments:
#   $1 — Tour location/request string (required)
#   $2 — Number of stops (default: 8)
#
# The script:
#   1. Builds and starts tourquality-* containers from the current worktree
#   2. Waits for health checks to pass
#   3. Generates a tour via the tourquality orchestrator (port 5202)
#   4. Scores it with tour_rubric_scorer.py
#   5. Tears down tourquality-* containers
#   6. Reports cost from api_call_log.jsonl
#
# Prerequisites:
#   - .env with OPENAI_API_KEY and SERP_API_KEY
#   - Shared postgres (development-postgres-2-1) running
#   - development_default network exists
#
# Safety:
#   - TOUR_TEST_MODE=true ensures generated tours are flagged is_test
#   - Never touches audioura-* containers
#   - Cleanup on exit (trap)

set -euo pipefail

LOCATION="${1:?Usage: $0 \"location\" [stops]}"
STOPS="${2:-8}"
COMPOSE_FILE="docker-compose-tourquality.yml"
ORCHESTRATOR_URL="http://localhost:5202"
GENERATOR_URL="http://localhost:5200"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[tourquality]${NC} $*"; }
warn()  { echo -e "${YELLOW}[tourquality]${NC} $*"; }
error() { echo -e "${RED}[tourquality]${NC} $*" >&2; }

# Ensure cleanup on exit
cleanup() {
    info "Tearing down tourquality stack..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
    info "Teardown complete."
}
trap cleanup EXIT

# --- Pre-flight checks ---
info "Pre-flight checks..."

if ! docker network inspect development_default &>/dev/null; then
    error "development_default network not found. Start the main stack first."
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -q "development-postgres-2-1"; then
    error "Postgres container (development-postgres-2-1) not running."
    exit 1
fi

# Record row count before
ROW_COUNT_BEFORE=$(docker exec development-postgres-2-1 \
    psql -U admin -d audiotours -t -c "SELECT COUNT(*) FROM audio_tours;" | tr -d ' ')
info "Row count before: $ROW_COUNT_BEFORE"

# Record shared container state
info "Shared container state (before):"
docker ps --format "table {{.Names}}\t{{.ID}}\t{{.Image}}" | \
    grep -E "audioura-tour-generator|audioura-tour-orchestrator|audioura-map-delivery" || true

# --- Build and start ---
info "Building tourquality stack from current worktree ($(pwd))..."
docker compose -f "$COMPOSE_FILE" build --quiet

info "Starting tourquality stack..."
docker compose -f "$COMPOSE_FILE" up -d

# --- Wait for health ---
info "Waiting for tourquality-generator health..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:5200/health &>/dev/null; then
        info "Generator healthy after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        error "Generator failed to become healthy after 60s"
        docker compose -f "$COMPOSE_FILE" logs tourquality-generator | tail -20
        exit 1
    fi
    sleep 1
done

info "Waiting for tourquality-orchestrator health..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:5202/health &>/dev/null; then
        info "Orchestrator healthy after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then
        error "Orchestrator failed to become healthy after 60s"
        docker compose -f "$COMPOSE_FILE" logs tourquality-orchestrator | tail -20
        exit 1
    fi
    sleep 1
done

# --- Generate tour ---
info "Generating tour: '$LOCATION' with $STOPS stops..."
info "(This may take 2-5 minutes depending on API response times)"

GENERATE_RESPONSE=$(curl -s -X POST "$ORCHESTRATOR_URL/generate-complete-tour" \
    -H "Content-Type: application/json" \
    -d "{
        \"location\": \"$LOCATION\",
        \"tour_type\": \"walking\",
        \"total_stops\": $STOPS,
        \"request_string\": \"$LOCATION\",
        \"user_id\": \"test-mac-mini\"
    }")

JOB_ID=$(echo "$GENERATE_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('job_id',''))" 2>/dev/null || echo "")

if [ -z "$JOB_ID" ]; then
    error "Failed to start generation. Response: $GENERATE_RESPONSE"
    exit 1
fi

info "Job started: $JOB_ID"

# Poll for completion
TOUR_FILE=""
for i in $(seq 1 120); do
    STATUS_RESPONSE=$(curl -s "$ORCHESTRATOR_URL/status/$JOB_ID" 2>/dev/null || echo '{"status":"unknown"}')
    STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")
    
    if [ "$STATUS" = "completed" ] || [ "$STATUS" = "complete" ]; then
        TOUR_FILE=$(echo "$STATUS_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Try various fields where the tour text path might be
for key in ['tour_file', 'output_file', 'tour_text_file', 'result']:
    if key in data and data[key]:
        print(data[key])
        break
" 2>/dev/null || echo "")
        info "Generation complete!"
        break
    elif [ "$STATUS" = "failed" ] || [ "$STATUS" = "error" ]; then
        error "Generation failed: $STATUS_RESPONSE"
        exit 1
    fi
    
    if [ $((i % 10)) -eq 0 ]; then
        PROGRESS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress','...'))" 2>/dev/null || echo "...")
        info "  Status: $STATUS — $PROGRESS (${i}s)"
    fi
    sleep 2
done

if [ "$STATUS" != "completed" ] && [ "$STATUS" != "complete" ]; then
    error "Generation timed out after 240s. Last status: $STATUS"
    exit 1
fi

# --- Find the generated tour text for scoring ---
# Look for the most recently modified .txt in tours/
LATEST_TOUR=$(find tours/ -name "*.txt" -newer "$COMPOSE_FILE" -type f 2>/dev/null | \
    head -1 || echo "")

if [ -z "$LATEST_TOUR" ] && [ -n "$TOUR_FILE" ]; then
    LATEST_TOUR="$TOUR_FILE"
fi

if [ -z "$LATEST_TOUR" ]; then
    # Fall back: find most recent tour text file
    LATEST_TOUR=$(find tours/ -name "*tour*.txt" -type f -exec ls -t {} + 2>/dev/null | head -1 || echo "")
fi

# --- Score ---
if [ -n "$LATEST_TOUR" ] && [ -f "$LATEST_TOUR" ]; then
    info "Scoring tour: $LATEST_TOUR"
    echo "---"
    python3 tour_rubric_scorer.py "$LATEST_TOUR" --n "$STOPS" || warn "Scorer returned non-zero (manual classification needed)"
    echo "---"
else
    warn "Could not locate tour text file for scoring."
    warn "  Check tours/ directory manually. Job response: $STATUS_RESPONSE"
fi

# --- Cost report ---
info "Cost report:"
if [ -f "api_call_log.jsonl" ]; then
    # Sum costs from log entries created during this run
    python3 -c "
import json, sys
from datetime import datetime, timedelta

total_cost = 0.0
entries = 0
with open('api_call_log.jsonl') as f:
    for line in f:
        try:
            entry = json.loads(line)
            cost = entry.get('cost', entry.get('total_cost', 0))
            if cost:
                total_cost += float(cost)
                entries += 1
        except:
            pass
# Show last N entries as likely from this run
print(f'  Total logged cost: \${total_cost:.4f} ({entries} entries)')
" 2>/dev/null || warn "Could not parse cost log"
else
    warn "No api_call_log.jsonl found. Check container logs for cost data."
    docker compose -f "$COMPOSE_FILE" logs tourquality-generator 2>/dev/null | \
        grep -i "cost\|total_cost\|usage" | tail -5 || true
fi

# --- Post-generation verification ---
ROW_COUNT_AFTER=$(docker exec development-postgres-2-1 \
    psql -U admin -d audiotours -t -c "SELECT COUNT(*) FROM audio_tours;" | tr -d ' ')
info "Row count after: $ROW_COUNT_AFTER (was $ROW_COUNT_BEFORE)"

# Verify is_test flag on new rows
if [ "$ROW_COUNT_AFTER" -gt "$ROW_COUNT_BEFORE" ]; then
    NEW_ROWS_TEST=$(docker exec development-postgres-2-1 \
        psql -U admin -d audiotours -t -c \
        "SELECT COUNT(*) FROM audio_tours WHERE id > (SELECT MAX(id) - ($ROW_COUNT_AFTER - $ROW_COUNT_BEFORE) FROM audio_tours) AND is_test = TRUE;" | tr -d ' ')
    info "New rows with is_test=TRUE: $NEW_ROWS_TEST"
fi

# --- Shared containers untouched ---
info "Shared container state (after generation, before teardown):"
docker ps --format "table {{.Names}}\t{{.ID}}\t{{.Image}}" | \
    grep -E "audioura-tour-generator|audioura-tour-orchestrator|audioura-map-delivery" || true

info "Done. Stack will be torn down now (trap)."
