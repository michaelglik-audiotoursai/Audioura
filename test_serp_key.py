"""Validate SERP_API_KEY against serper.dev — never prints the key.
Run from the development folder:  python test_serp_key.py
Also works in-container (reads os.environ first, falls back to .env file).
Stdlib only (no pip installs needed). Windows CRLF-safe.
"""
import json
import os
import sys
import urllib.request

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def read_env_key(path, name):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:  # utf-8-sig strips a BOM if Notepad added one
            for line in f:
                line = line.strip().lstrip("\ufeff")
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        return None
    return None

# Prefer os.environ (works in-container); fall back to .env file (works on host)
key = os.environ.get("SERP_API_KEY")
source = "os.environ"
if not key:
    key = read_env_key(ENV_PATH, "SERP_API_KEY")
    source = f".env ({ENV_PATH})"
if not key:
    print("FAIL: SERP_API_KEY not found in environment or .env file")
    sys.exit(1)
print(f"Source: {source}")

if "\r" in key or " " in key:
    print("WARN: key contains whitespace/CR — check the .env line")
print(f"Key loaded: {len(key)} chars, ends ...{key[-4:]}")

req = urllib.request.Request(
    "https://google.serper.dev/search",
    data=json.dumps({"q": "Chagall Song of Songs Vava dedication Nice"}).encode(),
    headers={"X-API-KEY": key, "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode())
        organic = body.get("organic", [])
        credits = resp.headers.get("X-Credits-Remaining") or body.get("credits", "n/a")
        print(f"PASS: HTTP {resp.status}, {len(organic)} organic results")
        if organic:
            print(f"  First result: {organic[0].get('title', '')[:80]}")
        print(f"  Credits info: {credits}")
except urllib.error.HTTPError as e:
    if e.code in (401, 403):
        print(f"FAIL: HTTP {e.code} — key rejected (wrong/expired key)")
    else:
        print(f"FAIL: HTTP {e.code} — {e.read().decode()[:200]}")
    sys.exit(1)
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
