#!/usr/bin/env bash
# GCS-TR1 RED proof: reproduce the historic failures on the deployed v35 baseline
# (byte-identical to commit 73d8eb5), using the same local Postgres + MinIO stack.
#
# Usage (from translation-service/):  bash tests_tr1/prove_red.sh
# Exits non-zero when the failures are reproduced (that is the expected "red").
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_DIR="$(cd "$HERE/.." && pwd)"
COMPOSE="$HERE/docker-compose.test.yml"
PROJECT="gcs-tr1-red"
V35="$SVC_DIR/_v35_translation_service.py"

cleanup() {
  echo "--- tearing down red stack ---"
  docker compose -p "$PROJECT" -f "$COMPOSE" down -v --remove-orphans || true
  rm -f "$V35"
}
trap cleanup EXIT

echo "--- extracting v35 baseline (73d8eb5) ---"
git -C "$SVC_DIR/.." show 73d8eb5:translation-service/translation_service.py > "$V35"

echo "--- bringing up Postgres + MinIO ---"
docker compose -p "$PROJECT" -f "$COMPOSE" up -d

for _ in $(seq 1 40); do
  docker compose -p "$PROJECT" -f "$COMPOSE" exec -T tr1-postgres pg_isready -U admin -d audiotours >/dev/null 2>&1 && break
  sleep 1
done
for _ in $(seq 1 40); do
  curl -sf http://127.0.0.1:9010/minio/health/live >/dev/null 2>&1 && break
  sleep 1
done

export DB_HOST=127.0.0.1 DB_PORT=55432 DB_NAME=audiotours DB_USER=admin DB_PASSWORD=password123
export BLOB_STORAGE_TYPE=r2 R2_ENDPOINT=http://127.0.0.1:9010 R2_ACCESS_KEY_ID=minioadmin \
       R2_SECRET_ACCESS_KEY=minioadmin R2_BUCKET=v1-audiotours-r2-bucket
export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1

cd "$SVC_DIR"

# ensure the bucket exists
python - <<'PY'
from blobstorage import R2BlobStorage
s = R2BlobStorage()
try:
    s.client.create_bucket(Bucket=s.bucket)
except Exception:
    pass
PY

echo "--- running RED proof against v35 ---"
python tests_tr1/prove_red_v35.py
rc=$?
echo "prove_red_v35.py exit=$rc (non-zero == failures reproduced, as expected)"
exit "$rc"
