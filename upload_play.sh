#!/usr/bin/env bash
# Upload the built Android App Bundle to Google Play closed testing.
#
# Dry run is the DEFAULT — nothing is committed to Play without --apply.
# Auth is short-lived impersonation of the play-publisher service account;
# there is NO service-account key file anywhere. See PLAY_UPLOAD.md.
#
# Usage:
#   bash upload_play.sh [--apply] [--notes "<text>" | --notes-file <path>] \
#                       [--aab <path>] [--track <name>]
#
# The iOS counterpart is upload_testflight.sh (Mac Mini); this matches its shape.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE" && pwd)"
TOOLS_DIR="$REPO_ROOT/tools"
VENV_DIR="$TOOLS_DIR/.venv-play"
REQ_FILE="$TOOLS_DIR/play_upload_requirements.txt"

[ -f "$REQ_FILE" ] || { echo "Missing $REQ_FILE"; exit 1; }

# Locate a Python 3 interpreter (Windows/Git Bash often only has 'py' or 'python').
PYTHON=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PYTHON="$cand"; break; fi
done
[ -n "$PYTHON" ] || { echo "No python interpreter found on PATH"; exit 1; }

# Venv Python differs by OS (Scripts on Windows, bin elsewhere).
if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
  VENV_PY="$VENV_DIR/Scripts/python.exe"
elif [ -x "$VENV_DIR/bin/python" ]; then
  VENV_PY="$VENV_DIR/bin/python"
else
  VENV_PY=""
fi

if [ -z "$VENV_PY" ]; then
  echo "Creating local venv at $VENV_DIR (gitignored)…"
  "$PYTHON" -m venv "$VENV_DIR"
  if [ -x "$VENV_DIR/Scripts/python.exe" ]; then
    VENV_PY="$VENV_DIR/Scripts/python.exe"
  else
    VENV_PY="$VENV_DIR/bin/python"
  fi
  "$VENV_PY" -m pip install --quiet --upgrade pip
  "$VENV_PY" -m pip install --quiet -r "$REQ_FILE"
fi

# keytool: prefer PATH, else the known Adoptium JDK on this laptop.
if command -v keytool >/dev/null 2>&1; then
  KEYTOOL="keytool"
elif [ -x "/c/Program Files/Eclipse Adoptium/jdk-21.0.4.7-hotspot/bin/keytool.exe" ]; then
  KEYTOOL="/c/Program Files/Eclipse Adoptium/jdk-21.0.4.7-hotspot/bin/keytool.exe"
else
  KEYTOOL="keytool"
fi
export KEYTOOL

exec "$VENV_PY" "$TOOLS_DIR/play_upload.py" --repo-root "$REPO_ROOT" --keytool "$KEYTOOL" "$@"
