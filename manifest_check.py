#!/usr/bin/env python3
"""
Startup manifest verification.

On service start, compare the build manifest against the files actually
present.  Mismatch → log at ERROR naming each differing file.

Does NOT crash the service — just makes drift impossible to miss.

Usage:
    import manifest_check
    manifest_check.verify_on_startup()    # call once at import time
    manifest_check.get_health_info()      # for /health endpoint
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("manifest_check")

MANIFEST_PATH = os.environ.get("BUILD_MANIFEST_PATH", "/app/.build_manifest.json")
APP_DIR = "/app"

# Module-level state set once at startup
_manifest_data = None
_manifest_ok = True
_drift_files = []


def _md5_file(path):
    """Return hex MD5 of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_on_startup():
    """
    Load the build manifest and compare against live files.
    Logs ERROR for every mismatch.  Sets module state for /health.
    """
    global _manifest_data, _manifest_ok, _drift_files

    if not os.path.exists(MANIFEST_PATH):
        logger.error(
            "[MANIFEST] No build manifest found at %s — "
            "image was built without manifest generation. "
            "Cannot verify code integrity.", MANIFEST_PATH
        )
        _manifest_data = None
        _manifest_ok = False
        _drift_files = ["<manifest_missing>"]
        return

    with open(MANIFEST_PATH) as f:
        _manifest_data = json.load(f)

    files = _manifest_data.get("files", {})
    mismatches = []

    for filename, expected in files.items():
        live_path = os.path.join(APP_DIR, filename)
        if not os.path.exists(live_path):
            mismatches.append(f"{filename}: MISSING (expected md5={expected['md5']})")
            continue
        live_md5 = _md5_file(live_path)
        if live_md5 != expected["md5"]:
            live_size = os.path.getsize(live_path)
            mismatches.append(
                f"{filename}: CHANGED md5 expected={expected['md5']} "
                f"actual={live_md5} (size {expected['size']}→{live_size})"
            )

    # Also check for .py files present but NOT in manifest (unexpected additions)
    manifest_names = set(files.keys())
    for entry in sorted(os.listdir(APP_DIR)):
        if entry.endswith(".py") and os.path.isfile(os.path.join(APP_DIR, entry)):
            if entry not in manifest_names:
                mismatches.append(f"{entry}: UNEXPECTED (not in build manifest)")

    _drift_files = mismatches
    _manifest_ok = len(mismatches) == 0

    if _manifest_ok:
        logger.info(
            "[MANIFEST] Startup check PASSED — %d files verified, sha=%s, built=%s",
            len(files),
            _manifest_data.get("git_sha", "unknown"),
            _manifest_data.get("build_time", "unknown"),
        )
    else:
        logger.error(
            "[MANIFEST] *** CODE DRIFT DETECTED *** %d file(s) differ from build manifest "
            "(sha=%s, built=%s):",
            len(mismatches),
            _manifest_data.get("git_sha", "unknown"),
            _manifest_data.get("build_time", "unknown"),
        )
        for m in mismatches:
            logger.error("[MANIFEST]   %s", m)


def get_health_info():
    """
    Return dict suitable for inclusion in /health response.

    {
        "code_sha": "abc123...",
        "build_time": "2026-07-31T...",
        "manifest_ok": true/false,
        "drift_files": [...]   # only present when manifest_ok is false
    }
    """
    info = {
        "code_sha": _manifest_data.get("git_sha", "unknown") if _manifest_data else "no_manifest",
        "build_time": _manifest_data.get("build_time", "unknown") if _manifest_data else "no_manifest",
        "manifest_ok": _manifest_ok,
    }
    if not _manifest_ok:
        info["drift_files"] = _drift_files
    return info


# Auto-verify on import (only inside container where /app exists)
if os.path.isdir(APP_DIR):
    verify_on_startup()
else:
    _manifest_ok = False
    _drift_files = ["<not_in_container>"]
