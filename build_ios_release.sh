#!/bin/bash
# Build the iOS release IPA with the build-time secrets baked in.
#
# WHY THIS SCRIPT EXISTS (2026-09-16): build 24 was produced with a plain
# `flutter build ipa --release`. `Endpoints._builtInApiKey` is a
# `String.fromEnvironment('GATEWAY_API_KEY')` compile-time constant, so without
# --dart-define it compiled to "", the app sent no X-API-Key header, and every
# gateway call returned 401 — surfaced to the user as "Audioura couldn't connect
# securely." The Android path (build_flutter_clean.sh) already fails fast on
# this; iOS had no equivalent. Now it does.
set -euo pipefail

APP_DIR="$HOME/Audioura/audio_tour_app"
SECRETS="$HOME/Audioura/build_secrets.env"

if [ ! -f "$SECRETS" ]; then
  echo "ERROR: $SECRETS not found."
  echo "Create it in Terminal (never paste the value into a chat session):"
  echo "    printf 'GATEWAY_API_KEY=%s\\n' 'THE-KEY' > $SECRETS && chmod 600 $SECRETS"
  echo "The canonical value lives on the api-gateway Cloud Run service"
  echo "(Secret Manager / env API_KEY) and in Google Password Manager."
  exit 1
fi
. "$SECRETS"

if [ -z "${GATEWAY_API_KEY:-}" ]; then
  echo "ERROR: GATEWAY_API_KEY is empty in $SECRETS."
  echo "An IPA built now would 401 on every gateway call. Refusing."
  exit 1
fi

cd "$APP_DIR"
echo "Building $(grep '^version:' pubspec.yaml)"
flutter build ipa --release --dart-define=GATEWAY_API_KEY="$GATEWAY_API_KEY"

echo
echo "Built. Upload with:  bash ~/Audioura/upload_testflight.sh"
