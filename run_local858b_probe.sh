#!/usr/bin/env bash
# run_local858b_probe.sh — LOCAL-858B cheap second-authority probe in a DISPOSABLE
# container under project "local858b". No postgres, no DB write, no tour text —
# just the Serper /places second-authority resolution for the two requested
# landmarks with Wikidata BLOCKED. Metered + budget-capped (TASK_BUDGET_ID=
# LOCAL-858B, TASK_BUDGET_USD=0.35). NEVER an audioura-* container, never the
# live DB.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local858b"
TG_NAME="${PROJECT}-probe"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
TASK_BUDGET_DIR="${HOME}/.audioura_task_budgets"
mkdir -p "${METER_DIR}" "${TASK_BUDGET_DIR}"

cleanup () { docker rm -f "${TG_NAME}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

args=( docker run --rm --name "${TG_NAME}" --memory 2g --cpus 2 )
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(
  -e STORIED_MODE=true
  -e RESEARCH_BACKEND=serper
  -e K_SERVICE=local858b
  # Wikidata blocked; live lookup on so the second authority's live Serper fires.
  -e LANDMARK_LIVE_LOOKUP=1
  -e LANDMARK_WIKIDATA_BLOCKED=1
  # No DATABASE_URL on purpose — the probe uses use_cache=False, so no DB needed.
  -e DATABASE_URL=
)
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-858B
  -e AUDIOURA_TASK_BUDGET_DIR=/task_budgets
  -e TASK_BUDGET_ID=LOCAL-858B
  -e TASK_BUDGET_USD=0.35
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${TASK_BUDGET_DIR}:/task_budgets"
)
args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local858b_probe.py)

echo "[local858b] ===== running LOCAL-858B second-authority probe (cap \$0.35) ====="
"${args[@]}"
RC=${PIPESTATUS[0]}
echo "#################### LOCAL-858B probe done (rc=${RC}) ####################"
exit "${RC}"
