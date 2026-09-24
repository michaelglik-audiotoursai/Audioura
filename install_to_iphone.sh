#!/bin/bash
# install_to_iphone.sh — put the current Audioura build on Michael's iPhone.
#
# WHY THIS EXISTS: UserStopsScreen (Igor's enhancement, LOCAL-523) landed in the repo
# on 2026-09-23. The TestFlight build on the phone is from 2026-09-03 and predates it,
# so the feature cannot be tested without a fresh install. Michael chose a tethered
# install over a TestFlight upload — no Apple credential is needed and nothing is
# published.
#
# USAGE:  plug the iPhone into the Mac Mini with a cable, unlock it, then:
#             cd ~/Audioura && ./install_to_iphone.sh
#
# If the phone asks "Trust This Computer?", tap Trust and re-run.

set -u
APP_DIR="$HOME/Audioura/audio_tour_app"
cd "$APP_DIR" || { echo "✗ no $APP_DIR"; exit 1; }

echo "── 1/4  Is the phone visible? ─────────────────────────────────────────────"
DEVICES=$(flutter devices 2>/dev/null)
echo "$DEVICES" | grep -iE "ios" | grep -vi simulator

PHONE_ID=$(echo "$DEVICES" | grep -iE "•\s*ios" | grep -vi simulator \
           | head -1 | awk -F'•' '{print $2}' | tr -d ' ')

if [ -z "${PHONE_ID:-}" ]; then
  cat <<'NOPHONE'

✗ No physical iPhone found — only the simulator, or nothing at all.

  1. Plug the iPhone into the Mac Mini with a CABLE (not just the same Wi-Fi).
  2. Unlock the phone. If it asks "Trust This Computer?", tap Trust.
  3. Re-run this script.

NOPHONE
  exit 1
fi
echo "✓ using device: $PHONE_ID"

echo
echo "── 2/4  Point the app at this Mac ─────────────────────────────────────────"
# The app reads server_ip from SharedPreferences and falls back to Config.defaultServerIp.
# Confirm the compiled-in default still matches this machine's LAN address, because a
# DHCP lease change silently breaks local mode and looks like a server outage.
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
BAKED=$(grep -oE "defaultServerIp = '[0-9.]+'" lib/config.dart | grep -oE "[0-9.]+")
echo "   this Mac : ${LAN_IP:-unknown}"
echo "   baked in : ${BAKED:-unknown}"
if [ -n "${LAN_IP:-}" ] && [ "$LAN_IP" != "${BAKED:-}" ]; then
  echo "   ⚠️  MISMATCH — in the app go to Settings → server mode 'local' and set"
  echo "       the server IP to $LAN_IP by hand, or the app will call the wrong host."
else
  echo "   ✓ match"
fi

echo
echo "── 3/4  Are the local services up? ────────────────────────────────────────"
if curl -s -m 5 "http://localhost:5002/health" >/dev/null 2>&1; then
  echo "   ✓ orchestrator :5002 responding"
else
  echo "   ⚠️  orchestrator :5002 NOT responding — start it with:"
  echo "       docker compose -f docker-compose-master.yml up -d"
fi

echo
echo "── 4/4  Build and install (this takes a few minutes) ──────────────────────"
# `flutter install` puts the app on the phone and EXITS. `flutter run` would stay
# attached streaming logs until you press q, so the success message below would not
# appear until after you quit -- it looks like a hang. You want the app on the device
# to walk around with, not tethered to this terminal.
#   Need live logs for debugging instead?  flutter run --release -d "$PHONE_ID"
flutter install --release -d "$PHONE_ID"
RC=$?

echo
if [ $RC -eq 0 ]; then
  cat <<'DONE'
✓ Installed.

  To test Igor's enhancement:
    Settings → server mode = local, server IP = this Mac
    Generate Tour → specify your own stops → add each one → Generate

  What to check: the tour you get back contains the stops YOU named. If a stop
  cannot be verified at the venue it should be ANNOUNCED, never silently swapped
  for something else. A silent substitution is the bug (D562).
DONE
else
  echo "✗ flutter install exited $RC — read the error above; the phone may need to be"
  echo "  unlocked, or the bundle id may need a signing profile in Xcode."
fi
exit $RC
