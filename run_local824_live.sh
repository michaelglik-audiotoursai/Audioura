#!/usr/bin/env bash
# run_local824_live.sh — LOCAL-824 live proof that /geocode works on the ACTUAL
# Cloud Run map-delivery image.
#
# WHAT IT DOES
# Builds the map-delivery image FROM ITS OWN Dockerfile (context ./map_delivery,
# CMD `python app.py` — the exact image the cloud runs), tags it
# `local824-map-delivery` (NEVER an audioura-* / shared tag), and runs it as its
# OWN disposable container `local824-md` on a spare port (5824), with its OWN
# throwaway postgres (local824-postgres) so the live DB is never touched. It then
# calls GET /geocode for "Mui Ne" and "Venice, FL" — the two places in the
# ticket — which is at most 2 paid Serper queries (<= 4, the cap).
#
# [LOCAL-822] THE METER CONTRACT. This is a Kiro task run (TASK_BUDGET_ID set),
# so the baked-in meter guard REQUIRES the meterlog bind-mount or it refuses the
# paid call, $0 spent. We carry the canonical args from
# meter_container_env.docker_meter_args(task_id="LOCAL-824"): bind-mount
# ~/Audioura/meterlogs -> /meterlogs, canonical PAID_API_LOG, METER_SERVICE, and
# install the meter via PYTHONPATH=/opt/meter. So /geocode's Serper call lands
# exactly one paid_api_calls row on the HOST, tagged service=LOCAL-824.
#
# BUDGET: TASK_BUDGET_ID=LOCAL-824 TASK_BUDGET_USD=0.05 (two Serper Places
# queries at ~$0.001 each = ~$0.002, far under the cap).
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="local824"
NET="${PROJECT}_default"
PG_NAME="${PROJECT}-postgres"
MD_NAME="${PROJECT}-md"
IMAGE="local824-map-delivery:latest"      # OWN tag, never audioura-*
PORT=5824                                 # spare host port
ENV_FILE="/Users/micha/Audioura/.env"
METER_DIR="/Users/micha/Audioura/meterlogs"
mkdir -p "${METER_DIR}"

cleanup () {
  docker rm -f "${MD_NAME}" "${PG_NAME}" >/dev/null 2>&1 || true
  docker network rm "${NET}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[local824] building the map-delivery image from ./map_delivery (its own Dockerfile → app.py)"
docker build -t "${IMAGE}" "${HERE}/map_delivery" >/tmp/local824_build.log 2>&1 || {
  echo "BUILD FAILED — tail of /tmp/local824_build.log:"; tail -30 /tmp/local824_build.log; exit 1; }
echo "[local824] build OK"

echo "[local824] creating isolated network ${NET}"
docker network create "${NET}" >/dev/null 2>&1 || true

echo "[local824] starting throwaway postgres ${PG_NAME} (own data, never the live DB)"
docker rm -f "${PG_NAME}" >/dev/null 2>&1 || true
docker run -d --name "${PG_NAME}" --network "${NET}" \
  -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=password123 \
  -e POSTGRES_DB=audiotours \
  postgres:15 >/dev/null
for i in $(seq 1 20); do
  docker exec "${PG_NAME}" pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 1
done

# --- SERP key (value stays in the container env only; never echoed) ----------
SERP_KEY="$(grep -E '^SERP_API_KEY=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '"'"'"'' | tr -d '\r')"
if [ -z "${SERP_KEY}" ]; then
  echo "[local824] WARNING: no SERP_API_KEY in ${ENV_FILE}; /geocode will fall back to Nominatim (free)."
fi
KEY_SUFFIX="${SERP_KEY: -4}"

args=(
  docker run -d --name "${MD_NAME}"
  --network "${NET}"
  -p "${PORT}:5005"
  -e DATABASE_URL=postgresql://admin:password123@${PG_NAME}:5432/audiotours
  -e DB_HOST="${PG_NAME}" -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e SERP_API_KEY="${SERP_KEY}"
  -e TASK_BUDGET_ID=LOCAL-824
  -e TASK_BUDGET_USD=0.05
)
# [LOCAL-822] canonical meter args — bind-mount the shared meterlog dir, canonical
# log, service tag, install the meter via PYTHONPATH=/opt/meter.
args+=(
  -e PYTHONPATH=/opt/meter
  -e PAID_API_LOG=/meterlogs/paid_api_calls.jsonl
  -e METER_SERVICE=LOCAL-824
  -e METER_KEY_SUFFIX="${KEY_SUFFIX}"
  -v "${HERE}/_meter:/opt/meter:ro"
  -v "${METER_DIR}:/meterlogs"
)
args+=("${IMAGE}")

echo "[local824] starting map-delivery container ${MD_NAME} on :${PORT}"
"${args[@]}" >/dev/null

# Wait for /health
echo "[local824] waiting for /health ..."
HEALTHY=0
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then HEALTHY=1; break; fi
  sleep 1
done
if [ "${HEALTHY}" != "1" ]; then
  echo "[local824] container did not become healthy; logs:"; docker logs "${MD_NAME}" 2>&1 | tail -40; exit 1
fi
echo "[local824] healthy."

echo ""
echo "########## GET /geocode?q=Mui Ne ##########"
curl -sS "http://localhost:${PORT}/geocode?q=Mui%20Ne" ; echo
echo ""
echo "########## GET /geocode?q=Venice, FL ##########"
curl -sS "http://localhost:${PORT}/geocode?q=Venice,%20FL" ; echo
echo ""

echo "[local824] container stdout (GEOCODE lines show which path resolved):"
docker logs "${MD_NAME}" 2>&1 | grep -i "GEOCODE\|geocod" | tail -20

echo ""
echo "########## meter rows for service=LOCAL-824 ##########"
grep '"service": "LOCAL-824"' "${METER_DIR}/paid_api_calls.jsonl" 2>/dev/null | tail -10 || \
  grep 'LOCAL-824' "${METER_DIR}/paid_api_calls.jsonl" 2>/dev/null | tail -10 || \
  echo "(no LOCAL-824 rows yet — check the file)"

echo ""
echo "#################### LOCAL-824 live run done ####################"
