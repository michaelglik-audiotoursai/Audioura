#!/usr/bin/env bash
# run_local822_live.sh — LOCAL-822 live proof, two DISPOSABLE containers.
# NEVER an audioura-* container, never -p audioura, never the live DB (this probe
# makes no DB call and never writes it). BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-822
# TASK_BUDGET_USD=0.05, and each paid call uses max_tokens<=5.
#
#   RUN 1 — WITHOUT the meterlogs mount / identity: the LOCAL-822 container
#           meter-mount guard refuses the paid call before it is sent. $0 spent.
#   RUN 2 — WITH the full contract (meter_container_env.docker_meter_args): the
#           one tiny call goes out and its row lands in
#           ~/Audioura/meterlogs/paid_api_calls.jsonl with service=LOCAL-822.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
IMAGE="audioura-tour-generator:latest"
mkdir -p "${METER_DIR}"

common=(
  docker run --rm
  --memory 1g --cpus 1
)
# .env FIRST so our explicit -e below OVERRIDE anything it carries. (It currently
# has no DB_*/DATABASE_URL/DAILY_PAID_LIMIT_USD, but order-independence is safer.)
[ -f "${ENV_FILE}" ] && common+=(--env-file "${ENV_FILE}")
common+=(
  -e TASK_BUDGET_ID=LOCAL-822
  -e TASK_BUDGET_USD=0.05
  -e DB_HOST=127.0.0.1 -e DB_PORT=1 -e DB_NAME=none
  -e DB_USER=none -e DB_PASSWORD=none
)
# NOTE: DATABASE_URL is deliberately NOT set and DB_* point at a dead local port,
# so the meter's best-effort _db_write fails open instantly and NEVER touches any
# shared/live DB. The proof row lands ONLY in the host-mounted JSONL log.

echo "========================================================================"
echo "[local822] RUN 1 — WITHOUT the meterlogs mount -> expect REFUSED, \$0"
echo "========================================================================"
# Install the meter (PYTHONPATH=/opt/meter) so the guard is ACTIVE, but point
# PAID_API_LOG at an in-container-only path and set NO METER_SERVICE and NO
# meterlogs bind-mount. The guard must refuse. TASK_BUDGET_ID is set (budget), so
# identity is technically present — the refusal here is on the MISSING MOUNT.
run1=("${common[@]}"
  --name local822-nomount
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/tmp/ephemeral/paid_api_calls.jsonl
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${HERE}:/app" -w /app
  "${IMAGE}" python -u run_local822_container.py)
"${run1[@]}"
RC1=$?
echo "[local822] RUN 1 rc=${RC1}"

echo "========================================================================"
echo "[local822] RUN 2 — WITH the full contract -> expect CALL_SENT + a row"
echo "========================================================================"
# The canonical args meter_container_env.docker_meter_args() returns: bind-mount
# the shared meterlog dir, canonical PAID_API_LOG, meter installed, row tagged
# service=LOCAL-822.
run2=("${common[@]}"
  --name local822-contract
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-822
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}:/app" -w /app
  "${IMAGE}" python -u run_local822_container.py)
"${run2[@]}"
RC2=$?
echo "[local822] RUN 2 rc=${RC2}"

echo "########################################################################"
echo "[local822] DONE. Checking for the LOCAL-822 row in ${METER_DIR}/paid_api_calls.jsonl"
grep '"service": "LOCAL-822"' "${METER_DIR}/paid_api_calls.jsonl" | tail -3
exit 0
