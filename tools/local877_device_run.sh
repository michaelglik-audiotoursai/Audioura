#!/usr/bin/env bash
# [LOCAL-877] Drive integration_test/local877_player_resume_test.dart on an iOS
# simulator or an Android emulator, performing a REAL app background/foreground
# while the test waits, and taking screenshots at the markers.
#
#   tools/local877_device_run.sh ios     <simulator-udid>  <out-dir>
#   tools/local877_device_run.sh android <emulator-serial> <out-dir>
#
# Simulators/emulators only. Never a real phone.
set -euo pipefail
PLATFORM="$1"; DEVICE="$2"; OUT="$3"
BUNDLE=com.audioura.audiotours
ADB="${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb"
mkdir -p "$OUT"
LOG="$OUT/${PLATFORM}_run.log"
: > "$LOG"

shot() { # name
  if [ "$PLATFORM" = ios ]; then
    xcrun simctl io "$DEVICE" screenshot "$OUT/${PLATFORM}_$1.png" >/dev/null 2>&1 || true
  else
    "$ADB" -s "$DEVICE" exec-out screencap -p > "$OUT/${PLATFORM}_$1.png" || true
  fi
}
background() {
  if [ "$PLATFORM" = ios ]; then
    xcrun simctl launch "$DEVICE" com.apple.Preferences >/dev/null   # app -> background
  else
    "$ADB" -s "$DEVICE" shell input keyevent KEYCODE_HOME
  fi
}
foreground() {
  if [ "$PLATFORM" = ios ]; then
    xcrun simctl launch "$DEVICE" "$BUNDLE" >/dev/null
  else
    "$ADB" -s "$DEVICE" shell monkey -p "$BUNDLE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
  fi
}

# Marker feed the test writes to as it goes (flutter test stdout is buffered).
if [ "$PLATFORM" = ios ]; then
  MARKS=/tmp/l877_markers.txt; : > "$MARKS"
else
  MARKS="$OUT/android_markers.txt"; : > "$MARKS"
  python3 - "$MARKS" <<'PY' &
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
feed = sys.argv[1]
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        with open(feed, "a") as f:
            f.write(self.path.lstrip("/") + "\n")
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
HTTPServer(("0.0.0.0", 8877), H).serve_forever()
PY
  LOGCAT_PID=$!
  trap 'kill $LOGCAT_PID 2>/dev/null || true' EXIT
fi

( cd "$(dirname "$0")/../audio_tour_app" && \
  flutter test integration_test/local877_player_resume_test.dart -d "$DEVICE" \
    --dart-define=BACKGROUND_WAIT_SECS=14 ) >> "$LOG" 2>&1 &
TEST_PID=$!

seen() { grep -q "L877_MARKER:$1" "$MARKS"; }
wait_for() { # marker, timeout
  local t=0; until seen "$1"; do
    sleep 1; t=$((t+1))
    kill -0 $TEST_PID 2>/dev/null || { seen "$1" && return 0; echo "test ended before $1"; return 1; }
    [ $t -gt "${2:-300}" ] && { echo "timeout waiting for $1"; return 1; }
  done
  return 0
}

wait_for PLAYING_STOP1 600 && shot 1_playing_stop1
if wait_for READY_FOR_BACKGROUND 60; then
  sleep 2
  background; sleep 3; shot 2_backgrounded
  sleep 4
  foreground; sleep 2; shot 3_resumed
fi
wait_for SAME_STOP_STILL_PLAYING 90 && shot 4_same_stop_still_playing
wait_for NEXT_STOP2_PLAYING 60 && shot 5_next_stop2
wait_for PAUSED_FROM_BAR 60 && shot 6_paused_from_bar
wait $TEST_PID && echo "RESULT: PASS ($PLATFORM)" | tee -a "$LOG" || { echo "RESULT: FAIL ($PLATFORM)" | tee -a "$LOG"; exit 1; }
