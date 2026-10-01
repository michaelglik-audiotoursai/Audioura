#!/bin/bash
# gateway_key_check.sh — sourced by every script that bakes GATEWAY_API_KEY into an app.
#
# WHY (2026-10-01): an empty key was already caught, but a WRONG key was not, and a
# script that never passed the key at all (install_to_iphone.sh) slipped through
# entirely. Michael's iPhone then got 401 on every Preview call with
# "Sync failed: ClientException ... 401". The gateway cannot tell you which one
# happened; the build can.
#
# Compares a fingerprint of the key, never the key itself, so nothing secret is
# printed or committed. The pinned value is the live Secret Manager
# `gateway-api-key` (one version, created 2026-06-06). If that secret is ever
# rotated, update EXPECTED_* here in the same commit as build_secrets.env.
#
# Usage:  . gateway_key_check.sh   (after build_secrets.env has been sourced)
#         fails the calling script with exit 1 on any mismatch.

EXPECTED_GATEWAY_KEY_FP="1b56f014a180"   # sha256 prefix, 12 hex chars
EXPECTED_GATEWAY_KEY_LEN=21

if [ -z "${GATEWAY_API_KEY:-}" ]; then
  echo "ERROR: GATEWAY_API_KEY is empty. A build now would 401 on every gateway call. Refusing." >&2
  exit 1
fi

_gk_fp=$(printf '%s' "$GATEWAY_API_KEY" | shasum -a 256 | cut -c1-12)
if [ "$_gk_fp" != "$EXPECTED_GATEWAY_KEY_FP" ] || [ "${#GATEWAY_API_KEY}" -ne "$EXPECTED_GATEWAY_KEY_LEN" ]; then
  echo "ERROR: GATEWAY_API_KEY does not match the live gateway key." >&2
  echo "       got fingerprint $_gk_fp (len ${#GATEWAY_API_KEY}), expected $EXPECTED_GATEWAY_KEY_FP (len $EXPECTED_GATEWAY_KEY_LEN)." >&2
  echo "       A build now would 401 on every gateway call. Refusing." >&2
  echo "       Fix build_secrets.env from Secret Manager: gcloud secrets versions access latest --secret=gateway-api-key" >&2
  exit 1
fi
echo "✓ GATEWAY_API_KEY fingerprint matches the live gateway ($_gk_fp)"
unset _gk_fp
