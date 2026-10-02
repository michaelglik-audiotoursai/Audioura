#!/bin/bash
# Upload the built iOS IPA to TestFlight via the App Store Connect API.
#
# Credentials: an App Store Connect API key. The PRIVATE part is the .p8 file at
#   ~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8
# which altool finds by itself. The Key ID and Issuer ID are identifiers, not
# secrets, and live in .appstoreconnect.env (gitignored anyway, for tidiness).
#
# Usage:  bash upload_testflight.sh [path-to-ipa]
#
# Fallback if the API key is unavailable: Apple's Transporter app. It is NOT in
# Homebrew (checked 2026-09-16 — `brew install --cask transporter` fails, there
# is no such cask). It ships only through the Mac App Store:
#   https://apps.apple.com/us/app/transporter/id1450874784
set -euo pipefail

CFG="$HOME/.appstoreconnect/config.env"
[ -f "$CFG" ] && . "$CFG"

: "${ASC_KEY_ID:?Set ASC_KEY_ID in $CFG (10 characters, e.g. ABCD123XYZ)}"
: "${ASC_ISSUER_ID:?Set ASC_ISSUER_ID in $CFG (a UUID)}"

IPA="${1:-$HOME/Audioura/audio_tour_app/build/ios/ipa/audio_tour_app.ipa}"
[ -f "$IPA" ] || { echo "No IPA at $IPA — run: cd audio_tour_app && flutter build ipa --release"; exit 1; }

KEYFILE="$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"
[ -f "$KEYFILE" ] || { echo "Missing $KEYFILE"; exit 1; }

# Say out loud what is about to be shipped, read from the artifact itself.
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
( cd "$WORK" && unzip -q "$IPA" )
PLIST="$(ls -d "$WORK"/Payload/*.app/Info.plist | head -1)"
echo "Uploading:"
echo "  version   $(plutil -extract CFBundleShortVersionString raw "$PLIST")"
echo "  build     $(plutil -extract CFBundleVersion raw "$PLIST")"
echo "  bundle    $(plutil -extract CFBundleIdentifier raw "$PLIST")"
echo "  size      $(du -h "$IPA" | cut -f1)"
echo

xcrun altool --upload-app --type ios -f "$IPA" \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"

echo
echo "Uploaded. Apple processes for 5-15 minutes before it appears in TestFlight."
echo "Check: App Store Connect -> TestFlight -> iOS builds."
