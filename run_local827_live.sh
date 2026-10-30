#!/usr/bin/env bash
# run_local827_live.sh — LOCAL-827 live acceptance: WHOLE-TASK budget ENFORCED
# ACROSS two isolated --rm containers under ONE task id.
#
# Runs run_local827_container.py in TWO separate `docker run --rm` containers
# (local827-tg-1, local827-tg-2) — NEVER an audioura-* container, never the live
# DB. Both carry the SAME TASK_BUDGET_ID=LOCAL-827 / TASK_BUDGET_USD=0.0002. Each
# makes tiny OpenAI calls (max_tokens=1) through the baked-in meter.
#
# THE WHOLE POINT (the bug 827 fixes): the meter rows AND the whole-task spend
# now accumulate on the HOST across both --rm containers. Container 1 spends up
# toward the $0.0002 cap; container 2 reads container 1's spend from the shared
# meter log and is REFUSED almost immediately. Before 827 the ledger lived inside
# each --rm container and every run restarted from $0 (LOCAL-821B $0.81 vs $0.40).
#
# THE METER CONTRACT (LOCAL-819/820/827) — the canonical args from
# meter_container_env.docker_meter_args(task_id="LOCAL-827", meter_dir=.../_meter,
# host_task_budget_dir=~/.audioura_task_budgets, task_budget_usd=0.0002):
#   -e PYTHONPATH=/opt/meter
#   -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
#   -e METER_SERVICE=LOCAL-827
#   -e AUDIOURA_TASK_BUDGET_DIR=/task_budgets            [LOCAL-827]
#   -e TASK_BUDGET_ID=LOCAL-827 -e TASK_BUDGET_USD=0.0002 [LOCAL-827 cap armed]
#   -v <repo>/_meter:/opt/meter:ro
#   -v ~/Audioura/meterlogs:/meterlogs
#   -v ~/.audioura_task_budgets:/task_budgets            [LOCAL-827]
#
# Usage: ./run_local827_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TASK="LOCAL-827"
BUDGET="0.0002"
IMAGE="audioura-tour-generator:latest"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="${HOME}/Audioura/meterlogs"        # host dir meter_report.py sweeps
BUDGET_DIR="${HOME}/.audioura_task_budgets"    # host whole-task ledger dir (827)
mkdir -p "${METER_DIR}" "${BUDGET_DIR}"

cleanup () {
  docker rm -f local827-tg-1 local827-tg-2 >/dev/null 2>&1 || true
}
trap cleanup EXIT

run_one () {
  local name="$1" label="$2"
  local args=(
    docker run --rm --name "${name}"
    --memory 1g --cpus 1
  )
  [ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
  # [LOCAL-827] THE METER CONTRACT — exactly what
  # meter_container_env.docker_meter_args() returns. Keep in lock-step with it.
  args+=(
    -e PYTHONPATH=/opt/meter
    -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
    -e METER_SERVICE=LOCAL-827
    -e AUDIOURA_TASK_BUDGET_DIR=/task_budgets
    -e TASK_BUDGET_ID=LOCAL-827
    -e TASK_BUDGET_USD="${BUDGET}"
    -v "${HERE}/_meter:/opt/meter:ro"
    -v "${METER_DIR}:/meterlogs"
    -v "${BUDGET_DIR}:/task_budgets"
  )
  [ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")
  args+=(-v "${HERE}:/app" -w /app)
  args+=("${IMAGE}" python -u run_local827_container.py "${label}")
  echo "######## LOCAL-827 container ${label} (${name}) ########"
  "${args[@]}"
  echo "######## container ${label} done (rc=$?) ########"
}

echo "===== LOCAL-827 LIVE: whole-task cap \$${BUDGET} across TWO --rm containers ====="
echo "[local827] meter log: ${METER_DIR}/paid_api_calls.jsonl   ledger dir: ${BUDGET_DIR}"
echo

run_one local827-tg-1 run1
echo
run_one local827-tg-2 run2

echo
echo "===== PROOF (host-side, reads only) ====="
echo "--- meter_report.py --since today, service totals ---"
python3 "${HERE}/meter_report.py" --since "$(date -u +%Y-%m-%d)" --kind openai || true
echo
echo "--- task_budget_report.py ${TASK} (meter-log fallback) ---"
AUDIOURA_METERLOG_DIR="${METER_DIR}" python3 "${HERE}/task_budget_report.py" "${TASK}"
echo "task_budget_report exit=$?"
