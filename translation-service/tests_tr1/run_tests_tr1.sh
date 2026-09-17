#!/usr/bin/env bash
# GCS-TR1 red -> green harness.
#
# Brings up a local Postgres + MinIO (R2 stand-in), runs the pytest suite against
# translation-service, then tears the stack down. External AWS calls are patched in
# the tests, so no cloud credentials and no spend are involved.
#
# Usage (from translation-service/):   bash tests_tr1/run_tests_tr1.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_DIR="$(cd "$HERE/.." && pwd)"
COMPOSE="$HERE/docker-compose.test.yml"
PROJECT="gcs-tr1-test"

cleanup() {
  echo "--- tearing down test stack ---"
  docker compose -p "$PROJECT" -f "$COMPOSE" down -v --remove-orphans || true
}
trap cleanup EXIT

echo "--- bringing up Postgres + MinIO ---"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d

echo "--- waiting for Postgres ---"
for _ in $(seq 1 40); do
  if docker compose -p "$PROJECT" -f "$COMPOSE" exec -T tr1-postgres pg_isready -U admin -d audiotours >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "--- waiting for MinIO ---"
for _ in $(seq 1 40); do
  if curl -sf http://127.0.0.1:9010/minio/health/live >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# --- env the service + tests read (local Postgres, MinIO as R2) ---
export DB_HOST=127.0.0.1
export DB_PORT=55432
export DB_NAME=audiotours
export DB_USER=admin
export DB_PASSWORD=password123

export BLOB_STORAGE_TYPE=r2
export R2_ENDPOINT=http://127.0.0.1:9010
export R2_ACCESS_KEY_ID=minioadmin
export R2_SECRET_ACCESS_KEY=minioadmin
export R2_BUCKET=v1-audiotours-r2-bucket

# AWS SDK must never reach real endpoints even though methods are patched.
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1

echo "--- running pytest ---"
cd "$SVC_DIR"
python -m pytest tests_tr1/test_translation_tr1.py -v "$@"
