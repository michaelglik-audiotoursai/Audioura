#!/usr/bin/env bash
# run_local822_live.sh — LOCAL-822 / 822B live proof, DISPOSABLE containers.
# NEVER an audioura-* container, never -p audioura, never the live DB (this probe
# makes no DB call and never writes it). BUDGET ENFORCED: TASK_BUDGET_ID=LOCAL-822B
# TASK_BUDGET_USD=0.02, and each paid call uses max_tokens<=5. <= 2 tiny calls total.
#
#   RUN 1 — TASK RUN WITHOUT the meterlogs mount: the LOCAL-822 container
#           meter-mount guard refuses the paid call before it is sent. $0 spent.
#   RUN 2 — TASK RUN WITH the full contract (meter_container_env.docker_meter_args):
#           the one tiny call goes out and its row lands in
#           ~/Audioura/meterlogs/paid_api_calls.jsonl with service=LOCAL-822B.
#   RUN 3 — PRODUCTION (LOCAL-822B bounce): K_SERVICE=probe set (Cloud Run always
#           sets it), NO task id, NO mount. The guard must NOT arm, so the paid
#           call GOES THROUGH — proving the guard can never refuse production.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
IMAGE="audioura-tour-generator:latest"
mkdir -p "${METER_DIR}"

# Shared args for the TASK runs (1 & 2): the whole-task budget is armed.
common=(
  docker run --rm
  --memory 1g --cpus 1
)
# .env FIRST so our explicit -e below OVERRIDE anything it carries. (It currently
# has no DB_*/DATABASE_URL/DAILY_PAID_LIMIT_USD, but order-independence is safer.)
[ -f "${ENV_FILE}" ] && common+=(--env-file "${ENV_FILE}")
common+=(
  -e TASK_BUDGET_ID=LOCAL-822B
  -e TASK_BUDGET_USD=0.02
  -e DB_HOST=127.0.0.1 -e DB_PORT=1 -e DB_NAME=none
  -e DB_USER=none -e DB_PASSWORD=none
)
# NOTE: DATABASE_URL is deliberately NOT set and DB_* point at a dead local port,
# so the meter's best-effort _db_write fails open instantly and NEVER touches any
# shared/live DB. The proof row lands ONLY in the host-mounted JSONL log.

echo "========================================================================"
echo "[local822B] RUN 1 — TASK RUN WITHOUT the meterlogs mount -> expect REFUSED, \$0"
echo "========================================================================"
# Install the meter (PYTHONPATH=/opt/meter) so the guard is ACTIVE, but point
# PAID_API_LOG at an in-container-only path and set NO meterlogs bind-mount.
# TASK_BUDGET_ID=LOCAL-822B ARMS the guard; the mount is missing -> refuse.
run1=("${common[@]}"
  --name local822b-nomount
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/tmp/ephemeral/paid_api_calls.jsonl
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${HERE}:/app" -w /app
  "${IMAGE}" python -u run_local822_container.py)
"${run1[@]}"
RC1=$?
echo "[local822B] RUN 1 rc=${RC1}"

echo "========================================================================"
echo "[local822B] RUN 2 — TASK RUN WITH the full contract -> expect CALL_SENT + a row"
echo "========================================================================"
# The canonical args meter_container_env.docker_meter_args() returns: bind-mount
# the shared meterlog dir, canonical PAID_API_LOG, meter installed, row tagged
# service=LOCAL-822B.
run2=("${common[@]}"
  --name local822b-contract
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-822B
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
  -v "${HERE}:/app" -w /app
  "${IMAGE}" python -u run_local822_container.py)
"${run2[@]}"
RC2=$?
echo "[local822B] RUN 2 rc=${RC2}"

echo "========================================================================"
echo "[local822B] RUN 3 — PRODUCTION (K_SERVICE set, NO task id, NO mount) -> expect CALL_SENT"
echo "========================================================================"
# The bounce proof: the meter is baked into the image, so it runs on Cloud Run
# too. K_SERVICE=probe (Cloud Run always sets it) + NO TASK_BUDGET_ID + NO
# METER_SERVICE -> the guard is NOT armed and the paid call GOES THROUGH even with
# no meterlogs mount. We deliberately do NOT include the common[] task env here.
run3=(docker run --rm --memory 1g --cpus 1)
[ -f "${ENV_FILE}" ] && run3+=(--env-file "${ENV_FILE}")
run3+=(
  --name local822b-production
  -e K_SERVICE=probe
  -e DB_HOST=127.0.0.1 -e DB_PORT=1 -e DB_NAME=none
  -e DB_USER=none -e DB_PASSWORD=none
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/tmp/ephemeral/paid_api_calls.jsonl
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${HERE}:/app" -w /app
  "${IMAGE}" python -u run_local822_container.py)
"${run3[@]}"
RC3=$?
echo "[local822B] RUN 3 rc=${RC3}"

echo "########################################################################"
echo "[local822B] DONE. Checking for the LOCAL-822B row in ${METER_DIR}/paid_api_calls.jsonl"
grep '"service": "LOCAL-822B"' "${METER_DIR}/paid_api_calls.jsonl" | tail -3
exit 0
