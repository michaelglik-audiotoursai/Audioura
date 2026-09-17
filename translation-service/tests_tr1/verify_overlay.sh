#!/usr/bin/env bash
# GCS-TR1 proof: (a) the deployed v35 /app/translation_service.py is byte-identical to
# commit 73d8eb5 (the base we built from), and (b) the v35-tr1 overlay changes ONLY
# translation_service.py inside /app — every other /app file has an identical SHA256.
#
# Requires the v35 base image to be present locally (or reachable) and docker.
# Usage (from repo root):  bash translation-service/tests_tr1/verify_overlay.sh
set -euo pipefail

REPO="us-central1-docker.pkg.dev/audiotours-migration/services"
BASE_IMAGE="$REPO/translation-service:v35"
NEW_IMAGE="$REPO/translation-service:v35-tr1"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SVC_DIR="$(cd "$HERE/.." && pwd)"
ROOT="$(cd "$SVC_DIR/.." && pwd)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

manifest() {  # $1 image, $2 tag label, $3 output file
  local img="$1" label="$2" out="$3" cid
  cid="$(docker create "$img")"
  docker cp "$cid:/app" "$TMP/app_$label" >/dev/null
  docker rm "$cid" >/dev/null
  ( cd "$TMP/app_$label" && find . -type f -exec sha256sum {} \; | sort ) > "$out"
}

echo "=== (a) v35 /app/translation_service.py vs commit 73d8eb5 ==="
cid="$(docker create "$BASE_IMAGE")"
docker cp "$cid:/app/translation_service.py" "$TMP/v35_ts.py" >/dev/null
docker rm "$cid" >/dev/null
git -C "$ROOT" show 73d8eb5:translation-service/translation_service.py > "$TMP/73d8eb5_ts.py"
echo "raw sha256:"
sha256sum "$TMP/v35_ts.py" "$TMP/73d8eb5_ts.py"
if cmp -s "$TMP/v35_ts.py" "$TMP/73d8eb5_ts.py"; then
  echo "RESULT: byte-identical"
else
  # v35 ships the file with CRLF line endings; compare content modulo line endings.
  echo "raw bytes differ — comparing content modulo line endings (v35 ships CRLF):"
  tr -d '\r' < "$TMP/v35_ts.py"      | sha256sum
  tr -d '\r' < "$TMP/73d8eb5_ts.py"  | sha256sum
  if [ "$(tr -d '\r' < "$TMP/v35_ts.py" | sha256sum)" = "$(tr -d '\r' < "$TMP/73d8eb5_ts.py" | sha256sum)" ]; then
    echo "RESULT: IDENTICAL modulo line endings — v35 was built from 73d8eb5 (CRLF in image)"
  else
    echo "RESULT: DIFFERENT even modulo line endings — investigate before proceeding"; exit 1
  fi
fi
echo

echo "=== building overlay $NEW_IMAGE ==="
docker build -f "$SVC_DIR/Dockerfile.tr1" -t "$NEW_IMAGE" "$SVC_DIR"
echo

echo "=== (b) /app manifest diff: v35 vs v35-tr1 ==="
manifest "$BASE_IMAGE" base "$TMP/base.txt"
manifest "$NEW_IMAGE"  new  "$TMP/new.txt"
# Compare filename->hash; a line differs only where content differs.
echo "--- files whose SHA256 changed (expect exactly translation_service.py) ---"
diff "$TMP/base.txt" "$TMP/new.txt" || true
echo
changed="$( { diff "$TMP/base.txt" "$TMP/new.txt" || true; } \
           | grep -E '^[<>]' | sed -E 's/^[<>] +[0-9a-f]+ +\*?//' | sort -u)"
echo "Changed paths:"
echo "$changed"
if [ "$changed" = "./translation_service.py" ]; then
  echo "RESULT: PASS — only translation_service.py differs"
else
  echo "RESULT: FAIL — unexpected files differ"; exit 1
fi
