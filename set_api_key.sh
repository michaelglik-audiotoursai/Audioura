#!/bin/zsh
# Safely replace a key in ~/Audioura/.env without it ever appearing on screen,
# in shell history, or in a chat transcript.
#
# Usage:
#   ./set_api_key.sh OPENAI_API_KEY
#   ./set_api_key.sh AWS_ACCESS_KEY_ID
#   ./set_api_key.sh AWS_SECRET_ACCESS_KEY
#
# Why this exists: on 2026-08-04 Michael created a new OpenAI key and edited
# .env, but the file was never written — its mtime stayed at 2026-07-21 and the
# old key was still in place. A dotfile edited in a GUI editor can silently save
# somewhere else. This writes atomically and then reads the file back to prove
# the change landed.

set -e

VAR="$1"
ENV_FILE="$HOME/Audioura/.env"

if [ -z "$VAR" ]; then
  echo "Usage: ./set_api_key.sh VARIABLE_NAME"
  echo "  e.g. ./set_api_key.sh OPENAI_API_KEY"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE does not exist."
  exit 1
fi

OLD=$(grep -E "^${VAR}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
if [ -z "$OLD" ]; then
  echo "NOTE: $VAR is not currently in .env — it will be added."
else
  echo "Current $VAR: ${OLD:0:12}... (${#OLD} chars)"
fi

echo ""
echo "Paste the NEW value and press Enter. It will NOT be shown on screen."
printf "New %s: " "$VAR"
read -rs NEWVAL
echo ""

if [ -z "$NEWVAL" ]; then
  echo "ERROR: empty value — nothing changed."
  exit 1
fi

if [ "$NEWVAL" = "$OLD" ]; then
  echo "ERROR: that is the same value that is already there — nothing changed."
  exit 1
fi

# Back up first, timestamped, so a mistake is one copy away from undone.
BACKUP="$ENV_FILE.bak.$(date +%Y%m%dT%H%M%S)"
cp "$ENV_FILE" "$BACKUP"

# Write atomically: build the new file beside it, then move it into place.
TMP=$(mktemp)
VAR="$VAR" NEWVAL="$NEWVAL" /usr/bin/python3 - "$ENV_FILE" > "$TMP" <<'PY'
import os, re, sys
var, val = os.environ["VAR"], os.environ["NEWVAL"]
text = open(sys.argv[1]).read()
line = f"{var}={val}"
if re.search(rf"(?m)^{re.escape(var)}=", text):
    text = re.sub(rf"(?m)^{re.escape(var)}=.*$", line, text)
else:
    text = text.rstrip("\n") + "\n" + line + "\n"
sys.stdout.write(text)
PY
mv "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Read it back from disk — do not trust that the write happened.
CHECK=$(grep -E "^${VAR}=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
echo ""
if [ "$CHECK" = "$NEWVAL" ]; then
  echo "✅ $VAR updated: ${CHECK:0:12}... (${#CHECK} chars)"
  echo "   Backup of the previous file: $BACKUP"
  echo ""
  echo "Next: tell Claude \"key updated\" and it will restart the containers"
  echo "and verify a real API call succeeds."
else
  echo "❌ WRITE FAILED — .env still holds the old value."
  echo "   Restoring from $BACKUP and leaving everything as it was."
  cp "$BACKUP" "$ENV_FILE"
  exit 1
fi
