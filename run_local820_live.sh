#!/usr/bin/env bash
# run_local820_live.sh — LOCAL-820 LIVE meter proof in a DISPOSABLE container.
# NEVER an audioura-* container, never -p audioura, never the live DB, no tours.
# One isolated `docker run --rm` making <= 2 tiny OpenAI calls (max_tokens=5)
# through the REAL metered path, to prove the rows land in ~/Audioura/meterlogs
# tagged service=LOCAL-820 — the fix for the ~16k unmetered calls.
#
# BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-820 TASK_BUDGET_USD=0.10 (the meter's raw
# paid door refuses paid calls once the recorded total reaches it).
#
# Carries the [LOCAL-820] meter contract (exactly what
# meter_container_env.docker_meter_args() returns). Optional METER_KEY_SUFFIX is
# passed through so rows line up with the provider usage page per key.
#
# Usage: ./run_local820_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local820"
TG_NAME="${PROJECT}-tg"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
BUDGET_DIR="/Users/micha/.audioura_task_budgets"   # host dir task_budget_report.py reads by default
mkdir -p "${METER_DIR}" "${BUDGET_DIR}"

cleanup () { docker rm -f "${TG_NAME}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

args=(
  docker run --rm --name "${TG_NAME}"
  --memory 1g --cpus 1
)
# .env FIRST (brings OPENAI_API_KEY); our explicit -e below override it.
[ -f "${ENV_FILE}" ] && args+=(--env-file "${ENV_FILE}")
args+=(
  -e NARRATION_MODEL=gpt-4.1-mini
  -e TASK_BUDGET_ID=LOCAL-820
  -e TASK_BUDGET_USD=0.10
  -e AUDIOURA_TASK_BUDGET_DIR=/task_budgets
)
# [LOCAL-820] THE METER CONTRACT — the canonical args from
# meter_container_env.docker_meter_args(task_id="LOCAL-820", meter_dir=_meter,
# host_meter_dir=~/Audioura/meterlogs, key_suffix=<last few of key>).
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-820
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${BUDGET_DIR}:/task_budgets"
)
[ -n "${METER_KEY_SUFFIX:-}" ] && args+=(-e "METER_KEY_SUFFIX=${METER_KEY_SUFFIX}")

args+=(-v "${HERE}:/app" -w /app)
args+=(audioura-tour-generator:latest python -u run_local820_container.py)

echo "[local820] ===== live meter proof, cap \$0.10, metered to ${METER_DIR} ====="
"${args[@]}"
RC=${PIPESTATUS[0]}

echo "#################### LOCAL-820 live proof done (rc=${RC}) ####################"
exit "${RC}"
